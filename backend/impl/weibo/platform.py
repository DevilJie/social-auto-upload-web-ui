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

                # 等待视频真正上传完成(类型 radio 可见 = 表单可交互)
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
        """上传视频主文件 — 用 patched click 拦截动态 file input。

        核心思路:patch ``HTMLInputElement.prototype.click``。微博前端
        button click handler 必然要调 ``input.click()`` 才能打开 file picker
        (用户才能选文件),所以我们在 file input 被 ``.click()`` 时:
          1. 打上 ``data-weibo-upload='1'`` 标记
          2. 强制 append 到 body(若尚未连接),保证 Playwright 找得到
          3. **不调** 原始 click(不开 file picker)

        然后用 Playwright ``set_input_files`` 走 CDP 直接设文件,自动触发
        ``change`` 事件,微博前端 change handler 启动上传,上传完成后 UI
        自动切换到表单(类型 radio 可见)。

        为什么不用之前方案:
        - ``dispatchEvent click``:合成事件 Chrome 不开 picker
        - ``page.on('filechooser')`` / ``expect_file_chooser``:CloakBrowser
          屏蔽 filechooser 事件,30s 超时
        - click 后等 input 数量增加:动态 input 可能瞬时存在/不在 DOM,不可靠

        流程:
        1. patch ``HTMLInputElement.click``(idempotent,只 patch 一次)
        2. click ``button[id^='video_button_upload']``(普通 Playwright click)
        3. 等带标记的 file input 出现(最多 30s)
        4. ``set_input_files`` 走 CDP 设文件 + 触发 change 事件
        5. ``_wait_for_upload_form`` 等表单切换(类型 radio 可见)
        """
        file_size = os.path.getsize(file_path)
        logger.info(
            "[weibo] 准备上传视频: %s (%.1f MB)",
            os.path.basename(file_path), file_size / 1024 / 1024,
        )

        # 1. Patch HTMLInputElement.prototype.click
        #    关键三件事:
        #    a) 给 file input 打 data-weibo-upload='1' 标记
        #    b) 若 input 未连接 DOM,强制 append 到 body 并隐藏
        #       (Playwright locator 只能查 DOM,detached 元素查不到)
        #    c) 不调 origClick(不开 file picker,稍后走 set_input_files)
        patch_status = await page.evaluate(r"""() => {
            if (window.__weiboClickPatched) return 'already-patched';
            window.__weiboClickPatched = true;
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') {
                    try {
                        this.setAttribute('data-weibo-upload', '1');
                        if (!this.isConnected) {
                            this.style.display = 'none';
                            document.body.appendChild(this);
                        }
                    } catch (e) {
                        /* noop — 标记失败时不影响后续 set_input_files 兜底 */
                    }
                } else {
                    return origClick.apply(this, arguments);
                }
            };
            return 'patched';
        }""")
        logger.info("[weibo] click patch status: %s", patch_status)

        # 2. 找上传按钮
        upload_btn = page.locator("button[id^='video_button_upload']").first
        if await upload_btn.count() == 0:
            upload_btn = page.get_by_role(
                "button", name="上传视频", exact=True,
            ).first
        if await upload_btn.count() == 0:
            raise RuntimeError("[weibo] 未找到「上传视频」按钮")

        await upload_btn.wait_for(state="visible", timeout=10000)

        # 3. 点击按钮(普通 Playwright click,模拟真实用户)
        await upload_btn.click()
        logger.info("[weibo] 已点击「上传视频」按钮")

        # 4. 等带标记的 file input 出现
        marked_sel = "input[type='file'][data-weibo-upload='1']"
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            try:
                count = await page.locator(marked_sel).count()
            except Exception as e:
                logger.warning("[weibo] locator count 异常: %s", e)
                count = 0
            if count > 0:
                break
            await asyncio.sleep(0.5)
        else:
            all_count = await page.locator("input[type='file']").count()
            raise RuntimeError(
                "[weibo] 30s 内未检测到带标记的 file input。"
                f"当前 input[type=file] 数量: {all_count}。"
                "可能原因: button click handler 没调 input.click(),"
                "或 patch 被覆盖(检查 window.__weiboClickPatched)。"
            )

        # 5. set_input_files 走 CDP 设文件 + 触发 change 事件
        file_input = page.locator(marked_sel).first
        await file_input.set_input_files(file_path)
        logger.info(
            "[weibo] 视频文件已通过 patched input 提交: %s",
            os.path.basename(file_path),
        )

    # ------------------------------------------------------------------
    # Helper: wait for upload to finish and the form to appear
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_upload_form(page, timeout_s: int = 3600):
        """等待视频上传完成、表单可交互。

        **权威锚点**: 类型 radio「原创」可见且可点(2026-06-16 前一直用这个,
        验证可用)。早期版本用 textarea (placeholder 含「有什么新鲜事」)
        作为锚点,但 textarea 在微博页面**初始就渲染**,上传过程中也可见,
        不能代表上传完成。类型 radio 才是上传完成后才完全可交互的元素。

        上传未完成之前,所有后续表单设置操作(_set_video_type /
        _set_title / _set_cover / _set_category / _set_description /
        _set_content_statement / _click_publish) 全部阻塞在此函数,
        等 radio 可见才继续。

        **超时默认 60 分钟**(3600s):大视频 + 慢网络上 100MB 视频需要
        10~30min,留足余量。
        """
        radio = page.get_by_role("radio", name="原创", exact=True).first
        deadline = asyncio.get_event_loop().time() + timeout_s

        while asyncio.get_event_loop().time() < deadline:
            # 1. 类型 radio 可见 → 表单 ready
            try:
                if await radio.is_visible():
                    logger.info("[weibo] 类型 radio 可见,上传完成、表单可交互")
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
                uploading = await page.get_by_text("上传中", exact=True).count()
                done = await page.get_by_text("上传完成", exact=True).count()
                remaining = int(deadline - asyncio.get_event_loop().time())
                if remaining % 60 < 5 or remaining < 60:
                    logger.info(
                        "[weibo] 等待上传完成... 上传中=%d 上传完成=%d "
                        "(剩余 %ds)",
                        uploading, done, remaining,
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
            f"{timeout_s // 60}min),类型 radio 始终不可见。"
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
    # Helper: upload cover (click 上传封面 → ESC → hidden file input → 完成)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_cover(
        page,
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
    ):
        """上传封面。

        流程(spec):
        1. 点击「上传封面」链接(spec 说这会自动打开系统原生文件选择器)
        2. 立即按 ESC 关闭原生选择器
        3. 等待「编辑封面」弹层出现,找到 ``input[type=file]._file_1mhd8_65``
        4. set_input_files 上传图片
        5. 点击「完成」按钮

        优先使用横版封面;若只传了竖版,用竖版。
        """
        cover_path = thumbnail_landscape_path or thumbnail_portrait_path
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
        await asyncio.sleep(0.3)
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
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
        # spec: <input type="file" class="_file_1mhd8_65" accept=".jpg, .jpeg, ...">
        # 该弹层里有两个 file input,取第一个可用的
        file_inputs = page.locator("input[type='file'][accept*='jpg']")
        count = await file_inputs.count()
        if not count:
            logger.warning("[weibo] 封面弹层未找到 input[type=file]")
            return
        await file_inputs.first.set_input_files(cover_path)
        logger.info("[weibo] 已上传封面文件: %s", os.path.basename(cover_path))
        await asyncio.sleep(2)

        # 5. 点击「完成」按钮 (封面编辑弹层右下角)
        # 用 role+name 定位,避免 class 哈希漂移
        done_btn = page.get_by_role("button", name="完成", exact=True).first
        try:
            await done_btn.wait_for(state="visible", timeout=5000)
            await done_btn.click()
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
        # 注意: click 事件会冒泡,直接点文本即可触发父级 trigger 的 click handler
        trigger_text = page.get_by_text("请选择合适的频道", exact=True)
        try:
            await trigger_text.first.wait_for(state="visible", timeout=10000)
        except Exception as e:
            logger.warning("[weibo] 未找到分类下拉触发器(占位文本): %s", e)
            return

        # 1. 点开下拉(点文本即可,click 冒泡到父级)
        await trigger_text.first.click()
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
        trigger = page.get_by_text("内容声明", exact=True).first
        try:
            await trigger.wait_for(state="visible", timeout=5000)
        except Exception as e:
            logger.warning("[weibo] 未找到内容声明入口: %s", e)
            return

        await trigger.click()
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
