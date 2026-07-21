"""
Channels (视频号) platform implementation.

100% CloakBrowser — all browser operations use the new engine via
``BasePlatform.create_browser()`` / ``BasePlatform.create_context()``
and shared utilities from ``backend/impl/_utils.py``.
"""

import asyncio
import json
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger

logger = get_channel_logger("channels")

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_tencent_profile,
)
from ..base_platform import BasePlatform

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENCENT_LOGIN_URL = "https://channels.weixin.qq.com/login.html"
TENCENT_PLATFORM_URL = "https://channels.weixin.qq.com/platform"
TENCENT_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"
TENCENT_MANAGE_URL = "https://channels.weixin.qq.com/platform/post/list"

# 调试开关:True = 走到发布按钮时只输出参数日志、不实际点击发布(便于检查内容);
# False = 正常点击发布。验证完发布内容无误后改回 False 即可。
_PUBLISH_DRY_RUN = False


def _format_short_title(origin_title: str) -> str:
    """Format a title for the Channels short-title field (max 16 chars)."""
    allowed_special_chars = "《》“”:+?%°"
    filtered_chars = [
        char
        if char.isalnum() or char in allowed_special_chars
        else " " if char == "," else ""
        for char in origin_title
    ]
    formatted_string = "".join(filtered_chars)

    if len(formatted_string) > 16:
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        formatted_string += " " * (6 - len(formatted_string))

    return formatted_string


async def _is_login_completed(page) -> bool:
    """Detect whether the user has completed the QR-code login flow.

    登录成功后页面会从 ``/login.html`` 跳转到 ``/platform/*``（创作中心首页
    或其子页）。这里只看 URL：进入 ``/platform`` 且不在 ``/login`` 即视为
    登录完成。不依赖宽泛文本匹配，避免登录页文案误判。
    """
    url = page.url
    return "/platform" in url and "/login" not in url


# ---------------------------------------------------------------------------
# Upload helpers
# ---------------------------------------------------------------------------

async def _upload_video_file(page, file_path: str) -> None:
    """Upload the video file via the file-input element."""
    file_input = page.locator('input[type="file"]')
    await file_input.set_input_files(file_path)


async def _fill_title_and_tags(page, title: str, tags: list[str]) -> None:
    """Type hashtags into the rich-text description editor.

    视频号的主标题不再填入正文/描述区——title 由 _set_short_title 填到
    「短标题」输入框；正文/描述区只放描述和话题标签。
    """
    await page.locator("div.input-editor").click()
    for tag in tags:
        await page.keyboard.type("#" + tag)
        await page.keyboard.press("Space")
    logger.info(f"[填写标题] added {len(tags)} hashtags to description editor")


async def _fill_description(page, desc: str) -> None:
    """Type the description into the rich-text description editor.

    描述填入正文/描述区（与话题标签同区），title 不再混入此处。
    """
    if not desc:
        return
    await page.locator("div.input-editor").click()
    # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
    await clear_and_type(page, desc)
    logger.info(f"[填写简介] added description ({len(desc)} chars)")


async def _set_short_title(page, title: str, short_title: str | None = None) -> None:
    """Fill the short-title input if present.

    短标题输入框 placeholder 为「填写短标题有机会获得更多流量」，
    旧选择器（按「短标题」文字定位兄弟节点）匹配不到，导致短标题未填入。
    改为按 placeholder 直接定位，并保留兜底选择器。
    """
    value = short_title or _format_short_title(title)
    # 主选择器：placeholder 直接匹配（新版 DOM）
    selectors = [
        'input[placeholder*="填写短标题"]',
        'input[placeholder*="短标题"]',
    ]
    for selector in selectors:
        short_title_element = page.locator(selector).first
        if await short_title_element.count():
            await short_title_element.fill(value)
            logger.info(f"[填写标题] short title filled: {value!r} ({selector})")
            return
    # 兜底：旧版按「短标题」文字 + 兄弟 input
    try:
        legacy = (
            page.get_by_text("短标题", exact=True)
            .locator("..")
            .locator("xpath=following-sibling::div")
            .locator('span input[type="text"]')
        )
        if await legacy.count():
            await legacy.fill(value)
            logger.info(f"[填写标题] short title filled (legacy): {value!r}")
            return
    except Exception:
        pass
    logger.info("[填写标题] short title input not found, skipping")


async def _apply_collection(page, collection_name: str = "") -> None:
    """选择指定合集(按名称匹配);无名称时选第一个可用合集。

    DOM 定位(禁用 data-v 随机串):
      入口:「选择合集」文案(get_by_text)
      下拉选项:option-item > item > div.name(合集名)
    """
    # 点击「选择合集」展开下拉
    entry = page.get_by_text("选择合集", exact=True)
    if await entry.count() == 0:
        logger.info("[设置合集] 未找到「选择合集」入口,跳过")
        return
    await entry.first.click()
    await asyncio.sleep(1)

    # 解析下拉选项
    names = page.locator(".option-item .item .name")
    count = await names.count()
    if count == 0:
        logger.info("[设置合集] 无可用合集,跳过")
        return

    if collection_name:
        # 按名称匹配
        for i in range(count):
            name = (await names.nth(i).inner_text()).strip()
            if name == collection_name:
                await names.nth(i).locator("xpath=ancestor::div[contains(@class,'option-item')][1]").first.click()
                logger.info("[设置合集] 已选择合集: %s", collection_name)
                return
        logger.warning("[设置合集] 未找到合集: %s", collection_name)
    else:
        # 选第一个可用合集(原有逻辑)
        if count > 1:
            await names.nth(1).locator("xpath=ancestor::div[contains(@class,'option-item')][1]").first.click()
            logger.info("[设置合集] 已选择第一个可用合集")


async def _apply_location(page, location_name: str = "") -> None:
    """选择指定位置(按名称精确匹配);空字符串时跳过,保持默认「不显示位置」。

    DOM(用户实际抓取,weui 框架):
      入口: div.position-display-wrap (显示当前位置的内层卡片,点击展开搜索面板)
      搜索框: input[placeholder="搜索附近位置"] (.weui-desktop-form__input)
      下拉: div.common-option-list-wrap .option-item
        - 第一项 .option-item.active 永远是「不显示位置」(遍历时跳过 index 0)
        - 每项内 .location-item-info .name 是位置名
        - 已选项内含 .yes-icon svg

    策略(与 _apply_collection 一致):
      - 空值 → 直接 return(视频号默认就是「不显示位置」)
      - 找不到精确匹配 → warning + return(保持当前状态)
    """
    if not location_name:
        return  # 空值跳过,默认就是「不显示位置」

    # 1. 点击位置卡片展开搜索面板
    position_wrap = page.locator("div.position-display-wrap").first
    if await position_wrap.count() == 0:
        logger.info("[设置位置] 未找到位置卡片,跳过")
        return
    await position_wrap.click()
    await asyncio.sleep(1)

    # 2. 在搜索框输入关键字(打字机效果,触发视频号自身的搜索请求)
    search_input = page.locator('input[placeholder="搜索附近位置"]').first
    if await search_input.count() == 0:
        logger.warning("[设置位置] 未找到位置搜索框,跳过")
        return
    await search_input.click()
    await clear_and_type(page, location_name, delay=50)
    await asyncio.sleep(2)  # 等下拉刷新

    # 3. 在下拉项里找精确匹配(index 0 是「不显示位置」,跳过)
    options = page.locator("div.common-option-list-wrap .option-item")
    count = await options.count()
    for i in range(1, count):  # 跳过 index 0
        opt = options.nth(i)
        name_el = opt.locator(".location-item-info .name").first
        if await name_el.count() == 0:
            continue
        try:
            name = (await name_el.inner_text()).strip()
        except Exception:
            continue
        if name == location_name:
            await opt.click()
            logger.info("[设置位置] 已选择位置: %s", location_name)
            return
    logger.warning("[设置位置] 未找到位置: %s", location_name)


