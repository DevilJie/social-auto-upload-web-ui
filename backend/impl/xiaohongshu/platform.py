"""
Xiaohongshu platform implementation.

Pure CloakBrowser implementation -- all browser operations use
``_browser.py`` (CloakBrowser stealth layer) directly for every
login, cookie-check, profile-sync and publish action.
"""

import asyncio
import os
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser as _create_browser_async
from .._browser import create_browser_sync
from .._browser import create_context as _create_context_async
from .._utils import scrape_user_profile, save_login_result, parse_schedule_time
from ..base_platform import BasePlatform

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_XHS_LOGIN_URL = "https://creator.xiaohongshu.com/login"
_XHS_CREATOR_URL = "https://creator.xiaohongshu.com/"
_XHS_PUBLISH_VIDEO_URL = (
    "https://creator.xiaohongshu.com/publish/publish?from=homepage&target=video"
)
_XHS_LOGIN_BOX_SELECTOR = "div[class*='login-box']"
_XHS_LOGIN_SWITCH_SELECTOR = "img.css-wemwzq"
_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
_PUBLISH_STRATEGY_SCHEDULED = "scheduled"


# ======================================================================
# XiaohongshuPlatform
# ======================================================================

class XiaohongshuPlatform(BasePlatform):
    platform_id = 1
    platform_key = "xiaohongshu"
    platform_name = "小红书"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform Xiaohongshu login via QR code scan.

        Opens the creator page, switches to QR mode by clicking
        ``img.css-wemwzq``, extracts the QR code from the 3rd image,
        monitors URL change for login completion, then delegates to
        ``save_login_result`` for profile scraping + cookie + DB write.
        """
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if page.url != original_url:
                url_changed_event.set()

        browser = await _create_browser_async(login_mode=True, extra_args=["--lang en-GB"])
        context = await _create_context_async(browser)
        try:
            page = await context.new_page()
            await page.goto(_XHS_CREATOR_URL)

            # Switch to QR-code login mode
            await page.locator(_XHS_LOGIN_SWITCH_SELECTOR).click()

            # QR is the 3rd image on the page
            img_locator = page.get_by_role("img").nth(2)
            src = await img_locator.get_attribute("src")
            original_url = page.url
            print(f"[xhs] QR code src: {src}")
            status_queue.put(src)

            page.on(
                "framenavigated",
                lambda frame: (
                    asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None
                ),
            )

            try:
                await asyncio.wait_for(url_changed_event.wait(), timeout=200)
                print("[xhs] login page navigation detected")
            except asyncio.TimeoutError:
                print("[xhs] login timeout")
                status_queue.put("500")
                return

            # Login succeeded -- scrape profile, save cookie, write DB
            await save_login_result(
                context, page,
                platform_id=self.platform_id,
                platform_name=self.platform_name,
                status_queue=status_queue,
            )
        finally:
            await context.close()
            await browser.close()

    # ------------------------------------------------------------------
    # check_cookie()
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens the publish page and checks for login redirect or a visible
        login box.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            return False

        browser = await _create_browser_async(headless=True)
        try:
            context = await _create_context_async(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_XHS_PUBLISH_VIDEO_URL, timeout=30000)
                await page.wait_for_timeout(3000)

                # Redirected to login page means cookie expired
                if page.url.startswith(_XHS_LOGIN_URL):
                    print("[xhs] cookie expired (redirected to login)")
                    return False

                # Login box still visible means cookie expired
                login_box = page.locator(_XHS_LOGIN_BOX_SELECTOR).first
                if await login_box.count():
                    try:
                        if await login_box.is_visible():
                            print("[xhs] cookie expired (login box visible)")
                            return False
                    except Exception:
                        return False

                print("[xhs] cookie valid")
                return True
            except Exception as exc:
                print(f"[xhs] cookie check error: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile()
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Xiaohongshu creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _XHS_CREATOR_URL

        browser = await _create_browser_async(headless=True)
        try:
            context = await _create_context_async(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                name, avatar = await scrape_user_profile(page)
                return name, avatar
            except Exception as e:
                print(f"[xhs] sync profile failed: {e}")
                return "", ""
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center()
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Xiaohongshu creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _XHS_CREATOR_URL

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
    # publish_video()
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Xiaohongshu using CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video file names (relative to videoFile/)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional) -- enable scheduled publishing
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_path`` (*str*, optional)
        - ``desc`` (*str*, optional) -- description
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional) -- AI content declaration
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", [])
        account_files = kwargs.get("account_file", [])
        enable_timer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_path = kwargs.get("thumbnail_path", "")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content", "")

        # Resolve file paths
        account_paths = [Path(BASE_DIR / "cookiesFile" / f) for f in account_files]
        file_paths = [Path(BASE_DIR / "videoFile" / f) for f in files]
        if thumbnail_path:
            thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))

        # Parse schedule times
        publish_datetimes = parse_schedule_time(
            schedule_time_str, len(file_paths), enable_timer,
            videos_per_day, daily_times, start_days,
        )
        # XHS compat: if no schedule, pass 0
        if not enable_timer or not schedule_time_str:
            publish_datetimes = 0 if not enable_timer else publish_datetimes

        strategy = (
            _PUBLISH_STRATEGY_SCHEDULED
            if enable_timer and schedule_time_str
            else _PUBLISH_STRATEGY_IMMEDIATE
        )

        for index, file_path in enumerate(file_paths):
            for cookie_path in account_paths:
                print(f"[xhs] video file: {file_path}")
                print(f"[xhs] title: {title}")
                print(f"[xhs] desc: {desc}")
                print(f"[xhs] tags: {tags}")

                pub_date = (
                    publish_datetimes
                    if not isinstance(publish_datetimes, list)
                    else publish_datetimes[index]
                )

                asyncio.run(
                    _publish_single_video(
                        title=title,
                        file_path=str(file_path),
                        tags=tags,
                        publish_date=pub_date,
                        account_file=str(cookie_path),
                        thumbnail_path=thumbnail_path,
                        desc=desc,
                        ai_content=ai_content,
                        publish_strategy=strategy,
                    )
                )
        return True


# ======================================================================
# Internal publish helper
# ======================================================================

async def _publish_single_video(
    title: str,
    file_path: str,
    tags: list,
    publish_date,
    account_file: str,
    thumbnail_path: str = "",
    desc: str = "",
    ai_content: str = "",
    publish_strategy: str = _PUBLISH_STRATEGY_IMMEDIATE,
):
    """Upload and publish one video to Xiaohongshu using CloakBrowser."""

    browser = await _create_browser_async(headless=False)
    try:
        context = await _create_context_async(browser, storage_state=account_file)
        await context.grant_permissions(["geolocation"])
        try:
            page = await context.new_page()
            await _upload_video_content(
                page=page,
                title=title,
                file_path=file_path,
                tags=tags,
                desc=desc,
                thumbnail_path=thumbnail_path,
                ai_content=ai_content,
                publish_date=publish_date,
                publish_strategy=publish_strategy,
            )
            await context.storage_state(path=account_file)
            print("[xhs] cookie updated")
        finally:
            await context.close()
    finally:
        await browser.close()


# ======================================================================
# Core upload logic -- mirrors XiaoHongShuVideo.upload_video_content
# ======================================================================

async def _upload_video_content(
    page,
    title: str,
    file_path: str,
    tags: list,
    desc: str,
    thumbnail_path: str,
    ai_content: str,
    publish_date,
    publish_strategy: str,
):
    """All browser interaction for a single XHS video upload."""

    print(f"[xhs] starting upload: {title}")
    await page.goto(_XHS_PUBLISH_VIDEO_URL)
    await page.wait_for_url(_XHS_PUBLISH_VIDEO_URL)

    # --- Upload video file ---
    await page.locator(
        "div[class^='upload-content'] input[class='upload-input']"
    ).set_input_files(file_path)

    # Poll for upload completion
    while True:
        try:
            upload_input = await page.wait_for_selector(
                "input.upload-input", timeout=3000
            )
            preview_new = await upload_input.query_selector(
                'xpath=following-sibling::div[contains(@class, "preview-new")]'
            )
            if preview_new:
                all_text = await preview_new.inner_text()
                upload_success = any(
                    kw in all_text
                    for kw in [
                        "上传成功", "分辨率", "重新上传",
                        "编辑封面", "已上传", "已选择", "100%",
                    ]
                )
                if not upload_success:
                    stage_elements = await preview_new.query_selector_all("div.stage")
                    for stage in stage_elements:
                        text_content = await page.evaluate(
                            "(element) => element.textContent", stage
                        )
                        if "上传成功" in text_content or "分辨率" in text_content:
                            upload_success = True
                            break

                if upload_success:
                    print("[xhs] video uploaded successfully")
                    break

                print("[xhs] still uploading, waiting...")
            else:
                title_input = page.locator('input[placeholder*="填写标题"]')
                if await title_input.count() > 0 and await title_input.is_visible():
                    print("[xhs] title input appeared, continuing")
                    break
                print("[xhs] waiting for preview area...")
        except Exception as e:
            print(f"[xhs] upload status check: {e}")
        await asyncio.sleep(2)

    # --- Fill title (20 char limit) ---
    print("[xhs] filling title, desc and tags")
    await _fill_title(page, title)
    await _fill_desc(page, desc)
    await _fill_tags(page, tags)

    # --- Set cover / thumbnail ---
    await _set_thumbnail(page, thumbnail_path)

    # --- Set schedule time ---
    if publish_strategy == _PUBLISH_STRATEGY_SCHEDULED and publish_date != 0:
        await _set_schedule_time(page, publish_date)

    # --- Set AI content declaration ---
    await _set_content_declaration(page, ai_content)

    # --- Click publish ---
    while True:
        try:
            if publish_strategy == _PUBLISH_STRATEGY_SCHEDULED:
                await page.locator('button:has-text("定时发布")').click()
            else:
                await page.locator('button:has-text("发布")').click()
            await page.wait_for_url(
                "https://creator.xiaohongshu.com/publish/success?**",
                timeout=3000,
            )
            print("[xhs] video published successfully")
            break
        except Exception:
            print("[xhs] publish button click, retrying...")
            await asyncio.sleep(0.5)


# ======================================================================
# Individual fill helpers
# ======================================================================

async def _fill_title(page, title: str) -> None:
    """Fill the title input (max 20 characters)."""
    container = page.locator('input[placeholder*="填写标题"]')
    await container.fill(title[:20])


async def _fill_desc(page, desc: str) -> None:
    """Fill the description field."""
    if not desc:
        return
    desc_el = page.locator('p[data-placeholder*="输入正文描述"]')
    await desc_el.click()
    await page.keyboard.press("Backspace")
    await page.keyboard.press("Control+KeyA")
    await page.keyboard.press("Delete")
    await page.keyboard.type(desc)
    await page.keyboard.press("Enter")


async def _fill_tags(page, tags: list) -> None:
    """Add tags via keyboard + auto-complete dropdown."""
    if not tags:
        return

    # Ensure the desc area is focused so tags appear in the right place
    desc_el = page.locator('p[data-placeholder*="输入正文描述"]')
    if await desc_el.count() and await desc_el.is_visible():
        await desc_el.click()

    for tag in tags:
        await page.keyboard.type("#" + tag, delay=30)
        await page.locator("#creator-editor-topic-container").wait_for(
            state="visible", timeout=3000
        )
        first_item = page.locator("#creator-editor-topic-container .item").first
        await first_item.wait_for(state="visible", timeout=2000)
        await first_item.click()


async def _set_thumbnail(page, thumbnail_path: str) -> None:
    """Upload a custom cover image via the cover modal."""
    if not thumbnail_path:
        return
    if not os.path.exists(thumbnail_path):
        print(f"[xhs] thumbnail not found: {thumbnail_path}, skipping")
        return

    print("[xhs] setting cover image")

    try:
        # Click the cover upload area
        cover_plugin_title = page.locator("div.cover-plugin-title").filter(
            has_text="设置封面"
        )
        cover_upload_dialog = cover_plugin_title.locator(
            "xpath=ancestor::div[contains(@class, 'cover-plugin-preview')]"
        ).locator("div.cover > div.default:visible")
        await cover_upload_dialog.wait_for(state="visible", timeout=30000)
        await cover_upload_dialog.click(force=True)
        await page.wait_for_timeout(2000)

        # Find the cover modal
        modal_selectors = [
            "div.d-modal.cover-modal",
            "div.cover-modal",
            "div[class*='cover-modal']",
            "div[class*='cover-plugin-modal']",
            "div.d-modal",
        ]
        modal = None
        for sel in modal_selectors:
            if await page.locator(sel).count() > 0:
                modal = page.locator(sel).first
                break

        if not modal:
            print("[xhs] cover modal not found, skipping")
            return

        # Switch to upload cover tab
        tab_selectors = [
            "div.d-tabs-header:has-text('上传封面')",
            ".d-tabs-header-label:has-text('上传封面')",
            "h6:has-text('上传封面')",
            "text=上传封面",
        ]
        for sel in tab_selectors:
            count = await modal.locator(sel).count()
            if count > 0:
                try:
                    await modal.locator(sel).first.click(timeout=3000)
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass
                break

        # Upload file
        file_input = modal.locator('input[type="file"][accept*="image"]').first
        await file_input.wait_for(state="attached", timeout=10000)
        print(f"[xhs] uploading cover: {os.path.basename(thumbnail_path)}")
        await file_input.set_input_files(thumbnail_path)
        await page.wait_for_timeout(3000)

        # Click confirm button
        confirm_selectors = [
            "button.mojito-button:has-text('确定')",
            "button:has-text('确定')",
            ".d-modal-footer button:has-text('确定')",
        ]
        confirm_button = None
        for sel in confirm_selectors:
            if await modal.locator(sel).count() > 0:
                confirm_button = modal.locator(sel).first
                break

        if confirm_button:
            await confirm_button.click()
            try:
                await modal.wait_for(state="hidden", timeout=15000)
                print("[xhs] cover set successfully")
            except Exception:
                print("[xhs] cover modal did not close, continuing anyway")
        else:
            print("[xhs] confirm button not found, skipping cover")
    except Exception as e:
        print(f"[xhs] cover upload failed: {e}")


async def _set_schedule_time(page, publish_date) -> None:
    """Enable timed publishing and set the target date/time."""
    print(f"[xhs] setting schedule time: {publish_date}")
    await (
        page.locator(".custom-switch-card")
        .filter(has_text="定时发布")
        .locator(".d-switch")
        .click()
    )
    await asyncio.sleep(1)
    date_str = publish_date.strftime("%Y-%m-%d %H:%M")
    time_input = page.locator(".d-datepicker-input-filter input.d-text")
    await time_input.fill(str(date_str))
    await asyncio.sleep(1)


async def _set_content_declaration(page, ai_content: str) -> None:
    """Set AI content declaration via d-select dropdown."""
    if not ai_content:
        return

    print(f"[xhs] setting content declaration: {ai_content}")
    try:
        # Click the declaration dropdown trigger
        select_wrapper = page.locator(
            '.d-select-placeholder:has-text("添加内容类型声明")'
        ).first
        if await select_wrapper.count() > 0:
            await select_wrapper.click()
        else:
            await page.locator(".d-select-wrapper").first.click()
        await asyncio.sleep(1)

        # Click the target option
        target_option = page.locator(
            f'.d-option .d-option-name:has-text("{ai_content}")'
        )
        if await target_option.count() > 0:
            await target_option.first.click()
            print(f"[xhs] content declaration set: {ai_content}")
        else:
            print(f"[xhs] declaration option not found: {ai_content}")

        await asyncio.sleep(1)
    except Exception as exc:
        print(f"[xhs] content declaration failed (non-fatal): {exc}")
