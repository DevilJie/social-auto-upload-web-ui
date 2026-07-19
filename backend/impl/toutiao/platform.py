"""
今日头条平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作中心地址：https://mp.toutiao.com/profile_v4/index
视频发布地址：https://mp.toutiao.com/profile_v4/xigua/upload-video
"""

import asyncio
import json
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
    scrape_toutiao_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("toutiao")


class ToutiaoPlatform(BasePlatform):
    platform_id = 13
    platform_key = "toutiao"
    platform_name = "今日头条"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 头条 cookie 全部由 mp.toutiao.com / sso.toutiao.com 下发，
    # 通配 .toutiao.com 后对创作中心和子域都生效。
    platform_cookie_domain = ".toutiao.com"

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.toutiao.com)
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
            f"[toutiao] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Toutiao login via QR code scan."""
        logger.info("=" * 60)
        logger.info("[登录] 开始今日头条登录流程")
        logger.info("=" * 60)

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                logger.info("[登录] 正在打开头条创作中心...")
                await page.goto("https://mp.toutiao.com/profile_v4/index")
                await asyncio.sleep(3)

                # Extract QR code image
                src = None
                qr_selectors = [
                    'img[class*="qrcode"]',
                    'img[class*="qr-code"]',
                    'img[class*="QRCode"]',
                    'img[class*="scan-code"]',
                    'div[class*="qrcode"] img',
                    'div[class*="login"] img',
                    'img.web-login-scan-code__content__',
                ]
                for selector in qr_selectors:
                    try:
                        img_locator = page.locator(selector).first
                        if await img_locator.count():
                            src = await img_locator.get_attribute("src")
                            if src and (src.startswith("http") or src.startswith("data:")):
                                logger.info("[登录] 找到二维码图片，选择器: %s", selector)
                                break
                            src = None
                    except Exception:
                        continue

                if src:
                    logger.info("[登录] 二维码图片已发送到前端")
                    status_queue.put(src)
                else:
                    logger.warning("[登录] 未找到二维码图片")
                    status_queue.put(json.dumps({"error": "无法找到登录二维码"}))

                # Wait for login
                logger.info("[登录] 等待用户扫码...")
                max_wait = 300  # 5 minutes
                start_time = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    try:
                        current_url = page.url
                        if "auth/page/login" not in current_url and "profile_v4" in current_url:
                            logger.info("[登录] 检测到页面跳转，登录成功!")
                            break
                        user_panel = page.locator('div.user-panel')
                        if await user_panel.count():
                            logger.info("[登录] 检测到用户面板，登录成功!")
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)

                # Scrape profile & save
                logger.info("[登录] 正在获取用户信息...")
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_toutiao_profile,
                    account_id=account_id,
                )
                logger.info("[登录] 登录流程完成!")
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        logger.info("[Cookie检查] 开始检查cookie有效性: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(
                    "https://mp.toutiao.com/profile_v4/index",
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                await asyncio.sleep(3)

                user_panel = page.locator('div.user-panel')
                if await user_panel.count():
                    logger.info("[Cookie检查] Cookie有效，用户面板存在")
                    return True

                logger.warning("[Cookie检查] Cookie无效，未找到用户面板")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Toutiao creator centre."""
        logger.info("[同步资料] 开始同步用户资料: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                try:
                    await page.goto(
                        "https://mp.toutiao.com/profile_v4/index",
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception:
                    pass
                await asyncio.sleep(3)
                name, avatar = await scrape_toutiao_profile(page)
                logger.info("[同步资料] 获取到用户信息 - 昵称: %s, 头像: %s", name, avatar[:50] if avatar else "无")
                return name, avatar
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Toutiao creator centre in a visible browser window."""
        logger.info("[打开创作中心] 正在打开创作中心...")
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = "https://mp.toutiao.com/profile_v4/index"

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                logger.info("[打开创作中心] 创作中心已打开")
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
    # publish_video — full Toutiao upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Toutiao via CloakBrowser."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始今日头条视频发布流程")
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
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        # 16:9 / 9:16 次尺寸封面(头条横版视频用 16:9,竖版视频用 9:16)
        thumbnail_landscape_169_path = kwargs.get("thumbnail_landscape_169_path", "")
        thumbnail_portrait_916_path = kwargs.get("thumbnail_portrait_916_path", "")
        creation_declaration = kwargs.get("creation_declaration", "") or ""
        enable_generate_image = kwargs.get("enable_generate_image", True)
        collection_id = kwargs.get("collection_id", "")
        extend_link = kwargs.get("extend_link", False)
        extend_link_url = kwargs.get("extend_link_url", "")

        # 打印接收到的参数，用于调试
        logger.info("[参数调试] creation_declaration 原始值: %s (类型: %s)", creation_declaration, type(creation_declaration).__name__)
        logger.info("[参数调试] enable_generate_image: %s", enable_generate_image)
        logger.info("[参数调试] collection_id: %s", collection_id)
        logger.info("[参数调试] extend_link: %s (类型: %s)", extend_link, type(extend_link).__name__)
        logger.info("[参数调试] extend_link_url: %s", extend_link_url)

        # 处理作品声明：可能是字符串（逗号分隔）或列表
        if isinstance(creation_declaration, str):
            creation_declaration = [d.strip() for d in creation_declaration.split(",") if d.strip()]
        elif not isinstance(creation_declaration, list):
            creation_declaration = []

        # 打印发布参数
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 作品声明: %s", creation_declaration)
        logger.info("[发布参数] 生成图文: %s", enable_generate_image)
        logger.info("[发布参数] 合集ID: %s", collection_id or "无")
        logger.info("[发布参数] 扩展链接: %s (URL: %s)", extend_link, extend_link_url or "无")
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 横版16:9封面: %s", thumbnail_landscape_169_path or "无")
        logger.info("[发布参数] 竖版9:16封面: %s", thumbnail_portrait_916_path or "无")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(thumbnail_portrait_path)
        if thumbnail_landscape_169_path:
            thumbnail_landscape_169_path = str(thumbnail_landscape_169_path)
        if thumbnail_portrait_916_path:
            thumbnail_portrait_916_path = str(thumbnail_portrait_916_path)

        # Determine publish strategy and schedule times
        publish_strategy = "scheduled" if enableTimer and schedule_time_str else "immediate"
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
                        desc=desc,
                        thumbnail_landscape_path=thumbnail_landscape_path or None,
                        thumbnail_portrait_path=thumbnail_portrait_path or None,
                        thumbnail_landscape_169_path=thumbnail_landscape_169_path or None,
                        thumbnail_portrait_916_path=thumbnail_portrait_916_path or None,
                        creation_declaration=creation_declaration,
                        enable_generate_image=enable_generate_image,
                        collection_id=collection_id,
                        extend_link=extend_link,
                        extend_link_url=extend_link_url,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        publish_date,
        account_file: str,
        publish_strategy: str,
        desc="",
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
        creation_declaration=None,
        enable_generate_image=True,
        collection_id="",
        extend_link=False,
        extend_link_url="",
    ):
        """Upload a single video to one Toutiao account."""
        logger.info("[上传视频] 开始上传视频: %s", file_path)
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()
                logger.info("[上传视频] 正在打开发布页面...")
                await page.goto(
                    "https://mp.toutiao.com/profile_v4/xigua/upload-video"
                )
                await page.wait_for_url(
                    "https://mp.toutiao.com/profile_v4/xigua/upload-video"
                )
                logger.info("[上传视频] 发布页面已打开")

                # Upload video file
                logger.info("[上传视频] 正在上传视频文件...")
                file_input = page.locator('input[type="file"][accept*="video"]')
                if not await file_input.count():
                    file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择，等待上传完成...")

                # Wait for upload to complete
                max_wait = 14400  # 4 hours for large files (no timeout limit)
                start_time = asyncio.get_event_loop().time()
                upload_complete = False
                last_progress = ""
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    try:
                        success_text = page.locator('span.percent:has-text("上传成功")')
                        if await success_text.count():
                            upload_complete = True
                            logger.info("[上传视频] 视频上传成功!")
                            break
                        # 打印上传进度
                        progress_text = page.locator('span.percent')
                        if await progress_text.count():
                            current_progress = await progress_text.first.text_content()
                            if current_progress and current_progress != last_progress:
                                logger.info("[上传视频] %s", current_progress)
                                last_progress = current_progress
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                if not upload_complete:
                    logger.error("[上传视频] 视频上传超时! 已等待 %d 秒", max_wait)
                    return

                await asyncio.sleep(2)

                # Determine if this is a portrait video
                is_portrait = False
                try:
                    poster_editor = page.locator('div.xigua-poster-editor.portrait')
                    if await poster_editor.count():
                        is_portrait = True
                        logger.info("[视频类型] 检测到竖版视频")
                    else:
                        logger.info("[视频类型] 检测到横版视频")
                except Exception:
                    logger.info("[视频类型] 默认为横版视频")

                # Fill title (max 30 chars)
                logger.info("[填写标题] 标题: %s", title[:30])
                title_input = page.locator('input[placeholder*="请输入"][placeholder*="字符"]')
                if not await title_input.count():
                    title_input = page.locator('.article-title-wrap input')
                await title_input.wait_for(state="visible", timeout=10000)
                await title_input.fill(title[:30])
                logger.info("[填写标题] 标题填写完成")

                # Fill video description/简介 (横版视频才有)
                if not is_portrait:
                    logger.info("[填写简介] 开始填写视频简介...")
                    if desc:
                        logger.info("[填写简介] 简介内容: %s...", desc[:50])
                        # 头条的视频简介是一个 textarea 或 contenteditable div
                        desc_selectors = [
                            'div.video-form-item.form-item-desc div[contenteditable="true"]',
                            'div.form-item-desc textarea',
                            'div.form-item-desc div[contenteditable]',
                            '.video-form-item-wrapper textarea[placeholder*="简介"]',
                            '.video-form-item-wrapper div[contenteditable="true"]',
                        ]
                        desc_filled = False
                        for selector in desc_selectors:
                            try:
                                desc_el = page.locator(selector).first
                                if await desc_el.count():
                                    await desc_el.click()
                                    await asyncio.sleep(0.5)
                                    # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
                                    await clear_and_type(page, desc[:400])
                                    desc_filled = True
                                    logger.info("[填写简介] 视频简介填写成功!")
                                    break
                            except Exception as e:
                                logger.debug("[填写简介] 选择器 %s 失败: %s", selector, e)
                                continue

                        if not desc_filled:
                            # 尝试通过 placeholder 找
                            try:
                                desc_by_placeholder = page.get_by_placeholder("请输入视频简介")
                                if await desc_by_placeholder.count():
                                    await desc_by_placeholder.fill(desc[:400])
                                    logger.info("[填写简介] 通过 placeholder 填写成功")
                                    desc_filled = True
                            except Exception:
                                pass

                        if not desc_filled:
                            logger.warning("[填写简介] 未找到视频简介输入框!")
                    else:
                        logger.info("[填写简介] 无视频简介")
                else:
                    logger.info("[填写简介] 竖版视频不支持视频简介")

                # Fill tags (max 10)
                if tags:
                    logger.info("[填写标签] 开始填写标签: %s", tags[:10])
                    await self._fill_tags(page, tags[:10])
                    logger.info("[填写标签] 标签填写完成")
                else:
                    logger.info("[填写标签] 无标签")

                # Set thumbnail/cover
                if (thumbnail_landscape_path or thumbnail_portrait_path
                        or thumbnail_landscape_169_path or thumbnail_portrait_916_path):
                    logger.info("[设置封面] 开始设置封面...")
                    await self._set_thumbnail(
                        page,
                        thumbnail_landscape_path,
                        thumbnail_portrait_path,
                        thumbnail_landscape_169_path,
                        thumbnail_portrait_916_path,
                        is_portrait,
                    )
                    logger.info("[设置封面] 封面设置完成")
                else:
                    logger.info("[设置封面] 无自定义封面")

                # Set creation declaration (multi-select)
                if creation_declaration:
                    logger.info("[设置声明] 开始设置作品声明: %s", creation_declaration)
                    await self._set_creation_declaration(page, creation_declaration)
                    logger.info("[设置声明] 作品声明设置完成")
                else:
                    logger.info("[设置声明] 无作品声明")

                # Toggle video-to-image generation
                logger.info("[生成图文] 设置视频生成图文: %s", enable_generate_image)
                await self._toggle_generate_image(page, enable_generate_image)
                logger.info("[生成图文] 视频生成图文设置完成")

                # Set collection (landscape only)
                if collection_id and not is_portrait:
                    logger.info("[设置合集] 开始设置合集: %s", collection_id)
                    await self._set_collection(page, collection_id)
                    logger.info("[设置合集] 合集设置完成")
                elif collection_id and is_portrait:
                    logger.info("[设置合集] 竖版视频不支持合集功能")
                else:
                    logger.info("[设置合集] 无合集")

                # Set extend link (landscape only)
                if extend_link and not is_portrait:
                    logger.info("[扩展链接] 开始设置扩展链接: %s", extend_link_url)
                    await self._toggle_extend_link(page, extend_link_url)
                    logger.info("[扩展链接] 扩展链接设置完成")
                elif extend_link and is_portrait:
                    logger.info("[扩展链接] 竖版视频不支持扩展链接")
                else:
                    logger.info("[扩展链接] 无扩展链接")

                # Schedule if needed
                if publish_strategy == "scheduled" and publish_date != 0:
                    logger.info("[定时发布] 开始设置定时发布时间: %s", publish_date)
                    await self._set_schedule_time(page, publish_date)
                    logger.info("[定时发布] 定时发布时间设置完成")

                # Click publish
                logger.info("[发布] 正在点击发布按钮...")
                publish_btn = page.locator('button.action-footer-btn.submit')
                if not await publish_btn.count():
                    publish_btn = page.get_by_role("button", name="发布", exact=True)
                await publish_btn.click()

                # Wait for redirect (publish success)
                await asyncio.sleep(3)
                current_url = page.url
                if "upload-video" not in current_url:
                    logger.info("[发布] 视频发布成功! 页面跳转到: %s", current_url)
                else:
                    logger.info("[发布] 发布按钮已点击，等待确认...")

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # Helper: fill tags
    # ------------------------------------------------------------------

    @staticmethod
    async def _fill_tags(page, tags: list):
        """Fill hashtags (max 10) with dropdown selection."""
        logger.info("[标签] 开始填写 %d 个标签", len(tags))
        try:
            tag_input = page.locator('.hash-tag-editor input, .arco-input-tag-input')
            if not await tag_input.count():
                logger.warning("[标签] 未找到标签输入框!")
                return

            for i, tag in enumerate(tags[:10]):
                if not tag:
                    continue
                logger.info("[标签] 填写第 %d 个标签: %s", i + 1, tag)
                await tag_input.click()
                await asyncio.sleep(0.5)

                await page.keyboard.insert_text(tag)
                await asyncio.sleep(1.5)

                # Try to select from dropdown
                try:
                    dropdown_items = page.locator('.arco-dropdown-menu-item, [role="menuitem"]')
                    count = await dropdown_items.count()
                    if count > 0:
                        for j in range(count):
                            item = dropdown_items.nth(j)
                            item_text = (await item.text_content() or '').strip()
                            if tag in item_text:
                                await item.click()
                                logger.info("[标签] 从下拉列表选择: %s", item_text)
                                break
                        else:
                            await dropdown_items.first.click()
                            logger.info("[标签] 选择第一个下拉选项")
                    else:
                        await page.keyboard.press("Enter")
                        logger.info("[标签] 按 Enter 确认标签")
                except Exception:
                    await page.keyboard.press("Enter")
                    logger.info("[标签] 按 Enter 确认标签 (fallback)")

                await asyncio.sleep(0.5)

            logger.info("[标签] 所有标签填写完成")
        except Exception as e:
            logger.error("[标签] 填写标签失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set thumbnail (cover images)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_thumbnail(
        page,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
        is_portrait=False,
    ):
        """Set video cover/thumbnail.

        封面尺寸选择策略(按视频方向):
        - 横版视频 → 优先 16:9 横封面(thumbnail_landscape_169_path),
                    没有则回退到 4:3 横封面(thumbnail_landscape_path)
        - 竖版视频 → 优先 9:16 竖封面(thumbnail_portrait_916_path),
                    没有则回退到 3:4 竖封面(thumbnail_portrait_path)
        两者都为空才跳过。
        """
        if (not thumbnail_landscape_path and not thumbnail_portrait_path
                and not thumbnail_landscape_169_path and not thumbnail_portrait_916_path):
            return

        logger.info("[封面] 开始设置视频封面")
        try:
            cover_editor = page.locator('div.xigua-poster-editor')
            if not await cover_editor.count():
                logger.warning("[封面] 未找到封面编辑器!")
                return

            await cover_editor.click()
            await asyncio.sleep(2)
            logger.info("[封面] 封面编辑器已打开")

            # Switch to "本地上传" tab
            upload_tab = page.locator('li:has-text("本地上传")')
            if await upload_tab.count():
                await upload_tab.click()
                await asyncio.sleep(1)
                logger.info("[封面] 已切换到本地上传")

            # Find hidden file input and upload
            cover_input = page.locator('input[type="file"][accept*="image"]')
            if not await cover_input.count():
                cover_input = page.locator('input[type="file"]').first

            # 按视频方向优先选 16:9 / 9:16 新尺寸,没有才回退到 4:3 / 3:4
            if is_portrait:
                thumb_path = (thumbnail_portrait_916_path
                              or thumbnail_portrait_path
                              or thumbnail_landscape_path)
                size_label = "9:16 竖封面" if thumbnail_portrait_916_path else "3:4 竖封面(回退)"
            else:
                thumb_path = (thumbnail_landscape_169_path
                              or thumbnail_landscape_path
                              or thumbnail_portrait_path)
                size_label = "16:9 横封面" if thumbnail_landscape_169_path else "4:3 横封面(回退)"

            logger.info("[封面] 上传封面图片[%s]: %s", size_label, thumb_path)
            await cover_input.set_input_files(thumb_path)
            await asyncio.sleep(2)

            # 上传后头条会进入裁剪/预览页,依次尝试点击「完成裁剪」「确定」按钮。
            # 注意:不能用 class 定位(antd/头条自有 hash 会漂移),改用
            # button + 文字精确定位 + role=button 兜底。
            #
            # 规则:如果上传的图片就是头条规定比例(16:9 / 9:16),
            # 头条不会弹「完成裁剪」,直接显示「确定」→ 这时必须立刻跳过
            # 「完成裁剪」步骤,不能傻等。
            async def _click_btn_by_text(text, wait_timeout_ms=5000):
                """按可见文字点击按钮(button / [role=button]),不依赖 class。

                先用 count() 毫秒级探测元素是否存在,不存在立即返回 False
                (避免 wait_for 把整个 timeout 浪费在等一个不会出现的按钮上)。
                存在才 wait_for + click。返回 True/False。
                """
                candidates = [
                    f"button:has-text('{text}')",
                    f"[role='button']:has-text('{text}')",
                ]
                for sel in candidates:
                    loc = page.locator(sel).first
                    # 毫秒级探测:不存在直接跳下一个,不浪费时间
                    if await loc.count() == 0:
                        continue
                    try:
                        await loc.wait_for(state="visible", timeout=wait_timeout_ms)
                        if await loc.is_enabled():
                            await loc.click(timeout=wait_timeout_ms)
                            logger.info("[封面] 已点击「%s」(选择器=%s)", text, sel)
                            return True
                    except Exception:
                        continue
                logger.info("[封面] 未找到「%s」按钮,跳过", text)
                return False

            # 1. 完成裁剪(可选):图片符合规定比例时不会出现,直接跳过
            #    用 count() 探测,不存在立即跳过,不会卡 3 秒
            if await page.locator("button:has-text('完成裁剪')").count() > 0:
                await _click_btn_by_text("完成裁剪", wait_timeout_ms=5000)
                await asyncio.sleep(1)
            else:
                logger.info("[封面] 未出现「完成裁剪」(图片符合规定比例),直接点确定")

            # 2. 确定(必点,关闭封面编辑弹窗)
            ok = await _click_btn_by_text("确定", wait_timeout_ms=8000)
            if not ok:
                logger.warning("[封面] 未点到「确定」按钮,封面可能未生效")
            await asyncio.sleep(2)

            # 3. 二次确认对话框(可选)
            #    DOM 结构:
            #      <div>(对话框容器,类名带 hash 会漂移,不用)
            #        <div>...完成后无法继续编辑,是否确定完成？</div>  ← body 文字(稳定)
            #        <button>取消</button>
            #        <button>确定</button>                            ← 要点这个
            #      </div>
            #    定位锚点:body 文字"完成后无法继续编辑"(产品文案稳定,不依赖 class)。
            #    不能用 button:has-text('确定') 全局判断,会误匹配主弹窗残留的同名按钮。
            #    用 XPath 一次定位:同时含「完成后无法继续编辑」文字 + 含「取消」「确定」
            #    两个按钮的最小容器,再点其中的「确定」
            try:
                # contains() 配合 normalize-space 处理空白,翻译全角逗号(中文文案)
                dialog_root = page.locator(
                    "xpath=//*[contains(normalize-space(.), '完成后无法继续编辑') "
                    "and .//button[normalize-space()='取消'] "
                    "and .//button[normalize-space()='确定']][last()]"
                )
                if await dialog_root.count() > 0:
                    dialog_ok_btn = dialog_root.locator(
                        "button:has-text('确定')"
                    ).first
                    await dialog_ok_btn.wait_for(state="visible", timeout=3000)
                    if await dialog_ok_btn.is_enabled():
                        await dialog_ok_btn.click(timeout=3000)
                        logger.info("[封面] 已点击二次确认弹窗「确定」")
                        await asyncio.sleep(1)
                else:
                    logger.info("[封面] 未出现二次确认弹窗,流程结束")
            except Exception as e:
                logger.warning("[封面] 二次确认弹窗处理失败: %s", e)

            logger.info("[封面] 封面设置完成")
        except Exception as e:
            logger.error("[封面] 设置封面失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set creation declaration (multi-select)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_creation_declaration(page, declarations: list):
        """Set creation declarations (multi-select checkboxes)."""
        logger.info("[声明] 开始设置作品声明: %s", declarations)
        try:
            for i, decl in enumerate(declarations):
                if not decl:
                    continue
                logger.info("[声明] 选择第 %d/%d 个声明: %s", i + 1, len(declarations), decl)

                # 精确匹配：通过 inner-text 文本找到 checkbox，然后点击
                # DOM 结构: label > span.byte-checkbox-wrapper > span.byte-checkbox-inner-text
                checkbox_text = page.locator(f'span.byte-checkbox-inner-text:has-text("{decl}")').first
                if await checkbox_text.count():
                    # 找到包含该文本的 label
                    label = checkbox_text.locator('xpath=ancestor::label[1]')
                    if await label.count():
                        # 检查是否已勾选
                        checkbox = label.locator('input[type="checkbox"]')
                        if await checkbox.count():
                            is_checked = await checkbox.is_checked()
                            if not is_checked:
                                await label.click()
                                logger.info("[声明] 已勾选: %s", decl)
                                await asyncio.sleep(1)  # 等待勾选生效
                            else:
                                logger.info("[声明] 已经是勾选状态: %s", decl)
                        else:
                            await label.click()
                            logger.info("[声明] 点击 label: %s", decl)
                            await asyncio.sleep(1)
                    else:
                        logger.warning("[声明] 未找到 label: %s", decl)
                else:
                    logger.warning("[声明] 未找到声明选项: %s", decl)

            logger.info("[声明] 作品声明设置完成")
        except Exception as e:
            logger.error("[声明] 设置作品声明失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: toggle video-to-image generation
    # ------------------------------------------------------------------

    @staticmethod
    async def _toggle_generate_image(page, enable: bool):
        """Toggle the '生成图文' checkbox."""
        logger.info("[生成图文] 设置视频生成图文: %s", enable)
        try:
            checkbox_label = page.locator('label:has-text("生成图文")')
            if await checkbox_label.count():
                checkbox = checkbox_label.locator('input[type="checkbox"]')
                if await checkbox.count():
                    is_checked = await checkbox.is_checked()
                    if enable and not is_checked:
                        await checkbox_label.click()
                        logger.info("[生成图文] 已启用视频生成图文")
                    elif not enable and is_checked:
                        await checkbox_label.click()
                        logger.info("[生成图文] 已禁用视频生成图文")
                    else:
                        logger.info("[生成图文] 视频生成图文状态已是目标状态")
            else:
                logger.warning("[生成图文] 未找到生成图文选项!")
        except Exception as e:
            logger.error("[生成图文] 设置视频生成图文失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set collection (合集)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_collection(page, collection_id: str):
        """Set collection/series for the video."""
        logger.info("[合集] 开始设置合集: %s", collection_id)
        try:
            collection_btn = page.locator('button:has-text("选择合集")')
            if await collection_btn.count():
                await collection_btn.click()
                await asyncio.sleep(2)
                logger.info("[合集] 已打开合集选择弹窗")

                # Select the collection by ID or text
                collection_option = page.locator(f'input[type="radio"][value="{collection_id}"]')
                if await collection_option.count():
                    await collection_option.click()
                    logger.info("[合集] 已选择合集 (by ID): %s", collection_id)
                else:
                    collection_label = page.locator(f'label:has-text("{collection_id}")')
                    if await collection_label.count():
                        await collection_label.click()
                        logger.info("[合集] 已选择合集 (by text): %s", collection_id)
                    else:
                        logger.warning("[合集] 未找到合集: %s", collection_id)

                # Click confirm button
                confirm_btn = page.locator('.add-to-series-action button:has-text("确定")')
                if await confirm_btn.count():
                    await confirm_btn.click()
                    await asyncio.sleep(1)
                    logger.info("[合集] 已点击确定")
            else:
                logger.warning("[合集] 未找到选择合集按钮!")
        except Exception as e:
            logger.error("[合集] 设置合集失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: toggle extend link
    # ------------------------------------------------------------------

    @staticmethod
    async def _toggle_extend_link(page, link_url=""):
        """Toggle the extend link checkbox and fill the link URL."""
        logger.info("[扩展链接] 开始设置扩展链接, URL: %s", link_url)
        try:
            # 找到扩展链接的复选框（通过 form-item-external-link 定位）
            extend_link_section = page.locator('div.video-form-item.form-item-external-link')
            if not await extend_link_section.count():
                logger.warning("[扩展链接] 未找到扩展链接区域!")
                return

            # 在该区域中找到 checkbox label
            checkbox_label = extend_link_section.locator('label.byte-checkbox').first
            if not await checkbox_label.count():
                logger.warning("[扩展链接] 未找到扩展链接复选框!")
                return

            # 勾选复选框
            checkbox = checkbox_label.locator('input[type="checkbox"]')
            if await checkbox.count():
                is_checked = await checkbox.is_checked()
                if not is_checked:
                    await checkbox_label.click()
                    logger.info("[扩展链接] 已勾选扩展链接")
                    await asyncio.sleep(2)  # 等待输入框出现
                else:
                    logger.info("[扩展链接] 扩展链接已经是勾选状态")

            # 如果没有提供链接地址，直接返回
            if not link_url:
                logger.info("[扩展链接] 无链接地址，仅勾选复选框")
                return

            # 填写链接地址
            logger.info("[扩展链接] 正在寻找链接输入框...")

            # 根据用户提供的DOM，输入框在 div.video-form-item-extra 下
            link_input = page.locator('div.video-form-item-extra input[placeholder*="请填写链接地址"]')
            if not await link_input.count():
                # 尝试更宽松的选择器
                link_input = page.locator('input[placeholder*="请填写链接地址"]')
            if not await link_input.count():
                link_input = page.locator('input[placeholder*="https://www.toutiao.com"]')

            if await link_input.count():
                await link_input.fill(link_url)
                logger.info("[扩展链接] 链接地址已填写: %s", link_url)
            else:
                logger.warning("[扩展链接] 未找到链接输入框!")

        except Exception as e:
            logger.error("[扩展链接] 设置扩展链接失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set schedule time
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Set scheduled publish time."""
        logger.info("[定时发布] 开始设置定时发布时间: %s", publish_date)
        try:
            timer_btn = page.locator('button.action-footer-btn.timer:has-text("定时发布")')
            if await timer_btn.count():
                await timer_btn.click()
                await asyncio.sleep(2)
                logger.info("[定时发布] 已打开定时发布弹窗")

                # Parse the publish date
                month_day = publish_date.strftime("%m月%d日")
                hour = str(publish_date.hour)
                minute = str(publish_date.minute)
                logger.info("[定时发布] 设置日期: %s, 时间: %s:%s", month_day, hour, minute)

                # Select day
                day_select = page.locator('.day-select .byte-select-view')
                if await day_select.count():
                    await day_select.click()
                    await asyncio.sleep(1)
                    day_option = page.locator(f'.byte-select-option:has-text("{month_day}")')
                    if await day_option.count():
                        await day_option.click()
                        await asyncio.sleep(0.5)
                        logger.info("[定时发布] 日期已选择: %s", month_day)

                # Select hour
                hour_select = page.locator('.hour-select .byte-select-view')
                if await hour_select.count():
                    await hour_select.click()
                    await asyncio.sleep(1)
                    hour_option = page.locator(f'.byte-select-popup-inner .byte-select-option:has-text("{hour}")')
                    if await hour_option.count():
                        await hour_option.click()
                        await asyncio.sleep(0.5)
                        logger.info("[定时发布] 小时已选择: %s", hour)

                # Select minute
                minute_select = page.locator('.minute-select .byte-select-view')
                if await minute_select.count():
                    await minute_select.click()
                    await asyncio.sleep(1)
                minute_padded = minute.zfill(2)
                minute_option = page.locator(f'.byte-select-popup-inner .byte-select-option:has-text("{minute_padded}")')
                if await minute_option.count():
                    await minute_option.click()
                    await asyncio.sleep(0.5)
                    logger.info("[定时发布] 分钟已选择: %s", minute_padded)

                # Click the "定时发布" button in the dialog
                confirm_btn = page.locator('.byte-modal-footer button:has-text("定时发布")')
                if await confirm_btn.count():
                    await confirm_btn.click()
                    await asyncio.sleep(2)
                    logger.info("[定时发布] 定时发布设置完成")
            else:
                logger.warning("[定时发布] 未找到定时发布按钮!")
        except Exception as e:
            logger.error("[定时发布] 设置定时发布时间失败: %s", e)
