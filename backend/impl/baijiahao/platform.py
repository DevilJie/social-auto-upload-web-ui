"""
Baijiahao (百家号) platform implementation -- 100% CloakBrowser.

All browser operations go through ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` which delegate to CloakBrowser (stealth
Chromium) with automatic Playwright fallback.
"""

import asyncio
import os
import time
from datetime import datetime

from util._logger import bind_account_name, get_channel_logger
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    raise_if_page_closed,
    save_login_result,
    scrape_baijiahao_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("baijiahao")


class BaijiahaoPlatform(BasePlatform):
    platform_id = 6
    platform_key = "baijiahao"
    platform_name = "百家号"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 百度系 cookie 全部由 passport.baidu.com 下发，通配 .baidu.com 后对
    # baijiahao.baidu.com / passport.baidu.com / www.baidu.com 都生效。
    platform_cookie_domain = ".baidu.com"

    # Cookie 失效时可能跳到的所有百度账号体系登录/中间页子串。
    # 任一命中即视为失效,不再依赖单一精确业务登录 URL。
    _COOKIE_INVALID_URL_MARKERS = (
        "/builder/theme/bjh/login",
        "passport.baidu.com/v3/login",
        "passport.baidu.com/v3/ucenter",
        "wappass.baidu.com",
        "auth.baidu.com",
    )

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.baidu.com)
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
            f"[baijiahao] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

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
                    # 登录成功后在同一个 session 内补抓 stats(6 项运营数据),
                    # 与 sync_profile 共用同一份抓取逻辑
                    stats_fn=self._login_stats_fn,
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
        stored cookies.  Cookie invalid if:
        - cookie 文件不存在
        - 跳到任意失效 URL marker (见 ``_COOKIE_INVALID_URL_MARKERS``)
        - 跳出了 baijiahao.baidu.com 业务域 (兜底)
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            logger.info("[baijiahao] cookie file not found")
            return False
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

                current_url = page.url or ""
                # 黑名单: 任一失效 marker 命中即视为失效
                for marker in self._COOKIE_INVALID_URL_MARKERS:
                    if marker in current_url:
                        logger.info(
                            f"[baijiahao] cookie expired (matched: {marker})"
                        )
                        return False
                # 业务域兜底: URL 必须在 baijiahao.baidu.com 下才算成功
                if not current_url.startswith(
                    "https://baijiahao.baidu.com/"
                ):
                    logger.info(
                        f"[baijiahao] cookie redirected off-domain: {current_url}"
                    )
                    return False
                logger.info("[baijiahao] cookie valid")
                return True
            except Exception as exc:
                logger.info(f"[baijiahao] cookie check error: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile -- refresh user name / avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """Sync profile info (name, avatar, stats) from Baijiahao.

        抓取流程:
        1. 访问 https://baijiahao.baidu.com/builder/rc/home 抓 name/avatar
        2. 访问 https://baijiahao.baidu.com/ 抓 6 项 stats:
           累计投稿量/累计阅读(播放)量/累计百度搜索量/总粉丝量/累计总收益/近30天分润收益
        3. 同步完成后立即回写 storage_state,把本轮产生的 cookie + localStorage 一并落盘

        卡片显示 3 项(粉丝量/累计阅读(播放)量/累计百度搜索量),其余 3 项进悬浮窗。
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

                # 抓 stats(运营数据)
                try:
                    await page.goto("https://baijiahao.baidu.com/", wait_until="domcontentloaded", timeout=30000)
                    stats = await self._scrape_baijiahao_stats(page)
                except Exception as exc:
                    logger.info(f"[baijiahao] 抓 stats 失败(不影响 name/avatar): {exc}")
                    stats = []

                # 同步完成后立即把 storage_state 写回(关键):
                # 1) cookie 的真实 expires / httponly 等属性
                # 2) 百家号域下产生的 localStorage (userinfo / token 等)
                # 手工导入的 cookie 没有这些数据,不写回后续流程仍会失败。
                try:
                    await context.storage_state(path=cookie_path)
                    logger.info(
                        f"[baijiahao] sync_profile 已回写 storage_state: {cookie_path}"
                    )
                except Exception as e:
                    logger.info(f"[baijiahao] 回写 storage_state 失败: {e}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await browser.close()

    async def _scrape_baijiahao_stats(self, page) -> list:
        """抓取百家号首页 6 项运营数据。

        页面 DOM 结构(参见用户提供的 2026-07-20 抓取样本):
            <div class="FeReactApp-...-filterItem">
                <div class="FeReactApp-...-title">累计投稿量<span>...</span></div>
                <div class="FeReactApp-...-numbers"><span>18</span></div>
                ...
            </div>
        每块 .filterItem 都有 title(指标名)和 numbers(数值)。

        Returns:
            list[dict]: 按 SORT 排序的运营数据列表
        """
        stats = []
        # label_map: 百家号页面上的中文指标名 -> (ICON, SORT, 标准化 NAME)
        # SORT 1-3 是卡片显示的优先项(粉丝/播放量/搜索量);4-6 进悬浮窗
        label_map = {
            "总粉丝量":         ("user",  1, "粉丝"),
            "累计阅读(播放)量": ("play",  2, "播放量"),
            "累计百度搜索量":   ("play",  3, "搜索量"),
            "累计投稿量":       ("edit",  4, "投稿量"),
            "累计总收益":       ("coin",  5, "累计收益"),
            "近30天分润收益":   ("coin",  6, "近30天分润"),
        }

        try:
            try:
                await page.wait_for_selector(".FeReactApp-_3a492ee4f8f1a936-filterItem", timeout=10000)
            except Exception:
                logger.info("[baijiahao stats] 等待 .filterItem 超时")

            raw = await page.evaluate(
                '''() => {
                    const out = [];
                    document.querySelectorAll('.FeReactApp-_3a492ee4f8f1a936-filterItem').forEach(item => {
                        const titleEl = item.querySelector('.FeReactApp-_3a492ee4f8f1a936-title');
                        const numEl = item.querySelector('.FeReactApp-_3a492ee4f8f1a936-numbers span');
                        if (!titleEl || !numEl) return;
                        // title 文本去掉内嵌的 svg/icon 节点,只保留文字
                        const label = (titleEl.textContent || '').trim();
                        const num = (numEl.textContent || '').trim();
                        if (label && num) out.push({label, num});
                    });
                    return out;
                }'''
            )
            for item in raw:
                label = item.get('label', '')
                if label in label_map:
                    icon, sort_no, name = label_map[label]
                    try:
                        count = int(str(item.get('num', '0')).replace(',', '').replace(' ', '').replace('+', '') or '0')
                    except (ValueError, TypeError):
                        count = 0
                    stats.append({"ICON": icon, "COUNT": count, "NAME": name, "SORT": sort_no})
        except Exception as exc:
            logger.info(f"[baijiahao stats] 抓取失败: {exc}")

        stats.sort(key=lambda x: x.get("SORT", 999))
        return stats

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用 _scrape_baijiahao_stats 抓取逻辑。
        """
        try:
            try:
                await page.goto("https://baijiahao.baidu.com/", wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass
            return await self._scrape_baijiahao_stats(page)
        except Exception as exc:
            logger.info(f"[baijiahao login] _login_stats_fn 抓取失败: {exc}")
            return []

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
        # 16:9 横版封面:第一个 cover-container 固定上传 16:9
        thumbnail_landscape_169_path = kwargs.get("thumbnail_landscape_169_path", "") or ""
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
        logger.info("[发布参数] 横版16:9封面: %s", thumbnail_landscape_169_path or "无")
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
                        thumbnail_landscape_169_path=thumbnail_landscape_169_path,
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
        thumbnail_landscape_169_path="",
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
                    raise_if_page_closed(page)
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
                # 百家号封面对应关系固定, 不按视频方向:
                #   第一个 cover-container  → 横屏 16:9 封面
                #   第二个 cover-container  → 竖屏 3:4  封面
                picked_landscape = thumbnail_landscape_169_path or thumbnail_landscape_path
                picked_portrait = thumbnail_portrait_path
                logger.info(
                    "[设置封面] 横版16:9封面=%s, 竖版3:4封面=%s",
                    picked_landscape or "无", picked_portrait or "无",
                )
                logger.info("[设置封面] 开始设置视频封面...")
                await self._set_cover(
                    page,
                    picked_landscape,
                    picked_portrait,
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
            await self.close_browser(browser, is_close_by_code=True)

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
        # 描述为空时不再回落标题，保持为空
        desc_text = (desc or "").strip()[:2000]

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

        # 1. 清空编辑器 + 输入描述文本(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await editor.click()
        await asyncio.sleep(0.3)
        await clear_and_type(page, desc_text, delay=50)
        if desc_text:
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

    # ------------------------------------------------------------------
    # 文章(图文)发布 — 2026-10 侦察实测
    #   编辑器: /builder/rc/edit?type=news
    #   标题: contenteditable DIV(FeEditorApp)
    #   正文: iframe#ueditor_0 → body innerHTML 注入(保存接口 content 字段
    #         直接取 body HTML,已实测生效)
    #   正文图片: .edui-for-insertimage → 弹窗本地上传 → 确认 → 图床
    #         picproxy URL(发布后后台自动转 pics6.baidu.com CDN)
    #   封面: 「选择封面」弹窗,正文有图时自动选中正文首图 → 确定
    #   定时: 「定时发布」弹窗(取消/定时发布,1 小时~7 天)
    #   存草稿: POST /pcui/article/save
    #   发布:   POST /pcui/article/publish(无二次确认弹窗,直接发)
    # ------------------------------------------------------------------

    _ARTICLE_EDITOR_URL = (
        "https://baijiahao.baidu.com/builder/rc/edit?type=news"
    )
    _ARTICLE_TITLE_MAX = 64
    _ARTICLE_TITLE_SEL = '[class*="FeEditorApp"][contenteditable="true"]'
    _ARTICLE_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    )

    def publish_article(self, **kwargs) -> bool:
        """发布文章到百家号(同步入口)。

        kwargs:
            title (*str*) -- 文章标题(2~64 字)
            html (*str*) -- 正文 HTML(img src 为本地素材 URL,自动上传
                百家号图床后替换)
            account_file (*list[str]*) -- cookie 文件名列表
            cover_path (*str*, optional) -- 显式封面(正文无图时用;有正文图
                时封面弹窗自动选中正文首图)
            cover_mode (*str*, optional) -- 封面对布: single(默认)/three;
                three=三图模式(需 3 张图,不足自动退回单图)
            extra_cover_paths (*list[str]*, optional) -- 三图模式第 2/3 张图
            is_draft (*bool*) -- True(默认)= 存草稿;False = 直接发表
            dry_run (*bool*) -- True = 同 is_draft
            schedule_time_str (*str*, optional) -- 定时发布(仅发表模式生效,
                需当前时间后 1 小时~7 天内)
            creation_statement (*str*, optional) -- 创作声明:
                "采用AI生成内容" / 空
            source_declaration (*bool*, optional) -- 勾选「来源说明」
            source_time (*str*, optional) -- 来源说明联动: 来源时间
                (YYYY-MM-DD,选填,缺省当天)
            source_location (*str*, optional) -- 来源说明联动: 来源地点
                ("省/市" 或 "省,市",如 "北京市/北京市")
            podcast (*bool*, optional) -- 智能创作「自动生成播客」
                (平台默认勾选;False 时取消勾选)
        """
        allowed_keys = (
            "title", "html", "account_file", "cover_path",
            "cover_mode", "extra_cover_paths",
            "is_draft", "dry_run", "schedule_time_str",
            "creation_statement", "creation_declaration",
            "source_declaration", "source_time", "source_location",
            "podcast",
        )
        filtered = {k: kwargs[k] for k in allowed_keys if k in kwargs}
        # 统一参数名: creation_statement(与知乎文章一致)作为主入口,
        # creation_declaration 兼容旧调用
        if (
            "creation_statement" in filtered
            and "creation_declaration" not in filtered
        ):
            filtered["creation_declaration"] = filtered[
                "creation_statement"
            ]
        if filtered.get("dry_run", False):
            filtered["is_draft"] = True
        asyncio.run(self._publish_article_one(**{
            k: v for k, v in filtered.items()
            if k != "creation_statement"
        }))
        return True

    async def _publish_article_one(
        self,
        title: str,
        html: str,
        account_file,
        cover_path: str = "",
        cover_mode: str = "single",
        extra_cover_paths=None,
        is_draft: bool = True,
        dry_run: bool = False,
        schedule_time_str: str = "",
        creation_declaration: str = "",
        source_declaration: bool = False,
        source_time: str = "",
        source_location: str = "",
        podcast: bool = True,
    ):
        """单账号图文发布完整流程。"""
        from services.article_html import (
            extract_img_srcs,
            sanitize_article_html,
        )

        logger.info("[文章][百家号] 开始图文发布")
        logger.info("[文章][百家号] 标题: %s", title)
        logger.info("[文章][百家号] 正文 HTML 长度: %d", len(html))
        logger.info(
            "[文章][百家号] 模式: %s", "存草稿" if is_draft else "发表"
        )

        if not (title or "").strip():
            raise RuntimeError("[文章][百家号] 标题不能为空")
        if not (html or "").strip():
            raise RuntimeError("[文章][百家号] 正文不能为空")

        cookie_name = account_file[0] if isinstance(
            account_file, (list, tuple)
        ) else account_file
        cookie_path = str(Path(BASE_DIR / "cookiesFile") / cookie_name)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser,
                storage_state=cookie_path,
                user_agent=self._ARTICLE_UA,
            )
            try:
                page = await context.new_page()
                # 固定视口: 编辑器工具栏项较多, 窗口过窄时「图片」等按钮会被
                # 折叠进「…」溢出菜单, 坐标点击会落空(2026-10 实测)
                try:
                    await page.set_viewport_size(
                        {"width": 1680, "height": 1000}
                    )
                except Exception:
                    pass
                await page.goto(
                    self._ARTICLE_EDITOR_URL, timeout=60000
                )
                await self._wait_article_editor_ready(page)

                # 1. 标题
                await self._fill_article_title(page, title)

                # 2. 正文图片先上传(建立编辑器图片模型, 供封面「正文」tab 用)
                clean_html = sanitize_article_html(html)
                srcs = extract_img_srcs(clean_html)
                img_tags = []
                body_local_paths = []
                if srcs:
                    logger.info(
                        "[文章][百家号] 正文含 %d 张图片,开始上传",
                        len(srcs),
                    )
                    for src in srcs:
                        local = self._resolve_article_image_path(src)
                        body_local_paths.append(local)
                        tag = await self._insert_body_image(page, local)
                        img_tags.append(tag)
                    final_html = clean_html
                    for src, tag in zip(srcs, img_tags):
                        # 用完整 img 标签替换原标签(保留图床 picproxy URL)
                        import re as _re

                        pattern = _re.compile(
                            r"<img[^>]*src=[\"']"
                            + _re.escape(src)
                            + r"[\"'][^>]*>"
                        )
                        final_html = pattern.sub(
                            lambda _m, tag=tag: tag, final_html, count=1
                        )
                else:
                    final_html = clean_html

                # 3. 正文 HTML 注入(含图床 img 标签) — 必须在封面之前:
                #    封面弹窗「正文」tab 自动选正文首图,注入会重置编辑器
                #    DOM,先封面后注入会导致封面校验失效(2026-10 实测)
                await self._set_article_body_html(page, final_html)
                logger.info("[文章][百家号] 正文已注入")

                # 4. 封面(显式封面/三图/正文首图)
                await self._set_article_cover(
                    page,
                    cover_path=cover_path,
                    cover_mode=cover_mode,
                    extra_cover_paths=extra_cover_paths,
                    body_images=body_local_paths,
                )

                # 5. 智能创作「自动生成播客」(平台默认勾选,False 时取消)
                if podcast is False or str(podcast).strip().lower() in (
                    "false", "0",
                ):
                    await self._set_article_podcast(page, False)

                # 6. 创作声明 / 来源说明(来源说明联动 时间+地点)
                if creation_declaration or source_declaration:
                    await self._set_article_declaration(
                        page,
                        ai_content=creation_declaration == "采用AI生成内容",
                        source_note=(
                            bool(source_declaration)
                            or creation_declaration == "来源说明"
                        ),
                        source_time=source_time,
                        source_location=source_location,
                    )

                # 7. 定时(仅发表模式)
                scheduled = False
                if not is_draft and schedule_time_str:
                    try:
                        await self._set_article_schedule(
                            page, schedule_time_str
                        )
                        scheduled = True
                    except Exception as e:
                        logger.warning(
                            "[文章][百家号] 定时设置失败(将立即发表): %s", e
                        )

                # 8. 保存 / 发表
                if is_draft:
                    await self._save_article_draft(page)
                else:
                    await self._publish_article_now(
                        page, scheduled=scheduled
                    )

                await context.storage_state(path=cookie_path)
                logger.info("[文章][百家号] Cookie 状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ---------------------- 文章内部辅助方法 ----------------------

    @staticmethod
    async def _wait_article_editor_ready(page, timeout_s: int = 45):
        """等图文编辑器就绪: 标题 contenteditable + 正文 iframe。"""
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            title_ready = await page.evaluate(
                """(sel) => {
                  const el = document.querySelector(sel);
                  if (!el) return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                }""",
                BaijiahaoPlatform._ARTICLE_TITLE_SEL,
            )
            iframe_ready = await page.evaluate(
                """() => !!document.querySelector('#ueditor_0')"""
            )
            if title_ready and iframe_ready:
                # 关掉可能遮挡的「我知道了」提示
                try:
                    await page.evaluate(
                        """() => {
                          for (const b of document.querySelectorAll(
                              'button')) {
                            if ((b.innerText || '').trim() === '我知道了') {
                              b.click(); return;
                            }
                          }
                        }"""
                    )
                except Exception:
                    pass
                logger.info("[文章][百家号] 编辑器已就绪")
                return
            await asyncio.sleep(1)
        raise RuntimeError("[文章][百家号] 编辑器加载超时")

    @staticmethod
    async def _fill_article_title(page, title: str):
        """标题: contenteditable DIV,先全选清空再逐字输入。"""
        text = (title or "").strip()[: BaijiahaoPlatform._ARTICLE_TITLE_MAX]
        title_el = page.locator(
            BaijiahaoPlatform._ARTICLE_TITLE_SEL
        ).first
        await title_el.wait_for(state="visible", timeout=15000)
        await title_el.click()
        await page.keyboard.press("Control+a")
        await page.keyboard.press("Delete")
        await page.keyboard.type(text)
        await asyncio.sleep(0.6)
        actual = await page.evaluate(
            """(sel) => {
              const el = document.querySelector(sel);
              return el ? (el.innerText || '').trim() : '';
            }""",
            BaijiahaoPlatform._ARTICLE_TITLE_SEL,
        )
        if not actual:
            raise RuntimeError("[文章][百家号] 标题填写失败")
        logger.info("[文章][百家号] 标题已填写: %s", actual[:30])

    @staticmethod
    async def _insert_body_image(page, local_path: str) -> str:
        """正文插图: 图片按钮 → 弹窗(本地图片)上传 → 确认 → 返回 img 标签。

        2026-10 新版弹窗 tab: 本地图片 / AI配图 / 免费正版图库 / 素材库 /
        正版图集 / 网盘图片, 本地上传入口文案「本地上传」,
        file input = input[type=file][accept*=image]。编辑器图床返回
        picproxy URL(发布时后台转 CDN)。
        """
        frame = page.frame_locator("#ueditor_0")
        body = frame.locator("body").first
        before = await body.evaluate(
            "() => document.querySelectorAll('img').length"
        )
        # 1. 打开图片弹窗
        pos = await page.evaluate(
            """() => {
              const el = document.querySelector('.edui-for-insertimage');
              if (!el) return null;
              el.scrollIntoView({block: 'center'});
              const r = el.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not pos:
            raise RuntimeError("[文章][百家号] 未找到图片按钮")
        # 2. 打开弹窗并定位弹窗内的图片 file input
        #    不点「本地上传」: 会弹系统文件选择框, 直接对 input
        #    set_input_files 更稳(2026-10 实测)
        idx = -1
        for attempt in range(3):
            if attempt == 0:
                await page.mouse.click(pos["x"], pos["y"])
            else:
                await page.evaluate(
                    """() => {
                      const el = document.querySelector(
                        '.edui-for-insertimage');
                      if (el) el.click();
                    }"""
                )
            await asyncio.sleep(3)
            deadline = asyncio.get_event_loop().time() + 8
            while asyncio.get_event_loop().time() < deadline:
                raise_if_page_closed(page, action="文章发布")
                idx = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      const dialogs = [...document.querySelectorAll(
                          '.cheetah-modal, [class*=modal], [class*=Modal], '
                        + '[class*=dialog], [class*=Dialog]')]
                        .filter((m) => {
                          if (!vis(m)) return false;
                          const t = (m.innerText || '');
                          return t.includes('本地图片')
                            || t.includes('本地上传');
                        });
                      dialogs.sort((a, b) =>
                        (a.innerText || '').length
                        - (b.innerText || '').length);
                      if (!dialogs.length) return -1;
                      const d = dialogs[0];
                      d.id = '__bjh_img_dialog';
                      return 1;
                    }"""
                )
                if idx is not None and idx >= 0:
                    break
                await asyncio.sleep(1)
            if idx is not None and idx >= 0:
                break
            logger.warning(
                "[文章][百家号] 图片弹窗未就绪(第 %d 次重试)", attempt + 1
            )
            await asyncio.sleep(1.5)
        if idx is None or idx < 0:
            raise RuntimeError(
                "[文章][百家号] 图片弹窗未出现/file input 未找到"
            )
        finp = page.locator(
            '#__bjh_img_dialog input[type=file]'
        ).first
        await finp.wait_for(state="attached", timeout=10000)
        await finp.set_input_files(local_path)
        # 3. 等上传完成(进入裁剪态出现「N张上传成功」且「确认」可用)
        deadline = asyncio.get_event_loop().time() + 60
        uploaded = False
        probe = 0
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            state = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const d = document.getElementById('__bjh_img_dialog');
                  // 确认按钮可能挂在弹窗根的 footer(不在标记容器内),
                  // 这里全局找可见且可点的「确认」
                  const okBtns = [...document.querySelectorAll('button')]
                    .filter((b) => vis(b)
                      && (b.innerText || '').includes('确认') && !b.disabled);
                  return {
                    dialog: !!(d && vis(d)),
                    ok: okBtns.length > 0,
                    text: d ? (d.innerText || '').replace(/\\s+/g, ' ')
                      .slice(0, 200) : '',
                  };
                }"""
            )
            if probe < 3:
                logger.info(
                    "[文章][百家号] 图片弹窗状态: ok=%s text=%s",
                    (state or {}).get("ok"),
                    (state or {}).get("text"),
                )
                probe += 1
            if state.get("ok"):
                uploaded = True
                break
            await asyncio.sleep(1.5)
        if not uploaded:
            raise RuntimeError("[文章][百家号] 图片上传超时")
        # 4. 点「确认」(可见且可用)
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const btns = [...document.querySelectorAll('button')]
                .filter((b) => vis(b)
                  && (b.innerText || '').includes('确认') && !b.disabled);
              if (!btns.length) return false;
              btns[btns.length - 1].click();
              return true;
            }"""
        )
        if not clicked:
            raise RuntimeError("[文章][百家号] 图片弹窗确认按钮未找到")
        # 6. 等图片插入 iframe
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            cur = await body.evaluate(
                "() => document.querySelectorAll('img').length"
            )
            if cur > before:
                break
            await asyncio.sleep(1)
        await asyncio.sleep(1.5)
        # 7. 取最后一张 img 的完整标签
        tag = await body.evaluate(
            """() => {
              const imgs = [...document.querySelectorAll('img')];
              const im = imgs[imgs.length - 1];
              return im ? im.outerHTML : '';
            }"""
        )
        if not tag:
            raise RuntimeError("[文章][百家号] 图片插入失败")
        logger.info(
            "[文章][百家号] 正文图片已上传: %s...",
            tag[:80],
        )
        return tag

    @staticmethod
    async def _clear_article_body(page):
        frame = page.frame_locator("#ueditor_0")
        await frame.locator("body").first.evaluate(
            """() => {
              document.body.innerHTML = '<p><br></p>';
              document.body.dispatchEvent(
                new InputEvent('input', {bubbles: true}));
            }"""
        )
        await asyncio.sleep(1)

    @staticmethod
    async def _set_article_body_html(page, html: str):
        """正文 HTML 注入。

        优先用编辑器官方 API ``UE_V2.instants[*].setContent``(写入编辑器
        内部模型,保存/发布时稳定);失败回退 DOM innerHTML + input 事件。
        """
        method = await page.evaluate(
            """(html) => {
              try {
                const ue = window.UE_V2;
                const inst = ue && ue.instants
                  ? Object.values(ue.instants)[0] : null;
                if (inst && typeof inst.setContent === 'function') {
                  inst.setContent(html);
                  if (typeof inst.fireEvent === 'function') {
                    try { inst.fireEvent('contentchange'); } catch (e) {}
                  }
                  return 'ue';
                }
              } catch (e) {}
              const ifr = document.querySelector('#ueditor_0');
              const doc = ifr && ifr.contentDocument;
              if (!doc || !doc.body) return 'no-iframe';
              doc.body.innerHTML = html;
              doc.body.dispatchEvent(
                new InputEvent('input', {bubbles: true}));
              return 'dom';
            }""",
            html,
        )
        if method == "no-iframe":
            raise RuntimeError("[文章][百家号] 正文 iframe 不可用")
        # 校验正文长度(读 iframe 实际渲染)
        await asyncio.sleep(2)
        try:
            frame = page.frame_locator("#ueditor_0")
            length = await frame.locator("body").first.evaluate(
                "() => document.body.innerHTML.length"
            )
        except Exception:
            length = 0
        if not length or length < 10:
            raise RuntimeError(
                f"[文章][百家号] 正文注入后内容过短"
                f"(length={length}, method={method})"
            )
        logger.info(
            "[文章][百家号] 正文已注入(%s, innerHTML %d)", method, length
        )

    @staticmethod
    async def _set_article_cover(
        page, cover_path: str = "", cover_mode: str = "single",
        extra_cover_paths=None, body_images=None,
    ):
        """设置封面(平台「发文设置」必填项,支持单图/三图)。

        - cover_mode="three": 切到「三图」,依次给 3 个槽位上传封面;
          图片来源 = 显式封面 + extra_cover_paths + 正文图片;
          不足 3 张时退回单图并在日志中告警。
        - cover_path 给出: 走「本地上传」显式上传该图。
        - 未给出 cover_path: 保持原行为 —— 打开弹窗后点「确定」,
          正文有图时平台自动选中正文首图。
        """
        extra = [
            str(p) for p in (extra_cover_paths or [])
            if p and Path(str(p)).exists()
        ]
        body = [
            str(p) for p in (body_images or [])
            if p and Path(str(p)).exists()
        ]
        single = str(cover_path) if cover_path else ""
        want_three = str(cover_mode or "").strip().lower() in (
            "three", "3", "三图",
        )

        if want_three:
            imgs = []
            for p in ([single] if single else []) + extra + body:
                if p and Path(p).exists() and p not in imgs:
                    imgs.append(p)
            if len(imgs) < 3:
                logger.warning(
                    "[文章][百家号] 三图模式需要 3 张封面,实际 %d 张,"
                    "退回单图", len(imgs),
                )
                want_three = False
            else:
                picked = await BaijiahaoPlatform._set_cover_layout(
                    page, "三图"
                )
                if not picked:
                    logger.warning(
                        "[文章][百家号] 未找到「三图」开关,按单图处理"
                    )
                    want_three = False

        if want_three:
            # 三图: 每次都点「第一个空的 选择封面」槽位, 直到填满 3 张
            # (已填槽位的文案会变成「编辑/更换」, 因此始终取列表首项)
            target = 3
            for idx in range(target + 2):
                filled = await BaijiahaoPlatform._count_cover_imgs(page)
                if filled >= target:
                    break
                img = imgs[min(filled, len(imgs) - 1)]
                ok = await BaijiahaoPlatform._upload_one_cover_slot(
                    page, img, slot_index=0
                )
                now = await BaijiahaoPlatform._count_cover_imgs(page)
                logger.info(
                    "[文章][百家号] 三图封面 %d/3: %s (当前 %d 张)",
                    idx + 1, "ok" if ok else "失败", now,
                )
                if now <= filled:
                    logger.warning(
                        "[文章][百家号] 第 %d 张封面未生效(跳过)", idx + 1
                    )
            await asyncio.sleep(2)
            filled_now = await BaijiahaoPlatform._count_cover_imgs(page)
            logger.info(
                "[文章][百家号] 三图封面已设置: %d 张", filled_now
            )
            if filled_now >= 3:
                return
            # 平台三图槽位上传不稳定(第 3 张可能不生效) → 回退单图,
            # 保证「设置封面」必填项有值, 不阻塞发布
            logger.warning(
                "[文章][百家号] 三图仅成功 %d 张, 回退单图模式", filled_now
            )
            await BaijiahaoPlatform._set_cover_layout(page, "单图")
            await asyncio.sleep(2)
            if await BaijiahaoPlatform._count_cover_imgs(page) >= 1:
                return
            ok = await BaijiahaoPlatform._upload_one_cover_slot(
                page, imgs[0], slot_index=0
            )
            logger.info(
                "[文章][百家号] 单图封面上传: %s", "ok" if ok else "失败"
            )
            return

        if single and Path(single).exists():
            ok = await BaijiahaoPlatform._upload_one_cover_slot(
                page, single, slot_index=0
            )
            if ok:
                logger.info("[文章][百家号] 显式封面已设置: %s", single)
                return
            logger.warning(
                "[文章][百家号] 显式封面上传失败,尝试正文首图兜底"
            )

        # 兜底: 打开弹窗直接确定(正文有图时自动选中正文首图)
        pos = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const el = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && (e.innerText || '').trim() === '选择封面'
                  && e.getBoundingClientRect().height < 60);
              if (!el) return null;
              el.scrollIntoView({block: 'center'});
              const r = el.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not pos:
            logger.warning("[文章][百家号] 未找到选择封面入口(跳过)")
            return
        await page.mouse.click(pos["x"], pos["y"])
        await asyncio.sleep(3)
        clicked = await page.evaluate(
            """() => {
              const m = [...document.querySelectorAll('.cheetah-modal')]
                .filter((e) => e.getBoundingClientRect().width > 0)[0];
              if (!m) return false;
              for (const b of m.querySelectorAll('button')) {
                if ((b.innerText || '').includes('确定') && !b.disabled) {
                  b.click(); return true;
                }
              }
              return false;
            }"""
        )
        if not clicked:
            logger.warning(
                "[文章][百家号] 封面弹窗确定不可用(正文无图?),封面跳过"
            )
            # 关闭弹窗
            try:
                await page.evaluate(
                    """() => {
                      const m = [...document.querySelectorAll(
                          '.cheetah-modal')]
                        .filter((e) => e.getBoundingClientRect().width > 0)[0];
                      if (!m) return;
                      for (const b of m.querySelectorAll('button')) {
                        if ((b.innerText || '').trim() === '取消') {
                          b.click(); return;
                        }
                      }
                    }"""
                )
            except Exception:
                pass
            return
        await asyncio.sleep(3)
        logger.info("[文章][百家号] 封面已设置(正文首图)")

    @staticmethod
    async def _set_cover_layout(page, layout_text: str) -> bool:
        """切换封面布局(「单图」/「三图」radio)。"""
        return await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const lbs = [...document.querySelectorAll('label')]
                .filter(vis)
                .filter((e) => (e.innerText || '').trim() === text);
              if (!lbs.length) return false;
              lbs[0].scrollIntoView({block: 'center'});
              lbs[0].click();
              return true;
            }""",
            layout_text,
        )

    @staticmethod
    async def _count_cover_imgs(page) -> int:
        """统计「设置封面」区已填封面数量。"""
        return await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              for (const it of document.querySelectorAll('.cheetah-form-item')) {
                if (!vis(it)) continue;
                const lab = it.querySelector('.cheetah-form-item-label');
                if (!lab || !(lab.innerText || '').includes('设置封面')) continue;
                const imgs = [...it.querySelectorAll('img')].filter((i) =>
                  vis(i) && i.getBoundingClientRect().width > 40);
                return imgs.length;
              }
              return 0;
            }"""
        )

    @staticmethod
    async def _upload_one_cover_slot(
        page, local_path: str, slot_index: int = 0
    ) -> bool:
        """上传一张封面到第 slot_index 个「选择封面」槽位。

        流程: 点该槽位「选择封面」→ 弹窗 file input set_input_files →
        等「确定」可用 → 点确定。
        """
        pos = await page.evaluate(
            """(idx) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const els = [...document.querySelectorAll('*')]
                .filter(vis)
                .filter((e) => (e.innerText || '').trim() === '选择封面'
                  && e.getBoundingClientRect().height < 60);
              if (!els.length) return null;
              const el = els[Math.min(idx, els.length - 1)];
              el.scrollIntoView({block: 'center'});
              const r = el.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                      total: els.length};
            }""",
            slot_index,
        )
        if not pos:
            return False
        await page.mouse.click(pos["x"], pos["y"])
        await asyncio.sleep(2.5)
        # 只对「当前可见」的封面弹窗操作(历史弹窗节点会残留在 DOM)
        marked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const m = [...document.querySelectorAll('.cheetah-modal')]
                .filter((e) => vis(e))[0];
              if (!m) return false;
              m.id = '__bjh_cover_modal';
              return true;
            }"""
        )
        if not marked:
            logger.warning("[文章][百家号] 封面上传弹窗未出现")
            await BaijiahaoPlatform._close_cover_modal(page)
            return False
        finp = page.locator('#__bjh_cover_modal input[type=file]').first
        try:
            await finp.wait_for(state="attached", timeout=10000)
            await finp.set_input_files(local_path)
        except Exception as e:
            logger.warning("[文章][百家号] 封面 file input 上传失败: %s", e)
            await BaijiahaoPlatform._close_cover_modal(page)
            return False
        # 等「确定」可用(上传完成 + 图片可裁)
        loop = asyncio.get_event_loop()
        deadline = loop.time() + 30
        ready = False
        while loop.time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            ready = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const m = document.getElementById('__bjh_cover_modal');
                  if (!m || !vis(m)) return false;
                  return [...m.querySelectorAll('button')].some(
                    (b) => (b.innerText || '').includes('确定')
                      && !b.disabled && vis(b));
                }"""
            )
            if ready:
                break
            await asyncio.sleep(1.5)
        if not ready:
            logger.warning("[文章][百家号] 封面「确定」一直不可用")
            await BaijiahaoPlatform._close_cover_modal(page)
            return False
        ok = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const m = document.getElementById('__bjh_cover_modal');
              if (!m || !vis(m)) return false;
              for (const b of m.querySelectorAll('button')) {
                if (!vis(b)) continue;
                if ((b.innerText || '').includes('确定') && !b.disabled) {
                  b.click(); return true;
                }
              }
              return false;
            }"""
        )
        await asyncio.sleep(3)
        return bool(ok)

    @staticmethod
    async def _close_cover_modal(page):
        """关闭封面弹窗(点取消)。"""
        try:
            await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const m = [...document.querySelectorAll('.cheetah-modal')]
                    .filter(vis)[0];
                  if (!m) return;
                  for (const b of m.querySelectorAll('button')) {
                    if ((b.innerText || '').trim() === '取消') {
                      b.click(); return;
                    }
                  }
                }"""
            )
            await asyncio.sleep(1)
        except Exception:
            pass

    @staticmethod
    async def _set_article_podcast(page, enabled: bool):
        """智能创作「自动生成播客」开关(平台默认勾选)。"""
        state = None
        for _ in range(3):
            state = await page.evaluate(
                """(want) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const labels = [...document.querySelectorAll('label')]
                    .filter(vis)
                    .filter((e) =>
                      (e.innerText || '').includes('自动生成播客'));
                  if (!labels.length) return null;
                  const lb = labels[0];
                  const cb = lb.querySelector('input[type=checkbox]');
                  if (!cb) return null;
                  if (!!cb.checked !== want) {
                    // 先点 label(React 绑在 label 上), 不行再点 input
                    lb.click();
                  }
                  return !!cb.checked;
                }""",
                enabled,
            )
            await asyncio.sleep(1.2)
            state = await page.evaluate(
                """() => {
                  const labels = [...document.querySelectorAll('label')]
                    .filter((e) =>
                      (e.innerText || '').includes('自动生成播客'));
                  if (!labels.length) return null;
                  const cb = labels[0].querySelector(
                    'input[type=checkbox]');
                  return cb ? !!cb.checked : null;
                }"""
            )
            if state == enabled:
                break
        logger.info(
            "[文章][百家号] 自动生成播客: 目标=%s 实际=%s",
            "勾选" if enabled else "取消勾选",
            "已勾选" if state else "未勾选/未找到",
        )

    @staticmethod
    async def _set_article_declaration(
        page, ai_content: bool = False, source_note: bool = False,
        source_time: str = "", source_location: str = "",
    ):
        """创作声明: 「采用AI生成内容」/「来源说明」复选框。

        勾选「来源说明」后平台联动出现两个必填项:
        - 来源时间: ``input[placeholder="请选择时间"]`` (日期选择)
        - 来源地点: 省/市二级级联 (cheetah-cascader)
        保存接口对应 ``event_spec[time]`` / ``event_spec[pos]``。

        cheetah-checkbox 结构: label.cheetah-checkbox-wrapper > input。
        点击后 React 异步更新 checked,需延迟回读确认。
        """
        for label_text, want in (
            ("采用AI生成内容", ai_content),
            ("来源说明", source_note),
        ):
            if not want:
                continue
            clicked = await page.evaluate(
                """(labelText) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const labels = [...document.querySelectorAll(
                      'label.cheetah-checkbox-wrapper, label')]
                    .filter(vis)
                    .filter((e) => (e.innerText || '').includes(labelText));
                  for (const lb of labels) {
                    const cb = lb.querySelector(
                      'input[type=checkbox]');
                    if (!cb) continue;
                    if (!cb.checked) cb.click();
                    return true;
                  }
                  return false;
                }""",
                label_text,
            )
            await asyncio.sleep(1)
            state = await page.evaluate(
                """(labelText) => {
                  const labels = [...document.querySelectorAll(
                      'label.cheetah-checkbox-wrapper, label')]
                    .filter((e) => (e.innerText || '').includes(labelText));
                  for (const lb of labels) {
                    const cb = lb.querySelector(
                      'input[type=checkbox]');
                    if (cb) return cb.checked;
                  }
                  return null;
                }""",
                label_text,
            )
            logger.info(
                "[文章][百家号] 声明「%s」: %s",
                label_text,
                "已勾选" if state else "未勾选/未找到",
            )
        if source_note:
            # 来源说明联动项: 时间 + 地点
            if source_time:
                ok = await BaijiahaoPlatform._set_source_time(
                    page, source_time
                )
                logger.info(
                    "[文章][百家号] 来源时间「%s」: %s",
                    source_time, "已设置" if ok else "设置失败/跳过",
                )
            if source_location:
                ok = await BaijiahaoPlatform._set_source_location(
                    page, source_location
                )
                logger.info(
                    "[文章][百家号] 来源地点「%s」: %s",
                    source_location, "已设置" if ok else "设置失败/跳过",
                )
        await asyncio.sleep(1)

    @staticmethod
    def _parse_source_location(location: str) -> tuple[str, str]:
        """把 "北京市/北京市" / "广东省,深圳市" 解析为 (省, 市)。"""
        import re as _re

        parts = [
            p.strip() for p in _re.split(r"[/,，、|]", str(location or ""))
            if p.strip()
        ]
        if not parts:
            return "", ""
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    @staticmethod
    async def _set_source_time(page, date_str: str) -> bool:
        """来源说明联动: 来源时间(日期选择,默认今天)。"""
        from datetime import datetime as _dt

        try:
            dt = _dt.strptime(str(date_str).strip()[:10], "%Y-%m-%d")
        except ValueError:
            dt = _dt.now()
        # 1. 点开日期输入
        pos = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const inp = [...document.querySelectorAll(
                  '[class*=sourceDatePicker] input, '
                + 'input[placeholder="请选择时间"]')].filter(vis)[0];
              if (!inp) return null;
              inp.scrollIntoView({block: 'center'});
              const r = inp.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not pos:
            return False
        await page.mouse.click(pos["x"], pos["y"])
        await asyncio.sleep(2)
        # 等日历面板出现
        panel_ready = False
        for _ in range(10):
            panel_ready = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      '.cheetah-picker-dropdown, [class*=picker-panel], '
                    + '[class*=picker-dropdown], [class*=calendar], '
                    + '[class*=Calendar]')].some(vis);
                }"""
            )
            if panel_ready:
                break
            await asyncio.sleep(0.8)
        # 2. 翻到目标月份(最多翻 12 个月)
        for _ in range(12):
            header = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      '.cheetah-picker-header, [class*=picker-header], '
                    + '[class*=PickerHeader]')].filter(vis)
                    .map((e) => (e.innerText || '').trim()).join('|');
                }"""
            )
            if not header:
                break
            flat = header.replace(" ", "")
            if str(dt.year) in flat and f"{dt.month}月" in flat:
                break
            await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const btns = [...document.querySelectorAll(
                      '.cheetah-picker-header button, '
                    + '[class*=picker-header] button, '
                    + '[class*=picker-header] [class*=icon]')].filter(vis);
                  if (btns.length) btns[btns.length - 1].click();
                }"""
            )
            await asyncio.sleep(0.6)
        # 3. 点目标日(限定在日历面板内,避免命中表格 td)
        picked = await page.evaluate(
            """(day) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const panels = [...document.querySelectorAll(
                  '.cheetah-picker-dropdown, [class*=picker-panel], '
                + '[class*=picker-dropdown]')].filter(vis);
              const scope = panels.length ? panels[0] : document;
              const cells = [...scope.querySelectorAll(
                  '.cheetah-picker-cell, [class*=picker-cell], td')]
                .filter(vis)
                .filter((e) => {
                  const cls = String(e.className);
                  return !cls.includes('prev') && !cls.includes('next')
                    && !cls.includes('disabled');
                });
              for (const c of cells) {
                if ((c.innerText || '').trim() === String(day)) {
                  c.click(); return true;
                }
              }
              return false;
            }""",
            dt.day,
        )
        await asyncio.sleep(1.5)
        actual = await page.evaluate(
            """() => {
              const inp = document.querySelector(
                '[class*=sourceDatePicker] input, '
                + 'input[placeholder="请选择时间"]');
              return inp ? (inp.value || '').trim() : '';
            }"""
        )
        if picked and actual:
            logger.info("[文章][百家号] 来源日期已选: %s", actual)
            return True
        # 兜底: 直接写 input(React 受控值)
        try:
            await page.evaluate(
                """(val) => {
                  const inp = document.querySelector(
                    '[class*=sourceDatePicker] input, '
                    + 'input[placeholder="请选择时间"]');
                  if (!inp) return;
                  const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                  setter.call(inp, val);
                  inp.dispatchEvent(new Event('input', {bubbles: true}));
                  inp.dispatchEvent(new Event('change', {bubbles: true}));
                }""",
                dt.strftime("%Y-%m-%d"),
            )
            await asyncio.sleep(1)
        except Exception:
            pass
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        return False

    @staticmethod
    async def _set_source_location(page, location: str) -> bool:
        """来源说明联动: 来源地点(省/市二级级联)。"""
        province, city = BaijiahaoPlatform._parse_source_location(location)
        if not province:
            return False
        pos = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const w = [...document.querySelectorAll(
                  '.cheetah-cascader')].filter(vis)[0];
              if (!w) return null;
              w.scrollIntoView({block: 'center'});
              const r = w.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not pos:
            return False
        await page.mouse.click(pos["x"], pos["y"])
        await asyncio.sleep(1.5)
        ok_prov = await page.evaluate(
            """(name) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const menus = [...document.querySelectorAll(
                  '.cheetah-cascader-menus')].filter(vis)[0];
              if (!menus) return false;
              const uls = [...menus.querySelectorAll('ul')].filter(vis);
              if (!uls.length) return false;
              const items = [...uls[0].querySelectorAll('li')].filter(vis);
              let target = items.find((li) =>
                (li.innerText || '').trim() === name);
              if (!target) {
                target = items.find((li) => {
                  const t = (li.innerText || '').trim();
                  return t.includes(name) || name.includes(t);
                });
              }
              if (!target) return false;
              target.click();
              return true;
            }""",
            province,
        )
        await asyncio.sleep(1.2)
        if not ok_prov:
            logger.warning("[文章][百家号] 来源省份未找到: %s", province)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return False
        ok_city = await page.evaluate(
            """(name) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const menus = [...document.querySelectorAll(
                  '.cheetah-cascader-menus')].filter(vis)[0];
              if (!menus) return false;
              const uls = [...menus.querySelectorAll('ul')].filter(vis);
              if (uls.length < 2) return true;
              const items = [...uls[1].querySelectorAll('li')].filter(vis);
              if (!items.length) return true;
              let target = items.find((li) =>
                (li.innerText || '').trim() === name);
              if (!target) {
                target = items.find((li) => {
                  const t = (li.innerText || '').trim();
                  return t.includes(name) || name.includes(t);
                });
              }
              (target || items[0]).click();
              return true;
            }""",
            city,
        )
        await asyncio.sleep(1.5)
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        actual = await page.evaluate(
            """() => {
              const w = [...document.querySelectorAll('.cheetah-cascader')]
                .filter((e) => e.getBoundingClientRect().width > 0)[0];
              return w ? (w.innerText || '').trim() : '';
            }"""
        )
        logger.info(
            "[文章][百家号] 来源地点已设置: %s",
            (actual or "").replace("\n", " "),
        )
        return bool(ok_city)

    @staticmethod
    async def _set_article_schedule(page, schedule_time_str: str):
        """定时发布: 弹窗「定时发文」(日期/时/分 + 定时发布按钮)。"""
        from datetime import datetime as _dt

        dt = _dt.strptime(schedule_time_str.strip(), "%Y-%m-%d %H:%M:%S")
        now = _dt.now()
        diff_h = (dt - now).total_seconds() / 3600
        if not (1.0 <= diff_h <= 7 * 24):
            raise RuntimeError(
                "[文章][百家号] 定时时间需在当前时间后 1 小时~7 天内"
            )
        # 1. 打开定时弹窗
        pos = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const el = [...document.querySelectorAll('*')].find(
                (e) => vis(e) && (e.innerText || '').trim() === '定时发布'
                  && e.getBoundingClientRect().height < 50);
              if (!el) return null;
              el.scrollIntoView({block: 'center'});
              const r = el.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not pos:
            raise RuntimeError("未找到定时发布按钮")
        await page.mouse.click(pos["x"], pos["y"])
        await asyncio.sleep(3)
        modal = await page.evaluate(
            """() => {
              const m = [...document.querySelectorAll('.cheetah-modal')]
                .filter((e) => e.getBoundingClientRect().width > 0)
                .find((e) => (e.innerText || '').includes('定时发文'));
              return !!m;
            }"""
        )
        if not modal:
            raise RuntimeError("定时发文弹窗未打开")
        # 2. 填日期(点击日期输入 → 日历 → 选日)
        await BaijiahaoPlatform._pick_article_schedule_date(page, dt)
        # 3. 选时/分
        await BaijiahaoPlatform._pick_article_schedule_time(page, dt)
        # 4. 点弹窗内「定时发布」
        clicked = await page.evaluate(
            """() => {
              const m = [...document.querySelectorAll('.cheetah-modal')]
                .filter((e) => e.getBoundingClientRect().width > 0)
                .find((e) => (e.innerText || '').includes('定时发文'));
              if (!m) return false;
              for (const b of m.querySelectorAll('button')) {
                if ((b.innerText || '').trim() === '定时发布'
                    && !b.disabled) {
                  b.click(); return true;
                }
              }
              return false;
            }"""
        )
        if not clicked:
            raise RuntimeError("定时发文弹窗确认按钮不可用")
        await asyncio.sleep(3)
        logger.info(
            "[文章][百家号] 定时发布已设置: %s",
            dt.strftime("%Y-%m-%d %H:%M"),
        )

    @staticmethod
    async def _pick_article_schedule_date(page, dt):
        """定时弹窗选日期: 点日期输入 → 日历选日。"""
        inp = await page.evaluate(
            """() => {
              const m = [...document.querySelectorAll('.cheetah-modal')]
                .filter((e) => e.getBoundingClientRect().width > 0)
                .find((e) => (e.innerText || '').includes('定时发文'));
              if (!m) return null;
              const inputs = [...m.querySelectorAll('input')]
                .filter((i) => i.getBoundingClientRect().width > 0);
              if (!inputs.length) return null;
              const r = inputs[0].getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not inp:
            raise RuntimeError("定时弹窗日期输入未找到")
        await page.mouse.click(inp["x"], inp["y"])
        await asyncio.sleep(2)
        # 日历: 点目标日(优先匹配「日」数字按钮/单元格)
        clicked = await page.evaluate(
            """(day) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const cands = [...document.querySelectorAll(
                  '.cheetah-picker-cell, td, [class*=cell], [class*=day]')]
                .filter(vis)
                .filter((el) => {
                  const t = (el.innerText || '').trim();
                  return t === String(day);
                });
              if (!cands.length) return false;
              // 取最后一个(当前月)
              cands[cands.length - 1].click();
              return true;
            }""",
            dt.day,
        )
        if not clicked:
            raise RuntimeError("定时弹窗日历未找到目标日期")
        await asyncio.sleep(1.5)

    @staticmethod
    async def _pick_article_schedule_time(page, dt):
        """定时弹窗选 时/分(下拉选项)。"""
        for idx, (val, suffix) in enumerate(
            ((dt.hour, "点"), (dt.minute, "分"))
        ):
            pos = await page.evaluate(
                """(idx) => {
                  const m = [...document.querySelectorAll('.cheetah-modal')]
                    .filter((e) => e.getBoundingClientRect().width > 0)
                    .find((e) => (e.innerText || '').includes('定时发文'));
                  if (!m) return null;
                  const inputs = [...m.querySelectorAll('input')]
                    .filter((i) => i.getBoundingClientRect().width > 0);
                  if (inputs.length <= idx + 1) return null;
                  const r = inputs[idx + 1].getBoundingClientRect();
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                }""",
                idx,
            )
            if not pos:
                raise RuntimeError("定时弹窗时间输入未找到")
            await page.mouse.click(pos["x"], pos["y"])
            await asyncio.sleep(1.5)
            # 选项: 文本为「N点」/「N分」
            target = f"{val}{suffix}"
            ok = await page.evaluate(
                """(target) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const cands = [...document.querySelectorAll(
                      '[class*=option], li, [role=option], '
                    + '[class*=item], [class*=Item]')]
                    .filter(vis)
                    .filter((el) => (el.innerText || '').trim() === target);
                  if (!cands.length) return false;
                  cands[cands.length - 1].click();
                  return true;
                }""",
                target,
            )
            if not ok:
                raise RuntimeError(f"定时弹窗未找到选项: {target}")
            await asyncio.sleep(1.5)

    @staticmethod
    async def _save_article_draft(page):
        """存草稿: 点「存草稿」→ 等保存接口/成功提示。"""
        # 关掉可能残留的弹窗(否则遮罩拦截点击)
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.8)
        except Exception:
            pass
        saved = asyncio.Event()

        def _on_resp(resp):
            try:
                if "/pcui/article/save" in resp.url:
                    saved.set()
            except Exception:
                pass

        page.on("response", _on_resp)
        # 用真实鼠标点击: 找最小的可见「存草稿」元素坐标
        pos = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const els = [...document.querySelectorAll('button, div, span, a')]
                .filter(vis)
                .filter((e) => (e.innerText || '').trim() === '存草稿');
              els.sort((a, b) => {
                const ra = a.getBoundingClientRect();
                const rb = b.getBoundingClientRect();
                return ra.width * ra.height - rb.width * rb.height;
              });
              if (!els.length) return null;
              const r = els[0].getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                      disabled: !!els[0].disabled};
            }"""
        )
        if not pos:
            raise RuntimeError("[文章][百家号] 存草稿按钮未找到")
        logger.info("[文章][百家号] 点击存草稿(disabled=%s)", pos.get("disabled"))
        await page.mouse.click(pos["x"], pos["y"])
        try:
            await asyncio.wait_for(saved.wait(), timeout=30)
            logger.info("[文章][百家号] ✓ 已存草稿")
        except asyncio.TimeoutError:
            # 兜底: 看成功提示
            toast = await page.evaluate(
                """() => {
                  const t = (document.body.innerText || '');
                  return t.includes('存入草稿') || t.includes('保存成功')
                    || t.includes('已保存');
                }"""
            )
            if not toast:
                try:
                    await page.screenshot(
                        path=str(
                            Path(BASE_DIR / "logs"
                                 / "baijiahao_draft_failed.png")
                        ),
                        full_page=True,
                    )
                except Exception:
                    pass
                raise RuntimeError("[文章][百家号] 存草稿超时")
            logger.warning("[文章][百家号] 保存接口未捕获,但页面有成功提示")
        try:
            page.remove_listener("response", _on_resp)
        except Exception:
            pass
        await asyncio.sleep(2)

    @staticmethod
    async def _publish_article_now(page, scheduled: bool = False):
        """发表: 点「发布」→ 监听 /pcui/article/publish 响应判定成功。

        注意: expect_response 必须在点击之前注册,否则会错过请求。
        """
        import json as _json

        # 点击放 expect_response 上下文内
        try:
            async with page.expect_response(
                lambda r: "/pcui/article/publish" in r.url
                          and r.request.method == "POST",
                timeout=90000,
            ) as resp_info:
                # 优先 Playwright 原生点击(实测可靠);失败回退 JS 点击
                clicked = False
                try:
                    await page.locator(
                        'button.cheetah-btn-primary:has-text("发布")'
                    ).first.click(timeout=8000)
                    clicked = True
                except Exception:
                    clicked = await page.evaluate(
                        """() => {
                          const vis = (el) => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                          };
                          const el = [...document.querySelectorAll(
                              'button')]
                            .find((e) => vis(e)
                              && (e.innerText || '').trim() === '发布');
                          if (!el) return false;
                          el.click();
                          return true;
                        }"""
                    )
        except Exception as exc:
            raise RuntimeError(
                f"[文章][百家号] 发布接口无响应: {exc}"
            )
        if not clicked:
            raise RuntimeError("[文章][百家号] 发布按钮未找到")
        logger.info("[文章][百家号] 已点击发布,等待结果...")
        response = await resp_info.value
        body = None
        try:
            body = await response.json()
        except Exception:
            pass
        logger.info(
            "[文章][百家号] 发布响应: %s",
            _json.dumps(body, ensure_ascii=False)[:500]
            if body is not None else "(非 JSON)",
        )
        ok = False
        msg = ""
        if isinstance(body, dict):
            errno = body.get("errno")
            code = body.get("code")
            msg = str(
                body.get("errmsg") or body.get("message") or ""
            )
            if errno == 0 or code == 0:
                ok = True
            elif errno is not None or code is not None:
                raise RuntimeError(
                    f"[文章][百家号] 发表失败: errno={errno} "
                    f"code={code} msg={msg}"
                )
        if not ok:
            # 无明确错误码时,以 HTTP 2xx + 无错误提示视为成功(弱判定)
            if response.status == 200 and not msg:
                ok = True
                logger.warning(
                    "[文章][百家号] 发布响应无明确 code,按 HTTP 200 视为成功"
                )
            else:
                raise RuntimeError(
                    f"[文章][百家号] 发表失败(HTTP {response.status}): "
                    f"{msg or '未知错误'}"
                )
        # 等页面跳转(软校验)
        await asyncio.sleep(5)
        logger.info("[文章][百家号] ✓ 发表成功")

    @staticmethod
    def _resolve_article_image_path(src: str) -> str:
        """把正文 img src 解析为本地文件路径(上传图床用)。

        支持素材库 URL(/api/materials/file/...)、本地绝对路径、
        data: URL、外链 http(s)(下载到临时文件)。
        """
        import base64
        import mimetypes
        import tempfile
        import urllib.request
        from urllib.parse import unquote

        from storage import get_storage

        if src.startswith("data:"):
            head, _, b64 = src.partition(",")
            mime = head[5:].split(";")[0] or "image/png"
            ext = mimetypes.guess_extension(mime) or ".png"
            fd, path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(b64))
            return path

        marker = "/api/materials/file/"
        stored = ""
        if marker in src:
            stored = unquote(src.split(marker, 1)[1].split("?")[0])
        if stored:
            local = get_storage().get_local_path(stored)
            if local and Path(local).exists():
                return local
            full_url = src if src.startswith("http") else (
                f"http://127.0.0.1:5409{src}"
            )
            return BaijiahaoPlatform._download_to_temp(full_url, stored)

        if src.startswith(("http://", "https://")):
            return BaijiahaoPlatform._download_to_temp(
                src, Path(src.split("?")[0]).name or "img.png"
            )

        p = Path(src)
        if p.exists():
            return str(p)
        raise RuntimeError(f"[文章][百家号] 无法解析正文图片 src: {src}")

    @staticmethod
    def _download_to_temp(url: str, filename: str = "img.png") -> str:
        import tempfile
        import urllib.request

        resp = urllib.request.urlopen(url, timeout=30)
        data = resp.read()
        suffix = Path(filename).suffix or ".png"
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path
