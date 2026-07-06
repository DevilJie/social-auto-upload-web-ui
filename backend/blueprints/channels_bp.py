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
from impl._utils import clear_and_type

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

    # 无头模式:不弹浏览器窗口
    browser = await create_browser(headless=True)
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


@channels_bp.route('/locations', methods=['GET'])
def list_locations():
    """搜索账号附近的位置列表。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    位置关键字(必填,后端用 CloakBrowser 真实搜索)

    Returns:
        {"code": 200, "data": {"list": [{name, desc}], "total": N}}
    """
    account_id = request.args.get('account_id')
    keyword = (request.args.get('keyword') or '').strip()
    logger.info(f"[位置搜索] 收到请求: account_id={account_id}, keyword={keyword!r}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少 keyword 参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的视频号账号"}), 404

        result = run_async(_fetch_locations_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[位置搜索] 成功,共 {data.get('total', 0)} 个位置")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[位置搜索] 失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500
    except Exception as e:
        logger.error(f"[位置搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_locations_via_browser(cookie_file: str, keyword: str) -> dict:
    """打开视频号发布页,点位置卡 → 输入关键字 → 解析下拉 DOM 拿位置列表。

    DOM(用户实际抓取,weui 框架):
      入口: div.position-display-wrap (显示当前位置的内层卡片,点击展开搜索面板)
      搜索框: input[placeholder="搜索附近位置"] (.weui-desktop-form__input)
      下拉: div.common-option-list-wrap .option-item
        - 第一项 .option-item.active 永远是「不显示位置」(遍历时跳过 index 0)
        - 每项内 .location-item-info .name 是位置名,.desc 是地址

    与 _fetch_collections_via_browser 的差异:
      - 入口不是 get_by_text,而是 div.position-display-wrap
      - 必须输入 keyword 触发后端搜索(合集是直接拉全量)
      - 选项 .name 在 .location-item-info 下(合集在 .item 下)
      - 多了 .desc 地址字段
      - 跳过 index 0(合集靠文案排除)
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 无头模式:不弹浏览器窗口
    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开视频号发布页
            logger.info("[位置搜索] 打开视频号发布页...")
            try:
                await page.goto(_CHANNELS_UPLOAD_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
            except Exception as e:
                logger.info(f"[位置搜索] 页面加载(非致命): {e}")

            # 2. 等待位置卡 div.position-display-wrap 出现并点击展开
            logger.info("[位置搜索] 等待位置卡出现...")
            position_wrap = page.locator("div.position-display-wrap").first
            ready = False
            for _ in range(60):  # 最多等 30s
                if await position_wrap.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "页面加载超时,未找到位置卡(div.position-display-wrap)"}
            logger.info("[位置搜索] 点击位置卡展开搜索面板...")
            await position_wrap.click()
            await asyncio.sleep(1)

            # 3. 在搜索框输入关键字
            search_input = page.locator('input[placeholder="搜索附近位置"]').first
            if await search_input.count() == 0:
                return {"success": False, "error": "未找到位置搜索框(input[placeholder=搜索附近位置])"}
            await search_input.click()
            await clear_and_type(page, keyword, delay=50)
            logger.info(f"[位置搜索] 已输入关键字: {keyword},等下拉刷新...")
            await asyncio.sleep(2)

            # 4. 等待下拉 div.common-option-list-wrap .option-item 出现
            options = page.locator("div.common-option-list-wrap .option-item")
            ready = False
            for _ in range(20):  # 最多等 10s
                if await options.count() > 1:  # 至少要有 1 个真实位置(index 0 是「不显示位置」)
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "输入关键字后未出现位置下拉"}

            # 5. 解析下拉项(跳过 index 0,那是「不显示位置」)
            count = await options.count()
            logger.info(f"[位置搜索] 下拉出现 {count} 项(含「不显示位置」),开始解析")
            items = []
            for i in range(1, count):  # 跳过 index 0
                opt = options.nth(i)
                name_el = opt.locator(".location-item-info .name").first
                desc_el = opt.locator(".location-item-info .desc").first
                if await name_el.count() == 0:
                    continue
                try:
                    name = (await name_el.inner_text()).strip()
                except Exception:
                    continue
                if not name:
                    continue
                desc = ""
                try:
                    if await desc_el.count() > 0:
                        desc = (await desc_el.inner_text()).strip()
                except Exception:
                    pass
                items.append({"name": name, "desc": desc})

            logger.info(f"[位置搜索] 解析完成,共 {len(items)} 个位置")
            return {"success": True, "data": {"list": items, "total": len(items)}}
        finally:
            await context.close()
    finally:
        await browser.close()
