import asyncio
import hashlib
import hmac
import json
import os
import random
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue

import requests as _requests

# [FIX 2026-06-10] httpx（cloakbrowser 依赖）不支持 SOCKS proxy，系统设置了 ALL_PROXY=socks://
# 会让 cloakbrowser 的 wrapper update check 直接崩。启动时清掉 SOCKS env（保留 HTTP/HTTPS proxy）
for _k in ('ALL_PROXY', 'all_proxy'):
    os.environ.pop(_k, None)

from flask import Flask, Response, g, jsonify, request, send_from_directory
from flask_cors import CORS

BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from conf import (
    BASE_DIR,
    FEEDBACK_API_BASE_URL,
    FEEDBACK_APP_KEY,
    FEEDBACK_APP_SECRET,
    FEEDBACK_API_TIMEOUT,
)
from util._logger import get_channel_logger

logger = get_channel_logger("backend")


def _ensure_materials_table():
    """服务启动时确保 materials 表存在"""
    DB_PATH = BASE_DIR / "db" / "database.db"
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER DEFAULT 0,
            storage_type TEXT NOT NULL DEFAULT 'local',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            duration REAL DEFAULT 0,
            thumbnail_path TEXT DEFAULT '',
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    logger.info("[Startup] materials 表已就绪")


_ensure_materials_table()

logger.info(f"[Startup] Python {sys.version} starting...")
logger.info(f"[Startup] Script: {__file__}")
logger.info(f"[Startup] SAU_PORT={os.environ.get('SAU_PORT')}, SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")
from impl.registry import get_platform
from impl.settings import read_settings

app = Flask(__name__)
CORS(app)
# 视频/图片上传不限大小（用户 2026-06-10 明确要求）
# 警告：当前 materials_bp.py:125 用 file.read() 一次性读入内存，超大文件会 OOM
# 如未来需要处理 ≥10GB 文件，应改为流式写入（request.stream → storage.save_stream）
app.config['MAX_CONTENT_LENGTH'] = None

# SSE login status queues (keyed by account id)
active_queues: dict[str, Queue] = {}


def _is_terminal_login_sse_message(message: str) -> bool:
    if message in {"200", "500"}:
        return True
    try:
        payload = json.loads(message)
    except (TypeError, json.JSONDecodeError):
        return False
    return str(payload.get("status", "")).lower() in {"200", "500", "0", "error"}


def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
            if _is_terminal_login_sse_message(msg):
                break
        else:
            time.sleep(0.1)


# 注册阶段二扩展 API Blueprint
logger.info("[Startup] Importing ext_api...")
from ext_api import ext_api  # noqa: E402
app.register_blueprint(ext_api)
logger.info("[Startup] ext_api registered OK")

from routes.frames import frames_bp  # noqa: E402
app.register_blueprint(frames_bp)
logger.info("[Startup] frames_bp registered OK")

from blueprints.image_publish_bp import image_publish_bp  # noqa: E402
app.register_blueprint(image_publish_bp)
logger.info("[Startup] image_publish_bp registered OK")

from blueprints.douyin_image_bp import douyin_image_bp  # noqa: E402
app.register_blueprint(douyin_image_bp)
logger.info("[Startup] douyin_image_bp registered OK")

from blueprints.alipay_bp import alipay_bp  # noqa: E402
app.register_blueprint(alipay_bp)
logger.info("[Startup] alipay_bp registered OK")

from blueprints.materials_bp import materials_bp  # noqa: E402
app.register_blueprint(materials_bp)
logger.info("[Startup] materials_bp registered OK")

from blueprints.kuaishou_image_bp import kuaishou_image_bp  # noqa: E402
app.register_blueprint(kuaishou_image_bp)
logger.info("[Startup] kuaishou_image_bp registered OK")

from blueprints.uploads_bp import uploads_bp  # noqa: E402
app.register_blueprint(uploads_bp)
logger.info("[Startup] uploads_bp registered OK")

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
logger.info(f"[Startup] Frontend dir: {FRONTEND_DIR} (exists={FRONTEND_DIR.exists()})")


@app.route('/')
def index():
    if FRONTEND_DIR.exists():
        return send_from_directory(str(FRONTEND_DIR), 'index.html')
    return jsonify({"code": 200, "msg": "API server running"}), 200


@app.route('/assets/<path:filename>')
def custom_static(filename):
    return send_from_directory(str(FRONTEND_DIR / 'assets'), filename)


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(str(FRONTEND_DIR), 'favicon.ico')


@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(str(FRONTEND_DIR), 'vite.svg')


@app.route('/changelog/<path:filename>')
def serve_changelog(filename):
    changelog_dir = Path(__file__).parent.parent / "changelog"
    if not changelog_dir.exists():
        changelog_dir = BASE_DIR / "changelog"
    return send_from_directory(str(changelog_dir), filename)


# ── Helper ──────────────────────────────────────────────────

def _get_db_path():
    if data_dir := os.environ.get("SAU_DATA_DIR"):
        return Path(data_dir) / "db" / "database.db"
    return Path(__file__).parent.parent / "data" / "db" / "database.db"


