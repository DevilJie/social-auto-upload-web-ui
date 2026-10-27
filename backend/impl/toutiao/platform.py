"""
今日头条平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作中心地址：https://mp.toutiao.com/profile_v4/index
视频发布地址：https://mp.toutiao.com/profile_v4/xigua/upload-video
"""

import asyncio
import base64
import json
import mimetypes
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from queue import Queue
from urllib.parse import unquote, urlparse

import requests

from util._logger import bind_account_name, get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    raise_if_page_closed,
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
                    raise_if_page_closed(page)
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
                    # 登录成功后在同一个 session 内补抓 stats(粉丝数/总阅读量/累计收益),
                    # 与 sync_profile 共用同一份抓取逻辑
                    stats_fn=self._login_stats_fn,
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

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步头条昵称、头像、运营数据(stats)。

        创作中心首页 (https://mp.toutiao.com/profile_v4/index) 有一个
        .data-board 区块,内含 3 个 .data-board-item:
          - .data-board-item-title  标题(嵌在 svg 间的文字)
          - .data-board-item-primary 主数值(<a> 文本)
          - .data-board-item-secondary 昨日变化

        3 项 stats: 粉丝数 / 总阅读(播放)量 / 累计收益
        """
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
                # 抓 name/avatar(用原有 scraper)
                name, avatar = await scrape_toutiao_profile(page)
                logger.info(
                    "[同步资料] 获取到用户信息 - 昵称: %s, 头像: %s",
                    name, avatar[:50] if avatar else "无"
                )

                # 抓 stats(3 项 .data-board-item)
                try:
                    await page.wait_for_selector(".data-board-item", timeout=8000)
                except Exception:
                    logger.info("[toutiao stats] 等待 .data-board-item 超时")

                result = await page.evaluate(
                    '''() => {
                        const out = [];
                        document.querySelectorAll('.data-board-item').forEach(item => {
                            // 标题: 嵌在 svg 里,textContent 自动剥离 svg 内容
                            const titleEl = item.querySelector('.data-board-item-title');
                            // 主数值: <a> 里的文本
                            const primaryEl = item.querySelector('.data-board-item-primary');
                            if (!titleEl || !primaryEl) return;
                            // title 可能含 svg + 真实文字 + svg(问号图标)
                            // 我们想要的是 svg 后面的真实文字(粉丝数/总阅读(播放)量/累计收益)
                            const title = (titleEl.textContent || '').trim();
                            const num = (primaryEl.textContent || '').trim();
                            if (title && num) {
                                out.push({title, num});
                            }
                        });
                        return out;
                    }'''
                )

                # label_map: 标题文 -> (ICON, SORT, 标准化 NAME)
                label_map = {
                    "粉丝数":        ("user",   1, "粉丝数"),
                    "总阅读(播放)量": ("play",   2, "总阅读(播放)量"),
                    "累计收益":       ("coin",   3, "累计收益"),
                }
                stats = []
                for item in (result or []):
                    title = item.get('title', '')
                    num_str = str(item.get('num', '0'))
                    if title in label_map:
                        icon, sort_no, std_name = label_map[title]
                        # 累计收益值形如 "0元" 或 "6,275";去掉"元"和千分位逗号
                        cleaned = num_str.replace('元', '').replace(',', '').replace(' ', '').strip()
                        try:
                            count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                        except (ValueError, TypeError):
                            count = 0
                        stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})

                if not name and not avatar and not stats:
                    logger.info(f"[toutiao] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await browser.close()

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用同一份 evaluate 抓取逻辑,
        但 login 路径下旧 scrape_toutiao_profile 已经写过 name/avatar,
        这里只抓 stats 即可。
        """
        try:
            await page.wait_for_selector(".data-board-item", timeout=8000)
        except Exception:
            logger.info("[toutiao login] 等待 .data-board-item 超时")

        result = await page.evaluate(
            '''() => {
                const out = [];
                document.querySelectorAll('.data-board-item').forEach(item => {
                    const titleEl = item.querySelector('.data-board-item-title');
                    const primaryEl = item.querySelector('.data-board-item-primary');
                    if (!titleEl || !primaryEl) return;
                    const title = (titleEl.textContent || '').trim();
                    const num = (primaryEl.textContent || '').trim();
                    if (title && num) out.push({title, num});
                });
                return out;
            }'''
        )

        label_map = {
            "粉丝数":        ("user",   1, "粉丝数"),
            "总阅读(播放)量": ("play",   2, "总阅读(播放)量"),
            "累计收益":       ("coin",   3, "累计收益"),
        }
        stats = []
        for item in (result or []):
            title = item.get('title', '')
            num_str = str(item.get('num', '0'))
            if title in label_map:
                icon, sort_no, std_name = label_map[title]
                cleaned = num_str.replace('元', '').replace(',', '').replace(' ', '').strip()
                try:
                    count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                except (ValueError, TypeError):
                    count = 0
                stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
        return stats

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
                    raise_if_page_closed(page)
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
            #    DOM 结构(用户提供的真实 DOM):
            #      <div class="m-xigua-dialog m-modal m-dialog-edit">  ← 弹窗容器
            #        <div class="mask"></div>                          ← 遮罩
            #        <div class="m-content">
            #          <svg class="close">...</svg>
            #          <div class="content">
            #            <div class="body">完成后无法继续编辑,是否确定完成？</div>
            #            <div class="footer">
            #              <button class="m-button">取消</button>
            #              <button class="m-button red">确定</button>   ← 要点这个
            #            </div>
            #          </div>
            #        </div>
            #      </div>
            #
            # 定位策略(全程不依赖 class):
            # 1) 先用 body 文字"完成后无法继续编辑"找到对话框(产品文案稳定)
            # 2) 在该对话框范围内找 footer 里第 2 个 button(第 1 个是取消,第 2 个是确定)
            #    不能用 button:has-text('确定') —— 主弹窗也含同名按钮会误匹配
            # 3) 直接用 force=True 点击(避免被遮罩层/动画拦截)
            try:
                # 用 XPath 精确定位二次确认弹窗的「确定」按钮:
                # 1) 找同时含「完成后无法继续编辑」+「取消」+「确定」的元素(会匹配祖先链)
                # 2) 排除有更深层匹配的祖先(not(.//*[...])),只留最深一层的弹窗容器
                #    避免 Playwright 把 <html>/<body> 当匹配导致点中遮罩层
                # 3) 在该容器内定位同时含「取消」「确定」的 footer 的确定按钮
                #    (主弹窗只有「确定」无「取消」,不会误匹配)
                cond = (
                    ".//*[contains(normalize-space(.), '完成后无法继续编辑')] "
                    "and .//button[normalize-space()='取消'] "
                    "and .//button[normalize-space()='确定']"
                )
                dialog_ok_btn = page.locator(
                    f"xpath=//*[{cond} and not(.//*[{cond}])]"
                    "//div[button[normalize-space()='取消'] "
                    "and button[normalize-space()='确定']]"
                    "//button[normalize-space()='确定']"
                ).first
                if await dialog_ok_btn.count() > 0:
                    try:
                        await dialog_ok_btn.wait_for(state="visible", timeout=5000)
                    except Exception:
                        # 弹窗动画中可能 is_visible=False,继续 force click
                        pass
                    await dialog_ok_btn.click(force=True, timeout=5000)
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

    # ==================================================================
    # 文章(图文)发布 — 2026-10 侦察 + 2026-10-23 设置完整性复审
    #   编辑器: https://mp.toutiao.com/profile_v4/graphic/publish
    #   标题: textarea[placeholder*="请输入文章标题"](2~30 字)
    #   正文: .ProseMirror contenteditable, 粘贴 text/html 生效
    #         (h2 会被规范成 h1, strong/em/ul/blockquote 保留)
    #   正文图片: 工具栏图片按钮 → 右侧抽屉「上传图片」→「本地上传」
    #         → POST /spice/image 返回图床 image_url; 粘贴 HTML 时编辑器
    #         自动把该 URL 转存为平台图片节点(页面加载成功 = 已转存)
    #   「发文设置」区全量(2026-10-23 实测, 顺序):
    #     展示封面: radio 单图/三图/无封面(必填); 三图=正文前 3 图自动填充;
    #         单图=正文首图自动或「替换」上传; 无封面仍可定时/发表
    #     添加位置: .position-select 可搜索城市下拉(平台内置城市列表)
    #     投放广告: radio 投放广告赚收益(默认)/不投放广告(自定义 radio,
    #         选中态看 .byte-radio-inner.checked, input.checked 不可信);
    #         选「不投放广告」会弹二次确认框, 必须点「确定」否则遮罩留存
    #     声明首发: 头条首发 checkbox(平台记忆上次状态, 需双向同步) +
    #         授权平台自动维权 checkbox(仅首发勾选时显示)
    #     合集: 「添加至合集」按钮 → 添加合集弹窗(列表为空时提示暂无合集)
    #     同时发布微头条: 「发布得更多收益」checkbox —— 禁用状态不稳定
    #         (平台按账号/内容状态锁定), 与头条首发无稳定联动
    #     作品声明: 7 项 checkbox 外观, 平台按单选处理
    #         (勾选新项会自动取消旧项, 2026-10-23 复测确认)
    #   定时: 「定时发布」弹窗(day/hour/minute 三个 byte-select):
    #         当前时间后 2 小时 ~ 7 天; 无封面时同样可用
    #   存草稿: 编辑器自动保存 POST /mp/agw/article/publish (source=29)
    #   发表: 底部「预览并发布」→ 预览 overlay → 「发布」
    #         → POST /mp/agw/article/publish, code==0 即成功
    # ==================================================================

    _ARTICLE_EDITOR_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
    _ARTICLE_TITLE_MAX = 30
    _ARTICLE_IMAGE_MAX_BYTES = 20 * 1024 * 1024
    _ARTICLE_SCHEDULE_MIN_HOURS = 2
    _ARTICLE_SCHEDULE_MAX_DAYS = 7
    # 作品声明选项(2026-10 编辑器「作品声明」区实测)
    _ARTICLE_DECLARATION_OPTIONS = (
        "取材网络", "引用站内", "个人观点，仅供参考", "引用AI",
        "虚构演绎，故事经历", "投资观点，仅供参考",
        "健康医疗分享，仅供参考",
    )

    def publish_article(self, **kwargs) -> bool:
        """发布文章到今日头条(同步入口)。

        kwargs:
            title (*str*) -- 文章标题(2~30 字,超长截断)
            html (*str*) -- 正文 HTML(img src 为本地素材 URL,自动上传
                头条图床后替换)
            account_file (*list[str]*) -- cookie 文件名列表(取第一个)
            cover_path (*str*, optional) -- 显式封面本地路径(无则: 正文有图
                自动取首图单图封面,无图选「无封面」)
            is_draft (*bool*) -- True(默认)= 只存草稿(编辑器自动保存);
                False = 真实发表
            dry_run (*bool*) -- True = 强制 is_draft=True,只做完整表单 +
                截图 + 草稿,绝不发表
            schedule_time_str (*str*, optional) -- 定时发表(仅直接发表模式
                生效,当前时间后 2 小时 ~ 7 天)
            creation_statement (*str*) -- 作品声明(逗号分隔多项):
                取材网络/引用站内/个人观点，仅供参考/引用AI/
                虚构演绎，故事经历/投资观点，仅供参考/健康医疗分享，仅供参考
            creation_declaration (*str|list*) -- 同 creation_statement
                (兼容视频参数名)
            first_publish (*bool*) -- 勾选「头条首发」(正文需 ≥100 字,
                不满足时平台会拦下并 toast,此处降级为 warning 跳过)
            ad_revenue (*bool*, optional) -- True=投放广告赚收益(平台默认)
                False=不投放广告; None=不改动平台默认
            publish_micro_headline (*bool*, optional) -- 同时发布微头条
                「发布得更多收益」; None=不改动平台默认
            auto_rights (*bool*, optional) -- 授权平台自动维权(仅「头条首发」
                勾选时平台才显示该开关); None=不改动
            location (*str*, optional) -- 添加位置(城市名, 如「北京」),
                仅限平台城市列表内名称; 空=不设置
            collection_name (*str*, optional) -- 添加至合集(合集名称, 需已存在);
                空=不设置
            cover_mode (*str*) -- 单图(默认)/三图/无封面; 三图由平台按正文
                前 3 张图自动填充, 正文不足 3 张时降级单图
        """
        allowed_keys = (
            "title", "html", "account_file", "cover_path",
            "is_draft", "dry_run", "schedule_time_str",
            "creation_statement", "creation_declaration",
            "first_publish", "ad_revenue", "publish_micro_headline",
            "auto_rights", "location", "collection_name",
            "cover_mode", "source_declaration",
        )
        filtered = {k: kwargs[k] for k in allowed_keys if k in kwargs}
        # dry-run 安全默认: 一定停在发表前(只存草稿)
        if filtered.get("dry_run", False):
            filtered["is_draft"] = True
        asyncio.run(self._publish_article_one(**filtered))
        return True

    async def _publish_article_one(
        self,
        title: str,
        html: str,
        account_file,
        cover_path: str = "",
        is_draft: bool = True,
        dry_run: bool = False,
        schedule_time_str: str = "",
        creation_statement="",
        creation_declaration=None,
        first_publish=False,
        ad_revenue=None,
        publish_micro_headline=None,
        auto_rights=None,
        location: str = "",
        collection_name: str = "",
        cover_mode: str = "单图",
        source_declaration=False,
    ):
        """单账号图文发布完整流程(今日头条)。"""
        from datetime import datetime as _dt

        from services.article_html import (
            extract_img_srcs,
            replace_img_srcs,
            sanitize_article_html,
        )

        title = (title or "").strip()
        if not title:
            raise RuntimeError("[文章][头条] 标题不能为空")
        if len(title) > self._ARTICLE_TITLE_MAX:
            logger.warning(
                "[文章][头条] 标题超长(%d>%d 字),已截断",
                len(title), self._ARTICLE_TITLE_MAX,
            )
            title = title[: self._ARTICLE_TITLE_MAX]
        if not (html or "").strip():
            raise RuntimeError("[文章][头条] 正文不能为空")

        if isinstance(account_file, (list, tuple)):
            cookie_name = account_file[0] if account_file else ""
        else:
            cookie_name = account_file or ""
        if not cookie_name:
            raise RuntimeError("[文章][头条] 缺少账号 cookie 配置")
        cookie_path = str(Path(BASE_DIR / "cookiesFile") / cookie_name)

        declarations = self._parse_declarations(
            creation_declaration if creation_declaration else creation_statement
        )
        first_publish = self._as_bool(first_publish)
        ad_revenue = (
            None if ad_revenue in (None, "")
            else self._as_bool(ad_revenue)
        )
        publish_micro_headline = (
            None if publish_micro_headline in (None, "")
            else self._as_bool(publish_micro_headline)
        )
        auto_rights = (
            None if auto_rights in (None, "")
            else self._as_bool(auto_rights)
        )
        location = (location or "").strip()
        collection_name = (collection_name or "").strip()
        cover_mode = (cover_mode or "单图").strip()
        if self._as_bool(source_declaration) and declarations:
            logger.info("[文章][头条] source_declaration 对头条无对应项,忽略")

        logger.info("=" * 60)
        logger.info("[文章][头条] 开始文章发布")
        logger.info("[文章][头条] 标题: %s", title)
        logger.info("[文章][头条] 正文 HTML 长度: %d", len(html))
        logger.info(
            "[文章][头条] 模式: %s%s",
            "草稿(不发表)" if is_draft else "真实发表",
            "(dry-run)" if dry_run else "",
        )
        logger.info(
            "[文章][头条] 设置: 声明=%s 首发=%s 投放广告=%s 微头条=%s "
            "自动维权=%s 位置=%s 合集=%s 封面模式=%s 定时=%s",
            declarations or "无", first_publish,
            "默认" if ad_revenue is None else ad_revenue,
            "默认" if publish_micro_headline is None
            else publish_micro_headline,
            "默认" if auto_rights is None else auto_rights,
            location or "无", collection_name or "无",
            cover_mode, schedule_time_str or "无",
        )

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser, storage_state=cookie_path
            )
            try:
                page = await context.new_page()

                # 网络响应采集: 图片上传 / 草稿自动保存 / 发表接口
                store = {
                    "uploads": [], "draft_saves": [], "publishes": [],
                    "publish_errors": [], "agw_posts": [],
                }

                async def _on_response(response):
                    try:
                        url = response.url
                        is_upload = "/spice/image" in url
                        is_agw = "/mp/agw/" in url
                        if not (is_upload or is_agw):
                            return
                        ctype = response.headers.get("content-type") or ""
                        if (os.environ.get("TOUTIAO_DEBUG_NET")
                                and ("/mp/agw/article/publish" in url
                                     or "/publish" in url)):
                            logger.info(
                                "[net] resp status=%s ctype=%s url=%s",
                                response.status, ctype, url[:260],
                            )
                        if "json" not in ctype:
                            return
                        # 头条接口响应可能是 UTF-8 或 GBK,直接读 body 自行
                        # 解码(Playwright 的 response.json() 对 GBK 会乱码,
                        # 导致 message 无法用于区分保存/发表)
                        data = None
                        try:
                            raw = await response.body()
                            if raw:
                                for enc in ("utf-8", "gbk"):
                                    try:
                                        data = json.loads(raw.decode(enc))
                                        break
                                    except Exception:
                                        data = None
                        except Exception:
                            data = None
                        if data is None:
                            try:
                                data = await response.json()
                            except Exception:
                                return
                        req_post = ""
                        try:
                            req_post = response.request.post_data or ""
                        except Exception:
                            pass
                        if is_upload:
                            store["uploads"].append(data)
                            return
                        try:
                            method = response.request.method
                        except Exception:
                            method = ""
                        if method != "POST":
                            return
                        code = data.get("code", data.get("err_no"))
                        message = str(
                            data.get("message")
                            or data.get("reason")
                            or data.get("err_tips")
                            or ""
                        )
                        post_preview = (req_post or "")[:80]
                        store["agw_posts"].append(
                            (code, url[:200], post_preview)
                        )
                        if (os.environ.get("TOUTIAO_DEBUG_NET")
                                and "/mp/agw/article/publish" in url):
                            logger.info(
                                "[net] resp publish code=%s message=%s data=%s",
                                code, message,
                                json.dumps(
                                    data, ensure_ascii=False
                                )[:900],
                            )
                        item = {
                            "data": data, "post": req_post,
                            "status": response.status, "url": url,
                            "message": message,
                        }
                        # 头条文章保存/发表共用同一接口,靠响应 message 区分:
                        #   "保存成功"(自动存草稿) vs "发布成功"(真实发表)
                        if ("/mp/agw/article/publish" in url
                                and code in (0, "0")):
                            if "发布成功" in message or (
                                "发布" in message and "保存" not in message
                            ):
                                store["publishes"].append(item)
                            else:
                                store["draft_saves"].append(data)
                            return
                        # 其他 agw POST: 兜底按响应数据识别发表类结果
                        inner = data.get("data")
                        if not isinstance(inner, dict):
                            inner = {}
                        has_publish_payload = (
                            any(k in inner for k in (
                                "article_url", "group_id",
                            ))
                            or ("pgc_id" in inner and not inner.get("content"))
                        )
                        if code in (0, "0") and has_publish_payload:
                            store["publishes"].append(item)
                        elif code not in (0, "0") and any(
                            k in url for k in ("publish", "submit", "article")
                        ):
                            store["publish_errors"].append(item)
                    except Exception:
                        pass

                # context 级网络监听: 预览页「确认发布」可能由弹窗/子页面
                # 发起请求,仅监听 page 会漏掉,必须挂到 context 上。
                try:
                    context.on(
                        "response",
                        lambda r: asyncio.ensure_future(_on_response(r)),
                    )
                except Exception:
                    page.on(
                        "response",
                        lambda r: asyncio.ensure_future(_on_response(r)),
                    )

                await page.goto(
                    self._ARTICLE_EDITOR_URL,
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await self._wait_article_editor_ready(page)

                # 1. 标题
                await self._fill_article_title(page, title)

                # 2. 正文图片 → 头条图床 → 替换 HTML 中的 src
                clean_html = sanitize_article_html(html)
                srcs = extract_img_srcs(clean_html)
                if srcs:
                    logger.info(
                        "[文章][头条] 正文含 %d 张图片,开始上传图床...",
                        len(srcs),
                    )
                    local_paths = [
                        self._resolve_image_local_path(src) for src in srcs
                    ]
                    cdn_urls = await self._upload_article_images(
                        page, local_paths, store
                    )
                    clean_html = replace_img_srcs(
                        clean_html, dict(zip(srcs, cdn_urls))
                    )
                    logger.info(
                        "[文章][头条] 图片已全部上传图床,HTML 中 src 已替换"
                    )
                else:
                    logger.info("[文章][头条] 正文无图片,跳过图片上传")

                # 3. 粘贴正文 HTML(图片由编辑器服务端转存为平台图片节点)
                await self._paste_article_html(page, clean_html)
                if srcs:
                    await self._wait_pasted_images(page, len(srcs))

                # 4. 封面(必填项: 单图/三图/无封面; 三图按正文前 3 图自动填充)
                applied_cover_mode = "单图"
                try:
                    applied_cover_mode = await self._setup_article_cover(
                        page, cover_path, cover_mode, srcs, store
                    )
                except Exception as e:
                    logger.warning(
                        "[文章][头条] 封面设置失败(跳过): %s", e
                    )

                # 5. 作品声明(平台为单选; 多值取最后一项生效)
                if declarations:
                    try:
                        await self._set_article_declarations(
                            page, declarations
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 作品声明设置失败(跳过): %s", e
                        )

                # 6. 头条首发(平台默认会记忆上次状态, 两个方向都主动同步)
                try:
                    await self._set_article_first_publish(
                        page, bool(first_publish)
                    )
                except Exception as e:
                    logger.warning(
                        "[文章][头条] 头条首发设置失败(跳过): %s", e
                    )

                # 6.5 授权平台自动维权(仅首发勾选时平台才显示)
                if auto_rights is not None:
                    try:
                        await self._set_article_auto_rights(
                            page, bool(auto_rights),
                            first_publish=bool(first_publish),
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 自动维权设置失败(跳过): %s", e
                        )

                # 7. 投放广告(可选)
                if ad_revenue is not None:
                    try:
                        await self._set_article_ad_revenue(
                            page, ad_revenue
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 投放广告设置失败(跳过): %s", e
                        )

                # 8. 同时发布微头条(可选)
                if publish_micro_headline is not None:
                    try:
                        await self._set_article_micro_headline(
                            page, publish_micro_headline
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 微头条开关设置失败(跳过): %s", e
                        )

                # 8.2 添加位置(可选, 城市名)
                if location:
                    try:
                        await self._set_article_location(page, location)
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 添加位置失败(跳过): %s", e
                        )

                # 8.4 添加至合集(可选, 合集名称)
                if collection_name:
                    try:
                        await self._set_article_collection(
                            page, collection_name
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 添加合集失败(跳过): %s", e
                        )

                # 9. 定时发布(可选,仅直接发表模式; 失败则立即发表)
                scheduled = False
                if not is_draft and schedule_time_str:
                    try:
                        await self._set_article_schedule(
                            page, schedule_time_str
                        )
                        scheduled = True
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 定时设置失败(将立即发表): %s", e
                        )

                # 9.9 提交前弹窗清场(广告二次确认弹窗可能延迟出现)
                await self._settle_article_modals(
                    page, wait_late_ad=(ad_revenue is False))

                # 10. 提交前状态日志 + 截图
                await self._log_article_form_state(page, applied_cover_mode)
                await self._article_screenshot(
                    page, "toutiao_article_before_submit.png"
                )

                # 11. 草稿 / 发表
                if is_draft:
                    pgc_id = await self._wait_draft_saved(page, store)
                    # dry-run 额外验证: 打开「预览」确认表单可提交后关闭
                    try:
                        await self._open_article_preview(page)
                        await self._article_screenshot(
                            page, "toutiao_article_dryrun_preview.png"
                        )
                        await self._close_article_preview(page)
                        logger.info(
                            "[文章][头条] dry-run: 预览校验通过,已关闭预览"
                            "(未发表)"
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][头条] 预览校验未通过(草稿已保存,"
                            "不影响): %s", e,
                        )
                    await self._article_screenshot(
                        page, "toutiao_article_before_submit.png"
                    )
                    logger.info(
                        "[文章][头条] ✓ 草稿模式完成(草稿已自动保存,"
                        "pgc_id=%s,未发表)", pgc_id or "未知",
                    )
                else:
                    result = await self._click_article_publish(
                        page, store, scheduled=scheduled, title=title
                    )
                    logger.info(
                        "[文章][头条] ✓ 文章发表成功 pgc_id=%s",
                        result.get("pgc_id") or "未知",
                    )
                    await self._article_screenshot(
                        page, "toutiao_article_published.png"
                    )

                # 保存 cookie
                try:
                    await context.storage_state(path=cookie_path)
                    logger.info("[文章][头条] Cookie 状态已更新")
                except Exception as e:
                    logger.warning("[文章][头条] Cookie 保存失败: %s", e)

                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)
        logger.info("=" * 60)

    # ---------------------- 文章内部辅助方法 ----------------------

    @staticmethod
    def _as_bool(value) -> bool:
        """把前端可能传来的 bool/str/int 统一成 bool。"""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "是")
        return bool(value)

    @classmethod
    def _parse_declarations(cls, value) -> list:
        """作品声明: 支持 str(逗号/顿号/换行分隔) 或 list(逐项原样)。"""
        if not value:
            return []
        if isinstance(value, (list, tuple, set)):
            out = []
            for item in value:
                text = str(item or "").strip()
                if text and text not in out:
                    out.append(text)
            return out
        if isinstance(value, str):
            parts = re.split(r"[,，、;；\n]+", value)
            out = []
            for part in parts:
                part = part.strip()
                if part and part not in out:
                    out.append(part)
            return out
        return []

    @staticmethod
    async def _article_screenshot(page, filename: str) -> str:
        """文章流程截图(失败不影响流程)。"""
        try:
            shot_dir = Path(BASE_DIR) / "screenshots"
            shot_dir.mkdir(parents=True, exist_ok=True)
            path = shot_dir / filename
            await page.screenshot(path=str(path), full_page=True)
            logger.info("[文章][头条] 截图已保存: %s", path)
            return str(path)
        except Exception as e:
            logger.warning("[文章][头条] 截图失败(%s): %s", filename, e)
            return ""

    # ---------- 编辑器就绪 / 标题 / 通用关闭 ----------

    @staticmethod
    async def _wait_article_editor_ready(page, timeout_s: int = 60):
        """等图文编辑器就绪: 标题 textarea + 正文 ProseMirror。"""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            url = page.url or ""
            if "sso.toutiao.com" in url or "/login" in url:
                raise RuntimeError(
                    "[文章][头条] cookie 已失效(被重定向到登录页),"
                    "请重新登录账号"
                )
            ready = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const ta = document.querySelector(
                    'textarea[placeholder*="请输入文章标题"]');
                  const ed = document.querySelector('.ProseMirror');
                  return {ta: !!ta && vis(ta), ed: !!ed};
                }"""
            )
            if ready.get("ta") and ready.get("ed"):
                logger.info("[文章][头条] 图文编辑器已就绪")
                await ToutiaoPlatform._dismiss_article_guides(page)
                return
            await asyncio.sleep(1)
        raise RuntimeError(
            "[文章][头条] 图文编辑器加载超时(可能 cookie 失效)"
        )

    @staticmethod
    async def _dismiss_article_guides(page):
        """关闭页面引导气泡(「我知道了」等),避免遮挡底部设置区。"""
        for _ in range(3):
            try:
                clicked = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      for (const b of [...document.querySelectorAll(
                          'button, [role="button"]')].filter(vis)) {
                        const t = (b.innerText || '').trim();
                        if (t === '我知道了' || t === '知道了') {
                          b.click();
                          return t;
                        }
                      }
                      return null;
                    }"""
                )
            except Exception:
                return
            if not clicked:
                return
            logger.info("[文章][头条] 已关闭页面引导: %s", clicked)
            await asyncio.sleep(1)

    @staticmethod
    async def _fill_article_title(page, title: str):
        """标题: textarea[placeholder*="请输入文章标题"],2~30 字。"""
        box = page.locator(
            'textarea[placeholder*="请输入文章标题"]'
        ).first
        await box.wait_for(state="visible", timeout=20000)
        await box.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await box.fill(title)
        await asyncio.sleep(0.8)
        actual = (await box.input_value() or "").strip()
        if not actual:
            raise RuntimeError("[文章][头条] 标题填写失败")
        logger.info("[文章][头条] 标题已填写: %s(%d 字)", actual, len(actual))

    # ---------- 正文图片上传 ----------

    @staticmethod
    async def _open_image_drawer(page):
        """点正文工具栏「图片」按钮,打开右侧图片抽屉。

        定位: 工具栏按钮无文案,用 svg 特征(translate(3.7 5) 的图片框)
        定位 —— 跳过表格按钮(clip-rule 路径)。
        """
        pos = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const btns = [...document.querySelectorAll(
                '.syl-toolbar .syl-toolbar-button')].filter(vis);
              for (const b of btns) {
                const h = b.innerHTML;
                if (h.includes('translate(3.7 5)')
                    && !h.includes('clip-rule')) {
                  b.scrollIntoView({block: 'center'});
                  const r = b.getBoundingClientRect();
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }
              }
              return null;
            }"""
        )
        if not pos:
            raise RuntimeError("[文章][头条] 未找到正文图片工具栏按钮")
        await page.mouse.click(pos["x"], pos["y"])
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 25
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            opened = await page.evaluate(
                """() => [...document.querySelectorAll('.byte-drawer')]
                  .some((e) => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  })"""
            )
            if opened:
                logger.info("[文章][头条] 正文图片抽屉已打开")
                return
            await asyncio.sleep(1)
        raise RuntimeError("[文章][头条] 正文图片抽屉未打开")

    @staticmethod
    async def _click_drawer_text_button(page, text: str) -> bool:
        """点抽屉内的按钮(按文案,如「本地上传」「确定」)。"""
        return await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const drawer = [...document.querySelectorAll('.byte-drawer')]
                .filter(vis)[0];
              if (!drawer) return false;
              for (const b of [...drawer.querySelectorAll('button')]
                  .filter(vis)) {
                if ((b.innerText || '').trim() === text && !b.disabled) {
                  b.click();
                  return true;
                }
              }
              return false;
            }""",
            text,
        )

    @staticmethod
    async def _click_drawer_tab(page, text: str) -> bool:
        """点抽屉顶部 tab(如「上传图片」)。"""
        return await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const drawer = [...document.querySelectorAll('.byte-drawer')]
                .filter(vis)[0];
              if (!drawer) return false;
              for (const t of [...drawer.querySelectorAll(
                  '[class*="tabs-header-title"]')].filter(vis)) {
                if ((t.innerText || '').trim() === text) {
                  t.click();
                  return true;
                }
              }
              return false;
            }""",
            text,
        )

    @staticmethod
    async def _close_image_drawer(page):
        """关闭图片抽屉(点右上角关闭图标,兜底 Escape)。"""
        try:
            closed = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const icon = [...document.querySelectorAll(
                    '.byte-drawer-close-icon')].filter(vis)[0];
                  if (icon) { icon.click(); return true; }
                  const drawer = [...document.querySelectorAll(
                    '.byte-drawer')].filter(vis)[0];
                  if (!drawer) return true;
                  for (const b of [...drawer.querySelectorAll('button')]
                      .filter(vis)) {
                    if ((b.innerText || '').trim() === '取消') {
                      b.click(); return true;
                    }
                  }
                  return false;
                }"""
            )
            if not closed:
                await page.keyboard.press("Escape")
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.info("[文章][头条] 关闭图片抽屉失败: %s", e)

    async def _upload_article_images(self, page, local_paths, store):
        """逐张上传正文图片到头条图床,返回图床 URL 列表(顺序一致)。

        通道: 工具栏图片按钮 → 抽屉「上传图片」→「本地上传」→
        set_input_files → 等 POST /spice/image 响应 image_url。
        全部传完后关闭抽屉(不插入编辑器,后续统一粘贴 HTML)。
        """
        urls = []
        # 工具栏图片按钮需要正文编辑器处于聚焦状态(有光标)才响应
        try:
            editor = page.locator('.ProseMirror').first
            await editor.click(timeout=10000)
            await asyncio.sleep(1)
        except Exception as e:
            logger.warning("[文章][头条] 聚焦正文编辑器失败: %s", e)
        await self._open_image_drawer(page)
        try:
            # 确保在「上传图片」tab
            await self._click_drawer_tab(page, "上传图片")
            await asyncio.sleep(1.2)
            loop = asyncio.get_event_loop()
            for i, path in enumerate(local_paths):
                name = Path(path).name
                try:
                    size = os.path.getsize(path)
                except OSError:
                    raise RuntimeError(f"[文章][头条] 正文图片不存在: {path}")
                if size > self._ARTICLE_IMAGE_MAX_BYTES:
                    raise RuntimeError(
                        f"[文章][头条] 图片超过 20MB 限制: {name}"
                    )
                before = len(store["uploads"])
                clicked = await self._click_drawer_text_button(
                    page, "本地上传"
                )
                if not clicked:
                    raise RuntimeError(
                        "[文章][头条] 未找到「本地上传」按钮"
                    )
                await asyncio.sleep(1.5)
                finp = page.locator(
                    '.byte-drawer input[type=file]'
                ).first
                await finp.wait_for(state="attached", timeout=15000)
                raise_if_page_closed(page, action="文章发布")
                await finp.set_input_files(path)
                # 等这一张的上传响应
                deadline = loop.time() + 90
                while loop.time() < deadline:
                    raise_if_page_closed(page, action="文章发布")
                    if len(store["uploads"]) > before:
                        break
                    await asyncio.sleep(1)
                if len(store["uploads"]) <= before:
                    raise RuntimeError(
                        f"[文章][头条] 图片上传超时: {name}"
                    )
                data = store["uploads"][-1]
                code = data.get("code")
                if code not in (0, "0"):
                    raise RuntimeError(
                        f"[文章][头条] 图片上传失败({name}) code={code} "
                        f"message={data.get('message')}"
                    )
                url = ((data.get("data") or {}).get("image_url") or "")
                url = url.strip()
                if not url.startswith("http"):
                    raise RuntimeError(
                        f"[文章][头条] 图片上传未返回 image_url: {name}"
                    )
                urls.append(url)
                logger.info(
                    "[文章][头条] 图片 %d/%d 已上传图床: %s",
                    i + 1, len(local_paths), url[:100],
                )
                await asyncio.sleep(1)
        finally:
            await self._close_image_drawer(page)
        return urls

    # ---------- 正文粘贴 ----------

    @staticmethod
    async def _paste_article_html(page, html: str):
        """把完整 HTML 粘贴进 ProseMirror 正文编辑器。

        剪贴板 DataTransfer + ClipboardEvent('paste') 触发编辑器原生
        paste 处理(h 标签/列表/引用/加粗/图片卡片均按平台规则重建)。
        """
        length = await page.evaluate(
            """(html) => {
              const ed = document.querySelector('.ProseMirror');
              if (!ed) return 0;
              ed.focus();
              const dt = new DataTransfer();
              dt.setData('text/html', html);
              dt.setData('text/plain', html.replace(/<[^>]+>/g, ' '));
              ed.dispatchEvent(new ClipboardEvent('paste', {
                bubbles: true, cancelable: true, clipboardData: dt,
              }));
              return ed.innerHTML.length;
            }""",
            html,
        )
        if not length or length < 10:
            raise RuntimeError(
                f"[文章][头条] 正文粘贴后内容过短(length={length})"
            )
        await asyncio.sleep(4)
        logger.info("[文章][头条] 正文已粘贴(innerHTML %d 字符)", length)

    @staticmethod
    async def _wait_pasted_images(page, expected: int, timeout_s: int = 150):
        """等正文图片节点在编辑器内加载完成(平台服务端转存).

        成功: img-loading-container.success 数量 >= expected;
        失败: 出现 .image-error(图片粘贴失败)。
        """
        if expected <= 0:
            return
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        last = {}
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            state = await page.evaluate(
                """() => {
                  const ed = document.querySelector('.ProseMirror');
                  if (!ed) return {total: 0, done: 0, error: 0};
                  return {
                    total: ed.querySelectorAll('[__syl_tag]').length,
                    done: ed.querySelectorAll(
                      '.img-loading-container.success').length,
                    error: ed.querySelectorAll('.image-error').length,
                  };
                }"""
            )
            last = state
            if state.get("error", 0) > 0:
                raise RuntimeError(
                    "[文章][头条] 正文图片粘贴失败(编辑器图片节点报错)"
                )
            if state.get("done", 0) >= expected:
                logger.info(
                    "[文章][头条] 正文图片已全部就绪(%d/%d)",
                    state.get("done"), expected,
                )
                return
            await asyncio.sleep(2)
        logger.warning(
            "[文章][头条] 正文图片就绪确认超时(期望 %d,实际 %s)",
            expected, last,
        )

    # ---------- 封面 ----------

    @staticmethod
    async def _set_article_cover_mode(page, mode: str):
        """切换封面模式(单图/三图/无封面), 真实鼠标点击 label。

        2026-10 实测: byte-design 自定义 radio 对 JS 合成 click 不生效,
        必须用 Playwright locator 真实点击 label; 点完校验
        `.byte-radio-inner.checked` 是否落在目标项上。
        """
        mode = (mode or "").strip()
        if mode not in ("单图", "三图", "无封面"):
            raise RuntimeError(f"[文章][头条] 未知封面模式「{mode}」")
        label = page.locator(
            '.article-cover-radio-group label.byte-radio', has_text=mode
        ).first
        await label.scroll_into_view_if_needed(timeout=8000)
        await label.click(timeout=8000)
        await asyncio.sleep(1.2)
        checked = await page.evaluate(
            """() => {
              const lb = [...document.querySelectorAll(
                '.article-cover-radio-group label.byte-radio')]
                .find((el) => !!el.querySelector(
                  '.byte-radio-inner.checked'));
              return lb ? (lb.innerText || '').trim() : '';
            }"""
        )
        if (checked or "").strip() != mode:
            raise RuntimeError(
                f"[文章][头条] 封面模式切换未生效(期望 {mode}, 实际 "
                f"{checked or '未选中'})"
            )
        logger.info("[文章][头条] 封面模式已切换: %s", mode)
        return mode

    @staticmethod
    async def _count_article_cover_slots(page) -> int:
        """三图模式下统计已填充的封面槽数量(正文图自动填充)。"""
        return int(await page.evaluate(
            """() => [...document.querySelectorAll(
              '.article-cover-images img')].filter((im) =>
              (im.src || '').startsWith('http')).length"""
        ) or 0)

    @staticmethod
    async def _set_article_cover_none(page):
        """选择「无封面」(单图/三图/无封面 之一, radio value=1)。"""
        await ToutiaoPlatform._set_article_cover_mode(page, "无封面")
        logger.info("[文章][头条] 封面已选择「无封面」")

    @staticmethod
    async def _wait_article_cover_ready(page, timeout_s: int = 25) -> bool:
        """等封面图出现(正文有图时平台自动取首图作单图封面)。"""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            ok = await page.evaluate(
                """() => {
                  const img = document.querySelector(
                    '.article-cover-img-wrap img');
                  if (!img) return false;
                  return !!(img.src || '').startsWith('http');
                }"""
            )
            if ok:
                return True
            await asyncio.sleep(1)
        return False

    async def _set_article_custom_cover(self, page, cover_path, store):
        """指定 cover_path 时: 「替换/添加封面」→ 抽屉上传 → 确定。"""
        # 1. 打开封面抽屉(无自动封面时点「+」,已有自动封面时点「替换」)
        entry = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const rep = document.querySelector(
                '.article-cover-img-replace');
              if (rep) { rep.click(); return 'replace'; }
              const add = document.querySelector('.article-cover-add');
              if (add) { add.click(); return 'add'; }
              return null;
            }"""
        )
        if not entry:
            raise RuntimeError("未找到封面设置入口(+ / 替换)")
        logger.info("[文章][头条] 已打开封面抽屉(%s)", entry)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 20
        opened = False
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            opened = await page.evaluate(
                """() => [...document.querySelectorAll('.byte-drawer')]
                  .some((e) => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  })"""
            )
            if opened:
                break
            await asyncio.sleep(1)
        if not opened:
            raise RuntimeError("封面抽屉未打开")
        try:
            # 2. 切到「上传图片」tab
            await self._click_drawer_tab(page, "上传图片")
            await asyncio.sleep(1.5)
            # 3. 本地上传
            clicked = await self._click_drawer_text_button(
                page, "本地上传"
            )
            if not clicked:
                raise RuntimeError("封面抽屉未找到「本地上传」")
            await asyncio.sleep(1.5)
            before = len(store["uploads"])
            finp = page.locator('.byte-drawer input[type=file]').first
            await finp.wait_for(state="attached", timeout=15000)
            await finp.set_input_files(cover_path)
            deadline = loop.time() + 90
            while loop.time() < deadline:
                raise_if_page_closed(page, action="文章发布")
                if len(store["uploads"]) > before:
                    break
                await asyncio.sleep(1)
            if len(store["uploads"]) <= before:
                raise RuntimeError("封面上传超时")
            data = store["uploads"][-1]
            if data.get("code") not in (0, "0"):
                raise RuntimeError(
                    f"封面上传失败 code={data.get('code')} "
                    f"message={data.get('message')}"
                )
            await asyncio.sleep(2)
            # 4. 点上传后的缩略图选中(先取消选中,确保选最新一张)
            picked = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const drawer = [...document.querySelectorAll(
                    '.byte-drawer')].filter(vis)[0];
                  if (!drawer) return false;
                  const imgs = [...drawer.querySelectorAll('img')]
                    .filter((im) => im.getBoundingClientRect().width > 60);
                  if (!imgs.length) return false;
                  imgs[imgs.length - 1].click();
                  return true;
                }"""
            )
            if not picked:
                logger.warning(
                    "[文章][头条] 封面上传后未找到缩略图,尝试直接确定"
                )
            await asyncio.sleep(1.5)
            # 5. 确定
            confirmed = await self._click_drawer_text_button(
                page, "确定"
            )
            if not confirmed:
                raise RuntimeError("封面抽屉未找到「确定」")
            await asyncio.sleep(2)
            closed = await page.evaluate(
                """() => ![...document.querySelectorAll('.byte-drawer')]
                  .some((e) => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  })"""
            )
            if not closed:
                await self._close_image_drawer(page)
            # 6. 校验封面已生效
            ok = await self._wait_article_cover_ready(page, timeout_s=20)
            if not ok:
                raise RuntimeError("封面上传后未检测到封面图")
            logger.info("[文章][头条] 自定义封面已设置: %s", cover_path)
        finally:
            # 抽屉若还开着必须关掉,否则遮罩拦截后续点击
            opened = await page.evaluate(
                """() => [...document.querySelectorAll('.byte-drawer')]
                  .some((e) => {
                    const r = e.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  })"""
            )
            if opened:
                await self._close_image_drawer(page)

    async def _setup_article_cover(
        self, page, cover_path, cover_mode, srcs, store
    ) -> str:
        """封面统一处理, 返回实际生效的封面模式。

        平台三种模式(2026-10 实测):
          单图: 正文有图时自动取首图, 也可「替换」上传自定义封面
          三图: 平台按正文图片自动填充前 3 张(不足 3 张时平台校验会拦发表),
                故正文不足 3 张时自动降级单图
          无封面: 不展示封面, 仍可定时/发表
        """
        mode = (cover_mode or "单图").strip()
        if "无封面" in mode or mode.lower() in ("none", "no_cover"):
            await self._set_article_cover_none(page)
            return "无封面"
        if "三图" in mode:
            await self._set_article_cover_mode(page, "三图")
            await asyncio.sleep(1.5)
            filled = await self._count_article_cover_slots(page)
            if filled >= 3:
                logger.info(
                    "[文章][头条] 三图封面已由正文前 %d 张图自动填充", filled
                )
                return "三图"
            logger.warning(
                "[文章][头条] 三图封面需 3 张正文图, 当前仅 %d 张,"
                "自动降级为单图", filled,
            )
            await self._set_article_cover_mode(page, "单图")
            await asyncio.sleep(1)
        else:
            await self._set_article_cover_mode(page, "单图")
        if cover_path and Path(str(cover_path)).exists():
            try:
                await self._set_article_custom_cover(
                    page, str(cover_path), store
                )
                return "单图"
            except Exception as e:
                logger.warning(
                    "[文章][头条] 自定义封面上传失败(跳过): %s", e
                )
        # 正文有图 → 平台自动取首图作为单图封面
        if srcs:
            ok = await self._wait_article_cover_ready(page, timeout_s=25)
            if ok:
                logger.info("[文章][头条] 封面已自动使用正文首图(单图)")
                return "单图"
        # 无图 / 自动封面失败 → 选「无封面」(避免必填校验阻塞发表)
        logger.warning(
            "[文章][头条] 无可用封面,改选「无封面」避免必填校验阻塞"
        )
        await self._set_article_cover_none(page)
        return "无封面"

    # ---------- 发布设置项 ----------

    @staticmethod
    async def _set_article_declarations(page, declarations: list):
        """作品声明(头条实测为单选: 勾选新项会自动取消旧项, 为伪复选).

        2026-10 复测: 7 个选项均为 checkbox 外观但平台按单选处理,
        勾选新项会自动取消旧项。按传入顺序逐个设置, 最终以最后一项为准;
        回读平台实际勾选项记录日志, 便于发现配置与生效不一致。
        """
        if len(declarations) > 1:
            logger.warning(
                "[文章][头条] 作品声明平台为单选, 传入 %d 项, 仅最后一项"
                "「%s」会生效: %s",
                len(declarations), declarations[-1], declarations,
            )
        for text in declarations:
            state = await page.evaluate(
                """(text) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const norm = (s) => (s || '').replace(/\\s/g, '');
                  const boxes = [...document.querySelectorAll('.byte-checkbox')]
                    .filter(vis);
                  const lb = boxes.find((e) => {
                    const t = norm(e.innerText);
                    return t === norm(text) || t.startsWith(norm(text));
                  });
                  if (!lb) return 'not-found';
                  const cb = lb.querySelector('input[type=checkbox]');
                  if (!cb) return 'no-input';
                  if (cb.checked) return 'already';
                  cb.click();
                  return 'clicked';
                }""",
                text,
            )
            if state == "not-found":
                logger.warning(
                    "[文章][头条] 未找到作品声明选项: %s", text
                )
                continue
            await asyncio.sleep(0.7)
        await asyncio.sleep(1)
        # 回读平台实际保持勾选的作品声明项
        checked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              const EXCLUDE = ['头条首发', '发布得更多收益'];
              const out = [];
              for (const lb of [...document.querySelectorAll(
                  '.byte-checkbox')].filter(vis)) {
                const cb = lb.querySelector('input[type=checkbox]');
                if (!cb || !cb.checked) continue;
                const t = norm(lb.innerText);
                if (!t || t.length > 16) continue;
                if (EXCLUDE.some((x) => t.includes(norm(x)))) continue;
                out.push(t);
              }
              return out;
            }"""
        )
        expected = declarations[-1] if declarations else ""
        if expected and not any(
                expected.replace(" ", "") in (c or "") for c in checked):
            logger.warning(
                "[文章][头条] 作品声明回读与期望不一致(期望「%s」, "
                "实际勾选 %s)", expected, checked or [],
            )
        else:
            logger.info(
                "[文章][头条] 作品声明已勾选(平台实际): %s", checked or "无"
            )

    @staticmethod
    async def _read_first_publish_state(page):
        """回读「头条首发」勾选状态(找不到返回 None)。"""
        return await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              const lb = [...document.querySelectorAll('.byte-checkbox')]
                .filter(vis)
                .find((e) => norm(e.innerText).startsWith('头条首发'));
              if (!lb) return null;
              const cb = lb.querySelector('input[type=checkbox]');
              return cb ? !!cb.checked : null;
            }"""
        )

    @staticmethod
    async def _set_article_first_publish(page, enable: bool):
        """头条首发: 双向设置(平台编辑器会记忆上次状态)。

        2026-10 实测: 首发默认状态不固定(跟随上次编辑), 因此 checkbox
        为 False 时也必须主动取消勾选; 正文不足 100 字平台会 toast 拦截。
        """
        want = bool(enable)
        state = await page.evaluate(
            """(want) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              const lb = [...document.querySelectorAll('.byte-checkbox')]
                .filter(vis)
                .find((e) => norm(e.innerText).startsWith('头条首发'));
              if (!lb) return 'not-found';
              const cb = lb.querySelector('input[type=checkbox]');
              if (!cb) return 'no-input';
              if (cb.checked === want) return 'already';
              cb.click();
              return 'clicked';
            }""",
            want,
        )
        if state == "not-found":
            raise RuntimeError("未找到「头条首发」选项")
        await asyncio.sleep(2.2)
        checked = await ToutiaoPlatform._read_first_publish_state(page)
        if checked == want:
            logger.info(
                "[文章][头条] 头条首发已%s", "勾选" if want else "取消勾选"
            )
            return
        toast = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              return [...document.querySelectorAll(
                '[class*="toast"], [class*="message"]')].filter(vis)
                .map((e) => (e.innerText || '').trim())
                .filter(Boolean).join(' | ').slice(0, 200);
            }"""
        )
        logger.warning(
            "[文章][头条] 头条首发设置未生效(期望 %s, 实际 %s; "
            "正文可能不足 100 字)%s",
            want, checked, f": {toast}" if toast else "",
        )

    @staticmethod
    async def _close_auto_rights_modal(page) -> bool:
        """勾「授权平台自动维权」后若账号未开通全网维权, 平台弹窗拦截。

        2026-10-23 实测弹窗: 「温馨提示 请在开通全网维权后, 授权平台进行
        自动维权。 [取消] [去开通]」。必须点「取消」关闭, 否则遮罩拦截后续
        所有点击(不投放广告/位置/合集都会超时失败)。
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 6
        hit = False
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            hit = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const norm = (s) => (s || '').replace(/\\s+/g, '');
                  return [...document.querySelectorAll(
                    '.byte-modal, .byte-dialog')].filter(vis).some(
                    (el) => norm(el.innerText).includes('全网维权'));
                }"""
            )
            if hit:
                break
            await asyncio.sleep(1)
        if not hit:
            return False
        try:
            cancel = page.locator(
                '.byte-modal button', has_text="取消").first
            if await cancel.count():
                await cancel.click(timeout=8000)
            else:
                await page.keyboard.press("Escape")
        except Exception as e:
            logger.warning(
                "[文章][头条] 关闭「全网维权」提示弹窗失败: %s", e
            )
        await asyncio.sleep(1)
        logger.warning(
            "[文章][头条] 账号未开通全网维权,「授权平台自动维权」无法设置,"
            "已关闭提示弹窗并跳过"
        )
        return True

    @staticmethod
    async def _set_article_auto_rights(page, enable: bool,
                                       first_publish: bool = True):
        """授权平台自动维权(仅「头条首发」勾选时平台才显示该复选框)。

        注意: 账号未开通全网维权时, 点击会弹「温馨提示」弹窗, 该设置无法
        生效; 自动化点击后必须关闭弹窗并跳过, 不能阻塞后续设置。
        """
        if not first_publish:
            logger.warning(
                "[文章][头条] 自动维权仅在勾选「头条首发」时可用,跳过"
            )
            return
        want = bool(enable)
        state = await page.evaluate(
            """(want) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              let best = null;
              for (const el of document.querySelectorAll(
                  'div, section, label')) {
                if (!vis(el)) continue;
                const t = norm(el.innerText);
                if (!t.includes('授权平台自动维权')) continue;
                const cb = el.querySelector('input[type=checkbox]');
                if (!cb) continue;
                if (!best || t.length < norm(best.innerText).length) {
                  best = el;
                }
              }
              if (!best) return null;
              const cb = best.querySelector('input[type=checkbox]');
              const before = !!cb.checked;
              if (before !== want) cb.click();
              return {before, after: !!cb.checked};
            }""",
            want,
        )
        if state is None:
            logger.warning(
                "[文章][头条] 未找到「授权平台自动维权」选项(账号可能未开通"
                "全网维权),跳过"
            )
            return
        await asyncio.sleep(1.2)
        # 未开通全网维权时点击会弹提示窗, 必须关掉
        blocked = await ToutiaoPlatform._close_auto_rights_modal(page)
        if blocked:
            return
        after = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              let best = null;
              for (const el of document.querySelectorAll(
                  'div, section, label')) {
                if (!vis(el)) continue;
                const t = norm(el.innerText);
                if (!t.includes('授权平台自动维权')) continue;
                const cb = el.querySelector('input[type=checkbox]');
                if (!cb) continue;
                if (!best || t.length < norm(best.innerText).length) {
                  best = el;
                }
              }
              return best
                ? !!best.querySelector('input[type=checkbox]').checked
                : null;
            }"""
        )
        if after == want:
            logger.info(
                "[文章][头条] 授权平台自动维权已%s",
                "勾选" if want else "取消勾选",
            )
        else:
            logger.warning(
                "[文章][头条] 自动维权设置未生效(期望 %s, 实际 %s)",
                want, after,
            )

    @staticmethod
    async def _confirm_ad_revenue_modal(page) -> bool:
        """选「不投放广告」后平台会弹二次确认框, 必须点「确定」。

        2026-10-23 实测: 选「不投放广告」→ 弹窗「提示: 该文章选择了
        '不投放广告', 将不会产生广告收益。」[取消][确定]; 不确认会留下
        遮罩层, 拦截后续点击/发表(弹窗必关铁律)。
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 8
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            hit = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const norm = (s) => (s || '').replace(/\\s+/g, '');
                  for (const el of document.querySelectorAll(
                      '.byte-modal, .byte-dialog')) {
                    if (!vis(el)) continue;
                    const t = norm(el.innerText);
                    if (t.includes('不会产生广告收益')
                        || t.includes('不投放广告')) {
                      return true;
                    }
                  }
                  return false;
                }"""
            )
            if hit:
                break
            await asyncio.sleep(1)
        if not hit:
            logger.info(
                "[文章][头条] 投放广告选择后未出现二次确认弹窗(无需确认)"
            )
            return False
        confirmed = False
        try:
            btn = page.locator(
                '.byte-modal button', has_text="确定"
            ).first
            if await btn.count():
                await btn.click(timeout=8000)
                confirmed = True
        except Exception as e:
            logger.warning("[文章][头条] 点击广告确认弹窗「确定」失败: %s", e)
        if not confirmed:
            # 兜底: 关掉弹窗(避免遮罩阻塞发布), 但广告设置可能回到默认
            try:
                cancel = page.locator(
                    '.byte-modal button', has_text="取消").first
                if await cancel.count():
                    await cancel.click(timeout=5000)
            except Exception:
                pass
            logger.warning(
                "[文章][头条] 广告二次确认未完成, 已关闭弹窗(不投放广告"
                "可能未生效)"
            )
            return False
        await asyncio.sleep(1.2)
        left = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s+/g, '');
              return [...document.querySelectorAll(
                '.byte-modal, .byte-dialog')].filter(vis).some(
                (el) => norm(el.innerText).includes('不会产生广告收益'));
            }"""
        )
        if left:
            raise RuntimeError("广告确认弹窗点击确定后未关闭")
        logger.info(
            "[文章][头条] 已确认「不投放广告」二次确认弹窗(已关闭)"
        )
        return True

    @staticmethod
    async def _set_article_ad_revenue(page, enable: bool):
        """投放广告: 「投放广告赚收益」(默认) / 「不投放广告」。

        byte-design 自定义 radio 的 input.checked 不反映视觉选中态,
        统一用「真实鼠标点击 label + 回读 .byte-radio-inner.checked」校验;
        选「不投放广告」后平台会弹二次确认框, 必须点「确定」。
        """
        target = "投放广告赚收益" if enable else "不投放广告"
        label = page.locator('label.byte-radio', has_text=target).first
        await label.scroll_into_view_if_needed(timeout=8000)
        await label.click(timeout=8000)
        await asyncio.sleep(1)
        if not enable:
            await ToutiaoPlatform._confirm_ad_revenue_modal(page)
            # 平台二次确认弹窗可能延迟 10s+ 才出现, 再清场一次(等待延迟弹窗)
            await ToutiaoPlatform._settle_article_modals(
                page, wait_late_ad=True)
        state = await page.evaluate(
            """(target) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              const lb = [...document.querySelectorAll('label.byte-radio')]
                .filter(vis)
                .find((e) => norm(e.innerText) === norm(target));
              if (!lb) return null;
              return !!lb.querySelector('.byte-radio-inner.checked');
            }""",
            target,
        )
        if state is None:
            raise RuntimeError(f"未找到「{target}」选项")
        if not state:
            raise RuntimeError(f"「{target}」点击后未选中")
        logger.info("[文章][头条] 投放广告已设置: %s", target)

    @staticmethod
    async def _set_article_micro_headline(page, enable: bool):
        """同时发布微头条「发布得更多收益」开关。

        2026-10-23 多次复测: 该开关的禁用状态不稳定(同一账号不同轮次
        既有「勾选+disabled」也有可编辑的情况), 与「头条首发」是否勾选
        无稳定联动。自动化策略: 未禁用时按配置设置, 禁用时回读并跳过,
        不阻塞发布流程(平台可能按账号资质/内容状态锁定该开关)。
        """
        state = await page.evaluate(
            """(want) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s/g, '');
              const lb = [...document.querySelectorAll('.byte-checkbox')]
                .filter(vis)
                .find((e) => norm(e.innerText).startsWith('发布得更多收益'));
              if (!lb) return null;
              const cb = lb.querySelector('input[type=checkbox]');
              if (!cb) return null;
              const result = {checked: !!cb.checked, disabled: !!cb.disabled};
              if (!cb.disabled && cb.checked !== want) {
                cb.click();
                result.checked = !!cb.checked;
              }
              return result;
            }""",
            bool(enable),
        )
        if state is None:
            raise RuntimeError("未找到「发布得更多收益」选项")
        if state.get("disabled"):
            logger.info(
                "[文章][头条] 微头条开关平台已禁用(账号级锁定,当前=%s),"
                "本项设置不生效,跳过",
                "开启" if state.get("checked") else "关闭",
            )
            return
        logger.info(
            "[文章][头条] 同时发布微头条已设置: %s",
            "开启" if state.get("checked") else "关闭",
        )

    # ---------- 添加位置 / 合集 ----------

    async def _set_article_location(self, page, city: str):
        """添加位置: position-select 可搜索城市下拉(平台城市列表)。"""
        city = (city or "").strip()
        if not city:
            return
        view = page.locator('.position-select .byte-select-view').first
        await view.scroll_into_view_if_needed(timeout=8000)
        await view.click(timeout=8000)
        await asyncio.sleep(1.5)
        search = page.locator('.position-select input').first
        await search.click(timeout=8000)
        await search.press_sequentially(city, delay=80)
        await asyncio.sleep(2.5)
        option = page.locator(
            '.byte-select-popup .byte-select-option', has_text=city
        ).first
        if not await option.count():
            await page.keyboard.press("Escape")
            raise RuntimeError(
                f"平台城市列表未找到「{city}」(仅支持平台内置城市名)"
            )
        await option.click(timeout=8000)
        await asyncio.sleep(1.2)
        selected = await page.evaluate(
            """() => {
              const el = document.querySelector(
                '.position-cell .byte-select-view');
              return el ? (el.innerText || '').replace(/\\s+/g, ' ').trim()
                : '';
            }"""
        )
        if city not in (selected or ""):
            raise RuntimeError(
                f"添加位置未生效(期望「{city}」, 实际「{selected}」)"
            )
        logger.info("[文章][头条] 添加位置已设置: %s", city)

    async def _set_article_collection(self, page, name: str):
        """添加至合集: 打开「添加合集」弹窗选同名合集 → 确定。"""
        name = (name or "").strip()
        if not name:
            return
        btn = page.locator('.collection-btn').first
        await btn.scroll_into_view_if_needed(timeout=8000)
        await btn.click(timeout=8000)
        try:
            await page.wait_for_selector(
                '.add-collection-modal', state="visible", timeout=15000
            )
            await asyncio.sleep(1.2)
            state = await page.evaluate(
                """(name) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                  const box = document.querySelector(
                    '.add-collection-list-box');
                  if (!box) return {found: false, text: ''};
                  const text = norm(box.innerText).slice(0, 300);
                  if (text.includes('暂无合集')) {
                    return {found: false, text};
                  }
                  const cands = [...box.querySelectorAll('*')]
                    .filter((el) => vis(el) && norm(el.innerText));
                  const hit = cands.find((el) => norm(el.innerText) === name
                    && el.getBoundingClientRect().height < 80)
                    || cands.find((el) => norm(el.innerText).includes(name)
                      && el.getBoundingClientRect().height < 80);
                  if (!hit) return {found: false, text};
                  hit.click();
                  return {found: true, clicked: norm(hit.innerText)};
                }""",
                name,
            )
            if not state.get("found"):
                logger.warning(
                    "[文章][头条] 未找到合集「%s」(弹窗内容: %s),跳过",
                    name, state.get("text") or "空",
                )
                cancel = page.locator(
                    '.add-collection-modal button', has_text="取消"
                ).first
                if await cancel.count():
                    await cancel.click()
                await asyncio.sleep(1)
                return
            await asyncio.sleep(1)
            confirm = page.locator(
                '.add-collection-modal button', has_text="确定"
            ).first
            if not await confirm.count():
                raise RuntimeError("合集弹窗未找到「确定」")
            await confirm.click(timeout=8000)
            await asyncio.sleep(1.5)
            logger.info(
                "[文章][头条] 已添加至合集: %s", state.get("clicked") or name
            )
        except Exception:
            # 弹窗必关铁律: 任何异常都先关闭弹窗再抛出
            try:
                cancel = page.locator(
                    '.add-collection-modal button', has_text="取消"
                ).first
                if await cancel.count():
                    await cancel.click()
            except Exception:
                pass
            raise

    @staticmethod
    async def _install_ad_modal_auto_confirm(page) -> None:
        """在页面内装一个定时器, 自动点掉延迟出现的广告二次确认弹窗。

        2026-10-23 实测: 选「不投放广告」后, 二次确认弹窗可能在 10~20s 后
        才由平台异步渲染(甚至由自动保存/校验触发), 阻塞发表按钮点击。
        页面内 500ms 轮询, 出现即点「确定」, 并置 window.__ttAdConfirmed。
        """
        await page.evaluate(
            """() => {
              if (window.__ttAdConfirmTimer) return;
              const vis = (el) => {
                if (!el) return false;
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').replace(/\\s+/g, '');
              window.__ttAdConfirmTimer = setInterval(() => {
                try {
                  for (const el of document.querySelectorAll(
                      '.byte-modal, .byte-dialog, .byte-modal-wrapper')) {
                    if (!vis(el)) continue;
                    if (!norm(el.innerText).includes('不会产生广告收益')) {
                      continue;
                    }
                    const btn = [...el.querySelectorAll('button')]
                      .find((b) => norm(b.innerText) === '确定'
                        && !b.disabled && vis(b));
                    if (btn) {
                      btn.click();
                      window.__ttAdConfirmed = true;
                      return;
                    }
                  }
                } catch (e) {}
              }, 500);
            }"""
        )
        logger.info(
            "[文章][头条] 已安装「不投放广告」二次确认弹窗自动确认器"
        )

    @staticmethod
    async def _settle_article_modals(page, wait_late_ad: bool = False) -> None:
        """提交前清场: 确认/关闭设置过程中残留的二次确认弹窗。

        2026-10-23 实测「不投放广告」的二次确认弹窗可能延迟 10s+ 才出现
        (异步, 甚至出现在后续设置之后), 不确认会以遮罩拦住发表按钮点击,
        且截图里会残留弹窗。这里先装页面内自动确认器, 再轮询等待其生效;
        wait_late_ad=True 时最多等 25s(覆盖延迟弹窗), 否则快速返回。
        """
        await ToutiaoPlatform._install_ad_modal_auto_confirm(page)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + (25 if wait_late_ad else 8)
        idle_limit = 12 if wait_late_ad else 2
        idle = 0
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            state = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const norm = (s) => (s || '').replace(/\\s+/g, '');
                  for (const el of document.querySelectorAll(
                      '.byte-modal, .byte-dialog, .byte-modal-wrapper')) {
                    if (!vis(el)) continue;
                    const t = norm(el.innerText);
                    if (t.includes('不会产生广告收益')
                        || t.includes('不投放广告')) {
                      return 'ad';
                    }
                    if (t.includes('全网维权')) return 'rights';
                  }
                  return '';
                }"""
            )
            confirmed = await page.evaluate(
                "() => !!window.__ttAdConfirmed"
            )
            if not state:
                if confirmed:
                    logger.info(
                        "[文章][头条] 已自动确认「不投放广告」延迟弹窗"
                    )
                    return
                idle += 1
                if idle >= idle_limit:
                    return
                await asyncio.sleep(1)
                continue
            idle = 0
            if state == "ad":
                btn = page.locator(
                    '.byte-modal button', has_text="确定").first
                if await btn.count():
                    await btn.click(timeout=8000)
                    logger.info(
                        "[文章][头条] 提交前确认「不投放广告」二次确认弹窗"
                    )
                else:
                    await page.keyboard.press("Escape")
            else:
                cancel = page.locator(
                    '.byte-modal button', has_text="取消").first
                if await cancel.count():
                    await cancel.click(timeout=8000)
                else:
                    await page.keyboard.press("Escape")
                logger.info(
                    "[文章][头条] 提交前关闭「全网维权」提示弹窗"
                )
            await asyncio.sleep(1.5)
        logger.warning("[文章][头条] 提交前弹窗清场超时(继续提交)")

    # ---------- 定时发布 ----------

    @staticmethod
    async def _pick_timing_option(page, select_cls: str, text: str):
        """定时弹窗内某个 byte-select 选值(day/hour/minute)。"""
        clicked = await page.evaluate(
            """(cls) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const el = document.querySelector(
                '.common-timing-picker ' + cls + ' .byte-select-view');
              if (!el || !vis(el)) return false;
              el.click();
              return true;
            }""",
            select_cls,
        )
        if not clicked:
            raise RuntimeError(f"未找到定时下拉: {select_cls}")
        await asyncio.sleep(1.5)
        picked = await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const norm = (s) => (s || '').trim();
              const pops = [...document.querySelectorAll(
                '.byte-select-popup')].filter(vis);
              for (const pop of pops) {
                for (const opt of [...pop.querySelectorAll(
                    '.byte-select-option')].filter(vis)) {
                  if (norm(opt.innerText) === text) {
                    opt.click();
                    return true;
                  }
                }
              }
              for (const opt of [...document.querySelectorAll(
                  '.byte-select-option')].filter(vis)) {
                if (norm(opt.innerText) === text) {
                  opt.click();
                  return true;
                }
              }
              return false;
            }""",
            text,
        )
        if not picked:
            raise RuntimeError(f"定时下拉选项未找到: {text}")
        await asyncio.sleep(1.2)

    async def _set_article_schedule(self, page, schedule_time_str: str):
        """设置定时发布(「定时发布」弹窗: 日期/时/分 + 确认).

        头条约束: 当前时间后 2 小时 ~ 7 天。
        设置后不点弹窗的「预览并定时发布」按钮,由 _click_article_publish
        统一走预览 → 定时发布。
        """
        from datetime import datetime, timedelta

        try:
            dt = datetime.strptime(
                (schedule_time_str or "").strip(), "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            raise RuntimeError(
                "[文章][头条] 定时时间格式应为 YYYY-MM-DD HH:MM:SS"
            )
        diff = dt - datetime.now()
        if not (
            timedelta(hours=self._ARTICLE_SCHEDULE_MIN_HOURS)
            <= diff
            <= timedelta(days=self._ARTICLE_SCHEDULE_MAX_DAYS)
        ):
            raise RuntimeError(
                "[文章][头条] 定时发布需为当前时间后 2 小时 ~ 7 天内"
            )
        # 打开定时弹窗(底部 footer 「定时发布」精确文案按钮)
        clicked = False
        try:
            timer_btn = page.get_by_role(
                "button", name="定时发布", exact=True
            ).first
            await timer_btn.scroll_into_view_if_needed(timeout=8000)
            await timer_btn.click(timeout=8000)
            clicked = True
        except Exception as e:
            logger.warning(
                "[文章][头条] Playwright 点击「定时发布」失败,改用 JS: %s",
                e,
            )
        if not clicked:
            clicked = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  for (const b of [...document.querySelectorAll('button')]
                      .filter(vis)) {
                    if ((b.innerText || '').trim() === '定时发布'
                        && !b.disabled) {
                      b.click();
                      return true;
                    }
                  }
                  return false;
                }"""
            )
        if not clicked:
            raise RuntimeError("未找到底部「定时发布」按钮")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 20
        opened = False
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            opened = await page.evaluate(
                """() => {
                  const el = document.querySelector(
                    '.common-timing-picker');
                  if (!el) return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                }"""
            )
            if opened:
                break
            await asyncio.sleep(1)
        if not opened:
            raise RuntimeError(
                "定时发布弹窗未打开(表单校验未通过?)"
            )
        await self._pick_timing_option(
            page, ".day-select", f"{dt.month}月{dt.day}日"
        )
        await self._pick_timing_option(
            page, ".hour-select", str(dt.hour)
        )
        await self._pick_timing_option(
            page, ".minute-select", str(dt.minute)
        )
        expected = dt.strftime("%Y-%m-%d %H:%M")
        actual = await page.evaluate(
            """() => {
              const el = document.querySelector(
                '.common-timing-picker .publish-time');
              return el ? (el.innerText || '').trim() : '';
            }"""
        )
        if expected not in actual:
            raise RuntimeError(
                f"定时时间设置未生效(期望 {expected},实际 {actual})"
            )
        logger.info("[文章][头条] 定时发布时间已设置: %s", actual)

    # ---------- 预览 / 发表 ----------

    @staticmethod
    async def _wait_preview_overlay(page, timeout_s: int = 40) -> bool:
        """等底部预览遮罩(含「关闭预览」「发布」按钮)。"""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            ok = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll('button, [role=button]')]
                    .filter(vis)
                    .some((b) => (b.innerText || '').trim() === '关闭预览');
                }"""
            )
            if ok:
                return True
            await asyncio.sleep(1)
        return False

    async def _open_article_preview(self, page):
        """点底部「预览」打开预览遮罩(不发表,dry-run 校验用)。"""
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const b of [...document.querySelectorAll('button')]
                  .filter(vis)) {
                if ((b.innerText || '').trim() === '预览' && !b.disabled) {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if not clicked:
            raise RuntimeError("未找到底部「预览」按钮")
        await asyncio.sleep(4)
        if not await self._wait_preview_overlay(page, timeout_s=30):
            raise RuntimeError("预览遮罩未出现(表单校验未通过?)")

    @staticmethod
    async def _close_article_preview(page):
        """关闭预览遮罩(点「关闭预览」)。"""
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const b of [...document.querySelectorAll(
                  'button, [role=button]')].filter(vis)) {
                if ((b.innerText || '').trim() === '关闭预览') {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if clicked:
            await asyncio.sleep(1.5)
        else:
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)

    @staticmethod
    async def _detect_risk_control(page) -> str:
        """检测标题/发表过程中的风控验证(滑块/验证码)。"""
        try:
            return await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const sels = [
                    '.secsdk-captcha-drag-wrapper',
                    '#captcha_container',
                    '[class*="captcha"]',
                    '[id*="captcha"]',
                    'iframe[src*="captcha"]',
                    '[class*="sliderVerify"]',
                    '[class*="slider-verify"]',
                  ];
                  for (const sel of sels) {
                    for (const el of document.querySelectorAll(sel)) {
                      if (vis(el)) return sel;
                    }
                  }
                  if ((document.body.innerText || '')
                      .includes('请完成安全验证')) {
                    return 'text:请完成安全验证';
                  }
                  return '';
                }"""
            ) or ""
        except Exception:
            return ""

    @staticmethod
    async def _fetch_platform_json(page, path: str):
        """在页面上下文内 fetch 平台接口(复用登录 cookie),返回 JSON。"""
        try:
            res = await page.evaluate(
                """async (url) => {
                  try {
                    const r = await fetch(url, {credentials: 'include'});
                    const text = await r.text();
                    let data = null;
                    try { data = JSON.parse(text); } catch (e) { data = null; }
                    return {status: r.status, data};
                  } catch (e) {
                    return {status: 0, error: String(e)};
                  }
                }""",
                path,
            )
        except Exception as e:
            return {"status": 0, "error": str(e)}
        return res or {}

    @classmethod
    async def _fetch_article_draft_list(cls, page) -> list:
        """读取草稿箱列表(平台接口 code==0 才返回列表)."""
        res = await cls._fetch_platform_json(
            page,
            "/mp/agw/creator_center/draft_list?type=0&count=50&app_id=1231",
        )
        data = res.get("data")
        if not isinstance(data, dict):
            return []
        if data.get("code") not in (0, "0"):
            return []
        return data.get("draft_list") or []

    @classmethod
    async def _resolve_article_draft_id(cls, page, store, title) -> str:
        """解析本次发布的草稿 id(用于发表后草稿消失验证)。

        优先取最近一次自动保存响应里的 pgc_id;取不到则按标题匹配草稿箱。
        只有能在草稿箱列表中确认存在的 id 才返回,避免误判。
        """
        drafts = []
        for _ in range(3):
            drafts = await cls._fetch_article_draft_list(page)
            if drafts:
                break
            await asyncio.sleep(2)
        gids = []
        for it in drafts:
            for k in ("gid", "pgc_id"):
                if it.get(k):
                    gids.append(str(it[k]))
        candidate = ""
        try:
            if store.get("draft_saves"):
                data = store["draft_saves"][-1]
                inner = data.get("data") if isinstance(data, dict) else {}
                if isinstance(inner, dict):
                    candidate = str(inner.get("pgc_id") or "")
        except Exception:
            candidate = ""
        if candidate and candidate in gids:
            return candidate
        if title:
            matched = [
                d for d in drafts
                if (d.get("title") or "").strip() == title.strip()
            ]
            matched.sort(
                key=lambda d: d.get("update_time") or 0, reverse=True
            )
            if matched:
                return str(matched[0].get("gid") or "")
        return ""

    @classmethod
    async def _article_draft_gone(cls, page, draft_id: str) -> bool:
        """草稿箱 API code==0 且目标草稿 id 已不在列表中 = 已转为文章。"""
        if not draft_id:
            return False
        drafts = await cls._fetch_article_draft_list(page)
        for it in drafts:
            for k in ("gid", "pgc_id"):
                if str(it.get(k) or "") == str(draft_id):
                    return False
        return True

    async def _click_article_publish(
        self, page, store, scheduled=False, title=""
    ):
        """打开预览 → 点「发布」/「定时发布」→ 监听发表 API 判定结果.

        唯一成功依据: 发表类 POST 响应 code == 0(非 source=29 草稿保存)。
        失败 raise(含 code + message)。
        """
        # 可选网络调试(TOUTIAO_DEBUG_NET=1): 打印发布阶段全部 xhr/fetch
        if os.environ.get("TOUTIAO_DEBUG_NET"):
            async def _on_request(request):
                try:
                    if "toutiao.com" not in request.url:
                        return
                    rt = request.resource_type
                    if rt in ("xhr", "fetch", "document") and (
                        request.method != "GET" or rt == "document"
                    ):
                        logger.info(
                            "[net] %s %s %s post=%s",
                            rt, request.method, request.url[:240],
                            (request.post_data or "")[:160],
                        )
                except Exception:
                    pass

            page.on(
                "request",
                lambda r: asyncio.ensure_future(_on_request(r)),
            )
            logger.info("[net] 已开启发布阶段网络调试")
        footer_text = "预览并定时发布" if scheduled else "预览并发布"
        logger.info("[文章][头条] 点击底部「%s」...", footer_text)
        clicked = await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const b of [...document.querySelectorAll('button')]
                  .filter(vis)) {
                if ((b.innerText || '').trim() === text && !b.disabled) {
                  b.click();
                  return true;
                }
              }
              return false;
            }""",
            footer_text,
        )
        if not clicked:
            raise RuntimeError(f"[文章][头条] 未找到「{footer_text}」按钮")
        await asyncio.sleep(4)
        # 点击后进入两种预览形态之一:
        #   A. 全屏预览页(底部「返回编辑」「确认发布」)——底部
        #      「预览并发布」/定时弹窗「预览并定时发布」走这里
        #   B. 预览遮罩(「关闭预览」)——底部「预览」按钮走这里
        loop = asyncio.get_event_loop()
        mode = ""
        deadline = loop.time() + 45
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            info = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const btns = [...document.querySelectorAll(
                    'button, [role=button]')].filter(vis);
                  const has = (t) => btns.some(
                    (b) => (b.innerText || '').trim() === t);
                  return {
                    confirm: has('确认发布'),
                    overlay: has('关闭预览'),
                  };
                }"""
            )
            if info.get("confirm"):
                mode = "confirm"
                break
            if info.get("overlay"):
                mode = "overlay"
                break
            risk = await self._detect_risk_control(page)
            if risk:
                await self._article_screenshot(
                    page, "toutiao_article_risk_control.png"
                )
                raise RuntimeError(
                    f"[文章][头条] 点击「{footer_text}」后出现风控验证"
                    f"({risk}),请在有头浏览器人工完成验证后重试"
                )
            await asyncio.sleep(1.5)
        if not mode:
            await self._article_screenshot(
                page, "toutiao_article_preview_missing.png"
            )
            risk = await self._detect_risk_control(page)
            if risk:
                raise RuntimeError(
                    f"[文章][头条] 预览页未出现且检测到风控验证({risk}),"
                    "请在有头浏览器人工完成验证后重试"
                )
            raise RuntimeError(
                "[文章][头条] 预览页未出现(标题/正文/封面校验未通过)"
            )
        logger.info(
            "[文章][头条] 已进入预览%s",
            "页(确认发布)" if mode == "confirm" else "遮罩",
        )
        await self._article_screenshot(
            page, "toutiao_article_preview_overlay.png"
        )

        # 记录发布前草稿 id: 发表成功后该草稿会从草稿箱消失。
        # 头条发表请求的响应在部分网络路径下不回传给页面(浏览器中止读取),
        # 因此草稿箱状态作为 API 兜底判定(code==0 且草稿 id 消失)。
        draft_id = await self._resolve_article_draft_id(page, store, title)
        if draft_id:
            logger.info("[文章][头条] 发布前草稿 id: %s", draft_id)

        if mode == "confirm":
            # 全屏预览页 → 「确认发布」
            clicked = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  for (const b of [...document.querySelectorAll('button')]
                      .filter(vis)) {
                    if ((b.innerText || '').trim() === '确认发布'
                        && !b.disabled) {
                      b.click();
                      return true;
                    }
                  }
                  return false;
                }"""
            )
            if not clicked:
                raise RuntimeError(
                    "[文章][头条] 预览页未找到「确认发布」按钮"
                )
            logger.info("[文章][头条] 已点击预览页「确认发布」")
        else:
            # 预览遮罩 → 「发布」/「定时发布」
            final_text = "定时发布" if scheduled else "发布"
            logger.info("[文章][头条] 点击预览遮罩「%s」...", final_text)
            clicked = await page.evaluate(
                """(want) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const closeBtn = [...document.querySelectorAll(
                    'button, [role=button]')].filter(vis)
                    .find((b) => (b.innerText || '').trim() === '关闭预览');
                  if (!closeBtn) return false;
                  let holder = closeBtn.parentElement;
                  for (let d = 0; d < 4 && holder; d++) {
                    const target = [...holder.querySelectorAll('button')]
                      .filter(vis)
                      .find((b) => (b.innerText || '').trim() === want
                        && !b.disabled);
                    if (target) { target.click(); return true; }
                    holder = holder.parentElement;
                  }
                  for (const b of [...document.querySelectorAll('button')]
                      .filter(vis)) {
                    if ((b.innerText || '').trim() === want
                        && (b.className || '').toString()
                          .includes('publish-btn')) {
                      b.click();
                      return true;
                    }
                  }
                  return false;
                }""",
                final_text,
            )
            if not clicked:
                raise RuntimeError(
                    f"[文章][头条] 预览遮罩内未找到「{final_text}」按钮"
                )

        # 等发表接口响应(忽略草稿自动保存 source=29)
        loop = asyncio.get_event_loop()
        publish_started = loop.time()
        deadline = publish_started + 180
        draft_checked_at = publish_started
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            if store["publishes"]:
                break
            # 兜底判定: 草稿已转为文章(草稿箱 API code==0 且草稿 id 消失)
            if (draft_id and not store["publishes"]
                    and loop.time() - publish_started > 10
                    and loop.time() - draft_checked_at > 4):
                draft_checked_at = loop.time()
                if await self._article_draft_gone(page, draft_id):
                    logger.info(
                        "[文章][头条] ✓ 发表成功(草稿箱 API code=0 且草稿"
                        " id=%s 已消失,草稿已转为线上文章)", draft_id,
                    )
                    return {
                        "pgc_id": draft_id, "verified_by": "draft_list",
                    }
            risk = await self._detect_risk_control(page)
            if risk:
                await self._article_screenshot(
                    page, "toutiao_article_risk_control.png"
                )
                raise RuntimeError(
                    f"[文章][头条] 文章发表被风控验证拦截({risk}),"
                    "请在有头浏览器人工完成验证后重试"
                )
            # 偶发二次确认弹窗(「确定」/「确认发布」)
            confirmed = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const modals = [...document.querySelectorAll(
                    '.byte-modal, [class*="modal"], [class*="dialog"]')]
                    .filter(vis)
                    .filter((m) => !m.classList.contains(
                      'common-timing-picker'));
                  for (const m of modals) {
                    for (const b of [...m.querySelectorAll('button')]
                        .filter(vis)) {
                      const t = (b.innerText || '').trim();
                      if (['确定', '确认发布', '继续发布'].includes(t)
                          && !b.disabled) {
                        b.click();
                        return t;
                      }
                    }
                  }
                  return null;
                }"""
            )
            if confirmed:
                logger.info(
                    "[文章][头条] 已点二次确认按钮: %s", confirmed
                )
            await asyncio.sleep(2)

        if not store["publishes"]:
            await self._article_screenshot(
                page, "toutiao_article_publish_timeout.png"
            )
            # 诊断: 打印本轮捕获到的 agw POST 响应(便于定位发表接口)
            try:
                logger.warning(
                    "[文章][头条] 未识别到发表接口响应,已捕获 agw POST %d 条:",
                    len(store.get("agw_posts") or []),
                )
                for code_ix, url_ix, post_ix in (
                    store.get("agw_posts") or []
                )[-12:]:
                    logger.warning(
                        "[文章][头条]   code=%s url=%s post=%s",
                        code_ix, url_ix, post_ix,
                    )
            except Exception:
                pass
            errs = store.get("publish_errors") or []
            if errs:
                err = errs[-1]
                err_data = err.get("data") or {}
                err_code = err_data.get(
                    "code", err_data.get("err_no")
                )
                err_msg = (
                    err_data.get("message") or err_data.get("reason")
                    or err_data.get("err_tips") or "发表失败"
                )
                raise RuntimeError(
                    f"今日头条文章发表失败 code={err_code} "
                    f"message={err_msg}"
                )
            risk = await self._detect_risk_control(page)
            if risk:
                raise RuntimeError(
                    f"[文章][头条] 等待发表响应超时,且检测到风控验证"
                    f"({risk}),请人工验证后重试"
                )
            raise RuntimeError(
                "[文章][头条] 等待发表接口响应超时"
                "(未捕获到发表类 POST 响应,详见日志 agw POST 列表)"
            )

        item = store["publishes"][-1]
        data = item.get("data") or {}
        code = data.get("code", data.get("err_no"))
        msg = (
            data.get("message")
            or data.get("reason")
            or data.get("err_tips")
            or "发表失败"
        )
        logger.info(
            "[文章][头条] 发表接口响应: code=%s message=%s url=%s post=%s",
            code, msg, (item.get("url") or "")[:160],
            (item.get("post") or "")[:160],
        )
        if code in (0, "0"):
            pgc_id = ""
            try:
                pgc_id = str((data.get("data") or {}).get("pgc_id") or "")
            except Exception:
                pass
            logger.info(
                "[文章][头条] ✓ 发表成功 (code=0, pgc_id=%s)", pgc_id
            )
            # 软校验: 等页面跳转/成功提示,超时只告警
            jump_deadline = loop.time() + 40
            while loop.time() < jump_deadline:
                raise_if_page_closed(page, action="文章发布")
                url = page.url or ""
                if "/graphic/publish" not in url:
                    logger.info(
                        "[文章][头条] 发表后页面已跳转: %s", url
                    )
                    break
                await asyncio.sleep(2)
            return {"pgc_id": pgc_id, "response": data,
                    "verified_by": "publish_api"}

        # 失败如实抛出(bp 层记录到 publish_details.error_message)
        risk_words = ("验证", "风控", "异常", "安全", "受限", "违规")
        if code in (2015,) or any(w in str(msg) for w in risk_words):
            raise RuntimeError(
                f"今日头条风控拦截文章发表: {msg}(code={code})"
                "——请在有头浏览器完成安全验证后重试"
            )
        raise RuntimeError(
            f"今日头条文章发表失败 code={code} message={msg}"
        )

    # ---------- 表单状态日志 ----------

    @staticmethod
    async def _log_article_form_state(page, applied_cover_mode: str = ""):
        """发表前打印表单关键状态(DOM 回读, 作为设置生效的验证证据)."""
        try:
            state = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const cls = (el) => (typeof el.className === 'string'
                    ? el.className : '');
                  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                  const ta = document.querySelector(
                    'textarea[placeholder*="请输入文章标题"]');
                  const ed = document.querySelector('.ProseMirror');
                  const cover = document.querySelector(
                    '.article-cover-img-wrap img');
                  const wordHint = [...document.querySelectorAll('*')]
                    .filter(vis)
                    .map((e) => (e.innerText || '').trim())
                    .find((t) => /^共\\s*\\d+\\s*字$/.test(t) && t.length < 20)
                    || '';
                  const coverRadio = document.querySelector(
                    '.article-cover-radio-group .byte-radio-inner.checked');
                  const coverImgs = [...document.querySelectorAll(
                    '.article-cover-images img')].filter(
                      (im) => (im.src || '').startsWith('http')).length;
                  const declarations = [];
                  const EXCLUDE = ['头条首发', '发布得更多收益'];
                  for (const lb of [...document.querySelectorAll(
                      '.byte-checkbox')].filter(vis)) {
                    const cb = lb.querySelector('input[type=checkbox]');
                    if (!cb || !cb.checked) continue;
                    const t = norm(lb.innerText);
                    if (!t || t.length > 16) continue;
                    if (EXCLUDE.some((x) => t.includes(x))) continue;
                    declarations.push(t);
                  }
                  const radioChecked = (text) => {
                    const lb = [...document.querySelectorAll('label.byte-radio')]
                      .filter(vis).find((e) => norm(e.innerText) === text);
                    return !!(lb && lb.querySelector(
                      '.byte-radio-inner.checked'));
                  };
                  const adTarget = radioChecked('不投放广告')
                    ? '不投放广告'
                    : (radioChecked('投放广告赚收益')
                       ? '投放广告赚收益' : '未识别');
                  // 首发 / 微头条 / 自动维权 状态
                  const pickCheckbox = (text) => {
                    const lb = [...document.querySelectorAll(
                        '.byte-checkbox')].filter(vis).find((e) =>
                      norm(e.innerText).startsWith(text));
                    if (!lb) return null;
                    const cb = lb.querySelector('input[type=checkbox]');
                    return cb ? {checked: !!cb.checked,
                                 disabled: !!cb.disabled} : null;
                  };
                  const positionText = (() => {
                    const el = document.querySelector(
                      '.position-cell .byte-select-view');
                    return el ? norm(el.innerText) : '';
                  })();
                  const collectionText = (() => {
                    const el = document.querySelector(
                      '.collection-form-item');
                    return el ? norm(el.innerText) : '';
                  })();
                  return {
                    title: ta ? (ta.value || '').trim() : '',
                    bodyLen: ed ? (ed.innerText || '').trim().length : 0,
                    wordHint,
                    coverUrl: cover ? (cover.src || '') : '',
                    coverImgs,
                    coverMode: coverRadio
                      ? norm(coverRadio.closest('label').innerText)
                      : '',
                    checked: declarations,
                    adTarget,
                    firstPublish: pickCheckbox('头条首发'),
                    microHeadline: pickCheckbox('发布得更多收益'),
                    autoRights: (() => {
                      let best = null;
                      for (const el of document.querySelectorAll(
                          'div, section, label')) {
                        if (!vis(el)) continue;
                        if (!norm(el.innerText).includes(
                            '授权平台自动维权')) continue;
                        const cb = el.querySelector(
                          'input[type=checkbox]');
                        if (!cb) continue;
                        if (!best || norm(el.innerText).length
                            < norm(best.innerText).length) {
                          best = el;
                        }
                      }
                      if (!best) return null;
                      const cb = best.querySelector('input[type=checkbox]');
                      return {checked: !!cb.checked,
                              disabled: !!cb.disabled};
                    })(),
                    positionText,
                    collectionText,
                  };
                }"""
            )
            logger.info(
                "[文章][头条] 发表前表单回读: 标题=%r 正文字数=%d(%s) "
                "封面=%s(槽内图 %s 张) 封面模式=%s(期望 %s) 投放广告=%s "
                "首发=%s 微头条=%s 自动维权=%s 位置=%s 合集=%s 声明=%s",
                state.get("title"), state.get("bodyLen", 0),
                state.get("wordHint") or "-",
                "有" if state.get("coverUrl") else "无",
                state.get("coverImgs"),
                state.get("coverMode") or "-",
                applied_cover_mode or "-",
                state.get("adTarget"),
                state.get("firstPublish"),
                state.get("microHeadline"),
                state.get("autoRights") or "未显示",
                state.get("positionText") or "未设置",
                state.get("collectionText") or "未设置",
                state.get("checked") or [],
            )
        except Exception as e:
            logger.info("[文章][头条] 表单状态读取失败: %s", e)

    # ---------- 草稿保存等待 ----------

    @staticmethod
    async def _wait_draft_saved(page, store, timeout_s: int = 45) -> str:
        """等草稿自动保存(编辑器自动保存 POST source=29)。"""
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_s
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            if store.get("draft_saves"):
                data = store["draft_saves"][-1]
                if data.get("code") in (0, "0"):
                    pgc_id = ""
                    try:
                        pgc_id = str(
                            (data.get("data") or {}).get("pgc_id") or ""
                        )
                    except Exception:
                        pass
                    logger.info(
                        "[文章][头条] 草稿已自动保存(pgc_id=%s)", pgc_id
                    )
                    return pgc_id
            saved = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll('*')].filter(vis)
                    .some((e) => {
                      const t = (e.innerText || '').trim();
                      return t === '草稿已保存' || t === '草稿已自动保存';
                    });
                }"""
            )
            if saved:
                logger.info("[文章][头条] 页面提示草稿已保存")
                return ""
            await asyncio.sleep(1.5)
        logger.warning(
            "[文章][头条] 未捕获草稿保存接口响应/提示(可能已保存)"
        )
        return ""

    # ---------- 图片路径解析 ----------

    @staticmethod
    def _download_to_temp(url: str, filename: str) -> str:
        """下载远程图片到临时文件(正文外链图片/素材 URL 兜底)。"""
        ext = Path(filename).suffix or mimetypes.guess_extension(
            "image/jpeg"
        ) or ".jpg"
        fd, path = tempfile.mkstemp(suffix=ext)
        os.close(fd)
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            raise RuntimeError(
                f"[文章][头条] 下载图片失败({resp.status_code}): {url}"
            )
        Path(path).write_bytes(resp.content)
        return path

    @staticmethod
    def _resolve_image_local_path(src: str) -> str:
        """把正文 img src 解析为本地文件路径(上传头条图床用)。

        支持素材库 URL(/api/materials/file/<stored_path>)、本地绝对路径、
        data: URL(写临时文件)、外链 http(s)(下载到临时文件)。
        """
        from storage import get_storage

        if src.startswith("data:"):
            head, _, b64 = src.partition(",")
            mime = head[5:].split(";")[0] or "image/png"
            ext = mimetypes.guess_extension(mime) or ".png"
            fd, path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(b64))
            return path

        parsed = urlparse(src)
        marker = "/api/materials/file/"
        stored = ""
        if marker in src:
            stored = unquote(src.split(marker, 1)[1].split("?")[0])
        elif parsed.path and marker in parsed.path:
            stored = unquote(parsed.path.split(marker, 1)[1])

        if stored:
            # 素材 URL 形如 /api/materials/file/materials/2026/09/14/x.jpg;
            # 兼容缺 materials/ 前缀的历史 URL。
            candidates = [stored]
            if not stored.startswith("materials/"):
                candidates.append(f"materials/{stored}")
            for rel in candidates:
                local = get_storage().get_local_path(rel)
                if local and Path(local).exists():
                    return local
            full_url = src if src.startswith("http") else (
                f"http://127.0.0.1:5409{src}"
            )
            return ToutiaoPlatform._download_to_temp(
                full_url, stored.split("/")[-1]
            )

        if src.startswith(("http://", "https://")):
            return ToutiaoPlatform._download_to_temp(
                src, Path(urlparse(src).path).name or "img.png"
            )

        p = Path(src)
        if p.exists():
            return str(p)
        raise RuntimeError(f"[文章][头条] 无法解析正文图片 src: {src}")
