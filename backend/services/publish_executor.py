"""异步发布执行器 —— /postVideo 的后台串行执行层。

背景（根治目标）：大视频发布耗时几分钟到几十分钟，此前 /postVideo 在
HTTP 请求线程里同步等浏览器自动化跑完；挂起期间连接一旦被传输层掐断
（WebView2 网络栈 / 系统休眠恢复 / 页面刷新），前端就判失败并继续发布
下一个账号，而后端浏览器仍在发布，最终同时打开多个浏览器并发发布。

方案：/postVideo 只做参数校验并入队，立即返回 taskId；真正的发布在本
模块的**单工作线程**里串行执行——任意时刻最多 1 个浏览器在发布，天然
杜绝并发开多个浏览器。前端轮询 /postVideo/status/<task_id> 拿最终结果，
HTTP 请求本身秒回，不再存在「接口超时但后端还在发」。

任务状态为内存态（进程重启即丢）；发布结果的持久化仍由 app.py 的
_record_publish / _update_publish_result 写 publish_batches /
publish_details，任务丢失后以发布历史为准。
"""

import queue
import threading
import time
import uuid

# 终态任务保留 2 小时（供前端刷新/断线后补查），超时清理
_TASK_TTL_SECONDS = 2 * 60 * 60
# 终态任务最多保留条数（防内存无限增长）
_MAX_FINISHED_TASKS = 200

TERMINAL_STATUSES = ('success', 'failed')

_lock = threading.Lock()
_tasks: dict[str, dict] = {}
_queue: "queue.Queue" = queue.Queue()
_worker_started = False


def _prune_locked(now: float) -> None:
    """清理过期/超量的终态任务（调用方需已持有 _lock）。"""
    expired = [
        tid for tid, t in _tasks.items()
        if t['status'] in TERMINAL_STATUSES
        and now - (t['finishedAt'] or now) > _TASK_TTL_SECONDS
    ]
    for tid in expired:
        _tasks.pop(tid, None)
    # 仍超量则按完成时间淘汰最旧的终态任务
    finished = sorted(
        (t for t in _tasks.values() if t['status'] in TERMINAL_STATUSES),
        key=lambda t: t['finishedAt'] or 0,
    )
    for t in finished[:max(0, len(finished) - _MAX_FINISHED_TASKS)]:
        _tasks.pop(t['taskId'], None)


def _worker() -> None:
    while True:
        task_id, job = _queue.get()
        try:
            job(task_id)
        except Exception:
            # job 自身应兜底所有异常；这里只保证 worker 永不退出
            pass
        finally:
            with _lock:
                _prune_locked(time.time())
            _queue.task_done()


def _ensure_worker() -> None:
    global _worker_started
    if _worker_started:
        return
    with _lock:
        if not _worker_started:
            threading.Thread(
                target=_worker, daemon=True, name='publish-executor',
            ).start()
            _worker_started = True


def submit(job) -> str:
    """入队一个发布 job，立即返回 task_id。

    job 需接受 task_id 参数：``job(task_id)`` 在工作线程里被调用。
    """
    task_id = str(uuid.uuid4())
    with _lock:
        _tasks[task_id] = {
            'taskId': task_id,
            'status': 'queued',
            'msg': '',
            'submittedAt': time.time(),
            'startedAt': None,
            'finishedAt': None,
        }
    _ensure_worker()
    _queue.put((task_id, job))
    return task_id


def mark_running(task_id: str) -> None:
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t['status'] = 'running'
            t['startedAt'] = time.time()


def mark_finished(task_id: str, status: str, msg: str = '') -> None:
    if status not in TERMINAL_STATUSES:
        raise ValueError(f"非法终态: {status}")
    with _lock:
        t = _tasks.get(task_id)
        if t:
            t['status'] = status
            t['msg'] = msg
            t['finishedAt'] = time.time()


def get(task_id: str):
    """返回任务状态 dict 的副本；不存在返回 None。"""
    with _lock:
        t = _tasks.get(task_id)
        return dict(t) if t else None
