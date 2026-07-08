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
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger

logger = get_channel_logger("bilibili")

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_bilibili_profile,
)
from ..base_platform import BasePlatform

BILIBILI_UPLOAD_URL = "https://member.bilibili.com/platform/upload/video/frame"
BILIBILI_MANAGE_URL = "https://member.bilibili.com/platform/upload-manager/article"
BILIBILI_PUBLISH_STRATEGY_IMMEDIATE = "immediate"
BILIBILI_PUBLISH_STRATEGY_SCHEDULED = "scheduled"

# B 站视频上传/表单渲染的最大等待时长 —— 视频可能很大、网络可能很慢,
# 给足 4 小时(14400s),按 0.5s 轮询即 28800 次。宁可久等也不误判超时。
_UPLOAD_WAIT_SECONDS = 4 * 60 * 60  # 4 小时
_UPLOAD_WAIT_POLLS = _UPLOAD_WAIT_SECONDS * 2  # 0.5s/次 → 28800 次

# 调试开关:True = 走到提交按钮时只输出参数日志、不实际点击提交(便于检查内容);
# False = 正常点击提交。验证完发布内容无误后改回 False 即可。
_PUBLISH_DRY_RUN = False

# B 站标题禁止的字符:emoji(非 BMP 字符) + HTML 危险字符(<>\"'&)。
# 其他字符(中文、英文、数字、全角/半角标点、常见符号)全部允许。
_BILI_TITLE_FORBIDDEN_RE = re.compile(
    '[\u2600-\u27bf\ufe00-\ufe0f\u200d\u20e3\u200b-\u200f\u2028-\u202f\u2060-\u206f\ufff0-\uffff'
    '\U0001f000-\U0001faff'
    '<>"\'&]',
)


def _sanitize_title(text: str) -> str:
    """去掉 B 站标题里的 emoji 和 HTML 危险字符,其他字符保留。"""
    if not text:
        return text
    return _BILI_TITLE_FORBIDDEN_RE.sub('', text)


