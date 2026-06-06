#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 离线依赖打包脚本
# 在有网络的机器上运行，生成 dependency.tar.gz / .zip
# 目标用户解压到项目根目录即可使用
#
# 用法:
#   bash scripts/pack-deps.sh              # 当前平台
#   bash scripts/pack-deps.sh --platform linux-x64
#   bash scripts/pack-deps.sh --platform macos-arm64
#   bash scripts/pack-deps.sh --platform win-x64
# ============================================================

PLATFORM=""
if [[ "${1:-}" == "--platform" ]]; then
    PLATFORM="${2:-}"
fi

# 自动检测当前平台
OS="$(uname -s)"
ARCH="$(uname -m)"

if [[ -z "$PLATFORM" ]]; then
    case "$OS" in
        Linux)  PLATFORM="linux-x64" ;;
        Darwin)
            if [[ "$ARCH" == "arm64" ]]; then
                PLATFORM="macos-arm64"
            else
                PLATFORM="macos-x64"
            fi
            ;;
        *) echo "不支持的平台: $OS"; exit 1 ;;
    esac
fi

PLATFORM_OS="${PLATFORM%%-*}"

echo "============================================"
echo "  打包离线依赖: $PLATFORM"
echo "============================================"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEP_DIR="$PROJECT_ROOT/dependency"

# 清理旧目录
rm -rf "$DEP_DIR"
mkdir -p "$DEP_DIR/bin"

# --- 辅助函数 ---
info()  { echo "  [INFO] $1"; }
ok()    { echo "  [OK]   $1"; }
fail()  { echo "  [FAIL] $1"; exit 1; }

download() {
    local url="$1"
    local output="$2"
    info "下载: $url"
    curl -L --progress-bar -o "$output" "$url" || fail "下载失败: $url"
}

# ============================================================
# 1. CloakBrowser（最先下载，失败即停）
# ============================================================
echo ""
echo "[1/5] 下载 CloakBrowser..."

CB_DIR="$DEP_DIR/cloakbrowser"
CB_TMP=$(mktemp -d)
CB_ARCHIVE_SRC=""

if [[ "$PLATFORM_OS" == "macos" ]]; then
    # macOS 暂无官方离线包：需要用户提供 tar.gz 放到 scripts/ 下。
    # 支持两种命名：cloakbrowser-macos-{x64,arm64}.tar.gz（项目命名）
    # 或 cloakbrowser-darwin-{x64,arm64}.tar.gz（Node.js/Python 行业惯例）
    _mac_arch="${PLATFORM#macos-}"
    CB_LOCAL=""
    for _candidate in \
        "$SCRIPT_DIR/cloakbrowser-${PLATFORM}.tar.gz" \
        "$SCRIPT_DIR/cloakbrowser-darwin-${_mac_arch}.tar.gz"; do
        if [[ -f "$_candidate" ]]; then
            CB_LOCAL="$_candidate"
            break
        fi
    done
    if [[ -n "$CB_LOCAL" ]]; then
        cp "$CB_LOCAL" "$CB_TMP/cb-archive"
        CB_ARCHIVE_SRC="$CB_LOCAL"
    else
        echo "  [SKIP] macOS 的 CloakBrowser 需要用户提供离线包"
        echo "         请将以下任一文件放到 $SCRIPT_DIR/ 后重跑："
        echo "           - cloakbrowser-${PLATFORM}.tar.gz"
        echo "           - cloakbrowser-darwin-${_mac_arch}.tar.gz"
    fi
else
    CB_VERSION=$(curl -sL "https://api.github.com/repos/CloakHQ/CloakBrowser/releases/latest" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || true)
    CB_VERSION="${CB_VERSION#chromium-v}"
    [[ -z "$CB_VERSION" ]] && CB_VERSION="146.0.7680.177.5"

    case "$PLATFORM" in
        linux-x64) CB_ARCHIVE_NAME="cloakbrowser-linux-x64.tar.gz" ;;
        win-x64)   CB_ARCHIVE_NAME="cloakbrowser-windows-x64.zip" ;;
        *)         fail "CloakBrowser 不支持平台: $PLATFORM" ;;
    esac

    CB_URL="https://github.com/CloakHQ/CloakBrowser/releases/download/chromium-v${CB_VERSION}/${CB_ARCHIVE_NAME}"
    download "$CB_URL" "$CB_TMP/cb-archive"
    CB_ARCHIVE_SRC="$CB_URL"
fi