DB_PATH = _get_db_path()
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube", 9: "腾讯视频", 10: "爱奇艺", 11: "微博", 12: "支付宝"}
PLATFORM_ID_TO_KEY = {
    1: 'xiaohongshu', 2: 'channels', 3: 'douyin', 4: 'kuaishou', 5: 'bilibili',
    6: 'baijiahao', 7: 'tiktok', 8: 'youtube', 9: 'tencent_video', 10: 'iqiyi',
    11: 'weibo', 12: 'alipay',
}


def _get_account_record(account_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def _resolve_material_path(path_or_stored_path):
    """兼容旧调用：转发到 storage.resolve_material_path"""
    from storage import resolve_material_path
    return resolve_material_path(path_or_stored_path)


# ── Account management ──────────────────────────────────────

@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            for row in rows_list:
                tags = conn.execute('''
                    SELECT t.id, t.name, t.color FROM tags t
                    JOIN account_tags at ON t.id = at.tag_id
                    WHERE at.account_id = ?
                ''', (row[0],)).fetchall()
                row.append([dict(t) for t in tags])

        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"获取账号列表失败: {str(e)}", "data": None}), 500


@app.route("/getValidAccounts", methods=['GET'])
def getValidAccounts():
    """获取所有账号并使用新引擎逐个验证 cookie 有效性"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

        for row in rows_list:
            platform = get_platform(row[1])
            if platform:
                try:
                    valid = asyncio.run(platform.check_cookie(row[2]))
                except Exception:
                    valid = False
                new_status = 1 if valid else 0
                row[4] = new_status
                with sqlite3.connect(str(DB_PATH)) as conn:
                    conn.execute('UPDATE user_info SET status = ? WHERE id = ?', (new_status, row[0]))

        with sqlite3.connect(str(DB_PATH)) as conn:
            for row in rows_list:
                tags = conn.execute('''
                    SELECT t.id, t.name, t.color FROM tags t
                    JOIN account_tags at ON t.id = at.tag_id
                    WHERE at.account_id = ?
                ''', (row[0],)).fetchall()
                row.append([dict(t) for t in tags])

        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"获取账号列表失败: {str(e)}", "data": None}), 500


@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "Invalid or missing account ID", "data": None}), 400

    account_id = int(account_id)
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({"code": 404, "msg": "account not found", "data": None}), 404

            record = dict(record)
            if record.get('filePath'):
                cookie_file_path = Path(BASE_DIR / "cookiesFile" / record['filePath'])
                if cookie_file_path.exists():
                    try:
                        cookie_file_path.unlink()
                    except Exception as e:
                        logger.info(f"[WARN] 删除Cookie文件失败: {e}")

            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({"code": 200, "msg": "account deleted successfully", "data": None}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"delete failed: {str(e)}", "data": None}), 500


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    data = request.get_json()
    user_id = data.get('id')
    type_ = data.get('type')
    userName = data.get('userName')
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                'UPDATE user_info SET type = ?, userName = ? WHERE id = ?',
                (type_, userName, user_id)
            )
            conn.commit()
        return jsonify({"code": 200, "msg": "account update successfully", "data": None}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": "update failed!", "data": None}), 500


# ── Tag management ────────────────────────────────────────

@app.route('/api/tags', methods=['GET'])
def get_tags():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM tags ORDER BY name').fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = data.get('color') or random.choice([
        '#6366f1', '#8b5cf6', '#ec4899', '#f43f5e',
        '#f97316', '#f59e0b', '#10b981', '#14b8a6',
        '#0ea5e9', '#3b82f6',
    ])
    if not name:
        return jsonify({"code": 400, "msg": "标签名不能为空"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('INSERT INTO tags (name, color) VALUES (?, ?)', (name, color))
            tag_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
        return jsonify({"code": 200, "data": {"id": tag_id, "name": name, "color": color}})
    except sqlite3.IntegrityError:
        return jsonify({"code": 409, "msg": "标签名已存在"}), 409
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # SQLite 默认不强制外键,需要先清关联行
            conn.execute('DELETE FROM account_tags WHERE tag_id = ?', (tag_id,))
            conn.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/<int:account_id>/tags', methods=['PUT'])
def set_account_tags(account_id):
    data = request.get_json()
    tag_ids = data.get('tag_ids', [])
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('DELETE FROM account_tags WHERE account_id = ?', (account_id,))
            for tid in tag_ids:
                conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/batch/tags', methods=['PUT'])
def set_batch_account_tags():
    """批量为多个账号添加相同的标签(追加模式:不清除已有标签)"""
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    tag_ids = data.get('tag_ids', [])
    if not account_ids:
        return jsonify({"code": 400, "msg": "请选择至少一个账号"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            for account_id in account_ids:
                for tid in tag_ids:
                    conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200, "data": {"updated": len(account_ids)}})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/<int:account_id>/tags', methods=['GET'])
def get_account_tags(account_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT t.* FROM tags t
                JOIN account_tags at ON t.id = at.tag_id
                WHERE at.account_id = ?
                ORDER BY t.name
            ''', (account_id,)).fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


# ── Cookie file management ──────────────────────────────────

@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({"code": 400, "msg": "没有找到Cookie文件", "data": None}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({"code": 400, "msg": "Cookie文件名不能为空", "data": None}), 400
        if not file.filename.endswith('.json'):
            return jsonify({"code": 400, "msg": "Cookie文件必须是JSON格式", "data": None}), 400

        account_id = request.form.get('id')
        platform = request.form.get('platform')
        if not account_id or not platform:
            return jsonify({"code": 400, "msg": "缺少账号ID或平台信息", "data": None}), 400

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

        cookie_file_path = Path(BASE_DIR / "cookiesFile" / result['filePath'])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)
        file.save(str(cookie_file_path))

        return jsonify({"code": 200, "msg": "Cookie文件上传成功", "data": None}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"上传Cookie文件失败: {str(e)}", "data": None}), 500


@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({"code": 400, "msg": "缺少文件路径参数", "data": None}), 400

        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR / "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({"code": 400, "msg": "非法文件路径", "data": None}), 400
        if not cookie_file_path.exists():
            return jsonify({"code": 404, "msg": "Cookie文件不存在", "data": None}), 404

        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )
    except Exception as e:
        return jsonify({"code": 500, "msg": f"下载Cookie文件失败: {str(e)}", "data": None}), 500


# ── Core platform routes (new engine) ───────────────────────

@app.route('/checkAccount', methods=['GET'])
def check_account():
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "无效的账号ID"}), 400

    record = _get_account_record(int(account_id))
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在"}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    valid = asyncio.run(platform.check_cookie(record['filePath']))
    new_status = 1 if valid else 0
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.execute('UPDATE user_info SET status = ? WHERE id = ?', (new_status, record['id']))

    msg = "Cookie 有效" if valid else "Cookie 已失效，请重新登录"
    return jsonify({"code": 200, "msg": msg, "data": {"id": record['id'], "status": new_status, "valid": valid}})


@app.route('/syncProfile', methods=['POST'])
def sync_profile():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID", "data": None}), 400

    record = _get_account_record(account_id)
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型", "data": None}), 400

    name, avatar = asyncio.run(platform.sync_profile(record['filePath']))
    if name or avatar:
        with sqlite3.connect(str(DB_PATH)) as conn:
            if name:
                conn.execute('UPDATE user_info SET userName = ?, avatar = ? WHERE id = ?',
                             (name, avatar, account_id))
            else:
                conn.execute('UPDATE user_info SET avatar = ? WHERE id = ?', (avatar, account_id))

    return jsonify({"code": 200, "msg": "同步成功", "data": {"name": name, "avatar": avatar}})


@app.route('/api/image-proxy')
def image_proxy():
    """头像代理：绕过 sinaimg.cn 防盗链。后端请求带 Referer=weibo.com。"""
    url = request.args.get('url')
    if not url:
        return jsonify({"code": 400, "msg": "缺少 url 参数"}), 400
    import httpx
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/135.0.0.0 Safari/537.36",
                "Referer": "https://weibo.com/",
            },
            timeout=15,
        )
        return Response(resp.content, mimetype=resp.headers.get("content-type", "image/jpeg"))
    except Exception as e:
        logger.warning(f"[image-proxy] fetch failed: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/openCreatorCenter', methods=['POST'])
def open_creator_center():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID"}), 400

    record = _get_account_record(account_id)
    if not record:
        return jsonify({"code": 404, "msg": "账号不存在"}), 404

    platform = get_platform(record['type'])
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    thread = threading.Thread(
        target=lambda: asyncio.run(platform.open_creator_center(record['filePath'])),
        daemon=True
    )
    thread.start()
    return jsonify({"code": 200, "msg": "正在打开创作中心"})


@app.route('/login')
def login():
    type_str = request.args.get('type')
    id_str = request.args.get('id')
    account_id = request.args.get('account_id')
    if not type_str or not id_str:
        return jsonify({"code": 400, "msg": "缺少 type 或 id"}), 400

    platform = get_platform(int(type_str))
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    status_queue = Queue()
    active_queues[id_str] = status_queue

    def _cleanup():
        active_queues.pop(id_str, None)

    def _run_login():
        try:
            asyncio.run(platform.login(id_str, status_queue, account_id=account_id))
        except asyncio.CancelledError:
            logger.info(f"[login] 用户关闭了浏览器，{platform.platform_name} 登录取消")
            status_queue.put(json.dumps({"status": "error", "msg": "用户关闭了浏览器"}))

    thread = threading.Thread(
        target=_run_login,
        daemon=True
    )
    thread.start()

    response = Response(sse_stream(status_queue), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Content-Type'] = 'text/event-stream'
    response.call_on_close(_cleanup)
    return response


def _validate_publish_video(type_id, file_list):
    """校验视频文件是否符合平台限制。

    Returns:
        (ok, error_msg). 通过时 error_msg 为空字符串。
        材料缺失时跳过校验（兼容老路径直接上传）。
    """
    from util.video_limits import validate_video_for_platform

    if not file_list:
        return True, ""

    platform = get_platform(type_id)
    if platform is None or not hasattr(platform, "platform_key"):
        return True, ""

    platform_key = platform.platform_key

    first_file = next((f for f in file_list if f), None)
    if not first_file:
        return True, ""

    # 兜底：存量视频 duration 可能为 0（草稿/历史恢复绕过了素材库 probe）。
    # 在读 DB 拿到 duration 后，若仍 <=0 则同步补全，确保校验拿到真实时长。
    # 与原查询合并为一次 DB 访问，避免重复连接；表缺失/异常一律降级跳过。
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT duration, file_size FROM materials WHERE stored_path = ?",
            (first_file,),
        ).fetchone()

        # 时长缺失则同步兜底补全，再重读一次拿到最新值
        if row and (not row["duration"] or row["duration"] <= 0):
            conn.close()
            try:
                from services.duration_repair import ensure_duration_or_probe
                ensure_duration_or_probe(first_file, row["duration"])
            except Exception as _e:
                logger.debug("提交前时长兜底失败（不影响后续校验）: %s", str(_e))
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT duration, file_size FROM materials WHERE stored_path = ?",
                (first_file,),
            ).fetchone()
        conn.close()
    except Exception:
        return True, ""

    if row is None:
        return True, ""

    return validate_video_for_platform(platform_key, row["duration"], row["file_size"])


@app.route('/postVideo', methods=['POST'])
def postVideo():
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400

    logger.info("postVideo data: tag_type=%s, tag_value=%s, hotspot=%s, mix_id=%s",
                 data.get('tag_type'), data.get('tag_value'), data.get('hotspot'), data.get('mix_id'))

    platform = get_platform(data.get('type'))
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    # 视频时长/大小校验（早于 publish_video，避免无效提交）
    ok, err = _validate_publish_video(data.get('type'), data.get('fileList', []))
    if not ok:
        logger.info(f"发布视频校验失败: {err}")
        return jsonify({"code": 400, "msg": err}), 400

    try:
        # Resolve file paths through storage abstraction
        file_list = [_resolve_material_path(f) for f in data.get('fileList', [])]
        thumbnail_landscape = _resolve_material_path(data.get('thumbnailLandscape', ''))
        thumbnail_portrait = _resolve_material_path(data.get('thumbnailPortrait', ''))

        # 兜底：只上传了横版或竖版之一时，另一个用同图（保证 2 个封面都有内容）
        if thumbnail_landscape and not thumbnail_portrait:
            thumbnail_portrait = thumbnail_landscape
        elif thumbnail_portrait and not thumbnail_landscape:
            thumbnail_landscape = thumbnail_portrait

        # Some platforms have sync publish_video, others async.
        # asyncio.run() only works with coroutines — calling it on a
        # sync function that already uses asyncio.run() internally
        # would pass a bool to asyncio.run() and throw.
        # 提取新传入的参数
        activities = data.get('activities', [])
        hotspot = data.get('hotspot', '')
        tag_type = data.get('tag_type', '')
        tag_value = data.get('tag_value', '')
        mini_link = data.get('mini_link', '')
        mix_id = data.get('mix_id', '')

        publish_fn = platform.publish_video
        if asyncio.iscoroutinefunction(publish_fn):
            result = asyncio.run(publish_fn(
                title=data.get('title'),
                files=file_list,
                tags=data.get('tags'),
                activities=activities,
                account_file=data.get('accountList', []),
                category=data.get('category'),
                enableTimer=data.get('enableTimer'),
                videos_per_day=data.get('videosPerDay'),
                daily_times=data.get('dailyTimes'),
                start_days=data.get('startDays'),
                thumbnail_path=data.get('thumbnail', ''),
                thumbnail_landscape_path=thumbnail_landscape,
                thumbnail_portrait_path=thumbnail_portrait,
                productLink=data.get('productLink', ''),
                productTitle=data.get('productTitle', ''),
                desc=data.get('description', ''),
                schedule_time_str=data.get('scheduleTime', ''),
                ai_content=data.get('aiContent', ''),
                creation_declaration=data.get('creationDeclaration', ''),
                risk_warning=data.get('riskWarning', ''),
                enable_cash_activity=data.get('enableCashActivity', False),
                supplementary_declaration=data.get('supplementaryDeclaration', ''),
                is_draft=data.get('isDraft', False),
                audience=data.get('audience', 'not_kids'),
                altered_content=data.get('alteredContent', False),
                hotspot=hotspot,
                tag_type=tag_type,
                tag_value=tag_value,
                mini_link=mini_link,
                mix_id=mix_id,
                content_statement=data.get('contentStatement', ''),
                author_statement=data.get('authorStatement', ''),
                compilation=data.get('compilation', ''),
            ))
        else:
            result = publish_fn(
                title=data.get('title'),
                files=file_list,
                tags=data.get('tags'),
                activities=activities,
                account_file=data.get('accountList', []),
                category=data.get('category'),
                enableTimer=data.get('enableTimer'),
                videos_per_day=data.get('videosPerDay'),
                daily_times=data.get('dailyTimes'),
                start_days=data.get('startDays'),
                thumbnail_path=data.get('thumbnail', ''),
                thumbnail_landscape_path=thumbnail_landscape,
                thumbnail_portrait_path=thumbnail_portrait,
                productLink=data.get('productLink', ''),
                productTitle=data.get('productTitle', ''),
                desc=data.get('description', ''),
                schedule_time_str=data.get('scheduleTime', ''),
                ai_content=data.get('aiContent', ''),
                creation_declaration=data.get('creationDeclaration', ''),
                risk_warning=data.get('riskWarning', ''),
                enable_cash_activity=data.get('enableCashActivity', False),
                supplementary_declaration=data.get('supplementaryDeclaration', ''),
                is_draft=data.get('isDraft', False),
                audience=data.get('audience', 'not_kids'),
                altered_content=data.get('alteredContent', False),
                hotspot=hotspot,
                tag_type=tag_type,
                tag_value=tag_value,
                mini_link=mini_link,
                mix_id=mix_id,
                content_statement=data.get('contentStatement', ''),
                author_statement=data.get('authorStatement', ''),
                compilation=data.get('compilation', ''),
            )
        if result:
            return jsonify({"code": 200, "msg": "发布任务已提交", "data": None}), 200
        else:
            return jsonify({"code": 500, "msg": "发布失败：页面未跳转，表单校验未通过", "data": None}), 500
    except Exception as e:
        logger.info(f"发布视频时出错: {str(e)}")
        return jsonify({"code": 500, "msg": f"发布失败: {str(e)}", "data": None}), 500


@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()
    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400

    failures = []
    for idx, data in enumerate(data_list):
        platform = get_platform(data.get('type'))
        if not platform:
            failures.append({"index": idx, "reason": "不支持的平台类型"})
            continue

        # 视频时长/大小校验
        ok, err = _validate_publish_video(data.get('type'), data.get('fileList', []))
        if not ok:
            failures.append({"index": idx, "reason": err})
            continue

        try:
            # Resolve file paths through storage abstraction
            file_list = [_resolve_material_path(f) for f in data.get('fileList', [])]
            thumbnail_landscape = _resolve_material_path(data.get('thumbnailLandscape', ''))
            thumbnail_portrait = _resolve_material_path(data.get('thumbnailPortrait', ''))

            publish_fn = platform.publish_video
            if asyncio.iscoroutinefunction(publish_fn):
                result = asyncio.run(publish_fn(
                    title=data.get('title'),
                    files=file_list,
                    tags=data.get('tags'),
                    account_file=data.get('accountList', []),
                    category=data.get('category'),
                    enableTimer=data.get('enableTimer'),
                    videos_per_day=data.get('videosPerDay'),
                    daily_times=data.get('dailyTimes'),
                    start_days=data.get('startDays'),
                    thumbnail_path=data.get('thumbnail', ''),
                    thumbnail_landscape_path=thumbnail_landscape,
                    thumbnail_portrait_path=thumbnail_portrait,
                    productLink=data.get('productLink', ''),
                    productTitle=data.get('productTitle', ''),
                    desc=data.get('description', ''),
                    schedule_time_str=data.get('scheduleTime', ''),
                    ai_content=data.get('aiContent', ''),
                    creation_declaration=data.get('creationDeclaration', ''),
                    risk_warning=data.get('riskWarning', ''),
                    enable_cash_activity=data.get('enableCashActivity', False),
                    supplementary_declaration=data.get('supplementaryDeclaration', ''),
                    is_draft=data.get('isDraft', False),
                    audience=data.get('audience', 'not_kids'),
                    altered_content=data.get('alteredContent', False),
                ))
            else:
                result = publish_fn(
                    title=data.get('title'),
                    files=file_list,
                    tags=data.get('tags'),
                    account_file=data.get('accountList', []),
                    category=data.get('category'),
                    enableTimer=data.get('enableTimer'),
                    videos_per_day=data.get('videosPerDay'),
                    daily_times=data.get('dailyTimes'),
                    start_days=data.get('startDays'),
                    thumbnail_path=data.get('thumbnail', ''),
                    thumbnail_landscape_path=thumbnail_landscape,
                    thumbnail_portrait_path=thumbnail_portrait,
                    productLink=data.get('productLink', ''),
                    productTitle=data.get('productTitle', ''),
                    desc=data.get('description', ''),
                    schedule_time_str=data.get('scheduleTime', ''),
                    ai_content=data.get('aiContent', ''),
                    creation_declaration=data.get('creationDeclaration', ''),
                    risk_warning=data.get('riskWarning', ''),
                    enable_cash_activity=data.get('enableCashActivity', False),
                    supplementary_declaration=data.get('supplementaryDeclaration', ''),
                    is_draft=data.get('isDraft', False),
                    audience=data.get('audience', 'not_kids'),
                    altered_content=data.get('alteredContent', False),
                )
            if not result:
                failures.append({"index": idx, "reason": "发布失败：页面未跳转"})
        except Exception as e:
            failures.append({"index": idx, "reason": str(e)})

    if failures:
        return jsonify({"code": 500, "msg": f"{len(failures)} 个发布失败", "errors": failures}), 500
    return jsonify({"code": 200, "msg": None, "data": None}), 200


# ── Publish history tracking ────────────────────────────────

def _record_publish(batch_id, detail_id, platform, account_name, account_id,
                    video_path, title, description, tags, status, started_at,
                    account_configs, video_material_id='',
                    landscape_cover_material_id='',
                    portrait_cover_material_id=''):
    """插 1 行 publish_batches（如果不存在）+ 1 行 publish_details"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            # batch 用 INSERT OR IGNORE，多次同 batchId 调用只插一次
            conn.execute(
                """INSERT OR IGNORE INTO publish_batches
                   (id, type, title, description, video_material_id,
                    landscape_cover_material_id, portrait_cover_material_id,
                    account_count, status, created_at, updated_at)
                   VALUES (?, 'video', ?, ?, ?, ?, ?, 0, 'pending', ?, ?)""",
                (batch_id, title, description, video_material_id,
                 landscape_cover_material_id, portrait_cover_material_id,
                 started_at, started_at)
            )
            conn.execute(
                """INSERT INTO publish_details
                   (id, batch_id, account_id, account_name, platform, account_configs,
                    status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (detail_id, batch_id, account_id, account_name, platform,
                 json.dumps(account_configs, ensure_ascii=False), status, started_at)
            )
    except Exception as e:
        logger.info(f"[History] 记录发布失败: {e}")


def _update_publish_result(detail_id, status, finished_at, error_message=""):
    """更新 1 行 publish_details + 聚合 publish_batches 状态"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "UPDATE publish_details SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, finished_at, error_message, detail_id)
            )
            # 拿 batch_id
            row = conn.execute(
                "SELECT batch_id FROM publish_details WHERE id=?", (detail_id,)
            ).fetchone()
            if not row:
                return
            batch_id = row[0]
            # 聚合：算 success/failed 数量，更新 batch 状态
            counts = conn.execute(
                """SELECT
                    COUNT(*) AS total,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) AS success_n,
                    SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_n
                   FROM publish_details WHERE batch_id=?""",
                (batch_id,)
            ).fetchone()
            total, succ, fail = counts[0], counts[1] or 0, counts[2] or 0
            if total == 0:
                batch_status = 'pending'
            elif fail == 0:
                batch_status = 'success'
            elif succ == 0:
                batch_status = 'failed'
            else:
                batch_status = 'partial'
            conn.execute(
                """UPDATE publish_batches
                   SET status=?, success_count=?, failed_count=?, account_count=?,
                       finished_at=?, updated_at=?
                   WHERE id=?""",
                (batch_status, succ, fail, total, finished_at, finished_at, batch_id)
            )
    except Exception as e:
        logger.info(f"[History] 更新发布结果失败: {e}")


