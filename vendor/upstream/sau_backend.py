import asyncio
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from queue import Queue
from flask_cors import CORS
from myUtils.auth import check_cookie
from flask import Flask, request, jsonify, Response, render_template, send_from_directory
import json as json_module

from conf import BASE_DIR
from myUtils.login import get_tencent_cookie, douyin_cookie_gen, get_ks_cookie, xiaohongshu_cookie_gen, sync_account_profile, bilibili_cookie_gen
from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs, post_video_bilibili, post_video_baijiahao, post_video_tiktok, post_video_youtube
from uploader.baijiahao_uploader.main import baijiahao_cookie_gen_wrapper as baijiahao_cookie_gen
from uploader.tk_uploader.main_chrome import get_tiktok_cookie_wrapper as get_tiktok_cookie
from uploader.youtube_uploader.main import youtube_cookie_gen

active_queues = {}
app = Flask(__name__)

#允许所有来源跨域访问
CORS(app)

# 限制上传文件大小为1GB
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024

# 获取当前目录（假设 index.html 和 assets 在这里）
current_dir = os.path.dirname(os.path.abspath(__file__))

# 处理所有静态资源请求（未来打包用）
@app.route('/assets/<filename>')
def custom_static(filename):
    return send_from_directory(os.path.join(current_dir, 'assets'), filename)

# 处理 favicon.ico 静态资源（未来打包用）
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

# （未来打包用）
@app.route('/')
def index():  # put application's code here
    return send_from_directory(current_dir, 'index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400
    try:
        uuid_v1 = uuid.uuid1()
        final_filename = f"{uuid_v1}_{file.filename}"
        filepath = Path(BASE_DIR / "videoFile" / final_filename)
        file.save(filepath)

        # 写入素材库
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO file_records (filename, filesize, file_path) VALUES (?, ?, ?)',
                (file.filename, round(float(os.path.getsize(filepath)) / (1024 * 1024), 2), final_filename)
            )
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "File uploaded successfully",
            "data": {
                "filename": file.filename,
                "filepath": final_filename,
            }
        }), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e), "data": None}), 500

@app.route('/getFile', methods=['GET'])
def get_file():
    # 获取 filename 参数
    filename = request.args.get('filename')

    if not filename:
        return jsonify({"code": 400, "msg": "filename is required", "data": None}), 400

    # 防止路径穿越攻击
    if '..' in filename or filename.startswith('/'):
        return jsonify({"code": 400, "msg": "Invalid filename", "data": None}), 400

    # 拼接完整路径
    file_path = str(Path(BASE_DIR / "videoFile"))

    # 返回文件
    return send_from_directory(file_path,filename)


@app.route('/uploadSave', methods=['POST'])
def upload_save():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400

    # 获取表单中的自定义文件名（可选）
    custom_filename = request.form.get('filename', None)
    if custom_filename:
        filename = custom_filename + "." + file.filename.split('.')[-1]
    else:
        filename = file.filename

    try:
        # 生成 UUID v1
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")

        # 构造文件名和路径
        final_filename = f"{uuid_v1}_{filename}"
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{filename}")

        # 保存文件
        file.save(filepath)

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO file_records (filename, filesize, file_path)
            VALUES (?, ?, ?)
                                ''', (filename, round(float(os.path.getsize(filepath)) / (1024 * 1024),2), final_filename))
            conn.commit()
            print("✅ 上传文件已记录")

        return jsonify({
            "code": 200,
            "msg": "File uploaded and saved successfully",
            "data": {
                "filename": filename,
                "filepath": final_filename
            }
        }), 200

    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({
            "code": 500,
            "msg": f"upload failed: {e}",
            "data": None
        }), 500

@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        # 使用 with 自动管理数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row  # 允许通过列名访问结果
            cursor = conn.cursor()

            # 查询所有记录
            cursor.execute("SELECT * FROM file_records")
            rows = cursor.fetchall()

            # 将结果转为字典列表，并提取UUID
            data = []
            for row in rows:
                row_dict = dict(row)
                # 从 file_path 中提取 UUID (文件名的第一部分，下划线前)
                if row_dict.get('file_path'):
                    file_path_parts = row_dict['file_path'].split('_', 1)  # 只分割第一个下划线
                    if len(file_path_parts) > 0:
                        row_dict['uuid'] = file_path_parts[0]  # UUID 部分
                    else:
                        row_dict['uuid'] = ''
                else:
                    row_dict['uuid'] = ''
                data.append(row_dict)

            return jsonify({
                "code": 200,
                "msg": "success",
                "data": data
            }), 200
    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("get file failed!"),
            "data": None
        }), 500


@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    """快速获取所有账号信息，不进行cookie验证"""
    try:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM user_info''')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            print("\n📋 当前数据表内容（快速获取）：")
            for row in rows:
                print(row)

            return jsonify(
                {
                    "code": 200,
                    "msg": None,
                    "data": rows_list
                }), 200
    except Exception as e:
        print(f"获取账号列表时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"获取账号列表失败: {str(e)}",
            "data": None
        }), 500


