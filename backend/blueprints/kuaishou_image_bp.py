"""
快手图文发布相关 API 代理
使用 CloakBrowser 拦截音乐搜索接口。
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("kuaishou_image")

kuaishou_image_bp = Blueprint('kuaishou_image', __name__, url_prefix='/api/kuaishou-image')


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 4 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def run_async(coro):
    """在同步 Flask 上下文里跑 async 协程。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


@kuaishou_image_bp.route('/ping', methods=['GET'])
def ping():
    return jsonify({"code": 200, "msg": "kuaishou-image bp ok"})
