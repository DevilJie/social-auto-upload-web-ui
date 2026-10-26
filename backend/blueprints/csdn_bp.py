"""CSDN 内容创作平台相关 API 代理。

仿 ``toutiao_bp.py`` 的浏览器代理模式:用 CloakBrowser(账号登录态)打开
CSDN 文章编辑页 → 点开「文章标签」抽屉 → 抓取推荐标签 / 输入关键词后的
联想下拉,把结果转发给前端。

抽屉结构(2026-10-26 实测, 见 data/tmp/csdn_tag_test/drawer_*.html):
    触发按钮   .mark_selection button.tag__btn-tag
    抽屉容器   .mark-selection-popper
    输入框     input[placeholder*="Enter键入可添加自定义标签"]
    联想列表   .el_mcm-autocomplete-suggestion__list > li   (文本即标签名)
    推荐/分类  .el_mcm-tabs__item(43 个分类 tab) / .el_mcm-tag__content(推荐标签)
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

logger = get_channel_logger("csdn")

csdn_bp = Blueprint('csdn', __name__, url_prefix='/api/csdn')

_CSDN_EDITOR_URL = "https://mp.csdn.net/mp_blog/creation/editor"


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库取账号 cookie 文件名。account_id 为空时取任意一个 CSDN 账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 15 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None


# ======================================================================
# /api/csdn/tag-search
# ======================================================================

@csdn_bp.route('/tag-search', methods=['GET'])
def search_tags():
    """CSDN 文章标签搜索 —— 登录态浏览器抓标签抽屉联想下拉。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    标签关键词;为空则返回抽屉「推荐标签」

    Returns:
        {"code": 200, "data": {"list": ["python", "ipython", ...]}}
    """
    account_id = request.args.get('account_id')
    keyword = (request.args.get('keyword', '') or '').strip()

    logger.info(
        f"[标签搜索] 收到请求: account_id={account_id}, keyword={keyword!r}"
    )

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[标签搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的 CSDN 账号"}), 404

        result = run_async(_search_tags_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[标签搜索] 成功,共 {len(data.get('list', []))} 个")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[标签搜索] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[标签搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_tags_via_browser(cookie_file: str, keyword: str) -> dict:
    """打开 CSDN 编辑页 → 开标签抽屉 → 抓推荐/联想标签。"""
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()
            await page.set_viewport_size({"width": 1680, "height": 1000})
            await page.goto(_CSDN_EDITOR_URL, timeout=60000)

            # 等编辑器 + 标签触发按钮就绪
            trigger = page.locator(
                ".mark_selection button.tag__btn-tag"
            ).first
            try:
                await trigger.wait_for(state="visible", timeout=30000)
            except Exception as exc:
                return {
                    "success": False,
                    "error": f"CSDN 编辑页/标签入口未就绪: {exc}",
                }
            await trigger.scroll_into_view_if_needed(timeout=10000)
            await trigger.click(timeout=15000)
            await asyncio.sleep(2)

            pop = page.locator(".mark-selection-popper").first
            if not await pop.count():
                return {"success": False, "error": "标签抽屉未打开"}

            items: list = []
            if keyword:
                inp = page.locator(
                    'input[placeholder*="Enter键入可添加自定义标签"]'
                ).first
                await inp.click(timeout=10000)
                await inp.fill("")
                await inp.press_sequentially(keyword, delay=100)
                await asyncio.sleep(3)  # 等联想接口
                items = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      return [
                        ...document.querySelectorAll(
                          '.el_mcm-autocomplete-suggestion__list'
                          + ' > li[role=option]'),
                      ].filter(vis)
                       .map((e) => (e.innerText || '').trim())
                       .filter(Boolean);
                    }"""
                )
            else:
                # 无关键词: 返回抽屉推荐标签(排除分类 tab)
                items = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      return [
                        ...document.querySelectorAll('.el_mcm-tag__content'),
                      ].filter(vis)
                       .map((e) => (e.innerText || '').trim())
                       .filter((t) => t && t.length <= 20);
                    }"""
                )

            # 去重保序
            seen = set()
            tags = []
            for t in items:
                if t and t not in seen:
                    seen.add(t)
                    tags.append(t)

            return {"success": True, "data": {"list": tags}}
        finally:
            await context.close()
    finally:
        await browser.close()


# ======================================================================
# run_async helper(与 toutiao_bp 一致)
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
