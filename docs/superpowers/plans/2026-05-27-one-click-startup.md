# 一键启动脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建跨平台一键启动脚本（start.sh + start.bat），自动检测环境、安装依赖、启动服务并显示访问入口。

**Architecture:** 两个脚本分别覆盖 Unix（Linux/macOS）和 Windows 平台。脚本通过 git log 检测依赖变更，使用 venv 隔离 Python 依赖，后台启动前后端服务并轮询等待就绪。

**Tech Stack:** Bash (Linux/macOS), Batch/CMD (Windows), Python venv, npm

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `.gitignore` | 添加启动脚本生成的临时文件忽略规则 |
| Create | `start.sh` | Linux/macOS 一键启动脚本 |
| Create | `start.bat` | Windows 一键启动脚本 |

---

### Task 1: 更新 .gitignore

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: 添加忽略规则**

在 `.gitignore` 末尾追加：

```gitignore
# 启动脚本临时文件
.backend_deps_hash
.frontend_deps_hash
backend.log
frontend.log
```

- [ ] **Step 2: 验证**

```bash
grep -c "backend_deps_hash" .gitignore
```

Expected: `1`

- [ ] **Step 3: 提交**

```bash
git add .gitignore
git commit -m "chore: 添加启动脚本临时文件的 gitignore 规则"
```

---

### Task 2: 创建 start.sh（Linux/macOS）

**Files:**
- Create: `start.sh`

- [ ] **Step 1: 创建 start.sh**

```bash
cat > start.sh << 'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 一键启动脚本 — Linux + macOS
# ============================================================

# --- 颜色与符号 ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m'
CHECK="${GREEN}✓${NC}"
CROSS="${RED}✗${NC}"
WARN="${YELLOW}!${NC}"

# --- 项目根目录（脚本所在目录）---
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

# --- 日志文件 ---
BACKEND_LOG="$PROJECT_ROOT/backend.log"
FRONTEND_LOG="$PROJECT_ROOT/frontend.log"

# --- 后端/前端进程 PID ---
BACKEND_PID=""
FRONTEND_PID=""

# --- 清理函数 ---
cleanup() {
    echo ""
    echo "正在停止服务..."
    if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
        kill "$FRONTEND_PID" 2>/dev/null || true
        echo "  前端已停止 (PID: $FRONTEND_PID)"
    fi
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
        echo "  后端已停止 (PID: $BACKEND_PID)"
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

# --- 辅助函数 ---
print_step() {
    echo ""
    echo -e "[$1/6] $2..."
}

print_ok() {
    echo -e "  ${CHECK} $1"
}

print_fail() {
    echo -e "  ${CROSS} $1"
}

print_warn() {
    echo -e "  ${WARN} $1"
}

kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        # 再次检查
        pids=$(lsof -ti :"$port" 2>/dev/null || true)
        if [[ -n "$pids" ]]; then
            print_fail "端口 $port 仍被占用，请手动释放后重试"
            exit 1
        fi
    fi
}

get_dir_hash() {
    local dir=$1
    git -C "$PROJECT_ROOT" log -1 --format=%H -- "$dir" 2>/dev/null || echo "no-git"
}

check_hash_changed() {
    local hash_file=$1
    local current_hash=$2
    if [[ ! -f "$hash_file" ]]; then
        return 0 # 文件不存在，视为变更
    fi
    local saved_hash
    saved_hash=$(cat "$hash_file")
    [[ "$current_hash" != "$saved_hash" ]]
}

# ============================================================
# Step 1: 检查运行时环境
# ============================================================
print_step "1" "检查运行时环境"

if ! command -v python3 &>/dev/null; then
    print_fail "未找到 python3，请先安装 Python 3.8+"
    echo "  macOS: brew install python3"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "  Fedora: sudo dnf install python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1)
print_ok "Python $PYTHON_VERSION"

if ! command -v node &>/dev/null; then
    print_fail "未找到 node，请先安装 Node.js 16+"
    echo "  macOS: brew install node"
    echo "  Ubuntu/Debian: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install nodejs"
    exit 1
fi
NODE_VERSION=$(node --version 2>&1)

if ! command -v npm &>/dev/null; then
    print_fail "未找到 npm，请重新安装 Node.js"
    exit 1
fi
NPM_VERSION=$(npm --version 2>&1)
print_ok "Node $NODE_VERSION / npm $NPM_VERSION"

# ============================================================
# Step 2: 处理端口冲突
# ============================================================
print_step "2" "处理端口冲突"

kill_port 5409
print_ok "端口 5409 空闲"

kill_port 5173
print_ok "端口 5173 空闲"

# ============================================================
# Step 3: 准备后端环境 (venv)
# ============================================================
print_step "3" "准备后端环境 (venv)"

VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
HASH_FILE="$PROJECT_ROOT/.backend_deps_hash"
CURRENT_HASH=$(get_dir_hash "backend")

if [[ ! -d "$VENV_DIR" ]]; then
    print_ok "创建 venv..."
    python3 -m venv "$VENV_DIR"
    print_ok "安装 Python 依赖..."
    "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --quiet
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "后端环境就绪"
elif check_hash_changed "$HASH_FILE" "$CURRENT_HASH"; then
    print_ok "检测到 backend/ 有变更，更新依赖..."
    "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --quiet
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "venv 已存在，依赖无变更，跳过"
fi

# ============================================================
# Step 4: 准备前端环境 (npm)
# ============================================================
print_step "4" "准备前端环境 (npm)"

HASH_FILE="$PROJECT_ROOT/.frontend_deps_hash"
CURRENT_HASH=$(get_dir_hash "frontend")

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    print_ok "安装前端依赖..."
    (cd "$FRONTEND_DIR" && npm install --silent)
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "前端依赖就绪"
elif check_hash_changed "$HASH_FILE" "$CURRENT_HASH"; then
    print_ok "检测到 frontend/ 有变更，更新依赖..."
    (cd "$FRONTEND_DIR" && npm install --silent)
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "node_modules 已存在，依赖无变更，跳过"
fi

# ============================================================
# Step 5: 启动服务
# ============================================================
print_step "5" "启动服务"

# 启动后端
cd "$BACKEND_DIR"
nohup "$VENV_PYTHON" app.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
print_ok "后端已启动 (PID: $BACKEND_PID)"

# 启动前端
cd "$FRONTEND_DIR"
nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
print_ok "前端已启动 (PID: $FRONTEND_PID)"

cd "$PROJECT_ROOT"

# ============================================================
# Step 6: 等待服务就绪并显示入口
# ============================================================
print_step "6" "等待服务就绪"

# 等待后端
echo -n "  等待后端"
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:5409" 2>/dev/null | grep -q "200"; then
        echo ""
        print_ok "后端就绪"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo ""
        print_fail "后端启动超时，请查看 $BACKEND_LOG"
        tail -20 "$BACKEND_LOG" 2>/dev/null || true
        exit 1
    fi
    echo -n "."
    sleep 1
done

# 等待前端
echo -n "  等待前端"
for i in $(seq 1 30); do
    if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:5173" 2>/dev/null | grep -q "200"; then
        echo ""
        print_ok "前端就绪"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo ""
        print_fail "前端启动超时，请查看 $FRONTEND_LOG"
        tail -20 "$FRONTEND_LOG" 2>/dev/null || true
        exit 1
    fi
    echo -n "."
    sleep 1
done

# 显示访问入口
echo ""
echo "============================================"
echo -e "  ${GREEN}前端界面: http://localhost:5173${NC}"
echo -e "  ${GREEN}后端 API: http://localhost:5409${NC}"
echo "============================================"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 保持脚本运行，等待子进程
wait
SCRIPT
chmod +x start.sh
```

