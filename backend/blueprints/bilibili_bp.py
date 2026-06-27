"""B 站创作者平台相关 API 代理。

仿 xiaohongshu_bp.py 的 DOM 解析模式:用 CloakBrowser 打开 B 站视频发布页 →
上传测试视频触发表单渲染 → 点「请选择合集」入口 → 解析下拉 DOM 的
season-item-title 文本(合集名) → 返回给前端下拉选项。

开发阶段:有头模式,便于观察。
"""

import asyncio
import os
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("bilibili")

bilibili_bp = Blueprint('bilibili', __name__, url_prefix='/api/bilibili')

# B 站视频上传页(与 impl/bilibili/platform.py 同源)
_BILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"

# 4 小时上传等待
_UPLOAD_WAIT_SECONDS = 4 * 60 * 60
_UPLOAD_WAIT_POLLS = _UPLOAD_WAIT_SECONDS * 2  # 0.5s/次

# 测试视频候选路径(BASE_DIR 已是 .../data)
_TEST_VIDEO_CANDIDATES = [
    str(BASE_DIR / "materials" / "2026" / "06" / "19" / "legacy-e751bf81.mp4"),
    str(Path(__file__).parent.parent / "scripts" / "legacy_fixture" / "videoFile" / "11111111-2222-3333-4444-555555555555_test1.mp4"),
]


def _pick_test_video() -> str:
    """挑一个真实存在且非空(>100字节)的测试视频文件。"""
    for p in _TEST_VIDEO_CANDIDATES:
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 100:
                return p
        except OSError:
            continue
    return ""


def _get_cookie_path(cookie_file: str) -> str:
    """获取 cookie 文件的完整路径。"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    """从数据库按账号 id 取 cookie 文件名;account_id 为空则取任一 B 站账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        # type=5 为 B 站
        cursor.execute("SELECT filePath FROM user_info WHERE type = 5 LIMIT 1")
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
# 合集列表 API
# ======================================================================

