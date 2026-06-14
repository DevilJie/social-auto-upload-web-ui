"""
扩展 API Blueprint — 阶段二
任务管理、发布历史、统计数据、SSE 实时推送
"""

import json
import sqlite3
import queue
import threading
import urllib.parse
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, request, jsonify, Response

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR

from .task_queue import get_task_queue, PublishTask, TaskStatus
from ._personalized import compute_personalized
from services.draft_merge import (
    merge_config, validate_draft_for_publish, build_platform_kwargs,
)

ext_api = Blueprint('ext_api', __name__, url_prefix='/api/v2')

DB_PATH = BASE_DIR / "db" / "database.db"

# SSE 订阅者
_sse_subscribers: list[queue.Queue] = []
_sse_lock = threading.Lock()


_tables_ensured = False


def _ensure_tables(conn):
    """确保 drafts 表存在（兼容旧版本数据库升级）。"""
    global _tables_ensured
    if _tables_ensured:
        return
    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT DEFAULT 'video',
            title TEXT DEFAULT '',
            cover_path TEXT DEFAULT '',
            draft_data TEXT DEFAULT '{}',
            channels_summary TEXT DEFAULT '[]',
            video_duration REAL DEFAULT 0,
            video_file_size INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        # 迁移：为旧表添加 type 列
        try:
            conn.execute('ALTER TABLE drafts ADD COLUMN type TEXT DEFAULT "video"')
        except sqlite3.OperationalError:
            pass  # 列已存在
        conn.commit()
    except Exception:
        pass
    _tables_ensured = True


def _db_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _ensure_tables(conn)
    return conn


def _to_beijing_time(utc_str):
    """将 SQLite UTC 时间字符串转换为北京时间 ISO 格式"""
    if not utc_str:
        return utc_str
    try:
        dt = datetime.strptime(str(utc_str), '%Y-%m-%d %H:%M:%S')
        dt = dt + timedelta(hours=8)
        return dt.strftime('%Y-%m-%dT%H:%M:%S+08:00')
    except (ValueError, TypeError):
        return utc_str


def _resolve_cover_url(material_id: str) -> str:
    """解析 material_id → /api/materials/file/{stored_path} URL。失败返回空串。

    stored_path 可能是绝对路径。用 urllib.parse.quote 编码可避免前导 `/` 触发双斜杠。
    """
    if not material_id:
        return ''
    try:
        conn = _db_conn()
        row = conn.execute(
            "SELECT stored_path FROM materials WHERE id = ?", (material_id,)
        ).fetchone()
        conn.close()
        if not row:
            return ''
        return f"/api/materials/file/{urllib.parse.quote(row['stored_path'], safe='')}"
    except Exception:
        return ''


def _resolve_cover_from_path(stored_path: str) -> str:
    """直接用 stored_path 构造 /api/materials/file/{path} URL。空串返回空。

    stored_path 可能是绝对路径（thumbnail_path 来自 _resolve_material_path，
    例如 /home/czy/workspace/.../data/materials/2026/06/13/uuid.jpg），
    也可能是相对路径（含 materials/ 前缀）。要构造 storage API 的 file 路由
    URL，relative_path 必须等于 materials 表的 stored_path 列。
    """
    if not stored_path:
        return ''
    # 绝对路径：剥掉 BASE_DIR（data 目录）的父前缀，保留 materials/ 之后的部分
    import re
    m = re.search(r'(?:^|/)data/(materials/.+)$', stored_path)
    if m:
        relative = m.group(1)
    elif stored_path.startswith('materials/'):
        relative = stored_path
    else:
        # 兜底：取 basename
        import os
        relative = os.path.basename(stored_path)
    return f"/api/materials/file/{urllib.parse.quote(relative, safe='')}"


# ========== 任务管理 ==========

