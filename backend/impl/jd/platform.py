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
import sqlite3
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import get_channel_logger

from .._utils import save_login_result
from ..base_platform import BasePlatform

logger = get_channel_logger("jd")

JD_PUBLISH_URL = "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop"
JD_CREATOR_CENTER_URL = "https://dr.jd.com/jm/"

# Cookie 失效/未登录时会被重定向到这些域
JD_COOKIE_INVALID_MARKERS = (
    "passport.jd.com",
    "passport.shop.jd.com",
)

# 视为已登录的域名
JD_HOME_HOST = "dr.jd.com"

JD_DRY_RUN = os.environ.get("JD_DRY_RUN", "").lower() in ("1", "true", "yes")
# 反向开关:JD 端默认 dry-run(不真发布,只走完表单填写并截图)。
# 设 JD_REAL_PUBLISH=1 才会真的点发布按钮 —— 防止测试表单时误发。
# 显式 JD_DRY_RUN=0 也能关 dry-run(等价于 REAL_PUBLISH=1)。
JD_REAL_PUBLISH = os.environ.get("JD_REAL_PUBLISH", "").lower() in ("1", "true", "yes")
JD_DRY_RUN_DEFAULT = not JD_REAL_PUBLISH


def _resolve_cookie_filename(account_id: str | None) -> str | None:
    """根据 user_info.id 取 cookiesFile 路径(参考 jingmai/picker.py 的实现)。"""
    if not account_id:
        return None
    db_path = Path(BASE_DIR / "db" / "database.db")
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT filePath FROM user_info WHERE id = ?", (account_id,)
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning("查询 cookie 文件名失败 (account_id=%s): %s", account_id, e)
        return None


