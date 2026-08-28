"""视频号创作者平台相关 API 代理。

用 CloakBrowser 打开视频号发布页 → 点「选择合集」入口 →
解析下拉 DOM 的 div.name 文本(合集名) → 返回给前端下拉选项。

开发阶段:有头模式,便于观察。
"""

from __future__ import annotations

import asyncio
import sqlite3
import threading
from pathlib import Path
from typing import Optional

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


@channels_bp.route('/activities', methods=['GET'])
def list_activities():
    """搜索可参与的活动列表。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    活动关键字(必填,后端用 CloakBrowser 真实搜索)

    Returns:
        {"code": 200, "data": {"list": [{activity_id, name, creator_name}], "total": N}}
    """
    account_id = request.args.get('account_id')
    keyword = (request.args.get('keyword') or '').strip()
    logger.info(f"[活动搜索] 收到请求: account_id={account_id}, keyword={keyword!r}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少 keyword 参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的视频号账号"}), 404

        result = run_async(_fetch_activities_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[活动搜索] 成功,共 {data.get('total', 0)} 个活动")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[活动搜索] 失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500
    except Exception as e:
        logger.error(f"[活动搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_activities_via_browser(cookie_file: str, keyword: str) -> dict:
    """打开视频号发布页,点活动卡 → 输入关键字 → 解析下拉 DOM 拿活动列表。

    DOM(用户实际抓取,weui 框架):
      入口: div.post-activity-wrap > div.activity-display (显示「不参与活动」/已选活动的卡片,点击展开)
      搜索框: input[placeholder="搜索活动"] (.weui-desktop-form__input)
      下拉: div.common-option-list-wrap .option-item
        - 第一项 .option-item.active 永远是「不参与活动」(遍历时跳过 index 0)
        - 每项内 .activity-item-info 下两个 span:
            .creator-name(发起人,可能为空,不参与活动那项就没有)
            .name(活动名)

    与 _fetch_locations_via_browser 的差异:
      - 入口是 div.post-activity-wrap(位置是 div.position-display-wrap)
      - 搜索框 placeholder 是「搜索活动」(位置是「搜索附近位置」)
      - 选项里 .creator-name 是发起人,.name 是活动名(位置是 .name + .desc)
      - activity_id 由后端生成(index+1 或 hash),视频号页面 DOM 里没看到 id 属性
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 无头模式:不弹浏览器窗口
    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开视频号发布页
            logger.info("[活动搜索] 打开视频号发布页...")
            try:
                await page.goto(_CHANNELS_UPLOAD_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(3)
            except Exception as e:
                logger.info(f"[活动搜索] 页面加载(非致命): {e}")

            # 2. 等待活动卡 div.post-activity-wrap 出现并点击展开
            logger.info("[活动搜索] 等待活动卡出现...")
            activity_wrap = page.locator("div.post-activity-wrap").first
            ready = False
            for _ in range(60):  # 最多等 30s
                if await activity_wrap.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "页面加载超时,未找到活动卡(div.post-activity-wrap)"}
            logger.info("[活动搜索] 点击活动卡展开搜索面板...")
            await activity_wrap.click()
            await asyncio.sleep(1)

            # 3. 在搜索框输入关键字
            search_input = page.locator('input[placeholder="搜索活动"]').first
            if await search_input.count() == 0:
                return {"success": False, "error": "未找到活动搜索框(input[placeholder=搜索活动])"}
            await search_input.click()
            await clear_and_type(page, keyword, delay=50)
            logger.info(f"[活动搜索] 已输入关键字: {keyword},等下拉刷新...")
            await asyncio.sleep(2)

            # 4. 等待下拉 div.common-option-list-wrap .option-item 出现
            options = page.locator("div.common-option-list-wrap .option-item")
            ready = False
            for _ in range(20):  # 最多等 10s
                if await options.count() > 1:  # 至少要有 1 个真实活动(index 0 是「不参与活动」)
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "输入关键字后未出现活动下拉"}

            # 5. 解析下拉项(跳过 index 0,那是「不参与活动」)
            count = await options.count()
            logger.info(f"[活动搜索] 下拉出现 {count} 项(含「不参与活动」),开始解析")
            items = []
            for i in range(1, count):  # 跳过 index 0
                opt = options.nth(i)
                name_el = opt.locator(".activity-item-info .name").first
                creator_el = opt.locator(".activity-item-info .creator-name").first
                if await name_el.count() == 0:
                    continue
                try:
                    name = (await name_el.inner_text()).strip()
                except Exception:
                    continue
                if not name:
                    continue
                creator_name = ""
                try:
                    if await creator_el.count() > 0:
                        creator_name = (await creator_el.inner_text()).strip().rstrip("· ").strip()
                except Exception:
                    pass
                # video号 DOM 里没看到 activity_id 属性,后端用 f"{name}|{creator_name}" 生成稳定 key
                activity_id = f"{name}|{creator_name}"
                items.append({
                    "activity_id": activity_id,
                    "name": name,
                    "creator_name": creator_name,
                })

            logger.info(f"[活动搜索] 解析完成,共 {len(items)} 个活动")
            return {"success": True, "data": {"list": items, "total": len(items)}}
        finally:
            await context.close()
    finally:
        await browser.close()


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


# ===================================================================
# 视频号剧集 picker(浏览器常驻,前端多次 search/go_page 调用)
# ===================================================================
import threading
from typing import Optional as _Opt

_drama_loop: Optional[asyncio.AbstractEventLoop] = None
_drama_loop_thread: Optional[threading.Thread] = None
_drama_loop_lock = threading.Lock()
_drama_loop_ready = threading.Event()


def _start_drama_loop():
    global _drama_loop
    _drama_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_drama_loop)
    _drama_loop_ready.set()
    _drama_loop.run_forever()


def _ensure_drama_loop():
    global _drama_loop_thread
    if _drama_loop_thread is None or not _drama_loop_thread.is_alive():
        with _drama_loop_lock:
            if _drama_loop_thread is None or not _drama_loop_thread.is_alive():
                _drama_loop_ready.clear()
                _drama_loop_thread = threading.Thread(target=_start_drama_loop, daemon=True)
                _drama_loop_thread.start()
                _drama_loop_ready.wait(timeout=5)
    return _drama_loop


def run_drama_picker_async(coro, timeout: float = 60):
    loop = _ensure_drama_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


# 剧集 picker session 池(按 account_id 单例)
_drama_pool: dict = {}
_drama_pool_lock = threading.Lock()


def _ok(data):
    return jsonify({"code": 200, "data": data})


def _err(msg, code: int = 500, http: int = 500):
    return jsonify({"code": code, "msg": msg}), http


def _resolve_drama_session_or_404(account_id: str):
    if not account_id:
        return None, _err("accountId 不能为空", 400, 400)
    s = _drama_pool.get(account_id)
    if s is None:
        return None, _err("剧集 picker 未打开或已关闭,请重新打开弹窗", 404, 404)
    return s, None


@channels_bp.route("/drama_picker/open", methods=["POST"])
def drama_picker_open():
    data = request.get_json(silent=True) or {}
    raw_id = data.get("accountId")
    account_id = str(raw_id).strip() if raw_id is not None else ""
    link_type = (data.get("linkType") or data.get("entry") or "drama").strip()
    if not account_id:
        return _err("accountId 不能为空", 400, 400)
    if link_type not in ("article", "red_envelope", "drama", "mini_drama"):
        return _err("linkType 必须是 article/red_envelope/drama/mini_drama", 400, 400)
    cookie_file = _get_account_cookie_file(account_id)
    if not cookie_file:
        return _err("账号不存在或未登录", 404, 404)

    from impl.channels.picker import ChannelsDramaPickerSession
    with _drama_pool_lock:
        old = _drama_pool.pop(account_id, None)
        if old is not None:
            try:
                run_drama_picker_async(old.close(), timeout=10)
            except Exception:
                pass
        session = ChannelsDramaPickerSession(account_id)
        _drama_pool[account_id] = session

    try:
        result = run_drama_picker_async(session.open(link_type), timeout=180)
        logger.info(
            "[Drama API] open ok account_id=%s link_type=%s items=%d",
            account_id, link_type, len(result.get("items", [])),
        )
        return _ok(result)
    except Exception as e:
        logger.error("[Drama API] open 失败: %s", e, exc_info=True)
        with _drama_pool_lock:
            _drama_pool.pop(account_id, None)
        try:
            run_drama_picker_async(session.close(), timeout=10)
        except Exception:
            pass
        return _err(f"打开剧集弹窗失败: {e}")


@channels_bp.route("/drama_picker/search", methods=["POST"])
def drama_picker_search():
    data = request.get_json(silent=True) or {}
    raw_id = data.get("accountId")
    account_id = str(raw_id).strip() if raw_id is not None else ""
    keyword = (data.get("keyword") or "").strip()
    s, err = _resolve_drama_session_or_404(account_id)
    if err:
        return err
    try:
        result = run_drama_picker_async(s.search(keyword), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error("[Drama API] search 失败: %s", e, exc_info=True)
        return _err(f"搜索失败: {e}")


@channels_bp.route("/drama_picker/go_page", methods=["POST"])
def drama_picker_go_page():
    data = request.get_json(silent=True) or {}
    raw_id = data.get("accountId")
    account_id = str(raw_id).strip() if raw_id is not None else ""
    page = int(data.get("page") or 1)
    s, err = _resolve_drama_session_or_404(account_id)
    if err:
        return err
    try:
        result = run_drama_picker_async(s.go_page(page), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error("[Drama API] go_page 失败: %s", e, exc_info=True)
        return _err(f"翻页失败: {e}")


@channels_bp.route("/drama_picker/close", methods=["POST"])
def drama_picker_close():
    data = request.get_json(silent=True) or {}
    raw_id = data.get("accountId")
    account_id = str(raw_id).strip() if raw_id is not None else ""
    if not account_id:
        return _ok({"closed": True})
    with _drama_pool_lock:
        session = _drama_pool.pop(account_id, None)
    if session is None:
        return _ok({"closed": True})
    try:
        run_drama_picker_async(session.close(), timeout=10)
    except Exception as e:
        logger.warning("[Drama API] close 异常(忽略): %s", e)
    return _ok({"closed": True})
