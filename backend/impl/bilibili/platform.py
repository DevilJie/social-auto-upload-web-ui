"""
Bilibili platform implementation — 100% CloakBrowser.

All browser operations go through the BasePlatform browser entry points
(``self.create_browser()``, ``self.create_context()``) which delegate to
CloakBrowser via ``_browser.py``.
"""

import asyncio
import os
import re
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import get_channel_logger

logger = get_channel_logger("bilibili")

from .._browser import create_browser_sync, create_context_sync
from .._utils import parse_schedule_time, save_login_result, scrape_bilibili_profile
from ..base_platform import BasePlatform

BILIBILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
BILIBILI_MANAGE_URL = "https://member.bilibili.com/platform/upload-manager/article"
BILIBILI_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
BILIBILI_PUBLISH_STRATEGY_SCHEDULED = "scheduled"

# Default category tid (music)
BILIBILI_DEFAULT_TID = 3

# tid -> Chinese name mapping (matches Bilibili's upload page)
_TID_CN_NAME = {
    1: "动画", 13: "番剧", 23: "电影", 167: "国创", 11: "电视剧",
    177: "纪录片", 4: "游戏", 119: "鬼畜", 3: "音乐", 129: "舞蹈",
    181: "影视", 5: "娱乐", 36: "知识", 188: "科技", 202: "资讯",
    211: "美食", 160: "生活", 223: "汽车", 155: "时尚", 234: "运动",
    217: "动物圈", 19: "VLOG",
    21: "日常", 28: "原创音乐", 31: "翻唱", 33: "连载动画",
    32: "完结动画", 95: "数码", 96: "星海", 122: "野生技术协会",
    207: "资讯", 251: "三农", 76: "游戏人物", 75: "单机游戏",
    65: "网络游戏", 163: "手机游戏", 164: "桌游棋牌",
    171: "电子竞技", 172: "MAD·AMV", 173: "MMD·3D",
}