async def _apply_original_statement(page, category: str | None = None) -> None:
    """Mark the video as original if the option is available."""
    # Simple checkbox
    if await page.get_by_label("视频为原创").count():
        await page.get_by_label("视频为原创").check()

    # Original declaration terms
    try:
        label_visible = await page.locator(
            'label:has-text("我已阅读并同意 《视频号原创声明使用条款》")'
        ).is_visible()
    except Exception:
        label_visible = False

    if label_visible:
        await page.get_by_label(
            "我已阅读并同意 《视频号原创声明使用条款》"
        ).check()
        await page.get_by_role("button", name="声明原创").click()

    # Advanced original declaration with category dropdown
    if await page.locator('div.label span:has-text("声明原创")').count() and category:
        checkbox = page.locator(
            "div.declare-original-checkbox input.ant-checkbox-input"
        )
        if not await checkbox.is_disabled():
            await checkbox.click()
            checked_locator = page.locator(
                "div.declare-original-dialog "
                "label.ant-checkbox-wrapper.ant-checkbox-wrapper-checked:visible"
            )
            if not await checked_locator.count():
                await page.locator(
                    "div.declare-original-dialog input.ant-checkbox-input:visible"
                ).click()

            original_type_form = page.locator(
                'div.original-type-form > div.form-label:has-text("原创类型"):visible'
            )
            if await original_type_form.count():
                await page.locator("div.form-content:visible").click()
                await page.locator(
                    "div.form-content:visible "
                    "ul.weui-desktop-dropdown__list "
                    f'li.weui-desktop-dropdown__list-ele:has-text("{category}")'
                ).first.click()
                await page.wait_for_timeout(1000)

            declare_button = page.locator('button:has-text("声明原创"):visible')
            if await declare_button.count():
                await declare_button.click()


# ---------------------------------------------------------------------------
# 视频标注(mark tag):发布页「选择视频标注」下拉
#
# DOM(用户实际抓取, 禁用 data-v 随机串):
#   入口: .mark-tag-select .select-display (点击展开 .mark-tag-options)
#   选项: .mark-tag-option > .option-main (文案精确匹配 tagName)
#
# 选「内容为自行拍摄」会弹 .weui-desktop-dialog:
#   标题: 「添加拍摄时间和地点」
#   拍摄时间: input[placeholder="请选择拍摄时间"] + weui 日历面板
#   拍摄地点: .location-cascader 级联(国家 -> 省 -> 市), 子级点击后懒加载
# 选「内容为转载」也会弹 dialog, 内含转载来源 input。
#
# 策略: 所有选项(含「无需标注」)都去页面真正选中; 弹窗/子字段全程容错,
# 找不到或匹配失败时 warning 跳过, 不中断发布。
# ---------------------------------------------------------------------------

_SHOOT_TAG = "内容为自行拍摄"
_REPOST_TAG = "内容为转载"


async def _select_mark_tag_option(page, tag_name: str) -> bool:
    """展开视频标注下拉并点击指定选项, 返回是否成功选中。

    点选「内容为自行拍摄 / 内容为转载」会触发二级弹窗, 弹窗由调用方
    (_fill_shoot_info_dialog / _fill_repost_source_dialog)处理。
    """
    select = page.locator(".mark-tag-select").first
    if await select.count() == 0:
        logger.warning("[视频标注] 未找到标注下拉入口, 跳过")
        return False

    # 点击 display 展开下拉(若已展开, 再点一次会收起, 故按状态决定)
    try:
        is_open = "is-open" in (await select.get_attribute("class") or "")
    except Exception:
        is_open = False
    if not is_open:
        await select.locator(".select-display").first.click()
        await asyncio.sleep(0.6)

    options = page.locator(".mark-tag-options .mark-tag-option")
    count = await options.count()
    for i in range(count):
        try:
            main_text = (await options.nth(i).locator(".option-main").first.inner_text(timeout=1000)).strip()
        except Exception:
            continue
        if main_text == tag_name:
            await options.nth(i).click()
            logger.info("[视频标注] 已选择标注: %s", tag_name)
            await asyncio.sleep(0.8)  # 等待可能的二级弹窗
            return True
    logger.warning("[视频标注] 下拉中未找到选项: %s", tag_name)
    return False


async def _fill_shoot_date_in_dialog(dialog, shoot_date: str) -> None:
    """在自行拍摄弹窗内填入拍摄时间(YYYY-MM-DD)。

    复用 weui datepicker 交互(与 _set_schedule_time 同款), 但 scope 限定在
    弹窗内, 避免误触发表单的定时发布选择器。
    """
    if not shoot_date:
        logger.info("[视频标注] 未提供拍摄时间, 跳过日期填写")
        return

    try:
        from datetime import datetime
        dt = datetime.strptime(shoot_date, "%Y-%m-%d")
    except ValueError:
        logger.warning("[视频标注] 拍摄时间格式非法(需 YYYY-MM-DD): %s, 跳过", shoot_date)
        return

    date_input = dialog.locator('input[placeholder="请选择拍摄时间"]').first
    if await date_input.count() == 0:
        logger.warning("[视频标注] 未找到拍摄时间输入框, 跳过")
        return
    await date_input.click()
    await asyncio.sleep(0.5)

    # 翻到目标月份(weui 面板按年/月标签判断)
    target_year = dt.strftime("%Y年")
    target_month = dt.strftime("%m月")
    for _ in range(24):  # 最多翻 24 个月
        try:
            labels = dialog.locator("span.weui-desktop-picker__panel__label")
            n = await labels.count()
            year_txt = (await labels.nth(0).inner_text(timeout=1000)).strip() if n > 0 else ""
            month_txt = (await labels.nth(1).inner_text(timeout=1000)).strip() if n > 1 else ""
            if year_txt == target_year and month_txt == target_month:
                break
        except Exception:
            pass
        nxt = dialog.locator("button.weui-desktop-btn__icon__right").first
        if await nxt.count():
            await nxt.click()
            await asyncio.sleep(0.2)
        else:
            break

    # 点对应日期(跳过 disabled / faded 占位)
    cells = dialog.locator("table.weui-desktop-picker__table a")
    total = await cells.count()
    for i in range(total):
        try:
            el = cells.nth(i)
            cls = await el.evaluate("e => e.className")
            if "weui-desktop-picker__disabled" in cls:
                continue
            txt = (await el.inner_text(timeout=1000)).strip()
            if txt == str(dt.day):
                await el.click()
                logger.info("[视频标注] 拍摄时间已填入: %s", shoot_date)
                await asyncio.sleep(0.3)
                return
        except Exception:
            continue
    logger.warning("[视频标注] 未在日历中找到可选日期: %s", shoot_date)


