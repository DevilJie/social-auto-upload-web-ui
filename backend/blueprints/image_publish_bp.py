"""
图集发布 Blueprint
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

def _update_image_publish_detail(detail_id, status, error_message=""):
    """更新单条 publish_details 状态，并聚合到 publish_batches"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "UPDATE publish_details SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, datetime.now().isoformat(), error_message, detail_id)
            )
            row = conn.execute(
                "SELECT batch_id FROM publish_details WHERE id=?", (detail_id,)
            ).fetchone()
            if not row:
                return
            batch_id = row[0]
            counts = conn.execute(
                """SELECT COUNT(*),
                          SUM(CASE WHEN status='success' THEN 1 ELSE 0 END),
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
                   FROM publish_details WHERE batch_id=?""",
                (batch_id,)
            ).fetchone()
            total, succ, fail = counts[0], counts[1] or 0, counts[2] or 0
            if total == 0:
                bs = 'pending'
            elif fail == 0:
                bs = 'success'
            elif succ == 0:
                bs = 'failed'
            else:
                bs = 'partial'
            conn.execute(
                """UPDATE publish_batches
                   SET status=?, success_count=?, failed_count=?, account_count=?,
                       finished_at=?, updated_at=?
                   WHERE id=?""",
                (bs, succ, fail, total, datetime.now().isoformat(),
                 datetime.now().isoformat(), batch_id)
            )
    except Exception as e:
        logger.info(f"[image_publish] 更新失败: {e}")


