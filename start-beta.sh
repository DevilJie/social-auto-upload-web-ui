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
MCP_DIR="$PROJECT_ROOT/backend-mcp"

# --- 本地依赖目录（优先使用）---
DEP_DIR="$PROJECT_ROOT/dependency"
DEP_BIN_DIR="$DEP_DIR/bin"
if [[ -d "$DEP_BIN_DIR" ]]; then
    export PATH="$DEP_BIN_DIR:$DEP_DIR/python/bin:$DEP_DIR/git/bin:$DEP_DIR/node/bin:$PATH"
fi

# CloakBrowser: 如果 dependency/cloakbrowser/ 下有 chrome 二进制，优先使用
CLOAKBROWSER_LOCAL="$DEP_DIR/cloakbrowser"
if [[ -f "$CLOAKBROWSER_LOCAL/chrome" ]]; then
    export CLOAKBROWSER_BINARY_PATH="$CLOAKBROWSER_LOCAL/chrome"
fi

# --- 项目代码管理（git clone / update）---
REPO_URL="https://github.com/DevilJie/social-auto-upload-web-ui.git"
MAIN_BRANCH="beta"

if [[ ! -d "$BACKEND_DIR" ]]; then
    # 首次使用：没有项目代码，从 GitHub 克隆
    if ! command -v git &>/dev/null; then
        echo -e "${CROSS} 未找到 git，无法克隆项目代码"
        exit 1
    fi
    echo ""
    echo -e "${CYAN}首次使用，正在从 GitHub 拉取项目代码...${NC}"
    cd "$PROJECT_ROOT"
    git init
    git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
    if ! git fetch origin "$MAIN_BRANCH"; then
        print_fail "无法连接 GitHub，请检查网络连接"
        echo "  如果无法访问 GitHub，请手动下载项目代码到当前目录"
        echo "  仓库地址: $REPO_URL"
        exit 1
    fi
    git checkout -f "$MAIN_BRANCH"
    echo -e "${CHECK} 项目代码拉取完成"
    echo ""
    exec bash "$PROJECT_ROOT/start.sh"
fi

# 已有项目代码：强制更新
if command -v git &>/dev/null && [[ -d "$PROJECT_ROOT/.git" ]]; then
    cd "$PROJECT_ROOT"
    git checkout "$MAIN_BRANCH" 2>/dev/null
    if git fetch origin "$MAIN_BRANCH" 2>/dev/null; then
        LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "")
        REMOTE=$(git rev-parse "origin/$MAIN_BRANCH" 2>/dev/null || echo "")
        if [[ -n "$REMOTE" && "$LOCAL" != "$REMOTE" ]]; then
            echo ""
            echo -e "${CYAN}发现新版本！是否更新？[Y/n]  更新将覆盖本地修改，未提交的代码将丢失${NC}"
            read -r answer
            if [[ ! "$answer" =~ ^[Nn]$ ]]; then
                git reset --hard "origin/$MAIN_BRANCH"
                echo -e "${CHECK} 更新完成，重新启动..."
                exec bash "$PROJECT_ROOT/start.sh"
            fi
        fi
    fi
fi

# --- 日志文件 ---
BACKEND_LOG="$PROJECT_ROOT/backend.log"
FRONTEND_LOG="$PROJECT_ROOT/frontend.log"
MCP_LOG="$PROJECT_ROOT/mcp.log"

# --- 后端/前端/MCP 进程 PID ---
BACKEND_PID=""
FRONTEND_PID=""
MCP_PID=""

# --- MCP transport mode（默认 sse 适合后台 daemon；stdio 需父进程喂 stdin）---
TRANSPORT_MODE="${MCP_TRANSPORT_MODE:-sse}"

