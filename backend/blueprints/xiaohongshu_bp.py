"""小红书创作者平台相关 API 代理。

仿 ``toutiao_bp.py`` / ``douyin_image_bp.py`` 的浏览器拦截模式:
用 CloakBrowser 打开小红书发布页 → 监听平台自身发起的接口响应 →
把结果转发给前端。

合集列表 / POI 搜索接口都带签名(edith 接口),无法直接 fetch,
必须依赖发布页 JS 自身发起的请求,故采用 ``page.on("response")`` 监听。

接口(文档 ~/优化.md):
    合集列表: https://edith.xiaohongshu.com/api/sns/v1/note/collection/pc/list_v2
    POI 搜索: https://edith.xiaohongshu.com/web_api/sns/v1/local/poi/creator/search
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from urllib.parse import quote

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("xiaohongshu")

xiaohongshu_bp = Blueprint('xiaohongshu', __name__, url_prefix='/api/xiaohongshu')

# 小红书视频发布页(与 impl/xiaohongshu/platform.py 同源)
_XHS_PUBLISH_VIDEO_URL = (
    "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video"
)
# 要监听的接口 URL 片段
_COLLECTION_API_FRAGMENT = "/api/sns/v1/note/collection/pc/list_v2"
_POI_API_FRAGMENT = "/web_api/sns/v1/local/poi/creator/search"

# 视频上传/发布表单渲染的最大等待时长 —— 视频文件可能很大、网络可能很慢,
# 这里给足 4 小时(14400s),按 0.5s 轮询即 28800 次。宁可久等也不误判超时。
_UPLOAD_WAIT_SECONDS = 4 * 60 * 60  # 4 小时
_UPLOAD_WAIT_POLLS = _UPLOAD_WAIT_SECONDS * 2  # 0.5s/次 → 28800 次

# 触发发布表单渲染用的测试视频(上传后页面才会出现「内容来源声明」等控件)。
# BASE_DIR 已是 .../data,故直接拼 materials/...;再用 fixture 兜底。
_TEST_VIDEO_CANDIDATES = [
    str(BASE_DIR / "materials" / "2026" / "06" / "19" / "legacy-e751bf81.mp4"),
    str(Path(__file__).parent.parent / "scripts" / "legacy_fixture" / "videoFile" / "11111111-2222-3333-4444-555555555555_test1.mp4"),
]


def _pick_test_video() -> str:
    """挑一个真实存在且非空(>100字节)的测试视频文件。"""
    import os
    for p in _TEST_VIDEO_CANDIDATES:
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 100:
                return p
        except OSError:
            continue
    return ""


def _upload_test_video(page, video_path: str):
    """上传测试视频触发发布表单渲染。

    复用 impl/xiaohongshu/platform.py 的上传 input 定位:
      div[class^='upload-content'] input[class='upload-input']
    (upload-input 是固定 class,非随机串)
    """
    return page.locator(
        "div[class^='upload-content'] input[class='upload-input']"
    ).set_input_files(video_path)


# ======================================================================
# cookie 辅助(与 douyin_image_bp 一致)
# ======================================================================

def _get_cookie_path(cookie_file: str) -> str:
    """获取 cookie 文件的完整路径。"""
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    """从数据库按账号 id 取 cookie 文件名;account_id 为空则取任一小红书账号。"""
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        # type=1 为小红书
        cursor.execute("SELECT filePath FROM user_info WHERE type = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


# ======================================================================
# run_async helper(与 alipay_bp / toutiao_bp 一致)
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


# ======================================================================
# 合集列表 API
# ======================================================================

@xiaohongshu_bp.route('/collections', methods=['GET'])
def list_collections():
    """获取账号的合集列表。

    Query params:
        account_id: 账号 id(用于取 cookie)

    流程:
        1. 用账号 cookie 打开小红书视频发布页
        2. 发布页 JS 会自动请求 collection/pc/list_v2(带签名)
        3. 监听该 response,解析 collection_info_list
        4. 标准化为 [{id, name, note_num, ...}] 返回

    Returns:
        {"code": 200, "data": {"list": [...], "total": N}}
    """
    account_id = request.args.get('account_id')
    logger.info(f"[合集列表] 收到请求: account_id={account_id}")

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[合集列表] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的小红书账号"}), 404

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
    """打开小红书发布页,点「加入合集」后直接解析下拉 DOM 拿合集列表。

    流程(与视频发布时的合集逻辑同源):
      1. 用账号 cookie 打开小红书视频发布页
      2. 先上传一个测试视频触发表单渲染(合集入口要表单渲染后才出现)
      3. 等待发布表单就绪(标题输入框出现)
      4. 点击「加入合集」入口,展开合集选择浮层
      5. 直接解析浮层 DOM 的 item-label 文本(合集名)
      6. 不点选(仅取列表),返回结果

    DOM 结构(优化.md):
      collection-plugin-popover-content > item > item-content > item-label(合集名)
      底部 popover-footer 里有「创建合集」按钮,用 item-label 定位天然排除它。

    全程文案/placeholder/固定语义 class 定位,禁用 data-v 随机串。
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 无头模式:合集 DOM 解析逻辑已验证通过,无需观察
    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开发布页
            logger.info("[合集列表] 打开小红书视频发布页...")
            try:
                await page.goto(_XHS_PUBLISH_VIDEO_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[合集列表] 页面加载(非致命): {e}")

            # 1.5 先上传一个测试视频 —— 合集入口要表单渲染后才出现。
            test_video = _pick_test_video()
            if not test_video:
                return {
                    "success": False,
                    "error": "未找到可用的测试视频文件,无法触发发布表单渲染",
                }
            logger.info(f"[合集列表] 上传测试视频触发表单: {test_video}")
            try:
                await _upload_test_video(page, test_video)
            except Exception as e:
                return {"success": False, "error": f"测试视频上传失败: {e}"}

            # 等待发布表单渲染完成(标题输入框出现即代表上传完成、表单就绪)
            title_input = page.locator('input[placeholder*="填写标题"]')
            logger.info("[合集列表] 等待视频上传完成 + 发布表单渲染(最多 4 小时)...")
            ready = False
            for _ in range(_UPLOAD_WAIT_POLLS):
                if await title_input.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {
                    "success": False,
                    "error": "视频上传后发布表单未渲染(标题输入框未出现)",
                }
            logger.info("[合集列表] 发布表单已渲染")
            await asyncio.sleep(1)

            # 2. 点击「加入合集」入口,展开合集选择浮层
            # 入口用文案定位:含「加入合集」字样的区域,向上找可点击父级。
            logger.info("[合集列表] 点击「加入合集」入口...")
            entry = page.get_by_text("加入合集", exact=True)
            if await entry.count() == 0:
                entry = page.get_by_text("选择合集", exact=False).first
            if await entry.count() == 0:
                return {"success": False, "error": "未找到「加入合集」入口"}
            entry_card = entry.locator(
                "xpath=ancestor::*[contains(.,'选择合集')][1]"
            ).first
            try:
                await entry_card.click(timeout=5000)
            except Exception:
                await entry.first.click(timeout=5000)
            logger.info("[合集列表] 已点击,等待合集浮层弹出...")
            await asyncio.sleep(1.5)

            # 3. 等待合集浮层出现 —— 容器 collection-plugin-popover-content(固定语义 class)
            popover = page.locator(".collection-plugin-popover-content")
            ready = False
            for _ in range(20):  # 最多等 10s
                if await popover.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "点击加入合集后未弹出合集选择浮层"}

            # 4. 解析每个合集项 —— 定位 item-content 下的 item-label 文本(合集名)。
            # DOM: item > item-content > item-label。item-label 是固定语义 class(非随机串)。
            labels = popover.locator(".item-label")
            count = await labels.count()
            logger.info(f"[合集列表] 浮层出现 {count} 个合集,开始解析")
            items = []
            for i in range(count):
                name = (await labels.nth(i).inner_text()).strip()
                if not name:
                    continue
                # 排除入口/底部按钮文案(非真实合集名):
                # 「选择合集」(入口按钮)、「加入合集」(入口标题)、「创建合集」(底部按钮)
                if name in ("选择合集", "加入合集", "创建合集"):
                    continue
                items.append({
                    "name": name,
                    # DOM 里只有合集名,无 id/note_num;发布时按 name 匹配选项即可
                })

            logger.info(f"[合集列表] 解析完成,共 {len(items)} 个合集")
            return {
                "success": True,
                "data": {"list": items, "total": len(items)},
            }
        finally:
            await context.close()
    finally:
        await browser.close()


