#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 一键启动脚本 — Linux + macOS
# ============================================================

# --- 颜色与符号 ---
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'
CHECK="${GREEN}✓${NC}"
CROSS="${RED}✗${NC}"
WARN="${YELLOW}!${NC}"
SPINNER=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

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
    if [[ -n "${TAIL_PID:-}" ]] && kill -0 "$TAIL_PID" 2>/dev/null; then
        kill "$TAIL_PID" 2>/dev/null || true
    fi
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

# 带旋转动画的等待命令执行
# 用法: run_with_spinner "提示信息" command [args...]
run_with_spinner() {
    local msg="$1"
    shift
    local cmd=("$@")
    local tmp_log
    tmp_log=$(mktemp)

    echo -n -e "  ${CYAN}⏳${NC} ${msg}"

    # 后台执行命令
    "${cmd[@]}" > "$tmp_log" 2>&1 &
    local pid=$!
    local i=0

    while kill -0 "$pid" 2>/dev/null; do
        printf "\r  ${CYAN}%s${NC} %s" "${SPINNER[$i]}" "$msg"
        i=$(( (i + 1) % ${#SPINNER[@]} ))
        sleep 0.2
    done

    wait "$pid" 2>/dev/null
    local exit_code=$?
    rm -f "$tmp_log"

    if [[ $exit_code -eq 0 ]]; then
        printf "\r  ${CHECK} %s\n" "$msg"
    else
        printf "\r  ${CROSS} %s\n" "$msg"
        return 1
    fi
}

kill_port() {
    local port=$1
    local pids
    pids=$(lsof -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
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
        return 0
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
    echo "    macOS:         brew install python3"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo "    Fedora:        sudo dnf install python3"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_ok "Python ${PYTHON_VERSION}"

if ! command -v node &>/dev/null; then
    print_fail "未找到 node，请先安装 Node.js 16+"
    echo "    macOS:         brew install node"
    echo "    Ubuntu/Debian: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install nodejs"
    exit 1
fi
NODE_VERSION=$(node --version 2>&1)

if ! command -v npm &>/dev/null; then
    print_fail "未找到 npm，请重新安装 Node.js"
    exit 1
fi
NPM_VERSION=$(npm --version 2>&1)
print_ok "Node ${NODE_VERSION} / npm ${NPM_VERSION}"

if ! command -v curl &>/dev/null; then
    print_fail "未找到 curl，请先安装 curl"
    echo "    macOS:         brew install curl"
    echo "    Ubuntu/Debian: sudo apt install curl"
    echo "    Fedora:        sudo dnf install curl"
    exit 1
fi
print_ok "curl $(curl --version 2>&1 | head -1 | awk '{print $2}')"

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
print_step "3" "准备后端环境"

VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
HASH_FILE="$PROJECT_ROOT/.backend_deps_hash"
CURRENT_HASH=$(get_dir_hash "backend")

if [[ ! -d "$VENV_DIR" ]] || [[ ! -f "$VENV_PIP" ]]; then
    echo -n -e "  ${CYAN}⏳${NC} 创建虚拟环境..."
    rm -rf "$VENV_DIR"
    if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
        printf "\r  ${WARN} 虚拟环境创建失败，正在安装 python3-venv...\n"
        PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if command -v apt-get &>/dev/null; then
            sudo apt-get install -y "python${PYTHON_VER}-venv" >/dev/null 2>&1 || {
                print_fail "安装 python3-venv 失败，请手动执行: sudo apt install python${PYTHON_VER}-venv"
                exit 1
            }
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3-venv >/dev/null 2>&1 || {
                print_fail "安装 python3-venv 失败，请手动执行: sudo dnf install python3-venv"
                exit 1
            }
        fi
        python3 -m venv "$VENV_DIR"
    fi
    printf "\r  ${CHECK} 虚拟环境创建完成\n"
    "$VENV_PIP" cache purge >/dev/null 2>&1 || true
    run_with_spinner "安装 Python 依赖（首次安装，请稍候）" "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --quiet --no-cache-dir
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "后端环境就绪"
elif check_hash_changed "$HASH_FILE" "$CURRENT_HASH"; then
    "$VENV_PIP" cache purge >/dev/null 2>&1 || true
    run_with_spinner "检测到变更，更新 Python 依赖" "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --quiet --no-cache-dir
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "依赖无变更，跳过"
fi

# ============================================================
# Step 4: 准备前端环境 (npm)
# ============================================================
print_step "4" "准备前端环境"

HASH_FILE="$PROJECT_ROOT/.frontend_deps_hash"
CURRENT_HASH=$(get_dir_hash "frontend")

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    run_with_spinner "安装前端依赖（首次安装，请稍候）" bash -c "cd '$FRONTEND_DIR' && npm install --prefer-offline 2>&1 | tail -1"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "前端依赖就绪"
elif check_hash_changed "$HASH_FILE" "$CURRENT_HASH"; then
    run_with_spinner "检测到变更，更新前端依赖" bash -c "cd '$FRONTEND_DIR' && npm install --prefer-offline 2>&1 | tail -1"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "依赖无变更，跳过"
fi

# ============================================================
# Step 5: 启动服务
# ============================================================
print_step "5" "启动服务"

# 确保端口完全释放
for i in $(seq 1 5); do
    if ! lsof -ti :5409 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

cd "$BACKEND_DIR"
export SAU_PORT=5409
# 清除系统代理，避免 cloakbrowser/httpx 读取到不支持的 socks:// 代理
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
nohup "$VENV_PYTHON" app.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
print_ok "后端已启动 (PID: $BACKEND_PID)"

cd "$FRONTEND_DIR"
nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
print_ok "前端已启动 (PID: $FRONTEND_PID)"

cd "$PROJECT_ROOT"

# ============================================================
# Step 6: 等待服务就绪并显示入口
# ============================================================
print_step "6" "等待服务就绪"

# 从日志中获取后端实际端口（后端可能因端口竞争回退到其他端口）
BACKEND_PORT=5409
echo -n "  等待后端就绪"
for i in $(seq 1 30); do
    # 检测日志中的实际端口（使用 sed 替代 grep -P，兼容 macOS）
    if [[ -f "$BACKEND_LOG" ]]; then
        detected_port=$(sed -n 's/.*Serving on http:\/\/0\.0\.0\.0:\([0-9]*\).*/\1/p' "$BACKEND_LOG" 2>/dev/null | tail -1)
        if [[ -n "$detected_port" ]]; then
            BACKEND_PORT="$detected_port"
        fi
    fi
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${BACKEND_PORT}/api/health" 2>/dev/null || true)
    if [[ "$http_code" == "200" ]]; then
        echo ""
        print_ok "后端就绪 (端口: ${BACKEND_PORT})"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo ""
        print_fail "后端启动超时，请查看日志: $BACKEND_LOG"
        tail -20 "$BACKEND_LOG" 2>/dev/null || true
        exit 1
    fi
    echo -n "."
    sleep 1
done

echo -n "  等待前端就绪"
for i in $(seq 1 30); do
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:5173" 2>/dev/null || true)
    if [[ "$http_code" == "200" ]]; then
        echo ""
        print_ok "前端就绪"
        break
    fi
    if [[ $i -eq 30 ]]; then
        echo ""
        print_fail "前端启动超时，请查看日志: $FRONTEND_LOG"
        tail -20 "$FRONTEND_LOG" 2>/dev/null || true
        exit 1
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "============================================"
echo -e "  ${GREEN}前端界面: http://localhost:5173${NC}"
echo -e "  ${GREEN}后端 API: http://localhost:${BACKEND_PORT}${NC}"
echo "============================================"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""
echo "--- 后端日志 ---"

tail -f "$BACKEND_LOG" &
TAIL_PID=$!
trap "kill $TAIL_PID 2>/dev/null; cleanup" SIGINT SIGTERM

wait || true
