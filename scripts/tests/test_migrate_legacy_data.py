"""迁移脚本的单元测试。"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 把 scripts/ 目录加入 sys.path，便于导入 migrate_legacy_data
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import migrate_legacy_data as mld


def _mock_response(status_code: int, body: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body or {"code": 200}
    resp.raise_for_status = MagicMock()
    return resp


def test_check_backend_healthy(monkeypatch):
    monkeypatch.setattr(mld.requests, "get",
                        lambda *a, **kw: _mock_response(200))
    assert mld.check_backend("http://127.0.0.1:5409") is True


def test_check_backend_unhealthy_status(monkeypatch):
    """后端返回 500 时视为不健康。"""
    resp = _mock_response(500)
    resp.raise_for_status = MagicMock(side_effect=Exception("HTTP 500"))
    monkeypatch.setattr(mld.requests, "get", lambda *a, **kw: resp)
    assert mld.check_backend("http://127.0.0.1:5409") is False


def test_check_backend_connection_refused(monkeypatch):
    """连接被拒绝时视为不健康。"""
    def fake_get(*a, **kw):
        raise mld.requests.exceptions.ConnectionError("refused")
    monkeypatch.setattr(mld.requests, "get", fake_get)
    assert mld.check_backend("http://127.0.0.1:5409") is False


def test_check_backend_timeout(monkeypatch):
    """超时视为不健康。"""
    def fake_get(*a, **kw):
        raise mld.requests.exceptions.Timeout("timeout")
    monkeypatch.setattr(mld.requests, "get", fake_get)
    assert mld.check_backend("http://127.0.0.1:5409") is False


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


def test_default_target_uses_sau_data_dir_env(monkeypatch, tmp_path):
    """SAU_DATA_DIR 环境变量被优先使用。"""
    monkeypatch.setenv("SAU_DATA_DIR", str(tmp_path))
    assert mld.default_target() == tmp_path


def test_default_target_uses_repo_data_dir(monkeypatch):
    """未设置 SAU_DATA_DIR 时使用 {脚本父目录的父目录}/data。"""
    monkeypatch.delenv("SAU_DATA_DIR", raising=False)
    expected = mld.Path(mld.__file__).resolve().parent.parent / "data"
    assert mld.default_target() == expected


def test_default_source_non_windows(monkeypatch):
    """非 Windows 下默认指向 scripts/legacy_fixture。"""
    monkeypatch.setattr(mld.sys, "platform", "linux")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    expected = Path(__file__).resolve().parent.parent / "legacy_fixture"
    assert mld.default_source() == expected


def test_default_source_windows(monkeypatch, tmp_path):
    """Windows 下默认指向 %LOCALAPPDATA%\\Social Auto Upload Web UI。"""
    monkeypatch.setattr(mld.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    expected = tmp_path / "Social Auto Upload Web UI"
    assert mld.default_source() == expected


def test_strip_uuid_prefix_standard():
    """标准 uuid 前缀被剥离。"""
    name = "1781ca06-5427-11f1-8000-bc2411b9d4e7_大理女孩-成品.mp4"
    assert mld.strip_uuid_prefix(name) == "大理女孩-成品.mp4"


def test_strip_uuid_prefix_uppercase():
    """大写 UUID 前缀同样被剥离。"""
    name = "AABBCCDD-1234-5678-9ABC-DEF012345678_video.mp4"
    assert mld.strip_uuid_prefix(name) == "video.mp4"


def test_strip_uuid_prefix_no_prefix():
    """没有 uuid 前缀时原样返回。"""
    name = "video.mp4"
    assert mld.strip_uuid_prefix(name) == "video.mp4"


def test_strip_uuid_prefix_inner_uuid_kept():
    """文件名中第二个及之后的 uuid 模式不被剥离。"""
    name = "11111111-2222-3333-4444-555555555555_aaa-bbb-ccc-ddd-eee.txt"
    assert mld.strip_uuid_prefix(name) == "aaa-bbb-ccc-ddd-eee.txt"


def test_is_allowed_ext_video():
    assert mld.is_allowed_ext("foo.mp4") is True
    assert mld.is_allowed_ext("foo.MP4") is True
    assert mld.is_allowed_ext("foo.mov") is True
    assert mld.is_allowed_ext("foo.webm") is True


def test_is_allowed_ext_image():
    assert mld.is_allowed_ext("foo.png") is True
    assert mld.is_allowed_ext("foo.jpg") is True
    assert mld.is_allowed_ext("foo.webp") is True


def test_is_allowed_ext_rejected():
    assert mld.is_allowed_ext("foo.DS_Store") is False
    assert mld.is_allowed_ext("foo") is False
    assert mld.is_allowed_ext("foo.tmp") is False
    assert mld.is_allowed_ext("foo.db") is False


def test_backup_creates_timestamped_copy(monkeypatch, tmp_path):
    """备份把整个 data 目录复制到 data.bak.YYYYMMDD_HHMMSS/。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "cookies").mkdir()
    (data_dir / "cookies" / "foo.json").write_text("x")

    timestamp = "20260605_153012"
    monkeypatch.setattr(mld, "_timestamp", lambda: timestamp)

    backup_path = mld.backup_data(data_dir, dry_run=False)
    assert backup_path == data_dir.parent / f"data.bak.{timestamp}"
    assert backup_path.exists()
    assert (backup_path / "data" / "cookies" / "foo.json").read_text() == "x"


