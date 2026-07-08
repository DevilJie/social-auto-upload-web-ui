"""
Douyin platform implementation — 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import re
import threading
import time
from pathlib import Path
from queue import Queue

from util._logger import bind_account_name, get_channel_logger

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

logger = get_channel_logger("douyin")

DOUYIN_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
DOUYIN_PUBLISH_STRATEGY_SCHEDULED = "scheduled"

# 调试开关:True = 走到发布按钮时只输出参数日志、不实际点击发布(便于检查内容);
# False = 正常点击发布。验证完发布内容无误后改回 False 即可。
_PUBLISH_DRY_RUN = False


class DouyinPlatform(BasePlatform):
    platform_id = 3
    platform_key = "douyin"
    platform_name = "抖音"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 抖音 cookie 全部由 .douyin.com 域下发，覆盖 creator.douyin.com 子域
    platform_cookie_domain = ".douyin.com"

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.douyin.com)
        - expires 给 7 天保守占位，sync_profile 跑完后 storage_state 会被
          回写为真实的 cookie（含真实 expires + localStorage）
        - localStorage 留空，由 sync_profile 自然补全
        """
        cookies: list[dict] = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": self.platform_cookie_domain,
                "path": "/",
                "expires": expires,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            })
        logger.info(
            f"[douyin] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Douyin login via QR code scan.

        Opens ``https://creator.douyin.com/``, extracts the QR image from
        ``get_by_role("img", name="二维码")``, sends the image URL to
        *status_queue*, then waits for the page to navigate away (indicating
        the user scanned the code).  On success, scrapes the user profile and
        saves the login result.
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
                await page.goto("https://creator.douyin.com/")
                original_url = page.url

                # Extract QR code image
                img_locator = page.get_by_role("img", name="二维码")
                src = await img_locator.get_attribute("src")
                logger.info("QR image src: %s", src)
                status_queue.put(src)

                # Monitor URL change via framenavigated
                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                # 不设超时——扫码登录可能耗时几分钟，浏览器由用户自己关
                await url_changed_event.wait()
                logger.info("Page navigation detected — login successful")

                # Scrape profile & save via shared utility
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
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        Opens ``https://creator.douyin.com/creator-micro/content/upload`` with
        the stored cookies.  If the page shows "扫码登录" within 5 seconds the
        cookie is considered invalid.
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                try:
                    await page.wait_for_url(
                        "https://creator.douyin.com/creator-micro/content/upload",
                        timeout=5000,
                    )
                except Exception:
                    logger.info("cookie check: page did not reach target URL")
                    return False

                # If "扫码登录" is visible the cookie has expired
                try:
                    await page.get_by_text("扫码登录").wait_for(timeout=5000)
                    logger.info("cookie check: 扫码登录 visible — cookie invalid")
                    return False
                except Exception:
                    logger.info("cookie check: no login prompt — cookie valid")
                    return True
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Douyin creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                try:
                    await page.goto(
                        "https://creator.douyin.com/",
                        wait_until="networkidle",
                        timeout=30000,
                    )
                except Exception:
                    # networkidle can timeout; page content may still be usable
                    pass
                name, avatar = await scrape_user_profile(page)
                return name, avatar
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window (sync CloakBrowser)
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Douyin creator centre in a visible browser window.

        打开后立即返回，不做任何等待或关闭 —— 浏览器由用户自己关。
        线程仅负责启动浏览器，启动完就结束（browser 对象保留在闭包里，
        CloakBrowser 子进程会随主进程存活）。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://creator.douyin.com/"

        def _launch():
            browser = create_browser_sync(headless=False)
            context = create_context_sync(browser, storage_state=cookie_path)
            page = context.new_page()
            page.goto(url)

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # publish_video — full Douyin upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Douyin via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- video title
        - ``files`` (*list[str]*) -- video absolute file paths (resolved by app.py)
        - ``tags`` (*list[str]*) -- hashtags
        - ``activities`` (*list[str]*, optional) -- official activities (appended as #tags to description)
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``category`` (*int*, optional)
        - ``enableTimer`` (*bool*, optional)
        - ``videos_per_day`` (*int*, optional)
        - ``daily_times`` (*list*, optional)
        - ``start_days`` (*int*, optional)
        - ``thumbnail_landscape_path`` (*str*, optional)
        - ``thumbnail_portrait_path`` (*str*, optional)
        - ``productLink`` (*str*, optional)
        - ``productTitle`` (*str*, optional)
        - ``desc`` (*str*, optional) -- 描述里的 ``#xxx`` 会计入话题总数,
          与 ``tags``、官方活动 ``activities`` 合并上限 5 个,超过将被前置校验拦截。
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional)
        """
        logger.info("=" * 60)
        logger.info("[发布视频] 开始抖音视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        activities = kwargs.get("activities", []) or []

        # ===== 前置校验:话题总数 ≤ 5(描述里的 #xxx + 标签 + 官方活动) =====
        desc = kwargs.get("desc", "") or ""
        ok, err = self._validate_publish_params(desc, tags, activities)
        if not ok:
            logger.error("[发布视频] 抖音前置校验失败: %s", err)
            raise ValueError(err)

        account_file = kwargs.get("account_file", [])
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        product_link = kwargs.get("productLink", "")
        product_title = kwargs.get("productTitle", "")
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content", "")
        hotspot = kwargs.get("hotspot", "")
        tag_type = kwargs.get("tag_type", "")
        tag_value = kwargs.get("tag_value", "")
        mini_link = kwargs.get("mini_link", "")
        mix_id = kwargs.get("mix_id", "")

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 商品链接: %s (标题: %s)", product_link or "无", product_title or "无")
        logger.info("[发布参数] 合集ID: %s", mix_id or "无")
        logger.info("[发布参数] 热点词: %s", hotspot or "无")
        logger.info("[发布参数] AI内容声明: %s", ai_content or "无")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        # files 已是绝对路径（app.py 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            # thumbnail_landscape_path 已是绝对路径
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            # thumbnail_portrait_path 已是绝对路径
            thumbnail_portrait_path = str(thumbnail_portrait_path)

        # Determine publish strategy and schedule times
        publish_strategy = (
            DOUYIN_PUBLISH_STRATEGY_SCHEDULED
            if enableTimer and schedule_time_str
            else DOUYIN_PUBLISH_STRATEGY_IMMEDIATE
        )
        logger.info("[发布策略] 发布策略: %s", publish_strategy)
        if schedule_time_str:
            logger.info("[发布策略] 定时发布时间: %s", schedule_time_str)

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
                        publish_strategy=publish_strategy,
                        activities=activities,
                        thumbnail_landscape_path=thumbnail_landscape_path or None,
                        thumbnail_portrait_path=thumbnail_portrait_path or None,
                        product_link=product_link,
                        product_title=product_title,
                        desc=desc,
                        ai_content=ai_content,
                        hotspot=hotspot,
                        tag_type=tag_type,
                        tag_value=tag_value,
                        mini_link=mini_link,
                        mix_id=mix_id,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # Internal helpers (ported from DouYinVideo / DouYinBaseUploader)
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: str,
        activities: list | None = None,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        product_link="",
        product_title="",
        desc="",
        ai_content="",
        hotspot="",
        tag_type="",
        tag_value="",
        mini_link="",
        mix_id="",
    ):
        """Upload a single video to one Douyin account."""
        logger.info("[上传视频] 开始上传视频: %s", file_path)
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=account_file
            )
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()
                logger.info("[上传视频] 正在打开发布页面...")
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/upload"
                )
                logger.info("[上传视频] 发布页面已打开")

                # Upload video file
                logger.info("[上传视频] 正在上传视频文件...")
                await page.locator(
                    "div[class^='container'] input"
                ).set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择，等待上传完成...")

                # Wait for redirect to publish page (version 1 or version 2)
                while True:
                    try:
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/publish?enter_from=publish_page",
                            timeout=3000,
                        )
                        break
                    except Exception:
                        try:
                            await page.wait_for_url(
                                "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
                                timeout=3000,
                            )
                            break
                        except Exception:
                            await asyncio.sleep(0.5)

                await asyncio.sleep(1)

                # Append activities as hashtags to description (与图文发布一致)
                if activities:
                    activity_tags = " ".join([f"#{act}" for act in activities])
                    desc = f"{desc or title} {activity_tags}".strip()

                # Fill title, description, tags
                logger.info("[填写标题] 开始填写标题与简介...")
                await self._fill_title_and_description(
                    page, title, desc or title, tags
                )
                logger.info("[填写标题] 标题与简介填写完成")
                logger.info("[填写标题] 标题: %s", title)

                # Wait for upload to complete
                while True:
                    try:
                        number = await page.locator(
                            '[class^="long-card"] div:has-text("重新上传")'
                        ).count()
                        if number > 0:
                            break
                        await asyncio.sleep(2)
                        if await page.locator(
                            'div.progress-div > div:has-text("上传失败")'
                        ).count():
                            logger.warning("[上传视频] 上传失败，正在重试")
                            await page.locator(
                                "div.progress-div [class^='upload-btn-input']"
                            ).set_input_files(file_path)
                    except Exception:
                        await asyncio.sleep(2)
                logger.info("[上传视频] 视频上传成功!")

                # Set product link
                if product_link and product_title:
                    logger.info("[商品链接] 开始设置商品链接: %s", product_link)
                    await self._set_product_link(page, product_link, product_title)

                # Set thumbnail / cover
                logger.info("[设置封面] 开始设置视频封面...")
                await self._set_thumbnail(
                    page, thumbnail_landscape_path, thumbnail_portrait_path
                )
                logger.info("[设置封面] 封面设置完成")

                # Toggle third-party content switch
                third_part_element = (
                    '[class^="info"] > [class^="first-part"] div div.semi-switch'
                )
                if await page.locator(third_part_element).count():
                    if "semi-switch-checked" not in await page.eval_on_selector(
                        third_part_element, "div => div.className"
                    ):
                        await page.locator(
                            third_part_element
                        ).locator("input.semi-switch-native-control").click()

                
                # Set mix/collection if provided (与图文发布一致)
                if mix_id:
                    logger.info("[设置合集] 开始设置合集: %s", mix_id)
                    await self._set_image_mix(page, mix_id)

                # Set AI content declaration
                if ai_content:
                    logger.info("[内容声明] 开始设置AI内容声明: %s", ai_content)
                    await self._set_declaration(page, ai_content)


                # Set tag (位置/小程序/游戏手柄/标记万物) if provided (与图文发布一致)
                if tag_type and tag_value:
                    logger.info("[设置标签] 开始设置标签: 类型=%s, 值=%s, 小程序链接=%s", tag_type, tag_value, mini_link)
                    await self._set_tag(page, tag_type, tag_value, mini_link)


                # Set hotspot if provided (与图文发布一致)
                if hotspot:
                    logger.info("[设置热点] 开始设置热点词: %s", hotspot)
                    await self._set_hotspot(page, hotspot)

                # Schedule if needed
                if (
                    publish_strategy == DOUYIN_PUBLISH_STRATEGY_SCHEDULED
                    and publish_date != 0
                ):
                    logger.info("[定时发布] 开始设置定时发布...")
                    await self._set_schedule_time(page, publish_date)
                    logger.info("[定时发布] 定时发布设置完成")

                # 调试:输出本次发布的全部参数(便于人工核对填写是否正确)
                logger.info("=" * 60)
                logger.info("[发布调试] ===== 本次发布参数汇总 (dry_run=%s) =====", _PUBLISH_DRY_RUN)
                logger.info("[发布调试] 标题(title)       : %s", title)
                logger.info("[发布调试] 视频文件(file_path): %s", file_path)
                logger.info("[发布调试] 描述(desc)        : %s", desc[:100] if desc else "(无)")
                logger.info("[发布调试] 标签(tags)        : %s (共 %d 个)", tags, len(tags))
                logger.info("[发布调试] 横版封面(landscape): %s", thumbnail_landscape_path or "(无)")
                logger.info("[发布调试] 竖版封面(portrait) : %s", thumbnail_portrait_path or "(无)")
                logger.info("[发布调试] 发布策略(strategy): %s", publish_strategy)
                logger.info("[发布调试] 定时时间(publish_date): %s", publish_date)
                logger.info("[发布调试] 官方活动(activities): %s", activities or "(无)")
                logger.info("[发布调试] 热点(hotspot)     : %s", hotspot or "(无)")
                logger.info("[发布调试] 标签类型(tag_type): %s", tag_type or "(无)")
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

                # Click publish and wait for redirect
                logger.info("[发布] 正在点击发布按钮...")
                while True:
                    try:
                        publish_button = page.get_by_role(
                            "button", name="发布", exact=True
                        )
                        if await publish_button.count():
                            await publish_button.click()
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/manage**",
                            timeout=3000,
                        )
                        logger.info("[发布] 视频发布成功! 页面跳转到: %s", page.url)
                        break
                    except Exception:
                        # Maybe a cover selection is required
                        await self._handle_auto_video_cover(page)
                        await asyncio.sleep(0.5)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: 前置校验 - 话题总数 ≤ 5(描述 #xxx + 标签 + 官方活动)
    # ------------------------------------------------------------------

    # 描述里话题正则:# 在行首或空白后,后跟非空白非 # 字符(独立话题)。
    # 不匹配 "a#b" / "http://x#anchor" / "##" / 孤立 "#"
    _HASHTAG_PATTERN = re.compile(r"(?:^|\s)#[^\s#]+", re.MULTILINE)

    @classmethod
    def _count_hashtags(cls, text: str) -> int:
        """统计描述文本里独立的 #xxx 话题数量。

        - 行首或空白后的 ``#`` 才算话题开头(避免 ``a#b``、``http://x#anchor`` 误判)。
        - ``##``、孤立 ``#`` 不计数。
        """
        if not text:
            return 0
        return len(cls._HASHTAG_PATTERN.findall(text))

    @staticmethod
    def _validate_publish_params(desc: str, tags: list, activities: list) -> tuple[bool, str]:
        """校验话题总数,返回 (ok, msg)。

        规则:描述里的 ``#xxx`` + 标签数 + 官方活动数 ≤ 5
        (抖音一条视频最多 5 个话题,超出发布页会拒绝)。
        """
        desc = desc or ""
        tags = tags or []
        activities = activities or []
        total = (
            DouyinPlatform._count_hashtags(desc)
            + len(tags)
            + len(activities)
        )
        if total > 5:
            return False, (
                f"抖音话题总数 {total} 超过 5 个"
                f"(描述 #xxx {DouyinPlatform._count_hashtags(desc)} + 标签 {len(tags)}"
                f" + 官方活动 {len(activities)}),请删减"
            )
        return True, ""

    # ------------------------------------------------------------------
    # Helper: fill title, description, tags
    # ------------------------------------------------------------------

    @staticmethod
    async def _fill_title_and_description(
        page, title: str, description: str, tags: list | None = None
    ):
        description_section = (
            page.get_by_text("作品描述", exact=True)
            .locator("xpath=ancestor::div[2]")
            .locator("xpath=following-sibling::div[1]")
        )

        title_input = description_section.locator('input[type="text"]').first
        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.fill(title[:30])

        description_editor = description_section.locator(
            '.zone-container[contenteditable="true"]'
        ).first
        await description_editor.wait_for(state="visible", timeout=10000)
        await description_editor.click()
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        # 只输入一次,不要重复输入
        clean_description = (description or "").rstrip()
        await clear_and_type(page, clean_description)

        await page.keyboard.press("Space")
        # 修：标签循环用单空格分隔，首 tag 前明确加一个空格
        for tag in tags or []:
            if not tag:
                continue
            # 用 insert_text 不会触发 IME 干扰
            await page.keyboard.insert_text(" " + "#" + tag)
            # Space 让抖音把 " #tag" 识别为 hashtag chip
            await page.keyboard.press("Space")
            # 修：移动光标到内容末尾，避免下次插入位置错乱
            await page.keyboard.press("End")

    # ------------------------------------------------------------------
    # Helper: set schedule time
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        await label_element.click()
        await asyncio.sleep(1)

        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")
        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await clear_and_type(page, str(publish_date_hour))
        await page.keyboard.press("Enter")
        await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Helper: set product link (购物车)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_product_link(page, product_link: str, product_title: str):
        await page.wait_for_timeout(2000)
        try:
            await page.wait_for_selector("text=添加标签", timeout=10000)
            dropdown = (
                page.get_by_text("添加标签")
                .locator("..")
                .locator("..")
                .locator("..")
                .locator(".semi-select")
                .first
            )
            if not await dropdown.count():
                logger.warning("[商品链接] 未找到标签下拉框")
                return False

            await dropdown.click()
            await page.wait_for_selector('[role="listbox"]', timeout=5000)
            await page.locator('[role="option"]:has-text("购物车")').click()

            await page.wait_for_selector(
                'input[placeholder="粘贴商品链接"]', timeout=5000
            )
            input_field = page.locator('input[placeholder="粘贴商品链接"]')
            await input_field.fill(product_link)

            add_button = page.locator('span:has-text("添加链接")')
            button_class = await add_button.get_attribute("class")
            if "disable" in button_class:
                logger.warning("[商品链接] 添加链接按钮不可用")
                return False
            await add_button.click()

            await page.wait_for_timeout(2000)
            error_modal = page.locator("text=未搜索到对应商品")
            if await error_modal.count():
                confirm_button = page.locator('button:has-text("确定")')
                await confirm_button.click()
                logger.warning("[商品链接] 商品链接无效")
                return False

            # Fill product short title
            await page.wait_for_timeout(2000)
            await page.wait_for_selector(
                'input[placeholder="请输入商品短标题"]', timeout=10000
            )
            short_title_input = page.locator(
                'input[placeholder="请输入商品短标题"]'
            )
            if not await short_title_input.count():
                logger.warning("[商品链接] 未找到商品短标题输入框")
                return False

            await short_title_input.fill(product_title[:10])
            await page.wait_for_timeout(1000)

            finish_button = page.locator('button:has-text("完成编辑")')
            if "disabled" not in await finish_button.get_attribute("class"):
                await finish_button.click()
                await page.wait_for_selector(
                    ".semi-modal-content", state="hidden", timeout=5000
                )
                return True

            # Button is disabled — close dialog
            cancel_button = page.locator('button:has-text("取消")')
            if await cancel_button.count():
                await cancel_button.click()
            else:
                close_button = page.locator(".semi-modal-close")
                await close_button.click()
            await page.wait_for_selector(
                ".semi-modal-content", state="hidden", timeout=5000
            )
            return False
        except Exception as e:
            logger.warning("[商品链接] 设置失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # Helper: set thumbnail (cover images)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_thumbnail(
        page, thumbnail_landscape_path=None, thumbnail_portrait_path=None
    ):
        if not thumbnail_landscape_path and not thumbnail_portrait_path:
            return

        logger.info("[封面] 开始设置视频封面")
        await page.click('text="选择封面"')
        cover_locator_str = 'div[id*="creator-content-modal"]'
        cover_locator = page.locator(cover_locator_str)
        await page.wait_for_selector(cover_locator_str)
        logger.info("[封面] 封面编辑器已打开")

        # 读取 tab 文本识别横版/竖版各自在第几个 tab
        tab_locator = cover_locator.locator("div[class*='steps'] div")
        tab_count = await tab_locator.count()
        portrait_tab_idx = None
        landscape_tab_idx = None
        for i in range(tab_count):
            try:
                text = await tab_locator.nth(i).inner_text()
                if "竖" in text:
                    portrait_tab_idx = i
                if "横" in text:
                    landscape_tab_idx = i
            except Exception:
                continue
        logger.info("[封面] 封面tab索引 - 竖版: %s, 横版: %s", portrait_tab_idx, landscape_tab_idx)

        # 通用函数：切换到指定 tab → 取当前可见的 upload input → 上传
        async def _upload_to_tab(tab_index, file_path):
            await cover_locator.locator("div[class*='steps'] div").nth(tab_index).click()
            await page.wait_for_timeout(1500)
            # 每次切 tab 后重新定位，当前 tab 只有一个可见的 upload input
            inp = cover_locator.locator(
                "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"
            ).first
            await inp.set_input_files(file_path)
            await page.wait_for_timeout(2000)

        if thumbnail_portrait_path and portrait_tab_idx is not None:
            await _upload_to_tab(portrait_tab_idx, thumbnail_portrait_path)
            logger.info("[封面] 竖版封面上传成功 (tab %s)", portrait_tab_idx)
        elif thumbnail_portrait_path:
            # 没找到竖版 tab，尝试默认第一个
            await page.wait_for_timeout(1000)
            await cover_locator.locator(
                "div[class^='semi-upload upload'] >> input.semi-upload-hidden-input"
            ).first.set_input_files(thumbnail_portrait_path)
            await page.wait_for_timeout(2000)
            logger.info("[封面] 竖版封面上传成功 (默认)")

        if thumbnail_landscape_path and landscape_tab_idx is not None:
            await _upload_to_tab(landscape_tab_idx, thumbnail_landscape_path)
            logger.info("[封面] 横版封面上传成功 (tab %s)", landscape_tab_idx)

        await cover_locator.locator('button:visible:has-text("完成")').click()
        logger.info("[封面] 封面设置完成")
        await page.wait_for_selector("div.extractFooter", state="detached")

    # ------------------------------------------------------------------
    # Helper: handle auto video cover prompt
    # ------------------------------------------------------------------

    @staticmethod
    async def _handle_auto_video_cover(page):
        try:
            if await page.get_by_text("请设置封面后再发布").first.is_visible():
                recommend_cover = page.locator(
                    '[class^="recommendCover-"]'
                ).first
                if await recommend_cover.count():
                    try:
                        await recommend_cover.click()
                        await asyncio.sleep(1)
                        confirm_text = "是否确认应用此封面？"
                        if await page.get_by_text(
                            confirm_text
                        ).first.is_visible():
                            await page.get_by_role(
                                "button", name="确定"
                            ).click()
                            await asyncio.sleep(1)
                        return True
                    except Exception as e:
                        logger.warning("[封面] 自动封面选择失败: %s", e)
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # publish_image — Douyin image note upload pipeline
    # ------------------------------------------------------------------

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image note to Douyin via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- note title (max 20 chars)
        - ``files`` (*list[str]*) -- image absolute file paths (resolved by image_publish_bp)
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``desc`` (*str*, optional) -- description (max 1000 chars)
        - ``cover_path`` (*str*, optional) -- cover image file name
        - ``mix_id`` (*str*, optional) -- mix/collection ID
        - ``music_name`` (*str*, optional) -- music name to search and select
        - ``hotspot`` (*str*, optional) -- hotspot keyword to search and select
        - ``tag_type`` (*str*, optional) -- tag type: 'location' | 'miniapp' | 'gamepad' | 'mark'
        - ``tag_value`` (*str*, optional) -- tag value (keyword or link)
        - ``mini_link`` (*str*, optional) -- mini app link (for miniapp type)
        - ``enableTimer`` (*bool*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``ai_content`` (*str*, optional) -- AI content declaration
        - ``activities`` (*list[str]*, optional) -- official activities (appended as #tags)
        - ``dry_run`` (*bool*, optional) -- if True, skip publish button click (default True)
        """
        logger.info("=" * 60)
        logger.info("[发布图集] 开始抖音图集发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        desc = kwargs.get("desc", "")
        cover_path = kwargs.get("cover_path", "")
        mix_id = kwargs.get("mix_id", "")
        music_name = kwargs.get("music_name", "")
        hotspot = kwargs.get("hotspot", "")
        tag_type = kwargs.get("tag_type", "")
        tag_value = kwargs.get("tag_value", "")
        mini_link = kwargs.get("mini_link", "")
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        ai_content = kwargs.get("ai_content", "")
        activities = kwargs.get("activities", []) or []
        dry_run = kwargs.get("dry_run", True)  # Default to dry run for safety

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 图片数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 封面: %s", cover_path or "无")
        logger.info("[发布参数] 合集ID: %s", mix_id or "无")
        logger.info("[发布参数] 音乐: %s", music_name or "无")
        logger.info("[发布参数] 热点词: %s", hotspot or "无")
        logger.info("[发布参数] 定时发布: %s", enable_timer)
        logger.info("[发布参数] AI内容声明: %s", ai_content or "无")
        logger.info("[发布策略] 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        # files 已是绝对路径（image_publish_bp 通过 _resolve_material_path 处理过）
        file_paths = [str(f) for f in files]

        # cover_path 已是绝对路径，无需拼接
        if cover_path and not Path(cover_path).is_file():
            logger.warning("[发布参数] 封面文件不存在: %s", cover_path)
            cover_path = ""

        # Append activities as hashtags to description
        if activities:
            activity_tags = " ".join([f"#{act}" for act in activities])
            desc = f"{desc} {activity_tags}".strip()

        for cookie_index, cookie_path in enumerate(account_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                await self._upload_image_note(
                    title=title,
                    file_paths=file_paths,
                    tags=tags,
                    account_file=cookie_path,
                    desc=desc,
                    cover_path=cover_path,
                    mix_id=mix_id,
                    music_name=music_name,
                    hotspot=hotspot,
                    tag_type=tag_type,
                    tag_value=tag_value,
                    mini_link=mini_link,
                    enable_timer=enable_timer,
                    schedule_time_str=schedule_time_str,
                    ai_content=ai_content,
                    dry_run=dry_run,
                )

        logger.info("=" * 60)
        logger.info("[发布图集] 图集发布流程完成!")
        logger.info("=" * 60)
        return True

    async def _upload_image_note(
        self,
        title: str,
        file_paths: list,
        tags: list,
        account_file: str,
        desc: str = "",
        cover_path: str = "",
        mix_id: str = "",
        music_name: str = "",
        hotspot: str = "",
        tag_type: str = "",
        tag_value: str = "",
        mini_link: str = "",
        enable_timer: bool = False,
        schedule_time_str: str = "",
        ai_content: str = "",
        dry_run: bool = True,
    ):
        """Upload image note to one Douyin account."""
        logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_paths))
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                await context.grant_permissions(["geolocation"])
                page = await context.new_page()

                # Navigate to image upload page
                # 抖音创作者中心是 SPA，永远不会触发 load 事件。
                # 用 domcontentloaded + URL 匹配即可，避免 30s 等待
                logger.info("[上传图集] 正在打开图集上传页面...")
                await page.goto(
                    "https://creator.douyin.com/creator-micro/content/upload?default-tab=3",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_url(
                    "https://creator.douyin.com/creator-micro/content/upload?default-tab=3",
                    timeout=60000,
                )
                logger.info("[上传图集] 图集上传页面已打开")

                # Upload images via hidden input
                logger.info("[上传图集] 正在上传 %d 张图片...", len(file_paths))
                file_input = page.locator("div[class^='container'] input[type='file']")
                await file_input.set_input_files(file_paths)

                # Wait for redirect to image publish page
                logger.info("[上传图集] 等待跳转到发布页面...")
                max_wait = 120  # seconds - longer timeout for many images
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    current_url = page.url
                    if "content/upload" not in current_url:
                        logger.info("[上传图集] 已跳转到: %s", current_url)
                        break
                    await asyncio.sleep(1)
                else:
                    logger.warning("[上传图集] 等待跳转超时")

                # Wait for all images to upload successfully
                # Calculate timeout based on image count: 30s per image, min 120s, max 600s
                upload_timeout_per_image = 30
                max_upload_wait = max(120, min(len(file_paths) * upload_timeout_per_image, 600))
                logger.info("[上传图集] 等待全部 %d 张图片上传完成 (超时: %ds)...", len(file_paths), max_upload_wait)
                uploaded_count = 0
                upload_start = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - upload_start) < max_upload_wait:
                    # Check for uploaded image count in the UI
                    image_items = page.locator('div[class*="img-"][draggable="true"]')
                    uploaded_count = await image_items.count()
                    logger.info("[上传图集] 已上传图片: %d/%d", uploaded_count, len(file_paths))
                    if uploaded_count >= len(file_paths):
                        logger.info("[上传图集] 全部 %d 张图片上传成功!", len(file_paths))
                        break
                    await asyncio.sleep(3)
                else:
                    logger.warning("[上传图集] 等待图片上传超时. 已上传: %d/%d", uploaded_count, len(file_paths))

                await asyncio.sleep(5)  # 等待更长时间确保页面加载完成

                # 逐字输入标题
                logger.info("[填写标题] 开始填写标题: %s", title[:20])
                title_input = page.get_by_placeholder("添加作品标题")
                await title_input.wait_for(state="visible", timeout=10000)
                await title_input.click()
                await title_input.fill('')
                await page.keyboard.type(title[:20])

                # 逐字输入描述，一次性注入标签
                logger.info("[填写简介] 开始填写简介与标签...")
                desc_editor = page.locator(
                    'div[data-zone-container="*"][contenteditable="true"]'
                ).first
                await desc_editor.wait_for(state="visible", timeout=10000)
                await desc_editor.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")

                await page.keyboard.type(desc[:1000])
                await asyncio.sleep(0.2)

                for tag in tags:
                    await page.keyboard.insert_text(" #" + tag)
                    await page.keyboard.press("Space")
                await asyncio.sleep(0.3)

                # Set cover if provided
                if cover_path:
                    logger.info("[设置封面] 开始设置封面图片...")
                    await self._set_image_cover(page, cover_path)

                # Set mix/collection if provided
                if mix_id:
                    logger.info("[设置合集] 开始设置合集: %s", mix_id)
                    await self._set_image_mix(page, mix_id)

                # Set music if provided
                if music_name:
                    logger.info("[选择音乐] 开始选择音乐: %s", music_name)
                    await self._select_music(page, music_name)

                # Set hotspot if provided
                if hotspot:
                    logger.info("[设置热点] 开始设置热点词: %s", hotspot)
                    await self._set_hotspot(page, hotspot)

                # Set tag (位置/小程序/游戏手柄/标记万物) if provided
                if tag_type and tag_value:
                    logger.info("[设置标签] 开始设置标签: 类型=%s, 值=%s, 小程序链接=%s", tag_type, tag_value, mini_link)
                    await self._set_tag(page, tag_type, tag_value, mini_link)

                # Set AI content declaration
                if ai_content:
                    logger.info("[内容声明] 开始设置内容声明: %s", ai_content)
                    await self._set_declaration(page, ai_content)

                # Set schedule time if needed
                if enable_timer and schedule_time_str:
                    publish_date = parse_schedule_time(
                        schedule_time_str, 1, enable_timer, 1, None, 0
                    )[0]
                    if publish_date != 0:
                        logger.info("[定时发布] 开始设置定时发布...")
                        await self._set_schedule_time(page, publish_date)
                        logger.info("[定时发布] 定时发布设置完成")

                logger.info("[填写完成] 表单填写完成, 模式: %s", "演练(dry_run)" if dry_run else "正式发布")

                if not dry_run:
                    # Click publish button
                    # 使用稳定的文本匹配：精确匹配"发布"按钮，排除"暂存离开"
                    logger.info("[发布] 正在点击发布按钮...")
                    publish_btn = page.get_by_role("button", name="发布", exact=True)
                    await publish_btn.wait_for(state="visible", timeout=10000)
                    await publish_btn.click()
                    logger.info("[发布] 发布按钮已点击, 等待页面跳转...")

                    # 等待页面跳转 - 跳转到 manage 页面才是发布成功
                    try:
                        await page.wait_for_url(
                            "https://creator.douyin.com/creator-micro/content/manage*",
                            timeout=60000
                        )
                        logger.info("[发布] 图集发布成功! 已跳转到管理页面")
                        result = True
                    except Exception:
                        # 检查当前URL
                        current_url = page.url
                        if "content/manage" in current_url:
                            logger.info("[发布] 图集发布成功! 已在管理页面")
                            result = True
                        else:
                            logger.warning("[发布] 图集发布可能失败 - 当前URL: %s", current_url)
                            result = False

                    # Save cookie state
                    await context.storage_state(path=account_file)
                    logger.info("[发布] Cookie状态已更新")
                else:
                    # Dry run mode - simulate publish
                    logger.info("=" * 40)
                    logger.info("[发布] [演练模式] 模拟点击发布! 发布成功!")
                    logger.info("=" * 40)
                    result = True

            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: set image cover
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_cover(page, cover_path: str):
        """Set cover image for image note."""
        try:
            # Click edit cover button - use text content for stability
            edit_cover_btn = page.get_by_text("编辑封面", exact=True)
            await edit_cover_btn.click()
            await asyncio.sleep(2)

            # Click upload cover tab
            upload_tab = page.get_by_role("tab", name="上传封面")
            await upload_tab.click()
            await asyncio.sleep(1)

            # Find hidden input=file in the upload area
            # Look for input[type="file"] that accepts images
            cover_input = page.locator('input[type="file"][accept*="image"]').first
            if not await cover_input.count():
                # Fallback: find any hidden file input
                cover_input = page.locator('input[type="file"]').first

            await cover_input.set_input_files(cover_path)
            await asyncio.sleep(3)

            # Click confirm in crop dialog - find button with text "确定"
            # Wait for crop dialog to appear
            await page.wait_for_selector('button:has-text("确定")', timeout=5000)
            # Click the confirm button (not the cancel button)
            confirm_buttons = page.locator('button:has-text("确定")')
            count = await confirm_buttons.count()
            logger.info("[封面] 找到 %d 个确定按钮", count)
            # Click the last one (should be the crop confirm)
            await confirm_buttons.last.click()
            await asyncio.sleep(2)

            # Click final confirm in cover editor
            final_confirm = page.locator('button:has-text("确定")').last
            await final_confirm.click()
            await asyncio.sleep(2)

            logger.info("[封面] 封面图片设置成功")
        except Exception as e:
            logger.warning("[封面] 封面设置失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set mix/collection
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_mix(page, mix_id: str):
        """Set mix/collection for image note."""
        try:
            # Click mix dropdown（视频页面可能用不同的文字）
            mix_labels = ["不选择合集", "选择合集", "添加合集"]
            mix_dropdown = None
            for label in mix_labels:
                d = page.locator(f'div.semi-select:has-text("{label}")').first
                if await d.count():
                    mix_dropdown = d
                    break
            if mix_dropdown is None:
                logger.warning("[设置合集] 未找到合集下拉框: %s", mix_id)
                return
            await mix_dropdown.click()
            await asyncio.sleep(2)

            # Select mix by ID or text
            mix_option = page.locator(
                f'div.semi-select-option:has-text("{mix_id}")'
            ).first
            if await mix_option.count():
                await mix_option.click()
                logger.info("[设置合集] 已选择合集: %s", mix_id)
            else:
                logger.warning("[设置合集] 未找到合集: %s", mix_id)
                # Close dropdown
                await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("[设置合集] 合集设置失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: select music
    # ------------------------------------------------------------------

    @staticmethod
    async def _select_music(page, music_name: str):
        """Search and select music."""
        try:
            # Click select music button - find the one in the music section
            # Use XPath to find the specific "选择音乐" button
            music_btn = page.locator('xpath=//div[contains(@class, "container-right")]//span[text()="选择音乐"]')
            if not await music_btn.count():
                # Fallback: find by text and click the visible one
                music_btn = page.get_by_text("选择音乐", exact=True).last
            await music_btn.click()
            await asyncio.sleep(3)

            # Search music - use placeholder for stability
            search_input = page.locator('input[placeholder="搜索音乐"]')
            await search_input.wait_for(state="visible", timeout=5000)
            await search_input.fill(music_name)
            await page.keyboard.press("Enter")
            await asyncio.sleep(3)

            # Find matching music card
            music_cards = page.locator('div.card-container-tmocjc')
            count = await music_cards.count()
            logger.info("[选择音乐] 找到 %d 个音乐卡片", count)

            # Find the card that matches the search text
            target_card = None
            for i in range(count):
                card = music_cards.nth(i)
                card_text = await card.text_content()
                if music_name in card_text:
                    target_card = card
                    logger.info("[选择音乐] 找到匹配音乐: %s", card_text[:50])
                    break

            if not target_card and count > 0:
                # Fallback: use first card
                target_card = music_cards.first
                logger.info("[选择音乐] 使用第一个音乐卡片作为兜底")

            if target_card:
                # Hover to show "使用" button
                await target_card.hover()
                await asyncio.sleep(1)

                # Click use button within this card
                use_btn = target_card.locator('button:has-text("使用")')
                if await use_btn.count():
                    await use_btn.click(force=True)
                    logger.info("[选择音乐] 已选择音乐: %s", music_name)
                else:
                    logger.warning("[选择音乐] 未找到使用按钮: %s", music_name)
            else:
                logger.warning("[选择音乐] 未找到音乐卡片: %s", music_name)

            await asyncio.sleep(2)
        except Exception as e:
            logger.warning("[选择音乐] 选择音乐失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set hotspot
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_hotspot(page, hotspot: str):
        """Search and select hotspot."""
        try:
            # Click hotspot - use text for stability (it's a span, not input)
            hotspot_text = page.get_by_text("点击输入热点词", exact=True)
            await hotspot_text.click()
            await asyncio.sleep(1)

            # Type hotspot keyword
            await page.keyboard.insert_text(hotspot)
            await asyncio.sleep(3)

            # Find matching hotspot option in dropdown
            hotspot_options = page.locator('div[role="option"]:not([aria-disabled="true"])')
            count = await hotspot_options.count()
            # 视频页面可能使用不同的下拉组件，尝试更多选择器
            if count == 0:
                hotspot_options = page.locator('[role="option"]:not([aria-disabled="true"])')
                count = await hotspot_options.count()
            if count == 0:
                # 尝试找任意可见的搜索结果项
                hotspot_options = page.locator('[class*="option"]:not([aria-disabled="true"])')
                count = await hotspot_options.count()
            logger.info("[设置热点] 找到 %d 个热点选项", count)

            # Click the option that matches the search text
            clicked = False
            for i in range(count):
                option = hotspot_options.nth(i)
                option_text = await option.text_content()
                if hotspot in option_text:
                    await option.click()
                    logger.info("[设置热点] 已选择热点: %s (匹配: %s)", hotspot, option_text[:50])
                    clicked = True
                    break

            if not clicked:
                # Fallback: click first option if no exact match
                if count > 0:
                    await hotspot_options.first.click()
                    logger.info("[设置热点] 已选择热点: %s (第一个选项)", hotspot)
                else:
                    logger.warning("[设置热点] 未找到热点: %s, 尝试回车", hotspot)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1)

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("[设置热点] 设置热点失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set tag (位置/小程序/游戏手柄/标记万物)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_tag(page, tag_type: str, tag_value: str, mini_link: str = ""):
        """Set tag with type and value.

        tag_type: 'location' | 'miniapp' | 'gamepad' | 'mark'
        tag_value: the search keyword or link
        mini_link: mini app link (for miniapp type)
        """
        try:
            # Tag type mapping
            type_map = {
                'location': '位置',
                'miniapp': '小程序',
                'gamepad': '游戏手柄',
                'mark': '标记万物',
                'film': '影视演艺',
            }
            type_text = type_map.get(tag_type, '位置')

            # 遍历所有 .semi-select，排除合集那个，找到标签类型选择器
            all_selects = page.locator('div.semi-select')
            select_count = await all_selects.count()
            tag_dropdown = None
            for i in range(select_count):
                sel = all_selects.nth(i)
                text = await sel.text_content()
                if "合集" not in text:
                    tag_dropdown = sel
                    break
            if tag_dropdown is None:
                logger.warning("[设置标签] 未找到标签类型选择器, 跳过")
                return
            await tag_dropdown.click()
            await asyncio.sleep(1)

            # Select tag type
            logger.info("[设置标签] 查找标签类型选项: %s", type_text)
            # 打印下拉中所有可见选项
            all_opts = page.locator('[role="option"]')
            opt_count = await all_opts.count()
            for oi in range(opt_count):
                try:
                    t = await all_opts.nth(oi).text_content()
                    logger.info("[设置标签]   option[%s]: %s", oi, t.strip()[:50] if t else "(空)")
                except Exception:
                    pass
            try:
                type_option = page.get_by_role("option", name=type_text)
                await type_option.wait_for(state="visible", timeout=5000)
            except Exception:
                logger.warning("[设置标签] 未找到标签类型选项: %s", type_text)
                await page.keyboard.press("Escape")
                return
            await type_option.click()
            await asyncio.sleep(1)

            # Helper function to find and click matching option
            async def find_and_click_option(page, tag_value, option_selector='div[role="option"]'):
                options = page.locator(option_selector)
                count = await options.count()
                logger.info("[设置标签] 找到 %d 个选项", count)

                # 先尝试完全匹配
                for i in range(count):
                    option = options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置标签: %s (完全匹配)", tag_value)
                        return True

                # 再尝试包含匹配
                for i in range(count):
                    option = options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if tag_value in option_text:
                        await option.click()
                        logger.info("[设置标签] 已设置标签: %s (包含匹配: %s)", tag_value, option_text[:50])
                        return True

                # Fallback: click first option
                if count > 0:
                    await options.first.click()
                    logger.info("[设置标签] 已设置标签: %s (第一个选项)", tag_value)
                    return True
                return False

            # Based on tag type, handle differently
            if tag_type == 'location':
                # Location: click to activate, then input search keyword
                location_select = page.get_by_text("输入相关位置，让更多人看到你的作品", exact=True)
                if await location_select.count() == 0:
                    location_select = page.get_by_text("输入地理位置", exact=True)
                await location_select.click()
                await asyncio.sleep(1)

                # Use keyboard to type directly since input is already focused
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入位置关键词: %s", tag_value)
                await asyncio.sleep(5)  # 位置查询可能有延迟，等待更长时间

                # Select matching result
                await find_and_click_option(page, tag_value)

            elif tag_type == 'miniapp':
                # Mini app: click to activate, then paste link
                miniapp_select = page.get_by_text("粘贴抖音小程序链接", exact=True)
                await miniapp_select.click()
                await asyncio.sleep(1)

                # Use mini_link if provided, otherwise use tag_value
                link_to_use = mini_link if mini_link else tag_value
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入小程序链接: %s", link_to_use)
                await asyncio.sleep(2)

                # Select matching result
                await find_and_click_option(page, tag_value, 'div[role="option"]:not([aria-disabled="true"])')

            elif tag_type == 'gamepad':
                # Game: click the semi-select component by placeholder text
                game_select = page.get_by_text("添加作品同款游戏", exact=True)
                await game_select.click()
                await asyncio.sleep(1)

                # Use keyboard to type directly since input is already focused
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入游戏标签值: %s", tag_value)
                await asyncio.sleep(3)

                # Find matching game option in dropdown
                game_options = page.locator('div.semi-popover [class*="anchor-game-option"]')
                count = await game_options.count()
                logger.info("[设置标签] 找到 %d 个游戏选项", count)

                # Click the option that matches the search text
                clicked = False
                # 先完全匹配
                for i in range(count):
                    option = game_options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置游戏标签: %s (完全匹配)", tag_value)
                        clicked = True
                        break
                if not clicked:
                    # 再包含匹配
                    for i in range(count):
                        option = game_options.nth(i)
                        option_text = (await option.text_content() or '').strip()
                        if tag_value in option_text:
                            await option.click()
                            logger.info("[设置标签] 已设置游戏标签: %s (包含: %s)", tag_value, option_text[:50])
                            clicked = True
                            break

            elif tag_type == 'mark':
                # Mark: input search keyword
                mark_input = page.get_by_placeholder("请输入或选择标记的物品")
                await mark_input.click()
                await asyncio.sleep(1)
                await page.keyboard.insert_text(tag_value)
                await asyncio.sleep(3)

                # Find matching mark option in dropdown
                mark_options = page.locator('div.semi-popover [class*="option-"]')
                count = await mark_options.count()
                logger.info("[设置标签] 找到 %d 个标记选项", count)

                # Click the option that matches the search text
                clicked = False
                for i in range(count):
                    option = mark_options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置标记标签: %s (完全匹配)", tag_value)
                        clicked = True
                        break
                if not clicked:
                    for i in range(count):
                        option = mark_options.nth(i)
                        option_text = (await option.text_content() or '').strip()
                        if tag_value in option_text:
                            await option.click()
                            logger.info("[设置标签] 已设置标记标签: %s (包含: %s)", tag_value, option_text[:50])
                            clicked = True
                            break

            elif tag_type == 'film':
                # Film/Media: input search keyword
                film_input = page.get_by_text("输入IP名称, 如 “少年的你”", exact=True)
                await film_input.click()
                await asyncio.sleep(1)
                await page.keyboard.insert_text(tag_value)
                logger.info("[设置标签] 已输入影视关键词: %s", tag_value)
                await asyncio.sleep(1)
                try:
                    await page.wait_for_selector('[role="option"]', timeout=8000)
                except Exception:
                    logger.warning("[设置标签] 影视搜索选项未出现")
                film_options = page.locator('[role="option"]')
                count = await film_options.count()
                logger.info("[设置标签] 找到 %d 个影视选项", count)
                for oi in range(count):
                    try:
                        ot = await film_options.nth(oi).text_content()
                        logger.info("[设置标签]   影视option[%s]: %s", oi, (ot or '').strip()[:80])
                    except Exception:
                        pass
                clicked = False
                for i in range(count):
                    option = film_options.nth(i)
                    option_text = (await option.text_content() or '').strip()
                    if option_text == tag_value:
                        await option.click()
                        logger.info("[设置标签] 已设置影视标签: %s (完全匹配)", tag_value)
                        clicked = True
                        break
                if not clicked:
                    for i in range(count):
                        option = film_options.nth(i)
                        option_text = (await option.text_content() or '').strip()
                        if tag_value in option_text:
                            await option.click()
                            logger.info("[设置标签] 已设置影视标签: %s (包含: %s)", tag_value, option_text[:50])
                            clicked = True
                            break

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("[设置标签] 设置标签失败: %s", e)

    @staticmethod
    async def _set_location_tag(page, location: str):
        """Search and select location tag."""
        try:
            # Click location input
            location_input = page.get_by_placeholder("输入相关位置，让更多人看到你的作品")
            if await location_input.count() == 0:
                location_input = page.get_by_placeholder("输入地理位置")
            await location_input.click()
            await asyncio.sleep(1)

            # Type location keyword
            await page.keyboard.type(location)
            await asyncio.sleep(2)

            # Select first result
            location_option = page.locator(
                'div[role="option"]'
            ).first
            if await location_option.count():
                await location_option.click()
                logger.info("[设置位置] 已选择位置: %s", location)
            else:
                logger.warning("[设置位置] 未找到位置: %s", location)
                await page.keyboard.press("Escape")

            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("[设置位置] 设置位置失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set AI content declaration
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_declaration(page, ai_content: str):
        logger.info("[内容声明] 开始设置内容声明: %s", ai_content)
        try:
            select_box = page.locator(".selectBox-buZRzi").first
            await select_box.wait_for(state="visible", timeout=10000)
            await select_box.click()
            await asyncio.sleep(2)

            clicked = await page.evaluate(
                """(targetText) => {
                const addons = document.querySelectorAll('.semi-radio-addon');
                for (const addon of addons) {
                    if (addon.textContent.trim() === targetText) {
                        addon.closest('label').click();
                        return addon.textContent.trim();
                    }
                }
                return null;
            }""",
                ai_content,
            )

            if clicked:
                logger.info("[内容声明] 已选择声明: %s", clicked)
                await asyncio.sleep(1)

                await page.evaluate(
                    """() => {
                    const btns = document.querySelectorAll('.btnWrapper-LtGF4z button');
                    for (const btn of btns) {
                        if (btn.textContent.trim() === '确定') {
                            btn.disabled = false;
                            btn.className = btn.className.replace('semi-button-disabled', '');
                            btn.click();
                        }
                    }
                }"""
                )
                logger.info("[内容声明] 声明已确认")
            else:
                logger.warning("[内容声明] 未找到声明选项: %s", ai_content)
                close_btn = page.locator(".semi-modal-close")
                if await close_btn.count() > 0:
                    await close_btn.first.click()

            await asyncio.sleep(1)
        except Exception as exc:
            logger.warning(
                "[内容声明] 声明设置失败 (非阻断): %s", exc
            )
