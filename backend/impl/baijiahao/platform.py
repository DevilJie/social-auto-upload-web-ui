"""
Baijiahao (百家号) platform implementation -- 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import os
from datetime import datetime

from util._logger import bind_account_name, get_channel_logger
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_baijiahao_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("baijiahao")


class BaijiahaoPlatform(BasePlatform):
    platform_id = 6
    platform_key = "baijiahao"
    platform_name = "百家号"

    # ------------------------------------------------------------------
    # login -- QR code / redirect via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Baijiahao login.

        Opens ``https://baijiahao.baidu.com/builder/theme/bjh/login`` and
        waits for the page to redirect to ``**/builder/rc/home**`` without
        timeout — QR code login may take several minutes.  On success,
        scrapes the user profile and saves the login result via the shared
        utility.
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/theme/bjh/login",
                    wait_until="domcontentloaded",
                )
                logger.info("百家号登录页面已打开，请完成扫码登录...")

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await page.wait_for_url("**/builder/rc/home**", timeout=0)
                logger.info("检测到登录成功，正在保存 cookie...")

                # Scrape profile & save via shared utility
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_baijiahao_profile,
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
    # check_cookie -- verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens ``https://baijiahao.baidu.com/builder/rc/home`` with the
        stored cookies.  If redirected to the login page, the cookie
        is considered invalid.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(
                browser, storage_state=cookie_path
            )
            try:
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/rc/home"
                )
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(2)

                if "baijiahao.baidu.com/builder/theme/bjh/login" in page.url:
                    logger.info("[baijiahao] cookie expired, needs re-login")
                    return False
                else:
                    logger.info("[baijiahao] cookie valid")
                    return True
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile -- refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Baijiahao account settings page.

        Uses ``scrape_baijiahao_profile`` from ``_utils`` to scrape the
        rendered account settings page.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(
                browser, storage_state=cookie_path
            )
            try:
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/rc/home"
                )
                name, avatar = await scrape_baijiahao_profile(page)
                return name, avatar
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center -- visible browser window (sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Baijiahao creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://baijiahao.baidu.com/"

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
    # publish_video -- full Baijiahao upload pipeline (sync entry point)
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Baijiahao (sync wrapper).

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional)
        - ``thumbnail_portrait_path`` (*str*, optional)
        - ``desc`` (*str*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``creation_declaration`` (*str*, optional)
        - ``supplementary_declaration`` (*str*, optional)
        - ``ai_content`` (*bool*, optional)
        """
        # ===== 前置校验:描述+标签总字符 ≤ 50(emoji 按 3 算),最多 10 标签 =====
        desc = kwargs.get("desc", "") or ""
        tags = kwargs.get("tags", []) or []
        ok, err = self._validate_publish_params(desc, tags)
        if not ok:
            logger.error("[发布视频] 百家号前置校验失败: %s", err)
            raise ValueError(err)

        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal: orchestrate all file x account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """Create a browser for each file+account combo and upload."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始百家号视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path")
        desc = kwargs.get("desc", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        creation_declaration = kwargs.get("creation_declaration", "")
        supplementary_declaration = kwargs.get("supplementary_declaration", "")
        ai_content = kwargs.get("ai_content", False)

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 创作声明: %s", creation_declaration or "无")
        logger.info("[发布参数] 补充声明: %s", supplementary_declaration or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enableTimer and schedule_time_str else "immediate")

        # Resolve full paths
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            # 已是绝对路径
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            # 已是绝对路径
            thumbnail_portrait_path = str(thumbnail_portrait_path)

        # Determine schedule times
        publish_datetimes = parse_schedule_time(
            schedule_time_str,
            len(file_paths),
            enableTimer,
            videos_per_day,
            daily_times,
            start_days,
        )

        for file_index, file_path in enumerate(file_paths):
            logger.info("-" * 40)
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s", file_index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_one_video(
                        title=title,
                        file_path=file_path,
                        tags=tags,
                        publish_date=publish_datetimes[file_index],
                        account_file=cookie_path,
                        thumbnail_landscape_path=thumbnail_landscape_path,
                        thumbnail_portrait_path=thumbnail_portrait_path,
                        desc=desc,
                        creation_declaration=creation_declaration,
                        supplementary_declaration=supplementary_declaration,
                        ai_content=ai_content,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Internal: upload one video to one account
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        desc="",
        creation_declaration="",
        supplementary_declaration="",
        ai_content=False,
    ):
        """Upload a single video to one Baijiahao account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser,
                storage_state=account_file,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.4324.150 Safari/537.36"
                ),
            )
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()
                await page.goto(
                    "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                    timeout=60000,
                )
                logger.info("[上传视频] 开始上传视频: %s", title)

                await page.wait_for_url(
                    "https://baijiahao.baidu.com/builder/rc/edit?type=videoV2",
                    timeout=60000,
                )
                logger.info("[上传视频] 发布页面已打开")

                # 注册上传完成请求监听器（必须在 set_input_files 之前注册，
                # 否则可能错过在表单填充期间触发的完成请求）
                upload_done = asyncio.Event()

                def _on_bjh_request(request):
                    if (
                        "materialui/video/compuploadvideo" in request.url
                        and not upload_done.is_set()
                    ):
                        upload_done.set()

                page.on("request", _on_bjh_request)

                # Upload video file
                logger.info("[上传视频] 正在上传视频文件...")
                video_input = page.locator(
                    "input[type='file'][accept*='.mp4']"
                )
                if await video_input.count() == 0:
                    video_input = page.locator("input[type='file']").first
                await video_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择，等待上传完成...")

                # Wait for the form page to appear
                while True:
                    try:
                        await page.wait_for_selector(
                            "div#formMain:visible"
                        )
                        break
                    except Exception:
                        logger.info("[上传视频] 正在等待进入视频发布页面...")
                        await asyncio.sleep(0.1)

                # Fill title and tags
                await asyncio.sleep(1)
                logger.info("[填写标题] 开始填写标题与话题...")
                await self._add_title_tags(page, title, desc, tags)
                logger.info("[填写标题] 标题: %s", title)
                logger.info("[填写标题] 标题与话题填写完成")

                # Wait for video upload to complete (network signal)
                upload_status = await self._wait_for_upload(
                    page, upload_done
                )
                if not upload_status:
                    logger.error("[上传视频] 发现上传出错了... 文件:%s", file_path)
                    raise Exception("Video upload failed")
                logger.info("[上传视频] 视频上传成功!")

                # Wait for cover area to be ready
                while True:
                    container_count = await page.locator(
                        "div[class*='coverWrap'] > "
                        "div[class*='cover-container']"
                    ).count()
                    if container_count >= 2:
                        logger.info(
                            "[设置封面] 封面区域已就绪（找到 %d 个 cover-container）",
                            container_count,
                        )
                        break
                    else:
                        logger.info(
                            "[设置封面] 等待封面区域就绪（当前 %d 个 cover-container）...",
                            container_count,
                        )
                        await asyncio.sleep(3)

                # Set custom covers
                logger.info("[设置封面] 开始设置视频封面...")
                await self._set_cover(
                    page,
                    thumbnail_landscape_path,
                    thumbnail_portrait_path,
                )
                logger.info("[设置封面] 封面设置完成")

                # Set creation declaration
                logger.info("[设置声明] 开始设置创作声明: %s", creation_declaration or "无")
                await self._set_creation_declaration(
                    page,
                    creation_declaration,
                    supplementary_declaration,
                )
                logger.info("[设置声明] 创作声明设置完成")

                # Publish (immediate or scheduled)
                logger.info("[发布] 正在点击发布按钮...")
                await self._publish_video(page, publish_date)
                await page.wait_for_timeout(2000)

                # Handle captcha if present
                captcha_dialog = page.locator(
                    "div.passMod_dialog-container:visible"
                )
                if await captcha_dialog.count():
                    logger.warning(
                        "[发布] 出现人机校验，请在浏览器中手动完成验证..."
                    )
                    try:
                        await captcha_dialog.wait_for(
                            state="hidden", timeout=120000
                        )
                        logger.info("[发布] 人机校验已完成")
                        await asyncio.sleep(3)
                    except Exception:
                        logger.error("[发布] 人机校验等待超时（120秒），退出")
                        raise Exception("人机校验等待超时")

                # Wait for publish success redirect
                try:
                    await page.wait_for_url(
                        "https://baijiahao.baidu.com/builder/rc/clue**",
                        timeout=30000,
                    )
                    logger.info("[发布] 视频发布成功! 页面跳转到: %s", page.url)
                except Exception:
                    current_url = page.url
                    logger.error(
                        "[发布] 发布后未跳转到成功页面, 当前URL: %s",
                        current_url,
                    )
                    raise Exception(
                        f"视频发布后未成功跳转, 当前URL: {current_url}"
                    )

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: 前置校验 - 描述+标签总字符 ≤50(emoji 按 3 算),最多 10 标签
    # ------------------------------------------------------------------

    @staticmethod
    def _count_chars(s: str) -> int:
        """按百家号规则计算字符数:中文/字母=1,emoji=3。"""
        n = 0
        for ch in s:
            # emoji 通常以 surrogate pair 或 grapheme cluster 出现,这里简化按 codepoint 判断
            if ord(ch) > 0xFFFF:
                n += 3
            else:
                n += 1
        return n

    @staticmethod
    def _validate_publish_params(desc: str, tags: list) -> tuple[bool, str]:
        """校验描述+标签,返回 (ok, msg)。

        规则:
        - 标签数 ≤ 10
        - 描述 + ' ' + ' '.join(f'#{t}' for t in tags) 总字符数 ≤ 50(emoji=3)
        """
        if tags and len(tags) > 10:
            return False, f"百家号最多 10 个标签,当前 {len(tags)} 个"

        # 模拟前端拼装(与 _add_title_tags 行为一致)
        parts = [desc or ""]
        if tags:
            parts.append(" ".join(f"#{t}" for t in tags))
        full = " ".join(p for p in parts if p).strip()
        char_count = BaijiahaoPlatform._count_chars(full)
        if char_count > 50:
            return False, (
                f"百家号描述+标签总字符数 {char_count} 超过 50(emoji 按 3 算),请精简"
            )
        return True, ""

    # ------------------------------------------------------------------
    # Helper: wait for video upload to complete
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_upload(
        page, upload_done: asyncio.Event,
    ) -> bool:
        """Wait for the authoritative upload-complete HTTP request.

        The caller must have registered a ``page.on("request")`` listener
        that sets ``upload_done`` when ``/materialui/video/compuploadvideo``
        is observed (registered BEFORE ``set_input_files`` so the request
        is not missed during form filling).

        DOM-based polling is unreliable — the cover overlay can flip
        states before the server has actually finished ingesting the
        file, leading to a publish click while the video is still
        uploading. The completion HTTP request is the source of truth.

        无超时:视频可能很大(≤16G),一直等到上传完成请求到达。

        Returns True on success, False on failure.
        """
        await upload_done.wait()
        logger.info("[上传视频] 视频上传完毕（检测到 compuploadvideo 请求）")
        return True

    # ------------------------------------------------------------------
    # Helper: fill title and tags (Baijiahao uses description field)
    # ------------------------------------------------------------------

    @staticmethod
    async def _add_title_tags(page, title, desc, tags):
        """Fill the description field (Lexical editor) with title and tags.

        Baijiahao publish page has a "作品描述" field (Lexical editor) rather
        than a separate title input. Tags are typed as #话题 via keyboard
        to trigger the topic search dropdown, then the first suggestion is
        selected.
        """
        desc_text = (desc or title or "").strip()[:2000]

        # Lexical contenteditable editor
        lexical_editor = page.locator('[data-lexical-editor="true"]')
        editor = None
        if await lexical_editor.count():
            editor = lexical_editor.first
        else:
            # Fallback: placeholder
            title_container = page.get_by_placeholder("添加标题获得更多推荐")
            if await title_container.count():
                full_text = desc_text
                if tags:
                    full_text += " " + " ".join(f"#{t}" for t in tags)
                await title_container.fill(full_text[:2000])
                logger.info("[填写简介] 已通过 placeholder 填充描述: %s", full_text[:2000])
                return
            logger.warning("[填写标题] 未找到描述输入框，跳过填充")
            return

        # 1. 输入描述文本
        await editor.click()
        await asyncio.sleep(0.3)
        await page.keyboard.press("Control+a")
        await asyncio.sleep(0.1)
        if desc_text:
            await page.keyboard.type(desc_text, delay=50)
            logger.info("[填写标题] 已填充作品描述: %s", desc_text)

        # 2. 逐个输入 #话题 并从下拉列表选择第一个
        for tag in (tags or []):
            await page.keyboard.type(f" #{tag}", delay=50)
            await asyncio.sleep(1)

            # 等待话题搜索下拉出现
            topic_list = page.locator("div[class*='topicListInner']")
            try:
                await topic_list.wait_for(state="visible", timeout=3000)
                first_item = topic_list.locator("div[class*='topicItem']").first
                await first_item.click()
                logger.info("[填写标题] 已选择话题: #%s", tag)
                await asyncio.sleep(0.5)
            except Exception:
                logger.info("[填写标题] 话题 #%s 未出现下拉建议，跳过选择", tag)

    # ------------------------------------------------------------------
    # Helper: publish (immediate or scheduled)
    # ------------------------------------------------------------------

    async def _publish_video(self, page, publish_date):
        """Click the publish button, with optional scheduling."""
        if publish_date != 0:
            await self._set_schedule_publish(page, publish_date)
        else:
            await self._direct_publish(page)

    @staticmethod
    async def _direct_publish(page):
        """Click the publish button immediately."""
        try:
            publish_button = page.locator(
                "button[data-testid='publish-btn']"
            )
            if await publish_button.count():
                await publish_button.click()
            else:
                publish_button = page.locator(
                    "button.cheetah-btn-primary:has-text('发布')"
                )
                if await publish_button.count():
                    await publish_button.first.click()
        except Exception as e:
            logger.error("[发布] 直接发布视频失败: %s", e)
            raise

    # ------------------------------------------------------------------
    # Helper: schedule publish
    # ------------------------------------------------------------------

    async def _set_schedule_publish(self, page, publish_date):
        """Open the schedule dialog and set the time.

        Baijiahao only allows scheduled publish within the next 1 hour to 7 days.
        If the target time is today, the selected hour must be strictly greater
        than the current hour.
        """
        now = datetime.now()
        delta_days = (publish_date.date() - now.date()).days

        if delta_days < 0:
            raise ValueError(
                f"定时发布失败: 发布时间 {publish_date} 已早于当前时间"
            )
        if delta_days > 7:
            raise ValueError(
                f"定时发布失败: 发布时间 {publish_date} 超出百家号 7 天限制"
            )
        if delta_days == 0 and publish_date.hour <= now.hour:
            raise ValueError(
                f"定时发布失败: 今天发布时小时({publish_date.hour})必须大于当前小时({now.hour})"
            )

        date_label = f"{publish_date.month}月{publish_date.day}日"
        hour_label = f"{publish_date.hour}点"
        minute_label = f"{publish_date.minute}分"

        schedule_button = page.get_by_role(
            "button", name="定时发布", exact=True
        )
        await schedule_button.click()
        await page.wait_for_selector("#select-date", timeout=5000)
        await page.wait_for_timeout(500)

        await self._pick_schedule_option(page, "#select-date", date_label)
        await self._pick_schedule_option(page, "#select-hour", hour_label)
        await self._pick_schedule_option(page, "#select-minute", minute_label)

        await page.wait_for_timeout(500)
        # Confirm button is INSIDE the schedule dialog (not the page-level one)
        await page.locator("div[role='dialog']").get_by_role(
            "button", name="定时发布"
        ).click()
        logger.info(
            "百家号定时发布设置完成: %s %s:%s",
            date_label, publish_date.hour, publish_date.minute,
        )

    @staticmethod
    async def _pick_schedule_option(page, input_id: str, label: str) -> None:
        """Open one of the schedule selects and pick the target option.

        Force-clicks the hidden combobox input to open the dropdown, then
        navigates from the currently-highlighted option (``aria-activedescendant``)
        to the target using ArrowUp / ArrowDown keys, and confirms with Enter.
        ``rc-virtual-list`` auto-scrolls to keep the active option in view,
        so keyboard navigation drives the visible scroll.

        ``input_id`` must include the leading ``#``.
        """
        await page.locator(input_id).click(force=True)
        try:
            await page.wait_for_selector(
                f"{input_id}[aria-expanded='true']", timeout=3000
            )
        except Exception:
            await page.wait_for_timeout(500)
        await page.wait_for_timeout(500)

        # Read current highlighted index (format: select-{kind}_list_{n})
        current_id = await page.evaluate(
            """(selector) => {
                const input = document.querySelector(selector);
                return input ? input.getAttribute('aria-activedescendant') : null;
            }""",
            input_id,
        )
        current_num = 0
        if current_id:
            parts = current_id.rsplit("_", 1)
            if len(parts) == 2 and parts[1].isdigit():
                current_num = int(parts[1])

        # Compute target list index from label
        if "分" in label:
            target_num = int(label.replace("分", ""))
        elif "点" in label:
            target_num = int(label.replace("点", ""))
        elif "日" in label:
            day = int(label.split("月")[1].replace("日", ""))
            target_num = day - datetime.now().day
            if target_num < 0 or target_num > 7:
                target_num = 0
        else:
            target_num = 0

        # Re-focus the combobox so key events are routed to its keydown handler
        await page.locator(input_id).focus()
        await page.wait_for_timeout(200)

        diff = target_num - current_num
        if diff != 0:
            key = "ArrowDown" if diff > 0 else "ArrowUp"
            for _ in range(abs(diff)):
                await page.keyboard.press(key)
                await page.wait_for_timeout(40)

        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)

    # ------------------------------------------------------------------
    # Helper: set custom cover images (landscape + portrait)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_cover(
        page,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
    ):
        """Upload custom cover images (landscape + portrait).

        Locates cover-container elements inside coverWrap, clicks each one
        to open a modal, uploads the image, and clicks confirm.
        """
        containers = page.locator(
            "div[class*='coverWrap'] > "
            "div[class*='cover-container']"
        )
        total = await containers.count()
        logger.info("[封面] 找到 %d 个 cover-container，开始逐个设置", total)

        for idx, (cover_type, cover_path) in enumerate(
            [
                ("横屏封面", thumbnail_landscape_path),
                ("竖屏封面", thumbnail_portrait_path),
            ]
        ):
            logger.info(
                "[封面] === 处理第 %d 个: %s ===", idx + 1, cover_type
            )

            if not cover_path or not os.path.exists(cover_path):
                logger.info("[封面] %s 无图片文件，跳过", cover_type)
                continue
            if idx >= total:
                logger.warning(
                    "[封面] cover-container 不足（%d），跳过%s",
                    total,
                    cover_type,
                )
                continue

            logger.info(
                "[封面] %s 图片: %s", cover_type, os.path.basename(cover_path)
            )
            try:
                container = containers.nth(idx)

                # 1. Click cover area to open modal
                logger.info(
                    "[封面] 点击第 %d 个 cover-container ...", idx + 1
                )
                await container.click()
                logger.info(
                    "[封面] 已点击%s，等待弹窗打开...", cover_type
                )

                # Wait for modal to appear
                await page.wait_for_selector(
                    "div.cheetah-modal:visible", timeout=10000
                )
                logger.info("[封面] %s弹窗已出现", cover_type)
                await asyncio.sleep(1)

                # 2. Upload image via file input inside the modal
                file_input_count = await page.locator(
                    "div.cheetah-modal:visible input[type='file']"
                ).count()
                logger.info(
                    "[封面] 弹窗中找到 %d 个 file input", file_input_count
                )

                dialog_input = page.locator(
                    "div.cheetah-modal:visible input[type='file']"
                ).first
                await dialog_input.set_input_files(cover_path)
                logger.info("[封面] 已上传%s文件", cover_type)
                await asyncio.sleep(2)

                # 3. Click confirm button in the modal
                confirm_btn = page.locator(
                    "div.cheetah-modal:visible "
                    "button.cheetah-btn-primary:has-text('确定')"
                )
                confirm_count = await confirm_btn.count()
                logger.info(
                    "[封面] 弹窗中找到 %d 个确定按钮", confirm_count
                )

                if confirm_count:
                    await confirm_btn.first.click()
                    logger.info("[封面] 已点击确定提交%s", cover_type)
                else:
                    logger.warning(
                        "[封面] %s弹窗未找到确定按钮", cover_type
                    )

                await asyncio.sleep(2)
                logger.info("[封面] %s设置完成", cover_type)

            except Exception as e:
                logger.error("[封面] 设置%s失败: %s", cover_type, e)

    # ------------------------------------------------------------------
    # Helper: set creation declaration
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_creation_declaration(
        page, creation_declaration="", supplementary_declaration=""
    ):
        """Set the creation declaration (required + supplementary).

        Opens the declaration dialog, selects matching radio options, and
        confirms.
        """
        if not creation_declaration and not supplementary_declaration:
            return

        logger.info(
            "设置创作声明 - 必选: %s, 补充: %s",
            creation_declaration,
            supplementary_declaration,
        )
        try:
            declaration_input = page.locator(
                "input[placeholder='请选择创作声明']"
            )
            if not await declaration_input.count():
                logger.info("[设置声明] 未找到创作声明输入框，跳过")
                return

            await declaration_input.click()
            logger.info("[设置声明] 已点击创作声明输入框")
            await asyncio.sleep(1)

            # Locate dialog
            modal = page.get_by_role("dialog", name="创作声明")
            await modal.wait_for(state="visible", timeout=5000)
            logger.info("[设置声明] 创作声明弹窗已出现")

            # Select required declaration
            if creation_declaration:
                target_text = creation_declaration.strip()
                count = await modal.locator(
                    "div.flex.items-center.cursor-pointer"
                ).count()
                clicked = False
                for i in range(count):
                    row = modal.locator(
                        "div.flex.items-center.cursor-pointer"
                    ).nth(i)
                    row_text = (await row.inner_text() or "").strip()
                    if row_text == target_text:
                        await row.locator(
                            "input.cheetah-radio-input"
                        ).click(force=True)
                        logger.info("[设置声明] 已选择必选声明: %s", row_text)
                        clicked = True
                        break
                if not clicked:
                    logger.warning(
                        "未找到匹配的必选声明: %s", target_text
                    )
                await asyncio.sleep(0.5)

            # Select supplementary declaration
            if supplementary_declaration:
                target_text = supplementary_declaration.strip()
                count = await modal.locator(
                    "div.flex.items-center.cursor-pointer"
                ).count()
                clicked = False
                for i in range(count):
                    row = modal.locator(
                        "div.flex.items-center.cursor-pointer"
                    ).nth(i)
                    row_text = (await row.inner_text() or "").strip()
                    if row_text == target_text:
                        await row.locator(
                            "input.cheetah-radio-input"
                        ).click(force=True)
                        logger.info("[设置声明] 已选择补充声明: %s", row_text)
                        clicked = True
                        break
                if not clicked:
                    logger.warning(
                        "未找到匹配的补充声明: %s", target_text
                    )
                await asyncio.sleep(0.5)

            # Click confirm
            confirm_btn = modal.locator(
                "button.cheetah-btn-primary:has-text('确定')"
            )
            if await confirm_btn.count():
                await confirm_btn.click()
                logger.info("[设置声明] 已点击创作声明确定按钮")
            else:
                logger.warning("[设置声明] 未找到创作声明确定按钮")

            await asyncio.sleep(1)
            logger.info("[设置声明] 创作声明设置完成")

        except Exception as e:
            logger.warning("[设置声明] 设置创作声明失败（不影响上传）: %s", e)
