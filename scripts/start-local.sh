#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
DEP_DIR="$ROOT_DIR/dependency"
DEP_BIN_DIR="$DEP_DIR/bin"

if [[ -d "$DEP_BIN_DIR" ]]; then
  export PATH="$DEP_BIN_DIR:$DEP_DIR/python/bin:$DEP_DIR/git/bin:$DEP_DIR/node/bin:$PATH"
fi

if [[ -f "$DEP_DIR/cloakbrowser/chrome" ]]; then
  export CLOAKBROWSER_BINARY_PATH="$DEP_DIR/cloakbrowser/chrome"
fi

HOST="${HOST:-127.0.0.1}"
SAU_PORT="${SAU_PORT:-17409}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
VITE_API_BASE_URL="${VITE_API_BASE_URL:-http://${HOST}:${SAU_PORT}}"

BACKEND_LOG="$ROOT_DIR/backend.log"
FRONTEND_LOG="$ROOT_DIR/frontend.log"
VENV_DIR="${BACKEND_VENV:-$BACKEND_DIR/venv}"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

BACKEND_PID=""
FRONTEND_PID=""

log() {
  printf '%s\n' "$1"
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

cleanup() {
  local code=$?
  trap - EXIT INT TERM

  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi

  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi

  exit "$code"
}

trap cleanup EXIT INT TERM

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

port_in_use() {
  local port="$1"

  if command_exists lsof; then
    lsof -P -n -ti :"$port" >/dev/null 2>&1
    return $?
  fi

  if command_exists nc; then
    nc -z "$HOST" "$port" >/dev/null 2>&1
    return $?
  fi

  return 1
}

wait_for_http() {
  local name="$1"
  local url="$2"
  local log_file="$3"
  local pid="${4:-}"

  printf '等待 %s 启动' "$name"
  for _ in $(seq 1 60); do
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      printf '\n'
      printf '%s 进程已退出，最近日志如下：\n' "$name" >&2
      tail -40 "$log_file" >&2 || true
      return 1
    fi

    if curl -fsS "$url" >/dev/null 2>&1; then
      printf '\n'
      return 0
    fi

    printf '.'
    sleep 1
  done

  printf '\n'
  printf '%s 启动超时，最近日志如下：\n' "$name" >&2
  tail -40 "$log_file" >&2 || true
  return 1
}

bootstrap_repo_if_missing() {
  if [[ -d "$BACKEND_DIR" && -d "$FRONTEND_DIR" ]]; then
    return 0
  fi

  command_exists git || fail "当前目录缺少项目代码，且未找到 git，无法自动拉取仓库"

  log "当前目录缺少 backend/frontend，正在拉取项目代码..."
  (
    cd "$ROOT_DIR"
    git init
    git remote add origin "https://github.com/DevilJie/social-auto-upload-web-ui.git" 2>/dev/null || git remote set-url origin "https://github.com/DevilJie/social-auto-upload-web-ui.git"
    git fetch --depth=1 origin master
    git checkout -f FETCH_HEAD
  )

  exec bash "$ROOT_DIR/start.sh" "$@"
}

ensure_backend_env() {
  command_exists python3 || fail "未找到 python3，请先安装 Python 3.10+"

  if [[ ! -x "$VENV_PYTHON" ]]; then
    log "创建后端虚拟环境: $VENV_DIR"
    python3 -m venv "$VENV_DIR"
  fi

  if [[ ! -f "$VENV_DIR/.requirements-installed" || "$BACKEND_DIR/requirements.txt" -nt "$VENV_DIR/.requirements-installed" ]]; then
    log "安装/更新后端依赖"
    "$VENV_PIP" install -r "$BACKEND_DIR/requirements.txt"
    touch "$VENV_DIR/.requirements-installed"
  fi
}

ensure_frontend_env() {
  command_exists node || fail "未找到 node，请先安装 Node.js 18+"
  command_exists npm || fail "未找到 npm，请先安装 Node.js 18+"

  local marker="$FRONTEND_DIR/node_modules/.sau-deps-installed"
  if [[ ! -d "$FRONTEND_DIR/node_modules" || ! -f "$marker" || "$FRONTEND_DIR/package.json" -nt "$marker" || "$FRONTEND_DIR/package-lock.json" -nt "$marker" ]]; then
    log "安装/更新前端依赖"
    (cd "$FRONTEND_DIR" && npm install)
    mkdir -p "$FRONTEND_DIR/node_modules"
    touch "$marker"
  fi
}

bootstrap_repo_if_missing "$@"

if ! command_exists curl; then
  fail "未找到 curl，无法检查服务健康状态"
fi

if ! command_exists ffmpeg || ! command_exists ffprobe; then
  log "提示: 未检测到 ffmpeg/ffprobe，视频帧提取相关功能可能不可用。"
fi

if port_in_use "$SAU_PORT"; then
  fail "后端端口 $SAU_PORT 已被占用。可临时指定其他端口：SAU_PORT=17410 bash start.sh"
fi

if port_in_use "$FRONTEND_PORT"; then
  fail "前端端口 $FRONTEND_PORT 已被占用。可临时指定其他端口：FRONTEND_PORT=17573 bash start.sh"
fi

ensure_backend_env
ensure_frontend_env

rm -f "$BACKEND_LOG" "$FRONTEND_LOG"

log "启动后端: http://$HOST:$SAU_PORT"
(
  cd "$BACKEND_DIR"
  SAU_PORT="$SAU_PORT" PYTHONUNBUFFERED=1 "$VENV_PYTHON" app.py
) >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

wait_for_http "后端" "http://$HOST:$SAU_PORT/api/health" "$BACKEND_LOG" "$BACKEND_PID"

log "启动前端: http://$HOST:$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  VITE_API_BASE_URL="$VITE_API_BASE_URL" \
  VITE_FRONTEND_PORT="$FRONTEND_PORT" \
  npm run dev -- --host "$HOST" --port "$FRONTEND_PORT" --strictPort
) >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

wait_for_http "前端" "http://$HOST:$FRONTEND_PORT" "$FRONTEND_LOG" "$FRONTEND_PID"

cat <<EOF

服务已启动：
  前端: http://$HOST:$FRONTEND_PORT
  后端: http://$HOST:$SAU_PORT

日志文件：
  后端: $BACKEND_LOG
  前端: $FRONTEND_LOG

按 Ctrl+C 停止服务。
EOF

while true; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    tail -40 "$BACKEND_LOG" >&2 || true
    fail "后端进程已退出"
  fi

  if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    tail -40 "$FRONTEND_LOG" >&2 || true
    fail "前端进程已退出"
  fi

  sleep 2
done
