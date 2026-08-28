"""
任务队列系统 - asyncio Queue + Worker 模式
支持并发控制、失败重试（指数退避）、进度追踪
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Optional

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl.registry import get_platform

logger = get_channel_logger("task_queue")

DB_PATH = BASE_DIR / "db" / "database.db"

# 任务间隔设置缓存（settings.batchTaskInterval，分钟）。worker 每次取任务前读取，
# 30s 缓存避免频繁开 DB；异常一律回退 0（= 连续发布，与旧行为一致）。
_interval_cache = {"value": 0.0, "fetched_at": 0.0}


def _get_interval_minutes() -> float:
    now = time.time()
    if now - _interval_cache["fetched_at"] < 30:
        return _interval_cache["value"]
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'batchTaskInterval'"
            ).fetchone()
        val = float(row[0]) if row and row[0] not in (None, "") else 0.0
    except Exception:
        val = 0.0
    val = max(0.0, val)
    _interval_cache["value"] = val
    _interval_cache["fetched_at"] = now
    return val


def _friendly_error(exc: Exception) -> str:
    """把原始异常转成用户可读的错误信息。

    用户手动关闭浏览器时，未被页面级守卫捕获的 await 会抛 Playwright 原文
    （如 "Target page, context or browser has been closed"），展示给用户很困惑，
    这里统一归一化为「浏览器/页面已被用户关闭」。
    """
    msg = str(exc)
    low = msg.lower()
    if (
        "target page, context or browser has been closed" in low
        or "browser has been closed" in low
        or "target closed" in low
        or "execution context was destroyed" in low
    ):
        return "浏览器/页面已被用户关闭，发布中止"
    return msg


class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


def aggregate_batch_status(*, succ: int, fail: int, in_flight: int, total: int) -> str:
    """根据 detail 状态聚合 batch 状态。

    优先级：
      1. total == 0            -> 'pending'    （无 detail，理论不该发生）
      2. in_flight > 0         -> 'running'    （仍有 queued/running detail 未结束）
      3. fail == 0             -> 'success'    （全部成功）
      4. succ == 0             -> 'failed'     （全部失败）
      5. 其余                  -> 'partial'    （混合成功+失败）
    """
    if total == 0:
        return 'pending'
    if in_flight > 0:
        return 'running'
    if fail == 0:
        return 'success'
    if succ == 0:
        return 'failed'
    return 'partial'


@dataclass
class PublishTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    batch_id: str = ''                       # 新增
    platform: str = ""
    platform_type: int = 0  # 1=小红书 2=视频号 3=抖音 4=快手 5=B站
    account_name: str = ""
    account_cookie_path: str = ""
    video_path: str = ""
    title: str = ""
    description: str = ""
    thumbnail_path: str = ""
    tags: list = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3
    error_message: str = ""
    publish_url: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    finished_at: Optional[str] = None

    # 新增：个性化配置字段
    video_landscape: dict | None = None
    video_portrait: dict | None = None
    cover_landscape: dict | None = None
    cover_portrait: dict | None = None
    video_format: str | None = None
    enable_timer: int | None = None
    schedule_time: str | None = None
    ai_content: str | None = None
    is_original: bool | None = None

    # 草稿批量发布溯源字段（Task 10 扩展）
    source: str = ''                # '' | 'draft' | 'normal'
    draft_id: int = 0
    account_id: int = 0
    detail_id: str = ''            # publish_details.id
    payload: dict = field(default_factory=dict)

    def to_dict(self):
        d = asdict(self)
        d['tags'] = json.dumps(self.tags, ensure_ascii=False)
        # payload 不持久化（仅 in-memory 透传），不写入 d
        return d

    @classmethod
    def from_row(cls, row_dict):
        """从数据库行构造"""
        tags = row_dict.get('tags', '[]')
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        return cls(
            id=row_dict['id'],
            batch_id=row_dict.get('batch_id', ''),
            platform=row_dict['platform'],
            platform_type=row_dict.get('platform_type', 0),
            account_name=row_dict['account_name'],
            account_cookie_path=row_dict.get('account_cookie_path', ''),
            video_path=row_dict['video_path'],
            title=row_dict['title'],
            description=row_dict.get('description', ''),
            thumbnail_path=row_dict.get('thumbnail_path', ''),
            tags=tags,
            status=row_dict['status'],
            retry_count=row_dict.get('retry_count', 0),
            max_retries=row_dict.get('max_retries', 3),
            error_message=row_dict.get('error_message', ''),
            publish_url=row_dict.get('publish_url', ''),
            created_at=row_dict['created_at'],
            started_at=row_dict.get('started_at'),
            finished_at=row_dict.get('finished_at'),
            source=row_dict.get('source', ''),
            draft_id=row_dict.get('draft_id', 0),
            account_id=row_dict.get('account_id', 0),
            detail_id=row_dict.get('detail_id', ''),
        )


def _build_account_configs(task: 'PublishTask') -> dict:
    """构造写入 publish_details.account_configs 的 dict。
    含全 per-platform form 字段，让历史卡片能完整还原发布时的内容。"""
    return {
        'title': task.title,
        'description': task.description,
        'tags': task.tags,
        'thumbnail_path': task.thumbnail_path,
        'platform_type': task.platform_type,
        'videoLandscape': task.video_landscape,
        'videoPortrait': task.video_portrait,
        'coverLandscape': task.cover_landscape,
        'coverPortrait': task.cover_portrait,
        'videoFormat': task.video_format,
        'enableTimer': task.enable_timer,
        'scheduleTime': task.schedule_time,
        'aiContent': task.ai_content,
        'isOriginal': task.is_original,
    }


class TaskQueue:
    """基于 asyncio 的任务队列，在后台线程中运行"""

    def __init__(self, max_concurrent: int = 2):
        self.queue: asyncio.Queue = None
        self.running: dict[str, PublishTask] = {}
        self.completed: list[PublishTask] = []
        self.max_concurrent = max_concurrent
        self._workers: list[asyncio.Task] = []
        self._loop: asyncio.AbstractEventLoop = None
        self._thread: threading.Thread = None
        self._started = False
        self._status_callbacks = []  # 状态变更回调
        self._interval_gate: asyncio.Lock | None = None  # 间隔模式的串行闸门
        # 取消支持：running 的 asyncio task 句柄 / 队列中待取消的 id / 已取消集合
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._queued_ids: set[str] = set()
        self._cancelled_ids: set[str] = set()
        self._cancel_lock = threading.Lock()

    def start(self):
        """在后台线程中启动事件循环"""
        if self._started:
            return
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._started = True
        logger.info(f"[TaskQueue] 启动，并发数={self.max_concurrent}")

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self.queue = asyncio.Queue()
        self._interval_gate = asyncio.Lock()
        for i in range(self.max_concurrent):
            self._loop.create_task(self._worker(f"worker-{i}"))
        self._loop.run_forever()

    async def _worker(self, name: str):
        while True:
            task = await self.queue.get()
            self._queued_ids.discard(task.id)
            # 任务间隔（settings.batchTaskInterval，分钟）：>0 时串行 + 完成后等待
            interval_min = _get_interval_minutes()
            gated = interval_min > 0
            if gated and self._interval_gate:
                await self._interval_gate.acquire()

            # 用户取消：出队前被标记取消 → 直接落 cancelled（不执行）
            with self._cancel_lock:
                was_cancelled = task.id in self._cancelled_ids
                if was_cancelled:
                    self._cancelled_ids.discard(task.id)
            if was_cancelled:
                task.status = TaskStatus.CANCELLED
                task.error_message = "用户取消发布"
                task.finished_at = datetime.now().isoformat()
                self.completed.append(task)
                self._update_db(task)
                self._notify_status(task)
                if gated and self._interval_gate:
                    self._interval_gate.release()
                self.queue.task_done()
                continue

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now().isoformat()
            self.running[task.id] = task
            self._running_tasks[task.id] = asyncio.current_task()
            self._update_db(task)
            self._notify_status(task)

            try:
                await self._execute(task)
                task.status = TaskStatus.SUCCESS
            except asyncio.CancelledError:
                task.status = TaskStatus.CANCELLED
                task.error_message = "用户取消发布"
            except Exception as e:
                # 重试逻辑已禁用 — 长耗时任务(如视频上传)失败立即标记 FAILED,
                # 避免误触发「同一任务再次开浏览器重新上传」
                task.status = TaskStatus.FAILED
                task.error_message = _friendly_error(e)

            finally:
                task.finished_at = datetime.now().isoformat()
                if task.id in self.running:
                    del self.running[task.id]
                self._running_tasks.pop(task.id, None)
                self.completed.append(task)
                self._update_db(task)
                self._notify_status(task)
                if gated and self._interval_gate:
                    try:
                        await asyncio.sleep(interval_min * 60)
                    finally:
                        self._interval_gate.release()
                self.queue.task_done()

    async def _execute(self, task: PublishTask):
        """调用上游 uploader 执行上传。

        新逻辑：当 task.payload 非空时，调 platform.publish_video(**payload)（splat）。
        旧逻辑（task.payload 为空时）：保留原 myUtils.postVideo 模块函数调用（向后兼容）。
        """
        # 新逻辑：payload 透传到 platform.publish_video
        if task.payload:
            platform = get_platform(task.platform_type)
            if not platform:
                raise ValueError(f"不支持的平台类型: {task.platform_type}")
            publish_fn = platform.publish_video
            if asyncio.iscoroutinefunction(publish_fn):
                return await publish_fn(**task.payload)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, lambda: publish_fn(**task.payload)
            )

        # 旧逻辑：保留原代码不动
        from myUtils.postVideo import (
            post_video_DouYin, post_video_ks,
            post_video_tencent, post_video_xhs,
            post_video_bilibili
        )

        file_list = [task.video_path]
        account_list = [task.account_cookie_path]
        tags = task.tags
        title = task.title
        thumbnail_path = task.thumbnail_path
        desc = task.description

        # 在 executor 中运行同步的上传函数
        loop = asyncio.get_event_loop()
        match task.platform_type:
            case 1:
                await loop.run_in_executor(
                    None, lambda: post_video_xhs(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        thumbnail_path=thumbnail_path, desc=desc
                    )
                )
            case 2:
                await loop.run_in_executor(
                    None, lambda: post_video_tencent(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0, False,
                        thumbnail_path=thumbnail_path, desc=desc
                    )
                )
            case 3:
                await loop.run_in_executor(
                    None, lambda: post_video_DouYin(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        thumbnail_landscape_path='', thumbnail_portrait_path=thumbnail_path,
                        productLink='', productTitle='', desc=desc
                    )
                )
            case 4:
                await loop.run_in_executor(
                    None, lambda: post_video_ks(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        thumbnail_path=thumbnail_path, desc=desc
                    )
                )
            case 5:
                await loop.run_in_executor(
                    None, lambda: post_video_bilibili(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        desc=desc
                    )
                )
            case _:
                raise ValueError(f"不支持的平台类型: {task.platform_type}")

    def add_task(self, task: PublishTask):
        """线程安全地添加任务到队列"""
        if not self._started:
            self.start()
        task.status = TaskStatus.QUEUED
        self._insert_db(task)
        self._queued_ids.add(task.id)
        asyncio.run_coroutine_threadsafe(self.queue.put(task), self._loop)
        logger.info(f"[TaskQueue] 任务已入队: {task.id} ({task.platform}/{task.account_name})")

    def cancel_task(self, task_id: str) -> bool:
        """取消任务：支持 running / queued / cancelled 前的任务。

        - queued（还在队列里）：标记取消，worker 出队时直接落 cancelled；
        - running：cancel 对应 asyncio task → worker 捕获 CancelledError 落 cancelled；
          注意同步平台(如微博)在 executor 线程里跑，无法强杀线程，但任务状态会
          立即置 cancelled（线程残留工作结束后自然消亡）；
        - 已完成的任务不可取消，返回 False。
        """
        with self._cancel_lock:
            if task_id in self.running:
                self._cancelled_ids.add(task_id)
                at = self._running_tasks.get(task_id)
                if at is not None and not at.done():
                    self._loop.call_soon_threadsafe(at.cancel)
                return True
            if task_id in self._queued_ids or task_id in self._cancelled_ids:
                self._cancelled_ids.add(task_id)
                return True
        return False

    def retry_task(self, task_id: str) -> bool:
        """重试失败的任务"""
        for task in list(self.completed):
            if task.id == task_id and task.status == TaskStatus.FAILED:
                task.retry_count = 0
                task.error_message = ""
                task.status = TaskStatus.QUEUED
                self.completed.remove(task)
                asyncio.run_coroutine_threadsafe(self.queue.put(task), self._loop)
                self._update_db(task)
                return True
        return False

    def get_status(self) -> dict:
        """获取队列状态"""
        pending = self.queue.qsize() if self.queue else 0
        running_tasks = [
            {"id": t.id, "platform": t.platform, "account": t.account_name, "title": t.title}
            for t in self.running.values()
        ]
        return {
            "pending": pending,
            "running": len(self.running),
            "completed": len(self.completed),
            "running_tasks": running_tasks,
        }

    def on_status_change(self, callback):
        """注册状态变更回调"""
        self._status_callbacks.append(callback)

    def _notify_status(self, task: PublishTask):
        for cb in self._status_callbacks:
            try:
                cb(task)
            except Exception as e:
                logger.info(f"[TaskQueue] 回调错误: {e}")

    # ========== 数据库操作 ==========

    def _insert_db(self, task: PublishTask):
        """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                # 素材 dict → id（cover 可能是抽帧封面，不在 materials 表，id 仅为溯源）
                def _mat_id(m):
                    return m.get('id', '') if isinstance(m, dict) else ''
                video_mat_id = _mat_id(task.video_landscape) or _mat_id(task.video_portrait)
                cover_l_id = _mat_id(task.cover_landscape)
                cover_p_id = _mat_id(task.cover_portrait)
                # batch 插一次，多次同 batch_id 跳过
                # 草稿批量发布时填 source='draft' + draft_id 溯源到草稿
                conn.execute(
                    """INSERT OR IGNORE INTO publish_batches
                       (id, type, title, description, video_material_id,
                        landscape_cover_material_id, portrait_cover_material_id,
                        account_count, status, created_at, updated_at,
                        source, draft_id)
                       VALUES (?, 'video', ?, ?, ?, ?, ?, 0, 'pending', ?, ?,
                               ?, ?)""",
                    (task.batch_id or task.id, task.title, task.description,
                     video_mat_id, cover_l_id, cover_p_id,
                     task.created_at, task.created_at,
                     task.source or '', task.draft_id or 0)
                )
                # 同 batch 后续任务带上了素材 ID 而首任务没有时补写（INSERT OR IGNORE 跳过行）
                conn.execute(
                    """UPDATE publish_batches
                       SET video_material_id=?, landscape_cover_material_id=?, portrait_cover_material_id=?
                       WHERE id=? AND COALESCE(landscape_cover_material_id, '')=''
                         AND COALESCE(portrait_cover_material_id, '')=''""",
                    (video_mat_id, cover_l_id, cover_p_id, task.batch_id or task.id)
                )
                # account_configs：把 task 字段打包成 JSON
                cfg = _build_account_configs(task)
                conn.execute(
                    """INSERT INTO publish_details
                       (id, batch_id, account_id, account_name, platform, account_configs,
                        status, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (task.id, task.batch_id or task.id, task.account_id or None,
                     task.account_name, task.platform,
                     json.dumps(cfg, ensure_ascii=False), task.status, task.created_at)
                )
        except Exception as e:
            logger.info(f"[TaskQueue] 插入数据库失败: {e}")

    def _update_db(self, task: PublishTask):
        """更新 1 行 publish_details + 聚合 publish_batches 状态"""
        try:
            with sqlite3.connect(str(DB_PATH)) as conn:
                conn.execute(
                    """UPDATE publish_details
                       SET status=?, retry_count=?, error_message=?, publish_url=?,
                           started_at=?, finished_at=?
                       WHERE id=?""",
                    (task.status, task.retry_count, task.error_message, task.publish_url,
                     task.started_at, task.finished_at, task.id)
                )
                # 聚合
                row = conn.execute(
                    "SELECT batch_id FROM publish_details WHERE id=?", (task.id,)
                ).fetchone()
                if not row: return
                batch_id = row[0]
                counts = conn.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),
                              SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END),
                              SUM(CASE WHEN status IN ('running', 'queued') THEN 1 ELSE 0 END)
                       FROM publish_details WHERE batch_id=?""",
                    (batch_id,)
                ).fetchone()
                total, succ, fail, in_flight = counts[0], counts[1] or 0, counts[2] or 0, counts[3] or 0
                bs = aggregate_batch_status(succ=succ, fail=fail, in_flight=in_flight, total=total)
                now = datetime.now().isoformat()
                conn.execute(
                    """UPDATE publish_batches
                       SET status=?, success_count=?, failed_count=?, account_count=?,
                           finished_at=?, updated_at=?
                       WHERE id=?""",
                    (bs, succ, fail, total, task.finished_at or now, now, batch_id)
                )
        except Exception as e:
            logger.info(f"[TaskQueue] 更新数据库失败: {e}")


# 全局单例
# 并发数=1：严格串行执行（一个任务（=一个视频×一个账号）发布完才轮到下一个），
# 避免多浏览器并发发布触发平台风控；配合 settings.batchTaskInterval 还能在任务间加等待。
task_queue = TaskQueue(max_concurrent=1)


def get_task_queue() -> TaskQueue:
    return task_queue
