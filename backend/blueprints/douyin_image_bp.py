"""
抖音图文发布相关API代理
使用CloakBrowser来请求抖音API，避免反检测
"""

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("douyin_image")

douyin_image_bp = Blueprint('douyin_image', __name__, url_prefix='/api/douyin-image')


def _get_cookie_path(cookie_file: str) -> str:
    """获取cookie文件的完整路径"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str:
    """从数据库获取账号的cookie文件路径"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 3 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


async def _fetch_with_browser(cookie_file: str, url: str, base_url: str = "https://creator.douyin.com/") -> dict:
    """使用CloakBrowser发送请求"""
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 先打开基础URL，确保cookie生效
            await page.goto(base_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            # 使用fetch API请求目标URL
            escaped_url = url.replace("'", "\\'").replace('"', '\\"')

            # 根据URL域名设置Referer
            referer = base_url
            if "tsearch.amemv.com" in url:
                referer = "https://creator.douyin.com/"

            result = await page.evaluate(f"""
                async () => {{
                    try {{
                        const response = await fetch("{escaped_url}", {{
                            credentials: 'include',
                            headers: {{
                                'Accept': 'application/json',
                                'Referer': '{referer}',
                            }}
                        }});

                        // 先获取文本，再尝试解析JSON
                        const text = await response.text();

                        if (!response.ok) {{
                            return {{ success: false, error: `HTTP ${{response.status}}: ${{text.substring(0, 200)}}` }};
                        }}

                        try {{
                            const data = JSON.parse(text);
                            return {{ success: true, data: data }};
                        }} catch (jsonError) {{
                            return {{ success: false, error: `JSON解析失败: ${{jsonError.message}}, 响应内容: ${{text.substring(0, 200)}}` }};
                        }}
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }}
            """)

            return result
        finally:
            await context.close()
    finally:
        await browser.close()


def run_async(coro):
    """在Flask中运行异步函数"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@douyin_image_bp.route('/mix-list', methods=['GET'])
def get_mix_list():
    """获取用户的合集列表"""
    account_id = request.args.get('account_id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少account_id参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "账号不存在"}), 404

        url = "https://creator.douyin.com/web/api/mix/list/?status=0%2C2&count=15&cursor=0&aid=1128"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"获取合集列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/activity-list', methods=['GET'])
def get_activity_list():
    """获取官方活动列表"""
    account_id = request.args.get('account_id')

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        url = "https://creator.douyin.com/web/api/media/activity/get/?page=1&size=9999&need_challenge=1&aid=1128"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"获取活动列表失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/hotspot-search', methods=['GET'])
def search_hotspot():
    """搜索热点"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '50')

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        url = f"https://creator.douyin.com/aweme/v1/hotspot/search/?query={quote(keyword)}&count={count}&aid=1128"
        result = run_async(_fetch_with_browser(cookie_file, url))

        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        else:
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"搜索热点失败: {e}")
        return jsonify({"code": 500, "msg": str(e)}), 500


