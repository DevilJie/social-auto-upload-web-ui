"""
抖音图文发布相关API代理
使用CloakBrowser来请求抖音API，避免反检测
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

import requests as http_requests
from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("douyin_image")

douyin_image_bp = Blueprint('douyin_image', __name__, url_prefix='/api/douyin-image')

# agw-auth 缓存: {account_id: {"token": "auth-v1/...", "cookies": {...}, "expire_at": timestamp}}
_agw_auth_cache = {}


def _get_cookie_path(cookie_file: str) -> str:
    """获取cookie文件的完整路径"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库获取账号的cookie文件路径"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 3 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def _parse_agw_auth_expiry(token: str) -> float:
    """解析 agw-auth token 中的过期时间"""
    # 格式: auth-v1/{ak}/{timestamp}/{expire}/{signature}
    try:
        parts = token.split("/")
        if len(parts) >= 4 and parts[0] == "auth-v1":
            timestamp = int(parts[2])
            expire = int(parts[3])
            return timestamp + expire
    except (ValueError, IndexError):
        pass
    return 0


def _load_cookies_from_file(cookie_path: str) -> dict:
    """从 Playwright cookie 文件加载为 requests 可用的 cookies dict"""
    try:
        with open(cookie_path, 'r') as f:
            data = json.load(f)
        cookies = {}
        for c in data.get("cookies", data if isinstance(data, list) else []):
            name = c.get("name", "")
            domain = c.get("domain", "")
            # 只保留抖音相关域名的 cookie
            if any(d in domain for d in [".douyin.com", ".amemv.com", ".bytedance.com"]):
                cookies[name] = c.get("value", "")
        return cookies
    except Exception as e:
        logger.error(f"加载cookie文件失败: {e}")
        return {}


def _is_cache_valid(account_id: str) -> bool:
    """检查缓存的 agw-auth 是否仍然有效"""
    if account_id not in _agw_auth_cache:
        return False
    cache = _agw_auth_cache[account_id]
    # 提前 60 秒过期，避免边界情况
    return time.time() < cache["expire_at"] - 60


def _direct_music_search(token: str, cookies: dict, keyword: str, cursor_val: str = "0", count: str = "20") -> dict:
    """使用缓存的 agw-auth 直接调用音乐搜索 API"""
    url = "https://tsearch.amemv.com/openapi/aweme/v1/music/search/"
    params = {
        "aid": "1128",
        "count": count,
        "search_source": "normal_search",
        "keyword": keyword,
        "cursor": cursor_val,
        "cookie_enabled": "true",
        "screen_width": "1920",
        "screen_height": "1080",
        "browser_language": "zh-CN",
        "browser_platform": "Win32",
        "browser_name": "Mozilla",
        "browser_version": "5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "browser_online": "true",
        "timezone_name": "Asia/Shanghai",
        "support_h265": "0",
    }
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "agw-auth": token,
        "openapi-omit-shark": "1",
        "origin": "https://creator.douyin.com",
        "referer": "https://creator.douyin.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
    }

    try:
        resp = http_requests.get(url, params=params, headers=headers, cookies=cookies, timeout=15)
        data = resp.json()
        return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"直接请求音乐搜索失败: {e}")
        return {"success": False, "error": str(e)}


