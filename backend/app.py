import asyncio
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from queue import Queue

from flask import Flask, Response, g, jsonify, request, send_from_directory
from flask_cors import CORS

logger = logging.getLogger(__name__)

logger.info(f"[Startup] Python {sys.version} starting...")
logger.info(f"[Startup] Script: {__file__}")
logger.info(f"[Startup] SAU_PORT={os.environ.get('SAU_PORT')}, SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
    logger.info(f"[Startup] Added backend dir to sys.path: {BACKEND_DIR}")

from conf import BASE_DIR
from impl.registry import get_platform

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

# SSE login status queues (keyed by account id)
active_queues: dict[str, Queue] = {}


def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
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


_VIDEOFILE_DIR = None

def _get_videofile_dir():
    global _VIDEOFILE_DIR
    if _VIDEOFILE_DIR is None:
        _VIDEOFILE_DIR = str(BASE_DIR / "videoFile")
        Path(_VIDEOFILE_DIR).mkdir(parents=True, exist_ok=True)
    return _VIDEOFILE_DIR


@app.route('/<path:filename>')
def serve_videofile(filename):
    """Serve files from videoFile directory (covers, etc.)"""
    if '..' in filename or filename.startswith('/'):
        return jsonify({"code": 400, "msg": "Invalid filename"}), 400
    vf_dir = _get_videofile_dir()
    fpath = Path(vf_dir) / filename
    if fpath.exists():
        return send_from_directory(vf_dir, filename)
    return jsonify({"code": 404, "msg": "File not found"}), 404


# ── Helper ──────────────────────────────────────────────────

def _get_db_path():
    if data_dir := os.environ.get("SAU_DATA_DIR"):
        return Path(data_dir) / "db" / "database.db"
    return Path(__file__).parent.parent / "data" / "db" / "database.db"


DB_PATH = _get_db_path()
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube", 9: "腾讯视频", 10: "爱奇艺"}


def _get_account_record(account_id):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ── File management ─────────────────────────────────────────

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"code": 400, "data": None, "msg": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"code": 400, "data": None, "msg": "No selected file"}), 400
    try:
        uuid_v1 = uuid.uuid1()
        final_filename = f"{uuid_v1}_{file.filename}"
        filepath = Path(BASE_DIR / "videoFile" / final_filename)
        file.save(filepath)

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                'INSERT INTO file_records (filename, filesize, file_path) VALUES (?, ?, ?)',
                (file.filename, round(float(os.path.getsize(filepath)) / (1024 * 1024), 2), final_filename)
            )

        return jsonify({
            "code": 200, "msg": "File uploaded successfully",
            "data": {"filename": file.filename, "filepath": final_filename}
        }), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500


@app.route('/getFile', methods=['GET'])
def get_file():
    filename = request.args.get('filename')
    if not filename:
        return jsonify({"code": 400, "msg": "filename is required", "data": None}), 400
    if '..' in filename or filename.startswith('/'):
        return jsonify({"code": 400, "msg": "Invalid filename", "data": None}), 400
    return send_from_directory(str(Path(BASE_DIR / "videoFile")), filename)


@app.route('/uploadSave', methods=['POST'])
def upload_save():
    if 'file' not in request.files:
        return jsonify({"code": 400, "data": None, "msg": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"code": 400, "data": None, "msg": "No selected file"}), 400

    custom_filename = request.form.get('filename', None)
    if custom_filename:
        filename = custom_filename + "." + file.filename.split('.')[-1]
    else:
        filename = file.filename

    try:
        uuid_v1 = uuid.uuid1()
        final_filename = f"{uuid_v1}_{filename}"
        filepath = Path(BASE_DIR / "videoFile" / final_filename)
        file.save(filepath)

        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                'INSERT INTO file_records (filename, filesize, file_path) VALUES (?, ?, ?)',
                (filename, round(float(os.path.getsize(filepath)) / (1024 * 1024), 2), final_filename)
            )

        return jsonify({
            "code": 200, "msg": "File uploaded and saved successfully",
            "data": {"filename": filename, "filepath": final_filename}
        }), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"upload failed: {e}", "data": None}), 500