@douyin_image_bp.route('/music-search', methods=['GET'])
def search_music():
    """搜索音乐 - 通过浏览器拦截网络请求获取结果"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    cursor_val = request.args.get('cursor', '0')
    count = request.args.get('count', '20')

    logger.info(f"[音乐搜索] 收到请求: account_id={account_id}, keyword={keyword}, cursor={cursor_val}, count={count}")

    if not keyword:
        logger.warning("[音乐搜索] 缺少keyword参数")
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[音乐搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的抖音账号"}), 404

        logger.info(f"[音乐搜索] 开始浏览器搜索: keyword={keyword}")
        result = run_async(_search_music_via_browser(cookie_file, keyword, cursor_val, count))

        logger.info(f"[音乐搜索] 浏览器返回结果: success={result.get('success')}, data_keys={list(result.get('data', {}).keys()) if result.get('data') else 'None'}")

        if result.get("success"):
            music_list = result.get("data", {}).get("music", [])
            logger.info(f"[音乐搜索] 搜索成功，找到 {len(music_list)} 首音乐")
            return jsonify({"code": 200, "data": result["data"]})
        else:
            logger.error(f"[音乐搜索] 搜索失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500

    except Exception as e:
        logger.error(f"[音乐搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_music_via_browser(cookie_file: str, keyword: str, cursor_val: str = "0", count: str = "20") -> dict:
    """通过浏览器自动化搜索音乐，拦截网络请求获取结果"""
    cookie_path = _get_cookie_path(cookie_file)

    # 准备测试图片
    test_image = Path(BASE_DIR / "test_music_search.jpg")
    if not test_image.exists():
        # 创建一个最小的测试图片（1x1 像素的 JPEG）
        try:
            from PIL import Image
            img = Image.new('RGB', (1, 1), color='red')
            img.save(str(test_image), 'JPEG')
        except ImportError:
            # 如果没有 PIL，创建一个假文件
            test_image.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 拦截音乐搜索 API 响应
            captured_response = None

            async def handle_response(response):
                nonlocal captured_response
                if "tsearch.amemv.com/openapi/aweme/v1/music/search" in response.url:
                    try:
                        logger.info(f"[浏览器拦截] 捕获到音乐搜索请求: {response.url[:100]}...")
                        data = await response.json()
                        captured_response = data
                        logger.info(f"[浏览器拦截] 响应数据: status_code={data.get('status_code')}, music_count={len(data.get('music', []))}")
                    except Exception as e:
                        logger.error(f"[浏览器拦截] 解析响应失败: {e}")

            page.on("response", handle_response)

            # 1. 打开图文发布页面
            logger.info("打开图文发布页面...")
            await page.goto("https://creator.douyin.com/creator-micro/content/upload?default-tab=3", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # 2. 上传测试图片
            logger.info("上传测试图片...")
            # 查找文件上传 input
            upload_selectors = [
                'input[type="file"]',
                'input[accept*="image"]',
                '.upload-btn input[type="file"]',
            ]
            uploaded = False
            for selector in upload_selectors:
                try:
                    input_el = page.locator(selector).first
                    if await input_el.count() > 0:
                        await input_el.set_input_files(str(test_image))
                        uploaded = True
                        logger.info(f"图片上传成功，选择器: {selector}")
                        break
                except Exception as e:
                    continue

            if not uploaded:
                return {"success": False, "error": "未找到文件上传入口"}

            # 3. 等待跳转到发布界面
            logger.info("等待跳转到发布界面...")
            await page.wait_for_timeout(5000)

            # 检查是否跳转成功
            current_url = page.url
            if "upload" in current_url and "publish" not in current_url:
                # 可能需要点击发布按钮
                try:
                    publish_btn = page.locator('button:has-text("发布"), .publish-btn, [class*="publish"]').first
                    if await publish_btn.is_visible():
                        await publish_btn.click()
                        await page.wait_for_timeout(3000)
                except Exception:
                    pass

            # 4. 点击"选择音乐"按钮
            logger.info("点击选择音乐按钮...")
            # 根据用户提供的DOM结构，点击包含"选择音乐"文字的容器
            music_selectors = [
                '.action-Q1y01k',  # 精确匹配用户提供的class
                'span:has-text("选择音乐")',
                '[class*="container-right"]:has-text("选择音乐")',
                'text="选择音乐"',
            ]

            music_clicked = False
            for selector in music_selectors:
                try:
                    btn = page.locator(selector).first
                    if await btn.is_visible(timeout=5000):  # 增加等待时间
                        await btn.click()
                        music_clicked = True
                        logger.info(f"点击选择音乐按钮成功，选择器: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"选择器 {selector} 失败: {e}")
                    continue

            if not music_clicked:
                # 尝试通过坐标点击（如果文字可见）
                try:
                    music_text = page.locator('text="选择音乐"').first
                    if await music_text.is_visible(timeout=3000):
                        await music_text.click()
                        music_clicked = True
                        logger.info("通过文字定位点击选择音乐成功")
                except Exception:
                    pass

            if not music_clicked:
                return {"success": False, "error": "未找到选择音乐按钮"}

            # 5. 等待音乐抽屉打开
            logger.info("等待音乐抽屉打开...")
            await page.wait_for_timeout(3000)

            # 6. 在搜索框输入关键词
            logger.info(f"搜索音乐: {keyword}")
            search_selectors = [
                'input[placeholder="搜索音乐"]',  # 精确匹配
                'input[placeholder*="搜索音乐"]',
                '.music-search-jpUg0G input',  # 匹配用户提供的class
                '.semi-input[placeholder*="搜索"]',
                'input.semi-input',
            ]

            search_filled = False
            for selector in search_selectors:
                try:
                    input_el = page.locator(selector).first
                    if await input_el.is_visible(timeout=5000):
                        # 清空输入框
                        await input_el.clear()
                        # 输入关键词
                        await input_el.fill(keyword)
                        # 等待一下确保输入完成
                        await page.wait_for_timeout(500)
                        # 按回车触发搜索
                        await input_el.press("Enter")
                        search_filled = True
                        logger.info(f"搜索框输入成功，选择器: {selector}")
                        break
                except Exception as e:
                    logger.debug(f"搜索框选择器 {selector} 失败: {e}")
                    continue

            if not search_filled:
                return {"success": False, "error": "未找到搜索框"}

            # 7. 等待搜索结果
            logger.info("[搜索音乐] 等待搜索结果...")
            for i in range(50):  # 最多等待 5 秒
                if captured_response:
                    break
                await page.wait_for_timeout(100)
                if i % 10 == 0:  # 每秒打印一次日志
                    logger.info(f"[搜索音乐] 等待中... {i*100}ms")

            if captured_response:
                music_list = captured_response.get("music", [])
                logger.info(f"[搜索音乐] ✅ 成功拦截到结果，共 {len(music_list)} 首音乐")
                if music_list:
                    logger.info(f"[搜索音乐] 第一首: {music_list[0].get('title', 'N/A')} - {music_list[0].get('author', 'N/A')}")
                return {"success": True, "data": captured_response}
            else:
                logger.error("[搜索音乐] ❌ 未能拦截到搜索结果")
                return {"success": False, "error": "未能拦截到搜索结果"}

        finally:
            await context.close()
    finally:
        await browser.close()
        # 清理测试图片
        try:
            if test_image.exists():
                test_image.unlink()
        except Exception:
            pass
