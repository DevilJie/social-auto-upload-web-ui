import os
import sys
from pathlib import Path

print(f"[Startup] Python {sys.version} starting...")
print(f"[Startup] Script: {__file__}")
print(f"[Startup] SAU_PORT={os.environ.get('SAU_PORT')}, SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

# 确保 backend/ 目录在 sys.path 中（嵌入式 Python 的 _pth 文件可能不会自动添加脚本目录）
BACKEND_DIR = Path(__file__).parent.resolve()
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
    print(f"[Startup] Added backend dir to sys.path: {BACKEND_DIR}")

UPSTREAM_DIR = Path(__file__).parent.parent / "vendor" / "upstream"
sys.path.insert(1, str(UPSTREAM_DIR))
print(f"[Startup] Upstream dir: {UPSTREAM_DIR} (exists={UPSTREAM_DIR.exists()})")

print("[Startup] Importing sau_backend...")
from sau_backend import app  # noqa: E402
print("[Startup] sau_backend imported OK")

# 注册阶段二扩展 API Blueprint
print("[Startup] Importing ext_api...")
from ext_api import ext_api  # noqa: E402
app.register_blueprint(ext_api)
print("[Startup] ext_api registered OK")

import json
import sqlite3
import uuid
from datetime import datetime

from flask import g, jsonify, request, send_from_directory

# 覆盖 sau_backend 的前端静态文件路由，指向正确的前端目录
# 打包后前端在 exe 同级的 frontend/ 目录
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
print(f"[Startup] Frontend dir: {FRONTEND_DIR} (exists={FRONTEND_DIR.exists()})")

if FRONTEND_DIR.exists():
    # 覆盖已有的 view functions，不重复注册路由
    app.view_functions['index'] = lambda: send_from_directory(str(FRONTEND_DIR), 'index.html')
    app.view_functions['custom_static'] = lambda filename: send_from_directory(str(FRONTEND_DIR / 'assets'), filename)
    app.view_functions['favicon'] = lambda: send_from_directory(str(FRONTEND_DIR), 'favicon.ico')
    app.view_functions['vite_svg'] = lambda: send_from_directory(str(FRONTEND_DIR), 'vite.svg')


def _get_db_path():
    """Get DB path from SAU_DATA_DIR env var, with fallback."""
    if data_dir := os.environ.get("SAU_DATA_DIR"):
        return Path(data_dir) / "db" / "database.db"
    # Fallback: dev environment (repo root/data/db/)
    return Path(__file__).parent.parent / "data" / "db" / "database.db"


DB_PATH = _get_db_path()
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube"}


def _record_publish(task_id, platform, account_name, video_path, title, description, tags, status, started_at, finished_at=None, error_message=""):
    """记录发布历史到 publish_tasks 表"""
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
        print(f"[History] 记录发布失败: {e}")


def _update_publish_result(task_id, status, finished_at, error_message=""):
    """更新发布结果"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute(
                """UPDATE publish_tasks
                   SET status=?, finished_at=?, error_message=?
                   WHERE id=?""",
                (status, finished_at, error_message, task_id)
            )
    except Exception as e:
        print(f"[History] 更新发布结果失败: {e}")


@app.before_request
def _ensure_db():
    """确保数据库文件和目录存在，且表结构完整"""
    db_path = _get_db_path()
    need_init = False
    if not db_path.exists():
        need_init = True
    else:
        # 文件存在但可能没有表（空数据库）
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
            print(f"[DB] Initialized database at {db_path}")
        except Exception as e:
            print(f"[DB] Failed to initialize database: {e}")


@app.before_request
def _before_publish():
    """在 /postVideo 请求前记录发布开始"""
    if request.path == '/postVideo' and request.method == 'POST':
        data = request.get_json(silent=True)
        if not data:
            return
        now = datetime.now().isoformat()
        task_id = str(uuid.uuid4())
        platform_type = data.get('type', 0)
        account_list = data.get('accountList', [])
        file_list = data.get('fileList', [])

        # 从 cookie 文件路径提取账号名
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
    """在 /postVideo 请求后更新发布结果"""
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


def find_available_port(start_port=5409, max_attempts=10):
    """Find an available port starting from start_port."""
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    raise RuntimeError(f"Could not find available port in range {start_port}-{start_port + max_attempts}")


@app.route("/api/health", methods=['GET'])
def health_check():
    """诊断端点：检查环境、数据库路径和连接"""
    import sqlite3 as _sqlite
    from conf import BASE_DIR as _BASE_DIR
    diag = {
        "sau_data_dir": os.environ.get("SAU_DATA_DIR"),
        "base_dir": str(_BASE_DIR),
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


if __name__ == "__main__":
    import os
    import socket

    # 初始化数据库（建表 + 增量迁移）
    print("[Startup] Initializing database...")
    from init_db import init_database, migrate_database
    init_database()
    migrate_database()
    print("[Startup] Database initialized OK")

    # 验证数据库可访问
    try:
        import sqlite3 as _sqlite
        _test_path = _get_db_path()
        print(f"[Startup] DB path: {_test_path} (exists={_test_path.exists()})")
        with _sqlite.connect(str(_test_path)) as _conn:
            _conn.execute("SELECT 1 FROM user_info LIMIT 1")
        print("[Startup] DB verification OK")
    except Exception as _e:
        print(f"[Startup] DB verification FAILED: {_e}")
        print(f"[Startup] SAU_DATA_DIR={os.environ.get('SAU_DATA_DIR')}")

    # Allow port override via environment variable (for dev convenience)
    port = int(os.environ.get("SAU_PORT", "5409"))
    # Check if the requested port is available, auto-increment if not
    if port == 5409:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
        except OSError:
            port = find_available_port(5409 + 1)
            print(f"[Startup] Port 5409 in use, using port {port}")
    print(f"[Startup] Starting Waitress server on port {port}")
    from waitress import serve
    # Expose port via environment variable for frontend
    os.environ["SAU_PORT"] = str(port)
    serve(app, host="0.0.0.0", port=port)