def test_backup_dry_run_does_not_copy(monkeypatch, tmp_path):
    """dry-run 模式下不实际复制。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "cookies").mkdir()
    timestamp = "20260605_153012"
    monkeypatch.setattr(mld, "_timestamp", lambda: timestamp)

    backup_path = mld.backup_data(data_dir, dry_run=True)
    assert backup_path == data_dir.parent / f"data.bak.{timestamp}"
    assert not backup_path.exists()


def test_backup_skip_returns_none(tmp_path):
    """skip_backup=True 时返回 None 且不创建目录。"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assert mld.backup_data(data_dir, dry_run=False, skip=True) is None


def test_copy_directory_overwrite(monkeypatch, tmp_path):
    """递归覆盖拷贝：目标文件存在时被覆盖，不存在的被创建。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "cookies").mkdir()
    (src / "cookies" / "a.json").write_text("new")

    dst = tmp_path / "dst"
    dst.mkdir()
    (dst / "cookies").mkdir()
    (dst / "cookies" / "old.json").write_text("old")

    copied, failed = mld.copy_directory(src / "cookies", dst / "cookies", dry_run=False)
    assert copied == 1
    assert failed == 0
    assert (dst / "cookies" / "a.json").read_text() == "new"
    # 目标已有的 old.json 不被删除（覆盖语义而非 mirror 语义）
    assert (dst / "cookies" / "old.json").read_text() == "old"


def test_copy_directory_dry_run(monkeypatch, tmp_path):
    """dry-run 模式不实际拷贝。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "f.txt").write_text("x")

    dst = tmp_path / "dst"
    dst.mkdir()

    copied, failed = mld.copy_directory(src, dst, dry_run=True)
    assert copied == 1
    assert failed == 0
    assert not (dst / "f.txt").exists()


def test_copy_directory_handles_subdirs(monkeypatch, tmp_path):
    """支持多层子目录递归。"""
    src = tmp_path / "src"
    (src / "deep" / "nested").mkdir(parents=True)
    (src / "deep" / "nested" / "f.txt").write_text("hello")

    dst = tmp_path / "dst"
    dst.mkdir()

    copied, failed = mld.copy_directory(src, dst, dry_run=False)
    assert copied == 1
    assert failed == 0
    assert (dst / "deep" / "nested" / "f.txt").read_text() == "hello"


def test_copy_directory_reports_failures(monkeypatch, tmp_path):
    """单个文件失败不影响其他文件，并计入 failed 计数。"""
    src = tmp_path / "src"
    src.mkdir()
    (src / "good.txt").write_text("ok")
    (src / "bad.txt").write_text("bad")

    dst = tmp_path / "dst"
    dst.mkdir()

    real_copy2 = mld.shutil.copy2

    def fake_copy2(src_file, dst_file, *a, **kw):
        if "bad" in str(src_file):
            raise OSError("simulated copy error")
        return real_copy2(src_file, dst_file, *a, **kw)

    monkeypatch.setattr(mld.shutil, "copy2", fake_copy2)

    copied, failed = mld.copy_directory(src, dst, dry_run=False)
    assert copied == 1
    assert failed == 1
    assert (dst / "good.txt").read_text() == "ok"
    assert not (dst / "bad.txt").exists()


