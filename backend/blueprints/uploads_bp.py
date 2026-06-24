"""
分片上传 Blueprint — 用于大文件（>100MB）上传 + 断点续传。

端点（全部在 /api/uploads 前缀下）:
  POST   /init         初始化上传会话
  POST   /chunk        接收单个分片
  POST   /merge        合并所有分片 + 写入 materials 表
  GET    /status       查询已上传分片（断点续传）
  DELETE /             取消上传 + 清理临时文件

设计要点：
  - 临时目录: data/upload_chunks/<upload_id>/<chunk_index>
  - 单片大小: 客户端可指定（1MB~100MB），默认 50MB
  - 单文件上限: 50GB
  - 断点续传: /init 幂等（upload_id 复用）/status 返回已上传分片列表
  - 并发: 客户端控制（默认 3），后端无锁（每个分片写到独立文件）
"""

import os
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify

from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("uploads")

uploads_bp = Blueprint("uploads", __name__, url_prefix="/api/uploads")

# 常量
CHUNK_DIR = BASE_DIR / "upload_chunks"
DEFAULT_CHUNK_SIZE = 50 * 1024 * 1024  # 50MB
MIN_CHUNK_SIZE = 1 * 1024 * 1024       # 1MB
MAX_CHUNK_SIZE = 100 * 1024 * 1024     # 100MB
MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50GB
MIN_FILE_SIZE = 1                       # 1 byte（兜底）


def _get_db():
    conn = sqlite3.connect(str(BASE_DIR / "db" / "database.db")
)
    conn.row_factory = sqlite3.Row
    return conn


def _guess_file_type(mime_type, filename=""):
    if mime_type and mime_type.startswith("video/"):
        return "video"
    if mime_type and mime_type.startswith("image/"):
        return "image"
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv",
                   ".m4v", ".wmv", ".mpeg", ".mpg"}:
            return "video"
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}:
            return "image"
    return "image"


def _session_dir(upload_id: str) -> Path:
    """单次上传的临时目录: data/upload_chunks/<upload_id>/"""
    return CHUNK_DIR / upload_id


def _chunk_path(upload_id: str, chunk_index: int) -> Path:
    return _session_dir(upload_id) / str(chunk_index)


def _count_uploaded_chunks(upload_id: str) -> int:
    """实盘扫描磁盘（比查 upload_chunks 表更可靠，能识别孤立文件）"""
    d = _session_dir(upload_id)
    if not d.is_dir():
        return 0
    return sum(1 for p in d.iterdir() if p.is_file() and p.name.isdigit())


def _list_uploaded_chunks(upload_id: str) -> list[int]:
    d = _session_dir(upload_id)
    if not d.is_dir():
        return []
    return sorted(int(p.name) for p in d.iterdir()
                  if p.is_file() and p.name.isdigit())


def _cleanup_session_files(upload_id: str):
    d = _session_dir(upload_id)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)


# ───────────────────────── /init ─────────────────────────

