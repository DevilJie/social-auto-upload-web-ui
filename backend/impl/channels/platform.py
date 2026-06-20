"""
Channels (视频号) platform implementation.

100% CloakBrowser — all browser operations use the new engine via
``BasePlatform.create_browser()`` / ``BasePlatform.create_context()``
and shared utilities from ``backend/impl/_utils.py``.
"""

import asyncio
import json
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import get_channel_logger

logger = get_channel_logger("channels")

from .._browser import create_browser_sync, create_context_sync
from .._utils import parse_schedule_time, save_login_result, scrape_tencent_profile
from ..base_platform import BasePlatform

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TENCENT_LOGIN_URL = "https://channels.weixin.qq.com"
TENCENT_UPLOAD_URL = "https://channels.weixin.qq.com/platform/post/create"
TENCENT_MANAGE_URL = "https://channels.weixin.qq.com/platform/post/list"


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


# ---------------------------------------------------------------------------
# QR-code extraction helpers
# ---------------------------------------------------------------------------

async def _extract_qrcode_src(page) -> str:
    """Extract the QR code image ``src`` from the Channels login page.

    The QR code lives inside an iframe (``login-for-iframe``) on the
    Channels login page.  Falls back to top-level selectors when the
    iframe is unavailable.
    """
    # Primary: iframe approach
    try:
        iframe_locator = page.frame_locator('[src*="login-for-iframe"]')
        qr_code_img = iframe_locator.locator("div#app img.qrcode").first
        await qr_code_img.wait_for(state="visible", timeout=30000)
        src = await qr_code_img.get_attribute("src")
        if src and src.startswith("data:image/"):
            return src
    except Exception:
        pass

    # Fallback: top-level selectors
    for selector in (
        "div.login-qrcode-wrap img.qrcode",
        "div.qrcode-wrap img.qrcode",
        "img.qrcode",
        'img[src^="data:image/"]',
    ):
        qr_code_img = page.locator(selector).first
        try:
            if not await qr_code_img.count() or not await qr_code_img.is_visible():
                continue
            src = await qr_code_img.get_attribute("src")
            if src and src.startswith("data:image/"):
                return src
        except Exception:
            continue

    raise RuntimeError("未获取到视频号登录二维码地址")


async def _is_qrcode_expired(page) -> bool:
    """Check whether the displayed QR code has expired."""
    for selector in (
        'div.mask.show p.refresh-tip:has-text("二维码已过期，点击刷新")',
        'div.mask.show p.refresh-tip:has-text("网络不可用，点击刷新")',
        'p.refresh-tip:has-text("二维码已过期，点击刷新")',
        'p.refresh-tip:has-text("网络不可用，点击刷新")',
    ):
        tip = page.locator(selector).first
        try:
            if await tip.count() and await tip.is_visible():
                return True
        except Exception:
            continue
    return False


async def _is_qrcode_scanned(page) -> bool:
    """Check whether the user has scanned the QR code."""
    for selector in (
        'div.qr-tip div:has-text("已扫码")',
        'div.qr-tip div:has-text("需在手机上进行确认")',
    ):
        tip = page.locator(selector).first
        try:
            if await tip.count() and await tip.is_visible():
                return True
        except Exception:
            continue
    return False


async def _refresh_qrcode(page) -> None:
    """Click the refresh area to regenerate an expired QR code."""
    # Try visible refresh-wrap first
    for selector in (
        "div.login-qrcode-wrap div.mask.show div.refresh-wrap",
        "div.login-qrcode-wrap div.mask.show .refresh-wrap",
    ):
        refresh_wrap = page.locator(selector).first
        try:
            if not await refresh_wrap.count() or not await refresh_wrap.is_visible():
                continue
            await refresh_wrap.click()
            return
        except Exception:
            continue

    # Try tip-based refresh
    for selector in (
        'div.mask.show p.refresh-tip:has-text("二维码已过期，点击刷新")',
        'div.mask.show p.refresh-tip:has-text("网络不可用，点击刷新")',
        'p.refresh-tip:has-text("二维码已过期，点击刷新")',
        'p.refresh-tip:has-text("网络不可用，点击刷新")',
    ):
        tip = page.locator(selector).first
        try:
            if not await tip.count() or not await tip.is_visible():
                continue
            refresh_wrap = tip.locator(
                "xpath=ancestor::div[contains(@class, 'refresh-wrap')]"
            ).first
            if await refresh_wrap.count():
                await refresh_wrap.click()
            else:
                await tip.click()
            return
        except Exception:
            continue

    # Final fallback
    fallback = page.locator("div.login-qrcode-wrap div.refresh-wrap").first
    if await fallback.count():
        await fallback.click()
        return

    raise RuntimeError("未找到可点击的视频号二维码刷新区域")


