"""
VIVO 内容创作平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作者中心地址：https://www.kaixinkan.com.cn/#/home
视频发布地址：https://www.kaixinkan.com.cn/#/content/uploads

对接原则(文档要求):禁止使用随机字符串匹配元素,即不依赖 class 中的 hash
片段(如 ``data-v-xxxx``)。所有 selector 都用产品语义 class 或稳定文案定位。
"""

import asyncio
import json
import os
import threading
from pathlib import Path
from queue import Queue

from util._logger import bind_account_name, get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_vivo_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("vivo")

# 创作者中心 / 视频发布地址
_VIVO_HOME_URL = "https://www.kaixinkan.com.cn/#/home"
_VIVO_UPLOAD_URL = "https://www.kaixinkan.com.cn/#/content/uploads"

# 视频上传最大等待时间(文档:不超过 2G / 90min,这里给足 4 小时)
_UPLOAD_MAX_WAIT = 4 * 60 * 60


class VivoPlatform(BasePlatform):
    platform_id = 16
    platform_key = "vivo"
    platform_name = "VIVO"

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform VIVO login via QR code scan.

        流程(参考 channels 平台 login):
          1. 用可见浏览器打开 VIVO 创作中心 ``/#/home``
          2. 未登录时由平台自动跳转到登录页(由用户在浏览器里扫码完成)
          3. 后端只轮询页面状态:一旦出现 ``.user-info-area`` 资料卡即判定登录成功
          4. 调用 ``save_login_result`` 抓取资料 + 落库 + 推送 status:200 给前端
          5. 成功后关闭浏览器;失败/超时则保留浏览器让用户看现场

        不主动推送二维码图片(与 channels 一致):VIVO 登录页结构未知且可能
        用 iframe 渲染,前端在打开的浏览器里直接扫即可,只等 status:200。
        """
        logger.info("=" * 60)
        logger.info("[登录] 开始 VIVO 登录流程")
        logger.info("=" * 60)

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                logger.info("[登录] 正在打开VIVO创作中心: %s", _VIVO_HOME_URL)
                try:
                    await page.goto(_VIVO_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.warning("[登录] 打开页面异常(继续等待用户操作): %s", e)
                logger.info("[登录] 页面已打开,当前 URL: %s", page.url)
                logger.info("[登录] 等待用户在浏览器中扫码登录...")

                # 轮询检测登录成功:用户资料卡 .user-info-area 出现
                # (VIVO 用 hash 路由,登录后会渲染 home 页资料卡)
                max_wait = 300  # 5 分钟
                poll_interval = 3
                start_time = asyncio.get_event_loop().time()
                logged_in = False
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    try:
                        if await page.locator(".user-info-area").count() > 0:
                            logger.info("[登录] 检测到用户资料卡,登录成功! URL: %s", page.url)
                            logged_in = True
                            break
                    except Exception as e:
                        logger.warning("[登录] 轮询异常(继续等待): %s", e)
                    await asyncio.sleep(poll_interval)

                if not logged_in:
                    # 关键:未登录成功就不要 save_login_result(避免抓到空数据写脏记录)
                    logger.error("[登录] 等待超时(5分钟未检测到登录),URL: %s", page.url)
                    status_queue.put(json.dumps({
                        "status": "failed",
                        "message": "登录超时,请重试",
                    }))
                    return  # finally 会关闭 context,但浏览器保留(success=False)

                # 登录成功 → 抓取资料 + 落库 + 推 status:200
                logger.info("[登录] 正在获取用户信息...")
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_vivo_profile,
                    account_id=account_id,
                )
                logger.info("[登录] 登录流程完成!")
                success = True
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
        except Exception as exc:
            logger.error("[登录] 异常: %s", exc)
            import traceback
            logger.error("[登录] traceback: %s", traceback.format_exc())
            status_queue.put(json.dumps({
                "status": "failed",
                "message": str(exc),
            }))
        finally:
            # 成功才关浏览器(失败/超时保留让用户看现场,与 channels 一致)
            if success:
                try:
                    await browser.close()
                except Exception:
                    pass

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
                    _VIVO_HOME_URL,
                    wait_until="domcontentloaded",
                    timeout=15000,
                )
                await asyncio.sleep(3)

                if await page.locator(".user-info-area").count() > 0:
                    logger.info("[Cookie检查] Cookie有效,用户资料卡存在")
                    return True

                logger.warning("[Cookie检查] Cookie无效,未找到用户资料卡")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar / fans / likes / follows
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """Sync profile info from VIVO creator centre.

        Returns:
            dict: ``{"name": str, "avatar": str, "stats": [{"ICON","COUNT","NAME","SORT"}, ...]}``
            VIVO 平台无关注数概念,follows 固定为 0。
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
                        _VIVO_HOME_URL,
                        wait_until="domcontentloaded",
                        timeout=30000,
                    )
                except Exception:
                    pass
                await asyncio.sleep(3)
                name, avatar, fans, likes, follows = await scrape_vivo_profile(page)
                logger.info(
                    "[同步资料] 昵称: %s, 头像: %s, 粉丝: %d, 获赞: %d, 关注: %d",
                    name, avatar[:50] if avatar else "无", fans, likes, follows,
                )
                return {
                    "name": name,
                    "avatar": avatar,
                    "stats": [
                        {"ICON": "user",   "COUNT": fans,   "NAME": "粉丝", "SORT": 1},
                        {"ICON": "like",   "COUNT": likes,  "NAME": "获赞", "SORT": 2},
                        {"ICON": "follow", "COUNT": follows, "NAME": "关注", "SORT": 3},
                    ],
                }
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the VIVO creator centre in a visible browser window."""
        logger.info("[打开创作中心] 正在打开创作中心...")
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(_VIVO_HOME_URL)
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
    # publish_video — full VIVO upload pipeline
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs) -> bool:
        """Publish a video to VIVO via CloakBrowser."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始 VIVO 视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)",
                        key, value, type(value).__name__)

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
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path", "")
        # VIVO 固定 3:4 竖版封面;若无竖版则用横版兜底
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path", "")

        # VIVO 平台特有参数
        vivo_location_name = kwargs.get("vivo_location_name", "")
        vivo_distribution = kwargs.get("vivo_distribution", False)
        vivo_declaration = kwargs.get("vivo_declaration", "")
        vivo_privacy = kwargs.get("vivo_privacy", "公开")
        vivo_download_permission = kwargs.get("vivo_download_permission", "允许")

        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 定时发布: %s", enableTimer)
        logger.info("[发布参数] 位置: %s", vivo_location_name or "(无)")
        logger.info("[发布参数] 作品同步: %s", vivo_distribution)
        logger.info("[发布参数] 自主声明: %s", vivo_declaration or "(无)")
        logger.info("[发布参数] 谁可以看: %s", vivo_privacy)
        logger.info("[发布参数] 下载权限: %s", vivo_download_permission)
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")

        # Resolve full paths
        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(thumbnail_portrait_path)
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(thumbnail_landscape_path)

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
            logger.info("[发布进度] 处理第 %d/%d 个视频: %s",
                        file_index + 1, len(file_paths), file_path)
            for cookie_index, cookie_path in enumerate(account_paths):
                cookie_name = Path(cookie_path).name
                nick = get_account_name_by_cookie_file(cookie_name)
                with bind_account_name(nick or "-"):
                    logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)",
                                cookie_index + 1, len(account_paths), nick or "未知")
                    await self._upload_one_video(
                        title=title,
                        file_path=file_path,
                        tags=tags,
                        desc=desc,
                        publish_date=publish_datetimes[file_index],
                        publish_strategy=publish_strategy,
                        account_file=cookie_path,
                        thumbnail_portrait_path=thumbnail_portrait_path or None,
                        thumbnail_landscape_path=thumbnail_landscape_path or None,
                        vivo_location_name=vivo_location_name,
                        vivo_distribution=vivo_distribution,
                        vivo_declaration=vivo_declaration,
                        vivo_privacy=vivo_privacy,
                        vivo_download_permission=vivo_download_permission,
                        # dry_run 模式:环境变量 VIVO_DRY_RUN=1 启用,
                        # 填完所有字段后停在发布界面,不点提交,方便观察
                        dry_run=os.environ.get("VIVO_DRY_RUN", "").strip() == "1",
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)
        return True

    # ------------------------------------------------------------------
    # Internal: upload one video to one account
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        desc: str,
        publish_date,
        publish_strategy: str,
        account_file: str,
        thumbnail_portrait_path=None,
        thumbnail_landscape_path=None,
        vivo_location_name: str = "",
        vivo_distribution: bool = False,
        vivo_declaration: str = "",
        vivo_privacy: str = "公开",
        vivo_download_permission: str = "允许",
        dry_run: bool = False,
    ):
        """Upload a single video to one VIVO account.

        严格按 vivo.md 文档流程,所有 selector 用产品语义 class 或文案定位,
        禁用 data-v-xxx / 随机字符串。

        dry_run=True 时填完所有字段后**停在发布界面**(不点提交按钮),
        让用户观察填写结果。设置环境变量 ``VIVO_DRY_RUN=1`` 启用。
        """
        logger.info("[上传视频] 开始上传视频: %s", file_path)
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()
                logger.info("[上传视频] 正在打开发布页面...")
                await page.goto(_VIVO_UPLOAD_URL)
                await asyncio.sleep(3)
                logger.info("[上传视频] 发布页面已打开")

                # 1. 上传视频文件(隐藏 input=file)
                logger.info("[上传视频] 正在上传视频文件...")
                file_input = page.locator('input[type="file"][accept*="video"]')
                if not await file_input.count():
                    file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(file_path)
                logger.info("[上传视频] 视频文件已选择,等待上传完成...")

                # 2. 等待上传完成:轮询 .upload-progress + .success-text
                # 文档:只有视频上传完成了才可以进行后续的设置,等待 4 小时
                max_wait = _UPLOAD_MAX_WAIT
                start_time = asyncio.get_event_loop().time()
                upload_complete = False
                last_progress = ""
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    try:
                        success_text = page.locator('.success-text:has-text("上传成功")')
                        if await success_text.count():
                            upload_complete = True
                            logger.info("[上传视频] 视频上传成功!")
                            break
                        # 打印上传进度
                        progress_el = page.locator(".upload-progress").first
                        if await progress_el.count():
                            current_progress = (await progress_el.text_content() or "").strip()
                            if current_progress and current_progress != last_progress:
                                logger.info("[上传视频] 进度: %s", current_progress)
                                last_progress = current_progress
                    except Exception:
                        pass
                    await asyncio.sleep(2)

                if not upload_complete:
                    logger.error("[上传视频] 视频上传超时! 已等待 %d 秒", max_wait)
                    return

                await asyncio.sleep(2)

                # 3. 视频描述 + 标签(#xxx 直接拼在描述里,总长≤500字)
                # contenteditable 富文本,按 CLAUDE.md 用 press_sequentially 逐字符输入
                full_desc = desc or ""
                has_tags = bool(tags)
                if has_tags:
                    tag_str = " ".join(f"#{t}" for t in tags if t)
                    if tag_str:
                        full_desc = (full_desc + " " + tag_str).strip()
                # VIVO 描述上限 500 字
                full_desc = full_desc[:500]

                if full_desc:
                    logger.info("[填写描述] 内容: %s...",
                                full_desc[:50] if full_desc else "(空)")
                    desc_editor = page.locator(
                        '.rich-text [contenteditable="true"].add-text'
                    ).first
                    if not await desc_editor.count():
                        # 兜底:任何 contenteditable
                        desc_editor = page.locator(
                            '.rich-text [contenteditable="true"]'
                        ).first
                    if await desc_editor.count():
                        await desc_editor.click()
                        await asyncio.sleep(0.3)
                        await desc_editor.press_sequentially(full_desc, delay=80)
                        # 有标签时,末尾追加一个空格激活最后的话题标签
                        # (VIVO 的 #xxx 话题需要空格触发联想/格式化,与小红书/视频号一致)
                        if has_tags:
                            await asyncio.sleep(0.5)
                            await page.keyboard.press(" ")
                            logger.info("[填写描述] 已追加末尾空格激活话题标签")
                        logger.info("[填写描述] 视频描述填写完成")
                    else:
                        logger.warning("[填写描述] 未找到描述输入框!")
                else:
                    logger.info("[填写描述] 无视频描述")

                # 4. 设置封面(固定 3:4 竖版封面)
                # 文档:点 .cover-photo-img 打开弹窗 → 切「上传封面」tab(#tab-2)
                #      → input=file 上传 → 等待关闭
                cover_path = thumbnail_portrait_path or thumbnail_landscape_path
                if cover_path:
                    logger.info("[设置封面] 开始设置封面(3:4 竖版): %s", cover_path)
                    await self._set_cover(page, cover_path)
                else:
                    logger.info("[设置封面] 无自定义封面,跳过")

                # 5. 设置位置(可选)
                if vivo_location_name:
                    logger.info("[设置位置] 开始设置位置: %s", vivo_location_name)
                    await self._set_location(page, vivo_location_name)
                else:
                    logger.info("[设置位置] 无位置,跳过")

                # 6. 作品同步(可选 checkbox)
                logger.info("[作品同步] 设置作品同步开关: %s", vivo_distribution)
                await self._toggle_distribution(page, vivo_distribution)

                # 7. 自主声明(可选 select)
                if vivo_declaration:
                    logger.info("[自主声明] 选择自主声明: %s", vivo_declaration)
                    await self._set_declaration(page, vivo_declaration)
                else:
                    logger.info("[自主声明] 无自主声明,跳过")

                # 8. 谁可以看 / 下载权限(radio,默认值与平台一致时跳过)
                logger.info("[谁可以看] 设置谁可以看: %s", vivo_privacy)
                await self._set_radio_by_label(page, "谁可以看", vivo_privacy)
                logger.info("[下载权限] 设置下载权限: %s", vivo_download_permission)
                await self._set_radio_by_label(
                    page, "下载权限", vivo_download_permission
                )

                # 9. 定时发布(可选)
                if publish_strategy == "scheduled" and publish_date != 0:
                    logger.info("[定时发布] 设置定时发布时间: %s", publish_date)
                    await self._set_schedule_time(page, publish_date)
                else:
                    logger.info("[定时发布] 立即发布,跳过定时设置")

                # 9.5 dry_run 模式:填完所有字段后停在发布界面,不点提交
                #     让用户在浏览器里观察填写结果(便于调试表单字段)
                if dry_run:
                    logger.info("=" * 60)
                    logger.info("[dry_run] 已填完所有字段,停在发布界面观察")
                    logger.info("[dry_run] 等待 5 分钟后继续(或 Ctrl+C 中断)...")
                    logger.info("=" * 60)
                    await asyncio.sleep(300)
                    logger.info("[dry_run] 等待结束,不执行提交,直接退出")
                    # 直接 return,跳过提交 + cookie 写回(防止误发布)
                    return

                # 10. 提交
                logger.info("[提交] 正在点击提交按钮...")
                submit_btn = page.locator(
                    '.btns button.el-button--primary:has-text("提交")'
                )
                if not await submit_btn.count():
                    submit_btn = page.get_by_role("button", name="提交", exact=True)
                await submit_btn.click()

                # 11. 等待跳转(成功判断:URL 离开 uploads 页)
                logger.info("[提交] 等待页面跳转判断发布结果...")
                success = False
                wait_start = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - wait_start) < 60:
                    current_url = page.url
                    if "content/uploads" not in current_url and "#/uploads" not in current_url:
                        success = True
                        logger.info("[提交] 发布成功! 页面跳转到: %s", current_url)
                        break
                    await asyncio.sleep(1)

                if not success:
                    logger.warning("[提交] 提交后未检测到页面跳转,可能发布失败")

                # 12. 回写 cookie
                await context.storage_state(path=account_file)
                logger.info("[提交] Cookie 状态已更新")
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # Helper: 设置封面(3:4 竖版)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_cover(page, cover_path: str):
        """点封面图打开弹窗 → 切「上传封面」tab → 上传 → 处理裁剪 → 点确定。

        DOM(实测):
          入口: <div class="cover-photo-img"> 整个区域可点
          弹窗: <div role="dialog" class="el-dialog"> (Element-plus dialog)
          Tab: <div id="tab-2" class="el-tabs__item">上传封面</div>
          上传 input(弹窗内):
            <input type="file" name="file" accept=".png,.jpg,.jpeg"
                   class="el-upload__input">
          裁剪区(上传后显示): <div class="vue-croppert">
          弹窗底部按钮(不是 button!是 div):
            <div class="dialog-footer-left">取消</div>
            <div class="dialog-footer-right">确定</div>

        关键陷阱:
          1. accept=".png,.jpg,.jpeg" 不是 "image",别用 accept*="image"
          2. 确定/取消是 div 不是 button,不能用 button:has-text
          3. 必须用 .el-dialog 容器限定作用域,避免点中主页面的同名元素
          4. 裁剪完成后「确定」才可点;若图片是 3:4,可能不弹裁剪直接可点确定
        """
        try:
            # 1. 点封面图触发编辑弹窗
            cover_img = page.locator(".cover-photo-img").first
            if not await cover_img.count():
                logger.warning("[封面] 未找到封面图,跳过")
                return
            await cover_img.click(force=True)
            await asyncio.sleep(2)
            logger.info("[封面] 封面编辑弹窗已打开")

            # 弹窗容器(Element-plus dialog),所有后续操作都用它限定作用域
            dialog = page.locator("div.el-dialog[role='dialog']").last
            if not await dialog.count():
                logger.warning("[封面] 未找到弹窗容器,跳过")
                return

            # 2. 切换到「上传封面」tab
            upload_tab = dialog.locator(
                '.el-tabs__item:has-text("上传封面")'
            ).first
            if not await upload_tab.count():
                upload_tab = dialog.locator("#tab-2").first
            if await upload_tab.count():
                cls = await upload_tab.get_attribute("class") or ""
                if "is-active" not in cls:
                    await upload_tab.click()
                    await asyncio.sleep(1.5)
                    logger.info("[封面] 已切换到「上传封面」")
                else:
                    logger.info("[封面] 「上传封面」tab 已是激活状态")
            else:
                logger.warning("[封面] 未找到「上传封面」tab")

            # 3. 在弹窗内找上传 input
            #    实测 accept=".png,.jpg,.jpeg",不要用模糊匹配
            cover_input = dialog.locator(
                'input[type="file"][accept=".png,.jpg,.jpeg"]'
            ).first
            if not await cover_input.count():
                # 兜底:弹窗内任意 input[type=file]
                cover_input = dialog.locator('input[type="file"]').first
            if not await cover_input.count():
                logger.warning("[封面] 弹窗内未找到上传 input,跳过")
                return
            await cover_input.set_input_files(cover_path)
            logger.info("[封面] 封面文件已上传,等待裁剪区渲染...")
            await asyncio.sleep(4)

            # 4. 等待裁剪区出现(vue-croppert 初始 display:none,上传后才显示)
            croppert = dialog.locator(".vue-croppert").first
            crop_visible = False
            for _ in range(20):  # 最多等 10s
                if await croppert.count() > 0:
                    style = await croppert.get_attribute("style") or ""
                    if "display: none" not in style:
                        crop_visible = True
                        break
                await asyncio.sleep(0.5)
            if crop_visible:
                logger.info("[封面] 裁剪区已渲染")
            else:
                logger.info("[封面] 裁剪区未出现(图片可能符合规定比例),直接确定")

            # 5. 点「确定」按钮(div 不是 button)
            #    用 .last 确保点在弹窗底部,而不是其他位置
            confirm_btn = dialog.locator(
                '.dialog-footer-right:has-text("确定")'
            ).first
            if await confirm_btn.count():
                await confirm_btn.click()
                logger.info("[封面] 已点击「确定」")
                await asyncio.sleep(2)
            else:
                logger.warning("[封面] 未找到「确定」按钮")

            logger.info("[封面] 封面设置完成")
        except Exception as e:
            logger.error("[封面] 设置封面失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: 设置位置(下拉搜索)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_location(page, location_name: str):
        """VIVO 位置设置(文档):

        入口: .sel-position-module(点击展开输入框)
        输入: 展开后的可编辑文本元素(type 逐字符触发搜索)
        下拉: .position-list li,每项 .position-name + .position-info

        匹配策略:遍历 li 读 .position-name 文本,精确匹配则点击。
        """
        try:
            # 1. 点击位置入口展开输入框
            pos_module = page.locator(".sel-position-module").first
            if not await pos_module.count():
                logger.warning("[设置位置] 未找到位置入口,跳过")
                return
            await pos_module.click()
            await asyncio.sleep(1)

            # 2. 展开后的可编辑输入框(placeholder「输入地理位置」)
            # 文档:<span class="top-show placeholder">输入地理位置</span>
            # 点击后变为可编辑,直接用 type 在该模块内输入
            # 这里用 page.keyboard.type 兜底(已 focus 在该模块)
            await page.keyboard.type(location_name, delay=80)
            logger.info("[设置位置] 已输入: %s,等待下拉...", location_name)
            await asyncio.sleep(2)

            # 3. 等待下拉列表 .position-list li 出现
            position_items = page.locator(".position-list li")
            ready = False
            for _ in range(60):  # 最多等 30s
                if await position_items.count() > 0:
                    ready = True
                    break
                await asyncio.sleep(0.5)
            if not ready:
                logger.warning("[设置位置] 输入后未出现下拉选项,跳过")
                return

            # 4. 遍历下拉项,按 .position-name 精确匹配
            count = await position_items.count()
            logger.info("[设置位置] 下拉出现 %d 个选项", count)
            for i in range(count):
                li = position_items.nth(i)
                name_el = li.locator(".position-name").first
                if not await name_el.count():
                    continue
                # .position-name 内可能有 <i> 图标,用 inner_text 取纯文本
                name_text = (await name_el.inner_text() or "").strip()
                if name_text == location_name or location_name in name_text:
                    await li.click()
                    logger.info("[设置位置] 已选择: %s", name_text)
                    await asyncio.sleep(1)
                    return

            # 没有精确匹配则点第一项
            logger.warning(
                "[设置位置] 未找到精确匹配「%s」,选择第一项兜底", location_name
            )
            await position_items.first.click()
            await asyncio.sleep(1)
        except Exception as e:
            logger.error("[设置位置] 设置位置失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: 作品同步(checkbox)
    # ------------------------------------------------------------------

    @staticmethod
    async def _toggle_distribution(page, enable: bool):
        """勾选/取消「同时分发到vivo浏览器、i视频、阅图」checkbox。

        DOM(文档):
          <label class="el-checkbox mr20">
            <input type="checkbox" class="el-checkbox__original">
            <span class="el-checkbox__label">同时分发到vivo浏览器、i视频、阅图...</span>
          </label>
        """
        try:
            # 用文案定位 label(文案稳定,不依赖 class)
            label = page.locator(
                'label.el-checkbox:has-text("同时分发到vivo浏览器")'
            ).first
            if not await label.count():
                logger.info("[作品同步] 未找到作品同步复选框,跳过")
                return

            checkbox = label.locator('input[type="checkbox"]').first
            is_checked = False
            if await checkbox.count():
                is_checked = await checkbox.is_checked()

            if enable and not is_checked:
                await label.click()
                logger.info("[作品同步] 已勾选作品同步")
                await asyncio.sleep(0.5)
            elif not enable and is_checked:
                await label.click()
                logger.info("[作品同步] 已取消作品同步")
                await asyncio.sleep(0.5)
            else:
                logger.info("[作品同步] 状态已是目标状态")
        except Exception as e:
            logger.error("[作品同步] 设置失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: 自主声明(select 下拉)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_declaration(page, declaration: str):
        """VIVO 自主声明下拉(文档):

        触发: .short-play-select 内的 .el-input__inner(readonly input)
        选项: .el-select-dropdown__item:has-text("...")
        """
        try:
            # 1. 点击下拉触发器展开选项
            trigger = page.locator(".short-play-select .el-input__inner").first
            if not await trigger.count():
                # 兜底:整个 short-play-select 区块
                trigger = page.locator(".short-play-select").first
            if not await trigger.count():
                logger.warning("[自主声明] 未找到下拉触发器,跳过")
                return
            await trigger.click()
            await asyncio.sleep(1)

            # 2. 在下拉项中找匹配文案点击
            option = page.locator(
                f'.el-select-dropdown__item:has-text("{declaration}")'
            ).first
            if await option.count():
                await option.click()
                logger.info("[自主声明] 已选择: %s", declaration)
                await asyncio.sleep(0.5)
            else:
                logger.warning("[自主声明] 未找到选项: %s", declaration)
                # 关闭下拉(点空白处)
                await page.keyboard.press("Escape")
        except Exception as e:
            logger.error("[自主声明] 设置失败: %s", e)

    # ------------------------------------------------------------------
    # Helper: 谁可以看 / 下载权限(radio)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_radio_by_label(page, field_label: str, value: str):
        """通用 radio 设置:按字段标签 + 选项值定位 radio 并选中。

        DOM(文档):
          <div class="video-form-item">
            <div class="video-form-label"><div class="name">谁可以看</div></div>
            <div role="radiogroup" class="el-radio-group">
              <label role="radio">
                <input type="radio" value="0">
                <span class="el-radio__label">公开</span>
              </label>
              ...
            </div>
          </div>
        """
        try:
            # 定位字段所在区块 → 该区块内 radio 文案匹配的 label
            field_block = page.locator(
                f'.video-form-item:has(.video-form-label .name:has-text("{field_label}"))'
            ).first
            if not await field_block.count():
                logger.warning("[%s] 未找到字段区块,跳过", field_label)
                return

            target_label = field_block.locator(
                f'label[role="radio"]:has(.el-radio__label:has-text("{value}"))'
            ).first
            if not await target_label.count():
                logger.warning("[%s] 未找到选项: %s", field_label, value)
                return

            # 检查是否已选中
            is_checked = await target_label.get_attribute("aria-checked") == "true"
            # 也看 class 是否含 is-checked
            if not is_checked:
                cls = await target_label.get_attribute("class") or ""
                is_checked = "is-checked" in cls

            if not is_checked:
                await target_label.click()
                logger.info("[%s] 已选择: %s", field_label, value)
                await asyncio.sleep(0.5)
            else:
                logger.info("[%s] 已是目标状态: %s", field_label, value)
        except Exception as e:
            logger.error("[%s] 设置失败: %s", field_label, e)

    # ------------------------------------------------------------------
    # Helper: 定时发布(element DateTimePicker)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """VIVO 定时发布设置(简化方案):

        用户实测 + DOM 分析:Element-plus datetimepicker 在弹窗里直接提供两个 input
        文本框(选择日期 + 选择时间),直接 fill 文本 + 点确定 即可,不需要走 spinner 滚动。
        spinner 滚动方案对 Element-plus 虚拟滚动面板不稳定,直接填文本最稳。

        DOM:
          <input type="text" placeholder="选择日期"> ← 直接 fill yyyy-MM-dd
          <input type="text" placeholder="选择时间"> ← 直接 fill HH:mm
          <button class="el-picker-panel__link-btn is-plain">确定</button> ← 点确定关闭
        """
        try:
            # 1. 点「定时发布」radio
            timer_radio = page.locator(
                'label[role="radio"]:has(span.el-radio__label:has-text("定时发布"))'
            ).first
            if await timer_radio.count():
                is_checked = await timer_radio.get_attribute("aria-checked") == "true"
                if not is_checked:
                    cls = await timer_radio.get_attribute("class") or ""
                    is_checked = "is-checked" in cls
                if not is_checked:
                    await timer_radio.click()
                    await asyncio.sleep(1.5)
                    logger.info("[定时发布] 已切换到定时发布")
            else:
                logger.warning("[定时发布] 未找到「定时发布」radio")
                return

            # 2. 点击日期编辑器展开选择器
            date_editor = page.locator(
                ".el-date-editor.el-input, .el-date-editor--datetime"
            ).first
            if not await date_editor.count():
                logger.warning("[定时发布] 未找到日期编辑器")
                return
            await date_editor.click()
            await asyncio.sleep(1.5)
            logger.info("[定时发布] 日期时间选择器已展开")

            # 3. 解析目标时间
            date_str = publish_date.strftime("%Y-%m-%d")
            time_str = publish_date.strftime("%H:%M")
            logger.info("[定时发布] 目标时间: %s %s", date_str, time_str)

            # 4. 直接 fill 日期文本框(yyyy-MM-dd)
            date_input = page.locator(
                '.el-date-picker__editor-wrap input[placeholder="选择日期"]'
            ).first
            if await date_input.count():
                await date_input.fill(date_str)
                await asyncio.sleep(0.3)
                logger.info("[定时发布] 日期已填: %s", date_str)
            else:
                logger.warning("[定时发布] 未找到「选择日期」文本框")

            # 5. 直接 fill 时间文本框(HH:mm)
            time_input = page.locator(
                '.el-date-picker__editor-wrap input[placeholder="选择时间"]'
            ).first
            if await time_input.count():
                await time_input.fill(time_str)
                await asyncio.sleep(0.3)
                logger.info("[定时发布] 时间已填: %s", time_str)
            else:
                logger.warning("[定时发布] 未找到「选择时间」文本框")

            # 6. 点确定按钮(底栏第二个 button,class 含 is-plain)
            confirm_btn = page.locator(
                '.el-picker-panel__footer button.is-plain'
            ).first
            if not await confirm_btn.count():
                # 兜底:用文案
                confirm_btn = page.locator(
                    '.el-picker-panel__footer button:has-text("确定")'
                ).first
            if await confirm_btn.count():
                await confirm_btn.click()
                logger.info("[定时发布] 已点击确定")
                await asyncio.sleep(1)
            else:
                logger.warning("[定时发布] 未找到确定按钮")

            logger.info("[定时发布] 定时发布设置完成")
        except Exception as e:
            logger.error("[定时发布] 设置失败: %s", e)
            import traceback
            logger.error("[定时发布] traceback: %s", traceback.format_exc())
