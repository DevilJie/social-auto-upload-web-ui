"""PublishTask 扩展字段测试。"""
import sys
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from ext_api.task_queue import PublishTask, TaskStatus, TaskQueue, aggregate_batch_status


def test_publish_task_default_new_fields():
    """新字段默认值。"""
    t = PublishTask()
    assert t.source == ''
    assert t.draft_id == 0
    assert t.account_id == 0
    assert t.payload == {}
    assert t.detail_id == ''


def test_publish_task_to_dict_includes_payload():
    """to_dict 不再序列化 payload（payload 是 in-memory，不持久化）。"""
    t = PublishTask(
        platform='bilibili', platform_type=5,
        source='draft', draft_id=42, account_id=3,
        payload={'title': 'T', 'files': ['/a.mp4']},
        detail_id='d-1',
    )
    d = t.to_dict()
    assert d['source'] == 'draft'
    assert d['draft_id'] == 42
    assert d['account_id'] == 3
    assert d['detail_id'] == 'd-1'
    # payload 不持久化（in-memory only），不再被 JSON 编码到 to_dict
    assert d['payload'] == {'title': 'T', 'files': ['/a.mp4']}
    assert not isinstance(d['payload'], str)


def test_publish_task_from_row_round_trip():
    """to_dict → from_row 往返保留新字段（payload in-memory，不进 DB）。"""
    t = PublishTask(
        platform='douyin', platform_type=3,
        source='draft', draft_id=99, account_id=5,
        payload={'title': 'X', 'ai_content': '内容由AI生成'},
        detail_id='d-2',
    )
    d = t.to_dict()
    t2 = PublishTask.from_row(d)
    assert t2.source == 'draft'
    assert t2.draft_id == 99
    assert t2.account_id == 5
    assert t2.detail_id == 'd-2'
    # payload 是 in-memory 字段，from_row 后回到默认 {}
    assert t2.payload == {}


def test_execute_splats_payload_to_platform_publish_video():
    """_execute 当 task.payload 非空时调 platform.publish_video(**payload)。"""
    from ext_api import task_queue as tq
    from ext_api.task_queue import TaskStatus

    # 构造一个最小 task
    t = PublishTask(
        platform='xiaohongshu', platform_type=1,
        payload={'title': 'T', 'files': ['/a.mp4'], 'tags': ['x'],
                 'desc': 'D', 'ai_content': '内容由AI生成'},
        account_id=1, source='draft', draft_id=42,
    )

    # Mock platform
    fake_platform = MagicMock()
    fake_platform.publish_video = MagicMock(return_value=True)

    with patch.object(tq, 'get_platform', return_value=fake_platform):
        queue = tq.get_task_queue()
        asyncio.run(queue._execute(t))

    # 验证 publish_video 被以 payload kwargs 调用
    fake_platform.publish_video.assert_called_once()
    call_kwargs = fake_platform.publish_video.call_args.kwargs
    assert call_kwargs['title'] == 'T'
    assert call_kwargs['files'] == ['/a.mp4']
    assert call_kwargs['tags'] == ['x']
    assert call_kwargs['desc'] == 'D'
    assert call_kwargs['ai_content'] == '内容由AI生成'


def test_execute_async_publish_video():
    """platform.publish_video 是 async 时也走 splat。"""
    from ext_api import task_queue as tq

    async def fake_async_publish(**kwargs):
        return True

    fake_platform = MagicMock()
    fake_platform.publish_video = fake_async_publish

    t = PublishTask(
        platform='douyin', platform_type=3,
        payload={'title': 'X', 'files': ['/a.mp4']},
    )

    with patch.object(tq, 'get_platform', return_value=fake_platform):
        queue = tq.get_task_queue()
        result = asyncio.run(queue._execute(t))

    assert result is True


def _make_test_queue():
    """构造一个 TaskQueue 实例但不启动后台线程/事件循环。"""
    q = TaskQueue(max_concurrent=1)
    return q


