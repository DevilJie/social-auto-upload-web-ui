"""今日头条内容创作平台相关 API 代理。

仿 ``alipay_bp.py`` 的网络拦截模式:用 CloakBrowser 打开头条发布页 →
上传一个空视频文件触发表单渲染 → 拦截合集搜索响应 → 把结果转发给前端。

合集列表是会话级的(需登录态 cookie),必须通过浏览器自动化获取。

请求体(文档 ~/toutiao.md):
    https://mp.toutiao.com/xigua/api/pSeries/simpleGetAlbumInfoByMediaId/
    ?params={"Limit":0,"Offset":0,"SortType":1}

响应结构:
    {
      "status": 0,
      "data": {
        "7288354781184639540": {
          "AuditStatus": 3,
          "Title": "一口气看完经典丧尸电影",
          "SeqsCount": 4,
          "CoverUrl": "...",
          "CoverUri": "...",
          "CoverHeight": 720,
          "CoverWidth": 1280
        }
      }
    }
"""

import asyncio
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("toutiao")

toutiao_bp = Blueprint('toutiao', __name__, url_prefix='/api/toutiao')

# 头条发布页(文档 ~/toutiao.md)
_TOUTIAO_PUBLISH_URL = (
    "https://mp.toutiao.com/profile_v4/xigua/upload-video"
)


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库取账号 cookie 文件名。account_id 为空时取任意一个头条账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 13 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ======================================================================
# /api/toutiao/compilation-search
# ======================================================================

@toutiao_bp.route('/compilation-search', methods=['GET'])
def search_compilation():
    """搜索头条合集 —— 浏览器拦截 pSeries/simpleGetAlbumInfoByMediaId。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    合集名称关键词(可选,为空则返回全部)

    Returns:
        {"code": 200, "data": {"list": [...], "total": N}}
    """
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')

    logger.info(
        f"[合集搜索] 收到请求: account_id={account_id}, keyword={keyword}"
    )

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的今日头条账号"}), 404

        result = run_async(_search_compilation_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            items = data.get("list", [])
            logger.info(
                f"[合集搜索] 成功,共 {len(items)} 个合集"
            )
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集搜索] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[合集搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_compilation_via_browser(cookie_file: str, keyword: str) -> dict:
    """用 CloakBrowser 直接调用合集接口获取列表。

    步骤:
        1. 打开头条创作中心页面（确保 cookie 生效）
        2. 直接调用 pSeries/simpleGetAlbumInfoByMediaId 接口
        3. 解析响应，提取合集列表
        4. 如果有关键词，过滤结果
    """
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 先打开头条创作中心，确保 cookie 生效
            logger.info("[合集搜索] 打开头条创作中心...")
            await page.goto("https://mp.toutiao.com/profile_v4/index", timeout=30000)
            await page.wait_for_load_state("domcontentloaded", timeout=15000)
            await asyncio.sleep(2)

            # 2. 直接调用合集接口
            logger.info("[合集搜索] 调用合集接口...")
            api_url = "https://mp.toutiao.com/xigua/api/pSeries/simpleGetAlbumInfoByMediaId/?params=%7B%22Limit%22%3A0%2C%22Offset%22%3A0%2C%22SortType%22%3A1%7D"

            # 使用 page.evaluate 直接 fetch 接口
            captured_response = await page.evaluate("""async (url) => {
                try {
                    const resp = await fetch(url, {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json',
                        }
                    });
                    return await resp.json();
                } catch (e) {
                    return { error: e.message };
                }
            }""", api_url)

            logger.info(f"[合集搜索] 接口响应: {str(captured_response)[:200]}...")

            if not captured_response or captured_response.get("error"):
                return {
                    "success": False,
                    "error": f"接口请求失败: {captured_response.get('error', '未知错误')}",
                }

            # 解析响应
            status = captured_response.get("status")
            data_obj = captured_response.get("data") or {}
            if status != 0:
                return {
                    "success": False,
                    "error": f"接口返回 status={status}",
                    "data": captured_response,
                }

            # 标准化输出(只保留前端需要的字段)
            items = []
            for series_id, info in data_obj.items():
                if not isinstance(info, dict):
                    continue
                title = info.get("Title", "")
                # 如果有关键词，过滤
                if keyword and keyword.lower() not in title.lower():
                    continue
                items.append({
                    "compilationId": series_id,
                    "title": title,
                    "coverUrl": info.get("CoverUrl", ""),
                    "total": info.get("SeqsCount", 0),
                })

            return {
                "success": True,
                "data": {
                    "list": items,
                    "total": len(items),
                },
            }

        finally:
            await context.close()
    finally:
        await browser.close()


# ======================================================================
# run_async helper(与 alipay_bp 一致)
# ======================================================================

def run_async(coro):
    """在新事件循环里跑协程(避免与 Flask 线程冲突)。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import threading
            result = {}
            def _run():
                new_loop = asyncio.new_event_loop()
                try:
                    result["v"] = new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            return result.get("v")
    except RuntimeError:
        pass
    return asyncio.run(coro)
