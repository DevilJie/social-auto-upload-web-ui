"""
图文发布 Blueprint
处理图片上传、发布、草稿管理等功能
"""

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, jsonify, request

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from storage import resolve_material_path

logger = get_channel_logger("image_publish")

image_publish_bp = Blueprint('image_publish', __name__, url_prefix='/api/image-publish')

DB_PATH = BASE_DIR / "db" / "database.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ========== 图片上传 ==========

# ========== 发布 ==========

@image_publish_bp.route('/publish', methods=['POST'])
def publish_images():
    """发布图文内容到各平台"""
    import asyncio
    from impl.registry import get_platform

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

        # 获取图片文件路径（从 materials 表读取 stored_path，再解析本地路径）
        from storage import get_storage
        storage = get_storage()
        image_files = []
        for img_id in image_ids:
            row = conn.execute(
                "SELECT stored_path FROM materials WHERE id = ?", (img_id,)
            ).fetchone()
            if row:
                local_path = storage.get_local_path(row['stored_path'])
                if local_path:
                    image_files.append(local_path)
                else:
                    image_files.append(row['stored_path'])
        conn.close()

        if not image_files:
            return jsonify({"code": 400, "msg": "未找到有效的图片文件"}), 400

        # 执行实际发布（取第一个账号配置）
        config = account_configs[0]
        platform_type = config.get('platform')
        if not platform_type:
            return jsonify({"code": 400, "msg": "缺少平台类型"}), 400

        # 平台类型映射（支持中文名称和英文key）
        platform_map = {
            'douyin': 3,
            '抖音': 3,
            'xiaohongshu': 1,
            '小红书': 1,
            'kuaishou': 4,
            '快手': 4,
        }
        platform_id = platform_map.get(platform_type)
        if not platform_id:
            return jsonify({"code": 400, "msg": f"不支持的平台: {platform_type}"}), 400

        platform = get_platform(platform_id)
        if not platform:
            return jsonify({"code": 400, "msg": "无法获取平台实例"}), 400

        # 获取账号cookie文件（直接使用前端传递的 filePath）
        cookie_file = config.get('filePath')
        if not cookie_file:
            return jsonify({"code": 400, "msg": "缺少账号cookie文件路径"}), 400

        # 获取 dry_run 参数（默认为 True，先核对数据）
        dry_run = config.get('dry_run', True)

        # 调试日志
        logger.info(f"发布参数: dry_run={dry_run}, cover_path={config.get('cover_path')}, "
                    f"music_name={config.get('music_name')}, hotspot={config.get('hotspot')}, "
                    f"hotspot_tags={config.get('hotspot_tags')}, "
                    f"aiContent={config.get('aiContent')}, isOriginal={config.get('isOriginal')}, "
                    f"tags={config.get('tags')}, "
                    f"mix_id={config.get('mix_id')}, tag_type={config.get('tag_type')}, "
                    f"tag_value={config.get('tag_value')}, mini_link={config.get('mini_link')}")

        # 调用平台的 publish_image 方法
        publish_fn = platform.publish_image
        if asyncio.iscoroutinefunction(publish_fn):
            result = asyncio.run(publish_fn(
                title=config.get('title', ''),
                files=image_files,
                tags=config.get('tags', []),
                account_file=[cookie_file],
                desc=config.get('description', ''),
                cover_path=resolve_material_path(config.get('cover_path', '')),
                mix_id=config.get('mix_id', ''),
                music_name=config.get('music_name', ''),
                hotspot=config.get('hotspot', ''),
                tag_type=config.get('tag_type', ''),
                tag_value=config.get('tag_value', ''),
                mini_link=config.get('mini_link', ''),
                enableTimer=bool(config.get('scheduleTime')),
                schedule_time_str=config.get('scheduleTime', ''),
                ai_content=config.get('aiContent', ''),
                is_original=config.get('isOriginal', False),
                activities=config.get('activities', []),
                author_declaration=config.get('aiContent', ''),
                music_id=config.get('music_id', ''),
                music_title=config.get('music_title', ''),
                dry_run=dry_run,
            ))
        else:
            result = publish_fn(
                title=config.get('title', ''),
                files=image_files,
                tags=config.get('tags', []),
                account_file=[cookie_file],
                desc=config.get('description', ''),
                cover_path=resolve_material_path(config.get('cover_path', '')),
                mix_id=config.get('mix_id', ''),
                music_name=config.get('music_name', ''),
                hotspot=config.get('hotspot', ''),
                tag_type=config.get('tag_type', ''),
                tag_value=config.get('tag_value', ''),
                mini_link=config.get('mini_link', ''),
                enableTimer=bool(config.get('scheduleTime')),
                schedule_time_str=config.get('scheduleTime', ''),
                ai_content=config.get('aiContent', ''),
                is_original=config.get('isOriginal', False),
                activities=config.get('activities', []),
                author_declaration=config.get('aiContent', ''),
                music_id=config.get('music_id', ''),
                music_title=config.get('music_title', ''),
                dry_run=dry_run,
            )

        if result:
            # 更新任务状态为成功
            conn = _get_db()
            conn.execute(
                "UPDATE image_publish_tasks SET status = 'success' WHERE id = ?",
                (task_id,)
            )
            conn.execute(
                "UPDATE image_publish_logs SET status = 'success' WHERE task_id = ?",
                (task_id,)
            )
            conn.commit()
            conn.close()
            return jsonify({"code": 200, "msg": "发布成功", "data": {"task_id": task_id}})
        else:
            # 更新任务状态为失败
            conn = _get_db()
            conn.execute(
                "UPDATE image_publish_tasks SET status = 'failed' WHERE id = ?",
                (task_id,)
            )
            conn.execute(
                "UPDATE image_publish_logs SET status = 'failed' WHERE task_id = ?",
                (task_id,)
            )
            conn.commit()
            conn.close()
            return jsonify({"code": 500, "msg": "发布失败"}), 500

    except Exception as e:
        logger.error(f"发布失败: {e}")
        return jsonify({"code": 500, "msg": f"发布失败: {str(e)}"}), 500