def _run_worker_through_tasks(worker, tasks_and_outcomes):
    """驱动 _worker 跑完一组任务场景，最后用 CancelledError 退出循环。

    tasks_and_outcomes: list of (PublishTask, outcome) where outcome in
        {'success', 'fail-retry', 'fail-permanent'}

    'fail-retry' 任务会在第一次处理时入队（retry_count 1 <= max_retries 1），
    第二次处理时 retry_count 2 > max_retries 1，进入永久失败分支。

    实现细节：用 asyncio.CancelledError 作为"无更多任务"的 sentinel，
    协程最外层的 `await self.queue.get()` 在 try/except 之外，会传播到 asyncio.run。
    我们在外层捕获这个 CancelledError 视为正常的"测试结束"信号。
    """
    task_done_calls = []

    queue = MagicMock()
    iter_state = {'idx': 0}
    queued_tasks = []

    def compute_remaining():
        return iter_state['idx'] < len(tasks_and_outcomes) or queued_tasks

    async def fake_get():
        if queued_tasks:
            return queued_tasks.pop(0)
        if compute_remaining():
            idx = iter_state['idx']
            iter_state['idx'] += 1
            return tasks_and_outcomes[idx][0]
        # sentinel: 抛 CancelledError 让 worker 协程从最外层 get() 退出
        raise asyncio.CancelledError("no more tasks")

    def fake_task_done():
        task_done_calls.append(iter_state['idx'])

    queue.get = fake_get
    async def fake_put(t):
        queued_tasks.append(t)
    queue.put = fake_put
    queue.task_done = fake_task_done

    worker.queue = queue
    worker.running = {}
    worker.completed = []
    worker._update_db = MagicMock()
    worker._notify_status = MagicMock()

    exec_idx = {'n': 0}

    async def fake_execute(task):
        outcome = tasks_and_outcomes[exec_idx['n']][1]
        if outcome == 'fail-retry':
            exec_idx['n'] += 1
            raise RuntimeError("simulated failure")
        elif outcome == 'fail-permanent':
            exec_idx['n'] += 1
            raise RuntimeError("simulated permanent failure")
        else:
            exec_idx['n'] += 1
            return True

    worker._execute = fake_execute

    for task, _ in tasks_and_outcomes:
        task.max_retries = 1

    # Patch asyncio.sleep 让重试退避不实际等待
    real_sleep = asyncio.sleep
    async def fast_sleep(_):
        await real_sleep(0)
    with patch('ext_api.task_queue.asyncio.sleep', side_effect=fast_sleep):
        try:
            asyncio.run(worker._worker("test-worker"))
        except asyncio.CancelledError:
            pass  # expected: sentinel triggers worker exit

    return task_done_calls


def _run_worker_through_tasks_cancellable(worker, tasks_and_outcomes):
    """驱动 _worker 跑完一组任务场景，捕获 CancelledError 用于退出循环。"""
    task_done_calls = []

    queue = MagicMock()
    iter_state = {'idx': 0}
    queued_tasks = []

    def compute_remaining():
        return iter_state['idx'] < len(tasks_and_outcomes) or queued_tasks

    async def fake_get_v2():
        if queued_tasks:
            return queued_tasks.pop(0)
        if compute_remaining():
            idx = iter_state['idx']
            iter_state['idx'] += 1
            return tasks_and_outcomes[idx][0]
        # 用 CancelledError 退出 worker 协程
        raise asyncio.CancelledError("no more tasks")

    def fake_task_done():
        task_done_calls.append(iter_state['idx'])

    queue.get = fake_get_v2
    queue.put = lambda t: queued_tasks.append(t)
    queue.task_done = fake_task_done

    worker.queue = queue
    worker.running = {}
    worker.completed = []
    worker._update_db = MagicMock()
    worker._notify_status = MagicMock()

    exec_idx = {'n': 0}

    async def fake_execute(task):
        outcome = tasks_and_outcomes[exec_idx['n']][1]
        if outcome == 'fail-retry':
            exec_idx['n'] += 1
            raise RuntimeError("simulated failure")
        elif outcome == 'fail-permanent':
            exec_idx['n'] += 1
            raise RuntimeError("simulated permanent failure")
        else:
            exec_idx['n'] += 1
            return True

    worker._execute = fake_execute

    for task, _ in tasks_and_outcomes:
        task.max_retries = 1

    # 跑 worker 协程，期望其以 CancelledError 退出
    try:
        asyncio.run(worker._worker("test-worker"))
    except asyncio.CancelledError:
        pass  # expected: sentinel 触发 worker 退出

    return task_done_calls


def test_worker_task_done_called_once_on_success():
    """成功路径：task_done() 在 finally 中调用 1 次。"""
    worker = _make_test_queue()
    t = PublishTask(platform='xiaohongshu', platform_type=1, account_name='a1')
    calls = _run_worker_through_tasks(worker, [(t, 'success')])
    assert len(calls) == 1, f"expected exactly one task_done call, got {len(calls)}: {calls}"
    assert t.status == TaskStatus.SUCCESS


def test_worker_task_done_called_once_after_retry():
    """失败重试路径：第一次 task_done() 在 retry 路径，第二次（永久失败）在 finally。共 2 次，无 ValueError。"""
    worker = _make_test_queue()
    t = PublishTask(platform='douyin', platform_type=3, account_name='a1')
    t.max_retries = 1
    # 用 fail-retry：第一次失败触发 retry（re-queue），第二次再失败（max_retries 耗尽）
    calls = _run_worker_through_tasks(worker, [(t, 'fail-retry')])
    # 两次循环（一次 retry 重入队，一次最终失败）应该恰好 2 次 task_done
    assert len(calls) == 2, f"expected 2 task_done calls (retry + permanent), got {len(calls)}: {calls}"
    assert t.status == TaskStatus.FAILED


