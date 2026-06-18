"""Weibo platform implementation — CloakBrowser."""

import asyncio
import os
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._utils import save_login_result, scrape_weibo_profile
from ..base_platform import BasePlatform
from util._logger import get_channel_logger

from . import categories as _weibo_categories

logger = get_channel_logger("weibo")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WEIBO_CREATOR_URL = "https://weibo.com/n/微博创作者中心"
_WEIBO_LOGIN_HOST = "passport.weibo.com"
_WEIBO_LOGIN_PATH = "/sso/signin"
_WEIBO_UPLOAD_URL = "https://weibo.com/upload/channel"

#: 类型 radio 文本 → weibo 内部 video_type 编码
_VIDEO_TYPE_MAP = {
    "原创": "0",
    "转载": "1",
    "二创": "2",
}


# ======================================================================
# WeiboPlatform
# ======================================================================

class WeiboPlatform(BasePlatform):
    platform_id = 11
    platform_key = "weibo"
    platform_name = "微博"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Weibo login.

        Real flow (per user testing, 2026-06-15):
        1. Goto ``weibo.com/n/微博创作者中心`` (the creator centre home).
        2. The "登录" link is in the top-right of the page; click it.
        3. Clicking triggers a popup / new tab / redirect to
           ``passport.weibo.com/sso/signin``.
        4. User completes login in the popup (QR scan, phone, password, etc.).
        5. After login, the main page auto-refreshes and shows the user's avatar
           and nickname in the top nav (rendered as ``a[href^="/u/"]`` containing
           an ``img[src*="sinaimg.cn"]``).
        6. ``save_login_result`` runs on the now-authenticated main page.

        No timeout: the user may take as long as needed. Browser close → task
        cancel (handled by ``login_mode=True`` in ``_browser.py``).
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()

                await page.goto(_WEIBO_CREATOR_URL)

                # Scroll a small amount (200px) just in case, but rely on text selector
                await page.evaluate("window.scrollTo(0, 200)")
                await asyncio.sleep(0.5)

                # Click the "登录" link by text (robust against hash class changes).
                # NB: <a> 不带 href 在现代浏览器中没有 link role，所以不能用
                # get_by_role("link", ...)。get_by_text 匹配文本节点，不依赖角色。
                login_link = page.get_by_text("登录").first
                await login_link.click(timeout=15000)
                logger.info("[weibo] login link clicked, waiting for user to complete login")

                # Wait indefinitely for the post-login profile link. The user
                # may take as long as needed; browser close → task cancel
                # (handled by login_mode=True in _browser.py).
                # 等待登录成功标志（无限等）：浏览器关闭由 login_mode=True 处理
                # 必须限定到顶部导航栏 .woo-tab-nav，否则未登录态主页面有热门博主
                # 链接（同样 a[href^="/u/"] img[src*="sinaimg.cn"]）会误判已登录
                await page.locator(
                    '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]'
                ).first.wait_for(timeout=999999999)
                logger.info("[weibo] login detected (profile link in top nav)")

                # Give the page a moment to render authenticated content
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_weibo_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # check_cookie()
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid.

        微博失效不会重定向到 passport.weibo.com，而是渲染未登录界面（右上角
        显示登录/注册按钮）。所以用顶部导航的 profile link 作为「已登录」的
        唯一锚点：存在则 cookie 有效。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            return False

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_WEIBO_CREATOR_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await page.wait_for_load_state("networkidle", timeout=10000)

                # 顶部导航栏出现 a[href^="/u/"] 即视为已登录
                profile_link = page.locator(
                    '.woo-tab-nav a[href^="/u/"] img[src*="sinaimg.cn"]'
                ).first
                valid = await profile_link.count() > 0
                logger.info(f"[weibo] cookie {'valid' if valid else 'expired, needs re-login'}")
                return valid
            except Exception as exc:
                logger.info(f"[weibo] cookie check error: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center()
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Weibo creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        from .._browser import create_browser_sync, create_context_sync

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
    # sync_profile()
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Weibo creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                return await scrape_weibo_profile(page)
            except Exception as e:
                logger.info(f"[weibo] sync profile failed: {e}")
                return "", ""
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # publish_video -- full Weibo upload pipeline (sync entry point)
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to Weibo (sync wrapper).

        Accepted keyword arguments (与百家号保持一致):

        - ``title`` (*str*) -- 视频标题(0~30 字)
        - ``files`` (*list[str]*) -- 视频绝对路径(app.py 解析过)
        - ``tags`` (*list[str]*) -- 话题(暂未支持,占位)
        - ``account_file`` (*list[str]*) -- cookie 文件名列表
        - ``thumbnail_landscape_path`` (*str*, optional) -- 横版封面
        - ``thumbnail_portrait_path`` (*str*, optional) -- 竖版封面
        - ``desc`` (*str*, optional) -- 微博正文
        - ``category`` (*list[str]*|*str*, optional) -- 级联分类
          ``[channel_name, sub_name]``;也兼容 ``"channel|sub"`` 字符串
        - ``ai_content`` (*str*, optional) -- 类型声明(原创/二创/转载)

        V1 暂不支持定时发布;``schedule_time_str`` 等参数被忽略。
        """
        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # publish_image -- full Weibo image-album pipeline (sync entry point)
    # ------------------------------------------------------------------

    def publish_image(self, **kwargs) -> bool:
        """Publish an image album to Weibo (sync wrapper).

        入口仅做 kwargs 解包 + dry-run 早返回 + 调 _upload_all_images。
        实际浏览器操作在 _upload_one_image。
        """
        dry_run = kwargs.get("dry_run", False)
        if dry_run:
            logger.info("[weibo] dry-run skip (publish_image)")
            return True
        asyncio.run(self._upload_all_images(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal: orchestrate all account uploads (one batch per account)
    # ------------------------------------------------------------------

    async def _upload_all_images(self, **kwargs):
        """Create a browser per account, upload all images in the batch.

        与 video 版 _upload_all 的关键区别:**单层账号循环** (图集是一账号
        一次发完所有图),不是 files × accounts 笛卡尔积。
        """
        files = kwargs.get("files", []) or []
        account_file = kwargs.get("account_file", []) or []
        title = kwargs.get("title", "")
        tags = kwargs.get("tags", []) or []
        desc = kwargs.get("desc", "") or ""
        ai_content = kwargs.get("ai_content", "") or ""
        # 忽略字段(微博图集不支持)
        # is_original / enableTimer / schedule_time_str / cover_path
        _ = kwargs.get("is_original")  # noqa
        _ = kwargs.get("enableTimer")  # noqa
        _ = kwargs.get("schedule_time_str")  # noqa
        _ = kwargs.get("cover_path")  # noqa

        # 入口校验:微博图集服务端硬上限 18 张
        if len(files) > 18:
            raise ValueError(
                f"[weibo] 图集最多 18 张,当前 {len(files)} 张"
            )

        file_path_list = [str(f) for f in files]
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]

        # 单层账号循环(不是笛卡尔积!)
        for cookie_path in account_paths:
            await self._upload_one_image(
                title=title,
                file_path_list=file_path_list,
                tags=tags,
                account_file=cookie_path,
                desc=desc,
                ai_content=ai_content,
            )

    # ------------------------------------------------------------------
    # Internal: upload one image album to one account
    # ------------------------------------------------------------------

    async def _upload_one_image(
        self,
        title: str,
        file_path_list: list,
        tags: list,
        account_file: str,
        desc: str = "",
        ai_content: str = "",
    ):
        """Upload one image album to one Weibo account.

        流程:
        1. 创建 browser + context + 走 weibo.com 主页(不是 /upload/channel)
        2. wait_for 创作卡片(发送按钮) — cookie 失效检测
        3. _upload_images 上传多图
        4. _set_description 填正文 + 标签(复用 video 版)
        5. _set_content_statement 选 5 选项内容声明(复用 video 版)
        6. _click_send 点击发送
        7. _wait_for_image_publish_success 等成功信号
        8. 保存 cookie
        """
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
                page = await context.new_page()
                # 关键: 走主页而不是 /upload/channel
                await page.goto("https://weibo.com", timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

                # 关键: wait_for 创作卡片(发送按钮) — cookie 失效/未登录会抛
                try:
                    await page.get_by_role(
                        "button", name="发送", exact=True
                    ).first.wait_for(state="attached", timeout=15000)
                except Exception as e:
                    raise RuntimeError(
                        f"[weibo] 创作卡片未渲染(cookie 失效/未登录?): {e}"
                    )
                await asyncio.sleep(2)  # 等图片工具/声明 trigger 完全渲染

                # 1. 上传图片
                await self._upload_images(page, file_path_list)

                # 2. 填正文 + 标签
                await self._set_description(page, desc, title, tags)

                # 3. 内容声明 (复用 video 版)
                await self._set_content_statement(page, ai_content)

                # 4. 发送
                await self._click_send(page)

                # 5. 等成功信号
                await self._wait_for_image_publish_success(page)

                # 6. 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[weibo] cookie 已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: upload image files via hidden input[type=file]
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_images(page, files: list):
        """上传图集多张图 — 多重兜底(2026-06-17 v1)。

        selector 策略:input[type=file][accept^='image/'][multiple]
        (用户提供的 DOM 行 9-10:accept 以 image/* 开头,且带 multiple)
        注意:input 祖父是 display:none,但 Playwright set_input_files 不要求
        visible,只要求 attached + enabled。

        多重兜底:
        1. 直接 set_input_files(files) 命中 input
        2. 失败则 expect_file_chooser + 点击「图片」trigger
        3. 再失败则 patch click/dispatchEvent/showPicker + MutationObserver

        等待完成:轮询「发送」按钮的 disabled 属性为 None(上传+表单就绪
        → 启用);最多 5 分钟。
        """
        if not files:
            logger.warning("[weibo] 无图片可上传")
            return

        logger.info("[weibo] 准备上传 %d 张图片", len(files))

        # 0. 安装 MutationObserver 兜底(参考 video 版 _upload_video_file)
        await page.evaluate(r"""() => {
            if (window.__weiboImgObserverInstalled) return;
            window.__weiboImgObserverInstalled = true;
            window.__weiboImgInitialInputCount =
                document.querySelectorAll('input[type="file"]').length;
            const observer = new MutationObserver(() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > window.__weiboImgInitialInputCount) {
                    for (let i = window.__weiboImgInitialInputCount;
                         i < inputs.length; i++) {
                        inputs[i].setAttribute('data-weibo-img-new', '1');
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }""")

        # 1. Patch 三个入口(参考 video 版)
        patch_status = await page.evaluate(r"""() => {
            if (window.__weiboImgAllPatched) return 'already-patched';
            window.__weiboImgAllPatched = true;
            const markInput = function (input) {
                try {
                    input.setAttribute('data-weibo-img-upload', '1');
                    if (!input.isConnected) {
                        input.style.display = 'none';
                        document.body.appendChild(input);
                    }
                } catch (e) {}
            };
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') {
                    markInput(this);
                } else {
                    return origClick.apply(this, arguments);
                }
            };
            const origDispatch = EventTarget.prototype.dispatchEvent;
            EventTarget.prototype.dispatchEvent = function (event) {
                if (this && this.type === 'file' && event &&
                    event.type === 'click' && event instanceof MouseEvent) {
                    markInput(this);
                    return true;
                }
                return origDispatch.apply(this, arguments);
            };
            if (HTMLInputElement.prototype.showPicker) {
                const origShow = HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker = function () {
                    if (this && this.type === 'file') {
                        markInput(this);
                    } else {
                        return origShow.apply(this, arguments);
                    }
                };
            }
            return 'patched';
        }""")
        logger.info("[weibo] img patch status: %s", patch_status)

        # 2. 找「图片」trigger
        # selector:文本 "图片" 在 woo-pop-wrap 内,且 sibling 包含 image upload input
        img_trigger = page.get_by_text("图片", exact=True).first
        if await img_trigger.count() == 0:
            raise RuntimeError("[weibo] 未找到「图片」工具图标")

        # 3. 优先直接 set_input_files(接受 hidden input)
        target_input_sel = (
            "input[type='file'][accept^='image/'][multiple]"
        )
        try:
            target_input = page.locator(target_input_sel).first
            await target_input.wait_for(state="attached", timeout=10000)
            await target_input.set_input_files(files)
            logger.info("[weibo] 已通过 set_input_files 提交 %d 张图", len(files))
        except Exception as e:
            logger.info("[weibo] 直接 set_input_files 失败: %s", e)

            # 兜底 1: expect_file_chooser + 点击 trigger
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await img_trigger.click(force=True)
                fc = await fc_info.value
                await fc.set_files(files)
                logger.info("[weibo] 已通过 expect_file_chooser 提交")
            except Exception as e2:
                logger.info("[weibo] expect_file_chooser 失败: %s", e2)
                # 兜底 2: 等带标记的 input 出现(patch 命中)
                marked_sel = (
                    "input[type='file'][data-weibo-img-upload='1'],"
                    "input[type='file'][data-weibo-img-new='1']"
                )
                deadline = asyncio.get_event_loop().time() + 30
                found = None
                while asyncio.get_event_loop().time() < deadline:
                    count = await page.locator(marked_sel).count()
                    if count > 0:
                        found = page.locator(marked_sel).first
                        break
                    await asyncio.sleep(0.5)
                if found is not None:
                    await found.set_input_files(files)
                    logger.info("[weibo] 已通过 patched input 提交")
                else:
                    raise RuntimeError(
                        f"[weibo] 30s 内未找到可用的 file input"
                    )

        # 4. 等待上传完成 — 轮询「发送」按钮 enabled(最稳判定)
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        deadline = asyncio.get_event_loop().time() + 300  # 5 分钟
        while asyncio.get_event_loop().time() < deadline:
            try:
                disabled = await send_btn.get_attribute("disabled")
                if disabled is None:
                    logger.info("[weibo] 图片已上传,发送按钮已启用")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)

        raise RuntimeError("[weibo] 5 分钟内图片未上传完成(发送按钮未启用)")

    # ------------------------------------------------------------------
    # Helper: click 发送 button
    # ------------------------------------------------------------------

    @staticmethod
    async def _click_send(page):
        """点击「发送」按钮(图集版,视频版是「发布」)。

        与 video 版 _click_publish 同构,只是 button name 不同。
        初始 disabled,表单就绪后启用 — 轮询 disabled 属性(最长 60s)。
        """
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        try:
            await send_btn.wait_for(state="visible", timeout=10000)
        except Exception as e:
            raise RuntimeError(f"[weibo] 未找到「发送」按钮: {e}")

        # 轮询 disabled(最长 60s)
        for _ in range(60):
            disabled = await send_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[weibo] 「发送」按钮一直 disabled,表单未就绪")

        await send_btn.click()
        logger.info("[weibo] 已点击「发送」按钮")

    # ------------------------------------------------------------------
    # Helper: wait for image publish success signal
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_image_publish_success(page, timeout_s: int = 60):
        """等待图集发布完成。

        微博图集发送后**无明显 toast**(与 video 版的「视频已上传成功」
        不同)。判定成功靠 2 个条件 OR:
        1. textarea 内容清空
        2. 创作卡片回到初始态(「发送」按钮重新 disabled)

        60s 内任一命中即视为成功。
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        textarea = page.locator("textarea[placeholder*='有什么新鲜事']").first
        send_btn = page.get_by_role("button", name="发送", exact=True).first

        while asyncio.get_event_loop().time() < deadline:
            try:
                # 条件 1: textarea 清空
                textarea_empty = await textarea.input_value() == ""
                # 条件 2: 发送按钮重新 disabled
                disabled = await send_btn.get_attribute("disabled")
                send_disabled = disabled is not None
                if textarea_empty or send_disabled:
                    logger.info("[weibo] 图集发布成功(textarea 空=%s, send 禁用=%s)",
                                textarea_empty, send_disabled)
                    return
            except Exception:
                pass
            await asyncio.sleep(2)

        raise RuntimeError(
            f"[weibo] 等待图集发布完成超时({timeout_s}s)"
        )

    # ------------------------------------------------------------------
    # Internal: orchestrate all file × account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """Create a browser per file+account combo and upload."""
        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path")
        desc = kwargs.get("desc", "") or ""
        category = kwargs.get("category")
        ai_content = kwargs.get("ai_content", "") or ""
        content_statement = kwargs.get("content_statement", "") or ""

        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(thumbnail_portrait_path)

        for file_path in file_paths:
            for cookie_path in account_paths:
                await self._upload_one_video(
                    title=title,
                    file_path=file_path,
                    tags=tags,
                    account_file=cookie_path,
                    thumbnail_landscape_path=thumbnail_landscape_path,
                    thumbnail_portrait_path=thumbnail_portrait_path,
                    desc=desc,
                    category=category,
                    ai_content=ai_content,
                    content_statement=content_statement,
                )

    # ------------------------------------------------------------------
    # Internal: upload one video to one account
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        account_file: str,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        desc="",
        category=None,
        ai_content="",
        content_statement="",
    ):
        """Upload a single video to one Weibo account."""
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
                page = await context.new_page()
                await page.goto(_WEIBO_UPLOAD_URL, timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                logger.info("[weibo] 正在上传-------%s", title)

                # 注册 weibocdn 上传请求监听(spec line 7215-7216)
                # 这是上传完成的权威信号; 同时打印每个分块请求便于诊断
                upload_req_count = {"n": 0}
                upload_resp_count = {"n": 0}

                def _on_upload_request(request):
                    url = request.url
                    # 监听所有 fileplatform 相关请求(不只 upload.json)
                    # 看 drop 上传完成后是否缺了某个"完成/合并"请求
                    if "fileplatform" in url or (
                        "weibocdn.com" in url and "upload" in url.lower()
                    ):
                        upload_req_count["n"] += 1
                        logger.info(
                            "[weibo] ▲ #%d %s %s",
                            upload_req_count["n"], request.method, url[:200],
                        )

                async def _on_upload_response(response):
                    url = response.url
                    if "fileplatform" in url or (
                        "weibocdn.com" in url and "upload" in url.lower()
                    ):
                        upload_resp_count["n"] += 1
                        # 读响应 body,看协议字段(最后一个分块可能有特殊标记)
                        body_preview = ""
                        try:
                            body = await response.text()
                            body_preview = body[:500].replace("\n", " ")
                        except Exception as e:
                            body_preview = f"<body 读取失败: {e}>"
                        logger.info(
                            "[weibo] ▼ #%d status=%d body=%s",
                            upload_resp_count["n"], response.status,
                            body_preview,
                        )

                page.on("request", _on_upload_request)
                page.on("response", _on_upload_response)

                # 上传视频文件
                await self._upload_video_file(page, file_path)

                # 等待视频真正上传完成(「上传中」spinner DOM 消失 = 上传完成)
                await self._wait_for_upload_form(page)

                # 类型(原创/二创/转载)
                await self._set_video_type(page, ai_content)

                # 标题
                await self._set_title(page, title)

                # 封面(ESC 关闭原生选择器 + 隐藏 input)
                await self._set_cover(
                    page,
                    thumbnail_landscape_path,
                    thumbnail_portrait_path,
                )

                # 分类(两级级联)
                await self._set_category(page, category)

                # 微博正文
                await self._set_description(page, desc, title, tags)

                # 内容声明(可选)
                await self._set_content_statement(page, content_statement)

                # 点发布
                await self._click_publish(page)

                # 等待发布成功标志
                await self._wait_for_publish_success(page)

                # 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[weibo] cookie 已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper: upload the video file via hidden input[type=file]
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """上传视频主文件 — 多重兜底(2026-06-16 v3)。

        CloakBrowser + 微博前端组合下,单一的 patch 路径不稳定:
        22:21 那次走 ``input.click()`` 命中;22:25、22:29 那次 patch 三个
        入口(click / dispatchEvent / showPicker)全不命中,但手动点击按钮
        能触发 file picker。说明 CloakBrowser 在某些会话里会屏蔽 button
        click 的副作用(不调任何 input API)。

        多重兜底:
        1. ``expect_file_chooser`` — Playwright 原生 API,优先用这个
        2. Patch click / dispatchEvent / showPicker — 三大入口
        3. MutationObserver 检测新 file input — 兜底(动态 input 加到 DOM)
        4. 多种点击方式 — force=True / mouse.move+click / JS .click()
        """
        file_size = os.path.getsize(file_path)
        logger.info(
            "[weibo] 准备上传视频: %s (%.1f MB)",
            os.path.basename(file_path), file_size / 1024 / 1024,
        )

        # 0. 安装 MutationObserver 兜底: 任何新加到 DOM 的 file input 都自动标记
        await page.evaluate(r"""() => {
            if (window.__weiboObserverInstalled) return;
            window.__weiboObserverInstalled = true;
            window.__weiboInitialInputCount =
                document.querySelectorAll('input[type="file"]').length;
            const observer = new MutationObserver(() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > window.__weiboInitialInputCount) {
                    for (let i = window.__weiboInitialInputCount;
                         i < inputs.length; i++) {
                        inputs[i].setAttribute('data-weibo-new', '1');
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }""")

        # 1. Patch 三个入口
        patch_status = await page.evaluate(r"""() => {
            if (window.__weiboAllPatched) return 'already-patched';
            window.__weiboAllPatched = true;
            const markInput = function (input) {
                try {
                    input.setAttribute('data-weibo-upload', '1');
                    if (!input.isConnected) {
                        input.style.display = 'none';
                        document.body.appendChild(input);
                    }
                } catch (e) {}
            };
            // click
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') {
                    markInput(this);
                } else {
                    return origClick.apply(this, arguments);
                }
            };
            // dispatchEvent(MouseEvent click)
            const origDispatch = EventTarget.prototype.dispatchEvent;
            EventTarget.prototype.dispatchEvent = function (event) {
                if (this && this.type === 'file' && event &&
                    event.type === 'click' && event instanceof MouseEvent) {
                    markInput(this);
                    return true;
                }
                return origDispatch.apply(this, arguments);
            };
            // showPicker
            if (HTMLInputElement.prototype.showPicker) {
                const origShow = HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker = function () {
                    if (this && this.type === 'file') {
                        markInput(this);
                    } else {
                        return origShow.apply(this, arguments);
                    }
                };
            }
            return 'patched';
        }""")
        logger.info("[weibo] patch status: %s", patch_status)

        # 2. 找上传按钮
        upload_btn = page.locator("button[id^='video_button_upload']").first
        if await upload_btn.count() == 0:
            upload_btn = page.get_by_role(
                "button", name="上传视频", exact=True,
            ).first
        if await upload_btn.count() == 0:
            raise RuntimeError("[weibo] 未找到「上传视频」按钮")

        await upload_btn.wait_for(state="visible", timeout=10000)

        # 3. 触发按钮 — 多重尝试,任一成功即可
        triggered = False

        # 方式 A: expect_file_chooser 优先(原生 Playwright API)
        try:
            async with page.expect_file_chooser(timeout=5000) as fc_info:
                await upload_btn.click(force=True)
            fc = await fc_info.value
            await fc.set_files(file_path)
            logger.info("[weibo] 已通过 expect_file_chooser 提交视频")
            triggered = True
        except Exception as e:
            logger.info("[weibo] expect_file_chooser 方式失败: %s", e)

        # 方式 B: 普通 click + 等带标记 input (patch 命中)
        if not triggered:
            try:
                await upload_btn.click(force=True)
                logger.info("[weibo] 已点击「上传视频」按钮(force=True)")
            except Exception as e:
                logger.warning("[weibo] force=True click 失败: %s", e)
                await upload_btn.evaluate("el => el.click()")
                logger.info("[weibo] 已点击「上传视频」按钮(JS .click())")

        # 4. 等带标记的 input 出现(patch 命中 或 MutationObserver 命中)
        marked_sel = (
            "input[type='file'][data-weibo-upload='1'],"
            "input[type='file'][data-weibo-new='1']"
        )
        deadline = asyncio.get_event_loop().time() + 30
        found_input = None
        while asyncio.get_event_loop().time() < deadline:
            try:
                count = await page.locator(marked_sel).count()
                if count > 0:
                    found_input = page.locator(marked_sel).first
                    logger.info("[weibo] 检测到标记的 file input(count=%d)", count)
                    break
            except Exception as e:
                logger.warning("[weibo] locator count 异常: %s", e)
            await asyncio.sleep(0.5)

        if found_input is not None:
            await found_input.set_input_files(file_path)
            logger.info(
                "[weibo] 视频文件已通过 patched input 提交: %s",
                os.path.basename(file_path),
            )
            return

        # 5. 三重都失败
        all_count = await page.locator("input[type='file']").count()
        raise RuntimeError(
            "[weibo] 30s 内未检测到带标记的 file input。"
            f"input[type=file] 总数: {all_count}。"
            "CloakBrowser 屏蔽了所有 click 路径,需要换策略。"
        )

    # ------------------------------------------------------------------
    # Helper: wait for upload to finish and the form to appear
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_upload_form(page, timeout_s: int = 14400):
        """等待视频上传完成、表单可交互。

        **权威锚点**(2026-06-17 调整): 两个信号中任一为真即返回。

        1. 「上传中」spinner DOM 消失 — 直接信号
        2. 发布按钮文字从「自动发布」变成「发布」 — 上传中按钮文案是
           「自动发布」,上传完成后变为「发布」。检测 ``button[name=发布]``
           可见即视为上传完成。

        用 OR 不用 AND 的原因: weibo 在文件传输完成(``check.json`` 200)
        后,「上传中」spinner DOM 仍会持续存在较长时间(可能用于转码阶段,
        实测 7+ 分钟仍未消失),仅看 spinner 会导致函数长时间挂起,所有
        后续表单操作全部阻塞。OR 逻辑下一旦发布按钮文字变更为「发布」
        就放行,避免误判。

        DOM 结构(spinner):
        ```html
        <div class="woo-box-flex woo-box-alignCenter _info_xxx_135">
            <svg class="woo-spinner-main">...</svg>
            <span>上传中</span>
            <span>3.01MB/14.33MB</span>
            <a>暂停</a><a>删除</a>
        </div>
        ```

        class 名是 CSS-modules 生成、会随构建变化 — 用「上传中」文本
        (exact match) 检测这个 DOM 是否还在。

        上传未完成之前,所有后续表单设置操作(_set_video_type /
        _set_title / _set_cover / _set_category / _set_description /
        _set_content_statement / _click_publish) 全部阻塞在此函数,
        等任一信号命中才继续。

        **超时默认 4 小时**(14400s):大视频(几 GB)+ 慢网络上传可能
        需要 1 小时甚至更久,留足余量。
        """
        # 检测「上传中」spinner DOM 是否还存在 + 发布按钮文字是否变成「发布」
        uploading_locator = page.get_by_text("上传中", exact=True)
        publish_btn = page.get_by_role("button", name="发布", exact=True).first
        deadline = asyncio.get_event_loop().time() + timeout_s

        while asyncio.get_event_loop().time() < deadline:
            # 1. 「上传中」DOM 消失 或 发布按钮可见(文字已从「自动发布」变成「发布」)
            try:
                uploading_gone = await uploading_locator.count() == 0
                publish_visible = await publish_btn.is_visible()
                if uploading_gone or publish_visible:
                    if uploading_gone and publish_visible:
                        logger.info(
                            "[weibo] 「上传中」DOM 已消失且「发布」按钮可见,"
                            "上传完成、表单可交互"
                        )
                    elif uploading_gone:
                        logger.info(
                            "[weibo] 「上传中」DOM 已消失,上传完成"
                        )
                    else:
                        logger.info(
                            "[weibo] 「上传中」DOM 仍存在,但「发布」按钮已可见,"
                            "视为上传完成、表单可交互(转码阶段 spinner 暂未消失)"
                        )
                    return
            except Exception:
                pass

            # 2. 上传失败检测
            try:
                if await page.get_by_text("上传失败", exact=True).count() > 0:
                    raise RuntimeError(
                        "[weibo] 视频上传失败(页面检测到「上传失败」文本)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

            # 3. 进度旁证(每 30s 一次,避免刷屏)
            try:
                remaining = int(deadline - asyncio.get_event_loop().time())
                if remaining % 60 < 5 or remaining < 60:
                    uploading_count = await uploading_locator.count()
                    logger.info(
                        "[weibo] 等待「上传中」消失或「发布」按钮可见... "
                        "上传中=%d (剩余 %ds)",
                        uploading_count, remaining,
                    )
            except Exception:
                pass

            await asyncio.sleep(5)

        # 超时
        try:
            url = page.url
        except Exception:
            url = "(unknown)"
        raise RuntimeError(
            f"[weibo] 等待视频上传完成超时({timeout_s}s = "
            f"{timeout_s // 60}min),「上传中」未消失且「发布」按钮未可见。"
            f"当前 URL: {url}"
        )

    # ------------------------------------------------------------------
    # Helper: select video type (原创/二创/转载)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_video_type(page, ai_content: str):
        """选择类型单选(原创/二创/转载)。ai_content 传的是 UI 标签文本。"""
        if not ai_content:
            return  # 默认值由微博控制,不强选
        # 取出 spec 里的 _VIDEO_TYPE_MAP 的 key (原创/转载/二创)
        target = None
        for label in _VIDEO_TYPE_MAP:
            if label in ai_content or ai_content in label:
                target = label
                break
        if not target:
            logger.warning("[weibo] 未知类型声明值: %s,跳过", ai_content)
            return
        # DOM: <label><input type="radio"><span>原创</span></label>
        # 标签内的 radio 的无障碍名取自兄弟 span 文本
        radio = page.get_by_role("radio", name=target, exact=True).first
        try:
            await radio.wait_for(state="visible", timeout=5000)
            await radio.click(force=True)
            logger.info("[weibo] 已选类型: %s", target)
        except Exception as e:
            logger.warning("[weibo] 选择类型失败(%s): %s", target, e)

    # ------------------------------------------------------------------
    # Helper: fill video title
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_title(page, title: str):
        """填充标题(0~30 字)。"""
        if not title:
            return
        # 微博标题 placeholder: 填写标题(0～30个字)
        title_input = page.locator("input[placeholder*='填写标题']").first
        await title_input.wait_for(state="visible", timeout=10000)
        # 标题最多 30 字
        truncated = title.strip()[:30]
        await title_input.fill(truncated)
        logger.info("[weibo] 已填标题: %s", truncated)

    # ------------------------------------------------------------------
    # Helper: 根据页面封面区域宽高比选横版/竖版封面
    # ------------------------------------------------------------------

    @staticmethod
    async def _pick_cover_by_aspect(
        page,
        landscape_path=None,
        portrait_path=None,
    ):
        """根据当前页面封面框的宽高比,选横版还是竖版封面。

        微博封面框用 ``<div style="padding-bottom: X%;"></div>`` 实现
        宽高比(X = height/width × 100):
        - X < 100 → 横版(landscape),16:9 时 X=56.25
        - X > 100 → 竖版(portrait),9:16 时 X≈177.78
        - X == 100 → 正方形(本函数按横版走)

        实现思路:从「上传封面」/「裁剪封面」链接反向查找,沿祖先
        找包含 ``div[style*="padding-bottom"]`` 的容器 — 该容器就是
        当前实际的封面框,里面的 aspect div 给出宽高比。读不到(还没
        渲染 / 解析失败)默认横版,向后兼容。

        注意:检测时机必须在表单渲染完成之后,否则 cover 区域 DOM
        不完整(2026-06-17 实测)。这里先 wait_for 「上传封面」链接
        attached 再跑 JS。
        """
        # 先等封面区域 DOM 完整 — 2026-06-17 实测:链接先于 picture 出现,
        # walk-up 14 层都找不到 aspect div(整个页面 totalAspects=0)。
        # 关键等待:link 所在 inner 容器(link 的祖父)里出现 <img>,这才是
        # picture 真正渲染好的直接信号,比等 abstract 的 "div[style*=
        # padding-bottom]" 可靠(后者会假阳性命中 padding-bottom:0 的
        # 无关 div)。
        try:
            await page.get_by_text("上传封面").first.wait_for(
                state="attached", timeout=10000,
            )
        except Exception as e:
            logger.warning("[weibo] 等「上传封面」链接超时: %s", e)

        try:
            # link 的 xpath=../.. 是 inner 容器
            # (_box_1ant3_2 / _a5lt_1gx9k_203),内含 picture + 链接区
            inner = page.get_by_text("上传封面", exact=True).first.locator(
                "xpath=../.."
            )
            await inner.locator("img").first.wait_for(
                state="attached", timeout=10000,
            )
        except Exception as e:
            logger.warning("[weibo] 等封面 picture(img) 超时: %s", e)

        try:
            aspect, debug = await page.evaluate(r"""() => {
                // 反向:从「上传封面」/「裁剪封面」链接向上找含 aspect div 的祖先
                // aspect div 选择器收紧到要带 %,避开 padding-bottom:0 的假阳性
                const ASPECT_SEL = 'div[style*="padding-bottom"][style*="%"]';
                const links = document.querySelectorAll('a');
                let coverLink = null;
                for (const a of links) {
                    const t = (a.textContent || '').trim();
                    if (t === '上传封面' || t === '裁剪封面') {
                        coverLink = a;
                        break;
                    }
                }
                if (!coverLink) {
                    return [null, {
                        reason: 'no cover link found',
                        allLinkTexts: Array.from(links)
                            .map(a => (a.textContent || '').trim())
                            .filter(s => s.length > 0 && s.length < 20)
                            .slice(0, 30),
                    }];
                }

                // 调试:aspect div 全局统计 + 第一个 aspect div 的 style
                const allAspects = document.querySelectorAll(ASPECT_SEL);
                const debug = {
                    totalAspects: allAspects.length,
                    firstAspectStyle: allAspects[0]
                        ? allAspects[0].getAttribute('style')
                        : null,
                    linkParentTag: coverLink.parentElement
                        ? coverLink.parentElement.tagName
                        : null,
                    linkParentClass: coverLink.parentElement
                        ? (coverLink.parentElement.className || '').substring(0, 80)
                        : null,
                    ancestorChain: [],
                };

                let p = coverLink.parentElement;
                let depth = 0;
                while (p && p !== document.body && depth < 20) {
                    const aspectDiv = p.querySelector(ASPECT_SEL);
                    const hasAspect = aspectDiv !== null;
                    debug.ancestorChain.push({
                        depth,
                        tag: p.tagName,
                        className: (p.className || '').substring(0, 80),
                        hasAspect,
                    });
                    if (hasAspect) {
                        const m = (
                            aspectDiv.getAttribute('style') || ''
                        ).match(
                            /padding-bottom:\s*([0-9.]+)\s*%/i
                        );
                        if (m) {
                            debug.matchedAt = depth;
                            debug.matchedStyle = aspectDiv.getAttribute('style');
                            return [parseFloat(m[1]), null];
                        }
                    }
                    p = p.parentElement;
                    depth++;
                }
                return [null, { reason: 'aspect div not found in ancestors', ...debug }];
            }""")
        except Exception as e:
            logger.warning("[weibo] 读取封面区域宽高比失败: %s", e)
            aspect = None
            debug = None

        if debug:
            logger.info("[weibo] 封面宽高比调试: %s", debug)

        if aspect is None:
            logger.info("[weibo] 读不到封面框宽高比,默认横版")
            return landscape_path or portrait_path

        if aspect < 100:
            logger.info(
                "[weibo] 封面框为横版(padding-bottom=%.2f%%),用横版封面",
                aspect,
            )
            return landscape_path or portrait_path
        else:
            logger.info(
                "[weibo] 封面框为竖版(padding-bottom=%.2f%%),用竖版封面",
                aspect,
            )
            return portrait_path or landscape_path

    # ------------------------------------------------------------------
    # Helper: upload cover (click 上传封面 → ESC → hidden file input → 完成)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_cover(
        page,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
    ):
        """上传封面。

        流程(spec ~/1.txt:12-19):
        1. 根据页面封面框宽高比选横版/竖版封面
           (见 ``_pick_cover_by_aspect``)
        2. 点击「上传封面」链接(自动打开系统原生文件选择器)
        3. 按 ESC 关闭原生选择器
        4. 等待「编辑封面」弹层出现
        5. 找到弹层内的隐藏 ``input[type=file]`` 上传图片
        6. 点击「完成」按钮
        """
        cover_path = await WeiboPlatform._pick_cover_by_aspect(
            page,
            landscape_path=thumbnail_landscape_path,
            portrait_path=thumbnail_portrait_path,
        )
        if not cover_path or not os.path.exists(cover_path):
            logger.info("[weibo] 无封面文件,跳过封面上传")
            return

        # 1. 点击「上传封面」(注意 a 标签无 href,用文本匹配)
        upload_cover_link = page.get_by_text("上传封面").first
        try:
            await upload_cover_link.wait_for(state="visible", timeout=10000)
        except Exception:
            logger.warning("[weibo] 未找到「上传封面」入口,跳过封面")
            return

        # 2. 点击 + 立即 ESC 关掉原生选择器(spec 强调此坑)
        await upload_cover_link.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.8)
        logger.info("[weibo] 已点击上传封面并 ESC 关闭原生选择器")

        # 3. 等待「编辑封面」弹层出现
        try:
            await page.get_by_text("编辑封面").first.wait_for(
                state="visible", timeout=10000
            )
            logger.info("[weibo] 封面编辑弹层已出现")
        except Exception as e:
            logger.warning("[weibo] 等待封面弹层超时: %s", e)
            return

        # 4. 找到隐藏 input[type=file] 上传
        # spec 弹层里有两个 file input,accept 都是 ".jpg, .jpeg, .bmp, ..."
        # 关键: **不能** 用 [accept*='jpg'] — 微博正文区也有一个 image
        # 上传 input,accept 是 "image/*, .jpg, .jpeg, ..."(以 image/*
        # 开头),会被一起匹配,导致 .first 选错。
        # 用 [accept^='.jpg'] 严格匹配"以 .jpg 开头",只命中封面弹层。
        file_inputs = page.locator("input[type='file'][accept^='.jpg']")
        count = await file_inputs.count()
        if not count:
            logger.warning("[weibo] 封面弹层未找到 input[type=file][accept^='.jpg']")
            return
        logger.info("[weibo] 找到 %d 个封面 file input", count)
        await file_inputs.first.set_input_files(cover_path)
        logger.info("[weibo] 已上传封面文件: %s", os.path.basename(cover_path))
        # 等图片处理完(上传到 weibo + 裁剪器加载预览)。2s 实测不够,
        # 经常「完成」点了之后弹层关掉但封面没存上(2026-06-17)。
        await asyncio.sleep(4)

        # 5. 点击「完成」按钮 (封面编辑弹层右下角)
        # 用 role+name 定位,避免 class 哈希漂移
        done_btn = page.get_by_role("button", name="完成", exact=True).first
        try:
            await done_btn.wait_for(state="visible", timeout=5000)
            # force=True 兜底:封面弹层是 fixed 定位,偶尔有透明遮罩
            # 拦截 pointer events,导致普通 click 一直 retry(2026-06-17 实测)
            await done_btn.click(force=True)
            logger.info("[weibo] 已点击封面完成按钮")
        except Exception as e:
            logger.warning("[weibo] 点击封面完成按钮失败: %s", e)

        # 6. 关键: 等待「编辑封面」弹层真正关闭,否则它会盖住下面的
        #    「请选择合适的频道」下拉触发器和微博正文 textarea,导致后续步骤
        #    全部因元素 hidden 而失败。
        try:
            await page.get_by_text(
                "编辑封面", exact=True,
            ).first.wait_for(state="hidden", timeout=15000)
            logger.info("[weibo] 封面编辑弹层已关闭")
        except Exception as e:
            logger.warning(
                "[weibo] 等待封面弹层关闭超时,尝试 ESC 强制关闭: %s", e,
            )
            # ESC 兜底
            for _ in range(2):
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
        await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Helper: set category via 2-level cascade selector
    # ------------------------------------------------------------------

    async def _set_category(self, page, category):
        """选择分类(两级级联)。

        ``category`` 可为:
        - ``["VLOG", "旅行"]`` (前端 cascader 默认传数组)
        - ``"VLOG|旅行"`` (兼容字符串)
        - ``None`` (跳过,使用默认)
        """
        if not category:
            logger.info("[weibo] 未传分类,使用默认")
            return

        if isinstance(category, str):
            parts = [p.strip() for p in category.split("|")]
            if len(parts) != 2:
                logger.warning("[weibo] 分类字符串格式错误: %s", category)
                return
            channel_name, sub_name = parts
        elif isinstance(category, (list, tuple)) and len(category) == 2:
            channel_name, sub_name = category[0], category[1]
        else:
            logger.warning("[weibo] 分类参数无法识别: %r", category)
            return

        # 查表验证
        found = _weibo_categories.lookup_sub_channel(channel_name, sub_name)
        if not found:
            logger.warning(
                "[weibo] 分类未在静态表里命中: %s/%s,仍尝试在页面上点",
                channel_name, sub_name,
            )

        # 级联下拉触发器: 初始有「请选择合适的频道」占位文本
        # 2026-06-17 实测:占位文本所在 inner div(woo-box-item-flex)
        # 被 Playwright 判 hidden(24× retry → timeout),不能直接点它,
        # 也不要用 wait_for(state="visible")。改用:
        # 1. wait_for(state="attached") — 只要在 DOM 里就行
        # 2. 点父级 trigger (wbpro-select 元素)
        # 3. force=True 绕过任何拦截检查
        trigger_text = page.get_by_text("请选择合适的频道", exact=True)
        try:
            await trigger_text.first.wait_for(state="attached", timeout=10000)
        except Exception as e:
            logger.warning("[weibo] 未找到分类下拉触发器(占位文本): %s", e)
            return

        # 1. 点开下拉 — 点父级 trigger (xpath=.. 是 Playwright 的"父节点"语法)
        trigger = trigger_text.first.locator("xpath=..")
        await trigger.click(force=True)
        await asyncio.sleep(0.5)

        # 下拉面板有两列: 左=频道,右=子分类。左列在 DOM 中先渲染,
        # 所以同名条目(如「美食」既是频道又是 VLOG 的子分类)取 first 得到频道,
        # 取 last 得到子分类。
        try:
            # 2. 等下拉打开: 已知频道「VLOG」必然在第一列
            await page.get_by_text("VLOG", exact=True).first.wait_for(
                state="visible", timeout=5000,
            )
            # 点目标频道(取 first: 频道列在前)
            await page.get_by_text(
                channel_name, exact=True,
            ).first.click()
            logger.info("[weibo] 已选一级频道: %s", channel_name)
            await asyncio.sleep(0.5)

            # 3. 等子分类列渲染: 目标 sub_name 应可见
            # 取 last: 子分类列在频道列之后,避免点到同名的频道
            sub_locator = page.get_by_text(sub_name, exact=True)
            await sub_locator.last.wait_for(state="visible", timeout=5000)
            await sub_locator.last.click()
            logger.info("[weibo] 已选二级子分类: %s", sub_name)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(
                "[weibo] 级联选择失败(channel=%s sub=%s): %s",
                channel_name, sub_name, e,
            )
            # ESC 关掉下拉避免挡住后续操作
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

    # ------------------------------------------------------------------
    # Helper: fill 微博正文 (description + tags as #话题)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_description(page, desc: str, title: str, tags: list):
        """填充微博正文 textarea。

        若 desc 为空,回落到 title;tags 拼成 #话题 形式追加。
        """
        # textarea placeholder: 有什么新鲜事想分享给大家?
        textarea = page.locator(
            "textarea[placeholder*='有什么新鲜事']"
        ).first
        await textarea.wait_for(state="visible", timeout=10000)

        text = (desc or title or "").strip()
        if tags:
            tag_str = " ".join(f"#{t}" for t in tags)
            text = f"{text} {tag_str}".strip() if text else tag_str
        if not text:
            return

        # 微博 textarea 不是标准 input,fill 不一定生效,用 click+type
        await textarea.click()
        await asyncio.sleep(0.2)
        await page.keyboard.type(text, delay=30)
        await page.keyboard.press("Space")
        logger.info("[weibo] 已填正文(长度=%d)", len(text))

    # ------------------------------------------------------------------
    # Helper: set 内容声明 (内容为自主创作/转载/AI生成/虚构演绎)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_content_statement(page, statement: str):
        """选择底部工具栏的「内容声明」。

        spec line 7206: 5 个选项 — 无(默认)、内容为自主创作、内容为转载、
        内容由AI生成、内容为虚构演绎。
        空值或「无」视为不设置(微博默认就是「无」)。
        """
        if not statement or statement.strip() == "无":
            return

        # trigger 是「内容声明」文本节点,click 冒泡到父级 woo-pop-ctrl
        # 但父级 <span class="woo-pop-ctrl"> 在 actionability 检查里
        # 会被判为「intercept pointer events」(2026-06-17 实测:50+ 次
        # retry → 页面上下弹),必须 force=True 跳过这个检查。
        trigger = page.get_by_text("内容声明", exact=True).first
        try:
            await trigger.wait_for(state="visible", timeout=5000)
        except Exception as e:
            logger.warning("[weibo] 未找到内容声明入口: %s", e)
            return

        await trigger.click(force=True)
        await asyncio.sleep(0.5)

        # 弹窗里的选项是 button,文本就是选项值
        option = page.get_by_role("button", name=statement.strip(), exact=True).first
        try:
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            logger.info("[weibo] 已选内容声明: %s", statement)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(
                "[weibo] 选择内容声明失败(%s): %s", statement, e,
            )
            # ESC 关闭弹出的内容声明面板
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

    # ------------------------------------------------------------------
    # Helper: click 发布 button
    # ------------------------------------------------------------------

    @staticmethod
    async def _click_publish(page):
        """点击页面右下角「发布」按钮。

        初始 disabled,表单填好后启用。用 role+name 定位避免 class 哈希漂移。
        """
        # get_by_role 只匹配可访问性树里的元素,hidden 元素(如未来 toast 的
        # 「再发一条视频」按钮)默认被排除,所以 .first 就是当前可见的发布按钮
        publish_btn = page.get_by_role("button", name="发布", exact=True).first
        try:
            await publish_btn.wait_for(state="visible", timeout=10000)
        except Exception as e:
            raise RuntimeError(f"[weibo] 未找到发布按钮: {e}")

        # 轮询 disabled 属性(最长 60s)
        for _ in range(60):
            disabled = await publish_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[weibo] 发布按钮一直 disabled,表单未就绪")

        await publish_btn.click()
        logger.info("[weibo] 已点击发布按钮")

    # ------------------------------------------------------------------
    # Helper: wait for publish success signal
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_publish_success(page, timeout_s: int = 60):
        """等待发布完成的信号。

        微博点发布后会显示 toast:「视频已上传成功,将在转码后发布」,
        或 URL 变化到视频管理页。两者满足其一即视为成功。
        """
        try:
            # 优先等 toast 文案
            await page.locator(
                "text=视频已上传成功"
            ).first.wait_for(state="visible", timeout=timeout_s * 1000)
            logger.info("[weibo] 发布成功(检测到「视频已上传成功」toast)")
        except Exception:
            # 兜底: 看 URL 是否跳走
            await asyncio.sleep(3)
            current = page.url
            if "weibo.com/upload/channel" not in current:
                logger.info("[weibo] 发布成功(URL 已跳转: %s)", current)
            else:
                raise RuntimeError(
                    f"[weibo] 发布后未检测到成功信号,当前 URL: {current}"
                )