@image_publish_bp.route('/publish', methods=['POST'])
def publish_images():
    """发布图集内容到各平台（单账号 + batchId 模式，前端循环调用）"""
    import asyncio
    from impl.registry import get_platform

    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    image_ids = data.get('image_ids', [])
    config = data.get('account_configs')
    batch_id = data.get('batchId') or str(uuid.uuid4())
    detail_id = str(uuid.uuid4())

    if not config or not isinstance(config, dict):
        return jsonify({"code": 400, "msg": "account_configs 必须是单个账号配置 dict"}), 400
    if not image_ids and not config.get('filePath'):
        return jsonify({"code": 400, "msg": "缺少 image_ids 或 filePath"}), 400

    now = datetime.now().isoformat()
    platform = config.get('platform', '未知')
    account_id = config.get('account_id')
    account_name = config.get('account_name') or Path(config.get('filePath', '')).stem
    title = config.get('title', '')
    description = config.get('description', '')

    # [DEBUG 2026-06-10] 详细日志：把整个请求体关键字段打印
    images_dbg = config.get('images') or []
    image_ids_dbg = [(img.get('id') if isinstance(img, dict) else None) for img in images_dbg]
    cover_id_dbg = (config.get('coverImage') or {}).get('id') if isinstance(config.get('coverImage'), dict) else None
    print(f"[image-publish REQUEST] batchId={batch_id} account={account_name} platform={platform} title={title} image_ids={image_ids[:5]}...({len(image_ids)} total) images_in_config={image_ids_dbg[:3]} coverImage_id={cover_id_dbg} creationDeclaration={config.get('creationDeclaration','')} aiContent={config.get('aiContent','')}", flush=True)

    # account_configs JSON：除了封面字段外的所有配置
    excluded = {'landscapeCoverMaterialId', 'portraitCoverMaterialId', 'filePath'}
    account_configs = {k: v for k, v in config.items() if k not in excluded}

    try:
        conn = _get_db()
        conn.execute(
            """INSERT OR IGNORE INTO publish_batches
               (id, type, title, description, image_material_ids,
                landscape_cover_material_id, portrait_cover_material_id,
                account_count, status, created_at, updated_at)
               VALUES (?, 'image', ?, ?, ?, ?, ?, 0, 'pending', ?, ?)""",
            (batch_id, title, description, json.dumps(image_ids, ensure_ascii=False),
             data.get('landscapeCoverMaterialId', ''),
             data.get('portraitCoverMaterialId', ''),
             now, now)
        )
        conn.execute(
            """INSERT INTO publish_details
               (id, batch_id, account_id, account_name, platform, account_configs,
                status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
            (detail_id, batch_id, account_id, account_name, platform,
             json.dumps(account_configs, ensure_ascii=False), now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({"code": 500, "msg": f"写入失败: {e}"}), 500

    # ---------- 实际发布执行（保留原有逻辑） ----------
    success = False
    err = ""
    try:
        # 获取图片文件路径（从 materials 表读取 stored_path，再解析本地路径）
        from storage import get_storage
        storage = get_storage()
        image_files = []
        conn = _get_db()
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

        # 即便 image_files 为空（如本测试），也要写完发布记录；只在有图片时才走平台调用
        platform_type = config.get('platform')
        cookie_file = config.get('filePath')

        if image_files and platform_type and cookie_file:
            # 平台类型映射（支持中文名称和英文key）
            platform_map = {
                'douyin': 3,
                '抖音': 3,
                'xiaohongshu': 1,
                '小红书': 1,
                'kuaishou': 4,
                '快手': 4,
                'weibo': 11, '微博': 11,   # 新增
                'alipay': 12, '支付宝': 12,  # 图集发布
            }
            platform_id = platform_map.get(platform_type)
            if not platform_id:
                raise ValueError(f"不支持的平台: {platform_type}")

            platform_obj = get_platform(platform_id)
            if not platform_obj:
                raise ValueError("无法获取平台实例")

            dry_run = config.get('dry_run', True)

            logger.info(f"发布参数: dry_run={dry_run}, cover_path={config.get('cover_path')}, "
                        f"music_name={config.get('music_name')}, hotspot={config.get('hotspot')}, "
                        f"hotspot_tags={config.get('hotspot_tags')}, "
                        f"aiContent={config.get('aiContent')}, isOriginal={config.get('isOriginal')}, "
                        f"tags={config.get('tags')}, "
                        f"mix_id={config.get('mix_id')}, tag_type={config.get('tag_type')}, "
                        f"tag_value={config.get('tag_value')}, mini_link={config.get('mini_link')}")

            # 调用平台的 publish_image 方法
            publish_fn = platform_obj.publish_image
            publish_kwargs = dict(
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
                author_statement=config.get('author_statement', '') or config.get('authorStatement', ''),
                music_id=config.get('music_id', ''),
                music_title=config.get('music_title', ''),
                dry_run=dry_run,
            )
            if asyncio.iscoroutinefunction(publish_fn):
                result = asyncio.run(publish_fn(**publish_kwargs))
            else:
                result = publish_fn(**publish_kwargs)
            success = bool(result)
        else:
            # 没有图片或缺配置：不调用平台（保留成功占位以便 batch 不卡 pending）
            err = "无图片或缺平台/cookie 配置，跳过实际发布"
            logger.info(f"[image_publish] {err}")
            success = True
    except Exception as e:
        logger.error(f"发布失败: {e}")
        err = str(e)
        success = False

    final_status = 'success' if success else 'failed'
    _update_image_publish_detail(detail_id, final_status, error_message=err)

    if success:
        return jsonify({"code": 200, "msg": "发布成功", "data": {"batch_id": batch_id, "detail_id": detail_id}})
    return jsonify({"code": 500, "msg": f"发布失败: {err}"}), 500


# ========== 草稿管理（已迁移到 /api/v2/drafts，保留兼容接口） ==========

@image_publish_bp.route('/drafts', methods=['GET'])
def get_drafts():
    """获取图集草稿列表（重定向到统一接口）"""
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
    """保存图集草稿（重定向到统一接口）"""
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
    """从图集草稿数据中提取标题"""
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
    """从图集草稿数据中提取封面路径"""
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
    """从图集草稿数据中提取渠道摘要"""
    publish_account_ids = draft_data.get('publishAccountIds', [])
    if not publish_account_ids:
        return []

    # 平台ID到名称和key的映射
    # 注意: platform key 必须与 frontend config/platforms.js 的 key 一致,
    # 否则草稿箱 getPlatformLogo() 匹配不到 logo。
    platform_id_to_name = {
        1: ('xiaohongshu', '小红书'),
        2: ('channels', '视频号'),
        3: ('douyin', '抖音'),
        4: ('kuaishou', '快手'),
        5: ('bilibili', 'B站'),
        6: ('baijiahao', '百家号'),
        11: ('weibo', '微博'),
        12: ('alipay', '支付宝'),   # 图集发布
        13: ('toutiao', '今日头条'),
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
    """删除图集草稿"""
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


# ========== 实际发布执行 ==========

@image_publish_bp.route('/execute-publish', methods=['POST'])
def execute_publish():
    """执行图集发布任务 - 调用平台API（单账号 + batchId 模式）"""
    import asyncio
    from impl.registry import get_platform

    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    platform_type = data.get('platform_type')
    if not platform_type:
        return jsonify({"code": 400, "msg": "缺少平台类型"}), 400

    image_ids = data.get('image_ids', [])
    if not image_ids:
        return jsonify({"code": 400, "msg": "请选择至少一张图片"}), 400

    batch_id = data.get('batchId') or str(uuid.uuid4())
    detail_id = str(uuid.uuid4())
    title = data.get('title', '')
    description = data.get('desc', '')
    account_file = data.get('account_file', [])
    account_id = data.get('account_id')
    account_name = data.get('account_name') or (
        Path(account_file[0]).stem if account_file else ''
    )

    # 平台名映射（与 /publish 一致，用于在 publish_details.platform 存可读名）
    platform_name_map = {1: '小红书', 2: '视频号', 3: '抖音', 4: '快手', 5: 'B站',
                         6: '百家号', 7: 'TikTok', 8: 'YouTube', 9: '腾讯视频', 10: '爱奇艺',
                         11: '微博', 12: '支付宝', 13: '今日头条', 14: '知乎', 15: 'CSDN'}
    platform_label = platform_name_map.get(int(platform_type), str(platform_type))

    now = datetime.now().isoformat()

    # account_configs JSON：除封面字段外的所有配置
    excluded = {'landscapeCoverMaterialId', 'portraitCoverMaterialId'}
    account_configs = {k: v for k, v in data.items() if k not in excluded}

    try:
        conn = _get_db()
        conn.execute(
            """INSERT OR IGNORE INTO publish_batches
               (id, type, title, description, image_material_ids,
                landscape_cover_material_id, portrait_cover_material_id,
                account_count, status, created_at, updated_at)
               VALUES (?, 'image', ?, ?, ?, ?, ?, 0, 'pending', ?, ?)""",
            (batch_id, title, description, json.dumps(image_ids, ensure_ascii=False),
             data.get('landscapeCoverMaterialId', ''),
             data.get('portraitCoverMaterialId', ''),
             now, now)
        )
        conn.execute(
            """INSERT INTO publish_details
               (id, batch_id, account_id, account_name, platform, account_configs,
                status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'running', ?)""",
            (detail_id, batch_id, account_id, account_name, platform_label,
             json.dumps(account_configs, ensure_ascii=False), now)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        return jsonify({"code": 500, "msg": f"写入失败: {e}"}), 500

    # ---------- 实际发布执行（保留原有逻辑） ----------
    success = False
    err = ""
    try:
        platform = get_platform(platform_type)
        if not platform:
            raise ValueError(f"不支持的平台类型: {platform_type}")

        # 从 materials 表读取 stored_path，再解析本地路径
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
            raise ValueError("未找到有效的图片文件")

        # 调用平台的 publish_image 方法
        publish_fn = platform.publish_image
        publish_kwargs = dict(
            title=title,
            files=image_files,
            tags=data.get('tags', []),
            account_file=account_file,
            desc=description,
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
        if asyncio.iscoroutinefunction(publish_fn):
            result = asyncio.run(publish_fn(**publish_kwargs))
        else:
            result = publish_fn(**publish_kwargs)
        success = bool(result)
    except Exception as e:
        logger.error(f"执行发布失败: {e}")
        err = str(e)
        success = False

    final_status = 'success' if success else 'failed'
    _update_image_publish_detail(detail_id, final_status, error_message=err)

    if success:
        return jsonify({"code": 200, "msg": "发布任务已执行", "data": {"batch_id": batch_id, "detail_id": detail_id}})
    return jsonify({"code": 500, "msg": f"发布失败: {err}"}), 500


@image_publish_bp.route('/drafts/batch-publish', methods=['POST'])
def batch_publish_image_drafts():
    """图集草稿批量发布：每个 draft 调一次 publish_images 走单账号链路。"""
    import json
    import sqlite3
    from flask import request, jsonify, current_app
    from services.draft_merge import validate_image_draft_for_publish

    data = request.get_json() or {}
    draft_ids = data.get('draft_ids') or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    from app import _get_db_path
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    placeholders = ','.join('?' * len(draft_ids))
    rows = conn.execute(
        f"SELECT id, image_ids, account_configs FROM image_drafts WHERE id IN ({placeholders})",
        draft_ids
    ).fetchall()
    conn.close()

    found_ids = {r[0] for r in rows}
    missing_ids = [i for i in draft_ids if i not in found_ids]
    if missing_ids:
        return jsonify({"code": 404, "msg": "图集草稿不存在", "missing_ids": missing_ids}), 404

    succeeded = []
    failed = []
    for r in rows:
        draft = {
            'id': r[0],
            'image_ids': json.loads(r[1] or '[]'),
            'account_configs': json.loads(r[2] or '{}'),
        }
        errs = validate_image_draft_for_publish(draft)
        if errs:
            failed.append({'draft_id': r[0], 'reason': '; '.join(errs)})
            continue

        # 调一次 publish_images：构造 data 让它走原来的单账号链路
        config = draft['account_configs']
        try:
            with current_app.test_request_context(
                '/api/image-publish/publish',
                method='POST',
                json={
                    'image_ids': draft['image_ids'],
                    'account_configs': config,
                    'landscapeCoverMaterialId': '',
                    'portraitCoverMaterialId': '',
                },
            ):
                resp = publish_images()
                # 兼容 2 种返回：(Response, status) tuple（mocked） 或 Response 对象（视图调用）
                if isinstance(resp, tuple):
                    body = resp[0].get_json() if hasattr(resp[0], 'get_json') else {}
                    status = resp[1]
                else:
                    body = resp.get_json() or {}
                    status = resp.status_code
                if status == 200 and body.get('code') == 200:
                    succeeded.append(r[0])
                else:
                    failed.append({'draft_id': r[0], 'reason': body.get('msg') or f'HTTP {status}'})
        except Exception as e:
            failed.append({'draft_id': r[0], 'reason': f'发布失败: {e}'})

    return jsonify({"code": 200, "succeeded": succeeded, "failed": failed}), 200
