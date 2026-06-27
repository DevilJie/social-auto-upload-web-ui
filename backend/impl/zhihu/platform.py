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
ZHIHU_CREATOR_URL = "https://www.zhihu.com/creator"

# 调试开关：True = 提交前只 dump 表单状态、不实际点击发布按钮。
# 验证完表单内容后改回 False 即恢复正常发布。
DEBUG_DRY_RUN_SUBMIT = False


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
                logger.info("[登录] 等待用户完成登录（检测右上角头像按钮）")

                # 头像按钮出现 = 登录成功。不设超时，用户自己关浏览器取消。
                await page.locator(".AppHeader-profileEntry").first.wait_for(
                    timeout=999999999
                )
                logger.info("[登录] 检测到头像按钮，登录成功")

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
                    logger.info("[校验Cookie] cookie 有效")
                    return True
                logger.info("[校验Cookie] cookie 已失效")
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
                logger.info(f"[同步资料] 失败: {e}")
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
        url = ZHIHU_CREATOR_URL

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

            # DEBUG：dump 所有收到的 kwargs（值被截断到 100 字符），便于排查前端到底传了什么
            for _k, _v in kwargs.items():
                _vs = repr(_v)
                if len(_vs) > 100:
                    _vs = _vs[:100] + "..."
                logger.info("[发布参数 RAW] %s = %s", _k, _vs)

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
                # 严格按素材表的视频方向选封面（spec: 视频格式由素材库 orientation 字段区分）
                video_orientation = _get_video_orientation(file_path)
                if video_orientation == "vertical":
                    picked_thumb = thumbnail_portrait or thumbnail_landscape
                    picked_label = "竖版"
                elif video_orientation == "horizontal":
                    picked_thumb = thumbnail_landscape or thumbnail_portrait
                    picked_label = "横版"
                else:
                    # 素材表无方向记录，兜底用前端 videoFormat
                    if video_format == "portrait":
                        picked_thumb = thumbnail_portrait or thumbnail_landscape
                        picked_label = "竖版(前端)"
                    else:
                        picked_thumb = thumbnail_landscape or thumbnail_portrait
                        picked_label = "横版(前端)"
                logger.info(
                    "[发布参数] 视频方向=%s, 选用%s封面: %s",
                    video_orientation or "未知", picked_label, picked_thumb or "无",
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
                        # _upload_single_video 在发布失败时直接 raise，
                        # 异常会传到 publish_video → app.py 的 except → 500+msg
                        await self._upload_single_video(
                            title=title,
                            file_path=file_path,
                            tags=tags,
                            publish_date=publish_date,
                            account_file=cookie_path,
                            category=category,
                            creation_declaration=creation_declaration,
                            desc=desc,
                            thumbnail_path=picked_thumb,
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
    ) -> str:
        """Returns:
            空串 = 发布成功
            非空串 = 错误消息（用于 publish_video 聚合后抛给 app.py）
        """
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

                # 3. 设置封面（spec 第 28-34 行；任何异常 Escape 关弹窗，不阻塞）
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

                # 10. 点击发布按钮（监听 /api/v4/content/publish 响应判断结果）
                submitted, submit_msg = await self._click_submit(page, is_scheduled)
                if submitted:
                    logger.info(f"[上传视频] ✓ 发布成功: {submit_msg}")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "zhihu_after_submit.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass
                else:
                    logger.info(f"[上传视频] ✗ 发布失败: {submit_msg}")
                    # 发布失败也保留现场日志，方便排查
                    try:
                        await page.screenshot(
                            path=str(log_dir / "zhihu_submit_failed.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass

                # upload_success 跟踪「浏览器流程跑完」（用于决定是否更新 cookie），
                # 与「发布是否成功」解耦：cookie 仍有效应当保存。
                upload_success = True
            finally:
                if upload_success:
                    try:
                        await context.storage_state(path=account_file)
                        logger.info("[上传视频] cookie 已更新")
                    except Exception:
                        pass
                if not DEBUG_DRY_RUN_SUBMIT:
                    try:
                        await context.close()
                    except Exception:
                        pass
        finally:
            if not DEBUG_DRY_RUN_SUBMIT:
                try:
                    await browser.close()
                except Exception:
                    pass
                logger.info("[上传视频] 浏览器已关闭")
            else:
                logger.info("[上传视频] ⏸ DEBUG 模式：保留浏览器打开，便于现场检查")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """上传视频文件 — 多策略探测 input=file。

        知乎上传页 ``input[type=file]`` 可能存在 iframe 内或主页，
        accept 属性也可能不一致；先 JS 探测一遍把页面上所有 file input
        的属性打到日志，再按 iframe→[accept*=video]→任意 input→点击
        可见上传按钮的顺序逐级兜底。每一步都打日志便于排查。
        """
        log_dir = Path(BASE_DIR / "logs")
        logger.info("[上传视频] 正在上传视频文件: %s", file_path)

        try:
            await page.screenshot(
                path=str(log_dir / "zhihu_upload_before.png"), full_page=True
            )
        except Exception:
            pass

        try:
            inputs_info = await page.evaluate("""() => {
                const inputs = [...document.querySelectorAll('input[type="file"]')];
                return inputs.map(inp => ({
                    accept: inp.accept || '',
                    name: inp.name || '',
                    multiple: inp.multiple,
                }));
            }""")
            logger.info("[上传视频] 页面 file input 探测: %s", inputs_info)
        except Exception as e:
            logger.info("[上传视频] file input 探测失败: %s", e)

        file_input = None

        # 策略 1: iframe 里找（参考 bilibili 的 iframe[name="videoUpload"]）
        try:
            upload_frame = page.frame_locator(
                'iframe[name="videoUpload"], '
                'iframe[name*="upload"], '
                'iframe[title*="upload" i], '
                'iframe[src*="upload" i]'
            )
            input_in_frame = upload_frame.locator('input[type="file"]').first
            await input_in_frame.wait_for(state="attached", timeout=3000)
            file_input = input_in_frame
            logger.info("[上传视频] ✓ iframe 内找到 file input")
        except Exception:
            logger.info("[上传视频] iframe 内未找到 file input，转主页面")

        # 策略 2: 主页面 input[accept*=video]
        if file_input is None:
            try:
                candidate = page.locator(
                    'input[type="file"][accept*="video"], '
                    'input[type="file"][accept*="mp4"]'
                ).first
                await candidate.wait_for(state="attached", timeout=5000)
                file_input = candidate
                logger.info("[上传视频] ✓ 主页面 video input 命中")
            except Exception:
                logger.info("[上传视频] 主页面未找到 [accept*=video] input")

        # 策略 3: 主页面任意 file input（兜底）
        if file_input is None:
            try:
                candidate = page.locator('input[type="file"]').first
                await candidate.wait_for(state="attached", timeout=5000)
                file_input = candidate
                logger.info("[上传视频] ✓ 兜底命中主页面第一个 file input")
            except Exception:
                logger.info("[上传视频] 主页面无任何 file input")

        # 策略 4: 点击可见的上传按钮/dropzone 后再找 input
        if file_input is None:
            try:
                logger.info("[上传视频] 尝试点击页面上可见的上传按钮")
                upload_btn = page.locator(
                    'button:has-text("上传视频"), '
                    'div[role="button"]:has-text("上传"), '
                    '[class*="UploadDropzone"], [class*="upload-dropzone"], '
                    'div:has-text("选择文件"):not(:has(*)), '
                    'div:has-text("拖拽"):not(:has(*))'
                ).first
                await upload_btn.wait_for(state="visible", timeout=5000)
                await upload_btn.click()
                await asyncio.sleep(1)
                file_input = page.locator('input[type="file"]').first
                await file_input.wait_for(state="attached", timeout=5000)
                logger.info("[上传视频] ✓ 点击上传按钮后找到 file input")
            except Exception as e:
                logger.info("[上传视频] 上传按钮兜底失败: %s", e)

        if file_input is None:
            try:
                await page.screenshot(
                    path=str(log_dir / "zhihu_upload_no_input.png"),
                    full_page=True,
                )
            except Exception:
                pass
            raise RuntimeError(
                "未找到视频上传 input，请查看 logs/zhihu_upload_before.png"
            )

        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择，等待上传完成")

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

        关键点：知乎上传页有多个 image input（描述区也有一个），
        不能用 ``input[accept*=image].first`` —— 会拿到描述区的 input，
        设了文件也不会触发封面上传。改用 file_chooser 拦截原生文件
        选择器，最稳。任何异常都 Escape 关弹窗，不阻塞后续步骤。
        """
        import os

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logger.info(f"[设置封面] 封面文件不存在: {thumbnail_path}")
            return

        log_dir = Path(BASE_DIR / "logs")
        logger.info("[设置封面] 开始设置封面")

        try:
            # 1. 点击「选择视频封面」打开弹窗
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

            # 3. 上传封面文件 —— 优先用 file_chooser（点 dropzone 触发原生选器）
            uploaded = False
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    # dropzone 区域：弹窗内的虚线框/上传区
                    dropzone = page.locator(
                        '.Modal-content [class*="Dropzone"], '
                        '.Modal-content [class*="dropzone"], '
                        '.Modal-content [class*="upload"], '
                        '[role="dialog"] [class*="Dropzone"], '
                        '[role="dialog"] [class*="upload"]'
                    ).first
                    await dropzone.wait_for(state="visible", timeout=5000)
                    await dropzone.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(thumbnail_path)
                uploaded = True
                logger.info("[设置封面] ✓ file_chooser 方式上传成功")
            except Exception as e:
                logger.info(f"[设置封面] file_chooser 方式失败，兜底直设 input: {e}")

            # 兜底：scope 到 Modal 内找 input（避开描述区 EditorArea 的 image input）
            if not uploaded:
                try:
                    # 弹窗根：Modal-content 或 [role=dialog]
                    modal_input = page.locator(
                        '.Modal-content input[type="file"], '
                        '[role="dialog"] input[type="file"]'
                    ).first
                    await modal_input.wait_for(state="attached", timeout=5000)
                    await modal_input.set_input_files(thumbnail_path)
                    uploaded = True
                    logger.info("[设置封面] ✓ Modal 内 input 命中")
                except Exception as e:
                    logger.info(f"[设置封面] Modal 内 input 兜底失败: {e}")

            # 再兜底：排除 EditorArea/WritePinV2-Form 的 image input
            if not uploaded:
                try:
                    inputs_info = await page.evaluate("""() => {
                        const inputs = [...document.querySelectorAll('input[type="file"][accept*="image"]')];
                        const filtered = inputs.filter(inp => {
                            let el = inp;
                            while (el) {
                                if (el.classList && (
                                    el.classList.contains('EditorArea') ||
                                    el.classList.contains('WritePinV2-Form') ||
                                    el.classList.contains('InputLike')
                                )) return false;
                                el = el.parentElement;
                            }
                            return true;
                        });
                        return filtered.length;
                    }""")
                    logger.info(f"[设置封面] 排除编辑区后剩 {inputs_info} 个 image input")
                    if inputs_info > 0:
                        # 用 evaluate 找到这个 input 并直接设值（playwright 定位用）
                        # 实际策略：先点 dropzone，再用 file_chooser
                        raise RuntimeError("无法可靠定位封面 input")
                except Exception as e:
                    logger.info(f"[设置封面] 排除法失败: {e}")

            if not uploaded:
                raise RuntimeError("封面文件未能上传到弹窗")

            # 4. 等待封面预览出现 = 上传完成（30s 给图片处理留足时间）
            logger.info("[设置封面] 等待封面预览/确认按钮...")
            preview_found = False
            for _ in range(30):
                try:
                    # 「重新上传」按钮出现 = 已上传，可重选
                    repl = page.locator(
                        '.Modal-content button:has-text("重新上传"), '
                        '[role="dialog"] button:has-text("重新上传")'
                    )
                    if await repl.count() > 0 and await repl.first.is_visible():
                        preview_found = True
                        logger.info("[设置封面] ✓ 检测到「重新上传」按钮，封面已上传")
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)

            if not preview_found:
                logger.info("[设置封面] 等待 30s 仍未检测到封面上传成功标志")

            # 5. 点击「确认选择」— 多策略确保点中
            confirm_btn = page.locator(
                '.Modal-content button:has-text("确认选择"), '
                '[role="dialog"] button:has-text("确认选择"), '
                '.Modal-content button.Button--primary:has-text("确认"), '
                '[role="dialog"] button.Button--primary:has-text("确认"), '
                'button.Button--primary:has-text("确认选择")'
            ).first
            await confirm_btn.wait_for(state="visible", timeout=15000)
            clicked = False
            for attempt, kwargs_click in enumerate([
                {"timeout": 5000},
                {"timeout": 5000, "force": True},
            ]):
                try:
                    await confirm_btn.click(**kwargs_click)
                    clicked = True
                    logger.info(f"[设置封面] ✓ 已点击「确认选择」(attempt={attempt + 1})")
                    break
                except Exception as e:
                    logger.info(f"[设置封面] 点击 attempt={attempt + 1} 失败: {e}")
            if not clicked:
                # 最后兜底：JS 直接 dispatch click
                try:
                    await confirm_btn.evaluate("el => el.click()")
                    clicked = True
                    logger.info("[设置封面] ✓ JS evaluate click 命中")
                except Exception as e:
                    logger.info(f"[设置封面] JS evaluate click 失败: {e}")

            # 6. 等模态框消失（确认弹窗关闭 = 真正生效）；超时则 Escape 兜底
            modal_closed = False
            for _ in range(15):
                try:
                    still_open = await page.locator(
                        '.Modal-content:visible, [role="dialog"]:visible'
                    ).count()
                    if still_open == 0:
                        modal_closed = True
                        logger.info("[设置封面] ✓ 弹窗已关闭")
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
            if not modal_closed:
                logger.info("[设置封面] 弹窗 15s 未关，Escape 兜底")
                try:
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(1)
                except Exception:
                    pass

        except Exception as exc:
            logger.info(f"[设置封面] 设置封面失败（非致命）: {exc}")
            try:
                await page.screenshot(
                    path=str(log_dir / "zhihu_cover_error.png"),
                    full_page=True,
                )
            except Exception:
                pass
            # 关掉可能仍打开的弹窗，避免遮挡后续步骤
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
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

        知乎简介是 contenteditable 富文本编辑器。简介 + 标签都用剪贴板粘贴
        （Ctrl+V），不再逐字 keyboard.type —— 后者在标签场景下 React 监听
        可能丢字符。每个标签末尾带空格触发话题联想。
        """
        import json as _json
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

        async def _paste(text: str):
            """通过剪贴板粘贴到当前焦点元素。"""
            try:
                await page.evaluate(
                    "async (s) => { await navigator.clipboard.writeText(s); }",
                    text,
                )
                await page.keyboard.press("Control+V")
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.info(f"[填写简介] 粘贴失败，回退 type: {e}")
                await page.keyboard.type(text)

        # 1. 粘贴简介
        if full_text:
            await _paste(full_text)
            await asyncio.sleep(0.3)

        # 2. 逐个逐字输入标签：press_sequentially 自动 focus，delay=150ms 每字符
        for tag in parsed_tags:
            text = f" #{tag}"
            logger.info(f"[填写标签] 逐字输入: '{text}'")
            await editor.press_sequentially(text, delay=150)
            await asyncio.sleep(2)
            await page.keyboard.press(" ")
            await asyncio.sleep(0.5)
            logger.info(f"[填写标签] 已输入空格激活: '{text}'")

    @staticmethod
    async def _set_video_mark(page, creation_declaration: str):
        """视频标记弹窗（spec 第 45-52 行）。

        即使默认「内容无需标注」也要打开弹窗 + 点确认（显式确认状态）。
        只有当用户选了非默认项时才点选项。
        """
        if not creation_declaration:
            creation_declaration = "内容无需标注"
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

            # 非默认才点选项（默认是预先勾选状态，无需点）
            if creation_declaration != "内容无需标注":
                option = modal.locator(
                    f'.VideoUploadForm-videoTypeModalOption:has-text("{creation_declaration}")'
                ).first
                await option.wait_for(state="visible", timeout=5000)
                await option.click()
                logger.info(f"[视频标记] 已选择: {creation_declaration}")
                await asyncio.sleep(0.5)

            # 不论默认还是非默认，都要点「确认」显式提交
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
        """所属领域下拉（spec 第 58-63 行）。

        spec DOM:trigger 是 ``button[role=combobox]`` 在 ``.VideoUploadForm-select``
        内（id 形如 PopoverN-toggle）；点击后渲染 ``Popover-content`` 包着
        ``[role=listbox]`` 内的 ``button[role=option]``。options 是 portal
        渲染（不在原 .VideoUploadForm-item 子树里），从全页找。
        """
        if not category:
            return

        logger.info(f"[所属领域] 设置: {category}")
        try:
            # 1. 定位「所属领域」区域（按 itemTitle 文本锚点）
            area = page.locator(
                '.VideoUploadForm-item',
                has=page.locator('.VideoUploadForm-itemTitle:has-text("所属领域")'),
            ).first
            await area.wait_for(state="visible", timeout=10000)

            # 2. 区域内的 combobox 按钮（id=PopoverN-toggle，N 会变，不用 id）
            trigger = area.locator('button[role="combobox"]').first
            await trigger.wait_for(state="visible", timeout=10000)

            # 3. 点击打开下拉；先普通点击，失败 force click 兜底
            for attempt in range(2):
                try:
                    await trigger.click(timeout=5000, force=(attempt == 1))
                    break
                except Exception as e:
                    if attempt == 0:
                        logger.info(f"[所属领域] 普通点击失败，尝试 force click: {e}")
                    else:
                        raise
            await asyncio.sleep(1)

            # 4. 等下拉 [role=listbox] 出现（portal 渲染，全页搜）
            listbox = page.locator(
                '.Popover-content [role="listbox"], div[role="listbox"]'
            ).first
            await listbox.wait_for(state="visible", timeout=10000)

            # 5. 在 listbox 里找匹配文案的 option
            option = listbox.locator(
                f'button[role="option"]:has-text("{category}")'
            ).first
            await option.wait_for(state="visible", timeout=10000)
            for attempt in range(2):
                try:
                    await option.click(timeout=5000, force=(attempt == 1))
                    break
                except Exception as e:
                    if attempt == 0:
                        logger.info(f"[所属领域] option 普通点击失败，force 重试: {e}")
                    else:
                        raise
            logger.info(f"[所属领域] ✓ 已选择: {category}")
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.info(f"[所属领域] 设置失败（非致命）: {exc}")
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
            except Exception:
                pass

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
    async def _click_submit(page, is_scheduled: bool) -> tuple[bool, str]:
        """点击右下角发布按钮（spec 第 99-104 行）。

        发布成功判定（唯一依据）：监听 ``POST /api/v4/content/publish`` 响应，
        ``code == 0`` 才算成功；其它情况（含超时、非 0 code、响应缺失）全部
        视为失败。返回后端的 ``message`` 作为失败原因。
        Returns:
            (success, message)
        """
        # DEBUG：dry-run 模式下只 dump 表单，不实际发布
        if DEBUG_DRY_RUN_SUBMIT:
            await ZhihuPlatform._dump_form_state(page)
            logger.info("[上传视频] ⏸ DEBUG_DRY_RUN_SUBMIT=True，跳过实际点击发布")
            return True, "dry-run"

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

        # 监听 POST /api/v4/content/publish 响应
        try:
            async with page.expect_response(
                lambda r: "/api/v4/content/publish" in r.url
                          and r.request.method == "POST",
                timeout=60000,
            ) as resp_info:
                try:
                    await submit.click()
                except Exception as exc:
                    logger.info(f"[上传视频] 点击发布按钮失败: {exc}")
                    return False, f"点击发布按钮失败: {exc}"
            response = await resp_info.value
        except Exception as exc:
            logger.info(f"[上传视频] 等待发布 API 响应超时: {exc}")
            return False, "等待发布 API 响应超时"

        try:
            data = await response.json()
        except Exception as exc:
            logger.info(f"[上传视频] 发布响应解析失败: {exc}")
            return False, "发布响应解析失败"

        code = data.get("code")
        msg = data.get("message") or data.get("toast_message") or "发布失败"
        if code == 0:
            logger.info("[上传视频] ✓ 发布成功 (code=0)")
            return True, "发布成功"
        # 失败直接 raise，app.py 的 except Exception 会接住返回 500+msg 给前端
        logger.info(f"[上传视频] ✗ 发布失败 code={code} message={msg}")
        raise RuntimeError(f"知乎发布失败 code={code} message={msg}")

    @staticmethod
    async def _dump_form_state(page):
        """调试用：把上传表单当前所有字段值打到日志，便于人工核对。

        知乎表单不是标准 form，元素散落在多个 VideoUploadForm-item 里，
        且部分是 contenteditable 富文本，统一用 page.evaluate 抓。
        """
        try:
            state = await page.evaluate(r"""() => {
                const get = (sel) => {
                    const el = document.querySelector(sel);
                    return el ? (el.value || el.innerText || el.textContent || '').trim() : null;
                };
                // 标题
                let title = '';
                const titleTa = document.querySelector('textarea[name="title"], .TitleArea textarea');
                if (titleTa) title = titleTa.value;
                // 简介（contenteditable）
                let desc = '';
                const descEd = document.querySelector('.EditorArea [contenteditable="true"], .Editable [contenteditable="true"]');
                if (descEd) desc = descEd.innerText;
                // 视频标记 - 找 VideoUploadForm-selectContainer 第一个里 Select-button 的 span
                let videoMark = '';
                const markBtn = document.querySelector('.VideoUploadForm-videoTypeSelectOverlay');
                // 视频标记 Select button span 文本
                const markSelects = document.querySelectorAll('.VideoUploadForm-selectContainer--modalTrigger .Select-button span, .VideoUploadForm-selectContainer--modalTrigger button[role="combobox"] span');
                if (markSelects.length) videoMark = markSelects[0].innerText.trim();
                // 原创视频 checkbox
                let original = null;
                const origCb = document.querySelector('.VideoUploadForm-typeContainer input[type="checkbox"]');
                if (origCb) original = origCb.checked;
                // 所属领域
                let category = '';
                const catItems = document.querySelectorAll('.VideoUploadForm-item');
                for (const it of catItems) {
                    const t = it.querySelector('.VideoUploadForm-itemTitle');
                    if (t && t.textContent.trim() === '所属领域') {
                        const span = it.querySelector('.Select-button span, button[role="combobox"] span');
                        if (span) category = span.textContent.trim();
                        break;
                    }
                }
                // 定时发布开关
                let scheduled = null;
                const schedCb = document.querySelector('.VideoUploadForm-scheduledPublish--switch input[type="checkbox"]');
                if (schedCb) scheduled = schedCb.checked;
                let scheduleTime = '';
                if (scheduled) {
                    const dp = document.querySelector('.DatePicker-Button');
                    if (dp) scheduleTime += dp.textContent.trim() + ' ';
                    const combos = document.querySelectorAll('.DateTimePicker button[role="combobox"] span');
                    const times = [...combos].map(s => s.textContent.trim());
                    scheduleTime += times.join(':');
                }
                // 封面：VideoUploadForm-image 是否有 img
                let cover = '';
                const coverImg = document.querySelector('.VideoUploadForm-image');
                if (coverImg) cover = coverImg.getAttribute('src') || '(无 src)';
                return {
                    title,
                    desc_preview: desc.slice(0, 80),
                    desc_len: desc.length,
                    videoMark,
                    original,
                    category,
                    scheduled,
                    scheduleTime,
                    cover,
                    url: location.href,
                };
            }""")
            logger.info("[DEBUG 表单状态] " + "=" * 40)
            for k, v in state.items():
                logger.info(f"[DEBUG 表单状态] {k}: {v}")
            logger.info("[DEBUG 表单状态] " + "=" * 40)
        except Exception as e:
            logger.info(f"[DEBUG 表单状态] 抓取失败: {e}")


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


def _get_video_orientation(file_path: str) -> str:
    """查询素材表 materials.orientation 字段。

    spec 要求：封面要严格按视频实际方向（横/竖）上传，方向以素材库
    orientation 字段为准（horizontal/vertical/square）。返回空串表示
    未查到，调用方兜底用前端 videoFormat。
    """
    import sqlite3
    try:
        db_path = Path(BASE_DIR) / "db" / "database.db"
        # 文件名通常是 <material_id>.mp4，直接用 id 查更快；同时兜底 stored_path
        m = _re_module.search(r'([a-f0-9-]{36})', file_path or '')
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if m:
                row = conn.execute(
                    "SELECT orientation FROM materials WHERE id = ?",
                    (m.group(1),),
                ).fetchone()
                if row:
                    return row["orientation"] or ""
            # 兜底：按 stored_path 全路径或后缀匹配
            row = conn.execute(
                "SELECT orientation FROM materials WHERE stored_path = ?",
                (file_path,),
            ).fetchone()
            if row:
                return row["orientation"] or ""
        return ""
    except Exception as e:
        logger.info(f"[发布参数] 查询视频方向失败: {e}")
        return ""