def test_worker_no_double_task_done():
    """回归测试：连续重试后 worker 不应触发 'task_done() called too many times'。

    在 asyncio.Queue 中，重复 task_done() 会抛 ValueError。这里通过一个
    使用真实 asyncio.Queue 的版本验证：worker 跑完后 unfinished_tasks 应等于 0
    （每次 get 都有对应 task_done），并且 worker 不抛 ValueError。

    通过在 task_done 上 wrap 计数 + 主动关闭 queue 模拟 sentinel 退出。
    """
    q = TaskQueue(max_concurrent=1)
    real_queue = asyncio.Queue()
    real_queue.put_nowait(PublishTask(
        platform='bilibili', platform_type=5, account_name='a1', max_retries=1
    ))
    q.queue = real_queue
    q.running = {}
    q.completed = []
    q._update_db = MagicMock()
    q._notify_status = MagicMock()

    call_count = {'n': 0}

    async def always_fail(task):
        call_count['n'] += 1
        raise RuntimeError("always fail")

    q._execute = always_fail

    # Wrap 真实 queue.task_done 计数
    real_task_done = real_queue.task_done
    task_done_count = {'n': 0}
    def counting_task_done():
        task_done_count['n'] += 1
        real_task_done()
    real_queue.task_done = counting_task_done

    # Patch asyncio.sleep 让重试退避不实际等待
    real_sleep = asyncio.sleep
    async def fast_sleep(_):
        await real_sleep(0)
    with patch('ext_api.task_queue.asyncio.sleep', side_effect=fast_sleep):
        # 启动 worker，超时打断无限循环
        async def main():
            try:
                await asyncio.wait_for(q._worker("test"), timeout=0.5)
            except asyncio.TimeoutError:
                pass
        asyncio.run(main())

    # worker 处理了 2 次（一次 retry 一次 permanent fail）→ 2 次 task_done
    # 在真实 asyncio.Queue 上，2 次 get + 2 次 task_done = 内部 counter 一致
    # 如果有 bug（double task_done），第二次 task_done 会抛 ValueError
    assert call_count['n'] == 2, f"execute should run 2 times, ran {call_count['n']}"
    assert task_done_count['n'] == 2, (
        f"task_done should be called 2 times, was called {task_done_count['n']} times"
    )
    # 验证 queue 内部 unfinished_tasks 已归零（说明 task_done 配对正确）
    assert real_queue._unfinished_tasks == 0, (
        f"queue unfinished_tasks should be 0, got {real_queue._unfinished_tasks}"
    )


# ---------- aggregate_batch_status 聚合逻辑测试 ----------

def test_aggregate_batch_status_total_zero_is_pending():
    """total=0 时返回 pending（理论上不会出现，仅防御）。"""
    assert aggregate_batch_status(succ=0, fail=0, in_flight=0, total=0) == 'pending'


def test_aggregate_batch_status_all_success():
    """全部成功 → success。"""
    assert aggregate_batch_status(succ=3, fail=0, in_flight=0, total=3) == 'success'


def test_aggregate_batch_status_all_failed():
    """全部失败 → failed。"""
    assert aggregate_batch_status(succ=0, fail=3, in_flight=0, total=3) == 'failed'


def test_aggregate_batch_status_mixed_partial():
    """混合（有成功有失败，无 in-flight）→ partial。"""
    assert aggregate_batch_status(succ=2, fail=1, in_flight=0, total=3) == 'partial'


def test_aggregate_batch_status_in_flight_with_only_success_returns_running():
    """回归测试：3 success + 0 failed + 2 in-flight → 必须是 running（不是 success）。

    修复前旧逻辑会因 fail==0 直接返回 'success'，导致详情仍处于 queued/running 时
    batch 已显示"全部成功"。
    """
    assert aggregate_batch_status(succ=3, fail=0, in_flight=2, total=5) == 'running'


def test_aggregate_batch_status_in_flight_with_mixed_returns_running():
    """回归测试：1 success + 1 failed + 1 queued → 必须是 running（不是 partial）。

    即便已有 failed/成功，只要仍有 in-flight detail，batch 不应判定为终态。
    """
    assert aggregate_batch_status(succ=1, fail=1, in_flight=1, total=3) == 'running'


def test_aggregate_batch_status_in_flight_priority_over_fail_zero():
    """in-flight 检查必须在 fail==0 分支之前：哪怕 fail=0，有 in-flight 也应 running。"""
    assert aggregate_batch_status(succ=0, fail=0, in_flight=1, total=1) == 'running'


def test_aggregate_batch_status_in_flight_with_queued_only():
    """单条 queued 详情（in_flight=1）→ running。"""
    assert aggregate_batch_status(succ=0, fail=0, in_flight=1, total=1) == 'running'


def test_aggregate_batch_status_single_running_detail():
    """单条 running 详情 → running。"""
    assert aggregate_batch_status(succ=0, fail=0, in_flight=1, total=1) == 'running'