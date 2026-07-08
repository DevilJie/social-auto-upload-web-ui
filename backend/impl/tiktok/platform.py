"""
TikTok platform implementation — CloakBrowser automation.

All browser operations go through BasePlatform's CloakBrowser entry points.
"""

import asyncio
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_user_profile,
)
from ..base_platform import BasePlatform

from util._logger import bind_account_name, get_channel_logger

logger = get_channel_logger("tiktok")

# TikTok upload page uses an iframe; these locators select the correct DOM root.
TK_IFRAME = '[data-tt="Upload_index_iframe"]'
TK_DEFAULT = 'body'


class TiktokPlatform(BasePlatform):
    platform_id = 7
    platform_key = "tiktok"
    platform_name = "TikTok"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".tiktok.com"

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
    # Login
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform TikTok login via browser.

        Opens ``https://www.tiktok.com/login?lang=en`` and waits
        indefinitely (timeout=0) for the URL to match a logged-in
        state (``foryou`` / ``following`` / ``upload`` / ``@...``),
        then scrapes the user profile and saves the result via
        :func:`save_login_result`.
        """
        browser = await self.create_browser(
            headless=False,
            login_mode=True,
        )
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto("https://www.tiktok.com/login?lang=en")

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                # timeout=0 表示永久等待（避免 Playwright 默认 30s 超时）
                await page.wait_for_url(
                    re.compile(r"/(foryou|following|upload|@)"),
                    timeout=0,
                )

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_user_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                # 释放 context 资源
                await context.close()
        finally:
            # 成功才关浏览器（失败/异常时留着让用户看现场）
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # Cookie validation
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Check whether the saved cookie file is still valid.

        Opens the TikTok Studio upload page and inspects ``<select>``
        elements for a class matching ``tiktok-.*-SelectFormContainer.*``,
        which indicates an expired / unauthenticated session.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=en")
            await page.wait_for_load_state("networkidle")
            try:
                select_elements = await page.query_selector_all("select")
                for element in select_elements:
                    class_name = await element.get_attribute("class")
                    if class_name and re.match(
                        r"tiktok-.*-SelectFormContainer.*", class_name
                    ):
                        return False
                return True
            except Exception:
                return True
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Profile sync
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from TikTok.

        Opens ``https://www.tiktok.com/tiktokstudio`` with saved
        cookies and reads the user info block in the home dashboard:

        - 昵称 — ``div[data-tt="NewHome_UserInfo_Hover"]`` 文本
        - 头像 — ``img[data-tt="components_Avatar_AvatarImg"]`` 的 ``src``

        Returns:
            tuple[str, str]: ``(display_name, avatar_url)`` — either
            field is ``""`` if the selector cannot be found.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(
                "https://www.tiktok.com/tiktokstudio",
                wait_until="domcontentloaded",
            )

            # Wait for the user-info block to render
            try:
                await page.wait_for_selector(
                    'div[data-tt="NewHome_UserInfo_FlexRow"]',
                    timeout=15_000,
                )
            except Exception:
                logger.info("[tiktok] sync_profile: user info block not found")
                return ("", "")

            nickname = ""
            try:
                nickname_el = page.locator(
                    'div[data-tt="NewHome_UserInfo_Hover"]'
                ).first
                if await nickname_el.count():
                    nickname = (await nickname_el.inner_text()).strip()
            except Exception:
                pass

            avatar_url = ""
            try:
                avatar_el = page.locator(
                    'img[data-tt="components_Avatar_AvatarImg"]'
                ).first
                if await avatar_el.count():
                    avatar_url = (await avatar_el.get_attribute("src")) or ""
            except Exception:
                pass

            logger.info(
                f"[tiktok] sync_profile: nickname={nickname!r} avatar_set={bool(avatar_url)}"
            )
            return (nickname, avatar_url)
        except Exception as e:
            logger.info(f"[tiktok] sync_profile error: {e}")
            return ("", "")
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Open creator centre (unchanged — uses sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the TikTok creator centre in a visible browser window.

        Uses the same synchronous Playwright pattern as the Douyin
        ``open_creator_center`` implementation.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://www.tiktok.com/tiktokstudio/upload?lang=en"

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
    # Publish video — main entry point (sync)
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to TikTok.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``thumbnail_portrait_path`` (*str*, optional) -- preferred (TikTok is portrait-first)
        - ``thumbnail_landscape_path`` (*str*, optional) -- fallback for landscape videos
        - ``thumbnail_path`` (*str*, optional) -- legacy single-thumbnail field
        - ``ai_content`` (*Any*, optional) -- truthy value enables the
          "AI 生成的内容" toggle on the publish page
        """
        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Publish video — async orchestrator
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs) -> None:
        """Iterate over (file, account) combinations and upload each."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始TikTok视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", [])
        account_files = kwargs.get("account_file", [])
        enable_timer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content")

        # Frontend now sends portrait + landscape separately. TikTok is
        # portrait-first, prefer portrait and fall back to landscape,
        # then to the legacy single-thumbnail field for back-compat.
        thumb = (
            kwargs.get("thumbnail_portrait_path")
            or kwargs.get("thumbnail_landscape_path")
            or kwargs.get("thumbnail_path")
        )

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 账号数量: %d", len(account_files))
        logger.info("[发布参数] 定时发布: %s", enable_timer)
        logger.info("[发布参数] 封面: %s", thumb or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

        # Resolve paths
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]
        cookie_paths = [
            str(Path(BASE_DIR / "cookiesFile" / c)) for c in account_files
        ]

        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enable_timer,
            videos_per_day,
            daily_times,
            start_days,
        )

        for idx, file_path in enumerate(file_paths):
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", idx + 1, len(file_paths), file_path)
            pub_dt = (
                publish_datetimes[idx]
                if isinstance(publish_datetimes, list)
                else publish_datetimes
            )
            for cookie_index, cookie_path in enumerate(cookie_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(cookie_paths), nick or "未知")
                    await self._upload_single(
                        title=title,
                        file_path=file_path,
                        tags=tags,
                        publish_date=pub_dt,
                        account_file=cookie_path,
                        thumbnail_path=thumb,
                        ai_content=ai_content,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Publish video — single upload
    # ------------------------------------------------------------------

    async def _upload_single(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        thumbnail_path: str | None = None,
        ai_content=None,
    ) -> None:
        """Upload one video to one TikTok account using CloakBrowser.
        """
        # === 诊断日志：打印关键参数 + 文件存在性验证 ===
        import os
        logger.info("[上传视频] === _upload_single 接收参数 ===")
        logger.info("[上传视频]   title=%r", title)
        logger.info("[上传视频]   file_path=%r", file_path)
        logger.info(
            "[上传视频]   file_path 是否存在=%s",
            os.path.exists(file_path) if file_path else "N/A (空)",
        )
        if file_path and not os.path.exists(file_path):
            # 列举父目录看实际有什么
            parent = os.path.dirname(file_path)
            if os.path.isdir(parent):
                siblings = os.listdir(parent)[:10]
                logger.info(
                    "[上传视频]   父目录 %r 存在，样本: %s", parent, siblings
                )
            else:
                logger.info("[上传视频]   父目录 %r 不存在！", parent)
        logger.info("[上传视频]   tags=%r", tags)
        logger.info("[上传视频]   publish_date=%r", publish_date)
        logger.info("[上传视频]   account_file=%r", account_file)
        logger.info(
            "[上传视频]   account_file 是否存在=%s",
            os.path.exists(account_file) if account_file else "N/A",
        )
        logger.info("[上传视频]   thumbnail_path=%r", thumbnail_path)
        if thumbnail_path:
            logger.info(
                "[上传视频]   thumbnail_path 是否存在=%s",
                os.path.exists(thumbnail_path),
            )
        logger.info("[上传视频]   ai_content=%r", ai_content)
        logger.info("[上传视频] === 参数打印完毕 ===")

        browser = await self.create_browser(
            headless=False,
        )

        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )
            page = await context.new_page()

            # 1. Navigate directly to upload page (?lang=en skips the lang picker)
            await page.goto("https://www.tiktok.com/tiktokstudio/upload?lang=en")
            logger.info(f"[上传视频] 开始上传: {title}")

            # 2. Wait for the upload UI to render.  The page can take a
            #    few seconds to mount the hidden <input type="file"> in
            #    the DOM — without this wait, set_input_files is called
            #    before the element exists and hangs.
            try:
                await page.wait_for_selector(
                    'input[type="file"]',
                    timeout=10_000,
                    state="attached",
                )
                logger.info("[上传视频] Hidden file input present in DOM")
            except Exception:
                logger.info(
                    "[上传视频] Hidden file input NOT in DOM within 10s — "
                    "will rely on set_input_files auto-wait"
                )

            # 3. Locate the hidden file input — iframe (legacy) first, main page fallback.
            if await page.locator('iframe[data-tt="Upload_index_iframe"]').count():
                file_input = page.frame_locator(TK_IFRAME).locator(
                    'input[type="file"]'
                ).first
                logger.info("[上传视频] Using iframe file input")
            else:
                file_input = page.locator('input[type="file"]').first
                logger.info("[上传视频] Using main page file input")

            try:
                await file_input.set_input_files(file_path, timeout=60_000)
                logger.info(f"[上传视频] 视频文件已选择: {file_path}")
            except Exception as e:
                logger.info(f"[上传视频] set_input_files FAILED: {e!r}")
                raise

            # 4. Wait for the publish UI to render (caption container visible)
            await page.locator('[data-e2e="caption_container"]').wait_for(
                state="visible", timeout=120_000
            )
            logger.info("[上传视频] Publish UI ready")

            # 5. Dismiss any first-run tutorial tooltip ("全新编辑功能已上线")
            await self._dismiss_tutorial_tooltip(page)

            # 6. Dismiss "开启自动内容检查？" modal if it appears
            await self._dismiss_content_check_modal(page)

            # 7. Fill title + tags
            logger.info(f"[上传视频] [step 7] start: title={title!r} tags={tags!r}")
            await self._add_title_tags(page, title, tags)
            logger.info("[上传视频] [step 7] done")

            # 8. Upload thumbnail if provided
            if thumbnail_path:
                logger.info(f"[上传视频] [step 8] start: thumbnail={thumbnail_path}")
                await self._set_cover(page, thumbnail_path)
                logger.info("[上传视频] [step 8] done")
            else:
                logger.info("[上传视频] [step 8] skipped (no thumbnail)")

            # 9. Toggle AI declaration if requested
            if ai_content and str(ai_content).lower() not in ("false", "0", ""):
                logger.info(f"[上传视频] [step 9] start: ai_content={ai_content!r}")
                await self._set_ai_declaration(page, enable=True)
                logger.info("[上传视频] [step 9] done")
            else:
                logger.info("[上传视频] [step 9] skipped")

            # 10. Schedule if needed
            if publish_date != 0:
                logger.info(f"[上传视频] [step 10] start: publish_date={publish_date}")
                await self._set_schedule_time(page, publish_date)
                logger.info("[上传视频] [step 10] done")
            else:
                logger.info("[上传视频] [step 10] skipped (no schedule)")

            # 11. Click publish and wait for success
            await self._click_publish(page)

            # 12. Log video ID
            video_id = await self._get_last_video_id(page)
            logger.info(f"[上传视频] video_id: {video_id}")

            # 13. Update cookie
            await context.storage_state(path=account_file)
            logger.info("[上传视频] Cookie updated")

            await asyncio.sleep(2)

        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Upload sub-operations (private helpers)
    # ------------------------------------------------------------------

    @staticmethod
    async def _dismiss_tutorial_tooltip(page) -> None:
        """Dismiss the "全新编辑功能已上线" tutorial tooltip if it appears.

        Tutorial tooltip shows once per account (first upload). Click the
        primary "知道了" button in the footer to close it. No-op if the
        tooltip is not present.
        """
        try:
            tooltip = page.locator('div.tutorial-tooltip').first
            if not await tooltip.is_visible(timeout=2_000):
                return
            got_it_btn = tooltip.locator(
                'button.Button__root--type-primary:has-text("知道了")'
            ).first
            await got_it_btn.wait_for(state="visible", timeout=3_000)
            await got_it_btn.click()
            logger.info("[关闭引导] Dismissed tutorial tooltip")
        except Exception:
            # Tooltip not shown — fine
            pass

    @staticmethod
    async def _dismiss_content_check_modal(page) -> None:
        """Dismiss the "开启自动内容检查？" modal if it appears.

        Clicks the primary 开启 button.  No-op if the modal is not
        present (e.g. user has already accepted the prompt before).
        """
        try:
            modal = page.locator('div.TUXModal.common-modal').first
            if not await modal.is_visible(timeout=2_000):
                return
            enable_btn = page.locator(
                'div.TUXModal.common-modal '
                'div.common-modal-footer '
                'button.Button__root--type-primary'
            ).first
            await enable_btn.wait_for(state="visible", timeout=3_000)
            await enable_btn.click()
            logger.info("[关闭弹窗] Dismissed '开启自动内容检查' modal")
        except Exception:
            # Modal not shown — fine
            pass

    @staticmethod
    async def _dismiss_ai_label_modal(page) -> None:
        """Dismiss the "标记 AI 生成的内容" confirmation modal.

        Appears after the user toggles the AI declaration switch on.
        We scope to the modal whose <h2> reads "标记 AI 生成的内容" so
        we never accidentally click the wrong primary button on the
        "开启自动内容检查？" modal.  Click "开启" to confirm.  No-op
        if the modal is not present.
        """
        try:
            modal = page.locator(
                'div.TUXModal.common-modal:has(h2:has-text("标记 AI 生成的内容"))'
            ).first
            if not await modal.is_visible(timeout=2_000):
                return
            enable_btn = modal.locator(
                'div.common-modal-footer '
                'button.Button__root--type-primary:has-text("开启")'
            ).first
            await enable_btn.wait_for(state="visible", timeout=3_000)
            await enable_btn.click()
            logger.info("[关闭弹窗] Dismissed '标记 AI 生成的内容' modal")
        except Exception:
            # Modal not shown — fine
            pass

    @staticmethod
    async def _dismiss_publish_confirm_modal(page) -> None:
        """Dismiss the "继续发布？" copyright-check warning modal.

        Appears after clicking 发布 if TikTok's copyright/content
        check is still running. Click "立即发布" to force-publish.
        No-op if the modal is not present.

        The modal may be inside an iframe (TikTok's upload page uses
        ``iframe[data-tt="Upload_index_iframe"]``), so we iterate through
        all frames. We use ``state="attached"`` (not ``state="visible"``)
        because the modal's opening transition animation makes the
        visibility check flaky — and ``force=True`` on click to bypass
        actionability checks that can also fail during the transition.
        """
        try:
            frames = [page] + list(page.frames)
            for frame in frames:
                try:
                    btn = frame.locator(
                        'div.TUXModal.common-modal-confirm-modal '
                        'div.common-modal-footer '
                        'button:has-text("立即发布")'
                    ).first
                    # 等 button 在 DOM 里(最多 10 秒,忽略可见性检查)
                    await btn.wait_for(state="attached", timeout=10_000)
                    # force click 跳过可见性/可点击性/遮挡检查
                    await btn.click(force=True, timeout=2_000)
                    logger.info(
                        f"[上传视频] Dismissed '继续发布？' modal "
                        f"in frame url={frame.url[:60]!r}"
                    )
                    return
                except Exception:
                    # Frame 不可访问或 button 不在,try next frame
                    continue
            logger.info("[关闭弹窗] _dismiss_publish_confirm_modal: button not found in any frame within 10s")
        except Exception as e:
            logger.info(f"[关闭弹窗] _dismiss_publish_confirm_modal: {e!r}")

    @staticmethod
    async def _add_title_tags(page, title: str, tags: list) -> None:
        """Enter video title and hashtags into the DraftEditor.

        TikTok uses Draft.js for the description editor — unlike a
        plain ``<textarea>``, it needs real keydown events to convert
        ``#xxx`` text into a hashtag chip.  ``insert_text`` bypasses
        keydown and the editor state gets stuck after the first tag,
        so we use ``keyboard.type`` with a per-character delay (same
        approach as the xiaohongshu publisher).
        """
        logger.info(f"[填写标题] [_add_title_tags] start: title={title!r} tags={tags!r}")
        editor = page.locator("div.public-DraftEditor-content").first
        logger.info("[填写标题] [_add_title_tags] waiting for editor visible")
        await editor.wait_for(state="visible", timeout=5_000)
        logger.info("[填写标题] [_add_title_tags] clicking editor")
        await editor.click()
        logger.info("[填写标题] [_add_title_tags] clearing editor")
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await clear_and_type(page, "")

        clean_title = (title or "").rstrip()
        if clean_title:
            logger.info(f"[填写标题] [_add_title_tags] typing title: {clean_title!r}")
            await page.keyboard.type(clean_title, delay=20)
        logger.info("[填写标题] [_add_title_tags] pressing Space to commit title")
        await page.keyboard.press("Space")
        await asyncio.sleep(0.3)

        for idx, tag in enumerate(tags or []):
            if not tag:
                continue
            logger.info(f"[填写标题] [_add_title_tags] tag {idx+1}/{len(tags)}: typing #{tag}")
            # type (not insert_text) so Draft.js sees keydown events
            await page.keyboard.type(" " + "#" + tag, delay=40)
            logger.info(f"[填写标题] [_add_title_tags] tag {idx+1}/{len(tags)}: sleep 0.4")
            await asyncio.sleep(0.4)
            logger.info(f"[填写标题] [_add_title_tags] tag {idx+1}/{len(tags)}: pressing Space")
            # Space commits #tag → hashtag chip
            await page.keyboard.press("Space")
            logger.info(f"[填写标题] [_add_title_tags] tag {idx+1}/{len(tags)}: sleep 0.3")
            # let the chip conversion settle before next iteration
            await asyncio.sleep(0.3)

        # Press Escape to close any lingering autocomplete dropdown
        # so the next interaction (cover/schedule click) isn't blocked.
        logger.info("[填写标题] [_add_title_tags] Escape to close any open dropdown")
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.3)
        logger.info("[填写标题] [_add_title_tags] done")

    @staticmethod
    async def _set_cover(page, thumbnail_path: str) -> None:
        """Open the cover editor dialog, upload the image, then save.

        流程：点 "编辑封面" → 弹窗里找隐藏的 input=file → 上传图片
        → 点 "保存" 关闭弹窗。
        """
        logger.info(f"[设置封面] [_set_cover] start: {thumbnail_path}")
        cover_container = page.locator('[data-e2e="cover_container"]').first
        logger.info("[设置封面] [_set_cover] waiting for cover_container")
        await cover_container.wait_for(state="visible", timeout=5_000)
        logger.info("[设置封面] [_set_cover] clicking 编辑封面")
        await cover_container.locator('.edit-container:has-text("编辑封面")').click()

        # Wait for cover editor dialog
        logger.info("[设置封面] [_set_cover] waiting for dialog")
        dialog = page.locator('div.Dialog__content[data-open="true"]').first
        await dialog.wait_for(state="visible", timeout=5_000)
        logger.info("[设置封面] [_set_cover] dialog visible, uploading image")

        # Find hidden image input (accept attribute pins it to jpeg/png/jpg)
        image_input = dialog.locator('input[type="file"]').first
        await image_input.set_input_files(thumbnail_path)
        logger.info("[设置封面] [_set_cover] image set, clicking 保存")

        # Click "保存" in the dialog header
        save_btn = dialog.locator('button.header-button:has-text("保存")').first
        await save_btn.wait_for(state="visible", timeout=5_000)
        await save_btn.click()
        logger.info("[设置封面] [_set_cover] save clicked, waiting for dialog to close")

        # Wait for dialog to close
        await dialog.wait_for(state="hidden", timeout=5_000)
        logger.info("[设置封面] 封面上传成功")

    @staticmethod
    async def _set_ai_declaration(page, *, enable: bool) -> None:
        """Toggle the "AI 生成的内容" switch.

        The switch sits inside the "显示更多" collapsed section
        (div.options-form[hidden]).  We expand that section first,
        otherwise the aigc_container is not visible and would hang
        the wait.
        """
        logger.info(f"[AI声明] [_set_ai_declaration] start: enable={enable}")

        # Step 1: Expand the "显示更多" advanced section if it's still collapsed
        try:
            more_btn = page.locator('div.more-btn:has-text("显示更多")').first
            visible_before = await more_btn.is_visible(timeout=1_000)
            logger.info(f"[AI声明] '显示更多' visible before click: {visible_before}")
            if visible_before:
                await more_btn.click(force=True)
                logger.info("[AI声明] Expanded '显示更多' section")
                await asyncio.sleep(0.8)
        except Exception as e:
            logger.info(f"[AI声明] Expand '显示更多' skipped/failed: {e!r}")

        # Step 2: Diagnose the options-form hidden state
        try:
            of = page.locator('div.options-form').first
            hidden_attr = await of.get_attribute("hidden")
            count = await page.locator('[data-e2e="aigc_container"]').count()
            logger.info(
                f"[上传视频] options-form hidden={hidden_attr!r} "
                f"aigc_container count={count}"
            )
        except Exception as e:
            logger.info(f"[AI声明] diagnosis failed: {e!r}")

        # Step 3: Wait for the AI container (longer timeout)
        container = page.locator('[data-e2e="aigc_container"]').first
        try:
            await container.wait_for(state="visible", timeout=10_000)
            logger.info("[AI声明] aigc_container visible")
        except Exception as e:
            count = await page.locator('[data-e2e="aigc_container"]').count()
            in_dom = count > 0
            logger.info(
                f"[上传视频] aigc_container NOT visible after 10s: "
                f"in_dom={in_dom} count={count} err={e.__class__.__name__}"
            )
            raise
        switch_content = container.locator('div.Switch__content').first
        checked = await switch_content.get_attribute("aria-checked")
        is_on = checked == "true"
        logger.info(f"[AI声明] AI switch initial state: is_on={is_on}")

        # Click the visible Switch__root — the underlying <input> is
        # styled ``appearance: none`` and ``aria-hidden="true"`` so it's
        # a state mirror, not a click target.  Real click handler sits
        # on the outer div.Switch__root.
        if enable and not is_on:
            logger.info("[AI声明] AI declaration: clicking Switch__root to enable")
            await container.locator('div.Switch__root').click(force=True)
            await asyncio.sleep(0.4)
            new_checked = await switch_content.get_attribute("aria-checked")
            logger.info(f"[AI声明] AI declaration after click: aria-checked={new_checked!r}")
            # Toggling AI on pops the "标记 AI 生成的内容" confirm modal
            await TiktokPlatform._dismiss_ai_label_modal(page)
        elif not enable and is_on:
            logger.info("[AI声明] AI declaration: clicking Switch__root to disable")
            await container.locator('div.Switch__root').click(force=True)
            await asyncio.sleep(0.4)
        else:
            logger.info(f"[AI声明] AI declaration already in target state (is_on={is_on})")

    @staticmethod
    async def _set_schedule_time(page, publish_date) -> None:
        """Set a scheduled publish date/time on the publish page.

        1. Click the 预约发布 radio label
        2. Click the date input, navigate the calendar to the target month
        3. Click the target day
        4. Click the time input, pick the hour/minute in the time picker
        """
        logger.info(f"[定时发布] [_set_schedule_time] start: {publish_date}")
        # 1. Click "预约发布" radio
        schedule_label = page.locator('label.Radio__root:has-text("预约发布")').first
        logger.info("[定时发布] [_set_schedule_time] waiting for 预约发布 label")
        await schedule_label.wait_for(state="visible", timeout=5_000)
        await schedule_label.click()
        logger.info("[定时发布] [_set_schedule_time] clicked 预约发布")

        # 2. Date input — TUXFormField with .TUXInputBox, value="YYYY-MM-DD"
        date_input = page.locator(
            'div.TUXFormField.TUXTextInput input.TUXTextInputCore-input'
        ).nth(1)
        await date_input.wait_for(state="visible", timeout=5_000)
        await date_input.click()

        calendar = page.locator('div.calendar-wrapper').first
        await calendar.wait_for(state="visible", timeout=5_000)

        # --- Navigate to target month ---
        CN_MONTHS = {
            "一月": 1, "二月": 2, "三月": 3, "四月": 4,
            "五月": 5, "六月": 6, "七月": 7, "八月": 8,
            "九月": 9, "十月": 10, "十一月": 11, "十二月": 12,
        }
        month_title = calendar.locator('span.month-title').first
        current_month_text = (await month_title.inner_text()).strip()
        current_month = CN_MONTHS.get(current_month_text)
        if current_month is None:
            # Fallback — try English parse, else default to current
            try:
                current_month = datetime.strptime(current_month_text, "%B").month
            except ValueError:
                logger.info(f"[定时发布] Unknown month title: {current_month_text}")
                current_month = publish_date.month

        # Click the right-arrow until the displayed month matches the target.
        # The picker only shows adjacent months (no year jump), so we bail out
        # after one click to avoid getting stuck.
        right_arrow = calendar.locator('span.arrow').nth(1)
        if current_month != publish_date.month:
            try:
                await right_arrow.click(timeout=2_000)
            except Exception:
                pass

        # --- Day selection ---
        valid_days = calendar.locator('span.day.valid')
        day_count = await valid_days.count()
        target_day = str(publish_date.day)
        for i in range(day_count):
            day_el = valid_days.nth(i)
            text = (await day_el.inner_text()).strip()
            if text == target_day:
                await day_el.click()
                break

        # Wait for calendar to close
        await calendar.wait_for(state="hidden", timeout=5_000)

        # 3. Time input — first TUXTextInput, value="HH:MM"
        time_input = page.locator(
            'div.TUXFormField.TUXTextInput input.TUXTextInputCore-input'
        ).nth(0)
        await time_input.wait_for(state="visible", timeout=5_000)
        await time_input.click()

        time_picker = page.locator(
            'div.tiktok-timepicker-time-picker-container'
        ).first
        await time_picker.wait_for(state="visible", timeout=5_000)

        hour_str = publish_date.strftime("%H")
        correct_minute = int(publish_date.minute / 5)
        minute_str = f"{correct_minute:02d}"

        await time_picker.locator(
            f'span.tiktok-timepicker-left:has-text("{hour_str}")'
        ).first.click()
        await time_picker.locator(
            f'span.tiktok-timepicker-right:has-text("{minute_str}")'
        ).first.click()

        # Close the time picker by clicking outside
        await page.keyboard.press("Escape")

    @staticmethod
    async def _click_publish(page) -> None:
        """Click the publish button and wait for redirect to content page.

        Button text is "发布" for immediate publish, "预约发布" for
        scheduled — both share ``data-e2e="post_video_button"``.  We
        poll the click until the URL changes to ``/tiktokstudio/content``.

        Guarded by ``page.is_closed()`` so the loop exits cleanly when
        the user (or TikTok's own navigation) closes the page — without
        this, a closed-page ``TargetClosedError`` re-enters the loop and
        Playwright throws ``Object prototype may only be an Object or
        null: undefined`` on the next locator call.
        """
        max_attempts = 60  # 60 * 0.5s = 30s upper bound on the loop
        for _ in range(max_attempts):
            # 如果 page 已关闭（用户关浏览器 / TikTok 跳页关闭），直接退出循环
            if page.is_closed():
                logger.info("[发布] Page closed, exit _click_publish loop")
                return
            try:
                publish_btn = page.locator(
                    'button[data-e2e="post_video_button"]'
                ).first
                await publish_btn.wait_for(state="visible", timeout=5_000)
                disabled = await publish_btn.get_attribute("disabled")
                if disabled is not None:
                    logger.info("[发布] Publish button disabled, waiting...")
                    await asyncio.sleep(0.5)
                    continue
                await publish_btn.click()
                # Clicking 发布 may pop a "继续发布？" copyright-check
                # warning — dismiss it before waiting for the URL to
                # change to /tiktokstudio/content.
                await TiktokPlatform._dismiss_publish_confirm_modal(page)

                await page.wait_for_url(
                    re.compile(r"/tiktokstudio/content"),
                    timeout=10_000,
                )
                logger.info("[发布] Video published successfully")
                return
            except Exception as e:
                logger.info(f"[发布] Waiting for publish... ({e.__class__.__name__})")
                await asyncio.sleep(0.5)
        logger.info(f"[发布] _click_publish loop exhausted {max_attempts} attempts")

    @staticmethod
    async def _get_last_video_id(page):
        """Extract the video ID of the most recently uploaded video.

        Called *after* the publish redirect to /tiktokstudio/content.
        """
        try:
            await page.wait_for_selector(
                'div[data-tt="components_PostTable_Container"]',
                timeout=10_000,
            )
            video_list = page.locator(
                'div[data-tt="components_PostTable_Container"] '
                'div[data-tt="components_PostInfoCell_Container"] a'
            )
            if await video_list.count():
                href = await video_list.nth(0).get_attribute("href")
                if href:
                    match = re.search(r"video/(\d+)", href)
                    return match.group(1) if match else None
        except Exception:
            pass
        return None