def test_upload_material_success(monkeypatch, tmp_path):
    """成功上传：返回 True，文件以原文件名（去前缀）传递。"""
    captured: dict = {}

    def fake_post(url, files, timeout):
        captured["url"] = url
        captured["files"] = files
        captured["timeout"] = timeout
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "code": 200,
            "data": {"id": "new-uuid", "stored_path": "materials/2026/06/new-uuid.mp4"},
        }
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "11111111-2222-3333-4444-555555555555_test.mp4"
    src.write_bytes(b"fake video content")

    ok = mld.upload_material(
        src, api_base="http://127.0.0.1:5409", dry_run=False,
    )
    assert ok is True
    assert captured["url"] == "http://127.0.0.1:5409/api/materials/upload"
    file_tuple = captured["files"]["file"]
    # file_tuple: (filename, file_obj, mime)
    assert file_tuple[0] == "test.mp4"  # uuid 前缀已剥离


def test_upload_material_dry_run(monkeypatch, tmp_path):
    """dry-run 模式不实际调用 HTTP。"""
    called = {"count": 0}

    def fake_post(*a, **kw):
        called["count"] += 1
        return MagicMock()

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "uuid_test.mp4"
    src.write_bytes(b"x")
    ok = mld.upload_material(src, api_base="http://x", dry_run=True)
    assert ok is True
    assert called["count"] == 0


def test_upload_material_http_error(monkeypatch, tmp_path, capsys):
    """HTTP 500 时返回 False 并打印错误。"""
    def fake_post(*a, **kw):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        resp.raise_for_status = MagicMock(
            side_effect=mld.requests.exceptions.HTTPError("500")
        )
        return resp

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "uuid_x.mp4"
    src.write_bytes(b"x")
    ok = mld.upload_material(src, api_base="http://x", dry_run=False)
    assert ok is False
    captured = capsys.readouterr()
    assert "ERROR" in captured.err


def test_upload_material_connection_error(monkeypatch, tmp_path, capsys):
    """连接错误时返回 False。"""
    def fake_post(*a, **kw):
        raise mld.requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(mld.requests, "post", fake_post)

    src = tmp_path / "uuid_x.mp4"
    src.write_bytes(b"x")
    ok = mld.upload_material(src, api_base="http://x", dry_run=False)
    assert ok is False
    captured = capsys.readouterr()
    assert "ERROR" in captured.err


def test_main_happy_path(monkeypatch, tmp_path, capsys):
    """完整流程：备份 → 探测 → 拷贝 → 上传，dry_run=False。"""
    # 准备旧版 fixture
    src = tmp_path / "old"
    (src / "cookies").mkdir(parents=True)
    (src / "cookies" / "a.json").write_text("ck")
    (src / "cookiesFile").mkdir()
    (src / "cookiesFile" / "b.json").write_text("cf")
    (src / "db").mkdir()
    (src / "db" / "database.db").write_text("db")
    (src / "videoFile").mkdir()
    (src / "videoFile" / "11111111-2222-3333-4444-555555555555_movie.mp4").write_bytes(b"v")
    (src / "videoFile" / "22222222-3333-4444-5555-666666666666_pic.png").write_bytes(b"p")
    (src / "videoFile" / "Thumbs.db").write_bytes(b"junk")  # 应被跳过

    # 准备目标 data（用 tmp_path/data，与后端 conf.py 行为对齐）
    target = tmp_path / "data"
    target.mkdir()
    (target / "cookies").mkdir()

    # stub 后端探测 + 上传
    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    upload_calls: list = []
    monkeypatch.setattr(mld, "upload_material",
                        lambda p, api_base, dry_run=False, timeout=300.0: upload_calls.append(p.name) or True)

    # stub 备份时间戳
    monkeypatch.setattr(mld, "_timestamp", lambda: "20260605_153012")

    # 用 monkeypatch 替换 sys.argv 注入参数
    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(src),
        "--target", str(target),
        "--api-base", "http://127.0.0.1:5409",
        "--yes",
    ])

    rc = mld.main()
    assert rc == 0

    # 断言：目标 data 包含拷贝内容
    assert (target / "cookies" / "a.json").read_text() == "ck"
    assert (target / "cookiesFile" / "b.json").read_text() == "cf"
    assert (target / "db" / "database.db").read_text() == "db"

    # 断言：备份存在
    backup = tmp_path / "data.bak.20260605_153012"
    assert backup.exists()
    assert (backup / "data" / "cookies").exists()

    # 断言：两个白名单文件都被上传，Thumbs.db 被跳过
    assert len(upload_calls) == 2
    assert "11111111-2222-3333-4444-555555555555_movie.mp4" in upload_calls
    assert "22222222-3333-4444-5555-666666666666_pic.png" in upload_calls

    # 断言：报告打印到 stdout
    out = capsys.readouterr().out
    assert "迁移报告" in out