@ext_api.route('/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表（读 publish_details，每行 = 1 个账号 × 1 个平台）"""
    status = request.args.get('status')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    offset = (page - 1) * page_size

    try:
        conn = _db_conn()
        where = ""
        params = []
        if status and status != 'all':
            where = "WHERE d.status = ?"
            params.append(status)

        total = conn.execute(
            f"SELECT COUNT(*) FROM publish_details d {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT d.*, b.title AS batch_title, b.type AS batch_type
                FROM publish_details d
                LEFT JOIN publish_batches b ON d.batch_id = b.id
                {where}
                ORDER BY d.created_at DESC LIMIT ? OFFSET ?""",
            params + [page_size, offset]
        ).fetchall()

        tasks = []
        for row in rows:
            d = dict(row)
            try:
                d['account_configs'] = json.loads(d.get('account_configs', '{}'))
            except json.JSONDecodeError:
                d['account_configs'] = {}
            tasks.append(d)

        conn.close()
        return jsonify({"code": 200, "data": {"list": tasks, "total": total, "page": page, "pageSize": page_size}})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/tasks', methods=['POST'])
def create_task():
    """创建发布任务"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    required = ['platformType', 'accountName', 'accountCookiePath', 'videoPath', 'title']
    for field in required:
        if not data.get(field):
            return jsonify({"code": 400, "msg": f"缺少必填字段: {field}"}), 400

    platform_map = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站"}
    platform_type = data['platformType']

    task = PublishTask(
        platform=platform_map.get(platform_type, "未知"),
        platform_type=platform_type,
        account_name=data['accountName'],
        account_cookie_path=data['accountCookiePath'],
        video_path=data['videoPath'],
        title=data['title'],
        description=data.get('description', ''),
        thumbnail_path=data.get('thumbnailPath', ''),
        tags=data.get('tags', []),
    )

    tq = get_task_queue()
    tq.add_task(task)

    return jsonify({"code": 200, "data": {"id": task.id, "status": task.status}})


@ext_api.route('/tasks/<detail_id>', methods=['GET'])
def get_task(detail_id):
    """获取单个任务（按 publish_details.id 查）"""
    try:
        conn = _db_conn()
        row = conn.execute(
            """SELECT d.*, b.title AS batch_title, b.type AS batch_type
               FROM publish_details d
               LEFT JOIN publish_batches b ON d.batch_id = b.id
               WHERE d.id = ?""",
            (detail_id,)
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"code": 404, "msg": "任务不存在"}), 404
        d = dict(row)
        try:
            d['account_configs'] = json.loads(d.get('account_configs', '{}'))
        except json.JSONDecodeError:
            d['account_configs'] = {}
        return jsonify({"code": 200, "data": d})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消任务"""
    tq = get_task_queue()
    if tq.cancel_task(task_id):
        return jsonify({"code": 200, "msg": "任务已取消"})
    return jsonify({"code": 400, "msg": "无法取消该任务"}), 400


@ext_api.route('/tasks/<task_id>/retry', methods=['POST'])
def retry_task(task_id):
    """重试失败任务"""
    tq = get_task_queue()
    if tq.retry_task(task_id):
        return jsonify({"code": 200, "msg": "任务已重新入队"})
    return jsonify({"code": 400, "msg": "无法重试该任务"}), 400


# ========== SSE 实时推送 ==========

@ext_api.route('/tasks/stream', methods=['GET'])
def task_stream():
    """SSE 实时推送任务状态变更"""
    q = queue.Queue(maxsize=10)

    with _sse_lock:
        _sse_subscribers.append(q)

    def on_status(task: PublishTask):
        try:
            q.put_nowait(json.dumps({
                "id": task.id,
                "status": task.status,
                "platform": task.platform,
                "account": task.account_name,
                "title": task.title,
                "error": task.error_message,
                "timestamp": datetime.now().isoformat(),
            }, ensure_ascii=False))
        except queue.Full:
            pass

    tq = get_task_queue()
    tq.on_status_change(on_status)

    def generate():
        try:
            while True:
                try:
                    data = q.get(timeout=30)
                    yield f"data: {data}\n\n"
                except queue.Empty:
                    yield ": heartbeat\n\n"
        except GeneratorExit:
            with _sse_lock:
                if q in _sse_subscribers:
                    _sse_subscribers.remove(q)

    response = Response(generate(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


# ========== 队列状态 ==========

@ext_api.route('/queue/status', methods=['GET'])
def queue_status():
    """获取任务队列状态"""
    tq = get_task_queue()
    return jsonify({"code": 200, "data": tq.get_status()})


# ========== 发布历史 ==========

def _normalize_detail_row(d):
    """把 publish_details 1 行 dict 规范化：JSON 反序列化 account_configs + 计算 duration"""
    try:
        d['account_configs'] = json.loads(d.get('account_configs', '{}'))
    except json.JSONDecodeError:
        d['account_configs'] = {}
    if d.get('started_at') and d.get('finished_at'):
        try:
            s = datetime.fromisoformat(d['started_at'])
            f = datetime.fromisoformat(d['finished_at'])
            d['duration'] = int((f - s).total_seconds())
        except (ValueError, TypeError):
            d['duration'] = None
    else:
        d['duration'] = None
    return d


def _serialize_batch_with_items(b, items):
    """把 publish_batches 1 行 + 关联的 publish_details 列表序列化成 API 响应

    列表端点 /history 和单批次端点 /history/<batch_id> 都通过此函数构造每条 batch 的数据。
    """
    # 给每个 detail 注入 personalized 派生字段（按 account_configs vs batch_row 公共值比较）
    for d_item in items:
        d_item['personalized'] = compute_personalized(
            d_item.get('account_configs') or {}, b
        )
    # 兜底：当 batch 列上的 material_id 都为空（封面是从视频抽帧得到的，没有 materials.id）时，
    # 从第一个 detail 的 account_configs 里取 coverLandscape / coverPortrait / thumbnail_path。
    fallback_cover_url = ''
    if items:
        first_cfg = items[0].get('account_configs') or {}
        fallback_cover_url = (
            _resolve_cover_from_path(first_cfg.get('coverLandscape', ''))
            or _resolve_cover_from_path(first_cfg.get('coverPortrait', ''))
            or _resolve_cover_from_path(first_cfg.get('thumbnail_path', ''))
        )
    return {
        'id': b['id'],
        'type': b['type'],
        'title': b.get('title', ''),
        'description': b.get('description', ''),
        'landscape_cover_material_id': b.get('landscape_cover_material_id', ''),
        'portrait_cover_material_id': b.get('portrait_cover_material_id', ''),
        'cover_url': _resolve_cover_url(b.get('landscape_cover_material_id', ''))
                    or _resolve_cover_url(b.get('portrait_cover_material_id', ''))
                    or fallback_cover_url,
        'account_count': b.get('account_count', 0),
        'success_count': b.get('success_count', 0),
        'failed_count': b.get('failed_count', 0),
        'status': b.get('status', 'pending'),
        'schedule_time': b.get('schedule_time', ''),
        'created_at': _to_beijing_time(b.get('created_at')),
        'started_at': _to_beijing_time(b.get('started_at')),
        'finished_at': _to_beijing_time(b.get('finished_at')),
        'items': items,
    }


@ext_api.route('/history', methods=['GET'])
def get_history():
    """获取发布历史（按批次分组），支持分页、平台/状态/类型过滤

    Query: type=video|image (可选), page=1, pageSize=20
    """
    type_ = request.args.get('type')
    status = request.args.get('status')
    platform = request.args.get('platform')  # 暂未使用，留扩展
    time_range = request.args.get('timeRange')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    offset = (page - 1) * page_size

    if time_range and not start_date:
        now = datetime.now()
        if time_range == 'today':
            start_date = now.strftime('%Y-%m-%d')
        elif time_range == '7days':
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        elif time_range == '30days':
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')

    conditions = []
    params = []
    if type_ in ('video', 'image'):
        conditions.append("type = ?")
        params.append(type_)
    if status:
        conditions.append("status = ?")
        params.append(status)
    if start_date:
        conditions.append("created_at >= ?")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= ?")
        params.append(end_date)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    try:
        conn = _db_conn()
        total = conn.execute(f"SELECT COUNT(*) FROM publish_batches {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM publish_batches {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        ).fetchall()
        batches = [dict(r) for r in rows]

        # 拿当前页所有 batch_id 的明细，一次 IN 查询
        if batches:
            batch_ids = [b['id'] for b in batches]
            placeholders = ','.join('?' * len(batch_ids))
            detail_rows = conn.execute(
                f"SELECT * FROM publish_details WHERE batch_id IN ({placeholders}) ORDER BY created_at ASC",
                batch_ids
            ).fetchall()
            details_by_batch: dict[str, list] = {}
            for d in detail_rows:
                dd = _normalize_detail_row(dict(d))
                details_by_batch.setdefault(dd['batch_id'], []).append(dd)
        else:
            details_by_batch = {}

        items = []
        for b in batches:
            batch_details = details_by_batch.get(b['id'], [])
            items.append(_serialize_batch_with_items(b, batch_details))

        conn.close()
        return jsonify({
            "code": 200,
            "data": {"items": items, "total": total, "page": page, "pageSize": page_size}
        })
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/history/<batch_id>', methods=['GET'])
def get_history_batch(batch_id):
    """获取单个发布批次详情（含所有明细）

    Response 200:
        {"code": 200, "data": <Batch with items>}
    Response 404:
        {"code": 404, "msg": "记录不存在或已被删除"}
    """
    try:
        conn = _db_conn()
        row = conn.execute(
            "SELECT * FROM publish_batches WHERE id = ?", (batch_id,)
        ).fetchone()
        if not row:
            conn.close()
            return jsonify({"code": 404, "msg": "记录不存在或已被删除"}), 404

        b = dict(row)
        detail_rows = conn.execute(
            "SELECT * FROM publish_details WHERE batch_id = ? ORDER BY created_at ASC",
            (batch_id,)
        ).fetchall()
        items = [_normalize_detail_row(dict(d)) for d in detail_rows]
        conn.close()

        data = _serialize_batch_with_items(b, items)
        return jsonify({"code": 200, "data": data})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ========== 统计数据 ==========

@ext_api.route('/stats', methods=['GET'])
def get_stats():
    """获取统计数据（成功率、发布量趋势等）"""
    try:
        conn = _db_conn()

        # 总体统计（读 publish_batches：每次"发布"= 1 个 batch）
        total = conn.execute("SELECT COUNT(*) FROM publish_batches").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM publish_batches WHERE status='success'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM publish_batches WHERE status='failed'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM publish_batches WHERE status IN ('pending','queued','running')").fetchone()[0]

        # 按平台统计（明细行才有 platform 字段，从 publish_details 聚合）
        platform_rows = conn.execute(
            "SELECT platform, COUNT(*) as count FROM publish_details GROUP BY platform"
        ).fetchall()
        by_platform = {row['platform']: row['count'] for row in platform_rows}

        # 最近7天趋势（以 batch 的 created_at 为口径）
        trend = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            next_date = (datetime.now() - timedelta(days=i-1)).strftime('%Y-%m-%d') if i > 0 else (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            count = conn.execute(
                "SELECT COUNT(*) FROM publish_batches WHERE created_at >= ? AND created_at < ?",
                (date, next_date)
            ).fetchone()[0]
            trend.append({"date": date, "count": count})

        # 本月发布数
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d')
        monthly_total = conn.execute(
            "SELECT COUNT(*) FROM publish_batches WHERE created_at >= ?", (month_start,)
        ).fetchone()[0]

        # 账号统计
        account_count = conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0]
        account_normal = conn.execute("SELECT COUNT(*) FROM user_info WHERE status=1").fetchone()[0]

        # 素材统计
        material_count = conn.execute("SELECT COUNT(*) FROM file_records").fetchone()[0]

        conn.close()

        success_rate = round(success / total * 100, 1) if total > 0 else 0

        return jsonify({"code": 200, "data": {
            # 发布历史页面直接使用的字段
            "total": total,
            "successRate": success_rate,
            "monthlyTotal": monthly_total,
            # 详细任务统计
            "tasks": {"total": total, "success": success, "failed": failed, "running": running, "successRate": success_rate},
            "byPlatform": by_platform,
            "trend": trend,
            "accounts": {"total": account_count, "normal": account_normal},
            "materials": {"total": material_count},
        }})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ========== 系统设置 ==========


@ext_api.route('/settings', methods=['GET'])
def get_settings():
    """获取系统设置"""
    try:
        conn = _db_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        settings = {row['key']: row['value'] for row in rows}
        conn.close()

        # 默认值
        defaults = {
            "publishInterval": "30",
            "maxConcurrent": "2",
            "browserMode": "headed",
            "heartbeatInterval": "3600",
            "autoFillTitle": "true",
            "autoSaveDraft": "true",
            "autoSaveInterval": "10",
            "portraitRatio": "9:16",
            "landscapeRatio": "16:9",
        }
        defaults.update(settings)
        # 转换布尔值类型
        for key in ['autoFillTitle', 'autoSaveDraft']:
            if key in defaults:
                defaults[key] = defaults[key] in ('true', 'True', '1', True)
        # 转换数值类型
        for key in ['publishInterval', 'maxConcurrent', 'heartbeatInterval', 'autoSaveInterval']:
            if key in defaults:
                try:
                    defaults[key] = int(defaults[key])
                except (ValueError, TypeError):
                    pass

        # storage / proxyUrl 从 SQLite 读取（JSON 类型字段需要解析）
        if 'storage' in defaults:
            try:
                defaults['storage'] = json.loads(defaults['storage'])
            except (json.JSONDecodeError, TypeError):
                defaults['storage'] = {'type': 'local', 's3': {}}
        else:
            defaults['storage'] = {'type': 'local', 's3': {}}
        if 'proxyUrl' not in defaults:
            defaults['proxyUrl'] = ''

        return jsonify({"code": 200, "data": defaults})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/settings', methods=['PUT'])
def update_settings():
    """更新系统设置"""
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空"}), 400

    try:
        need_reset_storage = 'storage' in data

        # 所有设置统一写入 SQLite（包括 storage / proxyUrl）
        conn = _db_conn()
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            else:
                value = str(value)
            conn.execute(
                """INSERT OR REPLACE INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, value, datetime.now().isoformat())
            )
        conn.commit()
        conn.close()

        if need_reset_storage:
            from storage import reset_storage
            reset_storage()

        return jsonify({"code": 200, "msg": "设置已更新"})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ========== 草稿箱 ==========