# ======================================================================
# POI 搜索 API(改造点 4 内容来源声明使用)
# ======================================================================

@xiaohongshu_bp.route('/search-poi', methods=['GET'])
def search_poi():
    """搜索拍摄地点 POI。

    Query params:
        account_id: 账号 id(用于取 cookie)
        keyword:    地点关键词(必填)

    流程:
        1. 用账号 cookie 打开小红书视频发布页
        2. 在发布页触发「内容来源声明 → 自主拍摄」流程打开拍摄地点弹窗
           (这里简化:直接监听 poi/creator/search;但该接口需弹窗内输入触发,
            故采用 page.evaluate 携 cookie fetch 兜底)
        3. 解析 poi_list

    Returns:
        {"code": 200, "data": {"poi_list": [...]}}
    """
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    logger.info(f"[POI搜索] 收到请求: account_id={account_id}, keyword={keyword}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            logger.warning(f"[POI搜索] 账号不存在: {account_id}")
            return jsonify({"code": 404, "msg": "没有可用的小红书账号"}), 404

        result = run_async(_fetch_poi_via_browser(cookie_file, keyword))

        if result.get("success"):
            data = result.get("data", {})
            logger.info(f"[POI搜索] 成功,共 {len(data.get('poi_list', []))} 个结果")
            return jsonify({"code": 200, "data": data})
        else:
            logger.error(f"[POI搜索] 失败: {result.get('error')}")
            return jsonify({
                "code": 500, "msg": result.get("error", "请求失败"),
            }), 500
    except Exception as e:
        logger.error(f"[POI搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _fetch_poi_via_browser(cookie_file: str, keyword: str) -> dict:
    """完整弹窗交互模式获取 POI 搜索结果(直接解析 DOM,不监听 HTTP)。

    真实走发布页操作流程(有头模式,便于观察验证):
      1. 用账号 cookie 打开小红书视频发布页
      2. 先上传一个测试视频触发表单渲染
      3. 点「内容来源声明」一级下拉 → 选「内容来源声明」
      4. 二级下拉 → 选「自主拍摄」
      5. 弹窗出现 → 在「拍摄地点」输入框输入 keyword(逐字符 type 触发搜索)
      6. 直接解析下拉 DOM 的 li[role="option"] 项,提取 name + subname 返回
      7. 不点选、不确认(仅搜索),直接返回结果

    全程文案/placeholder/role 定位,禁用 class/data-v。
    """
    cookie_path = _get_cookie_path(cookie_file)

    # 无头模式:POI 搜索 DOM 解析逻辑已验证通过,无需观察
    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            # 1. 打开发布页
            logger.info("[POI搜索] 打开小红书视频发布页...")
            try:
                await page.goto(_XHS_PUBLISH_VIDEO_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[POI搜索] 页面加载(非致命): {e}")

            # 1.5 先上传一个测试视频 —— 否则发布页停在「上传区」,
            # 「内容来源声明/自主拍摄」等控件不会渲染出来。
            test_video = _pick_test_video()
            if not test_video:
                return {
                    "success": False,
                    "error": "未找到可用的测试视频文件,无法触发发布表单渲染",
                }
            logger.info(f"[POI搜索] 上传测试视频触发表单: {test_video}")
            try:
                await _upload_test_video(page, test_video)
            except Exception as e:
                return {"success": False, "error": f"测试视频上传失败: {e}"}

            # 轮询等待发布表单渲染完成 —— 视频上传需要时间(上传中→上传完成),
            # 上传完成后页面才会渲染标题/描述/内容声明等发布表单控件。
            # 用标题输入框作为表单就绪标志(placeholder 固定为「填写标题」)。
            # 视频可能很大,等待给足 4 小时,避免误判超时。
            title_input = page.locator('input[placeholder*="填写标题"]')
            logger.info("[POI搜索] 等待视频上传完成 + 发布表单渲染(最多 4 小时)...")
            ready = False
            for _ in range(_UPLOAD_WAIT_POLLS):  # 最多等 4 小时
                if await title_input.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {
                    "success": False,
                    "error": "视频上传后发布表单未渲染(标题输入框未出现,可能上传失败或被风控)",
                }
            logger.info("[POI搜索] 发布表单已渲染")
            await asyncio.sleep(1)

            # 2. 一级下拉:点「添加内容类型声明」→ 选「内容来源声明」
            # 注意:该文案是 <div class="d-select-placeholder"> 里的纯文本,
            # 不是 <input> 的 placeholder 属性,不能用 get_by_placeholder!
            # 用 get_by_text 定位文本,再向上找可点击的 d-select 容器。
            logger.info("[POI搜索] 点击内容类型声明下拉...")
            trigger_text = page.get_by_text("添加内容类型声明", exact=True)
            if await trigger_text.count() == 0:
                return {"success": False, "error": "未找到「添加内容类型声明」占位文案"}
            # 向上找 d-select 容器(d-select 是组件库固定语义 class,非随机串)
            trigger = trigger_text.locator(
                "xpath=ancestor::div[contains(@class,'d-select')][1]"
            )
            await trigger.first.click()
            await asyncio.sleep(1.2)

            option = page.get_by_text("内容来源声明", exact=True)
            if await option.count() == 0:
                return {"success": False, "error": "未找到「内容来源声明」一级选项"}
            await option.first.click()
            logger.info("[POI搜索] 已选「内容来源声明」")
            await asyncio.sleep(1.2)

            # 3. 二级下拉:选「自主拍摄」
            logger.info("[POI搜索] 选择「自主拍摄」...")
            second_opt = page.get_by_text("自主拍摄", exact=True)
            if await second_opt.count() == 0:
                return {"success": False, "error": "未找到「自主拍摄」二级选项"}
            await second_opt.first.click()
            logger.info("[POI搜索] 已选「自主拍摄」,等待弹窗")
            await asyncio.sleep(1.5)

            # 4. 弹窗:在拍摄地点输入框输入 keyword
            # 用 type 逐字符输入(而非 fill) —— 小红书地点搜索是 el-autocomplete,
            # 监听键盘 input 事件才发请求;fill 直接设 value 不触发 input,接口不会请求。
            logger.info(f"[POI搜索] 在拍摄地点输入: {keyword}")
            loc_input = page.get_by_placeholder("下拉选择地点", exact=False)
            if await loc_input.count() == 0:
                return {"success": False, "error": "未找到拍摄地点输入框(自主拍摄弹窗未出现?)"}
            await loc_input.first.click()
            await loc_input.first.type(keyword, delay=80)  # 逐字符,触发 input 事件
            logger.info("[POI搜索] 已输入,等待下拉 DOM 渲染...")

            # 5. 等待下拉选项出现 —— 直接解析 DOM,不监听 HTTP(更稳,不依赖接口 URL/签名)。
            # 下拉结构: el-autocomplete-suggestion__list > li[role="option"],每项含
            #   .name(地名) + .subname(地址)。用 role="option" 语义属性定位选项。
            option_items = page.locator('li[role="option"]')
            ready = False
            for _ in range(120):  # 最多等 60s
                if await option_items.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                return {"success": False, "error": "输入后未出现地点下拉选项(接口未触发或网络慢)"}

            # 6. 逐项解析:每个 li 下有固定 class 的 div —— name(地名)+ subname(地址)。
            # DOM 结构: <div class="item"><div class="name">地名</div><div class="subname">地址</div></div>
            # 注:name/subname 是 Element 组件固定 class(非 data-v 随机串),稳定可用。
            count = await option_items.count()
            logger.info(f"[POI搜索] 下拉出现 {count} 个选项,开始解析")
            items = []
            for i in range(count):
                li = option_items.nth(i)
                name_el = li.locator("div.name").first
                sub_el = li.locator("div.subname").first
                name = (await name_el.inner_text()).strip() if await name_el.count() > 0 else ""
                address = (await sub_el.inner_text()).strip() if await sub_el.count() > 0 else ""
                if not name:
                    continue
                items.append({
                    "name": name,
                    "full_address": address,
                    "address": address,
                })

            logger.info(f"[POI搜索] 成功,共 {len(items)} 个结果")
            return {"success": True, "data": {"poi_list": items}}
        finally:
            await context.close()
    finally:
        await browser.close()