# 统一解压逻辑（macOS 用户提供 / linux + win 从 GitHub 下载）
if [[ -f "$CB_TMP/cb-archive" ]]; then
    mkdir -p "$CB_DIR"
    case "$PLATFORM" in
        win-x64) unzip -o "$CB_TMP/cb-archive" -d "$CB_DIR" ;;
        *)       tar -xzf "$CB_TMP/cb-archive" -C "$CB_DIR" ;;
    esac

    CB_FOUND=false
    if [[ "$PLATFORM_OS" == "win" ]]; then
        find "$CB_DIR" -name "chrome.exe" -type f -print -quit | grep -q . && CB_FOUND=true
    else
        CHROME_BIN=$(find "$CB_DIR" -name "chrome" -type f -print -quit 2>/dev/null || true)
        if [[ -n "$CHROME_BIN" ]]; then
            CB_FOUND=true
            chmod +x "$CHROME_BIN"
        fi
    fi

    if [[ "$CB_FOUND" == "true" ]]; then
        if [[ "$PLATFORM_OS" == "macos" ]]; then
            ok "CloakBrowser (用户提供离线包: ${CB_ARCHIVE_SRC##*/})"
        else
            ok "CloakBrowser"
        fi
    else
        echo "  [WARN] CloakBrowser 二进制未找到"
    fi
fi
rm -rf "$CB_TMP"

# ============================================================
# 2. Python (便携版 - 仅 Windows)
# ============================================================
echo ""
echo "[2/4] 下载 Python..."

if [[ "$PLATFORM_OS" == "win" ]]; then
    PY_DIR="$DEP_DIR/python"
    mkdir -p "$PY_DIR"
    PY_TMP=$(mktemp -d)

    PY_RELEASE="20260414"
    PY_VERSION="3.12.13"
    PY_ARCHIVE="cpython-${PY_VERSION}+${PY_RELEASE}-x86_64-pc-windows-msvc-install_only.tar.gz"
    PY_URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PY_RELEASE}/${PY_ARCHIVE}"

    download "$PY_URL" "$PY_TMP/python.tar.gz"
    tar -xzf "$PY_TMP/python.tar.gz" -C "$PY_TMP"
    if [[ -d "$PY_TMP/python" ]]; then
        cp -r "$PY_TMP/python/"* "$PY_DIR/"
    else
        cp -r "$PY_TMP/"* "$PY_DIR/" 2>/dev/null || true
    fi
    cp "$PY_DIR/python.exe" "$DEP_DIR/bin/python.exe" 2>/dev/null || true
    cp "$PY_DIR/Scripts/pip.exe" "$DEP_DIR/bin/pip.exe" 2>/dev/null || true

    rm -rf "$PY_TMP"
    ok "Python ${PY_VERSION}"
else
    echo "  [SKIP] Linux/macOS 用户请通过包管理器安装 Python 3.8+"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "    macOS:         brew install python3"
fi

# ============================================================
# 3. Git (便携版 - 仅 Windows)
# ============================================================
echo ""
echo "[3/4] 下载 Git..."

if [[ "$PLATFORM_OS" == "win" ]]; then
    GIT_DIR="$DEP_DIR/git"
    mkdir -p "$GIT_DIR"
    GIT_TMP=$(mktemp -d)

    GIT_TAG=$(curl -sL "https://api.github.com/repos/git-for-windows/git/releases/latest" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['tag_name'])" 2>/dev/null || echo "v2.49.0.windows.1")
    GIT_VER="${GIT_TAG#v}"
    GIT_VER="${GIT_VER%.windows.*}"
    GIT_ARCHIVE="MinGit-${GIT_VER}-64-bit.zip"
    GIT_URL="https://github.com/git-for-windows/git/releases/download/${GIT_TAG}/${GIT_ARCHIVE}"

    download "$GIT_URL" "$GIT_TMP/mingit.zip"
    unzip -o "$GIT_TMP/mingit.zip" -d "$GIT_DIR"
    cp "$GIT_DIR/cmd/git.exe" "$DEP_DIR/bin/git.exe" 2>/dev/null || true

    rm -rf "$GIT_TMP"
    ok "Git ${GIT_VER}"
else
    echo "  [SKIP] Linux/macOS 用户请通过包管理器安装 Git"
    echo "    Ubuntu/Debian: sudo apt install git"
    echo "    macOS:         brew install git 或 xcode-select --install"
fi

# ============================================================
# 4. ffmpeg + ffprobe
# ============================================================
echo ""
echo "[4/4] 下载 ffmpeg + ffprobe..."

FFMPEG_DIR=$(mktemp -d)