async def _fill_shoot_region_in_dialog(dialog, region_path: list[str]) -> None:
    """在自行拍摄弹窗内逐级选择拍摄地点级联菜单。

    region_path 形如 ['中国', '广东', '深圳']; 叶子国家(无省市)传 ['日本'] 即止。
    子级菜单点击后才懒加载, 故每级点完等子菜单出现再匹配下一级。

    交互时序(视频号 weui 级联):
      1. 点击 inner-button 展开第一级(国家, 共 240 项)
      2. 点国家 → 若有子级则展开下一级; 若是叶子则级联面板自动关闭
      3. 选到叶子后, .weui-desktop-dropdown-menu 消失 → 级联选择完成
      4. 调用方据此再点弹窗的「确认」按钮

    性能: 不用逐项 inner_text 遍历(240 项极慢), 改用 get_by_text 精确定位。
    """
    if not region_path:
        logger.info("[视频标注] 未提供拍摄地点, 跳过级联选择")
        return

    cascader = dialog.locator(".location-cascader").first
    if await cascader.count() == 0:
        logger.warning("[视频标注] 未找到拍摄地点级联组件, 跳过")
        return

    # 展开第一级(点击 inner-button 触发下拉)
    trigger = cascader.locator(".weui-desktop-form__dropdowncascade__dt__inner-button").first
    try:
        await trigger.click()
        await asyncio.sleep(0.8)  # 等第一级(240 国)渲染
    except Exception:
        logger.warning("[视频标注] 无法展开拍摄地点级联, 跳过")
        return

    # 逐级匹配: 用 get_by_text 精确定位当前可见菜单项(避免遍历 240 国)
    for level, target_name in enumerate(region_path):
        target_name = str(target_name).strip()
        # 级联项文本在 .weui-desktop-dropdown__list-ele__text 内, 用精确文本定位
        # scope 限定在 cascader 内, 避免误触其它下拉
        item = cascader.locator(
            ".weui-desktop-dropdown__list-ele__text"
        ).filter(has_text=target_name).first
        # 子级懒加载, 最多等 ~3s 让目标项出现
        try:
            await item.wait_for(state="visible", timeout=3000)
        except Exception:
            logger.warning("[视频标注] 拍摄地点第 %d 级未找到: %s", level + 1, target_name)
            return
        try:
            await item.click()
            logger.info("[视频标注] 拍摄地点第 %d 级已选: %s", level + 1, target_name)
        except Exception as e:
            logger.warning("[视频标注] 拍摄地点第 %d 级点击失败: %s (%s)", level + 1, target_name, e)
            return
        await asyncio.sleep(0.5)  # 等下一级懒加载/面板关闭

    # 选到叶子后, 级联下拉菜单(.weui-desktop-dropdown-menu)应自动消失。
    # 等它消失再返回, 让调用方安全地点「确认」(否则级联面板可能盖住确认按钮)。
    menu = cascader.locator(".weui-desktop-dropdown-menu").first
    for _ in range(20):  # 最多等 ~2s
        try:
            if await menu.count() == 0 or not await menu.is_visible():
                logger.info("[视频标注] 拍摄地点级联已收起, 选择完成: %s", " / ".join(map(str, region_path)))
                return
        except Exception:
            return
        await asyncio.sleep(0.1)
    logger.info("[视频标注] 拍摄地点级联仍未收起(已选 %s), 继续执行", " / ".join(map(str, region_path)))


async def _confirm_mark_tag_dialog(page, dialog=None) -> bool:
    """点击视频标注弹窗的「确定」按钮并关闭弹窗, 返回是否成功。

    视频号规则: 拍摄时间和拍摄地点都填完前, 确定按钮是 disabled 状态。
    故这里要等按钮从禁用变为可用(最多 ~5s), 再点击。
    1.txt 实测: 按钮文案是「确定」(非「确认」), class 含 weui-desktop-btn_disabled,
    位于弹窗 .weui-desktop-dialog__ft 内的 .weui-desktop-btn_wrp。

    Args:
        dialog: 若传入, 只在该弹窗 scope 内找确定按钮, 避免页面上多个弹窗
                (如封面裁剪/级联残留) 时点错。不传则退化为全局 .first。
    """
    scope = dialog if dialog is not None else page
    # 弹窗底部主按钮(优先匹配文案「完成」/「确定」, 兜底「确认」/ 主按钮)
    # 转载弹窗用「完成」, 自行拍摄弹窗用「确定」。
    selectors = (
        'div.weui-desktop-dialog__ft button:has-text("完成")',
        'div.weui-desktop-dialog__ft button:has-text("确定")',
        'div.weui-desktop-dialog__ft button:has-text("确认")',
        'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary',
        'button.weui-desktop-btn_primary:has-text("完成")',
        'button.weui-desktop-btn_primary:has-text("确定")',
    )
    btn = None
    for selector in selectors:
        try:
            cand = scope.locator(selector).first
            if await cand.count() and await cand.is_visible():
                btn = cand
                logger.info("[视频标注] 定位到确定按钮: %s", selector)
                break
        except Exception:
            continue
    if btn is None:
        logger.warning("[视频标注] 未找到弹窗确定按钮")
        return False

    # 等待按钮从 disabled 变为可用(拍摄信息填完后才解锁)
    for _ in range(25):  # 最多等 ~5s
        try:
            cls = await btn.get_attribute("class") or ""
            if "weui-desktop-btn_disabled" not in cls:
                break
        except Exception:
            break
        await asyncio.sleep(0.2)
    else:
        logger.warning("[视频标注] 确定按钮仍为禁用态(拍摄信息可能未填全), 仍尝试点击")

    try:
        await btn.click()
        logger.info("[视频标注] 弹窗已确定, 等待关闭")
        # 等弹窗消失(优先用传入的 dialog, 否则全局第一个)
        target = dialog if dialog is not None else page.locator("div.weui-desktop-dialog").first
        try:
            await target.wait_for(state="hidden", timeout=5000)
            logger.info("[视频标注] 弹窗已关闭")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.warning("[视频标注] 点击确定按钮失败: %s", e)
        return False


async def _fill_shoot_info_dialog(page, shoot_date: str, shoot_region: list[str]) -> None:
    """选「内容为自行拍摄」后, 在弹窗里填拍摄时间 + 拍摄地点并确认。"""
    dialog = page.locator("div.weui-desktop-dialog").filter(has_text="添加拍摄时间和地点").first
    try:
        await dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        logger.warning("[视频标注] 自行拍摄弹窗未出现, 跳过子字段填写")
        return
    logger.info("[视频标注] 自行拍摄弹窗已出现, 开始填写拍摄信息")

    await _fill_shoot_date_in_dialog(dialog, shoot_date)
    await _fill_shoot_region_in_dialog(dialog, shoot_region)
    # 把 dialog 传进去, 限定确定按钮的查找 scope, 避免误点其它弹窗
    await _confirm_mark_tag_dialog(page, dialog)