async def _is_login_completed(page) -> bool:
    """Detect whether the user has completed the QR-code login flow."""
    publish_markers = [
        page.locator('div:has-text("发表视频")').first,
        page.locator('button:has-text("发表")').first,
        page.locator('button:has-text("保存草稿")').first,
    ]
    for marker in publish_markers:
        try:
            if await marker.count() and await marker.is_visible():
                return True
        except Exception:
            continue

    if not (
        page.url.startswith(TENCENT_UPLOAD_URL)
        or page.url.startswith(TENCENT_MANAGE_URL)
    ):
        return False

    login_markers = [
        page.locator("div.login-qrcode-wrap").first,
        page.locator("div.qrcode-wrap").first,
        page.locator("img.qrcode").first,
        page.locator('span:has-text("微信扫码登录 视频号助手")').first,
    ]
    for marker in login_markers:
        try:
            if await marker.count() and await marker.is_visible():
                return False
        except Exception:
            continue

    return True


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
    logger.info(f"[channels] added {len(tags)} hashtags to description editor")


async def _fill_description(page, desc: str) -> None:
    """Type the description into the rich-text description editor.

    描述填入正文/描述区（与话题标签同区），title 不再混入此处。
    """
    if not desc:
        return
    await page.locator("div.input-editor").click()
    await page.keyboard.type(desc)
    logger.info(f"[channels] added description ({len(desc)} chars)")


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
            logger.info(f"[channels] short title filled: {value!r} ({selector})")
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
            logger.info(f"[channels] short title filled (legacy): {value!r}")
            return
    except Exception:
        pass
    logger.info("[channels] short title input not found, skipping")


async def _apply_collection(page) -> None:
    """Select the first available collection if there is more than one."""
    collection_elements = (
        page.get_by_text("添加到合集")
        .locator("xpath=following-sibling::div")
        .locator(".option-list-wrap > div")
    )
    if await collection_elements.count() > 1:
        await page.get_by_text("添加到合集").locator(
            "xpath=following-sibling::div"
        ).click()
        await collection_elements.first.click()


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
                logger.info("[channels] video upload complete")
                break

            logger.info("[channels] uploading video...")
            await asyncio.sleep(2)

            # Check for upload errors
            upload_failed = await page.locator("div.status-msg.error").count()
            delete_button = await page.locator(
                'div.media-status-content div.tag-inner:has-text("删除")'
            ).count()
            if upload_failed and delete_button:
                logger.info("[channels] upload error detected, retrying")
                await page.locator(
                    'div.media-status-content div.tag-inner:has-text("删除")'
                ).click()
                await page.get_by_role("button", name="删除", exact=True).click()
                await _upload_video_file(page, file_path)
        except Exception:
            logger.info("[channels] uploading video...")
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

    logger.info(f"[channels] 封面阻塞提示出现({action}):「{blocking}」，开始无限等待...")
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
            logger.info(f"[channels] 封面阻塞提示已消失，等待耗时 {waited}s，继续执行({action})")
            return
        if waited % 10 == 0:
            logger.info(f"[channels] 封面阻塞等待中({action}):「{still_blocking}」... ({waited}s)")


