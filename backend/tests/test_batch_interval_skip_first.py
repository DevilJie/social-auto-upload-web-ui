"""验证批次间隔等待的新架构（用户反馈：第一个视频卡死不发布）。

旧架构 bug：worker 完成任务后持锁 sleep(interval) —— 单 worker 下新提交的
任务（包括新批次的第一个视频）会被上一轮的间隔 sleep 阻塞最长 30 分钟，
且 sleep 无法被取消打断。

新架构：不持锁。worker 取到 task 时调用 _wait_batch_interval：
  - 本批次无完成记录（第一个 task）→ 立即执行
  - 有记录且未满间隔 → 分段等待（每段 ≤1s，可被取消打断）
  - 等待期间被取消 → 立即返回，走取消分支
  - 不同批次互不阻塞

本测试直接调用生产代码 TaskQueue._wait_batch_interval（不再重新模拟 worker）。
"""
import sys
import asyncio
import os
import tempfile
import time as time_mod
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

_tmpdir = tempfile.mkdtemp()
os.environ['SAU_DATA_DIR'] = _tmpdir


def _make_queue():
    from ext_api import task_queue as tq
    q = tq.TaskQueue(max_concurrent=1)
    q._started = True  # 跳过线程启动
    q.queue = asyncio.Queue()
    return q


def _make_task(task_id, batch_id):
    from ext_api.task_queue import PublishTask
    return PublishTask(
        id=task_id, batch_id=batch_id, platform='x', platform_type=1,
        account_name='u', video_path='/x.mp4', title='T',
    )


def test_first_task_of_batch_waits_zero():
    """本批次无完成记录 → 第一个 task 立即执行（不等任何间隔）。"""
    q = _make_queue()
    t = _make_task('t1', 'batch-A')

    async def run():
        t0 = time_mod.monotonic()
        await q._wait_batch_interval(t, interval_min=30.0)  # 即使 30 分钟也不等
        return time_mod.monotonic() - t0

    elapsed = asyncio.run(run())
    assert elapsed < 0.05, f'first task should not wait, took {elapsed:.3f}s'


def test_new_batch_not_blocked_by_old_batch():
    """批次 A 有完成记录，批次 B 的第一个 task 不受影响（立即执行）。"""
    q = _make_queue()
    # 批次 A 刚完成 —— 30 分钟间隔的等待点在遥远的未来
    q._batch_last_finished['batch-A'] = time_mod.time()
    t_b = _make_task('tB1', 'batch-B')

    async def run():
        t0 = time_mod.monotonic()
        await q._wait_batch_interval(t_b, interval_min=30.0)
        return time_mod.monotonic() - t0

    elapsed = asyncio.run(run())
    assert elapsed < 0.05, (
        f'new batch first task must not be blocked by old batch, took {elapsed:.3f}s'
    )


def test_same_batch_second_task_waits_interval():
    """同批次第二个 task 需等待剩余间隔（用极小间隔 0.001 分钟=60ms 实测）。"""
    q = _make_queue()
    t2 = _make_task('t2', 'batch-C')
    q._batch_last_finished['batch-C'] = time_mod.time()

    async def run():
        t0 = time_mod.monotonic()
        await q._wait_batch_interval(t2, interval_min=0.001)  # 60ms
        return time_mod.monotonic() - t0

    elapsed = asyncio.run(run())
    assert 0.03 < elapsed < 2.0, (
        f'second task should wait ~60ms, took {elapsed:.3f}s'
    )


def test_cancel_during_wait_returns_immediately():
    """等待期间被用户取消 → 立即返回（不等满间隔）。"""
    q = _make_queue()
    t = _make_task('t3', 'batch-D')
    # 完成点设为"刚刚"，间隔 30 分钟 → 正常要等 ~30 分钟
    q._batch_last_finished['batch-D'] = time_mod.time()
    # 模拟用户在等待开始前就标记了取消
    with q._cancel_lock:
        q._cancelled_ids.add(t.id)

    async def run():
        t0 = time_mod.monotonic()
        await q._wait_batch_interval(t, interval_min=30.0)
        return time_mod.monotonic() - t0

    elapsed = asyncio.run(run())
    assert elapsed < 1.5, (
        f'cancelled task must skip interval wait (≤1.5s for one tick), took {elapsed:.3f}s'
    )


def test_interval_expired_runs_immediately():
    """记录的完成点已超过间隔（等待已过期）→ 立即执行。"""
    q = _make_queue()
    t = _make_task('t4', 'batch-E')
    # 10 分钟前完成，间隔 1 分钟 → 早就到点
    q._batch_last_finished['batch-E'] = time_mod.time() - 600

    async def run():
        t0 = time_mod.monotonic()
        await q._wait_batch_interval(t, interval_min=1.0)
        return time_mod.monotonic() - t0

    elapsed = asyncio.run(run())
    assert elapsed < 0.05, f'expired wait should return at once, took {elapsed:.3f}s'
