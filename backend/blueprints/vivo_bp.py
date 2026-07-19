"""VIVO 内容创作平台相关 API 代理。

仿 ``xiaohongshu_bp.py`` 的浏览器自动化模式:用 CloakBrowser 打开 VIVO
发布页 → 上传测试视频触发表单渲染 → 在位置搜索框输入关键词 →
直接解析下拉 DOM 把结果转发给前端。

VIVO 位置搜索接口未公开、可能带签名,故采用浏览器自动化方案(与小红书
POI 搜索同源),不直接 fetch。

接口(vivo.md):
    发布页: https://www.kaixinkan.com.cn/#/content/uploads
    位置入口: .sel-position-module
    下拉: .position-list li,每项 .position-name + .position-info
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
from services.test_video import get_test_video

logger = get_channel_logger("vivo")

vivo_bp = Blueprint('vivo', __name__, url_prefix='/api/vivo')

# VIVO 视频发布页(与 impl/vivo/platform.py 同源)
_VIVO_UPLOAD_URL = "https://www.kaixinkan.com.cn/#/content/uploads"


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    """从数据库按账号 id 取 cookie 文件名;account_id 为空则取任意 VIVO 账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        # type=16 为 VIVO
        cursor.execute("SELECT filePath FROM user_info WHERE type = 16 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


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


# ======================================================================
# 位置搜索 API
# ======================================================================

@vivo_bp.route('/search-position', methods=['GET'])
def search_position():
    """搜索 VIVO 添加位置。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    位置关键词(必填)

    流程(vivo.md):
        1. 用账号 cookie 打开 VIVO 视频发布页
        2. 上传测试视频触发发布表单渲染(位置入口要表单渲染后才出现)
        3. 等待 .short-video-edit-component 渲染完成
        4. 点 .sel-position-module 展开位置输入框
        5. 输入 keyword 触发搜索(逐字符 type 触发 input 事件)
        6. 直接解析下拉 .position-list li 的 .position-name + .position-info
        7. 不点选、不提交,直接返回结果

    Returns:
        {"code": 200, "data": {"position_list": [{name, address}, ...]}}
    """
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    logger.info(f"[位置搜索] 收到请求: account_id={account_id}, keyword={keyword}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[位置搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的 VIVO 账号"}), 404

        result = run_async(_fetch_positions_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(
                f"[位置搜索] 成功,共 {len(data.get('position_list', []))} 个结果"
            )
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[位置搜索] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[位置搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_positions_via_browser(cookie_file: str, keyword: str) -> dict:
    """打开 VIVO 发布页 → 上传测试视频 → 输入关键词 → 解析下拉 DOM。

    全程用产品语义 class / 文案定位,禁用 data-v 随机串。
    """
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开发布页
            logger.info("[位置搜索] 打开 VIVO 视频发布页...")
            try:
                await page.goto(_VIVO_UPLOAD_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[位置搜索] 页面加载(非致命): {e}")

            # 2. 上传测试视频触发表单渲染(位置入口要表单渲染后才出现)
            test_video = get_test_video()
            if not test_video:
                return {
                    "success": False,
                    "error": "未找到可用的测试视频文件,无法触发发布表单渲染",
                }
            logger.info(f"[位置搜索] 上传测试视频触发表单: {test_video}")
            try:
                file_input = page.locator('input[type="file"][accept*="video"]').first
                if not await file_input.count():
                    file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(test_video)
            except Exception as e:
                return {"success": False, "error": f"测试视频上传失败: {e}"}

            # 3. 轮询等待视频上传完成 + 发布表单渲染
            # 用 .short-video-edit-component(视频描述/封面/位置等表单容器)作为
            # 表单就绪标志。视频上传需要时间(上传中→上传完成),等待给足 4 小时。
            logger.info("[位置搜索] 等待视频上传完成 + 发布表单渲染(最多 4 小时)...")
            edit_component = page.locator(".short-video-edit-component").first
            ready = False
            for _ in range(_UPLOAD_WAIT_POLLS):
                if await edit_component.count() > 0:
                    ready = True
                    break
                # 顺带检测上传成功标记
                if await page.locator('.success-text:has-text("上传成功")').count() > 0:
                    await asyncio.sleep(2)
                    if await edit_component.count() > 0:
                        ready = True
                        break
                await asyncio.sleep(0.5)
            if not ready:
                return {
                    "success": False,
                    "error": "视频上传后发布表单未渲染(可能上传失败或被风控)",
                }
            logger.info("[位置搜索] 发布表单已渲染")
            await asyncio.sleep(1)

            # 4. 点 .sel-position-module 展开位置输入框
            logger.info("[位置搜索] 点击位置入口...")
            pos_module = page.locator(".sel-position-module").first
            if await pos_module.count() == 0:
                return {"success": False, "error": "未找到位置入口(.sel-position-module)"}
            await pos_module.click()
            await asyncio.sleep(1)

            # 5. 输入关键词触发搜索(逐字符 type 触发 input 事件)
            logger.info(f"[位置搜索] 输入关键词: {keyword}")
            await page.keyboard.type(keyword, delay=80)
            await asyncio.sleep(2)

            # 6. 等待下拉列表 .position-list li 出现
            position_items = page.locator(".position-list li")
            ready = False
            for _ in range(60):  # 最多等 30s
                if await position_items.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "输入后未出现位置下拉选项"}

            # 7. 逐项解析 .position-name + .position-info
            count = await position_items.count()
            logger.info(f"[位置搜索] 下拉出现 {count} 个选项,开始解析")
            items = []
            for i in range(count):
                li = position_items.nth(i)
                name_el = li.locator(".position-name").first
                addr_el = li.locator(".position-info").first
                name = ""
                if await name_el.count() > 0:
                    # .position-name 内可能有 <i> 图标,用 inner_text 取纯文本
                    name = (await name_el.inner_text() or "").strip()
                address = ""
                if await addr_el.count() > 0:
                    address = (await addr_el.inner_text() or "").strip()
                if not name:
                    continue
                items.append({"name": name, "address": address})

            logger.info(f"[位置搜索] 成功,共 {len(items)} 个结果")
            return {"success": True, "data": {"position_list": items}}
        finally:
            await context.close()
    finally:
        await browser.close()


# 视频上传/发布表单渲染的最大等待时长 —— 视频文件可能很大、网络可能很慢,
# 这里给足 4 小时(14400s),按 0.5s 轮询即 28800 次。
_UPLOAD_WAIT_SECONDS = 4 * 60 * 60  # 4 小时
_UPLOAD_WAIT_POLLS = _UPLOAD_WAIT_SECONDS * 2  # 0.5s/次 → 28800 次