async def _fill_repost_source_dialog(page, repost_source: str) -> None:
    """选「内容为转载」后, 在弹窗里填转载来源(选填)并点「完成」。

    转载弹窗 DOM(用户实际抓取):
      标题: <h3>添加转载来源</h3>
      输入: <textarea class="repost-textarea" placeholder="在此处填写转载来源...">
      底部: 取消 / 完成(初始 disabled, 填入内容后解锁)
    """
    dialog = page.locator("div.weui-desktop-dialog").filter(has_text="添加转载来源").first
    try:
        await dialog.wait_for(state="visible", timeout=5000)
    except Exception:
        # 兜底: 用第一个可见 dialog
        dialog = page.locator("div.weui-desktop-dialog").first
        if not await dialog.count():
            logger.warning("[视频标注] 转载弹窗未出现, 跳过")
            return
    logger.info("[视频标注] 转载弹窗已出现, 开始填写转载来源")

    if repost_source:
        # 转载来源是 textarea(非 input), 用 class 或 placeholder 精确定位
        textarea_selectors = (
            'textarea.repost-textarea',
            'textarea[placeholder*="转载来源"]',
            'textarea:visible',
        )
        filled = False
        for selector in textarea_selectors:
            try:
                ta = dialog.locator(selector).first
                if await ta.count() and await ta.is_visible():
                    await ta.click()
                    await ta.fill("")
                    await ta.type(repost_source, delay=20)
                    logger.info("[视频标注] 转载来源已填入: %s", repost_source)
                    filled = True
                    await asyncio.sleep(0.5)  # 等「完成」按钮解锁
                    break
            except Exception:
                continue
        if not filled:
            logger.warning("[视频标注] 未找到转载来源输入框, 仅确认弹窗")
    else:
        logger.info("[视频标注] 未提供转载来源, 直接确认弹窗")

    await _confirm_mark_tag_dialog(page, dialog)


async def _apply_mark_tag(
    page,
    tag_name: str,
    shoot_date: str = "",
    shoot_region: list[str] | None = None,
    repost_source: str = "",
) -> None:
    """选择视频标注下拉项, 并在需要时处理二级弹窗。

    所有选项(含「无需标注」)都会去页面下拉里真正选中, 不因默认值跳过。
    """
    tag_name = (tag_name or "无需标注").strip()
    shoot_region = shoot_region or []
    logger.info("[视频标注] 开始设置, tag=%r, shoot_date=%r, region=%s, repost=%r",
                tag_name, shoot_date, shoot_region, repost_source)

    selected = await _select_mark_tag_option(page, tag_name)
    if not selected:
        return

    if tag_name == _SHOOT_TAG:
        await _fill_shoot_info_dialog(page, shoot_date, shoot_region)
    elif tag_name == _REPOST_TAG:
        await _fill_repost_source_dialog(page, repost_source)
    # 其他选项(含「无需标注」)无需二级弹窗, 选完即止


async def _wait_for_upload_complete(page, file_path: str) -> None:
    """Poll until the publish button becomes enabled (upload finished).

    If an upload error is detected, the failed file is deleted and
    re-uploaded automatically.
    """
    while True:
        try:
            publish_button = page.get_by_role("button", name="发表")
            button_class = await publish_button.get_attribute("class")
            if button_class and "weui-desktop-btn_disabled" not in button_class:
                logger.info("[上传视频] video upload complete")
                break

            logger.info("[上传视频] uploading video...")
            await asyncio.sleep(2)

            # Check for upload errors
            upload_failed = await page.locator("div.status-msg.error").count()
            delete_button = await page.locator(
                'div.media-status-content div.tag-inner:has-text("删除")'
            ).count()
            if upload_failed and delete_button:
                logger.info("[上传视频] upload error detected, retrying")
                await page.locator(
                    'div.media-status-content div.tag-inner:has-text("删除")'
                ).click()
                await page.get_by_role("button", name="删除", exact=True).click()
                await _upload_video_file(page, file_path)
        except Exception:
            logger.info("[上传视频] uploading video...")
            await asyncio.sleep(2)


# ---------------------------------------------------------------------------
# 封面设置阻塞等待：视频号在视频/封面处理中，悬停或点击封面区域会弹出
# weui-desktop-popover 提示「文件上传中...」/「预览图生成中...」，此时无法编辑封面，
# 必须无限等待该提示消失后才能继续。
# ---------------------------------------------------------------------------

# 需要阻塞的 popover 文案关键词（支持「后面还有其他文字」的模糊匹配）
_COVER_BLOCKING_KEYWORDS = ("文件上传中", "预览图生成中")


async def _wait_for_cover_ready(page, *, action: str = "") -> None:
    """检测并无限等待封面相关的阻塞型 popover 消失。

    视频号在视频上传/封面预览图生成期间，悬停或点击封面入口会弹出
    ``<div class="weui-desktop-popover__desc">文件上传中...`` 或
    ``预览图生成中...`` 提示，此时无法编辑封面。本函数无限轮询，直到
    该类提示消失才返回。

    Args:
        action: 触发场景描述，仅用于日志（如 "点击封面入口前"）。
    """
    popover = page.locator("div.weui-desktop-popover__desc")
    blocking = None
    try:
        count = await popover.count()
        for i in range(count):
            try:
                text = (await popover.nth(i).inner_text(timeout=1000)).strip()
            except Exception:
                continue
            if any(kw in text for kw in _COVER_BLOCKING_KEYWORDS):
                blocking = text
                break
    except Exception:
        blocking = None

    if not blocking:
        return

    logger.info(f"[设置封面] 封面阻塞提示出现({action}):「{blocking}」，开始无限等待...")
    waited = 0
    while True:
        await asyncio.sleep(1)
        waited += 1
        still_blocking = None
        try:
            count = await popover.count()
            for i in range(count):
                try:
                    text = (await popover.nth(i).inner_text(timeout=1000)).strip()
                except Exception:
                    continue
                if any(kw in text for kw in _COVER_BLOCKING_KEYWORDS):
                    still_blocking = text
                    break
        except Exception:
            still_blocking = None
        if not still_blocking:
            logger.info(f"[设置封面] 封面阻塞提示已消失，等待耗时 {waited}s，继续执行({action})")
            return
        if waited % 10 == 0:
            logger.info(f"[设置封面] 封面阻塞等待中({action}):「{still_blocking}」... ({waited}s)")


