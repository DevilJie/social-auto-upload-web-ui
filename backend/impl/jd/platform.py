"""京东平台发布实现。

参考 backend/impl/taobao_guanghe/platform.py(架构平行,具体 DOM 不同)。

平台信息:
- platform_id: 20
- platform_key: 'jd'
- platform_name: '京东'
- creator_center: https://dr.jd.com/jm/
- publish_url: https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop
"""

import asyncio
import logging
import os
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import bind_account_name, get_channel_logger

from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("jingmai")

JD_PUBLISH_URL = "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop"
JD_CREATOR_CENTER_URL = "https://dr.jd.com/jm/"

# Cookie 失效/未登录时会被重定向到这些域
JD_COOKIE_INVALID_MARKERS = (
    "passport.jd.com",
    "passport.shop.jd.com",
)

# 视为已登录的域名
JD_HOME_HOST = "dr.jd.com"

# 测试 dry-run 开关:JD_DRY_RUN=1 时跳过点击发布(只走完表单 + 截图 + 保持浏览器
# 供人工检查)。默认关闭(真实发布)。与淘宝光合 GUANGHE_DRY_RUN 机制一致。
_DRY_RUN_PUBLISH = bool(os.environ.get("JD_DRY_RUN"))


class JdPlatform(BasePlatform):
    """京东平台发布实现。

    当前 Task 10 只交付基础类结构 + login。其余抽象方法(check_cookie /
    open_creator_center / sync_profile / publish_video)在后续 Task 11-17 实现,
    本类先以 NotImplementedError 占位,保证 class 可实例化、registry 可注册。
    """

    platform_id = 20
    platform_key = "jd"
    platform_name = "京东"

    def __init__(self):
        self.browser = None
        self.page = None
        # 京东微前端架构:发布表单在 iframe(self.frame)里,top frame(self.page)
        # 只有主壳。所有表单操作必须在 iframe 上做,否则永远找不到元素
        # (picker.py 已踩过同样坑)。
        self.frame = None

    # ---------- 抽象方法:登录 ----------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开京东创作中心,等待用户扫码/手动登录后保存 cookie。

        Args:
            id: 账号唯一标识(同 account_id)
            status_queue: 进度队列
            account_id: 数据库账号 ID(可选)
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(JD_CREATOR_CENTER_URL)
                logger.info("[jd][登录] 等待用户完成登录(检测 URL 跳回创作中心)")

                # 轮询:URL 离开登录域、回到创作中心 = 登录成功。
                while True:
                    await asyncio.sleep(2)
                    current_url = page.url or ""
                    if JD_HOME_HOST in current_url and not any(
                        m in current_url for m in JD_COOKIE_INVALID_MARKERS
                    ):
                        # 二次确认仍在创作中心(排除中间态跳转)
                        await asyncio.sleep(3)
                        if JD_HOME_HOST in (page.url or ""):
                            logger.info("[jd][登录] URL 已回到创作中心,登录成功")
                            break

                # 登录后后台还在做 token 交换/重定向,登录态 cookie 可能尚未完全建立。
                # 主动重新导航首页,确保关键 cookie 已写入,供 storage_state 保存完整。
                logger.info("[jd][登录] 等待首页稳定(确保登录态完整)")
                try:
                    await page.goto(
                        JD_CREATOR_CENTER_URL, wait_until="domcontentloaded", timeout=30000
                    )
                except Exception as e:
                    logger.info(f"[jd][登录] 首页导航超时(忽略): {e}")
                await asyncio.sleep(2)

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=_scrape_jd_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await context.close()
                except Exception:
                    pass
        finally:
            if success:
                await browser.close()

    # ---------- 占位:后续 Task 实现 ----------

    async def check_cookie(self, cookie_file: str) -> bool:
        """检测 cookie 是否有效。

        策略:用 cookie 打开创作中心,如果被重定向到 passport.* → 无效。
        """
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            return False

        browser = await self.create_browser(headless=True)
        try:
            ctx = await self.create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            try:
                await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                url = page.url or ""
                for invalid_host in JD_COOKIE_INVALID_MARKERS:
                    if invalid_host in url:
                        logger.warning(f"京东 cookie 失效: 当前 URL {url}")
                        return False
                return True
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await ctx.close()
                except Exception:
                    pass
        finally:
            await browser.close()

    async def sync_profile(self, cookie_file: str):
        """同步账号昵称/头像。

        Returns:
            {"name": str, "avatar": str} 或 None(失败时)
        """
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            return None

        browser = await self.create_browser(headless=True)
        try:
            ctx = await self.create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            try:
                await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # 复用 jd 专用 scraper(顶栏 BEM class,无哈希)
                name, avatar = await _scrape_jd_profile(page)

                if name:
                    return {"name": name, "avatar": avatar}
                return None
            except Exception as e:
                logger.warning(f"sync_profile 失败: {e}")
                return None
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await ctx.close()
                except Exception:
                    pass
        finally:
            await browser.close()

    async def open_creator_center(self, cookie_file: str) -> None:
        """异步入口:打开创作中心(后台线程保持浏览器)。"""
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            raise FileNotFoundError(f"cookie 文件不存在: {cookie_file}")

        def _launch():
            from .._browser import create_browser_sync, create_context_sync
            browser = create_browser_sync(headless=False)
            try:
                ctx = create_context_sync(browser, storage_state=str(cookie_path))
                page = ctx.new_page()
                page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
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

    # ---------- 发布主流程 ----------

    def publish_video(self, **kwargs) -> bool:
        """发布视频到京东(京麦)。接受 app.py 统一传入的标准 kwargs(与淘宝光合对齐)。

        接受的 kwargs:
        - ``title`` (*str*) — 标题(≤27 字)
        - ``files`` (*list[str]*) — 视频绝对路径列表
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` — 封面
        - ``enableTimer`` / ``schedule_time_str`` — 定时发布
        - ``videos_per_day`` / ``daily_times`` / ``start_days`` — 自动排期
        - ``video_format`` (*str*) — 'landscape'/'portrait'
        - ``jd_related_type`` / ``jd_products`` / ``jd_novel`` / ``jd_declaration``
        """
        async def _run():
            logger.info("=" * 60)
            logger.info("[发布视频] 开始京东视频发布流程")
            logger.info("=" * 60)

            for _k, _v in kwargs.items():
                _vs = repr(_v)
                if len(_vs) > 100:
                    _vs = _vs[:100] + "..."
                logger.info("[发布参数 RAW] %s = %s", _k, _vs)

            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            account_files = kwargs.get("account_file", [])
            enable_timer = kwargs.get("enableTimer", False)
            videos_per_day = kwargs.get("videos_per_day", 1)
            daily_times = kwargs.get("daily_times")
            start_days = kwargs.get("start_days", 0)
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "") or ""
            thumbnail_portrait = kwargs.get("thumbnail_portrait_path", "") or ""
            thumbnail_landscape_169 = kwargs.get("thumbnail_landscape_169_path", "") or ""
            thumbnail_portrait_916 = kwargs.get("thumbnail_portrait_916_path", "") or ""
            schedule_time_str = kwargs.get("schedule_time_str", "") or kwargs.get("schedule_time", "") or ""
            video_format = kwargs.get("video_format", "") or ""
            # 京东关联挂件
            related_type = (kwargs.get("jd_related_type", "") or "").strip()
            jd_products = kwargs.get("jd_products", []) or []
            jd_novel = kwargs.get("jd_novel", "") or ""
            jd_declaration = kwargs.get("jd_declaration", "") or ""

            # 规范化小说(字符串 → {title: s};dict 直接用)。前端现在传整个对象,
            # 旧数据可能只有 title 字符串。
            if isinstance(jd_novel, str):
                jd_novel = {"title": jd_novel} if jd_novel else ""

            # 规范化关联商品(字符串 → {title: s};dict 直接用,最多 10 个)
            link_items = []
            for it in jd_products[:10]:
                if isinstance(it, str):
                    link_items.append({"title": it})
                elif isinstance(it, dict):
                    link_items.append(it)

            cookie_paths = [str(Path(BASE_DIR / "cookiesFile") / f) for f in account_files]
            file_paths = [str(f) for f in files]

            if not file_paths:
                raise ValueError("files 不能为空")
            if not cookie_paths:
                raise ValueError("account_file 不能为空")

            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 文件数量: %d, 账号数量: %d", len(file_paths), len(cookie_paths))
            logger.info("[发布参数] 关联类型: %s, 待关联商品数: %d", related_type or "无", len(link_items))
            logger.info("[发布参数] 创作声明: %s", jd_declaration or "无")

            publish_datetimes = parse_schedule_time(
                schedule_time_str, len(file_paths), enable_timer,
                videos_per_day, daily_times, start_days,
            )

            for index, file_path in enumerate(file_paths):
                # 根据视频方向选对应格式封面(横版→16:9,竖版→9:16,兜底普通横竖)
                if video_format == "landscape":
                    picked_thumb = (thumbnail_landscape_169 or thumbnail_landscape
                                    or thumbnail_portrait_916 or thumbnail_portrait)
                else:
                    picked_thumb = (thumbnail_portrait_916 or thumbnail_portrait
                                    or thumbnail_landscape_169 or thumbnail_landscape)

                publish_date = (
                    publish_datetimes[index]
                    if isinstance(publish_datetimes, list)
                    else publish_datetimes
                )

                for cookie_path in cookie_paths:
                    cookie_name = Path(cookie_path).name
                    nick = get_account_name_by_cookie_file(cookie_name)
                    with bind_account_name(nick or "-"):
                        await self._upload_single_video(
                            title=title,
                            file_path=file_path,
                            publish_date=publish_date,
                            account_file=cookie_path,
                            thumbnail_path=picked_thumb,
                            related_type=related_type,
                            link_items=link_items,
                            jd_novel=jd_novel,
                            jd_declaration=jd_declaration,
                        )

            logger.info("=" * 60)
            logger.info("[发布视频] 京东视频发布流程完成!")
            logger.info("=" * 60)

        asyncio.run(_run())
        return True

    async def _upload_single_video(
        self,
        title: str,
        file_path: str,
        publish_date,
        account_file: str,
        thumbnail_path: str | None = None,
        related_type: str = "",
        link_items: list = None,
        jd_novel: str = "",
        jd_declaration: str = "",
    ) -> None:
        """上传单个视频到一个京东账号。失败时 raise(异常传到 publish_video → app.py)。"""
        from . import _jd_link_ops as link_ops

        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()

                # 0. goto 发布页(带 cookie,直接深链,跳过首页导航)
                await page.goto(JD_PUBLISH_URL, wait_until="domcontentloaded", timeout=30000)

                # cookie 失效会被重定向到登录页
                current_url = page.url or ""
                if any(m in current_url for m in JD_COOKIE_INVALID_MARKERS):
                    raise RuntimeError("京东 cookie 失效,请重新登录")

                # 京东微前端:表单在 iframe 里,不在 top frame。找 iframe 后全部操作都进 iframe。
                frame = await link_ops.wait_publish_frame(page, timeout=20)
                logger.info("[上传视频] ✓ iframe=%s", frame.url)
                await frame.wait_for_selector(
                    ".video-upload-wrapper", timeout=15_000, state="visible",
                )
                await asyncio.sleep(1)

                # 设置实例属性,让辅助方法(_upload_video 等)复用 self.frame
                self.browser = browser
                self.page = page
                self.frame = frame

                # 1. 上传视频
                await self._upload_video(Path(file_path))
                await self._wait_upload_complete()

                # 2. 封面(可选)
                if thumbnail_path and Path(thumbnail_path).exists():
                    await self._set_cover(Path(thumbnail_path))

                # 3. 标题
                await self._fill_title(title)

                # 4. 关联挂件
                if related_type == "product" and link_items:
                    await self._link_products(link_items)
                elif related_type == "novel" and jd_novel:
                    await self._select_novel(jd_novel)

                # 5. 创作声明
                if jd_declaration:
                    await self._set_declaration(jd_declaration)

                # 6. 定时发布
                if publish_date and hasattr(publish_date, "strftime"):
                    await self._set_schedule_time(publish_date)

                # 提交前截图(用 page 截全页含 iframe)
                try:
                    await page.screenshot(
                        path=str(log_dir / "jd_before_submit.png"), full_page=True,
                    )
                except Exception:
                    pass

                # 7. dry-run 或 点击发布
                if _DRY_RUN_PUBLISH:
                    logger.info("[上传视频] 🐛 DRY_RUN 跳过点击发布,浏览器保持打开,供人工检查")
                    logger.info("[上传视频] 🐛 当前状态: 标题/封面/关联挂件/声明/定时 已填好")
                    try:
                        await page.screenshot(path=str(log_dir / "jd_dry_run.png"), full_page=True)
                    except Exception:
                        pass
                    try:
                        logger.info("[上传视频] 🐛 等待浏览器关闭(请手动关闭)...")
                        await page.wait_for_event("close", timeout=0)
                    except Exception:
                        pass
                else:
                    await self._click_publish()
                    await self._check_publish_success()
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
        finally:
            try:
                await self.close_browser(browser, is_close_by_code=True)
            except Exception:
                pass
            self.browser = None
            self.page = None
            self.frame = None
            logger.info("[上传视频] 浏览器已关闭")

    # ---------- 视频上传 ----------

    async def _upload_video(self, video_path: Path):
        """上传视频到 input[type=file]。

        京东发布页的 input[type=file] 在 .video-upload-wrapper 内,
        通常设置 display: none,需要通过 set_input_files 触发。
        """
        if not video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")

        file_input = await self.frame.wait_for_selector(
            ".video-upload-wrapper input[type='file']",
            timeout=10_000,
            state="attached",  # 京东 file input 是 display:none,不能等 visible
        )
        await file_input.set_input_files(str(video_path.absolute()))

    async def _wait_upload_complete(self, timeout: float = 600):
        """等视频上传完成(进度条 DOM 隐藏)。

        上传过程中 DOM: .uploading-con > .upload-text("已上传 N%")
        上传完成:    .uploading-con 不再可见

        实现:循环检测 .uploading-con 是否消失,或 .preview-box img 出现
        """
        # 1. 等 .uploading-con 出现
        await self.frame.wait_for_selector(
            ".uploading-con",
            timeout=30_000,
            state="visible",
        )
        # 2. 等 .uploading-con 消失
        await self.frame.wait_for_selector(
            ".uploading-con",
            timeout=timeout * 1000,
            state="hidden",
        )
        # 3. 额外等 .preview-box img(封面预览)出现
        try:
            await self.frame.wait_for_selector(
                ".preview-box img",
                timeout=30_000,
                state="visible",
            )
        except Exception:
            logger.warning("封面预览未出现,继续")

        await asyncio.sleep(1)

    # ---------- 封面 ----------

    async def _set_cover(self, cover_path: Path):
        """设置封面:点击'修改封面'按钮 → 上传本地图片 → 确定。

        1. 点 .preview-box .edit-cover-btn 打开弹窗
        2. 在弹窗内点 ._local-upload-localupload-upload-input_1vrwk_331 (input[type=file])
        3. 等缩略图加载
        4. 点弹窗确定按钮 .jd-btn-primary[data-component-label='确定']
        """
        if not cover_path.exists():
            raise FileNotFoundError(f"封面图片不存在: {cover_path}")

        # 1. 点"修改封面"
        edit_btn = await self.frame.wait_for_selector(
            ".edit-cover-btn",
            timeout=10_000,
        )
        await edit_btn.click()
        await asyncio.sleep(1)

        # 2. 等弹窗出现
        await self.frame.wait_for_selector(
            ".jd-modal-content",
            timeout=10_000,
            state="visible",
        )
        await self.frame.wait_for_selector(
            "._crop-image_1vrwk_165 img",
            timeout=10_000,
            state="visible",
        )

        # 3. 上传本地图片(京东封面上传 input 在 ._local-upload-localupload-upload-input_1vrwk_331)
        file_input = await self.frame.wait_for_selector(
            "._local-upload-localupload-upload-input_1vrwk_331",
            timeout=10_000,
            state="attached",  # 隐藏 file input
        )
        await file_input.set_input_files(str(cover_path.absolute()))

        # 4. 等图片加载
        await asyncio.sleep(2)

        # 5. 点弹窗确定按钮(在 .jd-modal-footer 内)
        confirm_btn = await self.frame.wait_for_selector(
            ".jd-modal-footer .jd-btn-primary",
            timeout=10_000,
        )
        await confirm_btn.click()

        # 6. 等弹窗关闭
        await self.frame.wait_for_selector(
            ".jd-modal-content",
            timeout=10_000,
            state="hidden",
        )
        await asyncio.sleep(1)

    # ---------- 标题 ----------

    async def _fill_title(self, title: str):
        """填写标题(最多 27 字,超长截断)。

        DOM: input#title (京东标题 input 有 id='title')
        """
        title = title.strip()[:27]  # 京东最多 27 字

        title_input = await self.frame.wait_for_selector(
            "input#title",
            timeout=10_000,
        )
        await title_input.click()
        await title_input.fill("")  # 清空
        await asyncio.sleep(0.3)
        await title_input.fill(title)
        await asyncio.sleep(0.5)

        # 验证:jd-form-item-has-success 类出现
        has_success = await self.frame.query_selector(
            "input#title"
        )
        if has_success:
            parent = await has_success.evaluate_handle(
                "el => el.closest('.jd-form-item')"
            )
            cls = await parent.get_property("className")
            cls_str = await cls.json_value()
            if "jd-form-item-has-success" not in cls_str:
                logger.warning(f"标题校验未通过: {cls_str}")

    # ---------- 关联挂件 ----------

    async def _link_products(self, items: list):
        """按 trace 分组重现(参考淘宝光合 _replay_groups 但简化)。

        流程:
        1. 切商品 radio + 点添加 + 等抽屉就绪(只开一次)
        2. 按 (keyword, page) 分组
        3. 每组重走:search(已合并 clear+Enter) → 翻页 → locate_and_check
        4. 点确定关闭抽屉
        """
        if not items:
            return

        # 0. import link_ops
        from . import _jd_link_ops as link_ops

        # 1. 打开抽屉
        await link_ops.switch_radio(self.frame, "product")
        await link_ops.click_add_card(self.frame)
        await link_ops.wait_panel_ready(self.frame)

        # 2. 分组
        groups: dict = {}
        for item in items:
            trace = item.get("trace") or {}
            sig = link_ops.trace_signature(trace)
            groups.setdefault(sig, []).append(item)

        logger.info(f"[关联商品] 待关联 items: {items}")

        # 3. 每组重走
        for (keyword, page), group_items in groups.items():
            # link_ops.search 内部已合并 clear + (if keyword) fill + Enter + wait,
            # 这里直接调,空 keyword 也会触发"全部商品"
            await link_ops.search(self.frame, keyword)

            if page > 1:
                # 翻到指定页
                current = await link_ops.get_current_page(self.frame)
                if current < page:
                    for _ in range(page - current):
                        nxt = await self.frame.query_selector(
                            ".jd-pagination-next:not(.jd-pagination-disabled)"
                        )
                        if not nxt:
                            raise RuntimeError(
                                f"无法翻到第 {page} 页:next 按钮不可用"
                            )
                        await nxt.click()
                        await link_ops.wait_page_change(self.frame)
                elif current > page:
                    for _ in range(current - page):
                        prv = await self.frame.query_selector(
                            ".jd-pagination-prev:not(.jd-pagination-disabled)"
                        )
                        if not prv:
                            raise RuntimeError(
                                f"无法翻到第 {page} 页:prev 按钮不可用"
                            )
                        await prv.click()
                        await link_ops.wait_page_change(self.frame)

            # 4. 精准勾选
            target_ids = [it.get("id", "") for it in group_items if it.get("id")]
            logger.info(f"[关联商品] keyword={keyword!r} page={page} target_ids={target_ids}")
            if not target_ids:
                raise RuntimeError(f"商品组 (keyword={keyword!r}, page={page}) 缺少 id")

            result = await link_ops.locate_and_check(self.frame, target_ids)
            logger.info(
                f"[关联商品] locate 结果: checked={result.checked} "
                f"already={result.already} disabled={result.disabled} missing={result.missing}"
            )
            if result.missing:
                raise RuntimeError(
                    f"关联商品失败,未找到商品(sku_id): {result.missing}"
                )
            if result.disabled:
                logger.warning(f"以下商品已下架,无法勾选: {result.disabled}")

        # 5. 等所有勾选的 React 状态更新完成,再点「确定」(否则确定先于勾选生效)
        await asyncio.sleep(1.0)
        await link_ops.click_confirm(self.frame)

    async def _select_novel(self, novel):
        """选小说(下拉搜索)。

        Args:
            novel: {"title": str, "image": str, "id": str}
        """
        from . import _jd_link_ops as link_ops

        # 1. 切到小说 radio
        await link_ops.switch_radio(self.frame, "novel")
        await asyncio.sleep(0.5)

        # 2. 调 link_ops.select_novel(按 title 搜索)
        await link_ops.select_novel(self.frame, novel.get("title", ""))

    # ---------- 创作声明 / 定时发布 ----------

    async def _set_declaration(self, declaration: str):
        """选创作声明。

        DOM 锚点:
        - 触发:  .content-declaration-wrapper .jd-select
        - 项:    .jd-select-item-option[label='{declaration}']
                 (京东创作声明选项带 label 属性,如 label="含AI生成内容")

        注意:不能用 .rc-virtual-list-holder-inner 等下拉出现 —— 页面有 2 个
        holder(创作声明 + 小说残留),wait_for_selector(state=visible) 只等第一个,
        而第一个不可见会超时。改用 label 精确匹配 + 轮询等下拉渲染。
        """
        # 1. 点创作声明 select
        select = await self.frame.wait_for_selector(
            ".content-declaration-wrapper .jd-select",
            timeout=10_000,
        )
        await select.click()

        # 2. 轮询等目标选项(用 label 精确匹配)出现
        target = None
        deadline = asyncio.get_event_loop().time() + 10
        while asyncio.get_event_loop().time() < deadline:
            items = await self.frame.query_selector_all(
                f".jd-select-item-option[label='{declaration}']"
            )
            if items:
                target = items[0]
                break
            await asyncio.sleep(0.3)

        if not target:
            raise RuntimeError(f"创作声明选项未找到: {declaration}")

        # 3. 点击选中
        await target.click()
        await asyncio.sleep(0.5)

    async def _set_schedule_time(self, schedule_time):
        """设定时发布时间。

        京东定时发布:
        1. 切到 .pro-radio-group 内 value='2' 的 radio('定时发布')
        2. 点 input[title](DatePicker 输入框),清空,fill 时间
        3. 在弹出的 DatePicker 中点确定按钮

        schedule_time 是 datetime 对象(parse_schedule_time 返回),也兼容 str。
        """
        from datetime import datetime

        # 京东 DatePicker 接受 'YYYY-MM-DD HH:mm' 格式
        if isinstance(schedule_time, datetime):
            formatted = schedule_time.strftime("%Y-%m-%d %H:%M")
        else:
            try:
                formatted = datetime.fromisoformat(str(schedule_time)).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                formatted = str(schedule_time)

        # 1. 切到定时发布 radio
        schedule_radio = await self.frame.wait_for_selector(
            ".jd-radio-wrapper input[value='2']",
            timeout=10_000,
        )
        await schedule_radio.click()
        await asyncio.sleep(0.5)

        # 2. 等 DatePicker 输入框出现
        date_input = await self.frame.wait_for_selector(
            ".pro-radio-extra input[placeholder='请选择日期'], .pro-radio-extra input",
            timeout=10_000,
        )
        await date_input.click()
        await asyncio.sleep(0.3)
        await date_input.fill("")
        await asyncio.sleep(0.3)
        await date_input.fill(formatted)
        await asyncio.sleep(0.5)

        # 3. 等 DatePicker 弹层(包含"确定"按钮)
        await self.frame.wait_for_selector(
            ".jd-picker-ok",
            timeout=10_000,
            state="visible",
        )

        # 4. 点确定按钮
        ok_btn = await self.frame.query_selector(".jd-picker-ok .jd-btn-primary")
        if not ok_btn:
            ok_btn = await self.frame.query_selector(".jd-picker-ok button")
        if not ok_btn:
            raise RuntimeError("DatePicker 确定按钮未找到")
        await ok_btn.click()
        await asyncio.sleep(1)

    # ---------- 发布 ----------

    async def _click_publish(self, timeout: float = 30):
        """点发布按钮。

        发布按钮可能因表单未完整而 disabled,需要等待其变为可点。
        """
        # 1. 等发布按钮 enabled
        deadline = asyncio.get_event_loop().time() + timeout
        btn = None
        while asyncio.get_event_loop().time() < deadline:
            btn = await self.frame.query_selector("._publishBtn_6bi9b_150")
            if btn:
                disabled = await btn.get_attribute("disabled")
                if disabled is None:
                    break
            btn = None
            await asyncio.sleep(0.5)

        if btn is None:
            raise RuntimeError("京东发布按钮未变为可用(超时)")

        # 2. 点击
        await btn.click()

        # 3. 等弹窗(可能有发布确认对话框)
        await asyncio.sleep(2)

    async def _check_publish_success(self, timeout: float = 60) -> bool:
        """检测发布成功:URL 跳转到其他页面。

        发布成功后,京东通常跳转到 https://dr.jd.com/jm/#/n/...
        中的视频管理页或提示页。

        Returns:
            True: 发布成功
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url
            # 判定:URL 跳出发布页(跳转到 content-list 等列表页/管理页)即成功。
            # 不依赖 original_url 对比 —— _click_publish 里 sleep(2) 后页面可能已跳转,
            # 若此时取 original_url 拿到的就是跳转后 URL,对比永远相等导致漏判。
            if "dr.jd.com" in url and "publish-video" not in url:
                logger.info(f"京东发布成功,跳转到: {url}")
                return True
            # 检测成功提示 toast(只匹配精确 toast 容器,避免与表单校验态 jd-form-item-has-success 冲突)
            for sel in [
                ".jd-message-success",
                ".ant-message-success",
                ".jd-notification-notice-success",
            ]:
                toast = await self.page.query_selector(sel)
                if toast:
                    txt = (await toast.inner_text()).strip()
                    if "成功" in txt or "发布" in txt:
                        logger.info(f"京东发布成功(toast {sel}): {txt}")
                        return True
            await asyncio.sleep(1)

        raise RuntimeError("京东发布失败,未检测到 URL 跳转或成功提示")


# ---------- profile scraper ----------


async def _scrape_jd_profile(page) -> tuple[str, str]:
    """京东专用 profile 抓取器(顶栏头像/昵称,无哈希 BEM class)。

    DOM 与京东京麦相同 — 复用同一组 class(``shop-menu-account__right-avatar``、
    ``shop-menu-accountV1__right-account-top-name``)。如果未来两者视觉层不同,
    再拆出独立 scraper。

    Returns:
        tuple[name, avatar]
    """
    name, avatar = "", ""
    try:
        await asyncio.sleep(2)

        try:
            avatar_el = page.locator(".shop-menu-account__right-avatar").first
            if await avatar_el.count() > 0:
                avatar = (await avatar_el.get_attribute("src") or "").strip()
                if avatar.startswith("//"):
                    avatar = "https:" + avatar
        except Exception as e:
            logger.info(f"[jd] 头像抓取失败: {e}")

        try:
            name_el = page.locator(
                ".shop-menu-accountV1__right-account-top-name"
            ).first
            if await name_el.count() > 0:
                name = (await name_el.get_attribute("title") or "").strip()
                if not name:
                    name = (await name_el.text_content() or "").strip()
        except Exception as e:
            logger.info(f"[jd] 昵称抓取失败: {e}")

        logger.info(
            f"[jd] profile scraped - name={name!r} avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:
        logger.info(f"[jd] profile scrape error: {e}")

    return name, avatar