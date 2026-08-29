"""发布链调度测试（用户设计的 DB 驱动链式调度）。

规则：
  1. 提交时建链（interval_minutes + next_batch_id），链头立即入队，
     后续视频暂存 _pending_batches 并写库 details=pending。
  2. 前驱视频全部任务终态（无论成败）→ _on_batch_maybe_finished 写
     next.scheduled_at = now + interval。
  3. _scheduler_tick 轮询：scheduled_at 到点 → 暂存任务入队执行；
     到点但暂存丢失（重启断链）→ 标 failed 提示重发。
  4. 取消：待排程视频可直接取消（未入队也生效）。
"""
import sys
import asyncio
import os
import sqlite3
import tempfile
import time as time_mod
from pathlib import Path
from datetime import datetime, timedelta

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir

_SCHEMA = """
CREATE TABLE publish_batches (
    id TEXT PRIMARY KEY,
    type TEXT DEFAULT 'video',
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    status TEXT DEFAULT 'pending',
    account_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    created_at TIMESTAMP, updated_at TIMESTAMP,
    started_at TIMESTAMP, finished_at TIMESTAMP,
    source TEXT DEFAULT '', draft_id INTEGER DEFAULT 0,
    scheduled_at TEXT DEFAULT '',
    interval_minutes REAL DEFAULT 0,
    next_batch_id TEXT DEFAULT ''
);
CREATE TABLE publish_details (
    id TEXT PRIMARY KEY,
    batch_id TEXT,
    status TEXT DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    error_message TEXT DEFAULT '',
    publish_url TEXT DEFAULT '',
    created_at TIMESTAMP, updated_at TIMESTAMP,
    started_at TIMESTAMP, finished_at TIMESTAMP
);
"""


def _setup(tmp_path, monkeypatch):
    db = tmp_path / "chain.db"
    with sqlite3.connect(str(db)) as conn:
        conn.executescript(_SCHEMA)
    monkeypatch.setattr('ext_api.task_queue.DB_PATH', db)
    from ext_api import task_queue as tq
    q = tq.TaskQueue(max_concurrent=1)
    q._started = True
    q._update_db = lambda *a, **k: None   # 不写库（部分用例单独验库）
    q._notify_status = lambda *a, **k: None
    return q, db


def _batch_row(db, bid, *, interval=2.0, nxt='', scheduled='', status='pending'):
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT INTO publish_batches (id, type, status, interval_minutes,"
            " next_batch_id, scheduled_at, created_at, updated_at)"
            " VALUES (?, 'video', ?, ?, ?, ?, ?, ?)",
            (bid, status, interval, nxt, scheduled,
             datetime.now().isoformat(), datetime.now().isoformat()),
        )


def _detail_row(db, did, bid, status):
    with sqlite3.connect(str(db)) as conn:
        conn.execute(
            "INSERT INTO publish_details (id, batch_id, status, created_at)"
            " VALUES (?, ?, ?, ?)",
            (did, bid, status, datetime.now().isoformat()),
        )


def _make_task(task_id, batch_id, interval=2.0):
    from ext_api.task_queue import PublishTask
    return PublishTask(
        id=task_id, batch_id=batch_id, platform='x', platform_type=1,
        account_name='u', video_path='/x.mp4', title='T',
        batch_interval_minutes=interval,
    )


def test_chain_schedules_next_after_batch_finish(tmp_path, monkeypatch):
    """前驱视频全部任务终态 → 下一个视频 scheduled_at = now + interval。"""
    q, db = _setup(tmp_path, monkeypatch)
    _batch_row(db, 'v1', interval=2.0, nxt='v2')
    _batch_row(db, 'v2', interval=2.0)
    _detail_row(db, 'd1', 'v1', 'failed')   # 无论成败
    _detail_row(db, 'd2', 'v1', 'cancelled')

    q._on_batch_maybe_finished(_make_task('d1', 'v1', 2.0))

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT scheduled_at, status FROM publish_batches WHERE id='v2'"
        ).fetchone()
    assert row[0], 'next video should be scheduled'
    assert row[1] == 'pending'
    due = datetime.fromisoformat(row[0])
    delta = (due - datetime.now()).total_seconds()
    assert 100 < delta < 140, f'scheduled ~2min ahead, got {delta:.0f}s'


def test_chain_waits_until_whole_batch_terminal(tmp_path, monkeypatch):
    """前驱视频还有任务未完成 → 不排程下一个。"""
    q, db = _setup(tmp_path, monkeypatch)
    _batch_row(db, 'v1', interval=1.0, nxt='v2')
    _batch_row(db, 'v2', interval=1.0)
    _detail_row(db, 'd1', 'v1', 'success')
    _detail_row(db, 'd2', 'v1', 'running')   # 还有 1 个在跑

    q._on_batch_maybe_finished(_make_task('d1', 'v1', 1.0))

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT scheduled_at FROM publish_batches WHERE id='v2'"
        ).fetchone()
    assert row[0] == '', 'must NOT schedule while batch unfinished'


