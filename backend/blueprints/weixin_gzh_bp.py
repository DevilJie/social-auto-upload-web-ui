"""微信公众号创作者平台相关 API 代理。

用 CloakBrowser 打开公众号合集管理页(appmsgalbummgr) →
点「视频合集」tab → 解析表格 .album-title 文本(合集名) →
返回给前端下拉选项。

公众号特殊性: 所有功能 URL 必须带 token(每次会话变化),
因此先访问 https://mp.weixin.qq.com/ 让 cookie 触发跳转,
再从 URL 解析 token 拼装合集管理页 URL。
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("weixin_gzh")

weixin_gzh_bp = Blueprint('weixin_gzh', __name__, url_prefix='/api/weixin_gzh')

# 公众号首页入口(不带 token,访问后由 cookie 触发自动跳转到带 token 的 home)
_LOGIN_URL = "https://mp.weixin.qq.com/"
_TOKEN_RE = re.compile(r"[?&]token=(\d+)")
# 合集管理页(token 由 _resolve_token 拼装,type=5 为视频合集)
_ALBUM_MGR_PATH = (
    "https://mp.weixin.qq.com/cgi-bin/appmsgalbummgr"
    "?action=list&token={token}&lang=zh_CN&type=5"
)


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        # type=17 为微信公众号
        cursor.execute("SELECT filePath FROM user_info WHERE type = 17 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def run_async(coro):
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


@weixin_gzh_bp.route('/collections', methods=['GET'])
def list_collections():
    """获取账号的合集列表(视频合集 / 贴图合集)。

    Query params:
        account_id: 账号 id(用于取 cookie)
        collection_type: 合集类型 tab 文案,默认「视频合集」;
                         图集传「贴图合集」。
                         若页面上找不到该 tab,说明账号无此类型合集,
                         返回空列表(不报错)。

    流程:
        1. 用账号 cookie 打开公众号首页,等 cookie 触发跳转,解析 token
        2. 用 token 打开合集管理页(appmsgalbummgr)
        3. 点对应 tab(视频合集/贴图合集);找不到则返回空
        4. 解析表格 tbody tr 的 .album-title 文本(合集名)

    Returns:
        {"code": 200, "data": {"list": [{"name": "..."}], "total": N}}
    """
    account_id = request.args.get('account_id')
    collection_type = request.args.get('collection_type') or '视频合集'
    logger.info(f"[合集列表] 收到请求: account_id={account_id}, collection_type={collection_type}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的微信公众号账号"}), 404

        result = run_async(_fetch_collections_via_browser(cookie_file, collection_type))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[合集列表] 成功[{collection_type}],共 {data.get('total', 0)} 个合集")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集列表] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[合集列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_collections_via_browser(cookie_file: str, collection_type: str = '视频合集') -> dict:
    """打开公众号合集管理页,点指定类型 tab,解析表格 DOM 拿合集列表。

    DOM 结构(需求文档):
      tab: <li class="weui-desktop-tag">视频合集/贴图合集</li>
      表格: table.weui-desktop-table > tbody > tr > td.album-title
        合集名在 .album-title-tips 文本里

    全程文案/结构语义定位,禁用 data-v 随机串。
    """
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 访问公众号首页,等 cookie 触发跳转,解析 token
            logger.info("[合集列表] 打开公众号首页,解析 token...")
            try:
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.info(f"[合集列表] 首页加载(非致命): {e}")

            token = ""
            deadline = asyncio.get_event_loop().time() + 15
            while asyncio.get_event_loop().time() < deadline:
                m = _TOKEN_RE.search(page.url or "")
                if m:
                    token = m.group(1)
                    break
                await asyncio.sleep(0.5)
            if not token:
                return {"success": False, "error": f"未能解析 token(cookie 可能失效), URL={page.url}"}
            logger.info(f"[合集列表] 获取到 token: {token}")

            # 2. 打开合集管理页
            album_url = _ALBUM_MGR_PATH.format(token=token)
            logger.info(f"[合集列表] 打开合集管理页...")
            try:
                await page.goto(album_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)
            except Exception as e:
                logger.info(f"[合集列表] 合集页加载(非致命): {e}")

            # 3. 点对应类型 tab(视频合集/贴图合集)
            #    **找不到 tab = 账号无该类型合集,直接返回空**(不报错、不继续解析)
            tag = page.locator(
                "li.weui-desktop-tag", has_text=collection_type
            ).first
            tag_found = False
            try:
                await tag.wait_for(state="visible", timeout=8000)
                await tag.click()
                tag_found = True
                logger.info(f"[合集列表] 已点击「{collection_type}」tab")
            except Exception:
                logger.info(f"[合集列表] 未找到「{collection_type}」tab → 账号无该类型合集,返回空")
                return {"success": True, "data": {"list": [], "total": 0}}
            await asyncio.sleep(1.5)

            # 4. 解析表格 tbody tr 的 .album-title 文本
            title_els = page.locator("table.weui-desktop-table tbody tr .album-title")
            ready = False
            for _ in range(20):
                if await title_els.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                # tab 找到了但表格空 = 该类型下无合集
                logger.info(f"[合集列表] 「{collection_type}」tab 下无合集")
                return {"success": True, "data": {"list": [], "total": 0}}

            count = await title_els.count()
            logger.info(f"[合集列表] 发现 {count} 个合集,开始解析")
            items = []
            for i in range(count):
                try:
                    # 合集名在 .album-title-tips 文本里
                    tips = title_els.nth(i).locator(".album-title-tips").first
                    if await tips.count():
                        name = (await tips.inner_text()).strip()
                    else:
                        name = (await title_els.nth(i).inner_text()).strip()
                    if name:
                        items.append({"name": name})
                except Exception as e:
                    logger.info(f"[合集列表] 第 {i} 项解析失败: {e}")

            logger.info(f"[合集列表] 解析完成,共 {len(items)} 个合集")
            return {"success": True, "data": {"list": items, "total": len(items)}}
        finally:
            await context.close()
    finally:
        await browser.close()
