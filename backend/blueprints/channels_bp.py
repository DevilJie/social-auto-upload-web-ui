"""视频号创作者平台相关 API 代理。

用 CloakBrowser 打开视频号发布页 → 点「选择合集」入口 →
解析下拉 DOM 的 div.name 文本(合集名) → 返回给前端下拉选项。

开发阶段:有头模式,便于观察。
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

logger = get_channel_logger("channels")

channels_bp = Blueprint('channels', __name__, url_prefix='/api/channels')

# 视频号发布页
_CHANNELS_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        # type=2 为视频号
        cursor.execute("SELECT filePath FROM user_info WHERE type = 2 LIMIT 1")
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


@channels_bp.route('/collections', methods=['GET'])
def list_collections():
    """获取账号的合集列表。

    Query params:
        account_id: 账号 id(用于取 cookie)

    Returns:
        {"code": 200, "data": {"list": [...], "total": N}}
    """
    account_id = request.args.get('account_id')
    logger.info(f"[合集列表] 收到请求: account_id={account_id}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的视频号账号"}), 404

        result = run_async(_fetch_collections_via_browser(cookie_file))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[合集列表] 成功,共 {data.get('total', 0)} 个合集")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集列表] 失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500
    except Exception as e:
        logger.error(f"[合集列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_collections_via_browser(cookie_file: str) -> dict:
    """打开视频号发布页,点「选择合集」后解析下拉 DOM 拿合集列表。

    DOM 结构(需求文档):
      post-album-wrap > post-album-display > display-text("选择合集")
      点击后展开 filter-wrap > option-list-wrap > option-item > item > name(合集名)
      底部 create 里有「创建新合集」按钮,用 name 定位天然排除。

    全程文案/结构语义定位,禁用 data-v 随机串。
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 开发阶段:有头模式
    browser = await create_browser(headless=False)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开视频号发布页
            logger.info("[合集列表] 打开视频号发布页...")
            try:
                await page.goto(_CHANNELS_UPLOAD_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
            except Exception as e:
                logger.info(f"[合集列表] 页面加载(非致命): {e}")

            # 2. 点击「选择合集」入口
            # DOM: div.display-text 里的「选择合集」文案
            # 需要等待页面加载完成(「选择合集」文案出现)再点击
            logger.info("[合集列表] 等待页面加载完成(选择合集入口出现)...")
            entry = page.get_by_text("选择合集", exact=True)
            ready = False
            for _ in range(60):  # 最多等 30s
                if await entry.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "页面加载超时,未找到「选择合集」入口"}
            logger.info("[合集列表] 点击「选择合集」入口...")
            await entry.first.click()
            logger.info("[合集列表] 已点击,等待合集浮层弹出...")
            await asyncio.sleep(1.5)

            # 3. 解析下拉 DOM —— div.name 是合集名(固定语义 class,非 data-v 随机串)
            # DOM: option-list-wrap > option-item > item > div.name
            names = page.locator(".option-item .item .name")
            ready = False
            for _ in range(20):
                if await names.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "点击后未弹出合集选择浮层"}

            count = await names.count()
            logger.info(f"[合集列表] 浮层出现 {count} 个合集,开始解析")
            items = []
            for i in range(count):
                name = (await names.nth(i).inner_text()).strip()
                if not name:
                    continue
                # 排除「创建新合集」按钮文案
                if name in ("创建新合集", "选择合集"):
                    continue
                items.append({"name": name})

            logger.info(f"[合集列表] 解析完成,共 {len(items)} 个合集")
            return {"success": True, "data": {"list": items, "total": len(items)}}
        finally:
            await context.close()
    finally:
        await browser.close()
