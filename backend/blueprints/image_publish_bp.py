"""
图文发布 Blueprint
处理图片上传、发布、草稿管理等功能
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request, send_from_directory

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger

logger = get_channel_logger("image_publish")

image_publish_bp = Blueprint('image_publish', __name__, url_prefix='/api/image-publish')

DB_PATH = BASE_DIR / "db" / "database.db"
UPLOAD_DIR = BASE_DIR / "image-publish"

# 支持的图片格式
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif'}


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ========== 图片上传 ==========

@image_publish_bp.route('/upload', methods=['POST'])
def upload_image():
    """上传图片文件"""
    if 'file' not in request.files:
        return jsonify({"code": 400, "msg": "没有文件"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"code": 400, "msg": "文件名为空"}), 400

    if not _allowed_file(file.filename):
        return jsonify({"code": 400, "msg": f"不支持的图片格式，仅支持: {', '.join(ALLOWED_EXTENSIONS)}"}), 400

    try:
        image_id = str(uuid.uuid4())
        ext = Path(file.filename).suffix.lower()
        stored_filename = f"{image_id}{ext}"

        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filepath = UPLOAD_DIR / stored_filename
        file.save(str(filepath))

        filesize = round(os.path.getsize(filepath) / 1024, 2)  # KB

        conn = _get_db()
        conn.execute(
            """INSERT INTO image_records (id, original_filename, stored_filename, filesize)
               VALUES (?, ?, ?, ?)""",
            (image_id, file.filename, stored_filename, filesize)
        )
        conn.commit()
        conn.close()

        return jsonify({
            "code": 200,
            "msg": "上传成功",
            "data": {
                "id": image_id,
                "filename": file.filename,
                "stored_filename": stored_filename,
                "filesize": filesize,
                "url": f"/api/image-publish/files/{stored_filename}",
            }
        })
    except Exception as e:
        logger.error(f"上传图片失败: {e}")
        return jsonify({"code": 500, "msg": f"上传失败: {str(e)}"}), 500


# ========== 图片访问 ==========

@image_publish_bp.route('/files/<path:filepath>')
def serve_image(filepath):
    """提供已上传图片的访问"""
    if '..' in filepath or filepath.startswith('/'):
        return jsonify({"code": 400, "msg": "无效的文件路径"}), 400

    full_path = UPLOAD_DIR / filepath
    if not full_path.exists():
        return jsonify({"code": 404, "msg": "文件不存在"}), 404

    return send_from_directory(str(UPLOAD_DIR), filepath)


# ========== 图片删除 ==========

@image_publish_bp.route('/images/<image_id>', methods=['DELETE'])
def delete_image(image_id):
    """删除已上传的图片"""
    try:
        conn = _get_db()
        row = conn.execute(
            "SELECT stored_filename FROM image_records WHERE id = ?", (image_id,)
        ).fetchone()

        if not row:
            conn.close()
            return jsonify({"code": 404, "msg": "图片不存在"}), 404

        stored_filename = row['stored_filename']
        filepath = UPLOAD_DIR / stored_filename
        if filepath.exists():
            filepath.unlink()

        conn.execute("DELETE FROM image_records WHERE id = ?", (image_id,))
        conn.commit()
        conn.close()

        return jsonify({"code": 200, "msg": "删除成功"})
    except Exception as e:
        logger.error(f"删除图片失败: {e}")
        return jsonify({"code": 500, "msg": f"删除失败: {str(e)}"}), 500


# ========== 发布 ==========

@image_publish_bp.route('/publish', methods=['POST'])
def publish_images():
    """发布图文内容到各平台"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    image_ids = data.get('image_ids', [])
    account_configs = data.get('account_configs', [])

    if not image_ids:
        return jsonify({"code": 400, "msg": "请选择至少一张图片"}), 400
    if not account_configs:
        return jsonify({"code": 400, "msg": "请选择至少一个发布账号"}), 400

    try:
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = _get_db()
        conn.execute(
            """INSERT INTO image_publish_tasks (id, image_ids, account_configs, status, created_at, updated_at)
               VALUES (?, ?, ?, 'pending', ?, ?)""",
            (task_id, json.dumps(image_ids), json.dumps(account_configs, ensure_ascii=False), now, now)
        )

        # 为每个账号创建发布日志
        for config in account_configs:
            conn.execute(
                """INSERT INTO image_publish_logs (task_id, account_id, platform, status)
                   VALUES (?, ?, ?, 'pending')""",
                (task_id, config.get('account_id', 0), config.get('platform', ''))
            )

        conn.commit()
        conn.close()

        return jsonify({
            "code": 200,
            "msg": "发布任务已创建",
            "data": {"task_id": task_id}
        })
    except Exception as e:
        logger.error(f"创建发布任务失败: {e}")
        return jsonify({"code": 500, "msg": f"发布失败: {str(e)}"}), 500


