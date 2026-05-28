"""
抖音图文发布相关API代理
使用CloakBrowser来请求抖音API，避免反检测
"""

import asyncio
import json
import sys
from pathlib import Path

from flask import Blueprint, request, jsonify

sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("douyin_image")

douyin_image_bp = Blueprint('douyin_image', __name__, url_prefix='/api/douyin-image')


def _get_cookie_path(cookie_file: str) -> str:
    """获取cookie文件的完整路径"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


async def _fetch_with_browser(cookie_file: str, url: str, base_url: str = "https://creator.douyin.com/") -> dict:
    """使用CloakBrowser发送请求"""
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 先打开基础URL，确保cookie生效
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 使用fetch API请求目标URL
            # 转义URL中的特殊字符
            escaped_url = url.replace("'", "\\'").replace('"', '\\"')

            # 根据URL域名设置Referer
            referer = base_url
            if "tsearch.amemv.com" in url:
                referer = "https://creator.douyin.com/"

            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const response = await fetch("{escaped_url}", {{
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                                'Referer': '{referer}',
                            }}
                        }});

                        // 先获取文本，再尝试解析JSON
                        const text = await response.text();

                        if (!response.ok) {{
                            return {{ success: false, error: `HTTP ${{response.status}}: ${{text.substring(0, 200)}}` }};
                        }}

                        try {{
                            const data = JSON.parse(text);
                            return {{ success: true, data: data }};
                        }} catch (jsonError) {{
                            return {{ success: false, error: `JSON解析失败: ${{jsonError.message}}, 响应内容: ${{text.substring(0, 200)}}` }};
                        }}
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }}
            """)

            return result
        finally:
            await context.close()
    finally:
        await browser.close()


def run_async(coro):
    """在Flask中运行异步函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@douyin_image_bp.route('/mix-list', methods=['GET'])
def get_mix_list():
    """获取用户的合集列表"""
    account_id = request.args.get('account_id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少account_id参数"}), 400

    try:
        # 从数据库获取账号的cookie文件
        import sqlite3
        conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
        cursor = conn.cursor()
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"code": 404, "msg": "账号不存在"}), 404

        cookie_file = row[0]

        # 构建请求URL
        url = "https://creator.douyin.com/web/api/mix/list/?status=0%2C2&count=15&cursor=0&aid=1128"

        # 使用CloakBrowser请求
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"获取合集列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/activity-list', methods=['GET'])
def get_activity_list():
    """获取官方活动列表"""
    account_id = request.args.get('account_id')

    try:
        import sqlite3
        conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
        cursor = conn.cursor()

        if account_id:
            cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        else:
            # 如果没有指定账号，使用第一个抖音账号
            cursor.execute("SELECT filePath FROM user_info WHERE type = 3 LIMIT 1")

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        cookie_file = row[0]

        url = "https://creator.douyin.com/web/api/media/activity/get/?page=1&size=9999&need_challenge=1&aid=1128"

        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"获取活动列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/hotspot-search', methods=['GET'])
def search_hotspot():
    """搜索热点"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '50')

    try:
        import sqlite3
        conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
        cursor = conn.cursor()

        if account_id:
            cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        else:
            cursor.execute("SELECT filePath FROM user_info WHERE type = 3 LIMIT 1")

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        cookie_file = row[0]

        from urllib.parse import quote
        url = f"https://creator.douyin.com/aweme/v1/hotspot/search/?query={quote(keyword)}&count={count}&aid=1128"

        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索热点失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/music-search', methods=['GET'])
def search_music():
    """搜索音乐"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    cursor_val = request.args.get('cursor', '0')
    count = request.args.get('count', '20')

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        import sqlite3
        conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
        cursor = conn.cursor()

        if account_id:
            cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
        else:
            cursor.execute("SELECT filePath FROM user_info WHERE type = 3 LIMIT 1")

        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        cookie_file = row[0]

        from urllib.parse import quote
        url = f"https://tsearch.amemv.com/openapi/aweme/v1/music/search/?aid=1128&count={count}&search_source=normal_search&keyword={quote(keyword)}&cursor={cursor_val}"

        # 音乐搜索需要先打开抖音域名，让cookie生效
        result = run_async(_fetch_with_browser(cookie_file, url, base_url="https://www.douyin.com/"))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索音乐失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500
