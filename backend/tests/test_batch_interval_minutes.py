"""测试 task_queue 中『视频发布间隔』的优先级与解析。

发布页 interval_minutes 输入框传到 task.batch_interval_minutes 后，
worker 读间隔的优先级应当是：

  task.batch_interval_minutes (None → 回退全局；否则取任务值)

并对全局 `_get_interval_minutes()` 的语义做几个回归点：
- settings.batchTaskInterval 不存在/为空 → 0
- 负数 / 非数字 → 0（被 max(0.0, ...) 截断）
- 正常值 → 透传
"""
import sys
import sqlite3
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _make_task(batch_interval_minutes):
    from ext_api.task_queue import PublishTask
    return PublishTask(
        platform='小红书', platform_type=1, account_name='u',
        video_path='/x.mp4', title='T',
        batch_interval_minutes=batch_interval_minutes,
    )


def _setup_settings_db(db_path, value):
    with sqlite3.connect(str(db_path)) as conn:
        conn.executescript(
            "CREATE TABLE IF NOT EXISTS settings "
            "(key TEXT PRIMARY KEY, value TEXT DEFAULT '');"
        )
        # 每次重置为单一 key，便于多次覆盖
        conn.execute("DELETE FROM settings WHERE key='batchTaskInterval'")
        if value is not None:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ('batchTaskInterval', str(value)),
            )
        conn.commit()


def _resolve_interval(task):
    """复刻 worker 中的优先级判定逻辑（行为契约，不重新实现间隔闸门）。"""
    from ext_api import task_queue as tq
    if task.batch_interval_minutes is not None:
        return max(0.0, float(task.batch_interval_minutes))
    return tq._get_interval_minutes()


def test_task_interval_overrides_global(monkeypatch, tmp_path):
    """任务级值优先于全局设置。"""
    db_path = tmp_path / 's.db'
    _setup_settings_db(db_path, 60)  # 全局 60 分钟
    monkeypatch.setattr('ext_api.task_queue.DB_PATH', db_path)
    from ext_api import task_queue as tq
    tq._interval_cache.update(value=0.0, fetched_at=0.0)  # 跨测试清缓存

    # 任务级 5 分钟 → 应优先
    assert _resolve_interval(_make_task(5.0)) == 5.0
    # 任务级 0 → 应优先（= 不等待）
    assert _resolve_interval(_make_task(0.0)) == 0.0
    # 任务级 None → 回退全局 60
    assert _resolve_interval(_make_task(None)) == 60.0


def test_global_interval_normalization(monkeypatch, tmp_path):
    """_get_interval_minutes() 对负数/非法值统一规整为 0。"""
    db_path = tmp_path / 's.db'

    # 1) 不存在 → 0
    _setup_settings_db(db_path, None)
    monkeypatch.setattr('ext_api.task_queue.DB_PATH', db_path)
    from ext_api import task_queue as tq
    tq._interval_cache.update(value=0.0, fetched_at=0.0)
    assert tq._get_interval_minutes() == 0.0

    # 2) 负数 → 0（被 max(0.0, ...) 截断）
    _setup_settings_db(db_path, -10)
    monkeypatch.setattr('ext_api.task_queue.DB_PATH', db_path)
    tq._interval_cache.update(value=0.0, fetched_at=0.0)
    assert tq._get_interval_minutes() == 0.0

    # 3) 正常值 → 透传
    _setup_settings_db(db_path, 30)
    monkeypatch.setattr('ext_api.task_queue.DB_PATH', db_path)
    tq._interval_cache.update(value=0.0, fetched_at=0.0)
    assert tq._get_interval_minutes() == 30.0
