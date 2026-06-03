"""
快手图文发布相关 API 代理
使用 CloakBrowser 拦截音乐搜索接口。
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("kuaishou_image")

kuaishou_image_bp = Blueprint('kuaishou_image', __name__, url_prefix='/api/kuaishou-image')


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 4 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def run_async(coro):
    """在同步 Flask 上下文里跑 async 协程。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


@kuaishou_image_bp.route('/ping', methods=['GET'])
def ping():
    return jsonify({"code": 200, "msg": "kuaishou-image bp ok"})


KUAIHOU_MUSIC_SEARCH_URL = "https://cp.kuaishou.com/rest/cp/works/atlas/pc/upload/music/search"


@kuaishou_image_bp.route('/music-search', methods=['GET'])
def search_music():
    """搜索音乐 - 通过浏览器拦截网络请求获取结果"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '20')

    logger.info(f"[音乐搜索] 收到请求: account_id={account_id}, keyword={keyword}, count={count}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的快手账号"}), 404

        result = run_async(_search_music_via_browser(cookie_file, keyword, count))
        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500
    except Exception as e:
        logger.error(f"[音乐搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_music_via_browser(cookie_file: str, keyword: str, count: str = "20") -> dict:
    """用 CloakBrowser 打开图文发布页 → 上传测试图 → 等详情页 → 打开音乐抽屉 → 输入关键词 → 拦截 music-search API 响应。

    Note: ``count`` is accepted for API symmetry with douyin_image_bp.music-search
    but currently ignored — the intercepted URL is what Kuaishou's frontend
    uses, and we don't control its page size.
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 测试图 fallback
    test_image = Path(BASE_DIR / "test_kuaishou_music_search.jpg")
    if not test_image.exists():
        try:
            from PIL import Image
            img = Image.new('RGB', (1, 1), color='red')
            img.save(str(test_image), 'JPEG')
        except ImportError:
            test_image.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            captured = None

            async def handle_response(response):
                nonlocal captured
                if KUAIHOU_MUSIC_SEARCH_URL in response.url:
                    try:
                        data = await response.json()
                        captured = data
                    except Exception as e:
                        logger.error(f"[拦截] 解析失败: {e}")

            page.on("response", handle_response)

            # 1. 打开图文发布页
            logger.info("打开快手图文发布页...")
            await page.goto(
                "https://cp.kuaishou.com/article/publish/video?tabType=2",
                wait_until="domcontentloaded", timeout=60000,
            )
            await asyncio.sleep(2)

            # 2. 上传测试图
            logger.info("上传测试图...")
            # ?tabType=2 同时渲染视频/图片两个 tab 的上传按钮（隐藏 + 可见），
            # 用 :visible 过滤掉隐藏的「上传视频」按钮，只取可见的「上传图片」。
            # 后置选择器用 class*='upload-btn' 兜底：_upload-btn 的 hash 变化时仍能命中
            upload_btn = page.locator("button[class^='_upload-btn']:visible, button[class*='upload-btn']:visible").first
            await upload_btn.wait_for(state="visible", timeout=10000)
            async with page.expect_file_chooser() as fc_info:
                await upload_btn.click()
            fc = await fc_info.value
            await fc.set_files(str(test_image))
            await asyncio.sleep(2)

            # 3. 等待详情页
            start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start) < 60:
                if "publish/video" not in page.url:
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(3)

            # 4. 点击「添加音乐」按钮
            # 页面里有两个含「添加音乐」文本的元素：<label> 是标题（无 click handler），
            # 真正的可点击元素是带 +icon 的 div._button_3a3lq_1。点 label 不会打开抽屉。
            # 后置选择器按文本「添加音乐」兜底：_idle_ 类的 hash 变化时仍能命中
            logger.info("点击「添加音乐」按钮...")
            add_btn = page.locator("._idle_17rov_25 ._button_3a3lq_1, div._button_3a3lq_1:has-text('添加音乐')").first
            await add_btn.wait_for(state="visible", timeout=10000)
            await add_btn.click()
            await asyncio.sleep(2)

            # 5. 等待 drawer
            drawer = page.locator('div.ant-drawer-content-wrapper:visible').first
            await drawer.wait_for(state="visible", timeout=10000)
            await asyncio.sleep(1)

            # 6. 在搜索框输入
            logger.info(f"输入关键词: {keyword}")
            search_input = drawer.locator("input._search-input_19mmt_16, input[placeholder='搜索音乐']").first
            await search_input.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(keyword)
            await asyncio.sleep(4)  # 等接口响应

            # 7. 拿到 captured
            if not captured:
                return {"success": False, "error": "未捕获到音乐搜索响应"}

            music_list = (captured.get("data") or {}).get("musicList", [])
            result = {
                "musicList": [
                    {
                        "musicId": item.get("musicId", ""),
                        "title": item.get("title", ""),
                        "author": item.get("author", ""),
                        "duration": int(item.get("duration", 0)) // 1000,
                        "cover": (item.get("cover") or [{}])[0].get("url", ""),
                    }
                    for item in music_list
                ],
                "has_more": False,
                "cursor": "0",
            }
            return {"success": True, "data": result}
        finally:
            await context.close()
    finally:
        await browser.close()
