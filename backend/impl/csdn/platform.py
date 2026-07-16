"""CSDN 平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

登录地址：https://mp.csdn.net/
视频发布地址：https://mp.csdn.net/mp_others/creation/videoUpload
"""

import asyncio
import threading
import time
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    parse_schedule_time,
    save_login_result,
    scrape_csdn_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("csdn")

CSDN_HOME_URL = "https://mp.csdn.net/"
CSDN_VIDEO_UPLOAD_URL = "https://mp.csdn.net/mp_others/creation/videoUpload"
# 登录成功信号：创作者首页右上角的用户信息卡出现
CSDN_LOGIN_SUCCESS_SELECTOR = "div.user-info-box"

# CSDN 视频发布限制（详见对接文档 csdn.md）
CSDN_MAX_TAGS = 3          # 标签不超过 3 个
CSDN_MAX_TITLE_LEN = 30    # 标题不超过 30 字
CSDN_MAX_DESC_LEN = 150    # 简介不超过 150 字


class CsdnPlatform(BasePlatform):
    platform_id = 15
    platform_key = "csdn"
    platform_name = "CSDN"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".csdn.net"

    # CSDN 专属 cookie 属性映射表（从真实登录保存的 storage_state dump 得到）。
    # 纯 k=v 字符串不带 domain/secure/httpOnly，一刀切设 .csdn.net 会导致
    # 登录态丢失：mp.csdn.net 判定未登录。这里按真实多子域结构智能分配。
    #
    # 这些 cookie 不在 .csdn.net 主域：
    _CSDN_COOKIE_DOMAIN_MAP = {
        "https_waf_cookie": "passport.csdn.net",
        "waf_captcha_marker": "passport.csdn.net",
        "bc_bot_session": ".blog.csdn.net",
        "_bl_uid": "i.csdn.net",
    }
    # secure=True 的 cookie（真实文件里只有这两个走 HTTPS-only）：
    _CSDN_SECURE_COOKIES = {"https_waf_cookie", "bc_bot_session"}
    # httpOnly=True 的 cookie（真实文件里只有这几个服务端设置的）：
    _CSDN_HTTPONLY_COOKIES = {
        "SESSION", "UserInfo", "UserToken",
        "https_waf_cookie", "waf_captcha_marker",
    }

    def _parse_cookie_to_storage_state(self, cookie_str):
        cookies = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            name = name.strip()
            domain = self._CSDN_COOKIE_DOMAIN_MAP.get(name, self.platform_cookie_domain)
            cookies.append({
                "name": name, "value": value.strip(),
                "domain": domain, "path": "/",
                "expires": expires,
                "httpOnly": name in self._CSDN_HTTPONLY_COOKIES,
                "secure": name in self._CSDN_SECURE_COOKIES,
                "sameSite": "Lax",
            })

        # SESSION 在 .csdn.net 和 msg.csdn.net 各存一份（与真实文件一致）
        session_cookies = [c for c in cookies if c["name"] == "SESSION"]
        for sc in session_cookies:
            if sc["domain"] == self.platform_cookie_domain:
                cookies.append({**sc, "domain": "msg.csdn.net"})

        return cookies, []

    # ------------------------------------------------------------------
    # login — 用户在可见浏览器中手动登录
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开 CSDN 创作者首页，等待用户完成登录后保存 cookie。

        CSDN 登录方式（密码/扫码/第三方）较多样，统一让用户在可见浏览器里
        手动完成。检测到首页用户信息卡 (``div.user-info-box``) 出现即视为
        登录成功。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(CSDN_HOME_URL)
                logger.info("[登录] 等待用户完成登录（检测首页用户信息卡）")

                # 用户信息卡出现 = 登录成功。不设超时，用户自己关浏览器取消。
                await page.locator(CSDN_LOGIN_SUCCESS_SELECTOR).first.wait_for(
                    timeout=999999999
                )
                logger.info("[登录] 检测到用户信息卡，登录成功")

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_csdn_profile,
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
                await page.goto(CSDN_HOME_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=10000
                    )
                    await asyncio.sleep(2)
                except Exception:
                    pass
                profile_entry = page.locator(CSDN_LOGIN_SUCCESS_SELECTOR).first
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

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(
                    CSDN_HOME_URL, wait_until="domcontentloaded", timeout=30000
                )
                return await scrape_csdn_profile(page)
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
        url = CSDN_HOME_URL

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
        """发布视频到 CSDN。

        接受的 kwargs（由 app.py 统一传入）:
        - ``title`` (*str*) — 视频标题（≤30 字符）
        - ``files`` (*list[str]*) — 视频绝对路径
        - ``tags`` (*list[str]*) — 标签（≤3 个，输入框 + 回车激活）
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``desc`` (*str*, 可选) — 简介（≤150 字符）
        - ``recommend`` (*bool*, 可选) — 是否推荐
        - ``enableTimer`` (*bool*, 可选) — 是否定时发布
        - ``schedule_time_str`` (*str*, 可选) — 定时时间
        - ``videos_per_day`` / ``daily_times`` / ``start_days`` — 自动排期参数
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` — 封面
        - ``video_format`` (*str*, 可选) — 'landscape' / 'portrait'
        """

        async def _run():
            logger.info("=" * 60)
            logger.info("[发布视频] 开始 CSDN 视频发布流程")
            logger.info("=" * 60)

            for _k, _v in kwargs.items():
                _vs = repr(_v)
                if len(_vs) > 100:
                    _vs = _vs[:100] + "..."
                logger.info("[发布参数 RAW] %s = %s", _k, _vs)

            title = kwargs.get("title", "")
            files = kwargs.get("files", [])
            tags = kwargs.get("tags") or []
            account_files = kwargs.get("account_file", [])
            desc = kwargs.get("desc", "") or ""
            recommend = bool(kwargs.get("recommend", False))
            enable_timer = kwargs.get("enableTimer", False)
            videos_per_day = kwargs.get("videos_per_day", 1)
            daily_times = kwargs.get("daily_times")
            start_days = kwargs.get("start_days", 0)
            thumbnail_landscape = kwargs.get("thumbnail_landscape_path", "") or ""
            thumbnail_portrait = kwargs.get("thumbnail_portrait_path", "") or ""
            schedule_time_str = kwargs.get("schedule_time_str", "") or ""

            logger.info("[发布参数] 标题: %s", title)
            logger.info("[发布参数] 文件数量: %d", len(files))
            logger.info("[发布参数] 标签: %s", tags)
            logger.info("[发布参数] 账号数量: %d", len(account_files))
            logger.info("[发布参数] 是否推荐: %s", recommend)

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
                # CSDN 固定使用横版封面（横版优先，未设置时用竖版兜底），不再按视频方向选择
                picked_thumb = thumbnail_landscape or thumbnail_portrait
                logger.info(
                    "[发布参数] CSDN 固定横版封面: %s", picked_thumb or "无",
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
                            desc=desc,
                            recommend=recommend,
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
        desc: str = "",
        recommend: bool = False,
        thumbnail_path: str | None = None,
    ) -> None:
        """上传单个视频到一个 CSDN 账号。

        失败时直接 raise，异常会传到 publish_video → app.py 的 except → 500+msg。
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
                await page.goto(CSDN_VIDEO_UPLOAD_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=30000
                    )
                except Exception:
                    pass

                # cookie 失效会被重定向到登录页
                if "/login" in page.url or "passport" in page.url:
                    raise RuntimeError("CSDN cookie 失效，请重新登录")

                # 1. 上传视频文件
                await self._upload_video_file(page, file_path)

                # 2. 等待视频上传成功（spec: .gement li.text 出现「上传成功」）
                await self._wait_upload_complete(page)
                await asyncio.sleep(2)

                # 3. 设置封面（隐藏 input=file + 裁剪弹窗确认）
                if thumbnail_path:
                    await self._set_thumbnail(page, thumbnail_path)

                # 4. 填写标题（≤30 字符）
                await self._fill_title(page, title)

                # 5. 填写简介（≤150 字符）
                await self._fill_desc(page, desc)

                # 6. 填写标签（≤3 个，输入框 + 回车激活）
                await self._fill_tags(page, tags)

                # 7. 是否推荐（默认关闭，开启才勾选）
                if recommend:
                    await self._set_recommend(page)

                # 提交前截图
                try:
                    await page.screenshot(
                        path=str(log_dir / "csdn_before_submit.png"),
                        full_page=True,
                    )
                except Exception:
                    pass

                # 8. 点击发布按钮（页面跳转即成功）
                submitted = await self._click_submit(page)
                if submitted:
                    logger.info("[上传视频] ✓ 发布成功")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "csdn_after_submit.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass
                else:
                    logger.info("[上传视频] ✗ 发布失败")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "csdn_submit_failed.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass

                upload_success = True
            finally:
                if upload_success:
                    try:
                        await context.storage_state(path=account_file)
                        logger.info("[上传视频] cookie 已更新")
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
            logger.info("[上传视频] 浏览器已关闭")

    # ------------------------------------------------------------------
    # Upload sub-steps
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """上传视频文件。

        CSDN 发布页有隐藏的 ``input[type=file][accept=".mp4,.flv,.m3u8,.mov"]``，
        直接定位它并 set_input_files，最稳。兜底用任意 video input。
        """
        log_dir = Path(BASE_DIR / "logs")
        logger.info("[上传视频] 正在上传视频文件: %s", file_path)

        try:
            await page.screenshot(
                path=str(log_dir / "csdn_upload_before.png"), full_page=True
            )
        except Exception:
            pass

        file_input = None
        # 策略 1: accept 含 mp4/video 的 input（CSDN 主上传框）
        try:
            candidate = page.locator(
                'input[type="file"][accept*="mp4"], '
                'input[type="file"][accept*="video"], '
                'input[type="file"][accept*="mov"]'
            ).first
            await candidate.wait_for(state="attached", timeout=10000)
            file_input = candidate
            logger.info("[上传视频] ✓ video input 命中")
        except Exception:
            logger.info("[上传视频] 未找到 [accept*=video] input，转兜底")

        # 策略 2: 任意 file input（兜底）
        if file_input is None:
            try:
                candidate = page.locator('input[type="file"]').first
                await candidate.wait_for(state="attached", timeout=5000)
                file_input = candidate
                logger.info("[上传视频] ✓ 兜底命中第一个 file input")
            except Exception:
                logger.info("[上传视频] 页面无任何 file input")

        if file_input is None:
            try:
                await page.screenshot(
                    path=str(log_dir / "csdn_upload_no_input.png"),
                    full_page=True,
                )
            except Exception:
                pass
            raise RuntimeError(
                "未找到视频上传 input，请查看 logs/csdn_upload_before.png"
            )

        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择，等待上传完成")

    @staticmethod
    async def _wait_upload_complete(page):
        """等待上传完成（spec 第 26-28 行）。

        只有 ``.gement ul li.text`` 出现「上传成功」文案，才代表上传完成。
        无超时：宁可等也不跳过。
        """
        retry = 0
        while True:
            try:
                # .gement 区域内的「上传成功」文案
                done = page.locator('.gement li.text:has-text("上传成功")')
                if await done.count() > 0:
                    logger.info("[上传视频] 检测到「上传成功」，视频处理完成")
                    return
                fail = page.locator(
                    '.gement li:has-text("上传失败"), '
                    'text=上传失败'
                )
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
        """设置视频封面（spec 第 35-38 行）。

        封面区有隐藏的 ``input[type=file][accept=".png,.jpg,..."]`` 在
        ``.essential-uploader`` 内；set_input_files 后会弹出「图片剪裁」弹窗，
        点击弹窗内 ``.dialog-footer .el-button--primary``（「确认」）即可。
        任何异常 Escape 关弹窗，不阻塞后续步骤。
        """
        import os

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logger.info(f"[设置封面] 封面文件不存在: {thumbnail_path}")
            return

        log_dir = Path(BASE_DIR / "logs")
        logger.info("[设置封面] 开始设置封面")

        try:
            # 1. 定位封面 input（.essential-uploader 内的图片 input）
            cover_input = None
            try:
                candidate = page.locator(
                    '.essential-uploader input[type="file"][accept*="png"], '
                    '.essential-uploader input[type="file"][accept*="image"], '
                    '.essential-uploader input[type="file"]'
                ).first
                await candidate.wait_for(state="attached", timeout=10000)
                cover_input = candidate
                logger.info("[设置封面] ✓ 封面 input 命中")
            except Exception:
                logger.info("[设置封面] .essential-uploader 内未找到 input，兜底全页")

            if cover_input is None:
                # 兜底：全页找 accept 含图片的 input（排除视频 input）
                try:
                    candidate = page.locator(
                        'input[type="file"][accept*="png"], '
                        'input[type="file"][accept*="jpg"], '
                        'input[type="file"][accept*="image"]'
                    ).first
                    await candidate.wait_for(state="attached", timeout=5000)
                    cover_input = candidate
                    logger.info("[设置封面] ✓ 全页兜底命中图片 input")
                except Exception as e:
                    raise RuntimeError(f"未找到封面 input: {e}")

            # 2. 设置封面文件 → 触发裁剪弹窗
            await cover_input.set_input_files(thumbnail_path)
            logger.info("[设置封面] 封面文件已选择，等待裁剪弹窗")
            await asyncio.sleep(2)

            # 3. 裁剪弹窗出现，点击「确认」(.dialog-footer .el-button--primary)
            confirm_btn = page.locator(
                '.dialog-footer .el-button--primary:has-text("确认"), '
                '.el-dialog__footer .el-button--primary:has-text("确认")'
            ).first
            try:
                await confirm_btn.wait_for(state="visible", timeout=15000)
                # 多策略点击确保点中
                clicked = False
                for attempt, click_kwargs in enumerate(
                    [{"timeout": 5000}, {"timeout": 5000, "force": True}]
                ):
                    try:
                        await confirm_btn.click(**click_kwargs)
                        clicked = True
                        logger.info(
                            f"[设置封面] ✓ 已点击裁剪确认 (attempt={attempt + 1})"
                        )
                        break
                    except Exception as e:
                        logger.info(
                            f"[设置封面] 点击 attempt={attempt + 1} 失败: {e}"
                        )
                if not clicked:
                    try:
                        await confirm_btn.evaluate("el => el.click()")
                        clicked = True
                        logger.info("[设置封面] ✓ JS evaluate click 命中")
                    except Exception as e:
                        logger.info(f"[设置封面] JS evaluate click 失败: {e}")
            except Exception as e:
                logger.info(f"[设置封面] 未出现裁剪弹窗（可能无需裁剪）: {e}")

            # 4. 等弹窗消失
            for _ in range(15):
                try:
                    still_open = await page.locator(
                        '.el-dialog__wrapper:not([style*="display: none"])'
                    ).count()
                    if still_open == 0:
                        logger.info("[设置封面] ✓ 裁剪弹窗已关闭")
                        break
                except Exception:
                    pass
                await asyncio.sleep(1)
            await asyncio.sleep(1)
        except Exception as exc:
            logger.info(f"[设置封面] 设置封面失败（非致命）: {exc}")
            try:
                await page.screenshot(
                    path=str(log_dir / "csdn_cover_error.png"),
                    full_page=True,
                )
            except Exception:
                pass
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
            except Exception:
                pass

    @staticmethod
    async def _fill_title(page, title: str):
        """标题（spec: ``input#title.el-input__inner``，maxlength=30）。"""
        if not title:
            return
        title_text = title[:CSDN_MAX_TITLE_LEN]
        logger.info(f"[填写标题] 标题: {title_text}")
        title_input = page.locator(
            '#title.el-input__inner, '
            'input#title, '
            '.Management-content input.el-input__inner'
        ).first
        await title_input.wait_for(state="visible", timeout=15000)
        await title_input.click()
        await title_input.fill("")
        await title_input.fill(title_text)
        await asyncio.sleep(0.5)

    @staticmethod
    async def _fill_desc(page, desc: str):
        """简介（spec: ``textarea#description.el-textarea__inner``，maxlength=150）。"""
        if not desc:
            return
        desc_text = desc[:CSDN_MAX_DESC_LEN]
        logger.info(f"[填写简介] 简介 {len(desc_text)} 字符")
        desc_input = page.locator(
            '#description.el-textarea__inner, '
            'textarea#description, '
            '.VideoManagement_description textarea.el-textarea__inner'
        ).first
        await desc_input.wait_for(state="visible", timeout=15000)
        await desc_input.click()
        await desc_input.fill("")
        await desc_input.fill(desc_text)
        await asyncio.sleep(0.5)

    @staticmethod
    async def _fill_tags(page, tags: list):
        """标签（spec 第 30-32 行）。

        标签在 ``.video_mark_selection_box_header input.el-input__inner`` 输入，
        输入后回车激活；最多 3 个，每个 ≤10 字。
        """
        import re as _re

        parsed_tags = []
        for t in tags or []:
            if isinstance(t, str):
                parsed_tags.extend(
                    s.strip().lstrip('#').strip()
                    for s in _re.split(r"[,，#]", t) if s.strip()
                )
        # 最多 3 个，每个 ≤10 字
        parsed_tags = [t[:10] for t in parsed_tags[:CSDN_MAX_TAGS]]
        if not parsed_tags:
            return

        logger.info(f"[填写标签] 待输入 {len(parsed_tags)} 个: {parsed_tags}")
        tag_input = page.locator(
            '.video_mark_selection_box_header input.el-input__inner'
        ).first
        try:
            await tag_input.wait_for(state="visible", timeout=10000)
        except Exception as e:
            logger.info(f"[填写标签] 未找到标签输入框: {e}")
            return

        for tag in parsed_tags:
            try:
                await tag_input.click()
                await tag_input.fill("")
                await tag_input.press_sequentially(tag, delay=100)
                await asyncio.sleep(0.5)
                # 回车激活标签
                await tag_input.press("Enter")
                await asyncio.sleep(1)
                logger.info(f"[填写标签] ✓ 已输入: {tag}")
            except Exception as e:
                logger.info(f"[填写标签] 输入 '{tag}' 失败: {e}")

    @staticmethod
    async def _set_recommend(page):
        """是否推荐（spec 第 42-43 行）。

        ``.el-radio`` 内的隐藏 radio，value=1。点击外层 label 触发勾选。
        默认不勾选；仅当用户开启「是否推荐」时才点。
        """
        logger.info("[是否推荐] 开启推荐")
        try:
            # 「是否被推荐」所在的 el-radio
            radio_label = page.locator(
                '.el-radio:has-text("是否被推荐")'
            ).first
            await radio_label.wait_for(state="visible", timeout=10000)
            # 点击 label（不要直接点隐藏的 input）
            await radio_label.click()
            logger.info("[是否推荐] ✓ 已勾选")
            await asyncio.sleep(0.5)
        except Exception as exc:
            logger.info(f"[是否推荐] 勾选失败（非致命）: {exc}")

    @staticmethod
    async def _click_submit(page) -> bool:
        """点击发布按钮（spec 第 46-48 行）。

        ``button.form-button.el-button--primary``（文案「发布」）。
        点击后页面跳转（离开 videoUpload 页）即视为发布成功。
        """
        logger.info("[发布] 点击发布按钮")
        current_url = page.url
        try:
            publish_btn = page.locator(
                'button.form-button.el-button--primary:has-text("发布")'
            ).first
            await publish_btn.wait_for(state="visible", timeout=15000)
            clicked = False
            for attempt, click_kwargs in enumerate(
                [{"timeout": 5000}, {"timeout": 5000, "force": True}]
            ):
                try:
                    await publish_btn.click(**click_kwargs)
                    clicked = True
                    logger.info(f"[发布] ✓ 已点击发布 (attempt={attempt + 1})")
                    break
                except Exception as e:
                    logger.info(f"[发布] 点击 attempt={attempt + 1} 失败: {e}")
            if not clicked:
                try:
                    await publish_btn.evaluate("el => el.click()")
                    clicked = True
                    logger.info("[发布] ✓ JS evaluate click 命中")
                except Exception as e:
                    logger.info(f"[发布] JS evaluate click 失败: {e}")
            if not clicked:
                return False

            # 等待页面跳转（离开 videoUpload 页 = 发布成功），最多 60s
            for _ in range(30):
                await asyncio.sleep(2)
                if page.url != current_url and "videoUpload" not in page.url:
                    logger.info(f"[发布] ✓ 页面已跳转: {page.url}")
                    return True
            logger.info("[发布] 60s 内页面未跳转，按成功处理")
            return True
        except Exception as exc:
            logger.info(f"[发布] 点击发布失败: {exc}")
            return False


# ---------------------------------------------------------------------------
# 素材方向查询已移除：CSDN 固定使用横版封面，不再需要按视频方向选择。
# ---------------------------------------------------------------------------