# --- 清理函数 ---
cleanup() {
    echo ""
    echo "正在停止服务..."
    if [[ -n "${TAIL_PID:-}" ]] && kill -0 "$TAIL_PID" 2>/dev/null; then
        kill "$TAIL_PID" 2>/dev/null || true
    fi
    if [[ -n "$MCP_PID" ]] && kill -0 "$MCP_PID" 2>/dev/null; then
        kill "$MCP_PID" 2>/dev/null || true
        echo "  MCP 已停止 (PID: $MCP_PID)"
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
    pids=$(lsof -P -n -ti :"$port" 2>/dev/null || true)
    if [[ -n "$pids" ]]; then
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        pids=$(lsof -P -n -ti :"$port" 2>/dev/null || true)
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

# --- 检测系统包管理器，用于给出安装提示 ---
detect_pkg_manager() {
    if [[ "$(uname -s)" == "Darwin" ]]; then
        echo "brew"
    elif command -v apt-get &>/dev/null; then
        echo "apt"
    elif command -v dnf &>/dev/null; then
        echo "dnf"
    elif command -v yum &>/dev/null; then
        echo "yum"
    elif command -v pacman &>/dev/null; then
        echo "pacman"
    else
        echo "unknown"
    fi
}
PKG_MGR=$(detect_pkg_manager)

# 根据系统给出安装命令
install_hint() {
    local pkg="$1"
    case "$PKG_MGR" in
        brew)
            echo "    安装命令: brew install ${pkg}"
            ;;
        apt)
            echo "    安装命令: sudo apt install ${pkg}"
            ;;
        dnf)
            echo "    安装命令: sudo dnf install ${pkg}"
            ;;
        yum)
            echo "    安装命令: sudo yum install ${pkg}"
            ;;
        pacman)
            echo "    安装命令: sudo pacman -S ${pkg}"
            ;;
        *)
            echo "    请手动安装: ${pkg}"
            ;;
    esac
}

# 判断命令来源：内置 (dependency/) 还是系统
cmd_source() {
    local cmd_path
    cmd_path=$(command -v "$1" 2>/dev/null || true)
    if [[ -n "$cmd_path" && "$cmd_path" == "$DEP_DIR"* ]]; then
        echo "内置"
    else
        echo "系统"
    fi
}

if ! command -v python3 &>/dev/null; then
    print_fail "未找到 python3，请先安装 Python 3.8+"
    install_hint "python3 python3-venv python3-pip"
    exit 1
fi
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
print_ok "Python ${PYTHON_VERSION} ($(cmd_source python3))"

if ! command -v node &>/dev/null; then
    print_fail "未找到 node，请先安装 Node.js 16+"
    if [[ "$PKG_MGR" == "brew" ]]; then
        echo "    安装命令: brew install node"
    else
        echo "    安装命令: curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install nodejs"
    fi
    exit 1
fi
NODE_VERSION=$(node --version 2>&1)

if ! command -v npm &>/dev/null; then
    print_fail "未找到 npm，请重新安装 Node.js"
    exit 1
fi
NPM_VERSION=$(npm --version 2>&1)
print_ok "Node ${NODE_VERSION} / npm ${NPM_VERSION} ($(cmd_source node))"

if ! command -v curl &>/dev/null; then
    print_fail "未找到 curl"
    install_hint "curl"
    exit 1
fi
print_ok "curl $(curl --version 2>&1 | head -1 | awk '{print $2}') ($(cmd_source curl))"

if ! command -v ffmpeg &>/dev/null; then
    print_fail "未找到 ffmpeg"
    install_hint "ffmpeg"
    exit 1
fi
print_ok "ffmpeg $(ffmpeg -version 2>&1 | head -1 | awk '{print $3}') ($(cmd_source ffmpeg))"

if ! command -v ffprobe &>/dev/null; then
    print_fail "未找到 ffprobe，请先安装 ffmpeg（包含 ffprobe）"
    exit 1
fi
print_ok "ffprobe 已安装 ($(cmd_source ffprobe))"

# 清除系统代理，避免 httpx/cloakbrowser 读取到不支持的 socks:// 代理
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY

# ============================================================
# Step 2: 处理端口冲突
# ============================================================
print_step "2" "处理端口冲突"

kill_port 5409
print_ok "端口 5409 空闲"

kill_port 5173
print_ok "端口 5173 空闲"

kill_port 5410
print_ok "端口 5410 空闲"

# ============================================================
# Step 3: 准备后端环境 (venv)
# ============================================================
print_step "3" "准备后端环境"

VENV_DIR="$BACKEND_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python3"
VENV_PIP="$VENV_DIR/bin/pip"
PIP_MIRROR="https://mirrors.aliyun.com/pypi/simple/"
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
    echo -e "  ${CYAN}安装 Python 依赖（首次安装，请稍候）...${NC}"
    "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --no-cache-dir -i "$PIP_MIRROR"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "后端环境就绪"
