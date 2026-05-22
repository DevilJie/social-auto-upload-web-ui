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

from .._browser import create_browser_sync
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
    """Type the title and hashtags into the rich-text editor."""
    await page.locator("div.input-editor").click()
    await page.keyboard.type(title)
    await page.keyboard.press("Enter")
    for tag in tags:
        await page.keyboard.type("#" + tag)
        await page.keyboard.press("Space")
    print(f"[channels] added title + {len(tags)} hashtags")


async def _fill_description(page, desc: str) -> None:
    """Append the description after the title/tags."""
    if not desc:
        return
    await page.keyboard.press("Enter")
    await page.keyboard.type(desc)
    print(f"[channels] added description ({len(desc)} chars)")


async def _set_short_title(page, title: str, short_title: str | None = None) -> None:
    """Fill the short-title input if present."""
    short_title_element = (
        page.get_by_text("短标题", exact=True)
        .locator("..")
        .locator("xpath=following-sibling::div")
        .locator('span input[type="text"]')
    )
    if await short_title_element.count():
        await short_title_element.fill(short_title or _format_short_title(title))


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
                print("[channels] video upload complete")
                break

            print("[channels] uploading video...")
            await asyncio.sleep(2)

            # Check for upload errors
            upload_failed = await page.locator("div.status-msg.error").count()
            delete_button = await page.locator(
                'div.media-status-content div.tag-inner:has-text("删除")'
            ).count()
            if upload_failed and delete_button:
                print("[channels] upload error detected, retrying")
                await page.locator(
                    'div.media-status-content div.tag-inner:has-text("删除")'
                ).click()
                await page.get_by_role("button", name="删除", exact=True).click()
                await _upload_video_file(page, file_path)
        except Exception:
            print("[channels] uploading video...")
            await asyncio.sleep(2)


