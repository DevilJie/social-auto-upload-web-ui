"""迁移脚本的单元测试。"""
import sys
from pathlib import Path

# 把 scripts/ 目录加入 sys.path，便于导入 migrate_legacy_data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_legacy_data as mld


def test_parse_args_defaults(monkeypatch):
    """不传任何参数时，所有字段有合理默认值。"""
    monkeypatch.setattr(sys, "argv", ["migrate_legacy_data.py"])
    args = mld.parse_args()
    # api_base 默认 http://127.0.0.1:5409
    assert args.api_base == "http://127.0.0.1:5409"
    # dry-run / skip-backup / yes 默认 False
    assert args.dry_run is False
    assert args.skip_backup is False
    assert args.yes is False
    # source / target 是 Path 类型，字符串或 None（稍后解析）
    assert isinstance(args.source, (Path, type(None)))
    assert isinstance(args.target, (Path, type(None)))


def test_parse_args_custom(monkeypatch):
    """显式传入所有参数时被正确解析。"""
    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", "C:/old/data",
        "--target", "D:/new/data",
        "--api-base", "http://localhost:9999",
        "--dry-run",
        "--skip-backup",
        "--yes",
    ])
    args = mld.parse_args()
    assert str(args.source) == "C:/old/data"
    assert str(args.target) == "D:/new/data"
    assert args.api_base == "http://localhost:9999"
    assert args.dry_run is True
    assert args.skip_backup is True
    assert args.yes is True