# ========== 草稿管理 ==========

@image_publish_bp.route('/drafts', methods=['GET'])
def get_drafts():
    """获取图文草稿列表"""
    try:
        conn = _get_db()
        rows = conn.execute(
            "SELECT * FROM image_drafts ORDER BY updated_at DESC"
        ).fetchall()

        drafts = []
        for row in rows:
            d = dict(row)

            # 优先解析 draft_data（新格式）
            if d.get('draft_data'):
                try:
                    parsed = json.loads(d['draft_data'])
                    d['draft_data'] = parsed
                    # 从 draft_data 提取 image_ids
                    common_config = parsed.get('commonConfig', {})
                    images = common_config.get('images', [])
                    d['image_ids'] = [img['id'] for img in images] if isinstance(images, list) else []
                    d['commonConfig'] = common_config
                    d['account_configs'] = parsed.get('accountConfigs', {})
                    d['platformConfigs'] = parsed.get('platformConfigs', {})
                    d['accountOverrides'] = parsed.get('accountOverrides', {})
                    d['publishAccountIds'] = parsed.get('publishAccountIds', [])
                    d['expandedGroups'] = parsed.get('expandedGroups', [])
                    d['selectedPlatform'] = parsed.get('selectedPlatform', '')
                    d['selectedAccountId'] = parsed.get('selectedAccountId', None)
                except json.JSONDecodeError:
                    d['image_ids'] = []
            else:
                # 旧格式兼容
                try:
                    d['image_ids'] = json.loads(d.get('image_ids', '[]'))
                except json.JSONDecodeError:
                    d['image_ids'] = []
                try:
                    d['account_configs'] = json.loads(d.get('account_configs', '[]'))
                except json.JSONDecodeError:
                    d['account_configs'] = []

            # 获取图片 URL 列表
            image_urls = []
            for img_id in d['image_ids']:
                img_row = conn.execute(
                    "SELECT stored_filename FROM image_records WHERE id = ?", (img_id,)
                ).fetchone()
                if img_row:
                    image_urls.append(f"/api/image-publish/files/{img_row['stored_filename']}")
                else:
                    image_urls.append(None)
            d['image_urls'] = image_urls

            drafts.append(d)

        conn.close()
        return jsonify({"code": 200, "data": drafts})
    except Exception as e:
        logger.error(f"获取草稿列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@image_publish_bp.route('/drafts', methods=['POST'])
def save_draft():
    """保存图文草稿"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    # 新格式：完整状态存储（与视频发布一致）
    draft_data = data.get('draft_data')
    if draft_data:
        # 从 commonConfig.images 提取 image_ids
        common_config = draft_data.get('commonConfig', {})
        images = common_config.get('images', [])
        image_ids = [img['id'] for img in images] if isinstance(images, list) else []
        # 允许保存没有图片的草稿
        draft_id = data.get('id')
        now = datetime.now().isoformat()
        try:
            conn = _get_db()
            if draft_id:
                changes = conn.execute(
                    """UPDATE image_drafts SET draft_data=?, updated_at=? WHERE id=?""",
                    (json.dumps(draft_data, ensure_ascii=False), now, draft_id)
                ).rowcount
                conn.commit()
                conn.close()
                if changes == 0:
                    return jsonify({"code": 404, "msg": "草稿不存在"}), 404
            else:
                draft_id = str(uuid.uuid4())
                conn.execute(
                    """INSERT INTO image_drafts (id, draft_data, created_at, updated_at)
                       VALUES (?, ?, ?, ?)""",
                    (draft_id, json.dumps(draft_data, ensure_ascii=False), now, now)
                )
                conn.commit()
                conn.close()
            return jsonify({"code": 200, "msg": "草稿保存成功", "data": {"id": draft_id}})
        except Exception as e:
            logger.error(f"保存草稿失败: {e}")
            return jsonify({"code": 500, "msg": f"保存失败: {str(e)}"}), 500

    # 旧格式：兼容处理
    image_ids = data.get('image_ids', [])
    account_configs = data.get('account_configs', [])
    if not image_ids:
        return jsonify({"code": 400, "msg": "请选择至少一张图片"}), 400

    draft_id = data.get('id')
    now = datetime.now().isoformat()

    try:
        conn = _get_db()
        if draft_id:
            changes = conn.execute(
                """UPDATE image_drafts SET image_ids=?, account_configs=?, updated_at=? WHERE id=?""",
                (json.dumps(image_ids), json.dumps(account_configs, ensure_ascii=False), now, draft_id)
            ).rowcount
            conn.commit()
            conn.close()
            if changes == 0:
                return jsonify({"code": 404, "msg": "草稿不存在"}), 404
        else:
            draft_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO image_drafts (id, image_ids, account_configs, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (draft_id, json.dumps(image_ids), json.dumps(account_configs, ensure_ascii=False), now, now)
            )
            conn.commit()
            conn.close()
        return jsonify({"code": 200, "msg": "草稿保存成功", "data": {"id": draft_id}})
    except Exception as e:
        logger.error(f"保存草稿失败: {e}")
        return jsonify({"code": 500, "msg": f"保存失败: {str(e)}"}), 500


@image_publish_bp.route('/drafts/<draft_id>', methods=['DELETE'])
def delete_draft(draft_id):
    """删除图文草稿"""
    try:
        conn = _get_db()
        changes = conn.execute("DELETE FROM image_drafts WHERE id = ?", (draft_id,)).rowcount
        conn.commit()
        conn.close()

        if changes == 0:
            return jsonify({"code": 404, "msg": "草稿不存在"}), 404

        return jsonify({"code": 200, "msg": "草稿已删除"})
    except Exception as e:
        logger.error(f"删除草稿失败: {e}")
        return jsonify({"code": 500, "msg": f"删除失败: {str(e)}"}), 500


# ========== 发布历史 ==========

@image_publish_bp.route('/history', methods=['GET'])
def get_history():
    """获取图文发布历史"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    status_filter = request.args.get('status')
    offset = (page - 1) * page_size

    try:
        conn = _get_db()

        where = ""
        params = []
        if status_filter and status_filter != 'all':
            where = "WHERE status = ?"
            params.append(status_filter)

        total = conn.execute(
            f"SELECT COUNT(*) FROM image_publish_tasks {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT * FROM image_publish_tasks {where}
                ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            params + [page_size, offset]
        ).fetchall()

        tasks = []
        for row in rows:
            d = dict(row)
            try:
                d['image_ids'] = json.loads(d.get('image_ids', '[]'))
            except json.JSONDecodeError:
                d['image_ids'] = []
            try:
                d['account_configs'] = json.loads(d.get('account_configs', '[]'))
            except json.JSONDecodeError:
                d['account_configs'] = []

            # 查询该任务的发布日志
            log_rows = conn.execute(
                "SELECT * FROM image_publish_logs WHERE task_id = ?", (d['id'],)
            ).fetchall()
            d['logs'] = [dict(log) for log in log_rows]

            tasks.append(d)

        conn.close()
        return jsonify({
            "code": 200,
            "data": {
                "items": tasks,
                "total": total,
                "page": page,
                "pageSize": page_size,
            }
        })
    except Exception as e:
        logger.error(f"获取发布历史失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500