def test_chain_no_double_schedule(tmp_path, monkeypatch):
    """下一个视频已排程过 → 不覆盖（UPDATE 条件 scheduled_at=''）。"""
    q, db = _setup(tmp_path, monkeypatch)
    fixed = (datetime.now() + timedelta(minutes=5)).isoformat()
    _batch_row(db, 'v1', interval=2.0, nxt='v2')
    _batch_row(db, 'v2', interval=2.0, scheduled=fixed)
    _detail_row(db, 'd1', 'v1', 'success')

    q._on_batch_maybe_finished(_make_task('d1', 'v1', 2.0))

    with sqlite3.connect(str(db)) as conn:
        row = conn.execute(
            "SELECT scheduled_at FROM publish_batches WHERE id='v2'"
        ).fetchone()
    assert row[0] == fixed, 'existing schedule must not be overwritten'


def test_scheduler_tick_enqueues_due_batch(tmp_path, monkeypatch):
    """到点的待发布视频 → 暂存任务入队执行。"""
    q, db = _setup(tmp_path, monkeypatch)
    past = (datetime.now() - timedelta(seconds=5)).isoformat()
    _batch_row(db, 'v2', interval=0.02, scheduled=past)   # 0.02 分钟前到期
    t = _make_task('d1', 'v2', 0.02)
    q.add_pending_batch('v2', [t])

    enqueued = []
    q.add_task = lambda task: enqueued.append(task)   # 记录入队
    q._scheduler_tick()

    assert [x.id for x in enqueued] == ['d1'], 'due task should be enqueued'
    with q._pending_lock:
        assert 'v2' not in q._pending_batches, 'pending batch should be consumed'


def test_scheduler_tick_marks_restart_broken_chain(tmp_path, monkeypatch):
    """到点但暂存丢失（重启）→ batch/details 标 failed 提示重发。"""
    q, db = _setup(tmp_path, monkeypatch)
    past = (datetime.now() - timedelta(seconds=5)).isoformat()
    _batch_row(db, 'v2', interval=1.0, scheduled=past)
    _detail_row(db, 'd1', 'v2', 'pending')

    q._scheduler_tick()

    with sqlite3.connect(str(db)) as conn:
        b = conn.execute(
            "SELECT status FROM publish_batches WHERE id='v2'"
        ).fetchone()
        d = conn.execute(
            "SELECT status, error_message FROM publish_details WHERE id='d1'"
        ).fetchone()
    assert b[0] == 'failed'
    assert d[0] == 'failed'
    assert '重新发布' in d[1]


def test_scheduler_tick_ignores_not_due(tmp_path, monkeypatch):
    """未到点 → 不入队。"""
    q, db = _setup(tmp_path, monkeypatch)
    future = (datetime.now() + timedelta(minutes=10)).isoformat()
    _batch_row(db, 'v2', interval=2.0, scheduled=future)
    q.add_pending_batch('v2', [_make_task('d1', 'v2', 2.0)])

    enqueued = []
    q.add_task = lambda task: enqueued.append(task)
    q._scheduler_tick()
    assert enqueued == [], 'future batch must not be enqueued'


def test_cancel_pending_batch_cancels_without_enqueue(tmp_path, monkeypatch):
    """取消待排程视频：任务直接落 cancelled，不入队。"""
    from ext_api.task_queue import TaskStatus
    q, db = _setup(tmp_path, monkeypatch)
    _batch_row(db, 'v2', interval=30.0)
    t = _make_task('d1', 'v2', 30.0)
    q.add_pending_batch('v2', [t])

    ok = q.cancel_task('d1')   # 通过 task_id 路由到待排程取消

    assert ok is True
    assert t.status == TaskStatus.CANCELLED
    assert t.error_message == '用户取消发布'
    with q._pending_lock:
        assert 'v2' not in q._pending_batches


def test_worker_chain_tasks_no_interval_wait(tmp_path, monkeypatch):
    """发布链任务在 worker 里不等待（间隔由 DB 调度器负责），快速背靠背执行。"""
    from ext_api.task_queue import TaskStatus
    q, db = _setup(tmp_path, monkeypatch)

    async def fake_execute(task):
        await asyncio.sleep(0.02)

    q._execute = fake_execute
    started_at = {}

    def notify(task):
        if task.status == TaskStatus.RUNNING and task.id not in started_at:
            started_at[task.id] = time_mod.monotonic()

    q._notify_status = notify
    # 两个不同视频的任务都带 batch_interval_minutes → chain_mode → worker 不等待
    q.queue = asyncio.Queue()

    async def run():
        q.queue.put_nowait(_make_task('t1', 'vA', 30.0))
        q.queue.put_nowait(_make_task('t2', 'vB', 30.0))
        w = asyncio.ensure_future(q._worker('w1'))
        for _ in range(400):
            if len(q.completed) >= 2:
                break
            await asyncio.sleep(0.01)
        w.cancel()
        try:
            await w
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert all(t.status == TaskStatus.SUCCESS for t in q.completed)
    gap = started_at['t2'] - started_at['t1']
    assert gap < 0.15, (
        f'chain tasks must run back-to-back in worker (interval handled by '
        f'DB scheduler), gap={gap:.3f}s'
    )
