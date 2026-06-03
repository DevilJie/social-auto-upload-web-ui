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
        cursor.execute("SELECT filePath FROM user_info WHERE id = ? AND type = 4", (account_id,))
        row = cursor.fetchone()
        if row:
            conn.close()
            return row[0]
    # fallback：任意一个可用的快手账号
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


KUAISHOU_MUSIC_SEARCH_URL = "https://cp.kuaishou.com/rest/cp/works/atlas/pc/upload/music/search"


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
                url = response.url
                # 记录所有 POST/PUT 请求（通常是 API 调用）
                if response.request.method in ("POST", "PUT"):
                    logger.info(f"[网络] {response.request.method} {url[:120]}")
                if KUAISHOU_MUSIC_SEARCH_URL in url:
                    logger.info(f"[拦截] 命中音乐搜索接口: {url[:120]}")
                    try:
                        data = await response.json()
                        captured = data
                        logger.info(f"[拦截] 解析成功，musicList 长度: {len((data.get('data') or {}).get('musicList', []))}")
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
            upload_btn = page.locator("button[class^='_upload-btn']:visible, button[class*='upload-btn']:visible").first
            await upload_btn.wait_for(state="visible", timeout=10000)
            async with page.expect_file_chooser() as fc_info:
                await upload_btn.click()
            fc = await fc_info.value
            await fc.set_files(str(test_image))
            await asyncio.sleep(2)

            # 3. 等待编辑页加载（URL 不会变，等「添加音乐」按钮出现即可）
            logger.info("[步骤3] 等待编辑页加载...")
            await page.locator("div:text-is('添加音乐')").first.wait_for(state="visible", timeout=30000)
            logger.info(f"[步骤3] 编辑页已加载, URL: {page.url}")

            # 截图：进入详情页后的状态
            shot_path = str(Path(BASE_DIR / "debug_after_upload.png"))
            await page.screenshot(path=shot_path, full_page=True)
            logger.info(f"[步骤3] 截图已保存: {shot_path}")

            # 4. 点击「添加音乐」按钮
            # 调试：列出所有含「添加音乐」文本的元素
            logger.info("[步骤4] 开始查找「添加音乐」...")
            count = await page.locator("*:has-text('添加音乐')").count()
            logger.info(f"[步骤4] 含「添加音乐」的元素数量: {count}")
            for i in range(min(count, 10)):
                el = page.locator("*:has-text('添加音乐')").nth(i)
                info = await el.evaluate("e => ({ tag: e.tagName, cls: e.className.substring(0,80), text: e.textContent.trim().substring(0,50), visible: e.offsetParent !== null })")
                logger.info(f"  [{i}] <{info['tag']}> class=\"{info['cls']}\" text=\"{info['text']}\" visible={info['visible']}")

            # 找到含「添加音乐」文本的 div，点击其父级按钮容器（不依赖 class）
            text_div = page.locator("div:text-is('添加音乐')").first
            try:
                await text_div.wait_for(state="visible", timeout=10000)
                logger.info("[步骤4] 找到「添加音乐」div，准备点击父级...")
                parent = text_div.locator("xpath=..")
                parent_info = await parent.evaluate("e => ({ tag: e.tagName, cls: e.className.substring(0,80) })")
                logger.info(f"[步骤4] 父级: <{parent_info['tag']}> class=\"{parent_info['cls']}\"")
                await parent.click()
                logger.info("[步骤4] 点击成功!")
            except Exception as e:
                logger.error(f"[步骤4] 点击失败: {e}")
                # fallback: 直接 JS 点击
                logger.info("[步骤4] 尝试 JS fallback...")
                await page.evaluate("""
                    const els = document.querySelectorAll('*');
                    for (const el of els) {
                        if (el.textContent.trim() === '添加音乐' && el.parentElement) {
                            el.parentElement.click(); break;
                        }
                    }
                """)
                logger.info("[步骤4] JS fallback 执行完毕")
            await asyncio.sleep(2)

            # 5. 等待 drawer
            logger.info("[步骤5] 等待音乐抽屉出现...")
            drawer = page.locator('div.ant-drawer-content-wrapper:visible').first
            try:
                await drawer.wait_for(state="visible", timeout=10000)
                logger.info("[步骤5] 音乐抽屉已出现")
            except Exception as e:
                logger.error(f"[步骤5] 音乐抽屉未出现: {e}")
                # 截图看看当前页面状态
                shot2 = str(Path(BASE_DIR / "debug_no_drawer.png"))
                await page.screenshot(path=shot2, full_page=True)
                logger.info(f"[步骤5] 截图已保存: {shot2}")
                return {"success": False, "error": f"音乐抽屉未出现: {e}"}
            await asyncio.sleep(1)

            # 6. 在搜索框输入关键词
            # 先重置 captured，丢弃打开抽屉时的默认搜索结果
            captured = None
            logger.info(f"[步骤6] 输入关键词: {keyword}")
            search_input = drawer.locator("input[placeholder='搜索音乐']").first
            try:
                await search_input.click()
            except Exception as e:
                logger.error(f"[步骤6] 搜索框点击失败: {e}")
                all_inputs = drawer.locator("input")
                input_count = await all_inputs.count()
                logger.info(f"[步骤6] 抽屉内 input 数量: {input_count}")
                for i in range(input_count):
                    inp = all_inputs.nth(i)
                    placeholder = await inp.get_attribute("placeholder")
                    visible = await inp.is_visible()
                    logger.info(f"  input[{i}] placeholder='{placeholder}' visible={visible}")
                return {"success": False, "error": f"搜索框点击失败: {e}"}

            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(keyword)
            logger.info("[步骤6] 关键词已输入，等待搜索接口响应...")

            # 等待新的搜索结果（最多 10 秒）
            for _ in range(20):
                if captured is not None:
                    break
                await asyncio.sleep(0.5)
            logger.info(f"[步骤6] 等待结束, captured={captured is not None}")

            # 7. 拿到 captured
            logger.info(f"[步骤7] captured={captured is not None}")
            if not captured:
                logger.warning("[步骤7] 未捕获到音乐搜索响应，可能接口未触发或被拦截")
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