class BilibiliPlatform(BasePlatform):
    platform_id = 5
    platform_key = "bilibili"
    platform_name = "B站"

    # ------------------------------------------------------------------
    # Login
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Bilibili login via QR code scan.

        Opens ``passport.bilibili.com/login``, finds the QR image via
        multi-selector, waits for the user to scan, then navigates to the
        account home page to scrape profile info.
        """
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if page.url != original_url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()

                await page.goto("https://passport.bilibili.com/login")
                original_url = page.url

                # Locate QR code image with multiple selectors
                src = None
                try:
                    qr_img = page.locator(
                        '.qrcode-img img, img[src*="qrcode"], .login-scan img'
                    ).first
                    src = await qr_img.get_attribute("src")
                    if not src:
                        qr_img = page.get_by_role("img").nth(0)
                        src = await qr_img.get_attribute("src")
                except Exception as e:
                    logger.info(f"[bilibili] failed to locate QR code: {e}")

                if src:
                    logger.info(f"[bilibili] QR code URL: {src[:80]}")
                    status_queue.put(src)
                else:
                    logger.info("[bilibili] QR code image not found")
                    status_queue.put("500")
                    await page.close()
                    await context.close()
                    return

                # Monitor page navigation for login completion
                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await url_changed_event.wait()
                logger.info("[bilibili] login page navigation detected")

                # Navigate to account home and scrape profile
                await page.goto("https://account.bilibili.com/account/home")
                await asyncio.sleep(2)

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_bilibili_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                # 释放 context + page 资源
                await page.close()
                await context.close()
        finally:
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # Cookie check
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid.

        Opens ``member.bilibili.com/platform/home`` with stored cookies.
        If redirected to ``passport.bilibili.com/login``, the cookie is stale.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto("https://member.bilibili.com/platform/home")
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(2)
                if "passport.bilibili.com/login" in page.url:
                    logger.info("[bilibili] cookie expired, needs re-login")
                    return False
                logger.info("[bilibili] cookie valid")
                return True
            except Exception:
                logger.info("[bilibili] cookie check timed out")
                return False
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Sync profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Bilibili account centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://account.bilibili.com/account/home"

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                name, avatar = await scrape_bilibili_profile(page)
                return name, avatar
            except Exception as e:
                logger.info(f"[bilibili] sync profile failed: {e}")
                return "", ""
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Open creator center
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Bilibili creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://member.bilibili.com/platform/upload-manager/article"

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
    # Publish video
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Bilibili.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*int*, optional)
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``desc`` (*str*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional) -- landscape cover
        - ``thumbnail_portrait_path`` (*str*, optional) -- portrait cover
        - ``schedule_time_str`` (*str*, optional)
        - ``creation_declaration`` (*str*, optional)
        """

        async def _run():
            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            tags = kwargs.get("tags", [])
            account_files = kwargs.get("account_file", [])
            category = kwargs.get("category")
            enable_timer = kwargs.get("enableTimer", False)
            videos_per_day = kwargs.get("videos_per_day", 1)
            daily_times = kwargs.get("daily_times")
            start_days = kwargs.get("start_days", 0)
            desc = kwargs.get("desc", "")
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "")
            thumbnail_portrait = kwargs.get("thumbnail_portrait_path", "")
            schedule_time_str = kwargs.get("schedule_time_str", "")
            # ai_content 字段已废弃：B 站新版去掉了"更多设置/声明与权益"，
            # 创作声明直接在主页面设置，保留参数接收以兼容 app.py 调用
            ai_content = kwargs.get("ai_content", "")
            creation_declaration = kwargs.get("creation_declaration", "")

            # Resolve full paths
            cookie_paths = [
                str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_files
            ]
            # files 已是绝对路径（app.py 调用 _resolve_material_path 处理过）
            file_paths = [str(f) for f in files]

            # Bilibili uses landscape cover
            thumbnail_path = None
            if thumbnail_landscape:
                # thumbnail_landscape 已是绝对路径
                thumbnail_path = str(thumbnail_landscape)

            # Parse schedule times
            publish_datetimes = parse_schedule_time(
                schedule_time_str,
                len(file_paths),
                enable_timer,
                videos_per_day,
                daily_times,
                start_days,
            )

            for index, file_path in enumerate(file_paths):
                publish_date = (
                    publish_datetimes[index]
                    if isinstance(publish_datetimes, list)
                    else publish_datetimes
                )
                for cookie_path in cookie_paths:
                    logger.info(f"[bilibili] uploading: {file_path}")
                    logger.info(f"[bilibili] title: {title}")
                    logger.info(f"[bilibili] desc: {desc}")
                    logger.info(f"[bilibili] tags: {tags}")

                    await self._upload_single_video(
                        title=title,
                        file_path=file_path,
                        tags=tags,
                        publish_date=publish_date,
                        account_file=cookie_path,
                        category=category,
                        desc=desc,
                        thumbnail_path=thumbnail_path,
                        creation_declaration=creation_declaration,
                    )

        asyncio.run(_run())
        return True

    # ------------------------------------------------------------------
    # Internal upload helpers
    # ------------------------------------------------------------------

    async def _upload_single_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        category=None,
        desc: str = "",
        thumbnail_path: str | None = None,
        creation_declaration: str = "",
    ):
        """Upload a single video to Bilibili using CloakBrowser."""
        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )

            upload_success = False
            try:
                page = await context.new_page()
                logger.info(f"[bilibili] starting upload: {title}")
                await page.goto(BILIBILI_UPLOAD_URL)
                await page.wait_for_url(
                    "**/platform/upload/**", timeout=30000
                )

                if "passport.bilibili.com" in page.url:
                    raise RuntimeError(
                        "Bilibili cookie expired, please re-login"
                    )

                # 1. Upload video file
                await self._upload_video_file(page, file_path)

                # 2. Wait for upload to complete
                await self._wait_upload_complete(page)
                await asyncio.sleep(3)

                # 2.5 等待页面就绪：B 站"推荐标签"区域（div.tag-wrp 下
                # 的 .hot-tag-container）出现后才说明表单已渲染完整，
                # 此时再开始填充标题/分类/标签等，否则可能因为表单
                # 元素未就绪而操作失败
                # 阻塞等待（10 分钟）—— 不设短超时，宁可等也不跳过
                hot_tag = page.locator(
                    'div.tag-wrp div.hot-tag-container'
                ).first
                await hot_tag.wait_for(
                    state="attached", timeout=600000
                )
                logger.info(
                    "[bilibili] hot-tag-container ready, "
                    "form is interactive"
                )

                # Pre-form screenshot
                await page.screenshot(
                    path=str(log_dir / "bilibili_before_form.png"),
                    full_page=True,
                )

                # 3. Fill title
                await self._fill_title(page, title)

                # 4. Set category
                await self._set_category(page, category)

                # 5. Fill tags
                await self._fill_tags(page, tags)

                # 6. Fill description
                await self._fill_desc(page, desc)

                # 7. Set cover/thumbnail
                await self._set_thumbnail(page, thumbnail_path)

                # 8. Set creation declaration (bcc-select dropdown)
                # B 站新版已废弃"更多设置/声明与权益"，保留创作声明即可
                await self._set_creation_declaration(page, creation_declaration)

                # 9. Set scheduled publish
                if (
                    isinstance(publish_date, int)
                    and publish_date == 0
                ):
                    publish_strategy = BILIBILI_PUBLISH_STRATEGY_IMMEDIATE
                elif publish_date != 0:
                    publish_strategy = BILIBILI_PUBLISH_STRATEGY_SCHEDULED
                else:
                    publish_strategy = BILIBILI_PUBLISH_STRATEGY_IMMEDIATE

                if (
                    publish_strategy == BILIBILI_PUBLISH_STRATEGY_SCHEDULED
                    and publish_date != 0
                ):
                    await self._set_schedule_time(page, publish_date)

                # Pre-submit screenshot
                await page.screenshot(
                    path=str(log_dir / "bilibili_before_submit.png"),
                    full_page=True,
                )

                # 10. Submit
                logger.info("[bilibili] submitting video")
                await page.evaluate(
                    "window.scrollTo(0, document.body.scrollHeight)"
                )
                await asyncio.sleep(1)

                submitted = False
                for attempt in range(10):
                    try:
                        submit_span = page.locator("span.submit-add")
                        if await submit_span.count() > 0:
                            await submit_span.first.scroll_into_view_if_needed()
                            await submit_span.first.click()
                            logger.info("[bilibili] clicked submit button")
                        else:
                            logger.info(
                                f"[bilibili] submit button not found, "
                                f"retry {attempt + 1}/10"
                            )
                            await asyncio.sleep(3)
                            continue

                        await asyncio.sleep(3)
                        for _ in range(15):
                            await asyncio.sleep(2)
                            btn_exists = (
                                await page.locator("span.submit-add").count()
                                > 0
                            )
                            if not btn_exists:
                                logger.info(
                                    "[bilibili] submit success "
                                    "(button disappeared)"
                                )
                                submitted = True
                                break
                            if (
                                page.url != BILIBILI_UPLOAD_URL
                                and "/platform/upload/" not in page.url
                            ):
                                logger.info(
                                    f"[bilibili] submit success, "
                                    f"redirected to: {page.url}"
                                )
                                submitted = True
                                break

                        if submitted:
                            break

                        logger.info(
                            f"[bilibili] page unchanged after click, "
                            f"retry {attempt + 1}/10"
                        )
                        await page.screenshot(
                            path=str(
                                log_dir / f"bilibili_submit_{attempt}.png"
                            ),
                            full_page=True,
                        )
                    except Exception as exc:
                        logger.info(
                            f"[bilibili] submit retry {attempt + 1}/10: {exc}"
                        )
                        await page.screenshot(
                            path=str(
                                log_dir / f"bilibili_submit_{attempt}.png"
                            ),
                            full_page=True,
                        )
                        await asyncio.sleep(2)

                if not submitted:
                    logger.info(
                        "[bilibili] could not confirm submission, "
                        "but it may have succeeded"
                    )

                if submitted:
                    logger.info("[bilibili] waiting 10s for processing")
                    await asyncio.sleep(10)
                    try:
                        await page.screenshot(
                            path=str(
                                log_dir / "bilibili_after_submit.png"
                            ),
                            full_page=True,
                        )
                    except Exception:
                        pass

                upload_success = True
            finally:
                if upload_success:
                    try:
                        await context.storage_state(path=account_file)
                        logger.info("[bilibili] cookie updated")
                    except Exception:
                        pass
                await context.close()
        finally:
            await browser.close()
            logger.info("[bilibili] browser closed")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """Select the video file via iframe or direct file input."""
        logger.info("[bilibili] uploading video file")

        file_input = None
        try:
            upload_frame = page.frame_locator('iframe[name="videoUpload"]')
            input_in_frame = upload_frame.locator('input[type="file"]')
            await input_in_frame.wait_for(state="attached", timeout=5000)
            file_input = input_in_frame
        except Exception:
            logger.info("[bilibili] upload iframe not found, trying main page")

        if file_input is None:
            file_input = page.locator(
                'input[type="file"][accept*="video"], input[type="file"]'
            ).first
            await file_input.wait_for(state="attached", timeout=10000)

        await file_input.set_input_files(file_path)
        logger.info("[bilibili] video file selected, waiting for upload")

    @staticmethod
    async def _wait_upload_complete(page):
        """Wait until the video upload is fully complete and the form
        is interactive.

        "上传完成" 文字出现只是上传成功的标志之一，但封面区需要
        等整个上传流程（含后处理如转码）才能点击。需要满足：
        1. "上传完成" 文字出现
        2. 上传进度条/转码状态消失
        3. 封面区域 (`div.cover-main`) 出现并可见
        """
        max_retries = 120
        retry_count = 0
        while retry_count < max_retries:
            try:
                # Check 1: "上传完成" 文字出现（iframe 或主页）
                done_found = False
                try:
                    upload_frame = page.frame_locator(
                        'iframe[name="videoUpload"]'
                    )
                    done_text = upload_frame.locator("text=上传完成")
                    if (
                        await done_text.count() > 0
                        and await done_text.first.is_visible()
                    ):
                        done_found = True
                except Exception:
                    pass
                if not done_found:
                    done_text_main = page.locator("text=上传完成")
                    if (
                        await done_text_main.count() > 0
                        and await done_text_main.first.is_visible()
                    ):
                        done_found = True

                if done_found:
                    # Check 2: 等待转码中/进度条消失
                    transcoding_locators = [
                        'text=转码中',
                        'text=正在转码',
                        'text=处理中',
                        '.bp-upload-progress',
                        '[class*="progress"]:has-text("100")',
                    ]
                    still_transcoding = False
                    for sel in transcoding_locators:
                        try:
                            loc = page.locator(sel)
                            if await loc.count() > 0 and await loc.first.is_visible():
                                still_transcoding = True
                                break
                        except Exception:
                            continue

                    if not still_transcoding:
                        # Check 3: 封面区域出现且可交互
                        cover_main = page.locator('div.cover-main').first
                        if (
                            await cover_main.count() > 0
                            and await cover_main.is_visible()
                        ):
                            logger.info(
                                "[bilibili] video upload complete, "
                                "cover area ready"
                            )
                            return

                # Check for upload failure
                fail_text = page.locator("text=上传失败")
                if await fail_text.count() > 0:
                    logger.info(
                        "[bilibili] upload failed detected"
                    )

                if retry_count % 10 == 0:
                    logger.info(
                        f"[bilibili] upload in progress... ({retry_count * 3}s)"
                    )

                await asyncio.sleep(3)
            except Exception as exc:
                logger.info(f"[bilibili] upload status check error: {exc}")
                await asyncio.sleep(3)
            retry_count += 1

        if retry_count == max_retries:
            logger.info("[bilibili] upload may not have completed (timeout)")

    @staticmethod
    async def _fill_title(page, title: str):
        """Fill the video title (max 80 chars)."""
        logger.info(f"[bilibili] filling title: {title[:30]}")
        title_input = page.locator(
            'input[placeholder*="标题"], input[placeholder*="Title"], '
            '.video-title input, [class*="title"] input[type="text"]'
        ).first
        await title_input.wait_for(state="visible", timeout=15000)
        await title_input.click()
        await title_input.fill("")
        await title_input.fill(title[:80])

    @staticmethod
    async def _set_category(page, category):
        """Set the video category (partition) via dropdown."""
        if not category:
            return

        # Resolve Chinese name from tid
        if isinstance(category, int):
            cn_name = _TID_CN_NAME.get(category, None)
        else:
            cn_name = str(category).strip()

        logger.info(
            f"[bilibili] setting category: category={category}, "
            f"cn_name={cn_name}"
        )

        if not cn_name:
            logger.info(
                f"[bilibili] unknown category: {category}, skipping"
            )
            return

        try:
            log_dir = Path(BASE_DIR / "logs")
            log_dir.mkdir(parents=True, exist_ok=True)

            # Click select-controller to open dropdown
            select_controller = page.locator(".select-controller").first
            await select_controller.wait_for(state="visible", timeout=10000)
            await select_controller.click()
            logger.info("[bilibili] clicked select-controller")
            await asyncio.sleep(1)

            # Click target partition in dropdown
            target_item = page.locator(
                f'.drop-list-v2-item[title="{cn_name}"]'
            )
            if await target_item.count() > 0:
                await target_item.first.click()
                logger.info(f"[bilibili] category set: {cn_name}")
            else:
                logger.info(
                    f"[bilibili] partition not found in dropdown: {cn_name}"
                )
                await page.screenshot(
                    path=str(
                        log_dir / "bilibili_partition_not_found.png"
                    ),
                    full_page=True,
                )

            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(
                f"[bilibili] category setting failed (non-fatal): {exc}"
            )

    @staticmethod
    async def _fill_tags(page, tags: list):
        """Fill video tags (up to 10 tags)."""
        if not tags:
            return

        # Parse tags: support "#tag1 #tag2" or "tag1,tag2" or mixed
        parsed = []
        for t in tags:
            if isinstance(t, str) and t.strip():
                parsed.extend(
                    s.strip() for s in re.split(r"[,，#]", t) if s.strip()
                )
            elif isinstance(t, str):
                parsed.append(t)
        tags = parsed

        logger.info(f"[bilibili] adding {len(tags)} tags")

        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        # Try multiple selectors for the tag input
        selectors = [
            'input[placeholder*="回车键Enter创建标签"]',
            'input[placeholder*="Enter创建标签"]',
            'input[placeholder*="按回车"]',
            'input[placeholder*="标签"]',
            ".tag-input input",
            '[class*="tag"] input[type="text"]',
        ]

        tag_input = None
        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    tag_input = loc
                    logger.info(f"[bilibili] found tag input: {sel}")
                    break
            except Exception:
                continue

        if tag_input is None:
            logger.info("[bilibili] tag input not found, taking debug screenshot")
            await page.screenshot(
                path=str(log_dir / "bilibili_tag_input_not_found.png"),
                full_page=True,
            )
            return

        for i, tag in enumerate(tags[:10]):
            try:
                # Re-locate input after each tag (DOM may change)
                current_input = None
                for sel in selectors:
                    try:
                        loc = page.locator(sel).first
                        if await loc.count() > 0 and await loc.is_visible():
                            current_input = loc
                            break
                    except Exception:
                        continue
                if current_input is None:
                    logger.info("[bilibili] tag input lost, stopping")
                    break

                await current_input.click()
                await asyncio.sleep(0.3)
                await current_input.type(str(tag), delay=50)
                await asyncio.sleep(0.3)
                await current_input.press("Enter")
                await asyncio.sleep(0.5)
                logger.info(
                    f"[bilibili] added tag ({i + 1}/{min(len(tags), 10)}): "
                    f"{tag}"
                )
            except Exception as exc:
                logger.info(f"[bilibili] failed to add tag '{tag}': {exc}")

    @staticmethod
    async def _fill_desc(page, desc: str):
        """Fill the video description."""
        if not desc:
            return

        logger.info("[bilibili] filling description")
        desc_editor = page.locator(
            '[contenteditable="true"][class*="editor"], '
            ".ql-editor, "
            '[class*="desc"] textarea, '
            '[class*="desc"] [contenteditable="true"]'
        ).first
        if await desc_editor.count() > 0 and await desc_editor.is_visible():
            await desc_editor.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(desc, delay=10)
        else:
            logger.info("[bilibili] description editor not found")

    @staticmethod
    async def _set_thumbnail(page, thumbnail_path: str | None):
        """Upload cover image via the Bilibili cover editor modal.

        兼容性策略：避免硬编码 class 名 / scoped hash / 固定文案。
        按"由稳到脆"顺序探测：
        1. 页面上直接存在的 cover file input（无需点任何按钮）
        2. 任意可点击的"封面"语义按钮（基于 role / aria-label / 文本）
        3. class 模糊匹配（不依赖 scoped hash）
        """
        if not thumbnail_path:
            return
        if not os.path.exists(thumbnail_path):
            logger.info(f"[bilibili] cover file not found: {thumbnail_path}")
            return

        log_dir = Path(BASE_DIR / "logs")
        logger.info("[bilibili] setting cover")

        try:
            await page.screenshot(
                path=str(log_dir / "bilibili_cover_before.png"),
                full_page=True,
            )

            # Step 1: Open cover editor dialog
            # 路径：div.cover-main > div.cover-item > div.cover-img > span.edit-text
            # 不使用 data-v-* scoped hash（每次发版会变）
            dialog_opened = False
            trigger_selectors = [
                # 最精确：完整路径，不依赖 scoped hash
                'div.cover-main div.cover-item div.cover-img span.edit-text',
                # class 子串 + 文本
                '[class*="cover-main"] [class*="cover-item"] [class*="cover-img"] [class*="edit-text"]',
                'span[class*="edit-text"]:has-text("封面设置")',
                'span.edit-text:has-text("封面设置")',
                '[class*="edit-text"]:has-text("封面设置")',
                # 文本兜底
                'span:has-text("封面设置")',
                'button:has-text("封面设置")',
                'text=封面设置',
                # 旧版 B 站（保留兼容）
                "div.cover-item",
                ".cover-item",
                ".video-cover-container",
                ".cover-wrap",
                ".cover-add",
                '[data-reporter-id="112"]',
                ".upload-video-cover",
                'div[class*="cover"] >> text=选择封面',
                'div[class*="cover"] >> text=封面',
            ]
            for sel in trigger_selectors:
                count = await page.locator(sel).count()
                if count > 0:
                    try:
                        await page.locator(sel).first.click(timeout=3000)
                        dialog_opened = True
                        break
                    except Exception:
                        continue

            if not dialog_opened:
                logger.info(
                    "[bilibili] all cover triggers failed, "
                    "skipping cover"
                )
                return

            # Wait for cover editor dialog
            # 兼容旧版"封面制作"和新版"封面设置"两种标题
            dialog = None
            for dialog_sel in [
                'div.bcc-dialog:has-text("封面制作")',
                'div.bcc-dialog:has-text("封面设置")',
                'div.bcc-dialog',
            ]:
                cand = page.locator(dialog_sel).first
                try:
                    await cand.wait_for(state="visible", timeout=8000)
                    dialog = cand
                    break
                except Exception:
                    continue
            if dialog is None:
                raise RuntimeError("封面编辑弹窗未出现")
            await asyncio.sleep(1)
            await asyncio.sleep(1)

            await page.screenshot(
                path=str(log_dir / "bilibili_cover_editor.png"),
                full_page=True,
            )

            # Step 2: Select 4:3 area
            editor_4_3 = page.locator(
                "div.cover-editor-panel-canvas-image.editor_4_3"
            ).first
            if await editor_4_3.count() > 0:
                await editor_4_3.click()
                await asyncio.sleep(0.5)

            # Step 3: Check "sync both ratios" checkbox
            sync_checkbox = page.locator(
                '.sync-checkbox input[type="checkbox"]'
            ).first
            if await sync_checkbox.count() > 0:
                is_checked = await sync_checkbox.is_checked()
                if not is_checked:
                    sync_label = page.locator(".sync-checkbox").first
                    await sync_label.click()
                await asyncio.sleep(0.5)

            await page.screenshot(
                path=str(log_dir / "bilibili_cover_sync_checked.png"),
                full_page=True,
            )

            # Step 4: Upload cover file
            file_input = page.locator(
                '.cover-upload input[type="file"]'
            ).first
            file_count = await file_input.count()

            if file_count > 0:
                await file_input.set_input_files(thumbnail_path)
                logger.info(
                    f"[bilibili] cover file selected: "
                    f"{os.path.basename(thumbnail_path)}"
                )
            else:
                fallback_input = page.locator(
                    'input[accept*="image"]'
                ).first
                if await fallback_input.count() > 0:
                    await fallback_input.set_input_files(thumbnail_path)
                else:
                    logger.info("[bilibili] cover file input not found")
                    return

            # Wait for image processing
            await asyncio.sleep(3)

            # Step 5: Click done button
            submit_btn = page.locator("div.button.submit").first
            if await submit_btn.count() > 0:
                await submit_btn.click()
            await asyncio.sleep(1)

            # Step 6: Click confirm button inside dialog
            confirm_btn = dialog.locator(
                "button.bcc-button--primary"
            ).first
            if await confirm_btn.count() > 0:
                await confirm_btn.click()
            await asyncio.sleep(1)

            # Ensure any stray dialogs are closed
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            logger.info("[bilibili] cover set successfully")

        except Exception as exc:
            try:
                await page.screenshot(
                    path=str(log_dir / "bilibili_cover_error.png"),
                    full_page=True,
                )
            except Exception:
                pass
            raise RuntimeError(f"cover setting failed: {exc}") from exc

    @staticmethod
    async def _set_creation_declaration(page, creation_declaration: str):
        """Set creation declaration via bcc-select dropdown.

        Only shown for some accounts. Silently skipped when not found.
        """
        if not creation_declaration:
            return

        logger.info(
            f"[bilibili] setting creation declaration: "
            f"{creation_declaration}"
        )
        try:
            # Close any popover that may be obscuring
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            select_input = page.locator(
                'input.bcc-select-input-inner[placeholder*="创作声明"]'
            )
            if await select_input.count() == 0:
                # 兼容：用 section title "创作声明" 定位所在容器的 select input
                scoped = page.locator(
                    'div.statement-content, '
                    'div[class*="statement-content"]'
                ).first
                scoped_input = scoped.locator(
                    'input.bcc-select-input-inner'
                ).first
                if await scoped_input.count() > 0:
                    select_input = scoped_input
                else:
                    logger.info(
                        "[bilibili] creation declaration dropdown not "
                        "present, skipping"
                    )
                    return

            await select_input.first.scroll_into_view_if_needed()
            await asyncio.sleep(0.5)
            await select_input.first.click(force=True)
            await asyncio.sleep(1)

            # 等下拉打开：检测 bcc-select-list-wrap 从 display:none 变为可见
            # 用户给的 DOM 里 .bcc-select-list-wrap 默认 display: none，
            # 展开后 inline style 被去除（display: block / 默认）。用
            # 内联 style 判定更准确（避免 :visible 在 display:none 时失效）
            list_wrap = page.locator(
                '.bcc-select-list-wrap:not([style*="display: none"])'
            )
            try:
                await list_wrap.first.wait_for(
                    state="attached", timeout=5000
                )
            except Exception:
                # 兜底：bcc-select 容器加 'is-open'/'is-focus' 类
                fallback = page.locator(
                    '.bcc-select.is-open, .bcc-select.is-focus, '
                    '.bcc-select[class*="open"], .bcc-select[class*="focus"]'
                )
                await fallback.first.wait_for(state="attached", timeout=3000)

            # 在创作声明容器内查选项（避免命中页面其他 bcc-select）
            scoped_options = page.locator(
                'div.statement-content, '
                'div[class*="statement-content"]'
            ).first.locator('li.bcc-option')
            try:
                await scoped_options.first.wait_for(
                    state="attached", timeout=5000
                )
            except Exception:
                pass

            count = await scoped_options.count()

            target_text = creation_declaration.strip()
            clicked = False
            for i in range(count):
                opt = scoped_options.nth(i)
                span = opt.locator("span").first
                opt_text = (await span.text_content() or "").strip()
                if opt_text == target_text:
                    await opt.click()
                    logger.info(
                        f"[bilibili] selected creation declaration: "
                        f"{opt_text}"
                    )
                    clicked = True
                    break

            if not clicked:
                logger.info(
                    f"[bilibili] creation declaration option not found: "
                    f"{target_text}"
                )

            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(
                f"[bilibili] creation declaration failed (non-fatal): "
                f"{exc}"
            )

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Set scheduled publish time via calendar and time picker."""
        from datetime import datetime

        if isinstance(publish_date, int) and publish_date == 0:
            return

        dt = publish_date
        logger.info(
            f"[bilibili] setting schedule: "
            f"{dt.strftime('%Y-%m-%d %H:%M')}"
        )

        try:
            # Step 1: Click switch-container to enable scheduled publish
            switch = page.locator(".switch-container").first
            await switch.wait_for(state="visible", timeout=10000)
            await switch.click()
            await asyncio.sleep(1)

            # Step 2: Open date picker and select date
            target_day = dt.day
            date_trigger = page.locator("div.date-picker-date").first
            await date_trigger.wait_for(state="visible", timeout=10000)
            await date_trigger.click()
            await asyncio.sleep(1)

            # Find clickable date in calendar grid
            target_date_el = page.locator(
                "div.date-picker-body-item.date-item"
            ).filter(has_text=str(target_day))
            date_set = False
            count = await target_date_el.count()
            for i in range(count):
                el = target_date_el.nth(i)
                classes = await el.get_attribute("class") or ""
                if "date-item-disabled" in classes:
                    continue
                text = (await el.text_content() or "").strip()
                if text == str(target_day):
                    await el.click()
                    date_set = True
                    break
            if not date_set:
                logger.info(
                    f"[bilibili] could not find clickable date: "
                    f"{target_day}"
                )
            await asyncio.sleep(0.5)

            # Step 3: Open time picker and select hour + minute
            target_hour = dt.strftime("%H")
            target_minute = dt.strftime("%M")
            time_trigger = page.locator("div.date-picker-timer").first
            await time_trigger.wait_for(state="visible", timeout=10000)
            await time_trigger.click()
            await asyncio.sleep(1)

            # Select hour (first panel)
            hour_panels = page.locator(".time-picker-panel-select-wrp")
            hour_panel = hour_panels.nth(0)
            hour_item = hour_panel.locator(
                "span.time-picker-panel-select-item"
            ).filter(has_text=target_hour)
            if await hour_item.count() > 0:
                await hour_item.first.click()
            await asyncio.sleep(0.3)

            # Select minute (second panel)
            minute_panel = hour_panels.nth(1)
            minute_item = minute_panel.locator(
                "span.time-picker-panel-select-item"
            ).filter(has_text=target_minute)
            if await minute_item.count() > 0:
                await minute_item.first.click()
            await asyncio.sleep(0.3)

            # Close time picker
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

            logger.info("[bilibili] schedule time set")
        except Exception as exc:
            logger.info(f"[bilibili] schedule time setting failed: {exc}")
