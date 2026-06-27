"""知乎平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

登录地址：https://www.zhihu.com/settings/account
视频发布地址：https://www.zhihu.com/upload-video?entry=navPanel
"""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_zhihu_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("zhihu")

ZHIHU_LOGIN_URL = "https://www.zhihu.com/settings/account"
ZHIHU_UPLOAD_URL = "https://www.zhihu.com/upload-video?entry=navPanel"


class ZhihuPlatform(BasePlatform):
    platform_id = 14
    platform_key = "zhihu"
    platform_name = "知乎"

    # ------------------------------------------------------------------
    # login — 用户在可见浏览器中手动登录
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开知乎登录页，等待用户完成登录后保存 cookie。

        知乎登录方式（密码/扫码/第三方）较多样且频繁变动，统一让用户在
        可见浏览器里手动完成。检测到右上角头像按钮出现即视为登录成功。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(ZHIHU_LOGIN_URL)
                logger.info("[zhihu] 等待用户完成登录（检测右上角头像按钮）")

                # 头像按钮出现 = 登录成功。不设超时，用户自己关浏览器取消。
                await page.locator(".AppHeader-profileEntry").first.wait_for(
                    timeout=999999999
                )
                logger.info("[zhihu] 检测到头像按钮，登录成功")

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_zhihu_profile,
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

    # ------------------------------------------------------------------
    # check_cookie
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(ZHIHU_LOGIN_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=10000
                    )
                    await asyncio.sleep(2)
                except Exception:
                    pass
                profile_entry = page.locator(".AppHeader-profileEntry").first
                if await profile_entry.count() > 0:
                    logger.info("[zhihu] cookie valid")
                    return True
                logger.info("[zhihu] cookie expired")
                return False
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(
                    ZHIHU_LOGIN_URL, wait_until="domcontentloaded", timeout=30000
                )
                return await scrape_zhihu_profile(page)
            except Exception as e:
                logger.info(f"[zhihu] sync profile failed: {e}")
                return "", ""
            finally:
                await page.close()
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = ZHIHU_UPLOAD_URL

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
    # publish_video
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """发布视频到知乎。

        接受的 kwargs（由 app.py 统一传入）:
        - ``title`` (*str*) — 视频标题（≤50 字符）
        - ``files`` (*list[str]*) — 视频绝对路径
        - ``tags`` (*list[str]*) — 标签（写入简介区，#xxx 格式 + 空格激活）
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``category`` (*str*, 可选) — 所属领域（34 选 1）
        - ``creation_declaration`` (*str*, 可选) — 视频标记，默认「内容无需标注」
        - ``enableTimer`` (*bool*, 可选) — 是否定时发布
        - ``schedule_time_str`` (*str*, 可选) — 定时时间
        - ``videos_per_day`` / ``daily_times`` / ``start_days`` — 自动排期参数
        - ``desc`` (*str*, 可选) — 简介（≤2000 字符）
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` — 封面
        - ``video_format`` (*str*, 可选) — 'landscape' / 'portrait'
        """

        async def _run():
            logger.info("=" * 60)
            logger.info("[发布视频] 开始知乎视频发布流程")
            logger.info("=" * 60)

            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            tags = kwargs.get("tags") or []
            account_files = kwargs.get("account_file", [])
            category = kwargs.get("category") or ""
            creation_declaration = kwargs.get("creation_declaration") or "内容无需标注"
            enable_timer = kwargs.get("enableTimer", False)
            videos_per_day = kwargs.get("videos_per_day", 1)
            daily_times = kwargs.get("daily_times")
            start_days = kwargs.get("start_days", 0)
            desc = kwargs.get("desc", "") or ""
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "") or ""
            thumbnail_portrait = kwargs.get("thumbnail_portrait_path", "") or ""
            schedule_time_str = kwargs.get("schedule_time_str", "") or ""
            video_format = kwargs.get("video_format", "") or "landscape"

            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 文件数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 账号数量: %d", len(account_files))
            logger.info("[发布参数] 视频标记: %s", creation_declaration)
            logger.info("[发布参数] 所属领域: %s", category or '不设置')
            logger.info("[发布参数] 定时发布: %s", enable_timer)

            cookie_paths = [
                str(Path(BASE_DIR / "cookiesFile") / f) for f in account_files
            ]
            file_paths = [str(f) for f in files]

            thumbnail_path = (
                thumbnail_landscape if video_format != "portrait" else thumbnail_portrait
            )
            if not thumbnail_path:
                thumbnail_path = thumbnail_landscape or thumbnail_portrait

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
                logger.info(
                    "[发布进度] 处理第 %d/%d 个视频: %s",
                    index + 1, len(file_paths), file_path,
                )
                publish_date = (
                    publish_datetimes[index]
                    if isinstance(publish_datetimes, list)
                    else publish_datetimes
                )
                for cookie_index, cookie_path in enumerate(cookie_paths):
                    cookie_name = Path(cookie_path).name
                    nick = get_account_name_by_cookie_file(cookie_name)
                    with bind_account_name(nick or "-"):
                        logger.info(
                            "[发布进度] 发布到第 %d/%d 个账号 (%s)",
                            cookie_index + 1, len(cookie_paths), nick or "未知",
                        )
                        await self._upload_single_video(
                            title=title,
                            file_path=file_path,
                            tags=tags,
                            publish_date=publish_date,
                            account_file=cookie_path,
                            category=category,
                            creation_declaration=creation_declaration,
                            desc=desc,
                            thumbnail_path=thumbnail_path,
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
        category: str = "",
        creation_declaration: str = "内容无需标注",
        desc: str = "",
        thumbnail_path: str | None = None,
    ):
        log_dir = Path(BASE_DIR / "logs")
        log_dir.mkdir(parents=True, exist_ok=True)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            upload_success = False
            try:
                page = await context.new_page()
                logger.info(f"[上传视频] 开始上传视频: {title}")
                await page.goto(ZHIHU_UPLOAD_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=30000
                    )
                except Exception:
                    pass

                # cookie 失效会被重定向到登录页
                if "/signin" in page.url or "/login" in page.url:
                    raise RuntimeError("知乎 cookie 失效，请重新登录")

                # 1. 上传视频文件
                await self._upload_video_file(page, file_path)

                # 2. 等待视频上传成功
                await self._wait_upload_complete(page)
                await asyncio.sleep(2)

                # 3. 设置封面
                if thumbnail_path:
                    await self._set_thumbnail(page, thumbnail_path)

                # 4. 填写标题（≤50 字符）
                await self._fill_title(page, title)

                # 5. 填写简介 + 标签（≤2000 字符，标签用 #xxx + 空格激活）
                await self._fill_desc_and_tags(page, desc, tags)

                # 6. 视频标记（弹窗）
                await self._set_video_mark(page, creation_declaration)

                # 7. 原创视频开关（默认开启，确保勾选状态）
                await self._ensure_original_checked(page)

                # 8. 所属领域
                if category:
                    await self._set_category(page, category)

                # 9. 定时发布
                is_scheduled = (
                    isinstance(publish_date, int) and publish_date != 0
                ) or (not isinstance(publish_date, int) and publish_date)
                if is_scheduled:
                    await self._set_schedule_time(page, publish_date)

                # 提交前截图
                try:
                    await page.screenshot(
                        path=str(log_dir / "zhihu_before_submit.png"),
                        full_page=True,
                    )
                except Exception:
                    pass

                # 10. 点击发布按钮
                submitted = await self._click_submit(page, is_scheduled)
                if submitted:
                    logger.info("[上传视频] 发布成功（页面跳转）")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "zhihu_after_submit.png"),
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
                try:
                    await context.close()
                except Exception:
                    pass
        finally:
            try:
                await browser.close()
            except Exception:
                pass
            logger.info("[上传视频] browser closed")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        logger.info("[上传视频] 正在上传视频文件...")
        file_input = page.locator('input[type="file"][accept*="video"]').first
        try:
            await file_input.wait_for(state="attached", timeout=10000)
        except Exception:
            file_input = page.locator('input[type="file"]').first
            await file_input.wait_for(state="attached", timeout=10000)
        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择, 等待上传完成")

    @staticmethod
    async def _wait_upload_complete(page):
        """等待「上传成功」文案出现（spec 第 24 行）。

        `<div class="css-1269sre">上传成功</div>` 由后端在视频处理完成后
        渲染。无超时：宁可等也不跳过。
        """
        retry = 0
        while True:
            try:
                done = page.locator('text=上传成功')
                if await done.count() > 0 and await done.first.is_visible():
                    logger.info("[上传视频] 检测到「上传成功」，视频处理完成")
                    return
                fail = page.locator('text=上传失败')
                if await fail.count() > 0 and await fail.first.is_visible():
                    raise RuntimeError("视频上传失败")
            except RuntimeError:
                raise
            except Exception as exc:
                logger.info(f"[上传视频] 状态检查异常: {exc}")
            if retry % 10 == 0:
                logger.info(f"[上传视频] 上传中... ({retry * 3}s)")
            await asyncio.sleep(3)
            retry += 1

    @staticmethod
    async def _set_thumbnail(page, thumbnail_path: str):
        """设置视频封面（spec 第 28-34 行）。

        流程: 点击「选择视频封面」→ 切换到「本地上传」tab →
        文件 input → 点击「确认选择」。
        """
        import os

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logger.info(f"[设置封面] 封面文件不存在: {thumbnail_path}")
            return

        log_dir = Path(BASE_DIR / "logs")
        logger.info("[设置封面] 开始设置封面")

        try:
            # 1. 点击「选择视频封面」
            edit_btn = page.locator(
                '.VideoUploadForm-imageEditButton, '
                '[class*="VideoUploadForm-imageEditButton"]'
            ).first
            await edit_btn.wait_for(state="visible", timeout=15000)
            await edit_btn.click()
            logger.info("[设置封面] 已点击「选择视频封面」")
            await asyncio.sleep(1)

            # 2. 切换到「本地上传」tab
            local_tab = page.get_by_text("本地上传").first
            await local_tab.wait_for(state="visible", timeout=10000)
            await local_tab.click()
            logger.info("[设置封面] 已切换到「本地上传」")
            await asyncio.sleep(1)

            # 3. 上传封面文件（弹窗内的隐藏 input=file）
            file_input = page.locator('input[type="file"][accept*="image"]').first
            await file_input.wait_for(state="attached", timeout=10000)
            await file_input.set_input_files(thumbnail_path)
            logger.info("[设置封面] 封面文件已选择")
            await asyncio.sleep(2)

            # 4. 点击「确认选择」
            confirm_btn = page.locator(
                'button:has-text("确认选择"), '
                'button.Button--primary:has-text("确认")'
            ).first
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await confirm_btn.click()
            logger.info("[设置封面] 已点击「确认选择」")
            await asyncio.sleep(2)
        except Exception as exc:
            logger.info(f"[设置封面] 设置封面失败（非致命）: {exc}")
            try:
                await page.screenshot(
                    path=str(log_dir / "zhihu_cover_error.png"),
                    full_page=True,
                )
            except Exception:
                pass

    @staticmethod
    async def _fill_title(page, title: str):
        """标题 ≤50 字符（spec 第 38 行）。"""
        if not title:
            return
        title_text = title[:50]
        logger.info(f"[填写标题] 标题: {title_text}")
        title_input = page.locator(
            'textarea[name="title"], '
            'textarea[placeholder*="标题"], '
            '.TitleArea textarea'
        ).first
        await title_input.wait_for(state="visible", timeout=15000)
        await title_input.click()
        await title_input.fill("")
        await title_input.fill(title_text)
        await asyncio.sleep(0.5)

    @staticmethod
    async def _fill_desc_and_tags(page, desc: str, tags: list):
        """简介 ≤2000 字符（spec 第 39 行），标签用 #xxx + 空格激活（spec 第 42 行）。

        知乎简介是 contenteditable 富文本编辑器，标签需要 # 开头并跟随空格
        触发话题联想，逐个输入保证每个标签都被识别。
        """
        import re as _re

        full_text = desc or ""
        if full_text and len(full_text) > 2000:
            full_text = full_text[:2000]

        parsed_tags = []
        for t in tags or []:
            if isinstance(t, str):
                parsed_tags.extend(
                    s.strip().lstrip('#').strip()
                    for s in _re.split(r"[,，#]", t) if s.strip()
                )

        logger.info(f"[填写简介] 简介 {len(full_text)} 字符, 标签 {len(parsed_tags)} 个")

        editor = page.locator(
            '.EditorArea [contenteditable="true"], '
            '.Editable [contenteditable="true"], '
            '.WritePinV2-Form [contenteditable="true"]'
        ).first
        await editor.wait_for(state="visible", timeout=15000)
        await editor.click()

        if full_text:
            await page.keyboard.type(full_text, delay=10)
            await asyncio.sleep(0.3)

        for tag in parsed_tags:
            await page.keyboard.type(f" #{tag}", delay=30)
            await asyncio.sleep(0.3)
            await page.keyboard.type(" ", delay=30)
            await asyncio.sleep(0.5)

    @staticmethod
    async def _set_video_mark(page, creation_declaration: str):
        """视频标记弹窗（spec 第 45-52 行）。

        点击 ``VideoUploadForm-videoTypeSelectOverlay`` 唤起弹窗 → 点选匹配项
        → 点击「确认」。默认「内容无需标注」无需打开弹窗。
        """
        if not creation_declaration or creation_declaration == "内容无需标注":
            logger.info("[视频标记] 默认「内容无需标注」，跳过")
            return

        logger.info(f"[视频标记] 设置视频标记: {creation_declaration}")

        try:
            overlay = page.locator(
                '.VideoUploadForm-videoTypeSelectOverlay, '
                'button[aria-label="选择视频标记"]'
            ).first
            await overlay.wait_for(state="visible", timeout=10000)
            await overlay.click()
            await asyncio.sleep(1)

            modal = page.locator(
                '.VideoUploadForm-videoTypeModalContent, '
                '.Modal-inner:has-text("添加视频标记")'
            ).first
            await modal.wait_for(state="visible", timeout=10000)

            option = modal.locator(
                f'.VideoUploadForm-videoTypeModalOption:has-text("{creation_declaration}")'
            ).first
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            logger.info(f"[视频标记] 已选择: {creation_declaration}")
            await asyncio.sleep(0.5)

            confirm = modal.locator(
                '.VideoUploadForm-videoTypeModalActions button:has-text("确认"), '
                '.ModalButtonGroup button.Button--blue:has-text("确认")'
            ).first
            await confirm.wait_for(state="visible", timeout=5000)
            await confirm.click()
            logger.info("[视频标记] 已点击确认")
            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(f"[视频标记] 设置失败（非致命）: {exc}")
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

    @staticmethod
    async def _ensure_original_checked(page):
        """确保「原创视频」开关处于开启状态（spec 第 54-56 行，默认 ON）。"""
        try:
            checkbox = page.locator(
                '.VideoUploadForm-typeContainer input[type="checkbox"]'
            ).first
            await checkbox.wait_for(state="attached", timeout=5000)
            is_checked = await checkbox.is_checked()
            if not is_checked:
                # 点击外层 label/button 触发开关
                toggle = page.locator(
                    '.VideoUploadForm-typeContainer button, '
                    '.VideoUploadForm-typeContainer label'
                ).first
                await toggle.click()
                logger.info("[原创视频] 已开启原创开关")
            else:
                logger.info("[原创视频] 原创开关已开启")
        except Exception as exc:
            logger.info(f"[原创视频] 检查失败（非致命）: {exc}")

    @staticmethod
    async def _set_category(page, category: str):
        """所属领域下拉（spec 第 58-63 行）。"""
        if not category:
            return

        logger.info(f"[所属领域] 设置: {category}")
        try:
            # 在「所属领域」区域内点击 Select 触发下拉
            area = page.locator(
                '.VideoUploadForm-item:has(.VideoUploadForm-itemTitle:has-text("所属领域"))'
            ).first
            trigger = area.locator('.Select-button, button[role="combobox"]').first
            await trigger.wait_for(state="visible", timeout=10000)
            await trigger.click()
            await asyncio.sleep(1)

            option = page.locator(
                f'.VideoUploadForm-selectList .Select-option:has-text("{category}"), '
                f'.Select-list .Select-option:has-text("{category}")'
            ).first
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            logger.info(f"[所属领域] 已选择: {category}")
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.info(f"[所属领域] 设置失败（非致命）: {exc}")

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """定时发布：日历 + 时下拉 + 分下拉（spec 第 66-97 行）。

        前端 UI 已约束 ≥1 小时后且 ≤1 个月内；这里只负责按日期选中。
        """
        from datetime import datetime

        if isinstance(publish_date, int):
            if publish_date == 0:
                return
            return
        if not publish_date:
            return

        dt = publish_date
        logger.info(f"[定时发布] 设置定时: {dt.strftime('%Y-%m-%d %H:%M')}")

        try:
            # 1. 打开定时发布开关
            switch = page.locator(
                '.VideoUploadForm-scheduledPublish--switch input[type="checkbox"], '
                '.VideoUploadForm-scheduledPublish label'
            ).first
            await switch.wait_for(state="attached", timeout=10000)
            is_on = False
            try:
                cb = page.locator(
                    '.VideoUploadForm-scheduledPublish--switch input[type="checkbox"]'
                ).first
                if await cb.count() > 0:
                    is_on = await cb.is_checked()
            except Exception:
                pass
            if not is_on:
                await switch.click()
                logger.info("[定时发布] 已打开开关")
                await asyncio.sleep(1)

            # 2. 选年月日（日历组件）
            date_btn = page.locator('.DatePicker-Button').first
            await date_btn.wait_for(state="visible", timeout=10000)
            await date_btn.click()
            await asyncio.sleep(1)

            target_year = dt.year
            target_month = dt.month
            target_day = dt.day

            for _ in range(24):
                tool_text = ""
                try:
                    tool = page.locator('.Calendar-topToolDate').first
                    if await tool.count() > 0:
                        tool_text = (await tool.text_content() or "").strip()
                except Exception:
                    pass

                if str(target_year) in tool_text and str(target_month) in tool_text:
                    break

                if tool_text:
                    try:
                        cur_year = int(_extract_year(tool_text))
                        cur_month = int(_extract_month(tool_text))
                        if (cur_year, cur_month) < (target_year, target_month):
                            await page.locator('.Calendar-topToolButton--nextMonth').first.click()
                        else:
                            await page.locator('.Calendar-topToolButton--prevMonth').first.click()
                        await asyncio.sleep(0.5)
                        continue
                    except Exception:
                        pass
                await page.locator('.Calendar-topToolButton--nextMonth').first.click()
                await asyncio.sleep(0.5)

            # 选择具体日期：排除禁用、非当月、占位
            day_cells = page.locator(
                'td.Calendar-day:not(.is-disabled):not(.is-not-this-month)'
            )
            day_set = False
            count = await day_cells.count()
            for i in range(count):
                cell = day_cells.nth(i)
                text = (await cell.text_content() or "").strip()
                if text == str(target_day):
                    await cell.click()
                    day_set = True
                    break
            if not day_set:
                logger.info(f"[定时发布] 找不到可点击日期 {target_day}")
            await asyncio.sleep(0.5)

            # 3. 选小时
            target_hour_padded = f"{dt.hour:02d}"
            hour_trigger = page.locator(
                '.DateTimePicker .Popover:has(.DatePicker) ~ .Popover .Select-button, '
                '.DateTimePicker button[role="combobox"]'
            ).nth(0)
            try:
                await hour_trigger.click(timeout=5000)
            except Exception:
                # 兜底：第二个 Popover 通常是小时
                hour_trigger = page.locator('.DateTimePicker button[role="combobox"]').nth(0)
                await hour_trigger.click(timeout=5000)
            await asyncio.sleep(0.5)
            hour_opt = page.locator(
                f'.DateTimePicker-selectList .Select-option:not([disabled]):has-text("{target_hour_padded}")'
            ).first
            if await hour_opt.count() > 0:
                await hour_opt.click()
                logger.info(f"[定时发布] 小时设为 {target_hour_padded}")
            else:
                logger.info(f"[定时发布] 找不到小时选项 {target_hour_padded}")
            await asyncio.sleep(0.5)

            # 4. 选分钟
            target_minute = f"{dt.minute:02d}"
            minute_trigger = page.locator(
                '.DateTimePicker button[role="combobox"]'
            ).nth(1)
            try:
                await minute_trigger.click(timeout=5000)
            except Exception:
                logger.info("[定时发布] 分钟下拉点击失败")
            await asyncio.sleep(0.5)
            minute_opt = page.locator(
                f'.DateTimePicker-selectList .Select-option:not([disabled]):has-text("{target_minute}")'
            ).first
            if await minute_opt.count() > 0:
                await minute_opt.click()
                logger.info(f"[定时发布] 分钟设为 {target_minute}")
            else:
                logger.info(f"[定时发布] 找不到分钟选项 {target_minute}")
            await asyncio.sleep(0.5)

            # 关闭可能仍打开的下拉
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            await asyncio.sleep(0.5)

        except Exception as exc:
            logger.info(f"[定时发布] 设置失败: {exc}")

    @staticmethod
    async def _click_submit(page, is_scheduled: bool) -> bool:
        """点击右下角发布按钮（spec 第 99-104 行）。

        按钮文案因模式而异：「发布视频」/「定时发布」。
        成功判定：页面 URL 跳转。
        """
        button_text = "定时发布" if is_scheduled else "发布视频"
        logger.info(f"[上传视频] 准备点击发布按钮: {button_text}")

        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)

        submit = page.locator(
            f'button.VideoUploadForm-submitButton:has-text("{button_text}"), '
            f'button:has-text("{button_text}")'
        ).first
        try:
            await submit.wait_for(state="visible", timeout=15000)
        except Exception:
            logger.info(f"[上传视频] 找不到「{button_text}」按钮，尝试通用提交")
            submit = page.locator('.VideoUploadForm-submitButton').first

        original_url = page.url
        try:
            await submit.click()
        except Exception as exc:
            logger.info(f"[上传视频] 点击发布按钮失败: {exc}")
            return False

        # 等待 URL 跳转 = 发布成功（spec 第 106 行）
        for _ in range(60):
            await asyncio.sleep(2)
            if page.url != original_url and "upload-video" not in page.url:
                logger.info(f"[上传视频] 页面已跳转: {page.url}")
                return True
        logger.info("[上传视频] 等待 URL 跳转超时（60 × 2s），发布可能失败")
        return False


# ---------------------------------------------------------------------------
# Calendar label parsing helpers (used by _set_schedule_time)
# ---------------------------------------------------------------------------

import re as _re_module


def _extract_year(text: str) -> str:
    m = _re_module.search(r'(\d{4})', text or '')
    return m.group(1) if m else '0'


def _extract_month(text: str) -> str:
    m = _re_module.search(r'(\d{1,2})\s*月', text or '')
    if not m:
        m = _re_module.search(r'\d{4}\s*年\s*(\d{1,2})', text or '')
    return m.group(1) if m else '0'