@app.route("/getValidAccounts",methods=['GET'])
def getValidAccounts():
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT * FROM user_info''')
        rows = cursor.fetchall()
        rows_list = [list(row) for row in rows]
        print("\n📋 当前数据表内容：")
        for row in rows:
            print(row)
        for row in rows_list:
            flag = asyncio.run(check_cookie(row[1], row[2]))
            if not flag:
                row[4] = 0
                cursor.execute('''
                UPDATE user_info
                SET status = ?
                WHERE id = ?
                ''', (0, row[0]))
                conn.commit()
                print("✅ 用户状态已更新")
        for row in rows:
            print(row)
        return jsonify({
            "code": 200,
            "msg": None,
            "data": rows_list
        }), 200

@app.route('/checkAccount', methods=['GET'])
def check_account():
    """检查单个账号的 cookie 是否有效"""
    account_id = request.args.get('id')
    if not account_id or not account_id.isdigit():
        return jsonify({"code": 400, "msg": "无效的账号ID"}), 400

    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM user_info WHERE id = ?', (int(account_id),))
        row = cursor.fetchone()
        if not row:
            return jsonify({"code": 404, "msg": "账号不存在"}), 404

        row_list = list(row)
        valid = asyncio.run(check_cookie(row[1], row[2]))
        new_status = 1 if valid else 0
        row_list[4] = new_status
        cursor.execute('UPDATE user_info SET status = ? WHERE id = ?', (new_status, row[0]))
        conn.commit()

    msg = "Cookie 有效" if valid else "Cookie 已失效，请重新登录"
    return jsonify({"code": 200, "msg": msg, "data": {"id": row[0], "status": new_status, "valid": valid}})

@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')

    if not file_id or not file_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing file ID",
            "data": None
        }), 400

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "File not found",
                    "data": None
                }), 404

            record = dict(record)

            # 获取文件路径并删除实际文件
            file_path = Path(BASE_DIR / "videoFile" / record['file_path'])
            if file_path.exists():
                try:
                    file_path.unlink()  # 删除文件
                    print(f"✅ 实际文件已删除: {file_path}")
                except Exception as e:
                    print(f"⚠️ 删除实际文件失败: {e}")
                    # 即使删除文件失败，也要继续删除数据库记录，避免数据不一致
            else:
                print(f"⚠️ 实际文件不存在: {file_path}")

            # 删除数据库记录
            cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "File deleted successfully",
            "data": {
                "id": record['id'],
                "filename": record['filename']
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500

@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = request.args.get('id')

    if not account_id or not account_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing account ID",
            "data": None
        }), 400

    account_id = int(account_id)

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "account not found",
                    "data": None
                }), 404

            record = dict(record)

            # 删除关联的cookie文件
            if record.get('filePath'):
                cookie_file_path = Path(BASE_DIR / "cookiesFile" / record['filePath'])
                if cookie_file_path.exists():
                    try:
                        cookie_file_path.unlink()
                        print(f"✅ Cookie文件已删除: {cookie_file_path}")
                    except Exception as e:
                        print(f"⚠️ 删除Cookie文件失败: {e}")

            # 删除数据库记录
            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account deleted successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": f"delete failed: {str(e)}",
            "data": None
        }), 500


# 同步账号资料（头像+昵称）
@app.route('/syncProfile', methods=['POST'])
def sync_profile():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID", "data": None}), 400

    try:
        import sys
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

            record = dict(row)
            platform_type = record['type']
            cookie_file = record['filePath']

        print(f"[SYNC] START platform={platform_type} cookie_file={cookie_file}", flush=True)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        name, avatar = loop.run_until_complete(sync_account_profile(platform_type, cookie_file))
        loop.close()
        print(f"[SYNC] RESULT platform={platform_type} name={name!r} avatar={avatar[:80] if avatar else 'None'}", flush=True)

        if name or avatar:
            with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
                cursor = conn.cursor()
                if name:
                    cursor.execute('UPDATE user_info SET userName = ?, avatar = ? WHERE id = ?',
                                   (name, avatar, account_id))
                else:
                    cursor.execute('UPDATE user_info SET avatar = ? WHERE id = ?',
                                   (avatar, account_id))
                conn.commit()

        return jsonify({
            "code": 200,
            "msg": "同步成功",
            "data": {"name": name, "avatar": avatar}
        }), 200

    except Exception as e:
        print(f"同步资料失败: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"同步失败: {str(e)}",
            "data": None
        }), 500


# 打开创作中心（用 Patchright 启动带cookie的浏览器）
@app.route('/openCreatorCenter', methods=['POST'])
def open_creator_center():
    account_id = request.json.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID"}), 400

    creator_urls = {
        1: "https://creator.xiaohongshu.com/",
        2: "https://channels.weixin.qq.com/platform",
        3: "https://creator.douyin.com/",
        4: "https://cp.kuaishou.com/article/publish/video",
        5: "https://member.bilibili.com/platform/upload-manager/article",
        6: "https://baijiahao.baidu.com/",
        7: "https://www.tiktok.com/tiktokstudio/upload?lang=en",
        8: "https://studio.youtube.com/",
    }

    try:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({"code": 404, "msg": "账号不存在"}), 404

            record = dict(row)
            platform_type = record['type']
            cookie_file = record['filePath']

        url = creator_urls.get(platform_type)
        if not url:
            return jsonify({"code": 400, "msg": "不支持该平台"}), 400

        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        def launch_browser():
            from patchright.sync_api import sync_playwright
            from myUtils.browser import create_browser_sync, create_context_sync
            pw = sync_playwright().start()
            browser = create_browser_sync(pw, headless=False)
            context = create_context_sync(browser, storage_state=cookie_path)
            page = context.new_page()
            page.goto(url)
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
                pw.stop()

        thread = threading.Thread(target=launch_browser, daemon=True)
        thread.start()

        return jsonify({"code": 200, "msg": "正在打开创作中心"}), 200

    except Exception as e:
        print(f"打开创作中心失败: {str(e)}")
        return jsonify({"code": 500, "msg": f"打开失败: {str(e)}"}), 500


# SSE 登录接口
@app.route('/login')
def login():
    # 1 小红书 2 视频号 3 抖音 4 快手
    type = request.args.get('type')
    # 账号名
    id = request.args.get('id')

    # 模拟一个用于异步通信的队列
    status_queue = Queue()
    active_queues[id] = status_queue

    def on_close():
        print(f"清理队列: {id}")
        del active_queues[id]
    # 启动异步任务线程
    thread = threading.Thread(target=run_async_function, args=(type,id,status_queue), daemon=True)
    thread.start()
    response = Response(sse_stream(status_queue,), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # 关键：禁用 Nginx 缓冲
    response.headers['Content-Type'] = 'text/event-stream'
    return response

@app.route('/postVideo', methods=['POST'])
def postVideo():
    # 获取JSON数据
    data = request.get_json()

    if not data:
        return jsonify({"code": 400, "msg": "请求数据不能为空", "data": None}), 400

    # 从JSON数据中提取fileList和accountList
    file_list = data.get('fileList', [])
    account_list = data.get('accountList', [])
    type = data.get('type')
    title = data.get('title')
    tags = data.get('tags')
    category = data.get('category')
    enableTimer = data.get('enableTimer')
    schedule_time_str = data.get('scheduleTime', '')
    if category == 0:
        category = None
    productLink = data.get('productLink', '')
    productTitle = data.get('productTitle', '')
    thumbnail_path = data.get('thumbnail', '')
    thumbnail_landscape_path = data.get('thumbnailLandscape', '')
    thumbnail_portrait_path = data.get('thumbnailPortrait', '')
    is_draft = data.get('isDraft', False)  # 新增参数：是否保存为草稿
    desc = data.get('description', '')  # 视频描述
    ai_content = data.get('aiContent', '')  # 声明与权益
    creation_declaration = data.get('creationDeclaration', '')  # 创作声明

    videos_per_day = data.get('videosPerDay')
    daily_times = data.get('dailyTimes')
    start_days = data.get('startDays')

    # 参数校验
    if not file_list:
        return jsonify({"code": 400, "msg": "文件列表不能为空", "data": None}), 400
    if not account_list:
        return jsonify({"code": 400, "msg": "账号列表不能为空", "data": None}), 400
    if not type:
        return jsonify({"code": 400, "msg": "平台类型不能为空", "data": None}), 400
    if not title:
        return jsonify({"code": 400, "msg": "标题不能为空", "data": None}), 400

    # 打印获取到的数据（仅作为示例）
    print("File List:", file_list)
    print("Account List:", account_list)

    try:
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, thumbnail_path=thumbnail_portrait_path or thumbnail_path, desc=desc, schedule_time_str=schedule_time_str, ai_content=ai_content)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, is_draft, thumbnail_path=thumbnail_portrait_path or thumbnail_path, desc=desc, schedule_time_str=schedule_time_str)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnail_landscape_path=thumbnail_landscape_path, thumbnail_portrait_path=thumbnail_portrait_path, productLink=productLink, productTitle=productTitle, desc=desc, schedule_time_str=schedule_time_str, ai_content=ai_content)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnail_path=thumbnail_landscape_path or thumbnail_path, desc=desc, schedule_time_str=schedule_time_str, author_declaration=ai_content)
            case 5:
                post_video_bilibili(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, desc=desc, thumbnailLandscape=thumbnail_landscape_path, schedule_time_str=schedule_time_str, ai_content=ai_content, creation_declaration=creation_declaration)
            case 6:
                post_video_baijiahao(title, file_list, tags, account_list, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnail_landscape_path=thumbnail_landscape_path, thumbnail_portrait_path=thumbnail_portrait_path,
                          desc=desc, schedule_time_str=schedule_time_str,
                          creation_declaration=creation_declaration, supplementary_declaration=data.get('supplementaryDeclaration', ''),
                          ai_content=ai_content)
            case 7:
                post_video_tiktok(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, schedule_time_str=schedule_time_str)
            case 8:
                post_video_youtube(title, file_list, tags, account_list,
                          enableTimer=enableTimer, videos_per_day=videos_per_day, daily_times=daily_times,
                          start_days=start_days, schedule_time_str=schedule_time_str,
                          audience=data.get('audience', 'not_kids'),
                          altered_content=data.get('alteredContent', False),
                          desc=desc, thumbnail_path=thumbnail_landscape_path or thumbnail_path)
            case _:
                return jsonify({"code": 400, "msg": f"不支持的平台类型: {type}", "data": None}), 400

        # 返回响应给客户端
        return jsonify(
            {
                "code": 200,
                "msg": "发布任务已提交",
                "data": None
            }), 200
    except Exception as e:
        print(f"发布视频时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"发布失败: {str(e)}",
            "data": None
        }), 500


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    # 获取JSON数据
    data = request.get_json()

    # 从JSON数据中提取 type 和 userName
    user_id = data.get('id')
    type = data.get('type')
    userName = data.get('userName')
    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 更新数据库记录
            cursor.execute('''
                           UPDATE user_info
                           SET type     = ?,
                               userName = ?
                           WHERE id = ?;
                           ''', (type, userName, user_id))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account update successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("update failed!"),
            "data": None
        }), 500

@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()

    if not isinstance(data_list, list):
        return jsonify({"code": 400, "msg": "Expected a JSON array", "data": None}), 400
    for data in data_list:
        # 从JSON数据中提取fileList和accountList
        file_list = data.get('fileList', [])
        account_list = data.get('accountList', [])
        type = data.get('type')
        title = data.get('title')
        tags = data.get('tags')
        category = data.get('category')
        enableTimer = data.get('enableTimer')
        schedule_time_str = data.get('scheduleTime', '')
        if category == 0:
            category = None
        productLink = data.get('productLink', '')
        productTitle = data.get('productTitle', '')
        is_draft = data.get('isDraft', False)
        desc = data.get('description', '')
        ai_content = data.get('aiContent', '')
        thumbnail_landscape_path = data.get('thumbnailLandscape', '')
        thumbnail_portrait_path = data.get('thumbnailPortrait', '')
        creation_declaration = data.get('creationDeclaration', '')

        videos_per_day = data.get('videosPerDay')
        daily_times = data.get('dailyTimes')
        start_days = data.get('startDays')
        # 打印获取到的数据（仅作为示例）
        print("File List:", file_list)
        print("Account List:", account_list)
        match type:
            case 1:
                post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                               start_days, schedule_time_str=schedule_time_str)
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days, is_draft, schedule_time_str=schedule_time_str)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, productLink, productTitle, schedule_time_str=schedule_time_str)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, schedule_time_str=schedule_time_str)
            case 5:
                post_video_bilibili(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnailLandscape=thumbnail_landscape_path, thumbnailPortrait=thumbnail_portrait_path, schedule_time_str=schedule_time_str)
            case 6:
                post_video_baijiahao(title, file_list, tags, account_list, enableTimer, videos_per_day, daily_times,
                          start_days, thumbnail_landscape_path=thumbnail_landscape_path, thumbnail_portrait_path=thumbnail_portrait_path,
                          desc=desc, schedule_time_str=schedule_time_str,
                          creation_declaration=creation_declaration, supplementary_declaration=data.get('supplementaryDeclaration', ''),
                          ai_content=ai_content)
            case 7:
                post_video_tiktok(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, schedule_time_str=schedule_time_str)
            case 8:
                post_video_youtube(title, file_list, tags, account_list,
                          enableTimer=enableTimer, videos_per_day=videos_per_day, daily_times=daily_times,
                          start_days=start_days, schedule_time_str=schedule_time_str,
                          audience=data.get('audience', 'not_kids'),
                          altered_content=data.get('alteredContent', False),
                          desc=desc, thumbnail_path=thumbnail_landscape_path or thumbnail_path)
    # 返回响应给客户端
    return jsonify(
        {
            "code": 200,
            "msg": None,
            "data": None
        }), 200

# Cookie文件上传API
@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({
                "code": 400,
                "msg": "没有找到Cookie文件",
                "data": None
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                "code": 400,
                "msg": "Cookie文件名不能为空",
                "data": None
            }), 400

        if not file.filename.endswith('.json'):
            return jsonify({
                "code": 400,
                "msg": "Cookie文件必须是JSON格式",
                "data": None
            }), 400

        # 获取账号信息
        account_id = request.form.get('id')
        platform = request.form.get('platform')

        if not account_id or not platform:
            return jsonify({
                "code": 400,
                "msg": "缺少账号ID或平台信息",
                "data": None
            }), 400

        # 从数据库获取账号的文件路径
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({
                "code": 500,
                "msg": "账号不存在",
                "data": None
            }), 404

        # 保存上传的Cookie文件到对应路径
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / result['filePath'])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)

        file.save(str(cookie_file_path))

        # 更新数据库中的账号信息（可选，比如更新更新时间）
        # 这里可以根据需要添加额外的处理逻辑

        return jsonify({
            "code": 200,
            "msg": "Cookie文件上传成功",
            "data": None
        }), 200

    except Exception as e:
        print(f"上传Cookie文件时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"上传Cookie文件失败: {str(e)}",
            "data": None
        }), 500


# Cookie文件下载API
@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({
                "code": 500,
                "msg": "缺少文件路径参数",
                "data": None
            }), 400

        # 验证文件路径的安全性，防止路径遍历攻击
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR / "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({
                "code": 500,
                "msg": "非法文件路径",
                "data": None
            }), 400

        if not cookie_file_path.exists():
            return jsonify({
                "code": 500,
                "msg": "Cookie文件不存在",
                "data": None
            }), 404

        # 返回文件
        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )

    except Exception as e:
        print(f"下载Cookie文件时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"下载Cookie文件失败: {str(e)}",
            "data": None
        }), 500


# ── Settings API ──

SETTINGS_FILE = Path(BASE_DIR) / "settings.json"

def _read_settings():
    if SETTINGS_FILE.exists():
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json_module.load(f)
    return {}

def _write_settings(data):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json_module.dump(data, f, ensure_ascii=False, indent=2)

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

# 包装函数：在线程中运行异步函数
def run_async_function(type,id,status_queue):
    import json
    match type:
        case '1':
            fn = xiaohongshu_cookie_gen
        case '2':
            fn = get_tencent_cookie
        case '3':
            fn = douyin_cookie_gen
        case '4':
            fn = get_ks_cookie
        case '5':
            fn = bilibili_cookie_gen
        case '6':
            fn = baijiahao_cookie_gen
        case '7':
            fn = get_tiktok_cookie
        case '8':
            fn = youtube_cookie_gen
        case _:
            status_queue.put(json.dumps({"status": "500", "msg": f"不支持的平台类型: {type}"}))
            return

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(fn(id, status_queue))
    except Exception as e:
        print(f"[LOGIN ERROR] type={type} id={id}: {type(e).__name__}: {e}")
        status_queue.put(json.dumps({"status": "500", "msg": f"登录失败: {e}"}))
    finally:
        loop.close()

# SSE 流生成器函数
def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
        else:
            # 避免 CPU 占满
            time.sleep(0.1)

def migrate_db():
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute('ALTER TABLE user_info ADD COLUMN avatar TEXT DEFAULT ""')
            conn.commit()
        except sqlite3.OperationalError:
            pass  # 列已存在

if __name__ == '__main__':
    migrate_db()
    app.run(host='0.0.0.0' ,port=5409)