async def _set_thumbnail(page, thumbnail_path: str | None, thumbnail_landscape_path: str | None = None, thumbnail_portrait_path: str | None = None) -> None:
    """Set the video cover/thumbnail.

    视频号发布页的封面入口数量取决于视频方向：
    - 竖版视频：只有竖版封面入口（个人主页卡片 3:4）
    - 横版视频：同时有横版封面入口（分享卡片 4:3）+ 竖版封面入口（个人主页卡片 3:4）

    本函数遍历页面上**所有可见**的封面入口，对每个入口分别上传对应方向的封面：
    - horizontal 入口 → thumbnail_landscape_path（4:3）
    - vertical 入口   → thumbnail_portrait_path（3:4）
    没有对应封面图的入口跳过。
    """
    if not thumbnail_path and not thumbnail_landscape_path and not thumbnail_portrait_path:
        return

    logger.info("[设置封面] setting cover image")

    # Step 1: 检测封面预览区是否存在
    cover_preview = page.locator('div:has(> .label):has-text("封面预览")').first
    try:
        if await cover_preview.count():
            await cover_preview.wait_for(state="visible", timeout=5000)
            logger.info("[设置封面] found cover preview area")
    except Exception:
        logger.info("[设置封面] no cover preview area found, trying direct cover detection")

    cover_dialog_selectors = [
        ("div.weui-desktop-dialog", "编辑个人主页卡片"),
        ("div.weui-desktop-dialog", "封面"),
        ("div.weui-desktop-dialog", "上传"),
        ("div.weui-desktop-dialog", "卡片"),
    ]

    async def _find_cover_dialog():
        """按既定选择器找当前可见的封面对话框，找不到返回 None。"""
        for selector, text_hint in cover_dialog_selectors:
            try:
                dialog = page.locator(selector).filter(has_text=text_hint).first
                if await dialog.count() and await dialog.is_visible():
                    logger.info(f"[设置封面] found cover dialog (text: {text_hint})")
                    return dialog
            except Exception:
                continue
        try:
            fallback = page.locator("div.weui-desktop-dialog").first
            if await fallback.count() and await fallback.is_visible():
                logger.info("[设置封面] using fallback dialog match")
                return fallback
        except Exception:
            pass
        return None

    async def _do_one_cover(cover_entry, cover_type, effective_thumbnail):
        """对单个封面入口执行：点击→(横版多一步 popover 点"直接编辑")→等对话框→上传→裁剪确认→确认。"""
        logger.info(f"[设置封面] 开始点击 {cover_type} 封面入口，直到对话框出现（无限重试）")
        cover_dialog = None
        attempt = 0
        while cover_dialog is None:
            attempt += 1
            try:
                try:
                    await cover_entry.hover()
                except Exception:
                    pass
                await page.wait_for_timeout(500)
                await _wait_for_cover_ready(page, action=f"{cover_type}封面入口 hover(第{attempt}轮)")
                await cover_entry.click()
                await page.wait_for_timeout(800)
                await _wait_for_cover_ready(page, action=f"{cover_type}封面入口 click(第{attempt}轮)")

                # 横版封面：点击后先弹出 ant-popover「使用此素材作为封面？」，
                # 需点「直接编辑」才会出现封面上传弹窗；竖版点击后直接出弹窗。
                if cover_type == 'horizontal':
                    popover_edit_btn = page.locator(
                        '.ant-popover .btn-directly-edit button, '
                        '.ant-popover button:has-text("直接编辑")'
                    ).first
                    try:
                        if await popover_edit_btn.count() and await popover_edit_btn.is_visible():
                            logger.info(f"[设置封面] {cover_type} 检测到推荐素材 popover，点击「直接编辑」")
                            await popover_edit_btn.click()
                            await page.wait_for_timeout(800)
                            await _wait_for_cover_ready(page, action=f"{cover_type}封面 popover「直接编辑」后")
                    except Exception as pop_exc:
                        logger.info(f"[设置封面] {cover_type} popover 处理异常(第{attempt}轮): {pop_exc}")

                cover_dialog = await _find_cover_dialog()
            except Exception as retry_exc:
                logger.info(f"[设置封面] {cover_type}封面入口重试异常(第{attempt}轮): {retry_exc}")
            if cover_dialog is None:
                if attempt == 1 or attempt % 5 == 0:
                    logger.info(f"[上传视频] {cover_type}封面对话框未出现，继续重试(第{attempt}轮)")
                await page.wait_for_timeout(1000)

        # 上传封面文件
        file_input_selectors = [
            '.single-cover-uploader-wrap input[type="file"]',
            'input[type="file"][accept*="image"]',
            '.cover-uploader-wrap input[type="file"]',
            'input[type="file"]',
        ]
        file_input = None
        for selector in file_input_selectors:
            try:
                locator = cover_dialog.locator(selector).first
                if await locator.count():
                    file_input = locator
                    logger.info(f"[设置封面] found file input: {selector}")
                    break
            except Exception:
                continue
        if not file_input:
            try:
                file_input = page.locator("div.weui-desktop-dialog input[type='file']").first
                if not await file_input.count():
                    logger.info(f"[设置封面] WARNING: no file input for {cover_type} cover, skipping")
                    return
            except Exception:
                return

        await file_input.wait_for(state="attached", timeout=10000)
        await _wait_for_cover_ready(page, action=f"上传{cover_type}封面文件前")
        logger.info(f"[设置封面] uploading {cover_type} cover: {effective_thumbnail}")
        await file_input.set_input_files(effective_thumbnail)
        await page.wait_for_timeout(2000)

        # 裁剪对话框
        crop_dialog = page.locator("div.weui-desktop-dialog").filter(has_text="裁剪封面图").first
        if await crop_dialog.count():
            try:
                await crop_dialog.wait_for(state="visible", timeout=10000)
                logger.info(f"[设置封面] {cover_type} crop dialog appeared")
                for selector in (
                    'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确定")',
                    'button:has-text("确定")',
                    "button.weui-desktop-btn_primary",
                ):
                    try:
                        btn = crop_dialog.locator(selector).first
                        if await btn.count() and await btn.is_visible():
                            await btn.click()
                            logger.info(f"[设置封面] {cover_type} crop confirmed: {selector}")
                            await page.wait_for_timeout(1000)
                            break
                    except Exception:
                        continue
            except Exception as exc:
                logger.info(f"[设置封面] WARNING: {cover_type} crop confirm error: {exc}")

        # 确认封面
        confirmed = False
        for selector in (
            'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确认")',
            'div.weui-desktop-dialog__ft button:has-text("确认")',
            'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确定")',
            "div.weui-desktop-dialog__ft button.weui-desktop-btn_primary",
            'button:has-text("确认")',
        ):
            try:
                btn = cover_dialog.locator(selector).first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    logger.info(f"[设置封面] {cover_type} cover confirmed: {selector}")
                    confirmed = True
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue
        if not confirmed:
            logger.info(f"[设置封面] WARNING: {cover_type} cover confirm button not found")
        logger.info(f"[设置封面] {cover_type} cover image set complete")

    # Step 2: 收集所有可见的封面入口及其类型
    cover_entry_defs = [
        # Vertical cover (个人主页卡片, 3:4)
        ('div.vertical-cover-wrap', 'vertical', thumbnail_portrait_path),
        # Horizontal cover (分享卡片, 4:3)
        ('div.horizon-cover-wrap', 'horizontal', thumbnail_landscape_path),
    ]
    # thumbnail_path 作为兜底：若没有对应方向的封面，用它
    for entry in cover_entry_defs:
        if not entry[2] and thumbnail_path:
            cover_entry_defs[cover_entry_defs.index(entry)] = (entry[0], entry[1], thumbnail_path)

    visible_entries = []
    for selector, ctype, thumb in cover_entry_defs:
        candidate = page.locator(selector).first
        try:
            if not await candidate.count():
                continue
            await candidate.wait_for(state="visible", timeout=3000)
            visible_entries.append((candidate, ctype, thumb))
            logger.info(f"[设置封面] cover entry found: {selector} ({ctype})")
        except Exception:
            continue

    if not visible_entries:
        logger.info("[设置封面] WARNING: no cover entry found, skipping cover")
        return

    # Step 3: 对每个可见入口依次设置封面（横版视频会有两个，竖版视频只有一个）
    for cover_entry, cover_type, effective_thumbnail in visible_entries:
        if not effective_thumbnail:
            logger.info(f"[设置封面] no thumbnail for {cover_type} cover, skipping")
            continue
        await _do_one_cover(cover_entry, cover_type, effective_thumbnail)

    logger.info("[设置封面] all cover images set complete")


