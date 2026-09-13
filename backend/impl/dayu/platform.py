"""
大鱼号平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作中心地址：https://mp.dayu.com/dashboard/index
视频发布地址：https://mp.dayu.com/dashboard/video/write（首页悬停「发布内容」→「短视频」进入）
发布成功跳转：https://mp.dayu.com/dashboard/contents
"""

import asyncio
import json
import threading
import time
from datetime import timedelta
from pathlib import Path
from queue import Queue

from util._logger import bind_account_name, get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    raise_if_page_closed,
    save_login_result,
    scrape_dayu_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("dayu")

HOME_URL = "https://mp.dayu.com/dashboard/index"
WRITE_URL = "https://mp.dayu.com/dashboard/video/write"
CONTENTS_URL = "https://mp.dayu.com/dashboard/contents"

# 大鱼号页面上规定的字数限制（发布表单实时显示 x/60、x/200）
MAX_TITLE_LENGTH = 60
MIN_TITLE_LENGTH = 5
MAX_DESC_LENGTH = 200
MAX_TAGS = 10


class DayuPlatform(BasePlatform):
    platform_id = 21
    platform_key = "dayu"
    platform_name = "大鱼号"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 大鱼号 cookie 由 mp.dayu.com 下发，通配 .dayu.com 后对创作中心生效
    platform_cookie_domain = ".dayu.com"

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.dayu.com)
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
            f"[dayu] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """大鱼号扫码登录。登录成功后跳转创作中心首页 dashboard/index。"""
        logger.info("=" * 60)
        logger.info("[登录] 开始大鱼号登录流程")
        logger.info("=" * 60)

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                logger.info("[登录] 正在打开大鱼号创作中心...")
                await page.goto(HOME_URL)
                await asyncio.sleep(3)

                # 已登录直接进入首页；未登录会停在登录页
                if await self._is_logged_in(page):
                    logger.info("[登录] 检测到已有登录态，直接保存")
                else:
                    # Extract QR code image
                    src = None
                    qr_selectors = [
                        'img[class*="qrcode"]',
                        'img[class*="qr-code"]',
                        'img[class*="QRCode"]',
                        'img[class*="scan-code"]',
                        'div[class*="qrcode"] img',
                        'div[class*="login"] img',
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
                        logger.warning("[登录] 未找到二维码图片，请手动在弹出的浏览器中登录")
                        status_queue.put(json.dumps({"error": "无法找到登录二维码，请在浏览器中手动登录"}))

                    # Wait for login (5 minutes)
                    logger.info("[登录] 等待用户扫码...")
                    max_wait = 300
                    start_time = asyncio.get_event_loop().time()
                    while (asyncio.get_event_loop().time() - start_time) < max_wait:
                        raise_if_page_closed(page, action="登录")
                        try:
                            if await self._is_logged_in(page):
                                logger.info("[登录] 检测到页面跳转到创作中心，登录成功!")
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
                    scrape_fn=scrape_dayu_profile,
                    account_id=account_id,
                    # 登录成功后在同一个 session 内补抓 stats(昨日播放/本月收益/粉丝数)
                    stats_fn=self._login_stats_fn,
                )
                logger.info("[登录] 登录流程完成!")
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    @staticmethod
    async def _is_logged_in(page) -> bool:
        """登录成功的标志：顶栏出现用户头像区(.header-user)。"""
        try:
            if await page.locator(".header-user").count():
                return True
        except Exception:
            pass
        return False

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
                await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=15000)
                await asyncio.sleep(3)

                if await page.locator(".header-user").count():
                    logger.info("[Cookie检查] Cookie有效，顶栏用户区存在")
                    return True

                logger.warning("[Cookie检查] Cookie无效，未找到顶栏用户区")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar / stats
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步大鱼号昵称、头像、运营数据(stats)。

        创作中心首页 (https://mp.dayu.com/dashboard/index) 顶部条:
          - 头像: .header-user img
          - 昵称: .header-info .name

        运营数据在 .index2-summary 区块,每个 .index2-summary_data 含
        标题(.index2-summary_data_header)和数值(.index2-summary_data_body)。
        无数据时页面显示 "--",按 0 处理。
        """
        logger.info("[同步资料] 开始同步用户资料: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                try:
                    await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)

                name, avatar = await scrape_dayu_profile(page)
                stats = await self._scrape_stats(page)
                logger.info(
                    "[同步资料] 获取到用户信息 - 昵称: %s, 头像: %s, stats: %d 项",
                    name, avatar[:50] if avatar else "无", len(stats),
                )

                if not name and not avatar and not stats:
                    logger.info(f"[dayu] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await browser.close()

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。"""
        return await self._scrape_stats(page)

    @staticmethod
    async def _scrape_stats(page) -> list:
        """抓取首页 .index2-summary 运营数据。

        label_map: 标题文本 -> (ICON, SORT, 标准化 NAME)。
        "我的成长"是等级文本(非数字)不计入 stats;"--" 按 0 处理。
        """
        try:
            await page.wait_for_selector(".index2-summary_data", timeout=8000)
        except Exception:
            logger.info("[dayu stats] 等待 .index2-summary_data 超时")

        try:
            result = await page.evaluate(
                '''() => {
                    const out = [];
                    document.querySelectorAll('.index2-summary_data').forEach(item => {
                        const titleEl = item.querySelector('.index2-summary_data_header');
                        const bodyEl = item.querySelector('.index2-summary_data_body');
                        if (!titleEl || !bodyEl) return;
                        const title = (titleEl.textContent || '').trim();
                        const num = (bodyEl.textContent || '').trim();
                        if (title && num) out.push({title, num});
                    });
                    return out;
                }'''
            )
        except Exception as e:
            logger.info("[dayu stats] 抓取失败: %s", e)
            return []

        label_map = {
            "昨日阅读/播放": ("play", 1, "昨日阅读/播放"),
            "本月收益":     ("coin", 2, "本月收益"),
            "粉丝数":       ("user", 3, "粉丝数"),
        }
        stats = []
        for item in (result or []):
            title = item.get("title", "")
            num_str = str(item.get("num", "0"))
            # 标题里可能带问号图标文字,用前缀匹配
            matched = next((k for k in label_map if title.startswith(k)), None)
            if not matched:
                continue
            icon, sort_no, std_name = label_map[matched]
            cleaned = (
                num_str.replace("￥", "").replace("¥", "")
                .replace(",", "").replace(" ", "").strip()
            )
            try:
                count = int(float(cleaned)) if cleaned else 0
            except (ValueError, TypeError):
                count = 0  # "--" 等非数字按 0
            stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
        return stats

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Dayu creator centre in a visible browser window."""
        logger.info("[打开创作中心] 正在打开创作中心...")
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(HOME_URL)
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
    # publish_video — full Dayu upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to Dayu via CloakBrowser."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始大鱼号视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", [])
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", [])
        category = kwargs.get("category", "") or ""
        desc = kwargs.get("desc", "")
        enableTimer = kwargs.get("enableTimer", False)
        videos_per_day = kwargs.get("videos_per_day", 1)
        daily_times = kwargs.get("daily_times")
        start_days = kwargs.get("start_days", 0)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        # 16:9 / 9:16 次尺寸封面(大鱼号横版视频封面用 16:9,竖版封面用 9:16)
        thumbnail_landscape_169_path = kwargs.get("thumbnail_landscape_169_path", "")
        thumbnail_portrait_916_path = kwargs.get("thumbnail_portrait_916_path", "")
        # 信息来源(作品声明): 无需标注/AI生成/虚构演绎/营销信息/转载/个人观点/不适宜未成年人
        creation_declaration = kwargs.get("creation_declaration", "") or ""
        # 信息来源=转载 时的原文链接(必填)
        dayu_repost_url = kwargs.get("dayu_repost_url", "") or ""

        if isinstance(category, list):
            # 前端级联组件可能传数组,取末级文本
            category = category[-1] if category else ""
        category = str(category).strip()

        # 打印发布参数
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频分类: %s", category or "未选择")
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 信息来源: %s", creation_declaration or "未选择(默认无需标注)")
        logger.info("[发布参数] 转载原文链接: %s", dayu_repost_url or "无")
        logger.info("[发布参数] 横版16:9封面: %s", thumbnail_landscape_169_path or "无")
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版9:16封面: %s", thumbnail_portrait_916_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")

        if len(title) < MIN_TITLE_LENGTH:
            raise RuntimeError(
                f"大鱼号标题至少 {MIN_TITLE_LENGTH} 个字 (当前 {len(title)} 字)"
            )

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]

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
                        category=category,
                        thumbnail_landscape_path=thumbnail_landscape_path or None,
                        thumbnail_portrait_path=thumbnail_portrait_path or None,
                        thumbnail_landscape_169_path=thumbnail_landscape_169_path or None,
                        thumbnail_portrait_916_path=thumbnail_portrait_916_path or None,
                        creation_declaration=creation_declaration,
                        dayu_repost_url=dayu_repost_url,
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
        category="",
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
        creation_declaration="",
        dayu_repost_url="",
    ):
        """Upload a single video to one Dayu account."""
        logger.info("[上传视频] 开始上传视频: %s", file_path)
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()
                await self._open_write_page(page)

                # Upload video file
                logger.info("[上传视频] 正在上传视频文件...")
                file_input_idx = await page.evaluate(
                    """() => {
                        const inputs = [...document.querySelectorAll('input[type=file]')];
                        for (let i = 0; i < inputs.length; i++) {
                            const accept = (inputs[i].accept || '').toLowerCase();
                            if (!accept || accept.includes('video')) return i;
                        }
                        return -1;
                    }"""
                )
                if file_input_idx >= 0:
                    file_input = page.locator('input[type="file"]').nth(file_input_idx)
                else:
                    file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择，等待上传完成...")

                # Wait for upload to complete:
                # 上传中: .article-write_video-container-uploading (进度条/百分比)
                # 完成:   .article-write_video-container-result 出现"视频上传成功"
                max_wait = 14400  # 4 hours for large files
                start_time = asyncio.get_event_loop().time()
                upload_complete = False
                last_progress = ""
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    raise_if_page_closed(page)
                    try:
                        result_box = page.locator(".article-write_video-container-result")
                        if await result_box.count():
                            result_text = (await result_box.text_content() or "").strip()
                            if "视频上传成功" in result_text:
                                upload_complete = True
                                logger.info("[上传视频] 视频上传成功!")
                                break
                        # 打印上传进度
                        progress_text = page.locator(".article-write_video-container-uploading_status")
                        if await progress_text.count():
                            current_progress = (
                                (await progress_text.first.text_content() or ""
                                 ).strip().replace("\n", " ")
                            )
                            if current_progress and current_progress != last_progress:
                                logger.info("[上传视频] %s", current_progress)
                                last_progress = current_progress
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                if not upload_complete:
                    raise RuntimeError(f"[上传视频] 视频上传超时! 已等待 {max_wait} 秒")

                await asyncio.sleep(2)

                # 检测横竖版(上传结果里会提示"检测为竖版视频")
                is_portrait = False
                try:
                    resolution_tip = page.locator(".video-resulotion-result")
                    if await resolution_tip.count():
                        tip_text = (await resolution_tip.first.text_content() or "").strip()
                        if "竖版" in tip_text:
                            is_portrait = True
                            logger.info("[视频类型] 检测到竖版视频")
                        else:
                            logger.info("[视频类型] 检测到横版视频")
                except Exception:
                    logger.info("[视频类型] 默认为横版视频")

                # ---- 填写标题(contenteditable,最少5字/最多60字) ----
                logger.info("[填写标题] 标题: %s", title[:MAX_TITLE_LENGTH])
                title_input = page.locator(".w-form-field-content-editable").first
                await title_input.wait_for(state="visible", timeout=10000)
                await clear_and_type(page, title[:MAX_TITLE_LENGTH], title_input)
                await asyncio.sleep(0.5)
                # 标题框带 tribute 联想(data-tribute),按 Esc 关闭联想下拉
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(0.3)
                except Exception:
                    pass
                logger.info("[填写标题] 标题填写完成")

                # ---- 填写视频简介(textarea,最多200字) ----
                if desc:
                    logger.info("[填写简介] 开始填写视频简介...")
                    desc_input = page.locator(".w-form-field-textarea textarea").first
                    if await desc_input.count():
                        await desc_input.fill(desc[:MAX_DESC_LENGTH])
                        logger.info("[填写简介] 视频简介填写成功!")
                    else:
                        logger.warning("[填写简介] 未找到视频简介输入框!")
                else:
                    logger.info("[填写简介] 无视频简介")

                # ---- 设置视频分类(必选) ----
                if category:
                    logger.info("[设置分类] 开始设置视频分类: %s", category)
                    await self._set_category(page, category)
                else:
                    logger.info("[设置分类] 未选择分类(默认保持页面初始值)")

                # ---- 填写标签(最多10个) ----
                if tags:
                    logger.info("[填写标签] 开始填写标签: %s", tags[:MAX_TAGS])
                    await self._fill_tags(page, tags[:MAX_TAGS])
                    logger.info("[填写标签] 标签填写完成")
                else:
                    logger.info("[填写标签] 无标签")

                # ---- 设置封面 ----
                # 视频封面(必填,横版 16:9) + 竖版封面(选填,9:16)
                landscape_cover = thumbnail_landscape_169_path or thumbnail_landscape_path
                portrait_cover = thumbnail_portrait_916_path or thumbnail_portrait_path
                if landscape_cover or portrait_cover:
                    logger.info("[设置封面] 开始设置封面...")
                    await self._set_covers(page, landscape_cover, portrait_cover)
                    logger.info("[设置封面] 封面设置完成")
                else:
                    logger.info("[设置封面] 无自定义封面")

                # ---- 信息来源(作品声明,必选) ----
                declaration = creation_declaration or "无需标注"
                if not creation_declaration:
                    logger.info("[设置声明] 未选择信息来源,默认选择「无需标注」")
                logger.info("[设置声明] 开始设置信息来源: %s", declaration)
                await self._set_source_remark(page, declaration, dayu_repost_url)
                logger.info("[设置声明] 信息来源设置完成")

                # ---- 定时发布(只能选 5 分钟间隔,7 天范围内) ----
                # _set_schedule_time 任一步失败都会抛 RuntimeError 中止发布,
                # 避免定时设置失败后视频被立即发布。
                if publish_strategy == "scheduled" and publish_date != 0:
                    logger.info("[定时发布] 开始设置定时发布时间: %s", publish_date)
                    await self._set_schedule_time(page, publish_date)

                # ---- 点击发表 ----
                # 主定位: data-spm-click 属性的语义段(阿里 SPM 埋点协议的稳定部分,
                # 属性值里的 wmid 是账号级随机 hex,不做匹配依据)。
                # 兜底: 限定 .article-write_box-opt 容器(发表/预览/清空/保存 按钮组的
                # 固定父级,语义 class)——has_text 是子串匹配,不限容器会误中
                # 预览弹窗里的「确认发表」按钮。
                logger.info("[发布] 正在点击发表按钮...")
                publish_btn = page.locator('button[data-spm-click*="videowrite.publish"]')
                if not await publish_btn.count():
                    publish_btn = page.locator(
                        '.article-write_box-opt button.w-btn_primary', has_text="发表"
                    )
                await publish_btn.first.click()

                # 等待发布结果:处理二次弹窗,成功则跳转 /dashboard/contents
                await self._wait_publish_result(page)

                # Save updated cookie state
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # Helper: wait for publish result (popups + redirect)
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_publish_result(page, timeout_s: int = 180):
        """点击「发表」后等待发布结果。

        需要处理的弹窗(出现哪个点哪个,可重复出现):
          1. 「视频画质过低提醒」-> 点击「继续上传」
          2. 「视频预览」二次确认 -> 点击「确认发表」

        成功标志:页面跳转到 https://mp.dayu.com/dashboard/contents
        """
        logger.info("[发布] 等待发布结果...")
        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < timeout_s:
            raise_if_page_closed(page)
            try:
                # 1. 画质过低提醒 -> 继续上传
                low_quality_pop = page.locator(
                    '.widgets-pop_container:has-text("视频画质过低")'
                )
                if await low_quality_pop.count():
                    continue_btn = low_quality_pop.locator(
                        'button', has_text="继续上传"
                    )
                    if await continue_btn.count():
                        await continue_btn.first.click()
                        logger.info("[发布] 已点击「继续上传」(画质过低提醒)")
                        await asyncio.sleep(1)
                        continue

                # 2. 视频预览确认弹窗 -> 确认发表
                confirm_btn = page.locator(
                    '.article-write-preview_btn button', has_text="确认发表"
                )
                if await confirm_btn.count():
                    await confirm_btn.first.click()
                    logger.info("[发布] 已点击「确认发表」(视频预览弹窗)")
                    await asyncio.sleep(1)
                    continue

                # 3. 跳转到内容管理页 = 发布成功
                if "/dashboard/contents" in page.url:
                    logger.info("[发布] 视频发布成功! 页面跳转到: %s", page.url)
                    return
            except Exception:
                pass
            await asyncio.sleep(1)

        raise RuntimeError(
            f"[发布] 等待发布结果超时({timeout_s}s),页面未跳转到内容管理页"
        )

    # ------------------------------------------------------------------
    # Helper: open video write page (hover 发布内容 -> 短视频)
    # ------------------------------------------------------------------

    @staticmethod
    async def _open_write_page(page):
        """从创作中心首页进入「发布内容 → 短视频」发布页。"""
        logger.info("[上传视频] 正在打开创作中心首页...")
        await page.goto(HOME_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_selector(".publish_btn", timeout=10000)
        except Exception as e:
            raise RuntimeError(f"[上传视频] 创作中心首页未出现「发布内容」按钮(cookie 可能失效): {e}")

        logger.info("[上传视频] 悬停「发布内容」展开菜单...")
        await page.locator(".publish_btn").hover()
        await asyncio.sleep(1)

        short_video_link = page.locator('.publish_menus_wrapper a[href="/dashboard/video/write"]')
        try:
            await short_video_link.wait_for(state="visible", timeout=5000)
        except Exception:
            # 菜单未展开时再 hover 一次兜底
            await page.locator(".publish_btn").hover()
            await asyncio.sleep(1)
        await short_video_link.first.hover()
        await asyncio.sleep(0.5)
        await short_video_link.first.click()
        logger.info("[上传视频] 已点击「短视频」菜单,等待发布页打开...")
        await page.wait_for_url("**/dashboard/video/write**", timeout=15000)
        logger.info("[上传视频] 发布页面已打开")

    # ------------------------------------------------------------------
    # Helper: set video category
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_category(page, category: str):
        """点击分类下拉,选择与 category 文本一致的选项。"""
        try:
            container = page.locator(".widgets-selects_container").first
            if not await container.count():
                logger.warning("[设置分类] 未找到分类下拉组件!")
                return
            await container.click()
            await asyncio.sleep(1)

            options = page.locator(".widgets-selects_select_container a")
            count = await options.count()
            target = None
            fallback_other = None
            for i in range(count):
                text = (await options.nth(i).text_content() or "").strip()
                if text == category:
                    target = options.nth(i)
                    break
                if text == "其他":
                    fallback_other = options.nth(i)
            if target is None:
                logger.warning("[设置分类] 未找到分类「%s」,回退选择「其他」", category)
                target = fallback_other
            if target is not None:
                await target.click()
                await asyncio.sleep(0.5)
                logger.info("[设置分类] 分类已选择")
            else:
                logger.warning("[设置分类] 分类选项列表为空!")
        except Exception as e:
            logger.error("[设置分类] 设置视频分类失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: fill tags (max 10, type + Enter, 1s interval)
    # ------------------------------------------------------------------

    @staticmethod
    async def _fill_tags(page, tags: list):
        """点击标签输入区激活输入组件,逐个输入标签并回车。"""
        try:
            tags_box = page.locator(".article-write_video-tags").first
            if not await tags_box.count():
                logger.warning("[填写标签] 未找到标签输入区!")
                return
            await tags_box.click()
            await asyncio.sleep(1)

            tag_input = tags_box.locator("input")
            for i, tag in enumerate(tags):
                if not tag:
                    continue
                logger.info("[填写标签] 填写第 %d 个标签: %s", i + 1, tag)
                if await tag_input.count():
                    await tag_input.first.click()
                # 打字机效果逐字符输入(比 fill 可靠,能触发输入框 onChange)
                await page.keyboard.type(str(tag), delay=100)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                await asyncio.sleep(1)

            logger.info("[填写标签] 所有标签填写完成")
        except Exception as e:
            logger.error("[填写标签] 填写标签失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set covers (视频封面 + 竖版封面,上传后点弹窗「保存」)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_covers(page, landscape_cover=None, portrait_cover=None):
        """设置视频封面(横版)和竖版封面。

        - 视频封面: #coverImg 内隐藏 input[type=file](16:9 横版)
        - 竖版封面: .article-write_box-vertical-cover 内 input[type=file](9:16)
        - 上传后弹出截取窗口,直接点击弹窗内的「保存」按钮
        """
        try:
            if landscape_cover:
                cover_input = page.locator("#coverImg input[type='file']").first
                if await cover_input.count():
                    logger.info("[设置封面] 上传视频封面(横版): %s", landscape_cover)
                    await cover_input.set_input_files(landscape_cover)
                    await asyncio.sleep(2)
                    await DayuPlatform._click_cover_dialog_save(page)
                else:
                    logger.warning("[设置封面] 未找到视频封面上传入口!")

            if portrait_cover:
                vertical_input = page.locator(
                    ".article-write_box-vertical-cover input[type='file']"
                ).first
                if await vertical_input.count():
                    logger.info("[设置封面] 上传竖版封面: %s", portrait_cover)
                    await vertical_input.set_input_files(portrait_cover)
                    await asyncio.sleep(2)
                    await DayuPlatform._click_cover_dialog_save(page)
                else:
                    logger.warning("[设置封面] 未找到竖版封面上传入口!")
        except Exception as e:
            logger.error("[设置封面] 设置封面失败: %s", e)

    @staticmethod
    async def _click_cover_dialog_save(page):
        """点击封面截取弹窗里的「保存」按钮(.widgets-pop_container 内 w-btn_primary)。"""
        try:
            save_btn = page.locator(
                ".widgets-pop_container button.w-btn_primary", has_text="保存"
            )
            if await save_btn.count():
                await save_btn.first.click()
                logger.info("[设置封面] 已点击封面弹窗「保存」")
                await asyncio.sleep(1.5)
            else:
                logger.info("[设置封面] 未出现封面截取弹窗,跳过保存")
        except Exception as e:
            logger.warning("[设置封面] 点击封面弹窗「保存」失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set 信息来源 (source remark radio + 转载原文链接)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_source_remark(page, declaration: str, repost_url: str = ""):
        """选择信息来源单选项;选「转载」时填写必填的原文链接。

        radio 的 value 与文案一致(无需标注/AI生成/虚构演绎/营销信息/转载/
        个人观点/不适宜未成年人),点击对应 label.ant-radio-wrapper。
        """
        try:
            wrapper = page.locator(
                "label.ant-radio-wrapper", has_text=declaration
            ).first
            if await wrapper.count():
                await wrapper.click()
                logger.info("[设置声明] 已选择信息来源: %s", declaration)
                await asyncio.sleep(0.5)
            else:
                logger.warning("[设置声明] 未找到信息来源选项: %s", declaration)
                return

            if declaration == "转载":
                if not repost_url:
                    raise RuntimeError("信息来源选择「转载」时必须填写原文链接")
                link_input = page.locator('input.ant-input[placeholder*="原文链接"]').first
                if not await link_input.count():
                    link_input = page.locator(
                        ".source-remark-detail input.ant-input"
                    ).first
                if await link_input.count():
                    await link_input.wait_for(state="visible", timeout=5000)
                    await link_input.fill(repost_url)
                    logger.info("[设置声明] 原文链接已填写: %s", repost_url)
                else:
                    raise RuntimeError("未找到原文链接输入框")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error("[设置声明] 设置信息来源失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: set schedule time (datetimepicker, 5-minute interval)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """设置定时发布时间。

        大鱼号定时发布组件只能选 5 分钟间隔(11:05/11:10...),7 天范围内。
        流程:点击「定时发布」开关 -> 出现日期组件 -> 依次选择 日/时/分。

        目标分钟数向上取整到 5 的倍数(避免比用户指定时间早发布)。
        """
        # 分钟向上取整到 5 的倍数
        minute = publish_date.minute
        snapped = ((minute + 4) // 5) * 5
        target = publish_date + timedelta(minutes=snapped - minute)
        logger.info(
            "[定时发布] 目标时间 %s (原 %s,对齐到 5 分钟间隔)",
            target.strftime("%Y-%m-%d %H:%M"), publish_date.strftime("%Y-%m-%d %H:%M"),
        )

        # 失败一律抛错(而不是仅告警后继续):
        # 定时设置失败时若继续点「发表」,视频会立即发布,与用户要的定时相悖。
        try:
            # 1. 点击「定时发布」开关
            timer_radio = page.locator(
                '.article-write_radio:has-text("定时发布") .w-radio'
            ).first
            if not await timer_radio.count():
                raise RuntimeError("未找到「定时发布」开关")
            await timer_radio.click()
            await asyncio.sleep(1)

            # 2. 点击日期组件弹出日/时/分选择
            # 组件结构: .widgets-datepicker-m > input + img + .widgets-datepicker-m_mask
            # mask 遮罩盖在 input 上方,直接点 input 会被 mask 拦截指针事件
            # (实测 Locator.click Timeout: mask intercepts pointer events),
            # 点 mask 本身即可弹出选择面板。
            raise_if_page_closed(page, action="定时发布")
            date_input = page.locator(".widgets-datepicker-m_input").first
            await date_input.wait_for(state="visible", timeout=5000)
            date_mask = page.locator(".widgets-datepicker-m_mask").first
            if await date_mask.count():
                await date_mask.click()
            else:
                await date_input.click(force=True)
            await asyncio.sleep(1)

            # 3. 选择日期(.datetimepicker-days)
            days_view = page.locator(".datetimepicker-days")
            await days_view.wait_for(state="visible", timeout=5000)

            # 对齐月份:switch 显示如「九月 2026」——注意是中文数字,
            # 必须用 _parse_switch 解析后比较,不能拿 f"{month}月 {year}"
            # 阿拉伯数字字符串直接比对(否则永不相等,误点 visibility:hidden
            # 的前后箭头,click 等可见性直接卡死 30s)。
            for _ in range(2):  # 最多跨 1 个月,尝试 2 次
                raise_if_page_closed(page, action="定时发布")
                switch_text = (
                    await days_view.locator("th.switch").text_content() or ""
                ).strip()
                shown = _parse_switch(switch_text)
                if shown == (target.year, target.month):
                    break
                if shown == (0, 0):
                    raise RuntimeError(f"无法解析日历月份标题: {switch_text!r}")
                # 目标月在右侧 -> 点 next;在左侧 -> 点 prev;
                # 超出可选范围时箭头是 visibility:hidden,点击前必须先判可见,
                # 否则 click 会一直等元素可见直至超时。
                arrow = (
                    "th.next" if (target.year, target.month) > shown else "th.prev"
                )
                arrow_loc = days_view.locator(arrow)
                if not await arrow_loc.is_visible():
                    raise RuntimeError(
                        f"日历无法从 {switch_text} 导航到 {target.year}-{target.month:02d}"
                        "(超出可选范围,大鱼号定时仅支持 7 天内)"
                    )
                await arrow_loc.click()
                await asyncio.sleep(0.5)
            else:
                raise RuntimeError(
                    f"日历翻页 2 次后仍未对齐到 {target.year}-{target.month:02d}"
                )

            raise_if_page_closed(page, action="定时发布")
            day_cell = days_view.locator(
                'td.day:not(.old):not(.new):not(.disabled)',
                has_text=str(target.day),
            )
            # has_text 是子串匹配,精确匹配当天数字
            count = await day_cell.count()
            picked = False
            for i in range(count):
                if (await day_cell.nth(i).text_content() or "").strip() == str(target.day):
                    await day_cell.nth(i).click()
                    picked = True
                    break
            if not picked:
                raise RuntimeError(f"日期面板未找到可点击的 {target.month}月{target.day}日")
            logger.info("[定时发布] 日期已选择: %s 日", target.day)
            await asyncio.sleep(0.5)

            # 4. 选择小时(.datetimepicker-hours)
            raise_if_page_closed(page, action="定时发布")
            hours_view = page.locator(".datetimepicker-hours")
            await hours_view.wait_for(state="visible", timeout=5000)
            hour_cell = None
            hour_opts = hours_view.locator("span.hour")
            for i in range(await hour_opts.count()):
                if (await hour_opts.nth(i).text_content() or "").strip() == f"{target.hour}:00":
                    hour_cell = hour_opts.nth(i)
                    break
            if hour_cell:
                await hour_cell.click()
                logger.info("[定时发布] 小时已选择: %s", target.hour)
            else:
                raise RuntimeError(f"小时面板未找到 {target.hour}:00 选项")
            await asyncio.sleep(0.5)

            # 5. 选择分钟(.datetimepicker-minutes,5 分钟间隔)
            raise_if_page_closed(page, action="定时发布")
            minutes_view = page.locator(".datetimepicker-minutes")
            await minutes_view.wait_for(state="visible", timeout=5000)
            want_minute = f"{target.hour:02d}:{target.minute:02d}"
            minute_cell = None
            minute_opts = minutes_view.locator("span.minute")
            for i in range(await minute_opts.count()):
                if (await minute_opts.nth(i).text_content() or "").strip() == want_minute:
                    minute_cell = minute_opts.nth(i)
                    break
            if minute_cell:
                await minute_cell.click()
                logger.info("[定时发布] 分钟已选择: %s", want_minute)
            else:
                raise RuntimeError(f"分钟面板未找到 {want_minute} 选项(5 分钟间隔)")
            logger.info(
                "[定时发布] 定时发布时间设置完成: %s",
                target.strftime("%Y-%m-%d %H:%M"),
            )
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"[定时发布] 设置定时发布时间失败: {e}") from e


def _parse_switch(switch_text: str):
    """把 datetimepicker 的「九月 2026」文本解析为 (year, month)。"""
    cn_nums = {
        "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
        "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12,
    }
    try:
        month_part, year_part = switch_text.replace("月", " 月 ").split(" 月 ")
        month = cn_nums.get(month_part.strip(), 0)
        year = int(year_part.strip())
        return (year, month)
    except Exception:
        return (0, 0)