@uploads_bp.route("/init", methods=["POST"])
def init_upload():
    """初始化上传会话。

    Body: {filename, file_size, mime_type?, chunk_size?}
    Response: {upload_id, total_chunks, chunk_size, uploaded_chunks[]}
    """
    data = request.get_json(silent=True) or {}
    filename = (data.get("filename") or "").strip()
    file_size = data.get("file_size")
    mime_type = data.get("mime_type") or ""
    chunk_size = data.get("chunk_size") or DEFAULT_CHUNK_SIZE

    if not filename:
        return jsonify({"code": 400, "msg": "filename 不能为空"}), 400
    if not isinstance(file_size, int) or file_size < MIN_FILE_SIZE:
        return jsonify({"code": 400, "msg": "file_size 必须为正整数"}), 400
    if file_size > MAX_FILE_SIZE:
        return jsonify({
            "code": 400,
            "msg": f"文件超过最大限制 {MAX_FILE_SIZE // 1024**3} GB",
        }), 400
    if not isinstance(chunk_size, int) or chunk_size < MIN_CHUNK_SIZE or chunk_size > MAX_CHUNK_SIZE:
        return jsonify({
            "code": 400,
            "msg": f"chunk_size 必须在 {MIN_CHUNK_SIZE//1024**2}~{MAX_CHUNK_SIZE//1024**2}MB 之间",
        }), 400

    upload_id = str(uuid.uuid4())
    total_chunks = (file_size + chunk_size - 1) // chunk_size
    file_type = _guess_file_type(mime_type, filename)

    conn = _get_db()
    conn.execute(
        """INSERT INTO upload_sessions
           (upload_id, original_filename, file_size, mime_type, file_type,
            chunk_size, total_chunks, status, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'uploading', ?, ?)""",
        (upload_id, filename, file_size, mime_type, file_type,
         chunk_size, total_chunks, datetime.now().isoformat(),
         datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()

    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    _session_dir(upload_id).mkdir(parents=True, exist_ok=True)

    logger.info(f"[uploads] init {filename} size={file_size} chunks={total_chunks} "
                f"upload_id={upload_id}")

    return jsonify({
        "code": 200,
        "data": {
            "upload_id": upload_id,
            "total_chunks": total_chunks,
            "chunk_size": chunk_size,
            "uploaded_chunks": [],
        },
    })


# ───────────────────────── /chunk ─────────────────────────

@uploads_bp.route("/chunk", methods=["POST"])
def upload_chunk():
    """接收单个分片。

    Form fields: upload_id, chunk_index, file
    Response: {uploaded_chunks, total_chunks}
    """
    upload_id = (request.form.get("upload_id") or "").strip()
    chunk_index_str = request.form.get("chunk_index") or ""
    file = request.files.get("file")

    if not upload_id or not chunk_index_str or not file:
        return jsonify({"code": 400, "msg": "缺少 upload_id / chunk_index / file"}), 400

    try:
        chunk_index = int(chunk_index_str)
    except ValueError:
        return jsonify({"code": 400, "msg": "chunk_index 必须为整数"}), 400
    if chunk_index < 0:
        return jsonify({"code": 400, "msg": "chunk_index 必须 >= 0"}), 400

    conn = _get_db()
    session = conn.execute(
        "SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)
    ).fetchone()
    if not session:
        conn.close()
        return jsonify({"code": 404, "msg": "upload session 不存在"}), 404
    if session["status"] != "uploading":
        conn.close()
        return jsonify({"code": 400, "msg": f"session 状态为 {session['status']}，无法上传分片"}), 400
    if chunk_index >= session["total_chunks"]:
        conn.close()
        return jsonify({
            "code": 400,
            "msg": f"chunk_index {chunk_index} 超出 total_chunks {session['total_chunks']}",
        }), 400

    target_dir = _session_dir(upload_id)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = _chunk_path(upload_id, chunk_index)

    # 直接保存（Flask 的 file.save 内部就是分块读 + 写文件，O(1) 内存）
    file.save(str(target_path))

    actual_size = target_path.stat().st_size
    expected_size = session["chunk_size"]
    # 最后一片允许小于 chunk_size
    if chunk_index == session["total_chunks"] - 1:
        expected_size = session["file_size"] - chunk_index * session["chunk_size"]
    if actual_size != expected_size:
        target_path.unlink(missing_ok=True)
        conn.close()
        return jsonify({
            "code": 400,
            "msg": f"分片 {chunk_index} 大小不符: 期望 {expected_size}, 实际 {actual_size}",
        }), 400

    # 记录到 upload_chunks 表（断点续传用）
    conn.execute(
        """INSERT OR REPLACE INTO upload_chunks
           (upload_id, chunk_index, chunk_size) VALUES (?, ?, ?)""",
        (upload_id, chunk_index, actual_size),
    )
    uploaded = _count_uploaded_chunks(upload_id)
    conn.execute(
        "UPDATE upload_sessions SET uploaded_chunks=?, updated_at=? WHERE upload_id=?",
        (uploaded, datetime.now().isoformat(), upload_id),
    )
    conn.commit()
    conn.close()

    return jsonify({
        "code": 200,
        "data": {
            "uploaded_chunks": uploaded,
            "total_chunks": session["total_chunks"],
        },
    })


# ───────────────────────── /merge ─────────────────────────

@uploads_bp.route("/merge", methods=["POST"])
def merge_chunks():
    """合并所有分片 → 写入 materials 表 → 清理临时文件。

    Body: {upload_id}
    Response: material info（同 materials_bp.upload 成功响应）
    """
    data = request.get_json(silent=True) or {}
    upload_id = (data.get("upload_id") or "").strip()
    if not upload_id:
        return jsonify({"code": 400, "msg": "缺少 upload_id"}), 400

    conn = _get_db()
    session = conn.execute(
        "SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)
    ).fetchone()
    if not session:
        conn.close()
        return jsonify({"code": 404, "msg": "upload session 不存在"}), 404
    if session["status"] == "completed":
        conn.close()
        return jsonify({"code": 400, "msg": "已经合并过了"}), 400

    total_chunks = session["total_chunks"]
    uploaded = _list_uploaded_chunks(upload_id)
    if len(uploaded) != total_chunks:
        missing = [i for i in range(total_chunks) if i not in uploaded]
        conn.close()
        return jsonify({
            "code": 400,
            "msg": f"分片不完整，已上传 {len(uploaded)}/{total_chunks}，缺少 {missing[:10]}...",
        }), 400

    # 创建最终文件
    material_id = str(uuid.uuid4())
    ext = os.path.splitext(session["original_filename"])[1].lower()
    now = datetime.now()
    relative_path = f"materials/{now.strftime('%Y/%m/%d')}/{material_id}{ext}"
    final_abs_path = BASE_DIR / relative_path
    final_abs_path.parent.mkdir(parents=True, exist_ok=True)

    # 按序拼接（流式追加，每片读完即释放）
    try:
        with open(final_abs_path, "wb") as out:
            for idx in range(total_chunks):
                chunk_file = _chunk_path(upload_id, idx)
                with open(chunk_file, "rb") as f:
                    shutil.copyfileobj(f, out, length=1024 * 1024)  # 1MB buffer
    except Exception as e:
        final_abs_path.unlink(missing_ok=True)
        conn.execute(
            "UPDATE upload_sessions SET status='failed', error_message=?, updated_at=? WHERE upload_id=?",
            (str(e), datetime.now().isoformat(), upload_id),
        )
        conn.commit()
        conn.close()
        logger.error(f"[uploads] merge {upload_id} failed: {e}")
        return jsonify({"code": 500, "msg": f"合并失败: {e}"}), 500

    final_size = final_abs_path.stat().st_size
    if final_size != session["file_size"]:
        final_abs_path.unlink(missing_ok=True)
        conn.execute(
            "UPDATE upload_sessions SET status='failed', error_message=?, updated_at=? WHERE upload_id=?",
            (f"合并后大小 {final_size} 与预期 {session['file_size']} 不符",
             datetime.now().isoformat(), upload_id),
        )
        conn.commit()
        conn.close()
        return jsonify({"code": 400, "msg": "合并后文件大小不符"}), 400

    mime_type = session["mime_type"] or "application/octet-stream"
    file_type = session["file_type"] or "image"

    # 写 materials 表
    conn.execute(
        """INSERT INTO materials
           (id, original_filename, stored_path, file_type, mime_type,
            file_size, storage_type, thumbnail_path, upload_time)
           VALUES (?, ?, ?, ?, ?, ?, 'local', '', ?)""",
        (material_id, session["original_filename"], relative_path,
         file_type, mime_type, final_size, now.isoformat()),
    )
    conn.execute(
        "UPDATE upload_sessions SET status='completed', material_id=?, updated_at=? WHERE upload_id=?",
        (material_id, datetime.now().isoformat(), upload_id),
    )
    conn.commit()
    conn.close()

    # 清理临时分片
    _cleanup_session_files(upload_id)

    # 视频素材后台抽帧 + probe duration（与 materials_bp 一致）
    if file_type == "video":
        from blueprints.materials_bp import _async_extract_thumb, _async_probe_duration
        threading.Thread(target=_async_extract_thumb,
                         args=(material_id, relative_path), daemon=True).start()
        threading.Thread(target=_async_probe_duration,
                         args=(material_id, relative_path), daemon=True).start()

    # 异步识别素材宽高 + orientation（视频和图片都需要）
    from blueprints.materials_bp import _async_probe_dimensions
    threading.Thread(target=_async_probe_dimensions,
                     args=(material_id, relative_path, file_type), daemon=True).start()

    from storage import get_storage
    storage = get_storage()
    url = storage.get_url(relative_path)

    logger.info(f"[uploads] merge OK {session['original_filename']} → {material_id}")

    return jsonify({
        "code": 200,
        "msg": "上传成功",
        "data": {
            "id": material_id,
            "original_filename": session["original_filename"],
            "stored_path": relative_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": final_size,
            "url": url,
            "thumbnail_path": None,
        },
    })


# ───────────────────────── /status ─────────────────────────

@uploads_bp.route("/status", methods=["GET"])
def status():
    """查询已上传分片（断点续传用）。

    Query: ?upload_id=xxx
    Response: {uploaded_chunks[], total_chunks, status, file_size, ...}
    """
    upload_id = (request.args.get("upload_id") or "").strip()
    if not upload_id:
        return jsonify({"code": 400, "msg": "缺少 upload_id"}), 400

    conn = _get_db()
    session = conn.execute(
        "SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)
    ).fetchone()
    conn.close()

    if not session:
        return jsonify({"code": 404, "msg": "upload session 不存在"}), 404

    # 以磁盘实盘为准（即使表里有记录，文件丢了也算未上传）
    uploaded = _list_uploaded_chunks(upload_id)

    return jsonify({
        "code": 200,
        "data": {
            "upload_id": upload_id,
            "original_filename": session["original_filename"],
            "file_size": session["file_size"],
            "total_chunks": session["total_chunks"],
            "chunk_size": session["chunk_size"],
            "uploaded_chunks": uploaded,
            "status": session["status"],
            "material_id": session["material_id"],
            "error_message": session["error_message"],
        },
    })


# ───────────────────────── DELETE / ─────────────────────────

@uploads_bp.route("/", methods=["DELETE"])
def cancel_upload():
    """取消上传 + 清理临时文件 + DB 记录标记 cancelled。"""
    upload_id = (request.args.get("upload_id") or "").strip()
    if not upload_id:
        return jsonify({"code": 400, "msg": "缺少 upload_id"}), 400

    conn = _get_db()
    session = conn.execute(
        "SELECT * FROM upload_sessions WHERE upload_id = ?", (upload_id,)
    ).fetchone()
    if not session:
        conn.close()
        return jsonify({"code": 404, "msg": "upload session 不存在"}), 404
    if session["status"] == "completed":
        conn.close()
        return jsonify({"code": 400, "msg": "已合并完成，无法取消"}), 400

    conn.execute(
        "UPDATE upload_sessions SET status='cancelled', updated_at=? WHERE upload_id=?",
        (datetime.now().isoformat(), upload_id),
    )
    conn.commit()
    conn.close()

    _cleanup_session_files(upload_id)
    logger.info(f"[uploads] cancelled {upload_id} ({session['original_filename']})")

    return jsonify({"code": 200, "msg": "已取消"})
