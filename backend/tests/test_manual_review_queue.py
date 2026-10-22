"""Manual review must not become success before the platform confirms it."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_waiting_review_holds_next_job_and_false_result_fails():
    from ext_api.task_queue import TaskQueue, PublishTask, TaskStatus

    async def run():
        queue = TaskQueue(max_concurrent=1)
        queue.queue = asyncio.Queue()
        queue._update_db = lambda task: None
        queue._notify_status = lambda task: None
        queue._on_batch_maybe_finished = lambda task: None
        reviewing, release = asyncio.Event(), asyncio.Event()
        started = []

        async def execute(task):
            started.append(task.id)
            if task.id == 'review':
                reviewing.set()
                await release.wait()
                return False
            return True

        queue._execute = execute
        first = PublishTask(id='review', batch_interval_minutes=0)
        second = PublishTask(id='next', batch_interval_minutes=0)
        queue.queue.put_nowait(first)
        queue.queue.put_nowait(second)
        worker = asyncio.create_task(queue._worker('review-test'))
        try:
            await asyncio.wait_for(reviewing.wait(), timeout=2)
            assert first.status == TaskStatus.RUNNING
            assert started == ['review']
            release.set()
            await asyncio.wait_for(queue.queue.join(), timeout=2)
            assert first.status == TaskStatus.FAILED
            assert second.status == TaskStatus.SUCCESS
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(run())


def test_cancelled_review_is_not_recorded_as_success():
    from ext_api.task_queue import TaskQueue, PublishTask, TaskStatus

    async def run():
        queue = TaskQueue(max_concurrent=1)
        queue.queue = asyncio.Queue()
        queue._update_db = lambda task: None
        queue._notify_status = lambda task: None
        queue._on_batch_maybe_finished = lambda task: None

        async def execute(task):
            raise asyncio.CancelledError('user closed review page')

        queue._execute = execute
        task = PublishTask(batch_interval_minutes=0)
        queue.queue.put_nowait(task)
        worker = asyncio.create_task(queue._worker('cancel-test'))
        try:
            await asyncio.wait_for(queue.queue.join(), timeout=2)
            assert task.status == TaskStatus.CANCELLED
        finally:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

    asyncio.run(run())