@app.before_request
def _ensure_db():
    db_path = _get_db_path()
    need_init = False
    if not db_path.exists():
        need_init = True
    else:
        try:
            with sqlite3.connect(str(db_path)) as _c:
                _c.execute("SELECT 1 FROM user_info LIMIT 1")
        except sqlite3.OperationalError:
            need_init = True
    if need_init:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            from init_db import init_database, migrate_database
            init_database()
            migrate_database()
            logger.info(f"[DB] Initialized database at {db_path}")
        except Exception as e:
            logger.info(f"[DB] Failed to initialize database: {e}")


@app.before_request
def _before_publish():
    if request.path == '/postVideo' and request.method == 'POST':
        data = request.get_json(silent=True)
        if not data:
            return
        now = datetime.now().isoformat()
        batch_id = data.get('batchId') or str(uuid.uuid4())
        detail_id = str(uuid.uuid4())
        platform_type = data.get('type', 0)
        account_list = data.get('accountList', [])
        file_list = data.get('fileList', [])

        account_name = ''
        account_id = data.get('accountId')
        if account_list:
            account_path = account_list[0]
            account_name = data.get('accountName') or Path(account_path).stem or account_path

        # [DEBUG 2026-06-10] 详细日志：把整个请求 body 的关键字段打印出来
        logger.info(
            "[/postVideo REQUEST] batchId=%s account=%s type=%s title=%s fileList=%s videoLandscape.id=%s videoPortrait.id=%s coverLandscape.id=%s coverPortrait.id=%s creationDeclaration=%s aiContent=%s isOriginal=%s category=%s authorStatement=%s compilation=%s scheduleTime=%s enableTimer=%s tags=%s",
            batch_id, account_name, platform_type,
            data.get('title', ''),
            file_list,
            (data.get('videoLandscape') or {}).get('id') if isinstance(data.get('videoLandscape'), dict) else data.get('videoLandscape'),
            (data.get('videoPortrait') or {}).get('id') if isinstance(data.get('videoPortrait'), dict) else data.get('videoPortrait'),
            (data.get('coverLandscape') or {}).get('id') if isinstance(data.get('coverLandscape'), dict) else data.get('coverLandscape'),
            (data.get('coverPortrait') or {}).get('id') if isinstance(data.get('coverPortrait'), dict) else data.get('coverPortrait'),
            data.get('creationDeclaration', ''),
            data.get('aiContent', ''),
            data.get('isOriginal', ''),
            data.get('category', ''),  # 新增：B 站分区字段（platformSettings.zone || 兜底）
            data.get('authorStatement', ''),  # 支付宝作者声明(必填)
            data.get('compilation', ''),  # 支付宝合集(名字)
            data.get('scheduleTime', ''),  # 定时发布
            data.get('enableTimer', ''),
            data.get('tags', ''),
        )

        # account_configs 存：除了 fileList/accountList/type/thumbnail/batchId/accountId/accountName 之外的所有字段
        # 注意：videoMaterialId/landscapeCoverMaterialId/portraitCoverMaterialId 既写 batch 列，也写进 JSON（让 JSON 自包含）
        # 注意：thumbnailLandscape/thumbnailPortrait（抽帧封面路径）也存进 JSON，
        # 供 /api/v2/history 的 _resolve_cover_url 在 material_id 缺失时回退使用
        # 注意：scheduleTime 现在也存进 JSON（spec §2.2 视频结构要求），
        # publish_batches.schedule_time 仍是 batch 级聚合字段，两者并存不冲突
        excluded = {'fileList', 'accountList', 'type', 'thumbnail',
                    'batchId',
                    'accountId', 'accountName'}
        account_configs = {k: v for k, v in data.items() if k not in excluded}

        _record_publish(
            batch_id=batch_id,
            detail_id=detail_id,
            platform=PLATFORM_MAP.get(platform_type, '未知'),
            account_id=account_id,
            account_name=account_name,
            video_path=file_list[0] if file_list else '',
            title=data.get('title', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            status='running',
            started_at=now,
            account_configs=account_configs,
            video_material_id=data.get('videoMaterialId', ''),
            landscape_cover_material_id=data.get('landscapeCoverMaterialId', ''),
            portrait_cover_material_id=data.get('portraitCoverMaterialId', ''),
        )
        g.publish_detail_id = detail_id
        g.publish_start_time = now


@app.after_request
def _after_publish(response):
    if request.path == '/postVideo' and hasattr(g, 'publish_detail_id'):
        now = datetime.now().isoformat()
        if response.status_code == 200:
            try:
                resp_data = json.loads(response.get_data(as_text=True))
                if resp_data.get('code') == 200:
                    _update_publish_result(g.publish_detail_id, 'success', now)
                else:
                    _update_publish_result(g.publish_detail_id, 'failed', now, resp_data.get('msg', ''))
            except (json.JSONDecodeError, ValueError):
                _update_publish_result(g.publish_detail_id, 'success', now)
        else:
            error_msg = ''
            try:
                resp_data = json.loads(response.get_data(as_text=True))
                error_msg = resp_data.get('msg', '')
            except (json.JSONDecodeError, ValueError):
                error_msg = f'HTTP {response.status_code}'
            _update_publish_result(g.publish_detail_id, 'failed', now, error_msg)
    return response


# ── Health / diagnostics ────────────────────────────────────

@app.route("/api/health", methods=['GET'])
def health_check():
    import sqlite3 as _sqlite
    diag = {
        "sau_data_dir": os.environ.get("SAU_DATA_DIR"),
        "base_dir": str(BASE_DIR),
        "db_path": str(_get_db_path()),
        "db_exists": _get_db_path().exists(),
        "python": sys.executable,
        "sys_prefix": sys.prefix,
        "sys_base_prefix": sys.base_prefix,
    }
    try:
        with _sqlite.connect(str(_get_db_path())) as _conn:
            count = _conn.execute("SELECT COUNT(*) FROM user_info").fetchone()[0]
            diag["db_user_count"] = count
            diag["db_ok"] = True
    except Exception as e:
        diag["db_ok"] = False
        diag["db_error"] = str(e)
    return jsonify(diag)


# ── 反馈系统代理（HMAC 签名由后端完成，前端永不接触 app_secret）──


def _feedback_sign(timestamp_ms: str, app_key: str = None, app_secret: str = None) -> str:
    if app_key is None:
        app_key = FEEDBACK_APP_KEY
    if app_secret is None:
        app_secret = FEEDBACK_APP_SECRET
    msg = f"{app_key}{timestamp_ms}{app_secret}".encode('utf-8')
    return hmac.new(app_secret.encode('utf-8'), msg, hashlib.sha256).hexdigest()


def _feedback_headers() -> dict:
    """生成带 HMAC 签名的反馈系统请求头。"""
    ts = str(int(time.time() * 1000))
    return {
        'X-App-Key': FEEDBACK_APP_KEY,
        'X-Timestamp': ts,
        'X-Sign': _feedback_sign(ts),
    }


def _get_feedback_email() -> str:
    """从 settings 表读 feedbackEmail（用户全局邮箱）。空字符串表示未配置。"""
    val = read_settings().get('feedbackEmail')
    return (val or '').strip() if isinstance(val, str) else ''


@app.route('/api/feedback/list', methods=['GET'])
def feedback_list():
    """状态筛选：全部 / 待确认 / 处理中 / 已完成 / 已拒绝
    - 不传 status + 不传 include_all → 仅 status 1+2（默认）
    - status=1/2/3/4 → 仅对应状态
    - include_all=true → 全部
    """
    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
    except ValueError:
        return jsonify({'code': 400, 'message': 'page / page_size 必须是整数', 'data': None}), 400

    status_str = request.args.get('status', '').strip()
    include_all = request.args.get('include_all', '').lower() == 'true'

    params = {'page': page, 'page_size': page_size}
    if status_str:
        try:
            params['status'] = int(status_str)
        except ValueError:
            return jsonify({'code': 400, 'message': 'status 必须是整数 (1-4)', 'data': None}), 400
    elif include_all:
        params['include_all'] = 'true'

    # 从 settings 表读用户邮箱，作为 metoo 计算依据
    viewer_email = _get_feedback_email()
    if viewer_email:
        params['email'] = viewer_email

    try:
        r = _requests.get(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            params=params,
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502

    # attachment.file_url 从相对路径改写为绝对 URL
    for item in data.get('data', {}).get('list', []):
        for att in item.get('attachments') or []:
            if att.get('file_url', '').startswith('/'):
                att['file_url'] = FEEDBACK_API_BASE_URL + att['file_url']

    return jsonify(data)


@app.route('/api/feedback/submit', methods=['POST'])
def feedback_submit():
    content = request.form.get('content', '').strip()
    # 邮箱优先取表单（覆盖场景），否则从 settings 读
    email = request.form.get('email', '').strip() or _get_feedback_email()
    if not email or not content:
        return jsonify({'code': 400, 'message': '邮箱和内容必填；如未配置邮箱请先在设置页填写', 'data': None}), 400

    files = []
    for f in request.files.getlist('files'):
        files.append(('files', (f.filename, f.stream, f.mimetype)))

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback",
            data={'email': email, 'content': content},
            files=files,
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502


@app.route('/api/feedback/vote', methods=['POST'])
def feedback_vote():
    body = request.get_json(silent=True) or {}
    fb_id = body.get('id')
    # 邮箱优先取 body（允许前端临时用别的身份），否则从 settings 读
    email = (body.get('email') or '').strip() or _get_feedback_email()
    if not fb_id or not email:
        return jsonify({'code': 400, 'message': 'id 和 email 必填；如未配置邮箱请先在设置页填写', 'data': None}), 400

    try:
        r = _requests.post(
            f"{FEEDBACK_API_BASE_URL}/api/v1/feedback/{fb_id}/vote",
            json={'email': email},
            headers=_feedback_headers(),
            timeout=FEEDBACK_API_TIMEOUT,
        )
        return (r.json(), r.status_code)
    except _requests.RequestException as e:
        return jsonify({'code': 502, 'message': f'反馈系统不可达: {e}', 'data': None}), 502


# ── Server entry ────────────────────────────────────────────

def find_available_port(start_port=5409, max_attempts=10):
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")


if __name__ == "__main__":
    import socket

    logger.info("[Startup] Initializing database...")
    from init_db import init_database, migrate_database
    init_database()
    migrate_database()
    logger.info("[Startup] Database initialized OK")

    try:
        import sqlite3 as _sqlite
        _test_path = _get_db_path()
        logger.info(f"[Startup] DB path: {_test_path} (exists={_test_path.exists()})")
        with _sqlite.connect(str(_test_path)) as _conn:
            _conn.execute("SELECT 1 FROM user_info LIMIT 1")
        logger.info("[Startup] DB verification OK")
    except Exception as _e:
        logger.info(f"[Startup] DB verification FAILED: {_e}")
        logger.info(f"[Startup] SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

    # 启动后台任务：补全存量视频素材 duration=0 的数据
    # （草稿/历史恢复走 DB 直读，绕过了「素材库选中→probe」，
    #  导致历史 duration=0 的数据漏识别，发布校验被跳过）
    try:
        from services.duration_repair import start_repair_in_background
        start_repair_in_background()
    except Exception as _e:
        logger.warning("[Startup] 时长补全任务启动失败（不影响主服务）: %s", _e)

    port = int(os.environ.get("SAU_PORT", "5409"))
    if port == 5409:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", port))
        except OSError:
            port = find_available_port(5409 + 1)
            logger.info(f"[Startup] Port 5409 in use, using port {port}")
    logger.info(f"[Startup] Starting Waitress server on port {port}")
    from waitress import serve
    os.environ["SAU_PORT"] = str(port)
    serve(app, host="0.0.0.0", port=port)
