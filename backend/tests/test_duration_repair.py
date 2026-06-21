"""services/duration_repair.py 测试。

覆盖：
- 启动批量补全：duration=0 的视频被识别并写库
- 启动批量补全：已有正常时长的视频不重复处理
- 启动批量补全：非视频素材（图片）被跳过
- 启动批量补全：识别失败（时长仍为 0）不影响整体流程
- 提交兜底：ensure_duration_or_probe 在时长缺失时识别补全
- 提交兜底：已有正常时长时直接返回，不触发识别
"""
import os
import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# duration_repair 内部用函数内 `from conf import BASE_DIR` 读 DB 路径，
# 因此测试通过 patch `conf.BASE_DIR` 指向独立临时目录，实现彻底 DB 隔离，
# 不依赖全局环境变量 / import 顺序，绝不污染真实库。
import conf  # noqa: E402

_SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_type TEXT NOT NULL,
    mime_type TEXT,
    file_size INTEGER DEFAULT 0,
    storage_type TEXT NOT NULL DEFAULT 'local',
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    duration REAL DEFAULT 0,
    thumbnail_path TEXT DEFAULT '',
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
"""


def _make_db():
    """创建独立临时 DB，返回 (tmp_dir, db_path)。"""
    tmp_dir = Path(tempfile.mkdtemp(prefix="duration_repair_test_"))
    db_path = tmp_dir / "db" / "database.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()
    return tmp_dir, db_path


def _insert(db_path, mid, file_type="video", duration=0, stored_path="fake.mp4", name="test.mp4"):
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """INSERT INTO materials (id, original_filename, stored_path, file_type, duration)
           VALUES (?, ?, ?, ?, ?)""",
        (mid, name, stored_path, file_type, duration),
    )
    conn.commit()
    conn.close()


def _get_duration(db_path, mid):
    conn = sqlite3.connect(str(db_path))
    row = conn.execute("SELECT duration FROM materials WHERE id = ?", (mid,)).fetchone()
    conn.close()
    return row[0] if row else None


class _BaseDBTest(unittest.TestCase):
    """每个子类/每次运行都用独立临时 DB，patch conf.BASE_DIR。"""

    db_path = None
    tmp_dir = None

    @classmethod
    def setUpClass(cls):
        cls.tmp_dir, cls.db_path = _make_db()
        cls._patcher = patch.object(conf, "BASE_DIR", cls.tmp_dir)
        cls._patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls._patcher.stop()

    def setUp(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM materials")
        conn.commit()
        conn.close()
        # 清空 inflight 集合，避免跨用例污染
        from services import duration_repair
        duration_repair._inflight_ids.clear()

    def _insert(self, mid, **kw):
        _insert(self.db_path, mid, **kw)

    def _get(self, mid):
        return _get_duration(self.db_path, mid)


class TestRepairZeroDurations(_BaseDBTest):
    def test_repairs_zero_duration_video(self):
        """duration=0 的视频应被识别写库"""
        from services import duration_repair
        self._insert("vid-1", duration=0, stored_path="a.mp4")
        with patch("storage.resolve_material_path", return_value="/tmp/a.mp4"), \
             patch("services.duration_repair.get_video_duration_safe",
                   return_value=88.5), \
             patch("time.sleep"), \
             patch.object(Path, "is_file", return_value=True):
            duration_repair.repair_zero_durations()
        assert self._get("vid-1") == 88.5

    def test_skips_nonzero_duration(self):
        """已有正常时长的视频不在查询范围内（SQL 已过滤）"""
        from services import duration_repair
        self._insert("vid-ok", duration=120.0, stored_path="b.mp4")
        with patch("services.duration_repair.get_video_duration_safe",
                   return_value=999.0) as mock_probe, \
             patch("time.sleep"):
            duration_repair.repair_zero_durations()
        # 不会被覆盖：SQL 只查 duration<=0 的
        assert self._get("vid-ok") == 120.0
        assert not mock_probe.called

    def test_skips_images(self):
        """图片素材不被处理"""
        from services import duration_repair
        self._insert("img-1", file_type="image", duration=0, stored_path="c.jpg")
        with patch("services.duration_repair.get_video_duration_safe",
                   return_value=999.0) as mock_probe, \
             patch("time.sleep"):
            duration_repair.repair_zero_durations()
        assert not mock_probe.called
        # 图片 duration 保持 0（未被改写）
        assert self._get("img-1") == 0

    def test_probe_failure_does_not_crash(self):
        """单条识别失败（时长仍为 0）不影响整体流程"""
        from services import duration_repair
        self._insert("vid-bad", duration=0, stored_path="d.mp4")
        with patch("storage.resolve_material_path", return_value="/tmp/d.mp4"), \
             patch("services.duration_repair.get_video_duration_safe",
                   return_value=0.0), \
             patch("time.sleep"), \
             patch.object(Path, "is_file", return_value=True):
            # 不应抛异常
            duration_repair.repair_zero_durations()
        # 失败的条目 duration 仍为 0，但流程正常结束
        assert self._get("vid-bad") == 0


class TestEnsureDurationOrProbe(_BaseDBTest):
    def test_returns_existing_duration_without_probe(self):
        """已有正常时长直接返回，不触发识别"""
        from services import duration_repair
        self._insert("vid-e", duration=60.0, stored_path="e.mp4")
        with patch("services.duration_repair.get_video_duration_safe",
                   return_value=999.0) as mock_probe:
            result = duration_repair.ensure_duration_or_probe("e.mp4", 60.0)
        assert result == 60.0
        assert not mock_probe.called

    def test_probes_when_missing(self):
        """duration 缺失时同步识别并写库"""
        from services import duration_repair
        self._insert("vid-m", duration=0, stored_path="m.mp4")
        with patch("storage.resolve_material_path", return_value="/tmp/m.mp4"), \
             patch("services.duration_repair.get_video_duration_safe",
                   return_value=77.0), \
             patch.object(Path, "is_file", return_value=True):
            result = duration_repair.ensure_duration_or_probe("m.mp4", 0.0)
        assert result == 77.0
        assert self._get("vid-m") == 77.0

    def test_returns_db_duration_on_second_call(self):
        """已被后台补全时，第二次调用直接读 DB 返回，不再 probe"""
        from services import duration_repair
        self._insert("vid-d", duration=0, stored_path="d2.mp4")
        # 第一次：补全到 DB
        with patch("storage.resolve_material_path", return_value="/tmp/d2.mp4"), \
             patch("services.duration_repair.get_video_duration_safe",
                   return_value=55.0), \
             patch.object(Path, "is_file", return_value=True):
            duration_repair.ensure_duration_or_probe("d2.mp4", 0.0)
        # 第二次：传入 0，但 DB 已有值，应直接返回 DB 值，不 probe
        with patch("services.duration_repair.get_video_duration_safe",
                   return_value=999.0) as mock_probe:
            result = duration_repair.ensure_duration_or_probe("d2.mp4", 0.0)
        assert result == 55.0
        assert not mock_probe.called


if __name__ == "__main__":
    unittest.main()