case "$PLATFORM" in
    linux-x64)
        download "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" "$FFMPEG_DIR/ffmpeg.tar.xz"
        tar -xf "$FFMPEG_DIR/ffmpeg.tar.xz" -C "$FFMPEG_DIR" --strip-components=1
        cp "$FFMPEG_DIR/ffmpeg" "$DEP_DIR/bin/ffmpeg"
        cp "$FFMPEG_DIR/ffprobe" "$DEP_DIR/bin/ffprobe"
        chmod +x "$DEP_DIR/bin/ffmpeg" "$DEP_DIR/bin/ffprobe"
        ;;
    macos-arm64)
        download "https://evermeet.cx/ffmpeg/getrelease/zip" "$FFMPEG_DIR/ffmpeg.zip"
        download "https://evermeet.cx/ffprobe/getrelease/zip" "$FFMPEG_DIR/ffprobe.zip"
        mkdir "$FFMPEG_DIR/ff" "$FFMPEG_DIR/fp"
        unzip -o "$FFMPEG_DIR/ffmpeg.zip" -d "$FFMPEG_DIR/ff"
        unzip -o "$FFMPEG_DIR/ffprobe.zip" -d "$FFMPEG_DIR/fp"
        cp "$FFMPEG_DIR/ff/ffmpeg" "$DEP_DIR/bin/ffmpeg"
        cp "$FFMPEG_DIR/fp/"* "$DEP_DIR/bin/ffprobe"
        chmod +x "$DEP_DIR/bin/ffmpeg" "$DEP_DIR/bin/ffprobe"
        ;;
    macos-x64)
        download "https://evermeet.cx/ffmpeg/getrelease/zip" "$FFMPEG_DIR/ffmpeg.zip"
        download "https://evermeet.cx/ffprobe/getrelease/zip" "$FFMPEG_DIR/ffprobe.zip"
        mkdir "$FFMPEG_DIR/ff" "$FFMPEG_DIR/fp"
        unzip -o "$FFMPEG_DIR/ffmpeg.zip" -d "$FFMPEG_DIR/ff"
        unzip -o "$FFMPEG_DIR/ffprobe.zip" -d "$FFMPEG_DIR/fp"
        cp "$FFMPEG_DIR/ff/ffmpeg" "$DEP_DIR/bin/ffmpeg"
        cp "$FFMPEG_DIR/fp/"* "$DEP_DIR/bin/ffprobe"
        chmod +x "$DEP_DIR/bin/ffmpeg" "$DEP_DIR/bin/ffprobe"
        ;;
    win-x64)
        download "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" "$FFMPEG_DIR/ffmpeg.zip"
        cd "$FFMPEG_DIR" && unzip -o ffmpeg.zip
        FFMPEG_BIN=$(find "$FFMPEG_DIR" -name "ffmpeg.exe" -type f | head -1)
        FFPROBE_BIN=$(find "$FFMPEG_DIR" -name "ffprobe.exe" -type f | head -1)
        cp "$FFMPEG_BIN" "$DEP_DIR/bin/ffmpeg.exe"
        cp "$FFPROBE_BIN" "$DEP_DIR/bin/ffprobe.exe"
        ;;
esac

rm -rf "$FFMPEG_DIR"
ok "ffmpeg + ffprobe"

# ============================================================
# 5. Node.js (便携版)
# ============================================================
echo ""
echo ""
echo "  (bonus) 下载 Node.js..."

NODE_DIR="$DEP_DIR/node"
mkdir -p "$NODE_DIR"
NODE_TMP=$(mktemp -d)