def _resolve_cookie_path(cookie_filename: str | None) -> Path | None:
    """把 cookiesFile 名字解析为绝对路径,文件不存在返回 None。"""
    if not cookie_filename:
        return None
    p = Path(BASE_DIR / "cookiesFile") / cookie_filename
    return p if p.exists() else None


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
        """同步入口:被 app.py 调用。

        kwargs:
            account_id: 账号 ID
            video_path: 视频文件路径
            title: 标题(必填,≤27 字)
            cover_path: 封面图路径(可选)
            jd_related_type: 'product' / 'novel' / ''
            jd_products: list[dict](含 id + trace)
            jd_novel: dict 或 ''
            jd_declaration: str
            schedule_time: str(ISO 格式)
        """
        try:
            return asyncio.run(self._publish_async(**kwargs))
        except Exception as e:
            logger.exception("京东 publish_video 失败")
            raise

    async def _publish_async(self, **kwargs) -> bool:
        """发布主流程(参考淘宝光合 platform.py L719-840)。"""
        account_id = kwargs.get("account_id")
        cookie_filename = _resolve_cookie_filename(account_id)
        cookie_file = _resolve_cookie_path(cookie_filename)

        if not cookie_file or not cookie_file.exists():
            raise FileNotFoundError(f"cookie 不存在,请先登录: account_id={account_id}")

        self.browser = await self.create_browser(headless=False)
        ctx = await self.create_context(self.browser, storage_state=str(cookie_file))
        self.page = await ctx.new_page()

        try:
            # 1. goto 发布页
            await self._goto_publish_page()

            # 2. 上传视频
            video_path = kwargs.get("video_path")
            if not video_path:
                raise ValueError("video_path 必填")
            await self._upload_video(Path(video_path))
            await self._wait_upload_complete()

            # 3. 设置封面(可选,京东有 * 必填但可接受默认封面)
            cover_path = kwargs.get("cover_path")
            if cover_path and Path(cover_path).exists():
                await self._set_cover(Path(cover_path))

            # 4. 填写标题
            title = kwargs.get("title", "")
            await self._fill_title(title)

            # 5. 关联挂件
            related_type = kwargs.get("jd_related_type", "")
            if related_type == "product" and kwargs.get("jd_products"):
                await self._link_products(kwargs["jd_products"])
            elif related_type == "novel" and kwargs.get("jd_novel"):
                await self._select_novel(kwargs["jd_novel"])

            # 6. 创作声明
            declaration = kwargs.get("jd_declaration", "")
            if declaration:
                await self._set_declaration(declaration)

            # 7. 定时发布
            schedule_time = kwargs.get("schedule_time", "")
            if schedule_time:
                await self._set_schedule_time(schedule_time)

            # 8. dry-run:走完所有表单填写后,**不点发布按钮**,只打印表单预览 + 截图,
            #    让用户能直接看到表单填得对不对。默认开启(JD_DRY_RUN_DEFAULT=True),
            #    需真发布时设环境变量 JD_REAL_PUBLISH=1。
            #    显式 JD_DRY_RUN=0 / JD_REAL_PUBLISH=1 关闭 dry-run。
            dry_run = JD_DRY_RUN or JD_DRY_RUN_DEFAULT
            if dry_run:
                await self._dry_run_preview(kwargs)
                logger.info("[JD dry-run] 跳过点击发布按钮(设 JD_REAL_PUBLISH=1 可真发布)")
                return True

            # 9. 点击发布按钮
            await self._click_publish()
            return await self._check_publish_success()
        finally:
            await self.close_browser(self.browser, is_close_by_code=True)
            self.browser = None
            self.page = None
            self.frame = None

    async def _goto_publish_page(self):
        """goto 发布页 + 进 iframe + 等表单渲染。

        关键:京东是微前端架构,top frame 只是主壳,真正的发布表单在 iframe 里。
        所有后续表单操作都用 self.frame,不能用 self.page(否则永远找不到元素)。
        """
        from backend.impl.jd import _jd_link_ops as link_ops

        # 1. domcontentloaded 快速返回(不用 networkidle,见 picker.py 同样优化)
        await self.page.goto(JD_PUBLISH_URL, wait_until="domcontentloaded")

        # 2. cookie 失效检测
        current_url = self.page.url or ""
        if any(m in current_url for m in JD_COOKIE_INVALID_MARKERS):
            raise RuntimeError("cookie 失效,请重新登录京东")

        # 3. 等发布表单 iframe 出现
        self.frame = await link_ops.wait_publish_frame(self.page, timeout=20)
        logger.info(f"[JD][publish] ✓ iframe={self.frame.url}")

        # 4. 在 iframe 里等表单关键元素
        await self.frame.wait_for_selector(
            ".video-upload-wrapper",
            timeout=15_000,
            state="visible",
        )
        await asyncio.sleep(1)

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
        from backend.impl.jd import _jd_link_ops as link_ops

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
            if not target_ids:
                raise RuntimeError(f"商品组 (keyword={keyword!r}, page={page}) 缺少 id")

            result = await link_ops.locate_and_check(self.frame, target_ids)
            if result.missing:
                raise RuntimeError(
                    f"关联商品失败,未找到商品(sku_id): {result.missing}"
                )
            if result.disabled:
                logger.warning(f"以下商品已下架,无法勾选: {result.disabled}")

        # 5. 关闭抽屉
        await link_ops.click_confirm(self.frame)

    async def _select_novel(self, novel):
        """选小说(下拉搜索)。

        Args:
            novel: {"title": str, "image": str, "id": str}
        """
        from backend.impl.jd import _jd_link_ops as link_ops

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
        - 下拉:  .rc-virtual-list-holder-inner
        - 项:    .jd-select-item-option[label='{declaration}']
        """
        # 1. 点 .content-declaration-wrapper .jd-select
        select = await self.frame.wait_for_selector(
            ".content-declaration-wrapper .jd-select",
            timeout=10_000,
        )
        await select.click()
        await asyncio.sleep(0.5)

        # 2. 等下拉出现
        await self.frame.wait_for_selector(
            ".rc-virtual-list-holder-inner",
            timeout=10_000,
            state="visible",
        )
        await asyncio.sleep(0.3)

        # 3. 点对应选项(用 label 属性精确匹配)
        item_selector = f".jd-select-item-option[label='{declaration}']"
        item = await self.frame.query_selector(item_selector)
        if not item:
            # 退而求其次:按文本匹配
            items = await self.frame.query_selector_all(".jd-select-item-option")
            for it in items:
                lbl = await it.get_attribute("label")
                if lbl and lbl.strip() == declaration:
                    item = it
                    break
        if not item:
            raise RuntimeError(f"创作声明选项未找到: {declaration}")

        await item.click()
        await asyncio.sleep(0.5)

    async def _set_schedule_time(self, schedule_time: str):
        """设定时发布时间。

        京东定时发布:
        1. 切到 .pro-radio-group 内 value='2' 的 radio('定时发布')
        2. 点 input[title](DatePicker 输入框),清空,fill ISO 时间
        3. 在弹出的 DatePicker 中点确定按钮
        """
        from datetime import datetime

        # 京东 DatePicker 接受 'YYYY-MM-DD HH:mm' 格式
        try:
            dt = datetime.fromisoformat(schedule_time)
            formatted = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            formatted = schedule_time

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

    async def _dry_run_preview(self, kwargs: dict):
        """dry-run 模式下打印表单预览 + 保存截图。

        从 iframe DOM 抓"实际填进去的值"(不是 kwargs 传入值),让用户能直接看到
        React 是否正确接收了输入,以及关联挂件/声明是否真的选上了。
        """
        from datetime import datetime

        logger.info("=" * 60)
        logger.info("[JD dry-run] 表单预览(实际 DOM 抓取,非 kwargs)")
        logger.info("=" * 60)

        # 视频路径(kwargs 传入值,DOM 没法直接读出文件路径)
        logger.info(f"  视频路径(kwargs): {kwargs.get('video_path')}")

        # 标题(input#title 的实际 value)
        try:
            title_el = await self.frame.query_selector("input#title")
            actual_title = await title_el.get_attribute("value") if title_el else ""
            expected_title = (kwargs.get("title") or "")[:27]
            mark = "✓" if actual_title == expected_title else "✗"
            logger.info(f"  标题: {mark} actual={actual_title!r} expected={expected_title!r}")
        except Exception as e:
            logger.warning(f"  标题读取失败: {e}")

        # 关联挂件类型(从 radio 选中态判断)
        try:
            radio_state = await self.frame.evaluate(
                """() => {
                    const checked = document.querySelector(
                        '.jd-radio-wrapper.jd-radio-wrapper-checked input.jd-radio-input'
                    );
                    if (!checked) return {value: null, label: null};
                    const label = checked.closest('.jd-radio-wrapper').textContent.trim();
                    return {value: checked.getAttribute('value'), label};
                }"""
            )
            logger.info(f"  关联挂件: value={radio_state.get('value')} label={radio_state.get('label')!r}")
        except Exception as e:
            logger.warning(f"  关联挂件 radio 读取失败: {e}")

        # 已选商品数量(从 .addgoods-upload 的 N/10 文本)
        try:
            addgoods_text = await self.frame.evaluate(
                """() => {
                    const el = document.querySelector('.addgoods-upload');
                    return el ? el.textContent.trim() : null;
                }"""
            )
            logger.info(f"  添加商品卡片文本: {addgoods_text!r} (期望形如 'N/10')")
        except Exception as e:
            logger.warning(f"  商品计数读取失败: {e}")

        # 创作声明(从 .content-declaration-wrapper .jd-select-title__selected 之类的文本)
        try:
            decl_text = await self.frame.evaluate(
                """() => {
                    const sel = document.querySelector('.content-declaration-wrapper .jd-select');
                    if (!sel) return null;
                    // jd-select 显示选中项的文本通常在 .jd-select-selection-item 或 select-selector 内
                    return (sel.textContent || '').trim().slice(0, 60);
                }"""
            )
            logger.info(f"  创作声明(select 文本): {decl_text!r} (期望={kwargs.get('jd_declaration')!r})")
        except Exception as e:
            logger.warning(f"  创作声明读取失败: {e}")

        # 定时发布(kwargs 传入值)
        if kwargs.get("schedule_time"):
            logger.info(f"  定时发布(kwargs): {kwargs.get('schedule_time')}")

        # 截图(保存到 data/logs/<date>/jd_dry_run_<timestamp>.png)
        try:
            from conf import BASE_DIR
            today = datetime.now().strftime("%Y-%m-%d")
            ts = datetime.now().strftime("%H%M%S")
            log_dir = Path(BASE_DIR) / "logs" / today
            log_dir.mkdir(parents=True, exist_ok=True)
            shot_path = log_dir / f"jd_dry_run_{ts}.png"
            await self.page.screenshot(path=str(shot_path), full_page=True)
            logger.info(f"  截图: {shot_path}")
        except Exception as e:
            logger.warning(f"  截图失败: {e}")

        logger.info("=" * 60)

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
        original_url = self.page.url
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url
            # 简单判定:URL 跳出发布页 hash
            if url != original_url and "publish-video.html" not in url:
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