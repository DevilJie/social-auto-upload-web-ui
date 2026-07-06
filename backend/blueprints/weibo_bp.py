"""微博创作者平台相关 API 代理。

用 CloakBrowser 打开微博视频上传页 → 上传测试视频触发表单渲染 →
点击合集开关 → 解析合集列表 DOM → 返回给前端下拉选项。

微博合集入口与 B 站不同:需先在表单里切换「加入合集」开关(.woo-switch-input),
切换后才会展开合集列表(_top2_* 容器,每项 input[value] 含合集名 + 集数)。
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
from impl.weibo.platform import WeiboPlatform
from services.test_video import get_test_video

logger = get_channel_logger("weibo")

weibo_bp = Blueprint('weibo', __name__, url_prefix='/api/weibo')

# 微博视频上传页(与 impl/weibo/platform.py 同源)
_WEIBO_UPLOAD_URL = "https://weibo.com/upload/channel"


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id):
    """从 user_info 表查微博账号(type=11)的 cookie 文件名。"""
    db_path = BASE_DIR / "db" / "database.db"
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()
        if account_id:
            cursor.execute(
                "SELECT filePath FROM user_info WHERE type = 11 AND id = ? LIMIT 1",
                (account_id,),
            )
        else:
            cursor.execute("SELECT filePath FROM user_info WHERE type = 11 LIMIT 1")
        row = cursor.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def run_async(coro):
    """在 Flask 同步路由里跑 async 协程(照抄 bilibili_bp)。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 已有 loop 在跑(Flask + Waitress 常见)→ 起新线程跑
            import threading
            result = {}
            def _run():
                new_loop = asyncio.new_event_loop()
                try:
                    result['value'] = new_loop.run_until_complete(coro)
                except Exception as e:
                    result['error'] = e
                finally:
                    new_loop.close()
            t = threading.Thread(target=_run)
            t.start()
            t.join()
            if 'error' in result:
                raise result['error']
            return result.get('value')
        else:
            return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@weibo_bp.route('/collections', methods=['GET'])
def list_collections():
    """获取微博账号的视频合集列表。

    流程(参考需求文档 DOM):
      1. 用账号 cookie 打开微博视频上传页
      2. 上传测试视频触发表单渲染(复用 WeiboPlatform._upload_video_file)
      3. 等表单就绪(发布按钮可见)
      4. 点击合集开关 .woo-switch-input(切换「加入合集」)
      5. 解析合集列表 DOM,从每个 input[value] 提取合集名

    Returns:
        {"code": 200, "data": {"list": [{"name": "..."}], "total": N}}
    """
    account_id = request.args.get('account_id')
    logger.info(f"[合集列表] 收到请求: account_id={account_id}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的微博账号"}), 404

        result = run_async(_fetch_collections_via_browser(cookie_file))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[合集列表] 成功,共 {data.get('total', 0)} 个合集")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[合集列表] 失败: {result.get('error')}")
            return jsonify({"code": 500, "msg": result.get("error", "请求失败")})
    except Exception as e:
        logger.error(f"[合集列表] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_collections_via_browser(cookie_file: str) -> dict:
    """打开微博上传页,上传测试视频触发表单,切换合集开关,解析合集 DOM。

    DOM 结构(需求文档):
      合集开关: label.woo-switch-main > input.woo-switch-input[type=checkbox]
      合集列表: div._scroll_* > div._top2_* (每项)
        每项内: input[type=text][value="合集名(共N集)"]
    """
    cookie_path = _get_cookie_path(cookie_file)

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开微博视频上传页
            logger.info("[合集列表] 打开微博视频上传页...")
            try:
                await page.goto(_WEIBO_UPLOAD_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[合集列表] 页面加载(非致命): {e}")

            # 2. 上传测试视频触发表单渲染(复用微博 platform 的上传逻辑)
            test_video = get_test_video()
            if not test_video:
                return {"success": False, "error": "未找到测试视频文件"}
            logger.info(f"[合集列表] 上传测试视频触发表单: {test_video}")

            await WeiboPlatform._upload_video_file(page, test_video)
            logger.info("[合集列表] 测试视频已选择,等待表单渲染(不等上传完成)...")

            # 3. 直接等合集开关出现 = 表单已渲染就绪(不需要等视频真正上传完成)
            #    微博表单是同页面渲染,选完视频后表单控件很快出现,合集开关 label.woo-switch-main 是稳定锚点
            logger.info("[合集列表] 等待合集开关出现...")
            switch_label = page.locator('label.woo-switch-main').first
            try:
                await switch_label.wait_for(state="visible", timeout=30000)
            except Exception:
                return {"success": False, "error": "未找到合集开关(label.woo-switch-main),表单未渲染"}

            # 4. 点击合集开关(label.woo-switch-main —— input 是 hidden,点击 label 才生效)
            logger.info("[合集列表] 点击合集开关...")
            await switch_label.click()
            logger.info("[合集列表] 已切换合集开关,等待合集列表展开...")
            await asyncio.sleep(1.5)

            # 5. 解析合集列表 DOM —— 每个合集项的 input[value] 形如 "AI(共0集)"
            #    定位合集列表容器内的文本输入(排除开关本身)
            #    合集项结构: div._top2_* > ... > input[type=text][value="合集名(共N集)"]
            album_inputs = page.locator('input[type="text"][value*="集"]')
            try:
                await album_inputs.first.wait_for(state="attached", timeout=10000)
            except Exception:
                # 没有合集也是正常情况(账号可能没创建过合集)
                logger.info("[合集列表] 未展开合集列表(账号可能无合集)")
                return {"success": True, "data": {"list": [], "total": 0}}

            count = await album_inputs.count()
            logger.info(f"[合集列表] 发现 {count} 个合集项,开始解析")
            items = []
            for i in range(count):
                try:
                    raw = await album_inputs.nth(i).get_attribute("value")
                    if not raw:
                        continue
                    # value 形如 "AI(共0集)" → name="AI", 提取集数
                    name = raw
                    note_num = None
                    if "（共" in raw:
                        name = raw.split("（共")[0].strip()
                    elif "(共" in raw:
                        name = raw.split("(共")[0].strip()
                    items.append({"name": name, "raw": raw})
                except Exception as e:
                    logger.info(f"[合集列表] 解析第 {i} 项失败(跳过): {e}")
                    continue

            logger.info(f"[合集列表] 解析完成,共 {len(items)} 个合集")
            return {"success": True, "data": {"list": items, "total": len(items)}}
        finally:
            try:
                await context.close()
            except Exception:
                pass
    finally:
        try:
            await browser.close()
        except Exception:
            pass