async def _set_thumbnail(page, thumbnail_path: str | None, thumbnail_landscape_path: str | None = None, thumbnail_portrait_path: str | None = None) -> None:
    """Set the video cover/thumbnail (5-step flow).

    Steps:
    1. Check for cover preview area, then determine which cover type is visible.
    2. Click the cover entry (vertical 3:4 or horizontal 4:3).
    3. Wait for the cover-edit dialog.
    4. Upload the cover image file.
    5. Handle the crop dialog if it appears.
    6. Confirm the cover selection.
    """
    if not thumbnail_path and not thumbnail_landscape_path and not thumbnail_portrait_path:
        return

    logger.info("[channels] setting cover image")

    # Step 1: check if cover preview area exists, then find visible cover type
    cover_preview = page.locator('div:has(> .label):has-text("封面预览")').first
    has_cover_preview = False
    try:
        if await cover_preview.count():
            await cover_preview.wait_for(state="visible", timeout=5000)
            has_cover_preview = True
            logger.info("[channels] found cover preview area")
    except Exception:
        logger.info("[channels] no cover preview area found, trying direct cover detection")

    # Step 2: click cover entry - try vertical first, then horizontal
    cover_entry_selectors = [
        # Vertical cover (个人主页卡片, 3:4)
        ('div.vertical-cover-wrap', 'vertical'),
        # Horizontal cover (分享卡片, 4:3)
        ('div.horizon-cover-wrap', 'horizontal'),
    ]
    cover_type = None
    cover_entry = None
    for selector, ctype in cover_entry_selectors:
        candidate = page.locator(selector).first
        try:
            if not await candidate.count():
                continue
            await candidate.wait_for(state="visible", timeout=3000)
            cover_entry = candidate
            cover_type = ctype
            logger.info(f"[channels] cover entry found: {selector} ({ctype})")
            break
        except Exception:
            continue

    if not cover_entry:
        logger.info("[channels] WARNING: no cover entry found, skipping cover")
        return

    # Determine which thumbnail to use based on cover type
    effective_thumbnail = thumbnail_path
    if cover_type == 'horizontal' and thumbnail_landscape_path:
        effective_thumbnail = thumbnail_landscape_path
    elif cover_type == 'vertical' and thumbnail_portrait_path:
        effective_thumbnail = thumbnail_portrait_path
    if not effective_thumbnail:
        logger.info(f"[channels] no thumbnail for {cover_type} cover, skipping")
        return

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
                    logger.info(f"[channels] found cover dialog (text: {text_hint})")
                    return dialog
            except Exception:
                continue
        # fallback：任意可见对话框
        try:
            fallback = page.locator("div.weui-desktop-dialog").first
            if await fallback.count() and await fallback.is_visible():
                logger.info("[channels] using fallback dialog match")
                return fallback
        except Exception:
            pass
        return None

    # Step 3: 点击封面入口直到对话框出现 —— 简单粗暴的无限重试。
    # 视频号在视频上传/封面预览图生成期间，点击封面入口会被 weui-desktop-popover
    # （「文件上传中...」/「预览图生成中...」）拦截，对话框不会弹出。
    # 因此每轮重试都先 hover/click → 阻塞等待 popover 消失 → 再查对话框，
    # 直到对话框出现为止。
    logger.info("[channels] 开始点击封面入口，直到封面对话框出现（无限重试）")
    cover_dialog = None
    attempt = 0
    while cover_dialog is None:
        attempt += 1
        try:
            # hover 触发（popover 可能是 hover 态才出现）
            try:
                await cover_entry.hover()
            except Exception:
                pass
            await page.wait_for_timeout(500)
            await _wait_for_cover_ready(page, action=f"封面入口 hover(第{attempt}轮)")

            # click 进入编辑
            await cover_entry.click()
            await page.wait_for_timeout(800)
            await _wait_for_cover_ready(page, action=f"封面入口 click(第{attempt}轮)")

            # 查对话框
            cover_dialog = await _find_cover_dialog()
        except Exception as retry_exc:
            logger.info(f"[channels] 封面入口重试异常(第{attempt}轮): {retry_exc}")

        if cover_dialog is None:
            if attempt == 1 or attempt % 5 == 0:
                logger.info(
                    f"[channels] 封面对话框未出现，继续重试点击封面入口(第{attempt}轮)"
                )
            await page.wait_for_timeout(1000)

    # Step 4: upload cover file
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
                logger.info(f"[channels] found file input: {selector}")
                break
        except Exception:
            continue

    if not file_input:
        try:
            file_input = page.locator(
                "div.weui-desktop-dialog input[type='file']"
            ).first
            if not await file_input.count():
                logger.info("[channels] WARNING: no file input for cover, skipping")
                return
        except Exception:
            return

    await file_input.wait_for(state="attached", timeout=10000)
    # 上传封面文件前再次阻塞等待（预览图生成中等提示可能此时出现）
    await _wait_for_cover_ready(page, action="上传封面文件前")
    logger.info(f"[channels] uploading cover ({cover_type}): {effective_thumbnail}")
    await file_input.set_input_files(effective_thumbnail)
    await page.wait_for_timeout(2000)

    # Step 5: handle crop dialog
    crop_dialog = page.locator("div.weui-desktop-dialog").filter(
        has_text="裁剪封面图"
    ).first
    if await crop_dialog.count():
        try:
            await crop_dialog.wait_for(state="visible", timeout=10000)
            logger.info("[channels] crop dialog appeared")
            for selector in (
                'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确定")',
                'button:has-text("确定")',
                "button.weui-desktop-btn_primary",
            ):
                try:
                    btn = crop_dialog.locator(selector).first
                    if await btn.count() and await btn.is_visible():
                        await btn.click()
                        logger.info(f"[channels] crop confirmed: {selector}")
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue
        except Exception as exc:
            logger.info(f"[channels] WARNING: crop confirm error: {exc}")

    # Step 6: confirm cover dialog
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
                logger.info(f"[channels] cover confirmed: {selector}")
                confirmed = True
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    if not confirmed:
        logger.info("[channels] WARNING: cover confirm button not found")

    logger.info("[channels] cover image set complete")


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
                logger.info("[channels] draft saved successfully")
            else:
                publish_button = page.locator(
                    'div.form-btns button:has-text("发表")'
                )
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(TENCENT_MANAGE_URL, timeout=30000)
                logger.info("[channels] video published successfully")
            break
        except Exception as exc:
            current_url = page.url
            if is_draft:
                if "post/list" in current_url or "draft" in current_url:
                    logger.info("[channels] draft saved successfully")
                    break
            else:
                if TENCENT_MANAGE_URL in current_url:
                    logger.info("[channels] video published successfully")
                    break
            logger.info(f"[channels] publish in progress... ({exc})")
            await asyncio.sleep(0.5)


