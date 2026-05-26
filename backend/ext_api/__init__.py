"""
扩展 API Blueprint — 阶段二
任务管理、发布历史、统计数据、SSE 实时推送
"""

import json
import sqlite3
import queue
import threading
from datetime import datetime, timedelta
from pathlib import Path
from flask import Blueprint, request, jsonify, Response

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR

from .task_queue import get_task_queue, PublishTask, TaskStatus

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


# ========== 任务管理 ==========

@ext_api.route('/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表（支持分页、状态过滤）"""
    status = request.args.get('status')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    offset = (page - 1) * page_size

    try:
        conn = _db_conn()
        where = ""
        params = []
        if status and status != 'all':
            where = "WHERE status = ?"
            params.append(status)

        total = conn.execute(f"SELECT COUNT(*) FROM publish_tasks {where}", params).fetchone()[0]

        rows = conn.execute(
            f"SELECT * FROM publish_tasks {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        ).fetchall()

        tasks = []
        for row in rows:
            d = dict(row)
            try:
                d['tags'] = json.loads(d.get('tags', '[]'))
            except json.JSONDecodeError:
                d['tags'] = []
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


@ext_api.route('/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """获取单个任务详情"""
    try:
        conn = _db_conn()
        row = conn.execute("SELECT * FROM publish_tasks WHERE id = ?", (task_id,)).fetchone()
        conn.close()
        if not row:
            return jsonify({"code": 404, "msg": "任务不存在"}), 404
        d = dict(row)
        try:
            d['tags'] = json.loads(d.get('tags', '[]'))
        except json.JSONDecodeError:
            d['tags'] = []
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

@ext_api.route('/history', methods=['GET'])
def get_history():
    """发布历史记录（支持日期范围、平台、状态过滤）"""
    # 平台 key → 中文名映射
    platform_key_map = {
        'xiaohongshu': '小红书', 'channels': '视频号', 'douyin': '抖音',
        'kuaishou': '快手', 'bilibili': 'B站',
    }

    platform = request.args.get('platform')
    status = request.args.get('status')
    time_range = request.args.get('timeRange')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('pageSize', 20))
    offset = (page - 1) * page_size

    # 将 timeRange 转换为实际日期范围
    if time_range and not start_date:
        now = datetime.now()
        if time_range == 'today':
            start_date = now.strftime('%Y-%m-%d')
        elif time_range == '7days':
            start_date = (now - timedelta(days=7)).strftime('%Y-%m-%d')
        elif time_range == '30days':
            start_date = (now - timedelta(days=30)).strftime('%Y-%m-%d')

    # 将平台 key 转换为中文名
    if platform and platform in platform_key_map:
        platform = platform_key_map[platform]

    conditions = []
    params = []

    if platform:
        conditions.append("platform = ?")
        params.append(platform)
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
        total = conn.execute(f"SELECT COUNT(*) FROM publish_tasks {where}", params).fetchone()[0]

        rows = conn.execute(
            f"SELECT * FROM publish_tasks {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [page_size, offset]
        ).fetchall()

        records = [dict(row) for row in rows]
        for r in records:
            try:
                r['tags'] = json.loads(r.get('tags', '[]'))
            except json.JSONDecodeError:
                r['tags'] = []
            # 为前端补充 duration 字段（秒数）
            if r.get('started_at') and r.get('finished_at'):
                try:
                    started = datetime.fromisoformat(r['started_at'])
                    finished = datetime.fromisoformat(r['finished_at'])
                    r['duration'] = int((finished - started).total_seconds())
                except (ValueError, TypeError):
                    r['duration'] = None
            else:
                r['duration'] = None

        conn.close()
        return jsonify({"code": 200, "data": {"items": records, "total": total, "page": page, "pageSize": page_size}})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ========== 统计数据 ==========

@ext_api.route('/stats', methods=['GET'])
def get_stats():
    """获取统计数据（成功率、发布量趋势等）"""
    try:
        conn = _db_conn()

        # 总体统计
        total = conn.execute("SELECT COUNT(*) FROM publish_tasks").fetchone()[0]
        success = conn.execute("SELECT COUNT(*) FROM publish_tasks WHERE status='success'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM publish_tasks WHERE status='failed'").fetchone()[0]
        running = conn.execute("SELECT COUNT(*) FROM publish_tasks WHERE status IN ('pending','queued','running')").fetchone()[0]

        # 按平台统计
        platform_rows = conn.execute(
            "SELECT platform, COUNT(*) as count FROM publish_tasks GROUP BY platform"
        ).fetchall()
        by_platform = {row['platform']: row['count'] for row in platform_rows}

        # 最近7天趋势
        trend = []
        for i in range(6, -1, -1):
            date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            next_date = (datetime.now() - timedelta(days=i-1)).strftime('%Y-%m-%d') if i > 0 else (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            count = conn.execute(
                "SELECT COUNT(*) FROM publish_tasks WHERE created_at >= ? AND created_at < ?",
                (date, next_date)
            ).fetchone()[0]
            trend.append({"date": date, "count": count})

        # 本月发布数
        month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime('%Y-%m-%d')
        monthly_total = conn.execute(
            "SELECT COUNT(*) FROM publish_tasks WHERE created_at >= ?", (month_start,)
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
        conn = _db_conn()
        for key, value in data.items():
            conn.execute(
                """INSERT OR REPLACE INTO settings (key, value, updated_at)
                   VALUES (?, ?, ?)""",
                (key, str(value), datetime.now().isoformat())
            )
        conn.commit()
        conn.close()
        return jsonify({"code": 200, "msg": "设置已更新"})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ========== 草稿箱 ==========

@ext_api.route('/drafts', methods=['GET'])
def get_drafts():
    """获取草稿列表"""
    try:
        conn = _db_conn()
        rows = conn.execute(
            "SELECT id, title, cover_path, channels_summary, video_duration, video_file_size, created_at, updated_at FROM drafts ORDER BY updated_at DESC"
        ).fetchall()
        drafts = []
        for row in rows:
            d = dict(row)
            try:
                d['channels_summary'] = json.loads(d.get('channels_summary', '[]'))
            except json.JSONDecodeError:
                d['channels_summary'] = []
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
    title = _extract_draft_title(draft_data)
    cover_path = _extract_draft_cover(draft_data)
    channels_summary = _extract_channels_summary(draft_data)
    video_duration = _extract_video_duration(draft_data)
    video_file_size = _extract_video_file_size(draft_data)

    try:
        conn = _db_conn()
        cursor = conn.execute(
            """INSERT INTO drafts (title, cover_path, draft_data, channels_summary, video_duration, video_file_size)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, cover_path, json.dumps(draft_data, ensure_ascii=False),
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