@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_records")
            rows = cursor.fetchall()

            data = []
            for row in rows:
                row_dict = dict(row)
                if row_dict.get('file_path'):
                    file_path_parts = row_dict['file_path'].split('_', 1)
                    row_dict['uuid'] = file_path_parts[0] if file_path_parts else ''
                else:
                    row_dict['uuid'] = ''
                data.append(row_dict)

        return jsonify({"code": 200, "msg": "success", "data": data}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": "get file failed!", "data": None}), 500


@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')
    if not file_id or not file_id.isdigit():
        return jsonify({"code": 400, "msg": "Invalid or missing file ID", "data": None}), 400

    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({"code": 404, "msg": "File not found", "data": None}), 404

            record = dict(record)
            file_path = Path(BASE_DIR / "videoFile" / record['file_path'])
            if file_path.exists():
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.info(f"[WARN] 删除实际文件失败: {e}")

            cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()

        return jsonify({
            "code": 200, "msg": "File deleted successfully",
            "data": {"id": record['id'], "filename": record['filename']}
        }), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": "delete failed!", "data": None}), 500


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
    if not type_str or not id_str:
        return jsonify({"code": 400, "msg": "缺少 type 或 id"}), 400

    platform = get_platform(int(type_str))
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    status_queue = Queue()
    active_queues[id_str] = status_queue

    def _cleanup():
        active_queues.pop(id_str, None)

    thread = threading.Thread(
        target=lambda: asyncio.run(platform.login(id_str, status_queue)),
        daemon=True
    )
    thread.start()

    response = Response(sse_stream(status_queue), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    response.headers['Content-Type'] = 'text/event-stream'
    response.call_on_close(_cleanup)
    return response


@app.route('/postVideo', methods=['POST'])
def postVideo():
    data = request.get_json()
    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400

    platform = get_platform(data.get('type'))
    if not platform:
        return jsonify({"code": 400, "msg": "不支持的平台类型"}), 400

    try:
        # Some platforms have sync publish_video, others async.
        # asyncio.run() only works with coroutines — calling it on a
        # sync function that already uses asyncio.run() internally
        # would pass a bool to asyncio.run() and throw.
        publish_fn = platform.publish_video
        if asyncio.iscoroutinefunction(publish_fn):
            result = asyncio.run(publish_fn(
                title=data.get('title'),
                files=data.get('fileList', []),
                tags=data.get('tags'),
                account_file=data.get('accountList', []),
                category=data.get('category'),
                enableTimer=data.get('enableTimer'),
                videos_per_day=data.get('videosPerDay'),
                daily_times=data.get('dailyTimes'),
                start_days=data.get('startDays'),
                thumbnail_path=data.get('thumbnail', ''),
                thumbnail_landscape_path=data.get('thumbnailLandscape', ''),
                thumbnail_portrait_path=data.get('thumbnailPortrait', ''),
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
                files=data.get('fileList', []),
                tags=data.get('tags'),
                account_file=data.get('accountList', []),
                category=data.get('category'),
                enableTimer=data.get('enableTimer'),
                videos_per_day=data.get('videosPerDay'),
                daily_times=data.get('dailyTimes'),
                start_days=data.get('startDays'),
                thumbnail_path=data.get('thumbnail', ''),
                thumbnail_landscape_path=data.get('thumbnailLandscape', ''),
                thumbnail_portrait_path=data.get('thumbnailPortrait', ''),
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

        try:
            publish_fn = platform.publish_video
            if asyncio.iscoroutinefunction(publish_fn):
                result = asyncio.run(publish_fn(
                    title=data.get('title'),
                    files=data.get('fileList', []),
                    tags=data.get('tags'),
                    account_file=data.get('accountList', []),
                    category=data.get('category'),
                    enableTimer=data.get('enableTimer'),
                    videos_per_day=data.get('videosPerDay'),
                    daily_times=data.get('dailyTimes'),
                    start_days=data.get('startDays'),
                    thumbnail_path=data.get('thumbnail', ''),
                    thumbnail_landscape_path=data.get('thumbnailLandscape', ''),
                    thumbnail_portrait_path=data.get('thumbnailPortrait', ''),
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
                    files=data.get('fileList', []),
                    tags=data.get('tags'),
                    account_file=data.get('accountList', []),
                    category=data.get('category'),
                    enableTimer=data.get('enableTimer'),
                    videos_per_day=data.get('videosPerDay'),
                    daily_times=data.get('dailyTimes'),
                    start_days=data.get('startDays'),
                    thumbnail_path=data.get('thumbnail', ''),
                    thumbnail_landscape_path=data.get('thumbnailLandscape', ''),
                    thumbnail_portrait_path=data.get('thumbnailPortrait', ''),
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


# ── Settings (file-based, for proxy etc.) ───────────────────

SETTINGS_FILE = BASE_DIR / "settings.json"


def _read_settings():
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _write_settings(data):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route('/api/v2/settings', methods=['GET'])
def api_get_settings():
    return jsonify({"code": 200, "msg": None, "data": _read_settings()})


@app.route('/api/v2/settings', methods=['PUT'])
def api_update_settings():
    data = request.get_json(force=True)
    current = _read_settings()
    current.update(data)
    _write_settings(current)
    return jsonify({"code": 200, "msg": "保存成功", "data": current})


# ── Publish history tracking ────────────────────────────────

def _record_publish(task_id, platform, account_name, video_path, title, description, tags, status, started_at, finished_at=None, error_message=""):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """INSERT INTO publish_tasks
                   (id, platform, account_name, video_path, title, description,
                    tags, status, retry_count, max_retries, error_message,
                    publish_url, created_at, started_at, finished_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 3, ?, '', ?, ?, ?)""",
                (task_id, platform, account_name, video_path, title, description,
                 json.dumps(tags, ensure_ascii=False), status, error_message,
                 started_at, started_at, finished_at)
            )
    except Exception as e:
        logger.info(f"[History] 记录发布失败: {e}")


def _update_publish_result(task_id, status, finished_at, error_message=""):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                "UPDATE publish_tasks SET status=?, finished_at=?, error_message=? WHERE id=?",
                (status, finished_at, error_message, task_id)
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
        task_id = str(uuid.uuid4())
        platform_type = data.get('type', 0)
        account_list = data.get('accountList', [])
        file_list = data.get('fileList', [])

        account_name = ''
        if account_list:
            account_path = account_list[0]
            account_name = Path(account_path).stem or account_path

        _record_publish(
            task_id=task_id,
            platform=PLATFORM_MAP.get(platform_type, '未知'),
            account_name=account_name,
            video_path=file_list[0] if file_list else '',
            title=data.get('title', ''),
            description=data.get('description', ''),
            tags=data.get('tags', []),
            status='running',
            started_at=now,
        )
        g.publish_task_id = task_id
        g.publish_start_time = now


@app.after_request
def _after_publish(response):
    if request.path == '/postVideo' and hasattr(g, 'publish_task_id'):
        now = datetime.now().isoformat()
        if response.status_code == 200:
            try:
                resp_data = json.loads(response.get_data(as_text=True))
                if resp_data.get('code') == 200:
                    _update_publish_result(g.publish_task_id, 'success', now)
                else:
                    _update_publish_result(g.publish_task_id, 'failed', now, resp_data.get('msg', ''))
            except (json.JSONDecodeError, ValueError):
                _update_publish_result(g.publish_task_id, 'success', now)
        else:
            error_msg = ''
            try:
                resp_data = json.loads(response.get_data(as_text=True))
                error_msg = resp_data.get('msg', '')
            except (json.JSONDecodeError, ValueError):
                error_msg = f'HTTP {response.status_code}'
            _update_publish_result(g.publish_task_id, 'failed', now, error_msg)
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

    port = int(os.environ.get("SAU_PORT", "5409"))
    if port == 5409:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
        except OSError:
            port = find_available_port(5409 + 1)
            logger.info(f"[Startup] Port 5409 in use, using port {port}")
    logger.info(f"[Startup] Starting Waitress server on port {port}")
    from waitress import serve
    os.environ["SAU_PORT"] = str(port)
    serve(app, host="0.0.0.0", port=port)
