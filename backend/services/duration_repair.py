"""视频时长补全服务。

解决历史存量数据中视频素材 ``duration`` 为 0 的问题：

- 正常链路：上传时 ``_async_probe_duration`` 后台写库；
  素材库选中时前端同步调 ``/probe`` 补全。
- 缺口：草稿/历史恢复走的是 DB 直读，绕过了「选中 → probe」，
  于是 ``duration=0`` 的存量数据一路漏到发布提交，
  导致 ``PublishCenter`` 的时长校验被跳过。

本模块提供两个能力：

1. :func:`repair_zero_durations` — 启动时在后台线程批量扫描
   ``materials`` 表中 ``duration <= 0`` 的视频，逐条识别并写库，
   全程打印进度日志。
2. :func:`ensure_duration_or_probe` — 发布提交入口的同步兜底：
   单条视频 ``duration <= 0`` 时即时识别补全。

本地存储与 S3 存储统一处理：S3 文件经 ``resolve_material_path``
自动下载到临时文件后再用 ffprobe/ffmpeg 识别。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from util._logger import get_channel_logger

from services.ffmpeg_service import get_video_duration_safe

# 使用项目统一的日志体系（标准库 logging，按 channel 分文件），
# 日志会写入 data/logs/{日期}/backend.log。
# 不要用 loguru，它默认只输出到 stderr，不会进项目的日志文件。
logger = get_channel_logger("backend")


# ---------------------------------------------------------------------------
# 并发控制
# ---------------------------------------------------------------------------
#
# 启动后台批量补全、上传时的 _async_probe_duration、提交时的同步兜底
# 三者可能并发识别「同一条」素材。用全局锁集合记录「正在处理」的
# material_id，避免重复 probe（probe 要下载 S3 文件/起子进程，开销不小）。
#
_inflight_lock = threading.Lock()
_inflight_ids: set[str] = set()


def _acquire(material_id: str) -> bool:
    """尝试把 material_id 标记为「正在识别」。成功返回 True。"""
    with _inflight_lock:
        if material_id in _inflight_ids:
            return False
        _inflight_ids.add(material_id)
        return True


def _release(material_id: str) -> None:
    with _inflight_lock:
        _inflight_ids.discard(material_id)


# ---------------------------------------------------------------------------
# 单条识别（上传 / 启动 / 提交兜底共用）
# ---------------------------------------------------------------------------

def _probe_one(conn, material_id: str, stored_path: str) -> float:
    """识别单条视频时长并写库，返回识别到的秒数（失败返回 0.0）。

    需要调用方先 :func:`_acquire` 拿到锁，结束后 :func:`_release`。
    """
    from storage import resolve_material_path

    local = resolve_material_path(stored_path)
    if not local or not Path(local).is_file():
        logger.warning(
            "[DurationRepair] 文件不存在，跳过 material_id=%s path=%s",
            material_id, stored_path,
        )
        return 0.0

    duration = get_video_duration_safe(local)
    if duration > 0:
        conn.execute(
            "UPDATE materials SET duration = ? WHERE id = ?",
            (duration, material_id),
        )
        conn.commit()
    return duration


# ---------------------------------------------------------------------------
# 启动时批量补全
# ---------------------------------------------------------------------------

def repair_zero_durations() -> None:
    """扫描所有 ``duration <= 0`` 的视频素材，逐条识别补全。

    设计要点：
    - 在后台 daemon 线程中执行，不阻塞服务启动；
    - 启动前 sleep 一小段，让 Waitress 先把端口起来、DB 先处理常规请求；
    - 逐条打印进度（``1/N``），方便在启动日志里看到进展；
    - 识别失败的条目跳过，不抛异常、不影响主服务；
    - 与上传时 ``_async_probe_duration`` 通过 ``_inflight_ids`` 去重。
    """
    import time

    time.sleep(2.0)  # 让 Waitress 先起来，避免与启动期高频请求争抢 DB

    try:
        from conf import BASE_DIR
        db_path = BASE_DIR / "db" / "database.db"
        if not db_path.exists():
            logger.info("[DurationRepair] 数据库不存在，跳过时长补全")
            return

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        rows = conn.execute(
            "SELECT id, stored_path, original_filename "
            "FROM materials "
            "WHERE file_type = 'video' "
            "  AND (duration IS NULL OR duration <= 0)"
        ).fetchall()

        total = len(rows)
        if total == 0:
            logger.info("[DurationRepair] 无需补全，所有视频素材时长均已识别")
            conn.close()
            return

        logger.info(
            "[DurationRepair] 检测到 %d 个视频缺失时长，开始后台补全...",
            total,
        )

        ok, fail, skip = 0, 0, 0
        for idx, row in enumerate(rows, start=1):
            material_id = row["id"]
            name = row["original_filename"] or row["stored_path"]
            logger.info(
                "[DurationRepair] (%d/%d) 正在识别: %s",
                idx, total, name,
            )

            if not _acquire(material_id):
                # 正被上传/其他流程 probe，跳过
                skip += 1
                logger.debug(
                    "[DurationRepair] (%d/%d) 跳过（正在识别中）: %s",
                    idx, total, name,
                )
                continue

            try:
                duration = _probe_one(conn, material_id, row["stored_path"])
                if duration > 0:
                    ok += 1
                    logger.info(
                        "[DurationRepair] (%d/%d) 识别成功: %s → %.1fs",
                        idx, total, name, duration,
                    )
                else:
                    fail += 1
                    logger.warning(
                        "[DurationRepair] (%d/%d) 识别失败（时长仍为 0）: %s",
                        idx, total, name,
                    )
            except Exception as exc:
                fail += 1
                logger.exception(
                    "[DurationRepair] (%d/%d) 识别异常: %s → %s",
                    idx, total, name, exc,
                )
            finally:
                _release(material_id)

        logger.info(
            "[DurationRepair] 补全完成: 共 %d 个，成功 %d，失败 %d，跳过 %d",
            total, ok, fail, skip,
        )
        conn.close()

    except Exception as exc:
        # 后台任务绝不能把主进程拖崩
        logger.exception("[DurationRepair] 批量补全任务异常: %s", exc)


def start_repair_in_background() -> threading.Thread:
    """在 daemon 线程中启动时长补全，立即返回。"""
    thread = threading.Thread(
        target=repair_zero_durations,
        daemon=True,
        name="duration-repair",
    )
    thread.start()
    logger.info("[Startup] 时长补全后台任务已启动")
    return thread


# ---------------------------------------------------------------------------
# 提交发布时的同步兜底
# ---------------------------------------------------------------------------

def ensure_duration_or_probe(stored_path: str, current_duration: float) -> float:
    """发布提交入口的同步兜底：时长缺失则即时识别。

    用于 ``postVideo`` / ``postVideoBatch``：若传入的 ``current_duration``
    非法（<=0），尝试识别一次并写库。已是正常时长则原样返回。

    返回值保证：能识别就返回 >0，识别不到仍返回 0（调用方应将 0 视为
    「未识别」，不阻塞业务——与既有行为一致）。
    """
    if current_duration and current_duration > 0:
        return current_duration

    from conf import BASE_DIR
    db_path = BASE_DIR / "db" / "database.db"
    if not db_path.exists() or not stored_path:
        return 0.0

    # 通过 stored_path 反查 material_id（草稿/历史恢复场景带的是 stored_path）
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT id, duration FROM materials "
            "WHERE stored_path = ? AND file_type = 'video' "
            "LIMIT 1",
            (stored_path,),
        ).fetchone()
        if not row:
            return 0.0

        # 二次确认：可能已被后台任务补全
        db_duration = row["duration"]
        if db_duration and db_duration > 0:
            return db_duration

        material_id = row["id"]
        if not _acquire(material_id):
            # 已在处理中，此处不等待，返回 0 由调用方决定
            return 0.0

        try:
            return _probe_one(conn, material_id, stored_path)
        finally:
            _release(material_id)
    except Exception as exc:
        logger.warning("[DurationRepair] 提交兜底识别失败 path=%s: %s", stored_path, exc)
        return 0.0
    finally:
        conn.close()