_PLATFORM_ID_MAP = {
    1: ('xiaohongshu', '小红书'),
    2: ('shipinhao', '视频号'),
    3: ('douyin', '抖音'),
    4: ('kuaishou', '快手'),
    5: ('bilibili', 'B站'),
    6: ('baijiahao', '百家号'),
}


def _extract_image_channels_from_draft(conn, draft_data):
    """从图文草稿的 draft_data 中提取渠道摘要（兜底）"""
    account_ids = draft_data.get('publishAccountIds', [])
    if not account_ids:
        return []
    try:
        placeholders = ','.join(['?'] * len(account_ids))
        rows = conn.execute(
            f"SELECT type FROM user_info WHERE id IN ({placeholders})", account_ids
        ).fetchall()
        counts = {}
        for row in rows:
            key, name = _PLATFORM_ID_MAP.get(row['type'], (str(row['type']), f'平台{row["type"]}'))
            if key not in counts:
                counts[key] = {'name': name, 'count': 0}
            counts[key]['count'] += 1
        return [{"platform": k, "name": v['name'], "count": v['count']} for k, v in counts.items()]
    except Exception:
        return []


@ext_api.route('/drafts', methods=['GET'])
def get_drafts():
    """获取草稿列表（支持 type 过滤：video/image）"""
    draft_type = request.args.get('type')
    try:
        conn = _db_conn()
        if draft_type:
            rows = conn.execute(
                "SELECT id, type, title, cover_path, channels_summary, video_duration, video_file_size, draft_data, created_at, updated_at FROM drafts WHERE type = ? ORDER BY updated_at DESC",
                (draft_type,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, type, title, cover_path, channels_summary, video_duration, video_file_size, draft_data, created_at, updated_at FROM drafts ORDER BY updated_at DESC"
            ).fetchall()
        drafts = []
        for row in rows:
            d = dict(row)
            try:
                d['channels_summary'] = json.loads(d.get('channels_summary', '[]'))
            except json.JSONDecodeError:
                d['channels_summary'] = []

            # 图文草稿：兜底修复 channels_summary
            if d.get('type') == 'image' and d.get('draft_data') and not d['channels_summary']:
                try:
                    dd = json.loads(d['draft_data'])
                    d['channels_summary'] = _extract_image_channels_from_draft(conn, dd)
                except (json.JSONDecodeError, KeyError):
                    pass
            d.pop('draft_data', None)  # 不在列表接口返回完整 draft_data

            d['created_at'] = _to_beijing_time(d.get('created_at'))
            d['updated_at'] = _to_beijing_time(d.get('updated_at'))
            drafts.append(d)
        conn.close()
        return jsonify({"code": 200, "data": drafts})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/drafts', methods=['POST'])
def create_draft():
    """创建草稿"""
    data = request.get_json()
    if not data or not data.get('draft_data'):
        return jsonify({"code": 400, "msg": "草稿数据不能为空"}), 400

    draft_data = data['draft_data']
    draft_type = data.get('type', 'video')  # 默认视频类型
    title = _extract_draft_title(draft_data)
    cover_path = _extract_draft_cover(draft_data)
    channels_summary = _extract_channels_summary(draft_data)
    video_duration = _extract_video_duration(draft_data)
    video_file_size = _extract_video_file_size(draft_data)

    try:
        conn = _db_conn()
        cursor = conn.execute(
            """INSERT INTO drafts (type, title, cover_path, draft_data, channels_summary, video_duration, video_file_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (draft_type, title, cover_path, json.dumps(draft_data, ensure_ascii=False),
             json.dumps(channels_summary, ensure_ascii=False),
             video_duration, video_file_size)
        )
        conn.commit()
        draft_id = cursor.lastrowid
        conn.close()
        return jsonify({"code": 200, "data": {"id": draft_id, "title": title}})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/drafts/<int:draft_id>', methods=['GET'])
def get_draft(draft_id):
    """获取草稿详情"""
    try:
        conn = _db_conn()
        row = conn.execute("SELECT * FROM drafts WHERE id = ?", (draft_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"code": 404, "msg": "草稿不存在"}), 404
        d = dict(row)
        try:
            d['channels_summary'] = json.loads(d.get('channels_summary', '[]'))
        except json.JSONDecodeError:
            d['channels_summary'] = []
        try:
            d['draft_data'] = json.loads(d.get('draft_data', '{}'))
        except json.JSONDecodeError:
            d['draft_data'] = {}
        d['created_at'] = _to_beijing_time(d.get('created_at'))
        d['updated_at'] = _to_beijing_time(d.get('updated_at'))
        return jsonify({"code": 200, "data": d})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/drafts/<int:draft_id>', methods=['PUT'])
def update_draft(draft_id):
    """更新草稿"""
    data = request.get_json()
    if not data or not data.get('draft_data'):
        return jsonify({"code": 400, "msg": "草稿数据不能为空"}), 400

    draft_data = data['draft_data']
    title = _extract_draft_title(draft_data)
    cover_path = _extract_draft_cover(draft_data)
    channels_summary = _extract_channels_summary(draft_data)
    video_duration = _extract_video_duration(draft_data)
    video_file_size = _extract_video_file_size(draft_data)

    try:
        conn = _db_conn()
        changes = conn.execute(
            """UPDATE drafts SET title=?, cover_path=?, draft_data=?, channels_summary=?,
               video_duration=?, video_file_size=?, updated_at=CURRENT_TIMESTAMP WHERE id=?""",
            (title, cover_path, json.dumps(draft_data, ensure_ascii=False),
             json.dumps(channels_summary, ensure_ascii=False),
             video_duration, video_file_size, draft_id)
        ).rowcount
        conn.commit()
        conn.close()
        if changes == 0:
            return jsonify({"code": 404, "msg": "草稿不存在"}), 404
        return jsonify({"code": 200, "data": {"id": draft_id, "title": title}})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@ext_api.route('/drafts/<int:draft_id>', methods=['DELETE'])
def delete_draft(draft_id):
    """删除草稿"""
    try:
        conn = _db_conn()
        changes = conn.execute("DELETE FROM drafts WHERE id = ?", (draft_id,)).rowcount
        conn.commit()
        conn.close()
        if changes == 0:
            return jsonify({"code": 404, "msg": "草稿不存在"}), 404
        return jsonify({"code": 200, "msg": "草稿已删除"})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ---------- Draft metadata extraction helpers ----------

def _extract_draft_title(draft_data):
    """从草稿数据中提取标题（第一个非空的平台标题）"""
    pc = draft_data.get('platformConfigs', {})
    for key in ['douyin', 'xiaohongshu', 'kuaishou', 'bilibili', 'channels',
                'baijiahao', 'tiktok', 'youtube', 'iqiyi', 'tencent_video']:
        title = pc.get(key, {}).get('title', '')
        if title and title.strip():
            return title.strip()[:100]
    return '无标题'


def _extract_draft_cover(draft_data):
    """从草稿数据中提取封面路径或URL"""
    cc = draft_data.get('commonConfig', {})
    for key in ['coverPortrait', 'coverLandscape']:
        cover = cc.get(key)
        if cover:
            if cover.get('path'):
                return cover['path']
            if cover.get('url'):
                return cover['url']
    return ''


def _extract_channels_summary(draft_data):
    """从草稿数据中提取渠道摘要（按平台分组计数）"""
    account_ids = draft_data.get('publishAccountIds', [])
    if not account_ids:
        return []

    platform_map = {
        'xiaohongshu': '小红书', 'channels': '视频号', 'douyin': '抖音',
        'kuaishou': '快手', 'bilibili': 'B站', 'baijiahao': '百家号',
        'tiktok': 'TikTok', 'youtube': 'YouTube', 'iqiyi': '爱奇艺',
        'tencent_video': '腾讯视频',
    }

    try:
        conn = _db_conn()
        placeholders = ','.join(['?'] * len(account_ids))
        rows = conn.execute(
            f"SELECT id, type FROM user_info WHERE id IN ({placeholders})",
            account_ids
        ).fetchall()
        conn.close()

        type_to_platform = {v: k for k, v in {
            'xiaohongshu': 1, 'channels': 2, 'douyin': 3,
            'kuaishou': 4, 'bilibili': 5,
            'baijiahao': 6, 'tiktok': 7, 'youtube': 8,
            'tencent_video': 9, 'iqiyi': 10,
        }.items()}

        platform_counts = {}
        for row in rows:
            pkey = type_to_platform.get(row['type'])
            if pkey:
                platform_counts[pkey] = platform_counts.get(pkey, 0) + 1

        return [{"platform": k, "name": platform_map.get(k, k), "count": v}
                for k, v in platform_counts.items()]
    except Exception:
        return []


def _extract_video_duration(draft_data):
    """从草稿数据中提取视频时长（暂存0，后续可从抽帧结果中获取）"""
    return 0


def _extract_video_file_size(draft_data):
    """从草稿数据中提取视频文件大小"""
    cc = draft_data.get('commonConfig', {})
    for key in ['videoPortrait', 'videoLandscape']:
        video = cc.get(key)
        if video and video.get('size'):
            return video['size']
    return 0


# ========== 更新日志 ==========

@ext_api.route('/changelog', methods=['GET'])
def get_changelog():
    """获取更新日志列表（按文件名倒序）"""
    import os
    changelog_dir = Path(__file__).parent.parent.parent / "changelog"
    if not changelog_dir.exists():
        changelog_dir = BASE_DIR / "changelog"
    if not changelog_dir.exists():
        return jsonify({"code": 200, "data": []})

    files = []
    for f in sorted(changelog_dir.iterdir()):
        if f.is_file() and f.suffix == '.html':
            # 从文件名提取日期 (20260525.html -> 2026-05-25)
            name = f.stem
            if len(name) == 8 and name.isdigit():
                date_str = f"{name[:4]}-{name[4:6]}-{name[6:8]}"
            else:
                date_str = name
            files.append({
                "filename": f.name,
                "date": date_str,
                "url": f"/changelog/{f.name}",
            })

    files.sort(key=lambda x: x['date'], reverse=True)
    return jsonify({"code": 200, "data": files})


# ========== 一键填写模板 ==========

@ext_api.route('/publish-templates', methods=['GET'])
def get_publish_templates():
    """一键填写：从历史成功/部分成功批次里取可复用的 per-channel 配置。

    Query: type=video|image (必填), page=1, page_size=20
    """
    type_ = request.args.get('type', '').strip()
    if type_ not in ('video', 'image'):
        return jsonify({"code": 400, "msg": "type 必须是 video 或 image"}), 400

    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
    except ValueError:
        return jsonify({"code": 400, "msg": "page / page_size 必须是整数"}), 400

    offset = (page - 1) * page_size
    conn = _db_conn()

    # 主查询：所有有 detail 带 account_configs 的成功/部分成功 batch
    rows = conn.execute(
        """SELECT b.id, b.type, b.title, b.description,
                  b.landscape_cover_material_id, b.portrait_cover_material_id,
                  b.video_material_id, b.image_material_ids,
                  b.created_at
           FROM publish_batches b
           WHERE b.type = ?
             AND b.status IN ('success', 'partial')
             AND EXISTS (SELECT 1 FROM publish_details d
                         WHERE d.batch_id = b.id AND d.account_configs != '{}')
           ORDER BY b.created_at DESC
           LIMIT ? OFFSET ?""",
        (type_, page_size, offset)
    ).fetchall()
    total = conn.execute(
        """SELECT COUNT(*) FROM publish_batches b
           WHERE b.type = ? AND b.status IN ('success', 'partial')
             AND EXISTS (SELECT 1 FROM publish_details d
                         WHERE d.batch_id = b.id AND d.account_configs != '{}')""",
        (type_,)
    ).fetchone()[0]

    # 解析 cover material_id → stored_path（thumbnail_path 必须是真实文件路径，
    # 前端 OneClickFillDialog 会拼到 /uploads/<path> 上）
    cover_ids = [
        r['landscape_cover_material_id'] or r['portrait_cover_material_id'] or ''
        for r in rows
    ]
    cover_ids = [cid for cid in cover_ids if cid]
    if cover_ids:
        placeholders = ','.join('?' * len(cover_ids))
        cover_rows = conn.execute(
            f"SELECT id, stored_path FROM materials WHERE id IN ({placeholders})",
            cover_ids
        ).fetchall()
        cover_path_map = {r['id']: r['stored_path'] for r in cover_rows}
    else:
        cover_path_map = {}

    conn.close()

    items = []
    for r in rows:
        # 拿第一个 detail 的 account_configs（用作可复用模板）
        # 单次小查询，按 batch_id 升序拿第一条
        dconn = _db_conn()
        first_detail = dconn.execute(
            "SELECT account_configs, platform FROM publish_details WHERE batch_id = ? "
            "AND account_configs != '{}' ORDER BY created_at ASC LIMIT 1",
            (r['id'],)
        ).fetchone()
        # 拿所有 platform 作 channels 列表
        all_platforms = dconn.execute(
            "SELECT DISTINCT platform FROM publish_details WHERE batch_id = ?",
            (r['id'],)
        ).fetchall()
        dconn.close()

        configs = json.loads((first_detail['account_configs'] if first_detail else None) or '{}')
        channels = [{'platform': p['platform']} for p in all_platforms if p['platform']]

        # cover 优先 landscape，回落 portrait；material_id 解析到 stored_path
        cover_id = r['landscape_cover_material_id'] or r['portrait_cover_material_id'] or ''
        thumbnail_path = cover_path_map.get(cover_id, '')

        # image_material_ids 是 JSON 数组字符串，取第一个元素作为 first_image_id
        img_ids_raw = r['image_material_ids'] or '[]'
        try:
            img_ids_list = json.loads(img_ids_raw)
            first_image_id = img_ids_list[0] if img_ids_list else None
        except (json.JSONDecodeError, TypeError):
            first_image_id = None

        items.append({
            "id": r['id'],
            "type": r['type'],
            "title": r['title'] or '',
            "description": r['description'] or '',
            "thumbnail_path": thumbnail_path,
            "first_image_id": first_image_id,
            "video_material_id": r['video_material_id'] or '',
            "channels": channels,
            "account_configs": configs,
            "created_at": r['created_at'],
        })

    return jsonify({
        "code": 200,
        "data": {
            "list": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    })


# ========== 草稿批量发布 ==========
@ext_api.route('/drafts/batch-publish', methods=['POST'])
def batch_publish_drafts():
    """视频草稿批量发布：每个 (draft, account) 入队 1 个 task。

    Body: {"draft_ids": [int, ...]}  (1-30 个视频草稿 id)
    Response: {"code": 200, "task_ids": [...], "failed": [...]}
    """
    data = request.get_json() or {}
    draft_ids = data.get('draft_ids') or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    from app import _get_db_path, PLATFORM_ID_TO_KEY
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    placeholders = ','.join('?' * len(draft_ids))
    rows = conn.execute(
        f"SELECT id, type, draft_data FROM drafts WHERE id IN ({placeholders})",
        draft_ids
    ).fetchall()
    conn.close()

    found_ids = {r['id'] for r in rows}
    missing_ids = [i for i in draft_ids if i not in found_ids]
    if missing_ids:
        return jsonify({"code": 404, "msg": "草稿不存在", "missing_ids": missing_ids}), 404

    wrong_type = [r['id'] for r in rows if r['type'] != 'video']
    if wrong_type:
        return jsonify({"code": 400, "msg": "包含非视频草稿", "wrong_type_ids": wrong_type}), 400

    # 反向映射：platform key → 整数平台 id（给 PublishTask.platform_type）
    KEY_TO_PLATFORM_ID = {v: k for k, v in PLATFORM_ID_TO_KEY.items()}

    # 通过模块属性查找 get_task_queue，让 monkeypatch.setattr(tq, 'get_task_queue', ...)
    # 能生效（直接调用本模块的 get_task_queue 会绕过 patch）。
    from . import task_queue as _tq
    task_queue = _tq.get_task_queue()
    task_ids = []
    failed = []
    # draft_id → batch_id 映射，让同一 draft 的多个 detail 共享一个 batch
    task_batch_id_by_draft = {}

    for r in rows:
        draft = {
            'id': r['id'],
            'type': r['type'],
            'draft_data': json.loads(r['draft_data'] or '{}'),
        }
        try:
            errs = validate_draft_for_publish(draft)
            if errs:
                failed.append({'draft_id': r['id'], 'reason': '; '.join(errs)})
                continue

            draft_data = draft['draft_data']
            common = draft_data.get('commonConfig') or {}
            platform_configs = draft_data.get('platformConfigs') or {}
            account_overrides = draft_data.get('accountOverrides') or {}
            publish_account_ids = draft_data.get('publishAccountIds') or []

            for account_id in publish_account_ids:
                # 查 user_info（生产 schema: id, type INTEGER, filePath TEXT）
                acc_conn = sqlite3.connect(str(db_path))
                acc_conn.row_factory = sqlite3.Row
                acc_row = acc_conn.execute(
                    "SELECT id, type, filePath, userName FROM user_info WHERE id = ?",
                    (account_id,),
                ).fetchone()
                acc_conn.close()
                if not acc_row:
                    failed.append({'draft_id': r['id'], 'reason': f'账号 {account_id} 不存在'})
                    continue

                account_platform = PLATFORM_ID_TO_KEY.get(acc_row['type'], '')
                platform_default = platform_configs.get(account_platform) or {}
                account_ov = account_overrides.get(str(account_id)) or {}

                platform_overrides = draft_data.get('platformOverrides') or {}
                merged = merge_config(
                    common, platform_default,
                    platform_overrides.get(account_platform),
                    account_ov,
                )

                account_obj = type('Account', (), {})()
                account_obj.id = acc_row['id']
                account_obj.platform = account_platform
                account_obj.file_path = acc_row['filePath']

                payload = build_platform_kwargs(merged, common, account_obj)

                ptype = KEY_TO_PLATFORM_ID.get(account_platform)
                if not ptype:
                    failed.append({'draft_id': r['id'], 'reason': f'未知平台: {account_platform}'})
                    continue

                task_id = str(uuid.uuid4())
                # 草稿批量发布：每个 (draft, account) 一个 detail，但同一 draft 的所有 detail 共享一个 batch_id
                # （task.batch_id 第一次循环时初始化，后续同 draft 共享；这里每个 draft_id 只一次循环无问题）
                if not task_batch_id_by_draft.get(r['id']):
                    task_batch_id_by_draft[r['id']] = str(uuid.uuid4())
                # 把 stored_path 相对路径转成绝对路径（与 postVideo 的 _resolve_material_path 一致）
                # 否则 worker 拿相对路径去 set_input_files，Playwright 找不到文件，会触发 3 次重试。
                from storage import resolve_material_path
                raw_video = (payload.get('files') or [''])[0]
                raw_thumbnail = payload.get('thumbnail_path', '') or ''
                resolved_video = resolve_material_path(raw_video)
                resolved_thumbnail = resolve_material_path(raw_thumbnail)
                if not resolved_video:
                    # 文件解析失败（草稿里引用了已被用户从磁盘删除的文件），直接标记失败，
                    # 避免 worker 重复开浏览器重试 3 次。
                    failed.append({
                        'draft_id': r['id'],
                        'reason': f'账号 {account_id} 视频文件不存在: {raw_video}',
                    })
                    continue
                task = PublishTask(
                    id=task_id,
                    batch_id=task_batch_id_by_draft[r['id']],
                    platform=account_platform,
                    platform_type=ptype,
                    account_name=acc_row['userName'] or '',
                    account_cookie_path=acc_row['filePath'] or '',
                    video_path=resolved_video,
                    title=payload.get('title', ''),
                    description=payload.get('desc', ''),
                    thumbnail_path=resolved_thumbnail,
                    tags=payload.get('tags') or [],
                    source='draft',
                    draft_id=r['id'],
                    account_id=account_id,
                    payload=payload,
                    # 草稿批量发布:失败立即标记 FAILED,不重试(用户需求)
                    max_retries=0,
                )
                try:
                    task_queue.add_task(task)
                    task_ids.append(task_id)
                except Exception as e:
                    failed.append({'draft_id': r['id'], 'reason': f'入队失败: {e}'})
        except Exception as e:
            failed.append({'draft_id': r['id'], 'reason': str(e)})

    return jsonify({"code": 200, "task_ids": task_ids, "failed": failed}), 200


# ========== 视频草稿批量删除 ==========

@ext_api.route('/drafts/batch', methods=['DELETE'])
def batch_delete_drafts():
    """视频草稿批量删除。

    Body: {"draft_ids": [int, ...]}  (1-30 个草稿 id)
    Response 200: {"code": 200, "deleted": [...], "failed": [{draft_id, reason}, ...]}
    Response 400: draft_ids 缺失/非列表/为空/超过 30
    """
    from flask import request
    data = request.get_json() or {}
    draft_ids = data.get('draft_ids') or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    from app import _get_db_path
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    placeholders = ','.join('?' * len(draft_ids))

    existing = {r[0] for r in conn.execute(
        f"SELECT id FROM drafts WHERE id IN ({placeholders})", draft_ids
    ).fetchall()}

    deleted = []
    failed = []
    for did in draft_ids:
        if did in existing:
            try:
                conn.execute("DELETE FROM drafts WHERE id = ?", (did,))
                deleted.append(did)
            except Exception as e:
                failed.append({'draft_id': did, 'reason': str(e)})
        else:
            failed.append({'draft_id': did, 'reason': '草稿不存在'})

    conn.commit()
    conn.close()

    return jsonify({"code": 200, "deleted": deleted, "failed": failed}), 200


# ========== 测试用 Flask app ==========
# 测试代码（test_publish_templates.py）通过 `ext_api.app.test_request_context()` 推请求上下文调用
# 路由函数。这个独立 Flask app 让 Blueprint 可独立测试，不污染 backend/app.py 的主 app。
from flask import Flask
app = Flask(__name__)
app.register_blueprint(ext_api)


# ========== 解决 `import ext_api` 与 `import ext_api.__init__` 是不同模块对象的问题 ==========
# Python 在 `import ext_api` 时把 `__init__.py` 注册为 `sys.modules['ext_api']`，
# 但 `import ext_api.__init__` 会把同一个文件再注册为 `sys.modules['ext_api.__init__']`。
# 两个条目指向不同 module 对象，导致测试中 patch `_db_conn` 不生效（route 函数的
# __globals__ 仍指向 `ext_api`，而 patch 修改的是 `ext_api.__init__`）。
# 这里把 `ext_api.__init__` 重定向到 `ext_api`，让两种 import 路径拿到同一个对象。
import sys as _sys
_sys.modules.setdefault('ext_api.__init__', _sys.modules[__name__])