@bilibili_bp.route('/collections', methods=['GET'])
def list_collections():
    """获取账号的合集列表。

    Query params:
        account_id: 账号 id(用于取 cookie)

    流程:
        1. 用账号 cookie 打开 B 站视频上传页
        2. 上传测试视频触发表单渲染
        3. 点「请选择合集」入口,展开合集选择浮层
        4. 直接解析浮层 DOM 的 season-item-title 文本(合集名)
        5. 不点选(仅取列表),返回结果

    Returns:
        {"code": 200, "data": {"list": [...], "total": N}}
    """
    account_id = request.args.get('account_id')
    logger.info(f"[合集列表] 收到请求: account_id={account_id}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的 B 站账号"}), 404

        result = run_async(_fetch_collections_via_browser(cookie_file))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[合集列表] 成功,共 {data.get('total', 0)} 个合集")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集列表] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[合集列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_collections_via_browser(cookie_file: str) -> dict:
    """打开 B 站视频上传页,点「请选择合集」后直接解析下拉 DOM 拿合集列表。

    流程:
      1. 用账号 cookie 打开 B 站视频上传页
      2. 上传测试视频触发表单渲染(合集入口要表单渲染后才出现)
      3. 等待发布表单就绪(标题输入框出现)
      4. 点击「请选择合集」入口,展开合集选择浮层
      5. 直接解析浮层 DOM 的 season-item-title 文本(合集名)
      6. 不点选(仅取列表),返回结果

    DOM 结构(需求文档):
      season-list > season-content > seasons > season-item > season-item-title(合集名)
      底部 season-add 里有「创建合集」按钮,用 season-item-title 定位天然排除它。

    全程文案/placeholder/固定语义 class 定位,禁用 data-v 随机串。
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 开发阶段:有头模式,便于观察浏览器自动化过程
    browser = await create_browser(headless=False)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开 B 站视频上传页
            logger.info("[合集列表] 打开 B 站视频上传页...")
            try:
                await page.goto(_BILI_UPLOAD_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[合集列表] 页面加载(非致命): {e}")

            # 1.5 上传测试视频触发表单渲染
            # B 站视频上传的 input 在 iframe[name="videoUpload"] 里,
            # 与 platform.py 的 _upload_video_file 保持一致的 iframe 回退策略。
            test_video = _pick_test_video()
            if not test_video:
                return {
                    "success": False,
                    "error": "未找到可用的测试视频文件,无法触发上传表单渲染",
                }
            logger.info(f"[合集列表] 上传测试视频: {test_video}")
            try:
                uploaded = False
                # 先尝试 iframe 内的 input
                try:
                    upload_frame = page.frame_locator('iframe[name="videoUpload"]')
                    file_input = upload_frame.locator(
                        'input[type="file"][accept*="video"], input[type="file"]'
                    ).first
                    await file_input.set_input_files(test_video)
                    uploaded = True
                    logger.info("[合集列表] 通过 iframe 上传成功")
                except Exception:
                    pass
                # 回退:主页面的 input
                if not uploaded:
                    file_input = page.locator(
                        'input[type="file"][accept*="video"], input[type="file"]'
                    ).first
                    await file_input.set_input_files(test_video)
                    logger.info("[合集列表] 通过主页面 input 上传成功")
            except Exception as e:
                return {"success": False, "error": f"测试视频上传失败: {e}"}

            # 等待「上传完成」(B 站上传完成标志)
            logger.info("[合集列表] 等待视频上传完成(最多 4 小时)...")
            done_text = page.get_by_text("上传完成", exact=True)
            for _ in range(_UPLOAD_WAIT_POLLS):
                if await done_text.count() > 0:
                    break
                await asyncio.sleep(0.5)
            else:
                return {"success": False, "error": "视频上传超时(超过 4 小时)"}
            logger.info("[合集列表] 上传完成")

            # 等待发布表单渲染(标题输入框出现即代表表单就绪)
            logger.info("[合集列表] 等待发布表单渲染(标题输入框,最多 4 小时)...")
            title_input = page.locator('input[placeholder*="标题"]').first
            form_ready = False
            for _ in range(_UPLOAD_WAIT_POLLS):
                if await title_input.count() > 0:
                    form_ready = True
                    break
                await asyncio.sleep(0.5)
            if not form_ready:
                return {"success": False, "error": "发布表单未渲染(标题输入框未出现)"}
            logger.info("[合集列表] 发布表单已渲染")
            await asyncio.sleep(2)

            # 2. 点击「请选择合集」入口
            logger.info("[合集列表] 点击「请选择合集」入口...")
            entry = page.get_by_text("请选择合集", exact=True)
            if await entry.count() == 0:
                return {"success": False, "error": "未找到「请选择合集」入口"}
            await entry.first.click()
            logger.info("[合集列表] 已点击,等待合集浮层弹出...")
            await asyncio.sleep(1.5)

            # 3. 解析下拉 DOM —— season-item-title 是组件库固定语义 class(非 data-v 随机串)
            # DOM 结构: season-list > season-content > seasons > season-item > p.season-item-title
            titles = page.locator(".season-item-title")
            ready = False
            for _ in range(20):  # 最多等 10s
                if await titles.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "点击后未弹出合集选择浮层"}

            count = await titles.count()
            logger.info(f"[合集列表] 浮层出现 {count} 个合集,开始解析")
            items = []
            for i in range(count):
                name = (await titles.nth(i).inner_text()).strip()
                if not name:
                    continue
                # 排除「创建合集」按钮文案
                if name in ("创建合集", "请选择合集"):
                    continue
                items.append({"name": name})

            logger.info(f"[合集列表] 解析完成,共 {len(items)} 个合集")
            return {
                "success": True,
                "data": {"list": items, "total": len(items)},
            }
        finally:
            await context.close()
    finally:
        await browser.close()