# ========== 草稿管理（已迁移到 /api/v2/drafts，保留兼容接口） ==========

@image_publish_bp.route('/drafts', methods=['GET'])
def get_drafts():
    """获取图文草稿列表（重定向到统一接口）"""
    import asyncio
    from ext_api import get_drafts as v2_get_drafts
    # 直接调用 v2 接口，传递 type=image 参数
    from flask import request as req
    # 修改请求参数
    req.args = req.args.copy()
    req.args['type'] = 'image'
    return v2_get_drafts()


@image_publish_bp.route('/drafts', methods=['POST'])
def save_draft():
    """保存图文草稿（重定向到统一接口）"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    draft_data = data.get('draft_data')
    if not draft_data:
        return jsonify({"code": 400, "msg": "草稿数据不能为空"}), 400

    # 从 commonConfig.images 提取 image_ids
    common_config = draft_data.get('commonConfig', {})
    images = common_config.get('images', [])
    image_ids = [img['id'] for img in images] if isinstance(images, list) else []

    draft_id = data.get('id')
    now = datetime.now().isoformat()

    try:
        conn = _get_db()
        if draft_id:
            # 更新现有草稿
            title = _extract_image_draft_title(draft_data)
            channels_summary = _extract_image_channels_summary(draft_data)
            cover_path = _extract_image_draft_cover(draft_data)
            if cover_path:
                changes = conn.execute(
                    """UPDATE drafts SET title=?, cover_path=?, draft_data=?, channels_summary=?, updated_at=? WHERE id=? AND type='image'""",
                    (title, cover_path, json.dumps(draft_data, ensure_ascii=False),
                     json.dumps(channels_summary, ensure_ascii=False), now, draft_id)
                ).rowcount
            else:
                # coverImage 为空时保留原 cover_path
                changes = conn.execute(
                    """UPDATE drafts SET title=?, draft_data=?, channels_summary=?, updated_at=? WHERE id=? AND type='image'""",
                    (title, json.dumps(draft_data, ensure_ascii=False),
                     json.dumps(channels_summary, ensure_ascii=False), now, draft_id)
                ).rowcount
            conn.commit()
            conn.close()
            if changes == 0:
                return jsonify({"code": 404, "msg": "草稿不存在"}), 404
        else:
            # 创建新草稿
            title = _extract_image_draft_title(draft_data)
            channels_summary = _extract_image_channels_summary(draft_data)
            cover_path = _extract_image_draft_cover(draft_data)
            cursor = conn.execute(
                """INSERT INTO drafts (type, title, cover_path, draft_data, channels_summary)
                   VALUES ('image', ?, ?, ?, ?)""",
                (title, cover_path, json.dumps(draft_data, ensure_ascii=False),
                 json.dumps(channels_summary, ensure_ascii=False))
            )
            conn.commit()
            draft_id = cursor.lastrowid
            conn.close()
        return jsonify({"code": 200, "msg": "草稿保存成功", "data": {"id": draft_id}})
    except Exception as e:
        logger.error(f"保存草稿失败: {e}")
        return jsonify({"code": 500, "msg": f"保存失败: {str(e)}"}), 500


def _extract_image_draft_title(draft_data):
    """从图文草稿数据中提取标题"""
    # 优先从 accountOverrides 中获取第一个非空标题（账号级配置）
    account_overrides = draft_data.get('accountOverrides', {})
    for account_id, override in account_overrides.items():
        title = override.get('title', '')
        if title and title.strip():
            return title.strip()[:100]

    # 然后从 platformConfigs 中获取（渠道级配置）
    pc = draft_data.get('platformConfigs', {})
    for key in ['douyin', 'xiaohongshu', 'kuaishou']:
        title = pc.get(key, {}).get('title', '')
        if title and title.strip():
            return title.strip()[:100]

    return '无标题'


def _extract_image_draft_cover(draft_data):
    """从图文草稿数据中提取封面路径"""
    common_config = draft_data.get('commonConfig', {})

    # 优先使用用户选择的封面
    cover = common_config.get('coverImage')
    if cover and isinstance(cover, dict):
        # 优先返回 stored_path（新存储系统）
        stored_path = cover.get('stored_path', '')
        if stored_path:
            return stored_path
        url = cover.get('url', '')
        if url:
            # 去掉 http://localhost:5409 前缀，保留相对路径
            if '://' in url:
                from urllib.parse import urlparse
                url = urlparse(url).path
            return url
        return cover.get('path', '') or cover.get('name', '') or ''

    # 兜底：第一张图片（优先 stored_path，兼容旧 path 字段）
    images = common_config.get('images', [])
    if images:
        img = images[0]
        if isinstance(img, dict):
            return img.get('stored_path', '') or img.get('path', '') or img.get('name', '') or ''
    return ''


def _extract_image_channels_summary(draft_data):
    """从图文草稿数据中提取渠道摘要"""
    publish_account_ids = draft_data.get('publishAccountIds', [])
    if not publish_account_ids:
        return []

    # 平台ID到名称和key的映射
    platform_id_to_name = {
        1: ('xiaohongshu', '小红书'),
        2: ('shipinhao', '视频号'),
        3: ('douyin', '抖音'),
        4: ('kuaishou', '快手'),
        5: ('bilibili', 'B站'),
        6: ('baijiahao', '百家号'),
    }

    try:
        conn = _get_db()
        placeholders = ','.join(['?'] * len(publish_account_ids))
        rows = conn.execute(
            f"SELECT id, type FROM user_info WHERE id IN ({placeholders})",
            publish_account_ids
        ).fetchall()
        conn.close()

        # 统计每个平台的账号数
        counts = {}  # platform_key -> {'name': ..., 'count': ...}
        for row in rows:
            ptype = row['type']
            key, name = platform_id_to_name.get(ptype, (str(ptype), f'平台{ptype}'))
            if key not in counts:
                counts[key] = {'name': name, 'count': 0}
            counts[key]['count'] += 1

        return [{"platform": key, "name": info['name'], "count": info['count']}
                for key, info in counts.items()]
    except Exception:
        return []


@image_publish_bp.route('/drafts/<draft_id>', methods=['DELETE'])
def delete_draft(draft_id):
    """删除图文草稿"""
    try:
        conn = _get_db()
        changes = conn.execute("DELETE FROM drafts WHERE id = ? AND type='image'", (draft_id,)).rowcount
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


# ========== 实际发布执行 ==========

@image_publish_bp.route('/execute-publish', methods=['POST'])
def execute_publish():
    """执行图文发布任务 - 调用平台API"""
    import asyncio
    from impl.registry import get_platform

    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    platform_type = data.get('platform_type')
    if not platform_type:
        return jsonify({"code": 400, "msg": "缺少平台类型"}), 400

    platform = get_platform(platform_type)
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    try:
        # 准备图片文件路径列表
        image_ids = data.get('image_ids', [])
        if not image_ids:
            return jsonify({"code": 400, "msg": "请选择至少一张图片"}), 400

        # 从数据库获取图片文件路径（从 materials 表读取 stored_path，再解析本地路径）
        from storage import get_storage
        storage = get_storage()
        conn = _get_db()
        image_files = []
        for img_id in image_ids:
            row = conn.execute(
                "SELECT stored_path FROM materials WHERE id = ?", (img_id,)
            ).fetchone()
            if row:
                local_path = storage.get_local_path(row['stored_path'])
                if local_path:
                    image_files.append(local_path)
                else:
                    image_files.append(row['stored_path'])
        conn.close()

        if not image_files:
            return jsonify({"code": 400, "msg": "未找到有效的图片文件"}), 400

        # 调用平台的 publish_image 方法
        publish_fn = platform.publish_image
        if asyncio.iscoroutinefunction(publish_fn):
            result = asyncio.run(publish_fn(
                title=data.get('title', ''),
                files=image_files,
                tags=data.get('tags', []),
                account_file=data.get('account_file', []),
                desc=data.get('desc', ''),
                cover_path=resolve_material_path(data.get('cover_path', '')),
                mix_id=data.get('mix_id', ''),
                music_name=data.get('music_name', ''),
                hotspot=data.get('hotspot', ''),
                location=data.get('location', ''),
                enableTimer=data.get('enableTimer', False),
                schedule_time_str=data.get('schedule_time_str', ''),
                ai_content=data.get('ai_content', ''),
                activities=data.get('activities', []),
                author_declaration=data.get('author_declaration', ''),
                music_id=data.get('music_id', ''),
                music_title=data.get('music_title', ''),
                dry_run=data.get('dry_run', True),
            ))
        else:
            result = publish_fn(
                title=data.get('title', ''),
                files=image_files,
                tags=data.get('tags', []),
                account_file=data.get('account_file', []),
                desc=data.get('desc', ''),
                cover_path=resolve_material_path(data.get('cover_path', '')),
                mix_id=data.get('mix_id', ''),
                music_name=data.get('music_name', ''),
                hotspot=data.get('hotspot', ''),
                location=data.get('location', ''),
                enableTimer=data.get('enableTimer', False),
                schedule_time_str=data.get('schedule_time_str', ''),
                ai_content=data.get('ai_content', ''),
                activities=data.get('activities', []),
                author_declaration=data.get('author_declaration', ''),
                music_id=data.get('music_id', ''),
                music_title=data.get('music_title', ''),
                dry_run=data.get('dry_run', True),
            )

        if result:
            return jsonify({"code": 200, "msg": "发布任务已执行", "data": None})
        else:
            return jsonify({"code": 500, "msg": "发布失败"}), 500

    except Exception as e:
        logger.error(f"执行发布失败: {e}")
        return jsonify({"code": 500, "msg": f"发布失败: {str(e)}"}), 500