async def _set_thumbnail(page, thumbnail_path: str | None) -> None:
    """Set the video cover/thumbnail (5-step flow).

    Steps:
    1. Click the cover entry in the upload form.
    2. Wait for the cover-edit dialog.
    3. Upload the cover image file.
    4. Handle the crop dialog if it appears.
    5. Confirm the cover selection.
    """
    if not thumbnail_path:
        return

    print("[channels] setting cover image")

    # Step 1: click cover entry
    cover_entry_selectors = [
        'div.vertical-cover-wrap:has-text("个人主页卡片"):has-text("3:4")',
        'div.vertical-cover-wrap:has-text("3:4")',
        'div.vertical-cover-wrap:has-text("个人主页卡片")',
        "div.vertical-cover-wrap",
    ]
    entry_clicked = False
    for selector in cover_entry_selectors:
        cover_entry = page.locator(selector).first
        try:
            if not await cover_entry.count():
                continue
            await cover_entry.wait_for(state="visible", timeout=3000)
            await cover_entry.click()
            await page.wait_for_timeout(500)
            print(f"[channels] cover entry clicked: {selector}")
            entry_clicked = True
            break
        except Exception:
            continue

    if not entry_clicked:
        print("[channels] WARNING: no cover entry found, skipping cover")
        return

    # Step 2: wait for cover dialog
    await page.wait_for_timeout(1500)
    cover_dialog_selectors = [
        ("div.weui-desktop-dialog", "编辑个人主页卡片"),
        ("div.weui-desktop-dialog", "封面"),
        ("div.weui-desktop-dialog", "上传"),
        ("div.weui-desktop-dialog", "卡片"),
    ]
    cover_dialog = None
    for selector, text_hint in cover_dialog_selectors:
        try:
            dialog = page.locator(selector).filter(has_text=text_hint).first
            if await dialog.count() and await dialog.is_visible():
                cover_dialog = dialog
                print(f"[channels] found cover dialog (text: {text_hint})")
                break
        except Exception:
            continue

    if not cover_dialog:
        try:
            fallback = page.locator("div.weui-desktop-dialog").first
            if await fallback.count() and await fallback.is_visible():
                cover_dialog = fallback
                print("[channels] using fallback dialog match")
        except Exception:
            pass

    if not cover_dialog:
        print("[channels] WARNING: cover dialog not found, skipping cover")
        return

    # Step 3: upload cover file
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
                print(f"[channels] found file input: {selector}")
                break
        except Exception:
            continue

    if not file_input:
        try:
            file_input = page.locator(
                "div.weui-desktop-dialog input[type='file']"
            ).first
            if not await file_input.count():
                print("[channels] WARNING: no file input for cover, skipping")
                return
        except Exception:
            return

    await file_input.wait_for(state="attached", timeout=10000)
    print(f"[channels] uploading cover: {thumbnail_path}")
    await file_input.set_input_files(thumbnail_path)
    await page.wait_for_timeout(2000)

    # Step 4: handle crop dialog
    crop_dialog = page.locator("div.weui-desktop-dialog").filter(
        has_text="裁剪封面图"
    ).first
    if await crop_dialog.count():
        try:
            await crop_dialog.wait_for(state="visible", timeout=10000)
            print("[channels] crop dialog appeared")
            for selector in (
                'div.weui-desktop-dialog__ft button.weui-desktop-btn_primary:has-text("确定")',
                'button:has-text("确定")',
                "button.weui-desktop-btn_primary",
            ):
                try:
                    btn = crop_dialog.locator(selector).first
                    if await btn.count() and await btn.is_visible():
                        await btn.click()
                        print(f"[channels] crop confirmed: {selector}")
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    continue
        except Exception as exc:
            print(f"[channels] WARNING: crop confirm error: {exc}")

    # Step 5: confirm cover dialog
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
                print(f"[channels] cover confirmed: {selector}")
                confirmed = True
                await page.wait_for_timeout(1000)
                break
        except Exception:
            continue

    if not confirmed:
        print("[channels] WARNING: cover confirm button not found")

    print("[channels] cover image set complete")


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
    await page.keyboard.type(publish_date.strftime("%H"))
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
                print("[channels] draft saved successfully")
            else:
                publish_button = page.locator(
                    'div.form-btns button:has-text("发表")'
                )
                if await publish_button.count():
                    await publish_button.click()
                await page.wait_for_url(TENCENT_MANAGE_URL, timeout=30000)
                print("[channels] video published successfully")
            break
        except Exception as exc:
            current_url = page.url
            if is_draft:
                if "post/list" in current_url or "draft" in current_url:
                    print("[channels] draft saved successfully")
                    break
            else:
                if TENCENT_MANAGE_URL in current_url:
                    print("[channels] video published successfully")
                    break
            print(f"[channels] publish in progress... ({exc})")
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

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform Channels (视频号) login via QR code scan.

        Opens ``https://channels.weixin.qq.com``, extracts the QR code
        from the login iframe, polls for scan/expiry, and completes the
        post-login flow via ``save_login_result``.
        """
        browser = await self.create_browser(login_mode=True)
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
            print("[channels] QR code ready, waiting for scan")

            # Poll for login completion
            poll_interval = 3
            max_checks = 100
            scanned_logged = False
            for _ in range(max_checks):
                if await _is_login_completed(page):
                    print(f"[channels] login successful, redirected to: {page.url}")
                    await asyncio.sleep(2)
                    await save_login_result(
                        context,
                        page,
                        platform_id=self.platform_id,
                        platform_name=self.platform_name,
                        status_queue=status_queue,
                        scrape_fn=scrape_tencent_profile,
                    )
                    return

                if not scanned_logged and await _is_qrcode_scanned(page):
                    print("[channels] QR code scanned, awaiting confirmation")
                    scanned_logged = True

                if await _is_qrcode_expired(page):
                    print("[channels] QR code expired, refreshing")
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

            # Timeout
            status_queue.put(json.dumps({
                "status": "failed",
                "message": "视频号扫码登录超时",
            }))
        except Exception as exc:
            print(f"[channels] login error: {exc}")
            status_queue.put(json.dumps({
                "status": "failed",
                "message": str(exc),
            }))
        finally:
            try:
                await context.close()
            except Exception:
                pass
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
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(TENCENT_UPLOAD_URL)
            try:
                await page.wait_for_url(TENCENT_UPLOAD_URL, timeout=5000)
            except Exception:
                pass

            login_button = page.get_by_text("扫码登录", exact=True).first
            if await login_button.count():
                print("[channels] cookie invalid — login form visible")
                return False

            print("[channels] cookie valid")
            return True
        except Exception as exc:
            print(f"[channels] cookie check error (treating as invalid): {exc}")
            return False
        finally:
            try:
                await context.close()
            except Exception:
                pass
            try:
                await browser.close()
            except Exception:
                pass

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
            print(f"[channels] sync_profile error: {exc}")
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
                context = browser.new_context(storage_state=cookie_path)
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
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*str*, optional) -- original declaration category
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``is_draft`` (*bool*, optional)
        - ``thumbnail_path`` (*str*, optional) -- cover image
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
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")

        # Resolve file paths
        resolved_files = [str(Path(BASE_DIR / "videoFile" / f)) for f in files]
        resolved_accounts = [
            str(Path(BASE_DIR / "cookiesFile" / a)) for a in account_files
        ]
        if thumbnail_path:
            thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(resolved_files),
            enable_timer,
            videos_per_day,
            daily_times,
            start_days,
        )

        # Run the async upload in a new event loop (same pattern as legacy)
        async def _do_upload():
            for index, file_path in enumerate(resolved_files):
                publish_date = publish_datetimes[index]
                for cookie_path in resolved_accounts:
                    print(f"[channels] uploading: {file_path}")
                    print(f"[channels] title: {title}")
                    print(f"[channels] desc: {desc}")
                    print(f"[channels] tags: {tags}")

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
                        await _fill_title_and_tags(page, title, tags)
                        await _fill_description(page, desc)
                        await _apply_collection(page)
                        await _apply_original_statement(page, category)

                        # Wait for upload to finish (auto-retries on error)
                        await _wait_for_upload_complete(page, file_path)

                        # Set cover image
                        await _set_thumbnail(page, thumbnail_path)

                        # Set schedule if needed
                        if enable_timer and publish_date != 0:
                            await _set_schedule_time(page, publish_date)

                        # Set short title
                        await _set_short_title(page, title)

                        # Submit
                        await _submit_publish(page, is_draft)

                        # Update stored cookies
                        await context.storage_state(path=cookie_path)
                        print("[channels] cookies updated")
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
