import os
import sqlite3
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify

materials_bp = Blueprint("materials", __name__, url_prefix="/api/materials")


def _get_db():
    from conf import BASE_DIR
    DB_PATH = BASE_DIR / "db" / "database.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _guess_file_type(mime_type, filename=""):
    if mime_type and mime_type.startswith("video/"):
        return "video"
    if mime_type and mime_type.startswith("image/"):
        return "image"
    # 兜底：根据扩展名推断（浏览器可能没有给出 mime type）
    if filename:
        ext = os.path.splitext(filename)[1].lower()
        if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v", ".wmv", ".mpeg", ".mpg"}:
            return "video"
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"}:
            return "image"
    return "image"


def _generate_video_thumbnail(material_id: str, source_path: str) -> str | None:
    """使用 ffmpeg 抽取视频第一帧作为封面图，返回相对路径；失败返回 None。"""
    from conf import BASE_DIR

    abs_source = None
    from storage import resolve_material_path
    local = resolve_material_path(source_path)
    if local and os.path.isfile(local):
        abs_source = local
    elif os.path.isfile(source_path):
        abs_source = source_path
    if not abs_source:
        return None

    rel_thumb = f"materials/thumbs/{material_id}.jpg"
    abs_thumb = BASE_DIR / rel_thumb
    abs_thumb.parent.mkdir(parents=True, exist_ok=True)

    try:
        # 在第 1 秒抽帧；若视频不足 1 秒则取第 0 秒
        cmd = [
            "ffmpeg", "-y",
            "-ss", "1",
            "-i", abs_source,
            "-frames:v", "1",
            "-vf", "scale=320:-2",
            "-q:v", "4",
            str(abs_thumb),
        ]
        result = subprocess.run(
            cmd, capture_output=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0 and os.path.isfile(abs_thumb):
            return rel_thumb
        # 失败回退到第 0 秒
        cmd[cmd.index("1") + 1:cmd.index("1") + 2] = ["0"]
        result = subprocess.run(
            cmd, capture_output=True, timeout=15,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode == 0 and os.path.isfile(abs_thumb):
            return rel_thumb
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None
    return None


def _async_extract_thumb(material_id: str, source_path: str):
    """后台异步抽帧。"""
    try:
        rel = _generate_video_thumbnail(material_id, source_path)
        if not rel:
            return
        conn = _get_db()
        conn.execute(
            "UPDATE materials SET thumbnail_path = ? WHERE id = ?",
            (rel, material_id),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[materials] thumbnail extraction failed for {material_id}: {e}")


@materials_bp.route("/upload", methods=["POST"])
def upload():
    """统一文件上传"""
    from storage import get_storage

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"code": 400, "msg": "未找到文件"})

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    now = datetime.now()
    relative_path = f"materials/{now.strftime('%Y/%m/%d')}/{file_id}{ext}"

    storage = get_storage()
    file_data = file.read()
    storage.save(file_data, relative_path)

    mime_type = file.content_type or "application/octet-stream"
    file_type = _guess_file_type(mime_type, file.filename)
    file_size = len(file_data)

    conn = _get_db()
    conn.execute(
        """INSERT INTO materials
           (id, original_filename, stored_path, file_type, mime_type, file_size, storage_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (file_id, file.filename, relative_path, file_type, mime_type, file_size, storage.type),
    )
    conn.commit()
    conn.close()

    # 视频素材异步抽帧作为缩略图
    if file_type == "video":
        threading.Thread(
            target=_async_extract_thumb,
            args=(file_id, relative_path),
            daemon=True,
        ).start()

    url = storage.get_url(relative_path)

    return jsonify({
        "code": 200,
        "msg": "上传成功",
        "data": {
            "id": file_id,
            "original_filename": file.filename,
            "stored_path": relative_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": file_size,
            "url": url,
            "thumbnail_path": None,
        },
    })


@materials_bp.route("/list", methods=["GET"])
def list_files():
    """分页素材列表

    Query params:
      - type: all | video | image (默认 all)
      - keyword: 文件名模糊搜索
      - page: 页码（从 1 开始）
      - page_size: 每页数量（默认 24，上限 96）
    """
    from storage import get_storage

    file_type = request.args.get("type", "all")
    keyword = (request.args.get("keyword") or "").strip()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", 24))
    except ValueError:
        page_size = 24
    page_size = max(1, min(page_size, 96))

    where_clauses = []
    params = []
    if file_type in ("video", "image"):
        where_clauses.append("file_type = ?")
        params.append(file_type)
    if keyword:
        where_clauses.append("original_filename LIKE ?")
        params.append(f"%{keyword}%")
    where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    conn = _get_db()
    total = conn.execute(
        f"SELECT COUNT(*) AS n FROM materials{where_sql}", params
    ).fetchone()["n"]

    offset = (page - 1) * page_size
    rows = conn.execute(
        f"SELECT * FROM materials{where_sql} "
        f"ORDER BY upload_time DESC, id DESC LIMIT ? OFFSET ?",
        (*params, page_size, offset),
    ).fetchall()

    storage = get_storage()
    items = []
    for row in rows:
        item = dict(row)
        item["url"] = storage.get_url(item["stored_path"])
        item["thumbnail_url"] = (
            storage.get_url(item["thumbnail_path"]) if item.get("thumbnail_path") else None
        )
        items.append(item)
    conn.close()

    total_pages = (total + page_size - 1) // page_size if page_size else 1

    return jsonify({
        "code": 200,
        "data": {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        },
    })


@materials_bp.route("/<material_id>", methods=["DELETE"])
def delete(material_id):
    """删除素材"""
    from storage import get_storage

    conn = _get_db()
    row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"code": 404, "msg": "素材不存在"})

    storage = get_storage()
    storage.delete(row["stored_path"])
    if row["thumbnail_path"]:
        storage.delete(row["thumbnail_path"])

    conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return jsonify({"code": 200, "msg": "删除成功"})


@materials_bp.route("/file/<path:relative_path>")
def serve_file(relative_path):
    """文件访问"""
    from storage import get_storage

    storage = get_storage()
    return storage.serve(relative_path)


@materials_bp.route("/test-s3", methods=["POST"])
def test_s3_connection():
    """测试 S3 连接"""
    data = request.get_json(force=True)
    try:
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=data.get("endpoint", ""),
            aws_access_key_id=data.get("access_key", ""),
            aws_secret_access_key=data.get("secret_key", ""),
            region_name=data.get("region", ""),
        )
        client.head_bucket(Bucket=data.get("bucket", ""))
        return jsonify({"code": 200, "msg": "连接成功"})
    except Exception as e:
        return jsonify({"code": 400, "msg": f"连接失败: {str(e)}"})