# ---------------------------------------------------------------------------
# Platform class
# ---------------------------------------------------------------------------

class ChannelsPlatform(BasePlatform):
    platform_id = 2
    platform_key = "channels"
    platform_name = "视频号"

    # ------------------------------------------------------------------
    # login — QR code in iframe, then save_login_result
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Channels (视频号) login via QR code scan.

        Opens ``https://channels.weixin.qq.com``, extracts the QR code
        from the login iframe, polls for scan/expiry, and completes the
        post-login flow via ``save_login_result``.
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            page = await context.new_page()

            await page.goto(TENCENT_LOGIN_URL)

            # Extract QR code and push to frontend
            qrcode_src = await _extract_qrcode_src(page)
            status_queue.put(json.dumps({
                "status": "qrcode",
                "qrcode": qrcode_src,
            }))
            logger.info("[channels] QR code ready, waiting for scan")

            # Poll for login completion（无限等，浏览器由用户自己关）
            poll_interval = 3
            scanned_logged = False
            while True:
                if await _is_login_completed(page):
                    logger.info(f"[channels] login successful, redirected to: {page.url}")
                    await asyncio.sleep(2)
                    await save_login_result(
                        context,
                        page,
                        platform_id=self.platform_id,
                        platform_name=self.platform_name,
                        status_queue=status_queue,
                        scrape_fn=scrape_tencent_profile,
                        account_id=account_id,
                    )
                    success = True
                    return

                if not scanned_logged and await _is_qrcode_scanned(page):
                    logger.info("[channels] QR code scanned, awaiting confirmation")
                    scanned_logged = True

                if await _is_qrcode_expired(page):
                    logger.info("[channels] QR code expired, refreshing")
                    await _refresh_qrcode(page)
                    await asyncio.sleep(1)
                    try:
                        qrcode_src = await _extract_qrcode_src(page)
                        status_queue.put(json.dumps({
                            "status": "qrcode",
                            "qrcode": qrcode_src,
                        }))
                    except Exception:
                        pass

                await asyncio.sleep(poll_interval)
        except Exception as exc:
            logger.info(f"[channels] login error: {exc}")
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

        Opens the Channels upload page and checks whether the login form
        (``扫码登录``) or the authenticated UI (``发表视频`` / ``微信小店``)
        is visible.
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
                logger.info("check_cookie: page created, 正在跳转到: %s", TENCENT_UPLOAD_URL)

                await page.goto(TENCENT_UPLOAD_URL, wait_until="domcontentloaded")
                logger.info("check_cookie: domcontentloaded 完成")

                await asyncio.sleep(2)
                await page.wait_for_load_state("networkidle")
                logger.info("check_cookie: networkidle 完成")

                final_url = page.url
                logger.info("check_cookie: 最终 URL = %s", final_url)

                try:
                    title = await page.title()
                    logger.info("check_cookie: 页面标题 = %s", title)
                except Exception as e:
                    logger.warning("check_cookie: 获取页面标题失败: %s", e)

                # 关键检查：如果跳转到 login.html 说明 cookie 失效
                if "login.html" in final_url:
                    logger.info("check_cookie: [FAIL] 已跳转到登录页，Cookie 失效 | URL: %s", final_url)
                    return False

                # 如果停留在 channels.weixin.qq.com（没有跳转到 login.html）说明 cookie 有效
                if "channels.weixin.qq.com" in final_url:
                    logger.info("check_cookie: [SUCCESS] 停留在 channels.weixin.qq.com，Cookie 有效 | URL: %s", final_url)
                    return True

                # 其他情况（跳转到其他域名）说明 cookie 失效
                logger.info("check_cookie: [FAIL] 已跳转到外部域名，Cookie 失效 | URL: %s", final_url)
                return False
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

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Channels creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(TENCENT_UPLOAD_URL)
            name, avatar = await scrape_tencent_profile(page)
            await page.close()
            await context.close()
            return name, avatar
        except Exception as exc:
            logger.info(f"[channels] sync_profile error: {exc}")
            return "", ""
        finally:
            try:
                await browser.close()
            except Exception:
                pass

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

        logger.info(
            "[channels] publish_video kwargs: "
            f"title={title!r}, files={resolved_files}, tags={tags}, "
            f"account_file={account_files}, category={category!r}, "
            f"enableTimer={enable_timer}, videos_per_day={videos_per_day}, "
            f"daily_times={daily_times}, start_days={start_days}, "
            f"is_draft={is_draft}, desc={desc!r}, "
            f"thumbnail_path={thumbnail_path!r}, "
            f"thumbnail_landscape_path={thumbnail_landscape_path!r}, "
            f"thumbnail_portrait_path={thumbnail_portrait_path!r}, "
            f"schedule_time_str={schedule_time_str!r}"
        )

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(resolved_files),
            enable_timer,
            videos_per_day,
            daily_times,
            start_days,
        )
        logger.info(
            f"[channels] parse_schedule_time 结果: schedule_time_str={schedule_time_str!r} "
            f"-> publish_datetimes={publish_datetimes}"
        )

        # Run the async upload in a new event loop (same pattern as legacy)
        async def _do_upload():
            for index, file_path in enumerate(resolved_files):
                publish_date = publish_datetimes[index]
                for cookie_path in resolved_accounts:
                    logger.info(f"[channels] uploading: {file_path}")
                    logger.info(f"[channels] title: {title}")
                    logger.info(f"[channels] desc: {desc}")
                    logger.info(f"[channels] tags: {tags}")

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
                        await _apply_collection(page)
                        await _apply_original_statement(page, category)

                        # Wait for upload to finish (auto-retries on error)
                        await _wait_for_upload_complete(page, file_path)

                        # Set cover image
                        await _set_thumbnail(page, thumbnail_path, thumbnail_landscape_path, thumbnail_portrait_path)

                        # Set schedule if needed
                        if enable_timer and publish_date != 0:
                            await _set_schedule_time(page, publish_date)

                        # Set short title
                        await _set_short_title(page, title)

                        # Submit
                        await _submit_publish(page, is_draft)

                        # Update stored cookies
                        await context.storage_state(path=cookie_path)
                        logger.info("[channels] cookies updated")
                    finally:
                        try:
                            await context.close()
                        except Exception:
                            pass
                        try:
                            await browser.close()
                        except Exception:
                            pass

        asyncio.run(_do_upload())
        return True