case "$PLATFORM" in
    linux-x64)
        download "https://nodejs.org/dist/v22.16.0/node-v22.16.0-linux-x64.tar.xz" "$NODE_TMP/node.tar.xz"
        tar -xf "$NODE_TMP/node.tar.xz" -C "$NODE_DIR" --strip-components=1
        ln -sf "$NODE_DIR/bin/node" "$DEP_DIR/bin/node"
        ln -sf "$NODE_DIR/bin/npm" "$DEP_DIR/bin/npm"
        ln -sf "$NODE_DIR/bin/npx" "$DEP_DIR/bin/npx"
        ;;
    macos-arm64)
        download "https://nodejs.org/dist/v22.16.0/node-v22.16.0-darwin-arm64.tar.gz" "$NODE_TMP/node.tar.gz"
        tar -xzf "$NODE_TMP/node.tar.gz" -C "$NODE_DIR" --strip-components=1
        ln -sf "$NODE_DIR/bin/node" "$DEP_DIR/bin/node"
        ln -sf "$NODE_DIR/bin/npm" "$DEP_DIR/bin/npm"
        ln -sf "$NODE_DIR/bin/npx" "$DEP_DIR/bin/npx"
        ;;
    macos-x64)
        download "https://nodejs.org/dist/v22.16.0/node-v22.16.0-darwin-x64.tar.gz" "$NODE_TMP/node.tar.gz"
        tar -xzf "$NODE_TMP/node.tar.gz" -C "$NODE_DIR" --strip-components=1
        ln -sf "$NODE_DIR/bin/node" "$DEP_DIR/bin/node"
        ln -sf "$NODE_DIR/bin/npm" "$DEP_DIR/bin/npm"
        ln -sf "$NODE_DIR/bin/npx" "$DEP_DIR/bin/npx"
        ;;
    win-x64)
        download "https://nodejs.org/dist/v22.16.0/node-v22.16.0-win-x64.zip" "$NODE_TMP/node.zip"
        cd "$NODE_TMP" && unzip -o node.zip
        NODE_INNER=$(find "$NODE_TMP" -maxdepth 1 -type d -name "node-*" | head -1)
        cp -r "$NODE_INNER/"* "$NODE_DIR/"
        cp "$NODE_DIR/node.exe" "$DEP_DIR/bin/node.exe"
        cp "$NODE_DIR/npm.cmd" "$DEP_DIR/bin/npm.cmd"
        cp "$NODE_DIR/npx.cmd" "$DEP_DIR/bin/npx.cmd"
        ;;
esac

rm -rf "$NODE_TMP"
ok "Node.js v22.16.0"

# ============================================================
# 写入 README
# ============================================================
cat > "$DEP_DIR/README.txt" << EOF
QianFan Sync 离线依赖包 ($PLATFORM)
====================================

目录结构:
  QianFan Sync/
  ├── dependency/
  │   ├── bin/              ffmpeg, ffprobe, node, npm, python, git
  │   ├── python/           Python 完整安装
  │   ├── git/              Git 完整安装
  │   ├── node/             Node.js 完整安装
  │   └── cloakbrowser/     CloakBrowser 浏览器
  ├── start.sh              Linux/macOS 启动脚本
  └── start.bat             Windows 启动脚本

使用方式:
  1. 解压整个压缩包到一个目录
  2. 进入 QianFan Sync 目录
  3. 运行 start.sh (Linux/macOS) 或 start.bat (Windows)
  4. 首次运行会自动从 GitHub 拉取项目代码
  5. 后续运行会检查并提示更新

平台: $PLATFORM
打包时间: $(date '+%Y-%m-%d %H:%M:%S')
EOF

# ============================================================
# 打包（QianFan Sync/ 包裹所有内容）
# ============================================================
echo ""
echo "============================================"
echo "  打包中..."

# 创建 QianFan Sync 临时目录结构
PACK_DIR="$PROJECT_ROOT/_pack_qianfan"
rm -rf "$PACK_DIR"
mkdir -p "$PACK_DIR/QianFan Sync"
mv "$DEP_DIR" "$PACK_DIR/QianFan Sync/dependency"
cp "$PROJECT_ROOT/start.sh" "$PACK_DIR/QianFan Sync/start.sh"
cp "$PROJECT_ROOT/start.bat" "$PACK_DIR/QianFan Sync/start.bat"

cd "$PACK_DIR"
if [[ "$PLATFORM_OS" == "win" ]]; then
    OUTPUT="$PROJECT_ROOT/QianFanSync-$PLATFORM.zip"
    zip -r -q "$OUTPUT" "QianFan Sync/"
else
    OUTPUT="$PROJECT_ROOT/QianFanSync-$PLATFORM.tar.gz"
    tar -czf "$OUTPUT" "QianFan Sync/"
fi

# 还原 dependency 目录到原位
mv "$PACK_DIR/QianFan Sync/dependency" "$DEP_DIR"
rm -rf "$PACK_DIR"

TOTAL_SIZE=$(du -sh "$DEP_DIR" | awk '{print $1}')
FILE_COUNT=$(find "$DEP_DIR" -type f | wc -l)

echo ""
echo "============================================"
echo "  打包完成!"
echo "============================================"
echo "  输出文件: $OUTPUT"
echo "  依赖大小: $TOTAL_SIZE"
echo "  文件数量: $FILE_COUNT"
echo ""
echo "  分发给用户后，解压到任意目录："
echo "    解压后得到: QianFan Sync/"
if [[ "$PLATFORM_OS" == "win" ]]; then
    echo "    进入目录，双击 start.bat"
else
    echo "    进入目录，运行: bash start.sh"
fi
echo "============================================"