def test_main_backend_unreachable(monkeypatch, tmp_path):
    """后端不可达时退出码 3。"""
    src = tmp_path / "old"
    src.mkdir()
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: False)

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(src),
        "--target", str(target),
        "--yes",
    ])

    rc = mld.main()
    assert rc == 3


def test_main_source_not_found(monkeypatch, tmp_path):
    """源路径不存在时退出码 1。"""
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(tmp_path / "nonexistent"),
        "--target", str(target),
        "--yes",
    ])

    rc = mld.main()
    assert rc == 1


def test_main_dry_run_no_modifications(monkeypatch, tmp_path):
    """dry-run 模式不实际写任何文件。"""
    src = tmp_path / "old"
    (src / "cookies").mkdir(parents=True)
    (src / "cookies" / "a.json").write_text("ck")

    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    upload_calls: list = []
    monkeypatch.setattr(mld, "upload_material",
                        lambda *a, **kw: upload_calls.append(True) or True)

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(src),
        "--target", str(target),
        "--dry-run",
        "--yes",
    ])

    rc = mld.main()
    assert rc == 0
    # 目标 cookies 目录被创建但不包含 a.json
    assert not (target / "cookies" / "a.json").exists()


def test_integration_against_legacy_fixture(monkeypatch, tmp_path, capsys):
    """端到端：用真实 legacy_fixture 跑完整流程。"""
    fixture_root = Path(__file__).resolve().parent.parent / "legacy_fixture"
    target = tmp_path / "data"
    target.mkdir()
    # 预填 target，让 backup 阶段能捕获到已有数据
    (target / "cookies").mkdir(parents=True, exist_ok=True)
    (target / "cookies" / "foo.json").write_text(
        '{"placeholder": "cookie fixture", "user": "test_user"}'
    )

    # 计算 fixture 中白名单/非白名单文件数（.DS_Store 可能在 .gitignore 下被
    # 本地存在但不被 git 跟踪，断言需对该情况保持鲁棒）
    vf = fixture_root / "videoFile"
    fixture_files = [p for p in vf.rglob("*") if p.is_file()]
    expected_allowed = sum(1 for p in fixture_files if mld.is_allowed_ext(p.name))
    expected_skipped = len(fixture_files) - expected_allowed

    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    upload_calls: list = []
    monkeypatch.setattr(mld, "upload_material",
                        lambda p, api_base, dry_run=False, timeout=300.0: upload_calls.append(p.name) or True)
    monkeypatch.setattr(mld, "_timestamp", lambda: "20260605_153012")

    monkeypatch.setattr(sys, "argv", [
        "migrate_legacy_data.py",
        "--source", str(fixture_root),
        "--target", str(target),
        "--yes",
    ])

    rc = mld.main()
    assert rc == 0

    # 拷贝内容
    assert (target / "cookies" / "foo.json").exists()
    assert (target / "cookiesFile" / "xhs.json").exists()
    assert (target / "db" / "database.db").exists()

    # 备份存在
    backup = tmp_path / "data.bak.20260605_153012"
    assert backup.exists(), f"Backup dir not created at {backup}"
    assert (backup / "data" / "cookies" / "foo.json").read_text() == '{"placeholder": "cookie fixture", "user": "test_user"}'

    # 上传白名单文件
    upload_names = [Path(p).name for p in upload_calls]
    assert "11111111-2222-3333-4444-555555555555_test1.mp4" in upload_names
    assert "66666666-7777-8888-9999-000000000000_test2.png" in upload_names
    assert ".DS_Store" not in upload_names  # 被跳过

    # 报告输出
    out = capsys.readouterr().out
    assert "迁移报告" in out
    assert f"videoFile/    成功 {expected_allowed}" in out
    assert f"跳过 {expected_skipped}" in out


def test_integration_idempotent_dry_run(monkeypatch, tmp_path):
    """连跑两次 dry-run 不修改任何文件。"""
    fixture_root = Path(__file__).resolve().parent.parent / "legacy_fixture"
    target = tmp_path / "data"
    target.mkdir()

    monkeypatch.setattr(mld, "check_backend", lambda api: True)
    monkeypatch.setattr(mld, "upload_material", lambda *a, **kw: True)

    for _ in range(2):
        monkeypatch.setattr(sys, "argv", [
            "migrate_legacy_data.py",
            "--source", str(fixture_root),
            "--target", str(target),
            "--dry-run",
            "--yes",
        ])
        rc = mld.main()
        assert rc == 0

    # dry-run 不应该产生任何 cookies/foo.json
    assert not (target / "cookies" / "foo.json").exists()