async def _fetch_agw_auth_via_browser(cookie_file: str) -> dict:
    """通过浏览器拦截获取 agw-auth token 和 cookies"""
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            captured_token = None

            def handle_request(req):
                nonlocal captured_token
                if "tsearch.amemv.com" in req.url:
                    headers = dict(req.headers)
                    token = headers.get("agw-auth", "")
                    if token and token != "NOT_FOUND":
                        captured_token = token

            page.on("request", handle_request)

            # 打开音乐页面，触发初始请求以获取 agw-auth
            await page.goto("https://creator.douyin.com/creator/music", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            if not captured_token:
                # 尝试触发搜索以获取 token
                search_selectors = [
                    'input[placeholder*="搜索"]',
                    'input[placeholder*="音乐"]',
                    'input[type="text"]',
                ]
                for selector in search_selectors:
                    el = page.locator(selector).first
                    if await el.is_visible():
                        await el.fill("test")
                        await page.wait_for_timeout(500)
                        await el.press("Enter")
                        await page.wait_for_timeout(3000)
                        break

            # 从浏览器上下文获取 cookies
            browser_cookies = await context.cookies()
            cookies_dict = {}
            for c in browser_cookies:
                if any(d in c.get("domain", "") for d in [".douyin.com", ".amemv.com", ".bytedance.com"]):
                    cookies_dict[c["name"]] = c["value"]

            return {
                "token": captured_token,
                "cookies": cookies_dict,
            }
        finally:
            await context.close()
    finally:
        await browser.close()


def _ensure_agw_auth(account_id: str, cookie_file: str) -> bool:
    """确保有有效的 agw-auth 缓存，如果没有则通过浏览器获取"""
    if _is_cache_valid(account_id):
        return True

    logger.info(f"agw-auth 缓存过期或不存在，通过浏览器重新获取 (account={account_id})")
    result = run_async(_fetch_agw_auth_via_browser(cookie_file))

    token = result.get("token")
    if not token:
        logger.error(f"通过浏览器获取 agw-auth 失败: {result}")
        return False

    expire_at = _parse_agw_auth_expiry(token)
    if expire_at == 0:
        # 解析失败，默认缓存 25 分钟
        expire_at = time.time() + 1500

    _agw_auth_cache[account_id] = {
        "token": token,
        "cookies": result.get("cookies", {}),
        "expire_at": expire_at,
    }

    logger.info(f"agw-auth 获取成功，缓存至 {time.strftime('%H:%M:%S', time.localtime(expire_at))}")
    return True


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
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "账号不存在"}), 404

        url = "https://creator.douyin.com/web/api/mix/list/?status=0%2C2&count=15&cursor=0&aid=1128"
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
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

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
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

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
    """搜索音乐 - 使用 agw-auth 缓存优化"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    cursor_val = request.args.get('cursor', '0')
    count = request.args.get('count', '20')

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        # 确定缓存 key（用 cookie_file 作为唯一标识）
        cache_key = cookie_file

        # 确保 agw-auth 缓存有效
        if not _ensure_agw_auth(cache_key, cookie_file):
            return jsonify({"code": 500, "msg": "获取 agw-auth 签名失败"}), 500

        # 使用缓存的 token 直接请求
        cache = _agw_auth_cache[cache_key]
        result = _direct_music_search(
            token=cache["token"],
            cookies=cache["cookies"],
            keyword=keyword,
            cursor_val=cursor_val,
            count=count,
        )

        if result.get("success"):
            data = result["data"]
            # 如果返回错误码，可能是 token 过期，清除缓存重试
            if data.get("status_code") != 0:
                logger.warning(f"音乐搜索返回错误码 {data.get('status_code')}，清除缓存重试")
                _agw_auth_cache.pop(cache_key, None)
                # 重试一次
                if not _ensure_agw_auth(cache_key, cookie_file):
                    return jsonify({"code": 500, "msg": "获取 agw-auth 签名失败"}), 500
                cache = _agw_auth_cache[cache_key]
                result = _direct_music_search(
                    token=cache["token"],
                    cookies=cache["cookies"],
                    keyword=keyword,
                    cursor_val=cursor_val,
                    count=count,
                )
                if result.get("success"):
                    return jsonify({"code": 200, "data": result["data"]})
                return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

            return jsonify({"code": 200, "data": data})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索音乐失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/music-cache-status', methods=['GET'])
def music_cache_status():
    """查看 agw-auth 缓存状态"""
    status = {}
    for key, cache in _agw_auth_cache.items():
        remaining = max(0, int(cache["expire_at"] - time.time()))
        status[key] = {
            "valid": _is_cache_valid(key),
            "remaining_seconds": remaining,
            "token_preview": cache["token"][:50] + "..." if cache.get("token") else None,
        }
    return jsonify({"code": 200, "data": status})
