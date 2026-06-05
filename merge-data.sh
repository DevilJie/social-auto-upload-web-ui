#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# 旧版数据迁移脚本 — Linux / macOS
# ============================================================
#
# 本脚本会调用 scripts/migrate_legacy_data.py，
# 把旧版 Windows 客户端的用户数据迁移到当前项目的 data/ 目录。
#
# 迁移前请先执行 ./start.sh 启动后端（需要 5409 端口可达）。
# 脚本会先备份当前 data/ 到 data.bak.YYYYMMDD_HHMMSS/，再迁移数据。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DATA="$SCRIPT_DIR/data"

cat <<EOF

============================================================
  旧版数据迁移到新版 data/ 目录
============================================================

此目录是需要迁移的源数据目录。请根据你的使用场景选择：

  [场景 A] Windows 一键 EXE 安装包用户
     数据目录: C:\\Users\\<用户名>\\AppData\\Local\\Social Auto Upload Web UI
     包含 cookies/、cookiesFile/、db/、videoFile/ 四个子目录

  [场景 B] 从 GitHub clone 源代码启动
     数据目录: 项目根目录下的 data/ 目录
     （即 merge-data.sh 所在目录的 data/ 子目录）

  [场景 C] 其他情况（如从备份恢复 .zip 解压）
     直接输入数据目录的完整路径

目标目录（自动计算）: $PROJECT_DATA

============================================================

EOF

read -r -p "请输入需要迁移的源数据目录完整路径: " SOURCE

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
echo "脚本会先备份当前 data/ 到 data.bak.YYYYMMDD_HHMMSS/，再迁移数据。"
echo
read -r -p "按 Enter 继续，Ctrl+C 取消..."

python3 "$SCRIPT_DIR/scripts/migrate_legacy_data.py" \
    --source "$SOURCE" \
    --target "$PROJECT_DATA" \
    --yes