elif check_hash_changed "$HASH_FILE" "$CURRENT_HASH"; then
    "$VENV_PIP" cache purge >/dev/null 2>&1 || true
    echo -e "  ${CYAN}检测到变更，更新 Python 依赖...${NC}"
    "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt" --no-cache-dir -i "$PIP_MIRROR"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "依赖无变更，跳过"
fi

# 检查 CloakBrowser 二进制文件
CLOAKBROWSER_DIR="$HOME/.cloakbrowser"
if [[ -n "${CLOAKBROWSER_BINARY_PATH:-}" ]]; then
    print_ok "CloakBrowser (本地依赖)"
elif ! ls "$CLOAKBROWSER_DIR"/chromium-*/chrome >/dev/null 2>&1; then
    echo -e "  ${CYAN}📥 首次使用，下载 CloakBrowser 浏览器${NC}"

    # 从 Python 获取下载信息
    DOWNLOAD_INFO=$("$VENV_PYTHON" -c "
import cloakbrowser.download as d
print(d.get_fallback_download_url())
print(d.get_binary_dir())
print(d.get_binary_path())
" 2>/dev/null)

    DOWNLOAD_URL=$(echo "$DOWNLOAD_INFO" | sed -n '1p')
    BINARY_DIR=$(echo "$DOWNLOAD_INFO" | sed -n '2p')
    BINARY_PATH=$(echo "$DOWNLOAD_INFO" | sed -n '3p')

    if [[ -z "$DOWNLOAD_URL" ]]; then
        print_fail "无法获取下载地址"
        exit 1
    fi

    # 使用 curl 下载（带进度条）
    TMP_FILE=$(mktemp /tmp/cloakbrowser-XXXXXX.tar.gz)
    echo -e "  ${CYAN}⬇  下载地址: ${DOWNLOAD_URL}${NC}"
    echo ""

    if ! curl -L -# -o "$TMP_FILE" "$DOWNLOAD_URL"; then
        # 主下载失败，尝试 GitHub 备用地址
        GITHUB_URL=$(echo "$DOWNLOAD_URL" | sed 's|cloakbrowser.dev|github.com/CloakHQ/cloakbrowser/releases/download|')
        echo ""
        echo -e "  ${WARN} 主下载失败，尝试 GitHub 备用地址..."
        if ! curl -L -# -o "$TMP_FILE" "$GITHUB_URL"; then
            rm -f "$TMP_FILE"
            print_fail "CloakBrowser 下载失败，请检查网络连接"
            exit 1
        fi
    fi

    # 解压到目标目录
    echo ""
    echo -n -e "  ${CYAN}📦 解压中...${NC}"
    mkdir -p "$BINARY_DIR"
    tar -xzf "$TMP_FILE" -C "$BINARY_DIR" 2>/dev/null
    rm -f "$TMP_FILE"

    # 确保二进制文件可执行
    chmod +x "$BINARY_PATH" 2>/dev/null
    chmod +x "$BINARY_DIR"/chrome-bin/chrome 2>/dev/null

    if [[ -f "$BINARY_PATH" ]] || ls "$BINARY_DIR"/chrome-bin/chrome >/dev/null 2>&1; then
        printf "\r  ${CHECK} CloakBrowser 下载完成\n"
    else
        printf "\r  ${CROSS} CloakBrowser 解压失败\n"
        exit 1
    fi
else
    print_ok "CloakBrowser 已安装"
fi

# ============================================================
# Step 4: 准备前端环境 (npm)
# ============================================================
print_step "4" "准备前端 + MCP 环境"

HASH_FILE="$PROJECT_ROOT/.frontend_deps_hash"
CURRENT_HASH=$(get_dir_hash "frontend")

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    run_with_spinner "安装前端依赖（首次安装，请稍候）" bash -c "cd '$FRONTEND_DIR' && npm install --prefer-offline --registry=https://registry.npmmirror.com 2>&1 | tail -1"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "前端依赖就绪"
elif check_hash_changed "$HASH_FILE" "$CURRENT_HASH"; then
    run_with_spinner "检测到变更，更新前端依赖" bash -c "cd '$FRONTEND_DIR' && npm install --prefer-offline --registry=https://registry.npmmirror.com 2>&1 | tail -1"
    echo "$CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "依赖无变更，跳过"
fi

# --- MCP: install deps + build ---
HASH_FILE="$PROJECT_ROOT/.mcp_deps_hash"
MCP_CURRENT_HASH=$(get_dir_hash "backend-mcp")

if [[ ! -d "$MCP_DIR/node_modules" ]]; then
    run_with_spinner "安装 MCP 依赖（首次安装，请稍候）" bash -c "cd '$MCP_DIR' && npm install --prefer-offline --registry=https://registry.npmmirror.com 2>&1 | tail -1"
    echo "$MCP_CURRENT_HASH" > "$HASH_FILE"
    print_ok "MCP 依赖就绪"
elif check_hash_changed "$HASH_FILE" "$MCP_CURRENT_HASH"; then
    run_with_spinner "检测到变更，更新 MCP 依赖" bash -c "cd '$MCP_DIR' && npm install --prefer-offline --registry=https://registry.npmmirror.com 2>&1 | tail -1"
    echo "$MCP_CURRENT_HASH" > "$HASH_FILE"
    print_ok "依赖更新完成"
else
    print_ok "依赖无变更，跳过"
fi

# 始终重新编译 MCP（保证 dist/ 与 src/ 同步）
run_with_spinner "编译 MCP (tsc)" bash -c "cd '$MCP_DIR' && npm run build 2>&1 | tail -5"
print_ok "MCP 编译完成"

# ============================================================
# Step 5: 启动服务
# ============================================================
print_step "5" "启动服务"

# 确保端口完全释放
for i in $(seq 1 5); do
    if ! lsof -P -n -ti :5409 >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

cd "$BACKEND_DIR"
export SAU_PORT=5409
nohup "$VENV_PYTHON" app.py > "$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!
print_ok "后端已启动 (PID: $BACKEND_PID)"

cd "$FRONTEND_DIR"
nohup npm run dev > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
print_ok "前端已启动 (PID: $FRONTEND_PID)"

cd "$MCP_DIR"
export TRANSPORT_MODE
nohup npm start > "$MCP_LOG" 2>&1 &
MCP_PID=$!
print_ok "MCP 已启动 (PID: $MCP_PID, transport: $TRANSPORT_MODE)"

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

# 等待 MCP（stdio 模式只要进程存活就 OK；sse/both 等端口 5410 监听）
echo -n "  等待 MCP 就绪"
for i in $(seq 1 15); do
    if ! kill -0 "$MCP_PID" 2>/dev/null; then
        echo ""
        print_fail "MCP 启动失败，请查看日志: $MCP_LOG"
        tail -20 "$MCP_LOG" 2>/dev/null || true
        exit 1
    fi
    if [[ "$TRANSPORT_MODE" == "sse" || "$TRANSPORT_MODE" == "both" ]]; then
        if lsof -P -n -ti :5410 >/dev/null 2>&1; then
            echo ""
            print_ok "MCP 就绪 (SSE 端口 5410)"
            break
        fi
    else
        # stdio 模式进程存活即就绪
        echo ""
        print_ok "MCP 就绪 (stdio)"
        break
    fi
    if [[ $i -eq 15 ]]; then
        echo ""
        print_warn "MCP 启动检查超时（15 秒），但进程仍在运行"
        break
    fi
    echo -n "."
    sleep 1
done

echo ""
echo "============================================"
echo -e "  ${GREEN}前端界面: http://localhost:5173${NC}"
echo -e "  ${GREEN}后端 API: http://localhost:${BACKEND_PORT}${NC}"
if [[ "$TRANSPORT_MODE" == "sse" || "$TRANSPORT_MODE" == "both" ]]; then
    echo -e "  ${GREEN}MCP  SSE:  http://localhost:5410/sse${NC}"
else
    echo -e "  ${GREEN}MCP  stdio: 启动中 (transport=$TRANSPORT_MODE)${NC}"
fi
echo "============================================"
echo ""
echo "按 Ctrl+C 停止所有服务"
echo ""
echo "--- 后端日志 ---"

tail -f "$BACKEND_LOG" &
TAIL_PID=$!
trap "kill $TAIL_PID 2>/dev/null; cleanup" SIGINT SIGTERM

wait || true