async def _set_schedule_time(page, publish_date) -> None:
    """Set the scheduled publish time in the Channels date/time picker."""
    label_element = page.locator("label").filter(has_text="定时").nth(1)
    await label_element.click()
    await page.click('input[placeholder="请选择发表时间"]')

    current_month = publish_date.strftime("%m月")
    page_month = await page.inner_text(
        'span.weui-desktop-picker__panel__label:has-text("月")'
    )
    if page_month != current_month:
        await page.click("button.weui-desktop-btn__icon__right")

    elements = await page.query_selector_all("table.weui-desktop-picker__table a")
    for element in elements:
        if "weui-desktop-picker__disabled" in await element.evaluate(
            "el => el.className"
        ):
            continue
        text = await element.inner_text()
        if text.strip() == str(publish_date.day):
            await element.click()
            break

    await page.click('input[placeholder="请选择时间"]')
    await page.keyboard.press("Control+KeyA")
    await page.keyboard.press("Delete")
    # 输入完整时分（HH:MM）。旧代码只输小时导致分钟恒为 00
    # （如 04:02 被填成 04:00）
    await page.keyboard.type(publish_date.strftime("%H:%M"))
    await page.locator("div.input-editor").click()


async def _dismiss_i_know_dialog(page) -> bool:
    """Dismiss the '我知道了' popup if present.

    视频号偶尔会在点击「发表」后弹出一个「我知道了」提示框(发布须知/平台规则提醒),
    阻塞后续跳转等待。函数尝试多种选择器定位按钮,命中可见则点击关闭。
    返回 True 表示确实关闭了一个弹窗,False 表示当前没弹窗或定位失败(被忽略)。
    """
    selectors = (
        'div.weui-desktop-dialog button:has-text("我知道了")',
        'div.weui-desktop-dialog button.weui-desktop-btn_primary:has-text("我知道了")',
        # 兜底:其它变体也按 kuaishou 既有套路去匹配 span 文本
        'button[type="button"] span:text("我知道了")',
    )
    for sel in selectors:
        try:
            btn = page.locator(sel).first
            if await btn.count() and await btn.is_visible():
                await btn.click()
                logger.info("[发布] 检测到「我知道了」弹窗,已点击关闭")
                await asyncio.sleep(0.5)  # 等弹窗动画消失
                return True
        except Exception:
            continue
    return False


async def _submit_publish(page, is_draft: bool = False) -> None:
    """Click the publish (or save-draft) button and wait for navigation."""
    while True:
        try:
            if is_draft:
                draft_button = page.locator(
                    'div.form-btns button:has-text("保存草稿")'
                )
                if await draft_button.count():
                    await draft_button.click()
                await page.wait_for_url("**/post/list**", timeout=30000)
                logger.info("[发布] draft saved successfully")
            else:
                publish_button = page.locator(
                    'div.form-btns button:has-text("发表")'
                )
                if await publish_button.count():
                    await publish_button.click()
                    # 视频号偶尔弹出「我知道了」提醒框,先关掉再等跳转
                    if await _dismiss_i_know_dialog(page):
                        # 弹窗关掉后,需要再次点击「发表」才能真正提交
                        publish_button = page.locator(
                            'div.form-btns button:has-text("发表")'
                        )
                        if await publish_button.count():
                            await publish_button.click()
                await page.wait_for_url(TENCENT_MANAGE_URL, timeout=30000)
                logger.info("[发布] video published successfully")
            break
        except Exception as exc:
            current_url = page.url
            if is_draft:
                if "post/list" in current_url or "draft" in current_url:
                    logger.info("[发布] draft saved successfully")
                    break
            else:
                if TENCENT_MANAGE_URL in current_url:
                    logger.info("[发布] video published successfully")
                    break
            logger.info(f"[发布] publish in progress... ({exc})")
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Platform class
# ---------------------------------------------------------------------------

