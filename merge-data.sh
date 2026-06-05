#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 旧版数据迁移脚本 — Linux / macOS
# ============================================================
#
# 调用 scripts/migrate_legacy_data.py 把指定目录的旧版数据迁移到 data/。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DATA="$SCRIPT_DIR/data"

echo
echo "============================================================"
echo "  旧版数据迁移到新版 data/ 目录"
echo "============================================================"
echo
echo "目标目录: $PROJECT_DATA"
echo
echo "请输入需要迁移的源数据目录完整路径。"
echo "（例如：/home/foo/Social Auto Upload Web UI）"
echo

read -r -p "源数据目录: " SOURCE

if [[ -z "$SOURCE" ]]; then
    echo "[错误] 未输入路径"
    exit 1
fi

if [[ ! -d "$SOURCE" ]]; then
    echo "[错误] 目录不存在: $SOURCE"
    exit 1
fi

echo
echo "源目录: $SOURCE"
echo "目标目录: $PROJECT_DATA"
echo
echo "提示：先执行 ./start.sh 启动后端，再运行本脚本。"
echo

python3 "$SCRIPT_DIR/scripts/migrate_legacy_data.py" \
    --source "$SOURCE" \
    --target "$PROJECT_DATA" \
    --yes
