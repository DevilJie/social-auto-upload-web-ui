#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 项目代码更新脚本 — Linux + macOS
# ============================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'
CHECK="${GREEN}✓${NC}"
CROSS="${RED}✗${NC}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
BACKEND_DIR="$PROJECT_ROOT/backend"
REPO_URL="https://github.com/DevilJie/social-auto-upload-web-ui.git"
MAIN_BRANCH="master"

if ! command -v git &>/dev/null; then
    echo -e "${CROSS} 未找到 git，无法更新"
    exit 1
fi

# 首次使用：没有项目代码，从 GitHub 克隆
if [[ ! -d "$BACKEND_DIR" ]]; then
    echo ""
    echo -e "${CYAN}首次使用，正在从 GitHub 拉取项目代码...${NC}"
    cd "$PROJECT_ROOT"
    git init
    git remote add origin "$REPO_URL" 2>/dev/null || git remote set-url origin "$REPO_URL"
    if ! git fetch origin "$MAIN_BRANCH"; then
        echo -e "${CROSS} 无法连接 GitHub，请检查网络连接"
        echo "  仓库地址: $REPO_URL"
        exit 1
    fi
    git checkout -f "$MAIN_BRANCH"
    echo -e "${CHECK} 项目代码拉取完成"
    exit 0
fi

# 已有项目代码：检查当前分支是否有更新
cd "$PROJECT_ROOT"
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")
if [[ -z "$CURRENT_BRANCH" || "$CURRENT_BRANCH" == "HEAD" ]]; then
    echo -e "${CROSS} 当前处于分离 HEAD 状态，无法更新"
    exit 1
fi

echo ""
echo "  当前分支: $CURRENT_BRANCH"
echo "  正在检查更新..."
if ! git fetch origin "$CURRENT_BRANCH" 2>/dev/null; then
    echo -e "${CROSS} 无法连接远端仓库，请检查网络连接"
    exit 1
fi

LOCAL_HASH=$(git rev-parse HEAD 2>/dev/null || echo "")
REMOTE_HASH=$(git rev-parse "origin/$CURRENT_BRANCH" 2>/dev/null || echo "")

if [[ -z "$REMOTE_HASH" ]]; then
    echo -e "${CROSS} 无法获取远端版本信息"
    exit 1
fi

if [[ "$LOCAL_HASH" == "$REMOTE_HASH" ]]; then
    echo -e "${CHECK} 已是最新版本"
    exit 0
fi

echo ""
echo -e "${CYAN}发现新版本！${NC}"
echo "  本地: ${LOCAL_HASH:0:7}"
echo "  远端: ${REMOTE_HASH:0:7}"
echo ""
echo -e "${CYAN}是否更新？[Y/n]  更新将覆盖本地修改，未提交的代码将丢失${NC}"
read -r answer
if [[ ! "$answer" =~ ^[Nn]$ ]]; then
    git reset --hard "origin/$CURRENT_BRANCH" > /dev/null 2>&1
    echo -e "${CHECK} 更新完成"
else
    echo "  已取消更新"
fi