def _truncate_desc_by_length(text: str, max_len: int = 2000) -> str:
    """按 emoji=3 规则截断简介,确保总字符数 ≤ max_len。"""
    if not text:
        return text
    result = []
    total = 0
    for ch in text:
        cost = 3 if ord(ch) > 0xFFFF else 1
        if total + cost > max_len:
            break
        result.append(ch)
        total += cost
    return "".join(result)

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

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # B站 cookie 全部由 .bilibili.com 域下发，覆盖 account/member 子域
    platform_cookie_domain = ".bilibili.com"

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.bilibili.com)
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
            f"[bilibili] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

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
            logger.info("=" * 60)
            logger.info("[发布视频] 开始B站视频发布流程")
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
            desc = kwargs.get("desc", "")
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "")
            thumbnail_portrait = kwargs.get("thumbnail_portrait_path", "")
            schedule_time_str = kwargs.get("schedule_time_str", "")
            # ai_content 字段已废弃：B 站新版去掉了"更多设置/声明与权益"，
            # 创作声明直接在主页面设置，保留参数接收以兼容 app.py 调用
            ai_content = kwargs.get("ai_content", "")
            creation_declaration = kwargs.get("creation_declaration", "")
            # B 站合集(账号级)
            bili_collection_name = kwargs.get("bili_collection_name", "")

            # 打印发布参数摘要
            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 文件数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
            logger.info("[发布参数] 账号数量: %d", len(account_files))
            logger.info("[发布参数] 定时发布: %s", enable_timer)
            logger.info("[发布参数] 横版封面: %s", thumbnail_landscape or "无")
            logger.info("[发布参数] 创作声明: %s", creation_declaration or "无")
            logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

            # Resolve full paths
            cookie_paths = [
                str(Path(BASE_DIR / "cookiesFile") / f) for f in account_files
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
                logger.info("-" * 40)
                logger.info("[发布进度] 处理第 %d/%d 个视频: %s", index + 1, len(file_paths), file_path)
                publish_date = (
                    publish_datetimes[index]
                    if isinstance(publish_datetimes, list)
                    else publish_datetimes
                )
                for cookie_index, cookie_path in enumerate(cookie_paths):
                    cookie_name = Path(cookie_path).name
                    nick = get_account_name_by_cookie_file(cookie_name)
                    with bind_account_name(nick or "-"):
                        logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(cookie_paths), nick or "未知")
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
                            bili_collection_name=bili_collection_name,
                        )

            logger.info("=" * 60)
            logger.info("[发布视频] 视频发布流程完成!")
            logger.info("=" * 60)

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
        bili_collection_name: str = "",
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
                logger.info(f"[上传视频] 开始上传视频: {title}")
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

                # 2.5 等待页面就绪：标题输入框出现即代表表单已渲染完整。
                # 用 placeholder 定位(禁用 class)，超时 4 小时。
                logger.info("[上传视频] 等待发布表单渲染(标题输入框,最多 4 小时)...")
                title_input = page.locator('input[placeholder*="标题"]').first
                form_ready = False
                for _ in range(_UPLOAD_WAIT_POLLS):
                    if await title_input.count() > 0:
                        form_ready = True
                        break
                    await asyncio.sleep(0.5)
                if not form_ready:
                    raise TimeoutError("发布表单未渲染(标题输入框未出现,超 4 小时)")
                logger.info(
                    "[上传视频] 发布表单已渲染(标题输入框就绪)"
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

                # 9.5 Set collection (合集)
                if bili_collection_name:
                    logger.info("[设置合集] 开始设置合集: %s", bili_collection_name)
                    await self._set_collection(page, bili_collection_name)

                # 调试:输出本次发布的全部参数(便于人工核对填写是否正确)
                logger.info("=" * 60)
                logger.info("[发布调试] ===== 本次发布参数汇总 (dry_run=%s) =====", _PUBLISH_DRY_RUN)
                logger.info("[发布调试] 标题(title)       : %s", title)
                logger.info("[发布调试] 视频文件(file_path): %s", file_path)
                logger.info("[发布调试] 简介(desc)        : %s", desc[:100] if desc else "(无)")
                logger.info("[发布调试] 标签(tags)        : %s (共 %d 个)", tags, len(tags))
                logger.info("[发布调试] 分区(category)    : %s", category)
                logger.info("[发布调试] 封面(thumbnail)   : %s", thumbnail_path or "(无)")
                logger.info("[发布调试] 创作声明(creation): %s", creation_declaration or "(无)")
                logger.info("[发布调试] 定时时间(publish_date): %s", publish_date)
                logger.info("[发布调试] 发布策略(strategy): %s", publish_strategy)
                logger.info("[发布调试] 合集(collection)  : %s", bili_collection_name or "(无)")
                logger.info("[发布调试] ========================================")
                logger.info("=" * 60)

                if _PUBLISH_DRY_RUN:
                    logger.warning("[发布调试] DRY_RUN 已开启 —— 跳过实际点击提交,流程到此结束(不发布)")
                    logger.info("[发布调试] DRY_RUN: 浏览器保持打开,等待你手动关闭窗口后再结束...")
                    try:
                        while browser.is_connected():
                            await asyncio.sleep(1)
                        logger.info("[发布调试] 检测到浏览器已关闭,流程结束")
                    except Exception:
                        pass
                    return

                # 10. Submit
                logger.info("[上传视频] submitting video")
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
                            logger.info("[上传视频] clicked submit button")
                        else:
                            logger.info(
                                f"[上传视频] submit button not found, "
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
                                    "[上传视频] submit success "
                                    "(button disappeared)"
                                )
                                submitted = True
                                break
                            if (
                                page.url != BILIBILI_UPLOAD_URL
                                and "/platform/upload/" not in page.url
                            ):
                                logger.info(
                                    f"[上传视频] submit success, "
                                    f"redirected to: {page.url}"
                                )
                                submitted = True
                                break

                        if submitted:
                            break

                        logger.info(
                            f"[上传视频] page unchanged after click, "
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
                            f"[上传视频] submit retry {attempt + 1}/10: {exc}"
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
                        "[上传视频] could not confirm submission, "
                        "but it may have succeeded"
                    )

                if submitted:
                    logger.info("[上传视频] waiting 10s for processing")
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
                        logger.info("[上传视频] cookie updated")
                    except Exception:
                        pass
                await context.close()
        finally:
            await browser.close()
            logger.info("[上传视频] browser closed")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """Select the video file via iframe or direct file input."""
        logger.info("[上传视频] 正在上传视频文件...")

        file_input = None
        try:
            upload_frame = page.frame_locator('iframe[name="videoUpload"]')
            input_in_frame = upload_frame.locator('input[type="file"]')
            await input_in_frame.wait_for(state="attached", timeout=5000)
            file_input = input_in_frame
        except Exception:
            logger.info("[上传视频] upload iframe not found, trying main page")

        if file_input is None:
            file_input = page.locator(
                'input[type="file"][accept*="video"], input[type="file"]'
            ).first
            await file_input.wait_for(state="attached", timeout=10000)

        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择, 等待上传完成")

    @staticmethod
    async def _wait_upload_complete(page):
        """Wait until the video upload is fully complete.

        唯一就绪标志:必须出现「上传完成」文案(DOM 里的 <span>上传完成</span>)。
        用 get_by_text("上传完成") 定位,禁用 class/data-v 定位。
        超时 4 小时,0.5s 轮询。
        """
        logger.info("[上传视频] 等待视频上传完成(最多 4 小时)...")
        done_text = page.get_by_text("上传完成", exact=True)
        for i in range(_UPLOAD_WAIT_POLLS):
            try:
                if await done_text.count() > 0:
                    await asyncio.sleep(2)  # 等稳定
                    elapsed = i * 0.5
                    logger.info(
                        "[上传视频] 检测到「上传完成」,上传成功 (耗时 %.0f 秒)",
                        elapsed,
                    )
                    return
                # 检测上传失败
                fail_text = page.get_by_text("上传失败", exact=True)
                if await fail_text.count() > 0:
                    raise RuntimeError("视频上传失败:检测到「上传失败」文案")
                if i % 60 == 0 and i > 0:  # 每 30 秒打一次日志
                    logger.info(
                        "[上传视频] 仍在上传中... (%.0f 秒)", i * 0.5
                    )
            except RuntimeError:
                raise
            except Exception as exc:
                if i % 60 == 0 and i > 0:
                    logger.info("[上传视频] 上传状态检查: %s", exc)
            await asyncio.sleep(0.5)
        raise TimeoutError("视频上传超时(超过 4 小时):未检测到「上传完成」")

    @staticmethod
    async def _fill_title(page, title: str):
        """Fill the video title (max 80 chars, no emoji/special chars)."""
        # 先去掉 emoji 和特殊字符,再截断 80 字
        safe_title = _sanitize_title(title)[:80]
        if safe_title != title:
            logger.info("[填写标题] 标题已过滤特殊字符: %r -> %r", title, safe_title)
        logger.info("[填写标题] 开始填写标题: %s", safe_title[:30])
        title_input = page.locator(
            'input[placeholder*="标题"], input[placeholder*="Title"], '
            '.video-title input, [class*="title"] input[type="text"]'
        ).first
        await title_input.wait_for(state="visible", timeout=15000)
        await title_input.click()
        await title_input.fill("")
        await title_input.fill(safe_title)

    @staticmethod
    async def _set_category(page, category):
        """Set the video category (partition) via dropdown."""
        # 修：严格判 None（category=0 不再被早退）
        if category is None or category == '':
            return

        # Resolve Chinese name from tid OR Chinese name
        if isinstance(category, int):
            cn_name = _TID_CN_NAME.get(category, None)
        elif isinstance(category, str):
            s = category.strip()
            # 反向映射：中文名 → 找是否在 _TID_CN_NAME 里
            rev = {v: k for k, v in _TID_CN_NAME.items()}
            if s in rev:
                cn_name = s  # 直接用中文名（点击下拉按 title 即可）
            elif s.isdigit() and int(s) in _TID_CN_NAME:
                cn_name = _TID_CN_NAME[int(s)]
            else:
                cn_name = s  # 兜底：直接用原字符串（UI 显示的中文名）
        else:
            cn_name = None

        logger.info(
            f"[上传视频] setting category: category={category}, "
            f"cn_name={cn_name}"
        )

        if not cn_name:
            logger.info(
                f"[上传视频] unknown category: {category}, skipping"
            )
            return

        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            # 策略 1：按 .section-title-content-main 模糊匹配 "分区"
            title = page.locator('.section-title-content-main', has_text='分区').first
            if await title.count() == 0:
                logger.error("[设置分区] 找不到 '分区' section 标题")
                await page.screenshot(path=str(log_dir / "bili_no_partition_title.png"), full_page=True)
                return

            # 2. 沿 xpath 找到 .selector-container（分区 section 的兄弟节点）
            selector_container = title.locator(
                "xpath=ancestor::div[contains(@class,'section-title-container')][1]/following-sibling::div[contains(@class,'selector-container')][1]"
            )
            if await selector_container.count() == 0:
                # 兜底：直接父 div（兼容老 DOM）
                selector_container = title.locator("xpath=ancestor::div[2]")
                logger.warning("[设置分区] 用 ancestor::div[2] 兜底定位 selector-container")

            # 3. 在该 selector-container 内找 .select-controller
            select_controller = selector_container.locator(".select-controller").first
            await select_controller.wait_for(state="visible", timeout=10000)

            # 4. force=True 避开遮挡（CSS hover 弹层/动画都可能拦截）
            await select_controller.click(force=True)
            logger.info("[设置分区] clicked select-controller (in 分区 section, force=True)")

            # 5. 等下拉项出现（drop-list-v2-container 是 B 站下拉容器）
            try:
                await page.locator(".drop-list-v2-container").first.wait_for(
                    state="visible", timeout=5000
                )
            except Exception:
                # 兜底：可能已经开了但选择器未匹配，再点一次
                logger.warning("[设置分区] 下拉未出现，尝试再点一次")
                await select_controller.click(force=True)
                await asyncio.sleep(1)

            # 6. 按 title 属性点击目标项
            target_item = page.locator(
                f'.drop-list-v2-item[title="{cn_name}"]'
            )
            if await target_item.count() > 0:
                await target_item.first.click(force=True)
                logger.info(f"[设置分区] category set: {cn_name}")
            else:
                logger.error(
                    f"[上传视频] partition not found in dropdown: {cn_name}"
                )
                await page.screenshot(
                    path=str(log_dir / "bilibili_partition_not_found.png"),
                    full_page=True,
                )

            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(f"[设置分区] category setting failed (non-fatal): {exc}")

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

        logger.info(f"[填写标签] adding {len(tags)} tags")

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
                    logger.info(f"[填写标签] found tag input: {sel}")
                    break
            except Exception:
                continue

        if tag_input is None:
            logger.info("[填写标签] tag input not found, taking debug screenshot")
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
                    logger.info("[填写标签] tag input lost, stopping")
                    break

                await current_input.click()
                await asyncio.sleep(0.3)
                await current_input.type(str(tag), delay=50)
                await asyncio.sleep(0.3)
                await current_input.press("Enter")
                await asyncio.sleep(0.5)
                logger.info(
                    f"[上传视频] added tag ({i + 1}/{min(len(tags), 10)}): "
                    f"{tag}"
                )
            except Exception as exc:
                logger.info(f"[填写标签] failed to add tag '{tag}': {exc}")

    @staticmethod
    async def _fill_desc(page, desc: str):
        """Fill the video description (max 2000 chars, emoji=3)."""
        if not desc:
            return
        # 按 emoji=3 规则截断到 2000 字
        safe_desc = _truncate_desc_by_length(desc, 2000)
        if len(safe_desc) != len(desc):
            logger.info("[填写简介] 简介已截断(emoji=3): %d -> %d 字符", len(desc), len(safe_desc))

        logger.info("[填写简介] filling description")
        desc_editor = page.locator(
            '[contenteditable="true"][class*="editor"], '
            ".ql-editor, "
            '[class*="desc"] textarea, '
            '[class*="desc"] [contenteditable="true"]'
        ).first
        if await desc_editor.count() > 0 and await desc_editor.is_visible():
            await desc_editor.click()
            # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
            await clear_and_type(page, safe_desc, delay=10)
        else:
            logger.info("[填写简介] description editor not found")

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
            logger.info(f"[设置封面] cover file not found: {thumbnail_path}")
            return

        log_dir = Path(BASE_DIR / "logs")
        logger.info("[设置封面] 开始设置封面")

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
                    "[上传视频] all cover triggers failed, "
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
                    f"[上传视频] cover file selected: "
                    f"{os.path.basename(thumbnail_path)}"
                )
            else:
                fallback_input = page.locator(
                    'input[accept*="image"]'
                ).first
                if await fallback_input.count() > 0:
                    await fallback_input.set_input_files(thumbnail_path)
                else:
                    logger.info("[设置封面] cover file input not found")
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

            logger.info("[设置封面] cover set successfully")

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
            f"[上传视频] setting creation declaration: "
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
                        "[上传视频] creation declaration dropdown not "
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
                        f"[上传视频] selected creation declaration: "
                        f"{opt_text}"
                    )
                    clicked = True
                    break

            if not clicked:
                logger.info(
                    f"[上传视频] creation declaration option not found: "
                    f"{target_text}"
                )

            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(
                f"[上传视频] creation declaration failed (non-fatal): "
                f"{exc}"
            )

    @staticmethod
    async def _set_collection(page, collection_name: str) -> None:
        """点击「请选择合集」并选择指定合集。

        DOM 定位(禁用 data-v 随机串):
          - 入口:「请选择合集」文案(get_by_text)
          - 下拉选项:season-item-title 是组件库固定语义 class(非随机串),
            按合集名称文本匹配后点击该选项。
          - 失败不阻塞发布(合集是可选项)。
        """
        if not collection_name:
            return

        try:
            # 1. 点击「请选择合集」入口
            entry = page.get_by_text("请选择合集", exact=True)
            if await entry.count() == 0:
                logger.warning("[设置合集] 未找到「请选择合集」入口,跳过")
                return
            await entry.first.click()
            await asyncio.sleep(1.5)
            logger.info("[设置合集] 已点击「请选择合集」")

            # 2. 在下拉浮层里按合集名称匹配选项
            # season-item-title 是组件库固定语义 class(非 data-v 随机串)
            option_items = page.locator(".season-item-title")
            # 等下拉出现(最多 10s)
            ready = False
            for _ in range(20):
                if await option_items.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                logger.warning("[设置合集] 下拉浮层未出现,跳过")
                return

            count = await option_items.count()
            for i in range(count):
                name = (await option_items.nth(i).inner_text()).strip()
                if name == collection_name:
                    # 点击合集项(点 season-item-title 的父级 season-item 更稳)
                    parent = option_items.nth(i).locator("xpath=ancestor::div[contains(@class,'season-item')][1]")
                    try:
                        await parent.first.click(timeout=3000)
                    except Exception:
                        await option_items.nth(i).click()
                    logger.info("[设置合集] 已选择合集: %s", collection_name)
                    await asyncio.sleep(1)
                    return

            logger.warning("[设置合集] 未找到合集: %s", collection_name)
            # 关闭下拉
            await page.keyboard.press("Escape")
        except Exception as e:
            logger.warning("[设置合集] 合集设置失败(非致命): %s", e)

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """Set scheduled publish time via calendar and time picker."""
        from datetime import datetime

        if isinstance(publish_date, int) and publish_date == 0:
            return

        dt = publish_date
        logger.info(
            f"[上传视频] setting schedule: "
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
                    f"[上传视频] could not find clickable date: "
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

            logger.info("[定时发布] schedule time set")
        except Exception as exc:
            logger.info(f"[定时发布] schedule time setting failed: {exc}")
