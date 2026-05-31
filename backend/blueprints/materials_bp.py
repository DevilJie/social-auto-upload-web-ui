import os
import sqlite3
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


def _guess_file_type(mime_type):
    if mime_type and mime_type.startswith("video/"):
        return "video"
    return "image"


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
    file_type = _guess_file_type(mime_type)
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
        },
    })


@materials_bp.route("/list", methods=["GET"])
def list_files():
    """获取素材列表"""
    from storage import get_storage

    file_type = request.args.get("type", "all")
    conn = _get_db()
    if file_type in ("video", "image"):
        rows = conn.execute(
            "SELECT * FROM materials WHERE file_type = ? ORDER BY upload_time DESC",
            (file_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM materials ORDER BY upload_time DESC"
        ).fetchall()

    storage = get_storage()
    result = []
    for row in rows:
        item = dict(row)
        item["url"] = storage.get_url(item["stored_path"])
        result.append(item)
    conn.close()
    return jsonify({"code": 200, "data": result})


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