- [ ] **Step 2: 验证脚本语法**

```bash
bash -n start.sh
```

Expected: 无输出（语法正确）

- [ ] **Step 3: 验证脚本可执行**

```bash
ls -la start.sh | grep -q "x" && echo "OK" || echo "FAIL"
```

Expected: `OK`

- [ ] **Step 4: 提交**

```bash
git add start.sh
git commit -m "feat: 添加 Linux/macOS 一键启动脚本 start.sh"
```

---

### Task 3: 创建 start.bat（Windows）

**Files:**
- Create: `start.bat`

- [ ] **Step 1: 创建 start.bat**

```bat
@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: 一键启动脚本 — Windows
:: ============================================================

:: --- 项目根目录（脚本所在目录）---
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"

:: --- 日志文件 ---
set "BACKEND_LOG=%PROJECT_ROOT%\backend.log"
set "FRONTEND_LOG=%PROJECT_ROOT%\frontend.log"

:: ============================================================
:: Step 1: 检查运行时环境
:: ============================================================
echo.
echo [1/6] 检查运行时环境...

python --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 python，请先安装 Python 3.8+
    echo   下载地址: https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYTHON_VER=%%i"
echo   ✓ %PYTHON_VER%

node --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 node，请先安装 Node.js 16+
    echo   下载地址: https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set "NODE_VER=%%i"

npm --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 npm，请重新安装 Node.js
    exit /b 1
)
for /f "tokens=*" %%i in ('npm --version') do set "NPM_VER=%%i"
echo   ✓ Node %NODE_VER% / npm %NPM_VER%

:: ============================================================
:: Step 2: 处理端口冲突
:: ============================================================
echo.
echo [2/6] 处理端口冲突...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5409 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   ✓ 端口 5409 空闲

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   ✓ 端口 5173 空闲

:: ============================================================
:: Step 3: 准备后端环境 (venv)
:: ============================================================
echo.
echo [3/6] 准备后端环境 (venv)...

set "VENV_DIR=%BACKEND_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "HASH_FILE=%PROJECT_ROOT%\.backend_deps_hash"

:: 获取 backend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- backend 2^>nul') do set "CURRENT_HASH=%%i"
if "%CURRENT_HASH%"=="" set "CURRENT_HASH=no-git"

if not exist "%VENV_DIR%" (
    echo   ✓ 创建 venv...
    python -m venv "%VENV_DIR%"
    echo   ✓ 安装 Python 依赖...
    "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --quiet
    echo %CURRENT_HASH%> "%HASH_FILE%"
    echo   ✓ 后端环境就绪
) else (
    :: 检查 hash 是否变更
    set "SAVED_HASH="
    if exist "%HASH_FILE%" (
        for /f "tokens=*" %%i in ('type "%HASH_FILE%"') do set "SAVED_HASH=%%i"
    ) else (
        set "SAVED_HASH=none"
    )
    if "%CURRENT_HASH%"=="!SAVED_HASH!" (
        echo   ✓ venv 已存在，依赖无变更，跳过
    ) else (
        echo   ✓ 检测到 backend/ 有变更，更新依赖...
        "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --quiet
        echo %CURRENT_HASH%> "%HASH_FILE%"
        echo   ✓ 依赖更新完成
    )
)

:: ============================================================
:: Step 4: 准备前端环境 (npm)
:: ============================================================
echo.
echo [4/6] 准备前端环境 (npm)...

set "HASH_FILE=%PROJECT_ROOT%\.frontend_deps_hash"

:: 获取 frontend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- frontend 2^>nul') do set "CURRENT_HASH=%%i"
if "%CURRENT_HASH%"=="" set "CURRENT_HASH=no-git"

if not exist "%FRONTEND_DIR%\node_modules" (
    echo   ✓ 安装前端依赖...
    cd /d "%FRONTEND_DIR%"
    call npm install --silent
    echo %CURRENT_HASH%> "%HASH_FILE%"
    echo   ✓ 前端依赖就绪
) else (
    set "SAVED_HASH="
    if exist "%HASH_FILE%" (
        for /f "tokens=*" %%i in ('type "%HASH_FILE%"') do set "SAVED_HASH=%%i"
    ) else (
        set "SAVED_HASH=none"
    )
    if "%CURRENT_HASH%"=="!SAVED_HASH!" (
        echo   ✓ node_modules 已存在，依赖无变更，跳过
    ) else (
        echo   ✓ 检测到 frontend/ 有变更，更新依赖...
        cd /d "%FRONTEND_DIR%"
        call npm install --silent
        echo %CURRENT_HASH%> "%HASH_FILE%"
        echo   ✓ 依赖更新完成
    )
)

:: ============================================================
:: Step 5: 启动服务
:: ============================================================
echo.
echo [5/6] 启动服务...

cd /d "%BACKEND_DIR%"
start "SAU-Backend" /B cmd /c ""%VENV_PYTHON%" app.py > "%BACKEND_LOG%" 2>&1"
echo   ✓ 后端已启动

cd /d "%FRONTEND_DIR%"
start "SAU-Frontend" /B cmd /c "npm run dev > "%FRONTEND_LOG%" 2>&1"
echo   ✓ 前端已启动

cd /d "%PROJECT_ROOT%"

:: ============================================================
:: Step 6: 等待服务就绪并显示入口
:: ============================================================
echo.
echo [6/6] 等待服务就绪...

:: 等待后端
echo   等待后端...
set /a "COUNT=0"
:wait_backend
set /a "COUNT+=1"
if %COUNT% GTR 30 (
    echo   X 后端启动超时，请查看 %BACKEND_LOG%
    exit /b 1
)
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:5409 2>nul | findstr "200" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_backend
)
echo   ✓ 后端就绪

:: 等待前端
echo   等待前端...
set /a "COUNT=0"
:wait_frontend
set /a "COUNT+=1"
if %COUNT% GTR 30 (
    echo   X 前端启动超时，请查看 %FRONTEND_LOG%
    exit /b 1
)
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:5173 2>nul | findstr "200" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_frontend
)
echo   ✓ 前端就绪

:: 显示访问入口
echo.
echo ============================================
echo   前端界面: http://localhost:5173
echo   后端 API: http://localhost:5409
echo ============================================
echo.
echo 按任意键停止所有服务...
pause >nul

:: 停止服务
taskkill /FI "WINDOWTITLE eq SAU-Backend*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq SAU-Frontend*" >nul 2>&1
echo 服务已停止

endlocal
```

- [ ] **Step 2: 验证脚本编码**

```bash
file start.bat | grep -q "ASCII\|UTF-8\|text" && echo "OK" || echo "FAIL"
```

Expected: `OK`

- [ ] **Step 3: 提交**

```bash
git add start.bat
git commit -m "feat: 添加 Windows 一键启动脚本 start.bat"
```

---

### Task 4: 端到端验证（Linux 环境）

- [ ] **Step 1: 运行 start.sh 验证完整流程**

```bash
./start.sh &
START_PID=$!
sleep 15
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5409
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5173
kill $START_PID 2>/dev/null
```

Expected: 两个 `200`

- [ ] **Step 2: 验证二次启动跳过依赖安装**

再次运行，确认输出包含"跳过"字样，不重复安装依赖。

- [ ] **Step 3: 最终提交**

```bash
git add -A
git status
git commit -m "feat: 完成一键启动脚本（Linux/macOS/Windows）"
```
