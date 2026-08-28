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
import threading
from pathlib import Path
from typing import Optional

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


def _ok(data: dict):
    return jsonify({"code": 200, "data": data})


def _err(msg: str, code: int = 500, http: int = 500):
    return jsonify({"code": code, "msg": msg}), http


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



# ---------- 视频号剧集 picker 路由 ----------
# 全局 picker event loop(后台 daemon 线程)
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
_drama_pool: dict[str, 'WeixinGzhDramaPickerSession'] = {}
_drama_pool_lock = threading.Lock()


def _get_drama_session_or_404(account_id: str):
    if not account_id:
        return None, _err("accountId 不能为空", 400, 400)
    s = _drama_pool.get(account_id)
    if s is None:
        return None, _err("剧集 picker 未打开或已关闭,请重新打开弹窗", 404, 404)
    return s, None


@weixin_gzh_bp.route('/drama_picker/open', methods=['POST'])
def drama_picker_open():
    """打开剧集 picker 弹窗(后台启浏览器 → 进 appmsg_edit_v2 → 开弹窗 → 首屏数据)。"""
    data = request.get_json(silent=True) or {}
    account_id = (data.get('accountId') or '').strip()
    if not account_id:
        return _err('accountId 不能为空', 400, 400)
    cookie_file = _get_account_cookie_file(account_id)
    if not cookie_file:
        return _err('账号不存在或未登录', 404, 404)
    cookie_path = Path(BASE_DIR / 'cookiesFile') / cookie_file

    from impl.weixin_gzh.picker import WeixinGzhDramaPickerSession
    with _drama_pool_lock:
        # 同账号已有 picker:异步销毁旧 session,起新 session
        old = _drama_pool.pop(account_id, None)
        if old is not None:
            try:
                run_drama_picker_async(old.close(), timeout=10)
            except Exception:
                pass
        session = WeixinGzhDramaPickerSession(account_id)
        _drama_pool[account_id] = session

    try:
        result = run_drama_picker_async(session.open(), timeout=180)
        logger.info(f"[Drama API] open ok account_id={account_id} items={len(result.get('items', []))}")
        return _ok(result)
    except Exception as e:
        logger.error(f"[Drama API] open 失败: {e}", exc_info=True)
        with _drama_pool_lock:
            _drama_pool.pop(account_id, None)
        try:
            run_drama_picker_async(session.close(), timeout=10)
        except Exception:
            pass
        return _err(f"打开剧集弹窗失败: {e}")


@weixin_gzh_bp.route('/drama_picker/search', methods=['POST'])
def drama_picker_search():
    data = request.get_json(silent=True) or {}
    account_id = (data.get('accountId') or '').strip()
    keyword = (data.get('keyword') or '').strip()
    s, err = _get_drama_session_or_404(account_id)
    if err:
        return err
    try:
        result = run_drama_picker_async(s.search(keyword), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Drama API] search 失败: {e}", exc_info=True)
        return _err(f"搜索失败: {e}")


@weixin_gzh_bp.route('/drama_picker/go_page', methods=['POST'])
def drama_picker_go_page():
    data = request.get_json(silent=True) or {}
    account_id = (data.get('accountId') or '').strip()
    page = int(data.get('page') or 1)
    s, err = _get_drama_session_or_404(account_id)
    if err:
        return err
    try:
        result = run_drama_picker_async(s.go_page(page), timeout=30)
        return _ok(result)
    except Exception as e:
        logger.error(f"[Drama API] go_page 失败: {e}", exc_info=True)
        return _err(f"翻页失败: {e}")


@weixin_gzh_bp.route('/drama_picker/close', methods=['POST'])
def drama_picker_close():
    data = request.get_json(silent=True) or {}
    account_id = (data.get('accountId') or '').strip()
    if not account_id:
        return _ok({"closed": True})
    with _drama_pool_lock:
        session = _drama_pool.pop(account_id, None)
    if session is None:
        return _ok({"closed": True})
    try:
        run_drama_picker_async(session.close(), timeout=10)
    except Exception as e:
        logger.warning(f"[Drama API] close 异常(忽略): {e}")
    return _ok({"closed": True})