class ChannelsPlatform(BasePlatform):
    platform_id = 2
    platform_key = "channels"
    platform_name = "视频号"

    # 支持 cookie 字符串导入账号（视频号登录态高度依赖 localStorage，
    # 仅灌 cookie 可能 sync 拉不到资料，需用户自行验证）
    supports_cookie_import = True
    platform_cookie_domain = ".qq.com"

    def _parse_cookie_to_storage_state(self, cookie_str):
        cookies = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair: continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(), "value": value.strip(),
                "domain": self.platform_cookie_domain, "path": "/",
                "expires": expires, "httpOnly": True, "secure": False, "sameSite": "Lax",
            })
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR code in iframe, then save_login_result
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Channels (视频号) login.

        直接打开登录页 ``/login.html``，由用户在浏览器里扫码完成登录。
        后端只负责轮询 URL：一旦从登录页跳到 ``/platform/*``，即判定登录成功，
        随后导航到创作中心首页抓取头像/昵称并落库。
        不再提取/推送二维码——前端只等 ``status:200``。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            page = await context.new_page()

            await page.goto(TENCENT_LOGIN_URL)
            logger.info("[发布] 登录页已打开，等待用户扫码")

            # 轮询 URL 判断登录完成（无限等，浏览器由用户自己关）
            poll_interval = 3
            while True:
                if await _is_login_completed(page):
                    logger.info(f"[发布] login successful, redirected to: {page.url}")
                    # 资料卡 (finder-card) 在创作中心首页 /platform 渲染。
                    # 若登录后落在子页（如 /platform/post/create），导航到首页再抓。
                    if not page.url.rstrip("/").endswith("channels.weixin.qq.com/platform"):
                        try:
                            await page.goto(TENCENT_PLATFORM_URL, timeout=15000)
                        except Exception as nav_e:
                            logger.info(f"[发布] 导航到创作中心首页失败(继续尝试抓取): {nav_e}")
                    await save_login_result(
                        context,
                        page,
                        platform_id=self.platform_id,
                        platform_name=self.platform_name,
                        status_queue=status_queue,
                        scrape_fn=scrape_tencent_profile,
                        account_id=account_id,
                        # 登录成功后在同一个 session 内补抓 stats(视频/关注者),
                        # 与 sync_profile 共用同一份抓取逻辑
                        stats_fn=self._login_stats_fn,
                    )
                    success = True
                    return

                await asyncio.sleep(poll_interval)
        except Exception as exc:
            logger.info(f"[发布] login error: {exc}")
            status_queue.put(json.dumps({
                "status": "failed",
                "message": str(exc),
            }))
        finally:
            try:
                # 释放 context 资源
                await context.close()
            except Exception:
                pass
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
                try:
                    await browser.close()
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # check_cookie — open upload URL, look for login markers
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid.

        访问 https://channels.weixin.qq.com/platform,
        如果页面停留没有重定向到登录页,就代表登录成功。
        """
        logger.info("=== check_cookie 开始 === cookie_file=%s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        cookie_file_path = Path(cookie_path)
        if not cookie_file_path.exists():
            logger.warning("check_cookie: cookie 文件不存在: %s", cookie_path)
            return False

        logger.info("check_cookie: cookie 文件存在，大小=%d", cookie_file_path.stat().st_size)

        browser = await self.create_browser(headless=True)
        logger.info("check_cookie: browser created, headless=True")

        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            logger.info("check_cookie: context created")

            try:
                page = await context.new_page()
                # 访问 /platform 页面(不是 /platform/post/create)
                check_url = "https://channels.weixin.qq.com/platform"
                logger.info("check_cookie: 正在跳转到: %s", check_url)

                await page.goto(check_url, wait_until="domcontentloaded")
                logger.info("check_cookie: domcontentloaded 完成")

                await asyncio.sleep(3)

                final_url = page.url
                logger.info("check_cookie: 最终 URL = %s", final_url)

                # 如果重定向到登录页(含 login),说明 cookie 失效
                if "login" in final_url.lower():
                    logger.info("check_cookie: [FAIL] 已重定向到登录页，Cookie 失效 | URL: %s", final_url)
                    return False

                # 如果页面停留(没有重定向到登录页),说明 cookie 有效
                logger.info("check_cookie: [SUCCESS] 页面停留未重定向，Cookie 有效 | URL: %s", final_url)
                return True
            except Exception as exc:
                logger.error("check_cookie: [EXCEPTION] 发生异常: %s", exc)
                import traceback
                logger.error("check_cookie: traceback: %s", traceback.format_exc())
                return False
            finally:
                logger.info("check_cookie: 正在关闭 context")
                await context.close()
        except Exception as e:
            logger.error("check_cookie: [EXCEPTION] browser/context 创建失败: %s", e)
            import traceback
            logger.error("check_cookie: traceback: %s", traceback.format_exc())
            return False
        finally:
            logger.info("check_cookie: 正在关闭 browser")
            await browser.close()
        logger.info("=== check_cookie 结束 ===")

    # ------------------------------------------------------------------
    # sync_profile — open platform URL with cookies, scrape profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """Sync profile info (name, avatar, stats) from Channels creator centre.

        抓取 finder-content-info 上的两个数字:
        - 视频数  (DOM: `.finder-content-info > div:first-child .finder-info-num`)
        - 关注者  (DOM: `.finder-content-info .second-info .finder-info-num`)
        (视频号没有粉丝数概念,"关注者"等价于粉丝)
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(TENCENT_PLATFORM_URL)
            name, avatar = await scrape_tencent_profile(page)
            stats = await self._scrape_channels_stats(page)
            await page.close()
            await context.close()
            return {"name": name, "avatar": avatar, "stats": stats}
        except Exception as exc:
            logger.info(f"[发布] sync_profile error: {exc}")
            return {"name": "", "avatar": "", "stats": []}
        finally:
            try:
                await browser.close()
            except Exception:
                pass


    async def _scrape_channels_stats(self, page) -> list:
            """抓取视频号创作者中心首页的运营数据。

            页面 DOM 结构(参见用户提供的 2026-07-19 抓取样本):
                <div class="finder-content-info">
                  <div><span>视频</span><span class="finder-info-num">11</span></div>
                  <div class="second-info"><span>关注者</span><span class="finder-info-num">2</span></div>
                </div>

            Returns:
                list[dict]: 按 SORT 排序的运营数据列表
            """
            stats = []
            label_map = {
                "视频":   ("video",  1, "视频"),
                "关注者": ("follow", 2, "关注者"),
            }

            try:
                await page.wait_for_selector(".finder-info-num", timeout=8000)
            except Exception:
                logger.info("[channels stats] 等待 .finder-info-num 超时")

            try:
                raw = await page.evaluate(
                    '''() => {
                        const out = [];
                        document.querySelectorAll('.finder-content-info > div').forEach(div => {
                            const numEl = div.querySelector('.finder-info-num');
                            if (!numEl) return;
                            // 标签在前一个 span 里(不是 .finder-info-num)
                            const labelSpan = div.querySelector('span:not(.finder-info-num)');
                            const label = labelSpan ? labelSpan.textContent.trim() : '';
                            const num = numEl.textContent.trim();
                            if (label) out.push({label, num});
                        });
                        return out;
                    }'''
                )
                for item in raw:
                    label = item.get('label', '')
                    if label in label_map:
                        icon, sort_no, name = label_map[label]
                        try:
                            count = int(str(item.get('num', '0')).replace(',', '').replace(' ', '') or '0')
                        except (ValueError, TypeError):
                            count = 0
                        stats.append({"ICON": icon, "COUNT": count, "NAME": name, "SORT": sort_no})
            except Exception as exc:
                logger.info(f"[channels stats] 抓取失败: {exc}")

            stats.sort(key=lambda x: x.get("SORT", 999))
            return stats

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用 _scrape_channels_stats 抓取逻辑,
        保证"登录后同步"和"同步按钮"看到的运营数据完全一致。
        """
        try:
            try:
                await page.goto(TENCENT_PLATFORM_URL, timeout=15000)
            except Exception:
                pass
            return await self._scrape_channels_stats(page)
        except Exception as exc:
            logger.info(f"[channels login] _login_stats_fn 抓取失败: {exc}")
            return []

    # ------------------------------------------------------------------
    # open_creator_center — KEEP AS-IS (sync CloakBrowser in thread)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Channels (视频号) creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://channels.weixin.qq.com/platform"

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # publish_video — full TencentVideo flow via CloakBrowser
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Channels (视频号).

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*str*, optional) -- original declaration category
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``is_draft`` (*bool*, optional)
        - ``thumbnail_path`` (*str*, optional) -- cover image
        - ``thumbnail_landscape_path`` (*str*, optional) -- landscape cover (4:3)
        - ``thumbnail_portrait_path`` (*str*, optional) -- portrait cover (3:4)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        """
        logger.info("=" * 60)
        logger.info("[发布视频] 开始视频号视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", [])
        account_files = kwargs.get("account_file", [])
        category = kwargs.get("category")
        enable_timer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        is_draft = kwargs.get("is_draft", False)
        thumbnail_path = kwargs.get("thumbnail_path")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        # 视频号合集(账号级)
        channels_collection_name = kwargs.get("channels_collection_name", "")
        # 视频号位置(平台级,空字符串=不显示位置)
        channels_location_name = kwargs.get("channels_location_name", "")
        # 视频号视频标注(平台级):所有选项(含「无需标注」)都会去页面下拉真正选中
        channels_mark_tag = kwargs.get("channels_mark_tag", "无需标注")
        # 自行拍摄联动:拍摄时间(YYYY-MM-DD 字符串)+ 拍摄地点([国家, 省, 市] 文本数组)
        channels_shoot_date = kwargs.get("channels_shoot_date", "")
        channels_shoot_region = kwargs.get("channels_shoot_region", []) or []
        # 转载联动:转载来源(选填文本)
        channels_repost_source = kwargs.get("channels_repost_source", "")

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_files))
        logger.info("[发布参数] 定时发布: %s", enable_timer)
        logger.info("[发布参数] 草稿模式: %s", is_draft)
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 创作声明: %s", category or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

        # Resolve file paths
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        resolved_files = [str(f) for f in files]
        resolved_accounts = [
            str(Path(BASE_DIR / "cookiesFile" / a)) for a in account_files
        ]
        if thumbnail_path:
            # thumbnail_path 已是绝对路径
            thumbnail_path = str(thumbnail_path)
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(thumbnail_portrait_path)

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(resolved_files),
            enable_timer,
            videos_per_day,
            daily_times,
            start_days,
        )
        logger.info(
            "[发布策略] 定时时间解析: schedule_time_str=%r -> publish_datetimes=%s",
            schedule_time_str, publish_datetimes,
        )

        # Run the async upload in a new event loop (same pattern as legacy)
        async def _do_upload():
            for index, file_path in enumerate(resolved_files):
                logger.info("-" * 40)
                logger.info("[发布进度] 处理第 %d/%d 个视频: %s", index + 1, len(resolved_files), file_path)
                publish_date = publish_datetimes[index]
                for cookie_index, cookie_path in enumerate(resolved_accounts):
                    cookie_name = Path(cookie_path).name
                    nick = get_account_name_by_cookie_file(cookie_name)
                    with bind_account_name(nick or "-"):
                        logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(resolved_accounts), nick or "未知")
                        logger.info("[上传视频] 开始上传视频: %s", file_path)
                        logger.info("[上传视频] 标题: %s", title)
                        logger.info("[上传视频] 简介: %s", desc)
                        logger.info("[上传视频] 标签: %s", tags)

                        # 有头模式发布(便于观察);不开 humanize(no_viewport=True 与
                        # 拟人化鼠标轨迹冲突,会抛 "Viewport size not available")
                        browser = await self.create_browser(headless=False)
                        try:
                            context = await self.create_context(
                                browser, storage_state=cookie_path
                            )
                            page = await context.new_page()

                            # Open upload page
                            await page.goto(TENCENT_UPLOAD_URL, timeout=60000)
                            try:
                                await page.wait_for_url(
                                    TENCENT_UPLOAD_URL, timeout=60000
                                )
                            except Exception:
                                pass

                            # Upload video file
                            await _upload_video_file(page, file_path)

                            # Fill metadata
                            # title → 短标题输入框（_set_short_title，稍后填）
                            # 正文/描述区 → desc + tags
                            await _fill_description(page, desc)
                            await _fill_title_and_tags(page, title, tags)
                            await _apply_collection(page, channels_collection_name)
                            await _apply_location(page, channels_location_name)
                            await _apply_original_statement(page, category)
                            await _apply_mark_tag(
                                page,
                                channels_mark_tag,
                                channels_shoot_date,
                                channels_shoot_region,
                                channels_repost_source,
                            )

                            # Wait for upload to finish (auto-retries on error)
                            await _wait_for_upload_complete(page, file_path)

                            # Set cover image
                            await _set_thumbnail(page, thumbnail_path, thumbnail_landscape_path, thumbnail_portrait_path)

                            # Set schedule if needed
                            if enable_timer and publish_date != 0:
                                await _set_schedule_time(page, publish_date)

                            # Set short title
                            await _set_short_title(page, title)

                            # 调试:输出本次发布的全部参数
                            logger.info("=" * 60)
                            logger.info("[发布调试] ===== 本次发布参数汇总 (dry_run=%s) =====", _PUBLISH_DRY_RUN)
                            logger.info("[发布调试] 标题(title)       : %s", title)
                            logger.info("[发布调试] 视频文件(file_path): %s", file_path)
                            logger.info("[发布调试] 描述(desc)        : %s", desc[:100] if desc else "(无)")
                            logger.info("[发布调试] 标签(tags)        : %s (共 %d 个)", tags, len(tags))
                            logger.info("[发布调试] 横版封面(landscape): %s", thumbnail_landscape_path or "(无)")
                            logger.info("[发布调试] 竖版封面(portrait) : %s", thumbnail_portrait_path or "(无)")
                            logger.info("[发布调试] 合集(collection)  : %s", channels_collection_name or "(无)")
                            logger.info("[发布调试] 位置(location)     : %s", channels_location_name or "(无)")
                            logger.info("[发布调试] 创作声明(category): %s", category or "(无)")
                            logger.info("[发布调试] 视频标注(mark_tag) : %s", channels_mark_tag or "(无)")
                            logger.info("[发布调试] 拍摄时间(shoot_dt): %s", channels_shoot_date or "(无)")
                            logger.info("[发布调试] 拍摄地点(shoot_rg): %s", " / ".join(channels_shoot_region) if channels_shoot_region else "(无)")
                            logger.info("[发布调试] 转载来源(repost)   : %s", channels_repost_source or "(无)")
                            logger.info("[发布调试] 定时(enable_timer): %s", enable_timer)
                            logger.info("[发布调试] ========================================")
                            logger.info("=" * 60)

                            if _PUBLISH_DRY_RUN:
                                logger.warning("[发布调试] DRY_RUN 已开启 —— 跳过实际点击发布,流程到此结束(不发布)")
                                logger.info("[发布调试] DRY_RUN: 浏览器保持打开,等待你手动关闭窗口后再结束...")
                                try:
                                    while browser.is_connected():
                                        await asyncio.sleep(1)
                                    logger.info("[发布调试] 检测到浏览器已关闭,流程结束")
                                except Exception:
                                    pass
                                return

                            # Submit
                            await _submit_publish(page, is_draft)

                            # Update stored cookies
                            await context.storage_state(path=cookie_path)
                            logger.info("[发布] Cookie状态已更新")
                        finally:
                            try:
                                await context.close()
                            except Exception:
                                pass
                            try:
                                await self.close_browser(browser, is_close_by_code=True)
                            except Exception:
                                pass

        asyncio.run(_do_upload())

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True
