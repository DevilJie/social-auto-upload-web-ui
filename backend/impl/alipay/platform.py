"""支付宝内容创作平台 (Alipay Creator Center) — CloakBrowser 实现。

platform_id = 12
platform_key = "alipay"
platform_name = "支付宝"

关键 URL:
- 创作中心首页(登录/资料抓取): https://c.alipay.com/page/life-account/index
- 视频发布页:                   https://c.alipay.com/page/content-creation/publish/short-video

文档 ``~/zfb.md`` 的强约束:**尽量不要用 CLASS 定位元素**(antd5 + CSS modules
hash 类名会随构建漂移)。本实现优先用 placeholder / role / text / aria /
``label[title]`` 定位,不得已时才用 ``[class*="xxx"]`` 前缀匹配。

发布页表单结构(2026-06-22 抓取):
- 标题:    ``input[placeholder*="好的标题"]`` (≤30 字)
- 描述:    ``textarea.mentions-textarea__input[placeholder*="作品描述"]``
- 话题:    描述区输入 ``#xxx`` → ``.mentions-textarea__suggestions__list`` 弹联想
- 封面:    点击"上传封面"区 → tab 切到"上传封面" → 隐藏 input[type=file] → "完成"
- 合集:    ``input[placeholder*="请选择要加入到的合集"]`` 搜索 → 等
           ``[role="option"]`` 渲染 → 点击 title 匹配项
- 作者声明(必填): ``input#*_tagList`` 父级 antd5-select → ``[role="option"]``
           → 点 title=statement
- 定时发布: ``input[name="publishType"][value="regularly"]`` → antd5-picker 选日期时间
- 发布按钮: ``button`` 文本"确认发布"
"""

import asyncio
import os
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import bind_account_name, get_channel_logger

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    get_account_name_by_cookie_file,
    save_login_result,
    scrape_alipay_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("alipay")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALIPAY_CREATOR_URL = "https://c.alipay.com/page/life-account/index"
_ALIPAY_PUBLISH_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-video"
)
# 图集(图文)发布页 — 与视频页 short-video 独立,文档 ~/ZFB-tuji.md
_ALIPAY_SHORT_CONTENT_URL = (
    "https://c.alipay.com/page/content-creation/publish/short-content"
)


# ======================================================================
# AlipayPlatform
# ======================================================================

class AlipayPlatform(BasePlatform):
    platform_id = 12
    platform_key = "alipay"
    platform_name = "支付宝"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """支付宝扫码登录流程。

        1. 打开创作中心首页 ``c.alipay.com/page/life-account/index``
        2. 用户自行完成登录(扫码/账密)
        3. 登录后页面渲染账号信息(``accountContainer`` 区块出现昵称 + 头像)
        4. ``save_login_result`` 走统一后登录流程(scrape + cookie + DB + SSE)

        无超时:用户可能耗时较长。浏览器关闭由 ``login_mode=True`` 处理。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_ALIPAY_CREATOR_URL)

                # 等待账号信息容器出现(昵称节点) — 登录完成的标志
                # 用 [class*="accountContainer"] 前缀匹配,避免完整 hash 漂移
                await page.locator(
                    'div[class*="accountContainer"] div[class*="name"]'
                ).first.wait_for(timeout=999999999)
                logger.info("[alipay] 登录成功(检测到账号信息容器)")

                # 等渲染稳定
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
                await asyncio.sleep(2)

                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_alipay_profile,
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
        """检查 cookie 是否仍然有效。

        判据:用 cookie 打开生活号首页,如果没有跳转到登录页面即视为有效;
        cookie 失效会被重定向到登录页(URL 中含 login/passport/authorize 等)。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            return False

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_ALIPAY_CREATOR_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=15000)

                final_url = page.url
                # 仍停留在生活号首页(没被重定向) → cookie 有效
                valid = "c.alipay.com/page/life-account/index" in final_url
                logger.info(
                    f"[alipay] cookie {'有效' if valid else '失效,需重新登录'} "
                    f"(final_url={final_url})"
                )
                return valid
            except Exception as exc:
                logger.info(f"[alipay] cookie 检查异常: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center()
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """打开支付宝创作中心首页(可见浏览器,线程内同步 API)。"""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _ALIPAY_CREATOR_URL

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
        """同步昵称 + 头像。"""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _ALIPAY_CREATOR_URL

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                return await scrape_alipay_profile(page)
            except Exception as e:
                logger.info(f"[alipay] 同步资料失败: {e}")
                return "", ""
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # publish_video -- sync entry point
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """支付宝视频发布(sync wrapper)。

        Accepted keyword arguments:

        - ``title`` (*str*)        — 标题(≤30 字)
        - ``files`` (*list[str]*)  — 视频绝对路径
        - ``tags`` (*list[str]*)   — 话题(描述区以 #xxx 触发联想)
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` (*str*)
        - ``desc`` (*str*)         — 描述
        - ``author_statement`` (*str*) — 作者声明(必填,6 选 1)
        - ``compilation`` (*str*)  — 合集名称(可选,精确匹配)
        - ``enableTimer`` (*bool*) / ``schedule_time_str`` (*str*) — 定时发布
        """
        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal: orchestrate all file × account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """文件 × 账号 笛卡尔积,每个组合一个 browser。"""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始支付宝视频发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        thumbnail_landscape_path = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait_path = kwargs.get("thumbnail_portrait_path")
        video_format = kwargs.get("video_format", "") or ""
        desc = kwargs.get("desc", "") or ""
        author_statement = kwargs.get("author_statement", "") or ""
        compilation = kwargs.get("compilation", "") or ""
        enable_timer = kwargs.get("enableTimer")
        schedule_time_str = kwargs.get("schedule_time_str", "") or ""

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 视频格式: %s", video_format or "未指定")
        logger.info("[发布参数] 作者声明: %s", author_statement or "无")
        logger.info("[发布参数] 合集: %s", compilation or "无")
        logger.info("[发布策略] 发布策略: %s", "scheduled" if enable_timer and schedule_time_str else "immediate")

        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        file_paths = [str(f) for f in files]
        if thumbnail_landscape_path:
            thumbnail_landscape_path = str(thumbnail_landscape_path)
        if thumbnail_portrait_path:
            thumbnail_portrait_path = str(thumbnail_portrait_path)

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
                        account_file=cookie_path,
                        thumbnail_landscape_path=thumbnail_landscape_path,
                        thumbnail_portrait_path=thumbnail_portrait_path,
                        video_format=video_format,
                        desc=desc,
                        author_statement=author_statement,
                        compilation=compilation,
                        enable_timer=enable_timer,
                        schedule_time_str=schedule_time_str,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Image (图集) publishing — 图文发布页 short-content
    # 文档 ~/ZFB-tuji.md
    # ------------------------------------------------------------------

    def publish_image(self, **kwargs) -> bool:
        """支付宝图集发布(sync wrapper)。

        Accepted keyword arguments:

        - ``title`` (*str*)        — 标题(≤30 字)
        - ``files`` (*list[str]*)  — 图片绝对路径列表(多图)
        - ``tags`` (*list[str]*)   — 话题
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``desc`` (*str*)         — 描述
        - ``author_statement`` (*str*) — 作者声明(默认「内容由AI生成」)
        - ``music_title`` (*str*)  — 选中的音乐名(可选)
        - ``music_id`` (*str*)     — 选中的音乐 id(可选,保留)
        """
        asyncio.run(self._upload_all_images(**kwargs))
        return True

    async def _upload_all_images(self, **kwargs):
        """图片集 × 账号 笛卡尔积,每个组合一个 browser。"""
        logger.info("=" * 60)
        logger.info("[发布图集] 开始支付宝图集发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        desc = kwargs.get("desc", "") or ""
        # 图集作者声明下拉只有「内容由AI生成」一个选项,空则兜底填它
        author_statement = (
            kwargs.get("author_statement", "")
            or kwargs.get("author_declaration", "")
            or "内容由AI生成"
        )
        music_title = kwargs.get("music_title", "") or ""

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 图片数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 作者声明: %s", author_statement or "无")
        logger.info("[发布参数] 音乐: %s", music_title or "无")

        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        file_paths = [str(f) for f in files]

        for cookie_index, cookie_path in enumerate(account_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                await self._upload_one_image_set(
                    title=title,
                    file_paths=file_paths,
                    tags=tags,
                    account_file=cookie_path,
                    desc=desc,
                    author_statement=author_statement,
                    music_title=music_title,
                )

        logger.info("=" * 60)
        logger.info("[发布图集] 图集发布流程完成!")
        logger.info("=" * 60)

    async def _upload_one_image_set(
        self,
        title: str,
        file_paths: list,
        tags: list,
        account_file: str,
        desc: str = "",
        author_statement: str = "内容由AI生成",
        music_title: str = "",
    ):
        """一组图片上传到单个账号的完整流程。"""
        logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_paths))
        logger.info("[上传图集] 标题: %s", title)
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
                await page.goto(_ALIPAY_SHORT_CONTENT_URL, timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                logger.info("[上传图集] 正在上传图片: %s", title)

                # 1. 上传图片(多图)
                await self._upload_images(page, file_paths)

                # 2. 等待表单可交互(标题输入框可见)
                await self._wait_for_image_form(page)

                # 3. 填标题
                await self._set_title(page, title)

                # 4. 填描述 + 话题
                await self._set_description_and_tags(page, desc, title, tags)

                # 5. 音乐(可选)
                if music_title:
                    await self._set_music(page, music_title)

                # 6. 作者声明(必填,默认「内容由AI生成」)
                await self._set_author_statement(page, author_statement)

                # 7. 点击「确认发布」
                await self._click_publish(page)

                # 8. 等待发布成功(图集走 short-content 跳转判据)
                await self._wait_for_publish_success(page, page_type="image")

                # 9. 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[上传图集] cookie 已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # Helper (image): upload multiple images via hidden input[type=file]
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_images(page, image_paths: list):
        """逐张上传图片 — 图集页 input[type=file][accept*='image']。

        支付宝图集上传区 DOM(文档 ~/ZFB-tuji.md):
          <input type="file" accept="image/jpeg,image/png" multiple
                 style="display: none;">

        上传接口: https://mass.alipay.com/file/auth/upload
        成功响应: {"code":0,"data":{"id":"A*PACJSqMSxtMAAAAAgBAAAAgAfah3AQ"}}
        失败响应: code != 0

        失败时 DOM 出现:
          <div class="ant-upload-list-item ant-upload-list-item-error">
            <span class="ant-upload-list-item-name" title="xxx.png">xxx.png</span>
            <button title="删除文件">...</button>
          </div>

        流程:
        1. 找到图片上传 input
        2. 逐张上传:
           a. 监听上传接口响应
           b. set_input_files 单张图片
           c. 等待上传完成(响应返回 或 错误 DOM 出现)
           d. 如果失败 → 删除失败项 → 重试(最多 3 次)
        """
        valid_paths = [p for p in image_paths if p and os.path.exists(p)]
        if not valid_paths:
            raise RuntimeError(
                "[上传图集] 无有效图片文件 "
                f"(传入 {len(image_paths)} 个)"
            )

        total_size = sum(os.path.getsize(p) for p in valid_paths)
        logger.info(
            "[上传图集] 准备逐张上传 %d 张图片(共 %.1f MB)",
            len(valid_paths), total_size / 1024 / 1024,
        )

        # 找到图片上传 input
        image_input = page.locator(
            "input[type='file'][accept*='image']"
        ).first
        try:
            await image_input.wait_for(state="attached", timeout=15000)
        except Exception:
            # 兜底:找任意非 video 的 file input
            all_inputs = page.locator("input[type='file']")
            cnt = await all_inputs.count()
            for i in range(cnt):
                fi = all_inputs.nth(i)
                accept_val = (await fi.get_attribute("accept") or "").lower()
                if "video" not in accept_val:
                    image_input = fi
                    break

        # 逐张上传
        uploaded_count = 0
        for idx, img_path in enumerate(valid_paths):
            max_retries = 3
            for attempt in range(max_retries):
                img_name = os.path.basename(img_path)
                logger.info(
                    "[上传图集] 上传图片 %d/%d: %s (尝试 %d/%d)",
                    idx + 1, len(valid_paths), img_name, attempt + 1, max_retries,
                )

                # 使用可变对象存储响应,避免闭包问题
                upload_result = {"response": None}
                async def handle_upload_response(response):
                    if "mass.alipay.com/file/auth/upload" in response.url:
                        try:
                            data = await response.json()
                            upload_result["response"] = data
                        except Exception:
                            pass

                page.on("response", handle_upload_response)

                try:
                    # 上传单张图片
                    await image_input.set_input_files(img_path)
                    await asyncio.sleep(0.5)  # 等待上传开始

                    # 等待上传完成(响应返回 或 错误 DOM)
                    for _ in range(100):  # 最多等 10s
                        if upload_result["response"] is not None:
                            break
                        # 检查是否出现错误 DOM
                        error_item = page.locator(
                            f'.ant-upload-list-item-error:has-text("{img_name}")'
                        ).first
                        if await error_item.count() > 0:
                            upload_result["response"] = {"code": -1, "error": "DOM error"}
                            break
                        await asyncio.sleep(0.1)

                    upload_response = upload_result["response"]
                    if upload_response is None:
                        logger.warning("[上传图集] 上传超时: %s", img_name)
                        continue

                    if upload_response.get("code") == 0:
                        logger.info(
                            "[上传图集] 上传成功: %s (id=%s)",
                            img_name, upload_response.get("data", {}).get("id", ""),
                        )
                        uploaded_count += 1
                        # 等待上传完成后再继续下一张
                        await asyncio.sleep(1)
                        break  # 成功,跳出重试循环
                    else:
                        logger.warning(
                            "[上传图集] 上传失败: %s (code=%s)",
                            img_name, upload_response.get("code"),
                        )
                        # 删除失败项
                        try:
                            delete_btn = page.locator(
                                f'.ant-upload-list-item-error:has-text("{img_name}") '
                                'button[title="删除文件"]'
                            ).first
                            if await delete_btn.count() > 0:
                                await delete_btn.click()
                                logger.info("[上传图集] 已删除失败项: %s", img_name)
                                await asyncio.sleep(0.5)
                        except Exception as e:
                            logger.warning("[上传图集] 删除失败项异常: %s", e)

                except Exception as e:
                    logger.warning("[上传图集] 上传异常: %s - %s", img_name, e)
                finally:
                    try:
                        page.remove_listener("response", handle_upload_response)
                    except Exception:
                        pass

        logger.info(
            "[上传图集] 图片上传完成: %d/%d 成功",
            uploaded_count, len(valid_paths),
        )
        if uploaded_count == 0:
            raise RuntimeError("[上传图集] 所有图片上传均失败")

    # ------------------------------------------------------------------
    # Helper (image): wait for form interactive
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_image_form(page, timeout_s: int = 120):
        """等待图集表单可交互(标题输入框可见)。

        图集页无需像视频页那样等大文件上传,判据简化为:
        标题输入框 ``input[placeholder*='好的标题']`` 可见。
        默认超时 120s(图集上传 + 处理通常很快,留余量)。
        """
        title_input = page.locator(
            "input[placeholder*='好的标题']"
        ).first
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await title_input.is_visible():
                    logger.info("[上传图集] 表单已可交互(标题输入框可见)")
                    return
            except Exception:
                pass
            await asyncio.sleep(3)
        raise RuntimeError(
            f"[上传图集] 等待表单就绪超时({timeout_s}s)"
        )

    # ------------------------------------------------------------------
    # Helper (image): select music (添加音乐 → hover → 使用)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_music(page, music_title: str):
        """选择背景音乐(文档 ~/ZFB-tuji.md 行 14-22)。

        支付宝音乐选择组件**没有搜索功能**，是分页显示(每页5首)。
        因此需要**逐页翻页查找**目标音乐，直到找到或没有更多页。

        流程:
        1. 点「添加音乐」button.ant-btn 打开「选择音乐」modal
        2. 等 antd5-modal「选择音乐」打开
        3. 循环:当前页查找 → 找到则点击使用 → 未找到则点下一页
        4. 等 modal 关闭

        支付宝音乐项 DOM:
          <div class="...group" ...>
            <img alt="{音乐名}" ...>
            <div title="{音乐名}" ...>...</div>
            <button class="...opacity-0 group-hover:opacity-100" style="visibility:hidden;">
              <span>使 用</span>
            </button>
          </div>

        分页 DOM:
          <ul class="antd5-pagination">
            <li title="Next Page" class="antd5-pagination-next">...</li>
          </ul>
        """
        if not music_title:
            return

        # 1. 点「添加音乐」
        try:
            add_music_btn = page.locator(
                "button.ant-btn:has-text('添加音乐')"
            ).first
            await add_music_btn.wait_for(state="visible", timeout=10000)
            await add_music_btn.click()
            logger.info("[上传图集] 已点击「添加音乐」,等待 modal")
            await asyncio.sleep(1.5)
        except Exception as e:
            logger.warning("[上传图集] 未找到「添加音乐」按钮: %s", e)
            return

        # 2. 等 modal 打开
        try:
            music_modal = page.locator(
                'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")'
            ).first
            await music_modal.wait_for(state="visible", timeout=10000)
        except Exception as e:
            logger.warning("[上传图集] 音乐 modal 未打开: %s", e)
            return

        # 3. 逐页翻页查找目标音乐
        max_pages = 20  # 安全上限,防止死循环
        found = False

        for page_num in range(1, max_pages + 1):
            logger.info("[上传图集] 音乐查找: 第 %d 页,目标「%s」", page_num, music_title)

            # 在当前页查找目标音乐
            clicked = await page.evaluate(
                """(name) => {
                    const modal = document.querySelector(
                        'div.antd5-modal[aria-modal="true"]'
                    );
                    if (!modal) return 'no-modal';
                    // 音乐项容器:每项是一个 div(含 img + title div + 使用 button)
                    const items = modal.querySelectorAll('div[class*="group"]');
                    const target = Array.from(items).find(el => {
                        const t = el.querySelector('div[title]');
                        const img = el.querySelector('img[alt]');
                        const tn = t ? t.getAttribute('title') : '';
                        const an = img ? img.getAttribute('alt') : '';
                        return tn === name || an === name
                            || (tn && tn.includes(name))
                            || (an && an.includes(name));
                    });
                    if (!target) return 'not-found';
                    // 触发 hover(group-hover:opacity-100)
                    target.dispatchEvent(
                        new MouseEvent('mouseenter', {bubbles: true})
                    );
                    target.dispatchEvent(
                        new MouseEvent('mouseover', {bubbles: true})
                    );
                    // 找「使用」按钮(button > span 文本「使 用」中间有空格)
                    const btns = target.querySelectorAll('button');
                    for (const b of btns) {
                        const txt = (b.textContent || '').replace(/\\s/g, '');
                        if (txt === '使用') {
                            b.style.visibility = 'visible';
                            b.style.opacity = '1';
                            b.click();
                            return 'clicked';
                        }
                    }
                    return 'no-btn';
                }""",
                music_title,
            )

            if clicked == "clicked":
                logger.info("[上传图集] 已选音乐: %s (第 %d 页)", music_title, page_num)
                found = True
                break
            elif clicked != "not-found":
                logger.warning("[上传图集] 音乐查找异常: %s", clicked)
                break

            # 当前页未找到,尝试翻到下一页
            try:
                next_btn = page.locator(
                    'li.antd5-pagination-next:not([aria-disabled="true"]):not(.antd5-pagination-disabled)'
                ).first
                # 检查下一页按钮是否可用
                next_count = await next_btn.count()
                if next_count == 0:
                    logger.info("[上传图集] 音乐「%s」未找到,已无更多页(共 %d 页)", music_title, page_num)
                    break

                await next_btn.click()
                logger.info("[上传图集] 翻到第 %d 页", page_num + 1)
                await asyncio.sleep(1.0)  # 等待下一页加载
            except Exception as e:
                logger.info("[上传图集] 翻页失败(可能已到最后一页): %s", e)
                break

        if not found:
            logger.warning("[上传图集] 未找到音乐「%s」,跳过音乐设置", music_title)
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return

        # 4. 等 modal 关闭(最多 8s)
        try:
            await page.locator(
                'div.antd5-modal[aria-modal="true"]:has-text("选择音乐")'
            ).wait_for(state="hidden", timeout=8000)
            logger.info("[上传图集] 音乐 modal 已关闭")
        except Exception:
            # 兜底:Esc 强关
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
        await asyncio.sleep(0.5)

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
        video_format: str = "",
        desc: str = "",
        author_statement: str = "",
        compilation: str = "",
        enable_timer=None,
        schedule_time_str: str = "",
    ):
        """单个视频上传到单个账号的完整流程。"""
        # 打印完整上送参数,便于排查(与其他渠道日志风格一致)
        logger.info(
            "[上传视频] ===== 上送参数 =====\n"
            "  title=%r\n"
            "  file_path=%r\n"
            "  tags=%r\n"
            "  account_file=%r\n"
            "  desc=%r\n"
            "  thumbnail_landscape=%r\n"
            "  thumbnail_portrait=%r\n"
            "  video_format=%r\n"
            "  author_statement=%r\n"
            "  compilation=%r\n"
            "  enable_timer=%r\n"
            "  schedule_time_str=%r\n"
            "========================",
            title, file_path, tags,
            os.path.basename(account_file),
            desc,
            thumbnail_landscape_path,
            thumbnail_portrait_path,
            video_format,
            author_statement,
            compilation,
            enable_timer,
            schedule_time_str,
        )
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
                await page.goto(_ALIPAY_PUBLISH_URL, timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)
                logger.info("[上传视频] 正在上传-------%s", title)

                # 1. 上传视频文件
                await self._upload_video_file(page, file_path)

                # 2. 等待上传完成 + 表单渲染
                await self._wait_for_upload_form(page)

                # 3. 填标题
                await self._set_title(page, title)

                # 4. 填描述 + 话题
                await self._set_description_and_tags(page, desc, title, tags)

                # 5. 上传封面(按视频格式选择对应封面)
                #    竖版视频(portrait)→竖版封面;横版视频(landscape)→横版封面
                #    未指定格式时横版优先兜底
                if video_format == "portrait":
                    cover_path = (
                        thumbnail_portrait_path or thumbnail_landscape_path
                    )
                elif video_format == "landscape":
                    cover_path = (
                        thumbnail_landscape_path or thumbnail_portrait_path
                    )
                else:
                    cover_path = (
                        thumbnail_landscape_path or thumbnail_portrait_path
                    )
                logger.info(
                    "[上传视频] 封面选择: 格式=%s → %s",
                    video_format or "未指定",
                    os.path.basename(cover_path) if cover_path else "无",
                )
                await self._set_cover(page, cover_path)

                # 6. 合集(可选)
                if compilation:
                    await self._set_compilation(page, compilation)

                # 7. 作者声明(必填)
                await self._set_author_statement(page, author_statement)

                # 8. 定时发布(可选)
                if enable_timer and schedule_time_str:
                    await self._set_schedule_time(page, schedule_time_str)

                # 9. 点击"确认发布"
                await self._click_publish(page)

                # 10. 等待发布成功
                await self._wait_for_publish_success(page)

                # 11. 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[上传视频] cookie 已更新")
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
        """上传视频主文件 — 多重兜底(参考微博实现)。

        策略:
        1. 直接 set_input_files 命中 video file input
        2. 失败则 patch click/dispatchEvent/showPicker + MutationObserver
        3. 兜底 expect_file_chooser + 点击上传区
        """
        file_size = os.path.getsize(file_path)
        logger.info(
            "[上传视频] 准备上传视频: %s (%.1f MB)",
            os.path.basename(file_path), file_size / 1024 / 1024,
        )

        # 0. 安装 MutationObserver + patch(与微博同款)
        await page.evaluate(r"""() => {
            if (window.__alipayObserverInstalled) return;
            window.__alipayObserverInstalled = true;
            window.__alipayInitialInputCount =
                document.querySelectorAll('input[type="file"]').length;
            const observer = new MutationObserver(() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > window.__alipayInitialInputCount) {
                    for (let i = window.__alipayInitialInputCount;
                         i < inputs.length; i++) {
                        inputs[i].setAttribute('data-alipay-new', '1');
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }""")

        await page.evaluate(r"""() => {
            if (window.__alipayAllPatched) return;
            window.__alipayAllPatched = true;
            const markInput = function (input) {
                try {
                    input.setAttribute('data-alipay-upload', '1');
                    if (!input.isConnected) {
                        input.style.display = 'none';
                        document.body.appendChild(input);
                    }
                } catch (e) {}
            };
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') markInput(this);
                else return origClick.apply(this, arguments);
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
                    if (this && this.type === 'file') markInput(this);
                    else return origShow.apply(this, arguments);
                };
            }
        }""")

        # 1. 优先直接 set_input_files(支付宝上传区有隐藏 input[type=file])
        target_input_sel = "input[type='file']"
        try:
            target_input = page.locator(target_input_sel).first
            await target_input.wait_for(state="attached", timeout=15000)
            await target_input.set_input_files(file_path)
            logger.info("[上传视频] 已通过 set_input_files 提交视频")
            return
        except Exception as e:
            logger.info("[上传视频] 直接 set_input_files 失败: %s", e)

        # 2. 兜底: expect_file_chooser + 点击上传区
        try:
            upload_area = page.get_by_text("将视频文件拖拽到此处").first
            if await upload_area.count() == 0:
                upload_area = page.locator(
                    "input[type='file'][accept*='video']"
                ).first
            async with page.expect_file_chooser(timeout=10000) as fc_info:
                await upload_area.click(force=True)
            fc = await fc_info.value
            await fc.set_files(file_path)
            logger.info("[上传视频] 已通过 expect_file_chooser 提交视频")
            return
        except Exception as e:
            logger.info("[上传视频] expect_file_chooser 失败: %s", e)

        # 3. 最后兜底: 等带标记 input 出现
        marked_sel = (
            "input[type='file'][data-alipay-upload='1'],"
            "input[type='file'][data-alipay-new='1']"
        )
        deadline = asyncio.get_event_loop().time() + 30
        while asyncio.get_event_loop().time() < deadline:
            try:
                count = await page.locator(marked_sel).count()
                if count > 0:
                    await page.locator(marked_sel).first.set_input_files(file_path)
                    logger.info("[上传视频] 已通过 patched input 提交视频")
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)

        all_count = await page.locator("input[type='file']").count()
        raise RuntimeError(
            f"[上传视频] 30s 内未找到可用的 file input "
            f"(input[type=file] 总数: {all_count})"
        )

    # ------------------------------------------------------------------
    # Helper: wait for upload to finish and the form to appear
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_upload_form(page, timeout_s: int = 14400):
        """等待视频上传完成、表单可交互。

        判据(OR):
        1. 标题输入框 ``input[placeholder*="好的标题"]`` 可见
        2. URL 跳转到带表单的发布详情页

        默认超时 4 小时,大文件 + 慢网络留足余量。
        """
        title_input = page.locator(
            "input[placeholder*='好的标题']"
        ).first
        deadline = asyncio.get_event_loop().time() + timeout_s

        while asyncio.get_event_loop().time() < deadline:
            try:
                # 上传失败检测
                if await page.get_by_text("上传失败", exact=True).count() > 0:
                    raise RuntimeError(
                        "[上传视频] 视频上传失败(页面检测到「上传失败」文本)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

            try:
                if await title_input.is_visible():
                    logger.info(
                        "[上传视频] 标题输入框已可见,上传完成、表单可交互"
                    )
                    return
            except Exception:
                pass

            # 进度旁证(每 60s 一次)
            try:
                remaining = int(deadline - asyncio.get_event_loop().time())
                if remaining % 60 < 5:
                    logger.info(
                        "[上传视频] 等待上传完成... (剩余 %ds)", remaining,
                    )
            except Exception:
                pass

            await asyncio.sleep(5)

        try:
            url = page.url
        except Exception:
            url = "(unknown)"
        raise RuntimeError(
            f"[上传视频] 等待视频上传完成超时({timeout_s}s),"
            f"标题输入框未出现。当前 URL: {url}"
        )

    # ------------------------------------------------------------------
    # Helper: fill title
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_title(page, title: str):
        """填标题(≤30 字)。placeholder: "一个好的标题,能获得更多人的喜欢哦"."""
        if not title:
            return
        title_input = page.locator(
            "input[placeholder*='好的标题']"
        ).first
        await title_input.wait_for(state="visible", timeout=10000)
        truncated = title.strip()[:30]
        await title_input.fill(truncated)
        logger.info("[上传视频] 已填标题: %s", truncated)

    # ------------------------------------------------------------------
    # Helper: fill description + tags
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_description_and_tags(
        page, desc: str, title: str, tags: list
    ):
        """填描述 + 话题。

        描述 placeholder: "填写作品描述,让你的作品更容易被看到"
        话题: 在描述区输入 ``#xxx`` → 等联想下拉 → 点第一项(或自定义话题项)

        DOM(文档行 15):
        ``ul.mentions-textarea__suggestions__list > li.mentions-textarea__suggestions__item``
        每个 li 内有 ``<div>#xxx</div><div>N次浏览</div>``,最后一项是"自定义话题"
        """
        textarea = page.locator(
            "textarea.mentions-textarea__input"
        ).first
        await textarea.wait_for(state="visible", timeout=10000)

        # 先填描述正文(不含 #话题,话题单独走联想)
        text = (desc or title or "").strip()
        if text:
            await textarea.click()
            await asyncio.sleep(0.2)
            await page.keyboard.type(text, delay=30)
            await page.keyboard.press("Space")
            logger.info("[上传视频] 已填描述(长度=%d)", len(text))
            await asyncio.sleep(0.3)

        # 话题逐一粘贴 #话题名 到描述区,然后输入空格确认。
        #
        # 支付宝话题交互:
        #   直接打 `#xxx` 逐字符输入时,联想接口可能拿不到话题词,
        #   下拉一直是默认热门推荐。改用 insert_text(模拟粘贴)一次性
        #   注入 `#话题名`,再输一个空格触发话题成型。
        for tag in (tags or []):
            tag = (tag or "").strip().lstrip("#")
            if not tag:
                continue
            try:
                logger.info("[上传视频] 开始添加话题 #%s", tag)
                await textarea.click()
                await asyncio.sleep(0.2)
                # 先键盘输入 # 触发 mention 插件的联想下拉
                await page.keyboard.type("#", delay=50)
                await asyncio.sleep(0.3)
                # 再用 Ctrl+V 粘贴话题名,触发真正的 paste 事件
                await page.evaluate(
                    "text => navigator.clipboard.writeText(text)",
                    tag,
                )
                await asyncio.sleep(0.1)
                await page.keyboard.press("Control+v")
                logger.info("[上传视频] 已输入#并Ctrl+V粘贴 %s,等待联想下拉...", tag)
                await asyncio.sleep(0.8)
                # 检查下拉是否出现
                suggestion_list = page.locator(
                    ".mentions-textarea__suggestions__list"
                ).first
                dropdown_visible = await suggestion_list.is_visible()
                if dropdown_visible:
                    # 下拉出现了,尝试精确匹配官方话题
                    items = suggestion_list.locator(
                        ".mentions-textarea__suggestions__item"
                    )
                    count = await items.count()
                    logger.info("[上传视频] 话题 #%s 联想下拉共 %d 项", tag, count)
                    matched = False
                    for i in range(count):
                        item = items.nth(i)
                        label_text = await item.locator(
                            "div > div:first-child"
                        ).first.text_content()
                        sub_text = await item.locator(
                            "div > div:nth-child(2)"
                        ).first.text_content()
                        label = (label_text or "").strip()
                        logger.info(
                            "[上传视频]   候选[%d] 话题=%s 标记=%s",
                            i, label, (sub_text or "").strip(),
                        )
                        if label == f"#{tag}" or label == tag:
                            await item.click()
                            matched = True
                            logger.info(
                                "[上传视频] 已选话题(官方精确): #%s", tag,
                            )
                            break
                    if not matched:
                        # 没有精确匹配,输入空格确认为自定义话题
                        await page.keyboard.press("Space")
                        logger.info("[上传视频] 已选话题(自定义): #%s", tag)
                else:
                    # 下拉没出现,直接输空格确认
                    await page.keyboard.press("Space")
                    logger.info("[上传视频] 已添加话题(无下拉,空格确认): #%s", tag)
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning("[上传视频] 添加话题 #%s 失败: %s", tag, e)
                try:
                    await page.keyboard.press("Escape")
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # Helper: upload cover
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_cover(page, cover_path):
        """上传封面。

        流程(文档 ~/zfb.md 行 17-27):
        1. 点击"上传封面"区域(打开封面设置弹窗)
        2. 在弹窗里切换到"上传封面" tab(默认在"截取封面")
           DOM: ``div.antd5-tabs-tab > div.antd5-tabs-tab-btn`` 文本="上传封面"
        3. 切换后 panel 渲染隐藏 input[type=file][accept*='image'] 上传横版封面
        4. 点击"完 成"按钮(文档实测按钮文本中间有空格,
           data-aspm-desc="封面图选择-确认")
        """
        if not cover_path or not os.path.exists(cover_path):
            logger.info("[上传视频] 无封面文件,跳过封面上传")
            return

        # 1. 点击"上传封面"触发入口(页面上的封面区,非 tab)
        #    DOM: div.z-10 文本="上传封面"(主表单的封面入口)
        upload_trigger = page.locator(
            "div.z-10", has_text="上传封面"
        ).first
        try:
            await upload_trigger.wait_for(state="visible", timeout=10000)
        except Exception:
            # 兜底:用文本定位(可能命中多个,取第一个可见的)
            upload_trigger = page.get_by_text("上传封面", exact=True).first
            try:
                await upload_trigger.wait_for(state="visible", timeout=5000)
            except Exception as e:
                logger.warning("[上传视频] 未找到「上传封面」入口: %s", e)
                return

        await upload_trigger.click()
        await asyncio.sleep(1.5)
        logger.info("[上传视频] 已点击「上传封面」入口,等待弹窗")

        # 2. 切换到"上传封面" tab(弹窗默认在"截取封面")
        #    DOM: div.antd5-tabs-tab > div.antd5-tabs-tab-btn(文本="上传封面")
        #    get_by_role("tab") 在 antd5 里常匹配不到,用文本+class 定位
        tab_switched = False
        try:
            upload_tab = page.locator(
                "div.antd5-tabs-tab-btn", has_text="上传封面"
            ).first
            await upload_tab.wait_for(state="visible", timeout=10000)
            await upload_tab.click()
            await asyncio.sleep(1)
            tab_switched = True
            logger.info("[上传视频] 已切换到「上传封面」tab")
        except Exception as e:
            logger.info("[上传视频] 切换「上传封面」tab 跳过(可能已在目标 tab): %s", e)

        # 3. 上传封面文件 —— 用 file_chooser 兜底 + set_input_files 双保险
        #    支付宝封面 input 的 accept 属性实测不含 "image" 字样,
        #    input[type='file'][accept*='image'] 选择器会失败(见后端日志)。
        #    改用三重策略,任一成功即可:
        #    ① 直接找任意 input[type=file] 尝试 set_input_files
        #    ② 监听 file_chooser + 点击上传区
        #    ③ JS 标记 + 等待 patched input
        uploaded = False

        # 策略 ①: 当前页面所有 input[type=file],过滤掉视频那个,
        #          找封面的(通常是第 2 个或 accept 不同的)
        try:
            all_file_inputs = page.locator("input[type='file']")
            fi_count = await all_file_inputs.count()
            logger.info("[上传视频] 当前 input[type=file] 数量: %d", fi_count)
            for i in range(fi_count):
                fi = all_file_inputs.nth(i)
                accept_val = await fi.get_attribute("accept") or ""
                # 跳过视频专用的 input
                if "video" in accept_val.lower():
                    continue
                # 这个 input 可能就是封面的(图片/空 accept)
                await fi.set_input_files(cover_path)
                logger.info(
                    "[上传视频] 已上传封面(策略① input #%d, accept=%r): %s",
                    i, accept_val, os.path.basename(cover_path),
                )
                uploaded = True
                break
        except Exception as e:
            logger.info("[上传视频] 策略① set_input_files 失败: %s", e)

        # 策略 ②: 监听原生 file_chooser + 点击上传触发区
        if not uploaded:
            try:
                # 上传触发区:tab 切换后的 panel 里通常有"点击上传"/拖拽区
                trigger = page.locator(
                    "div.antd5-tabs-tabpane-active "
                    "div[class*='upload'],"
                    "div.antd5-tabs-tabpane-active "
                    "[class*='dragger'],"
                    "div.antd5-tabs-tabpane-active "
                    "[class*='Upload']"
                ).first
                async with page.expect_file_chooser(timeout=8000) as fc_info:
                    await trigger.click(force=True)
                fc = await fc_info.value
                await fc.set_files(cover_path)
                uploaded = True
                logger.info(
                    "[上传视频] 已上传封面(策略② file_chooser): %s",
                    os.path.basename(cover_path),
                )
            except Exception as e:
                logger.info("[上传视频] 策略② file_chooser 失败: %s", e)

        if not uploaded:
            logger.warning("[上传视频] 封面上传所有策略均失败,跳过封面")
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass
            return

        # 等图片处理(上传 + 预览渲染 + 裁剪器就绪)
        await asyncio.sleep(3)

        # 4. 点击"完 成"按钮(文档实测文本中间有空格,data-aspm-desc=封面图选择-确认)
        #    优先用 data-aspm-desc 精确定位,兜底用文本
        done_btn = page.locator(
            'button[data-aspm-desc="封面图选择-确认"]'
        ).first
        try:
            await done_btn.wait_for(state="visible", timeout=10000)
        except Exception:
            # 兜底:文本匹配(antd5 button 内是 <span>完 成</span>)
            done_btn = page.locator(
                "button.antd5-btn-primary", has_text="完"
            ).first
        try:
            await done_btn.wait_for(state="visible", timeout=10000)
            await done_btn.click(force=True)
            logger.info("[上传视频] 已点击封面「完 成」按钮")
        except Exception as e:
            logger.warning("[上传视频] 点击封面确认按钮失败: %s", e)

        await asyncio.sleep(1)

    # ------------------------------------------------------------------
    # Helper: set compilation (合集,搜索下拉)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_compilation(page, compilation_name: str):
        """选择合集(发布流程的执行端)。

        前端 ``CompilationSelect`` 已经在发布前通过
        ``/api/alipay/compilation-search`` 预览过合集列表,用户选中的合集
        **以名字(title)** 传过来(与抖音 MixSelect 存 mix_name 一致,
        便于在草稿箱/发布历史里人读)。

        参数 compilation_name: 合集名字(前端 v-model 绑的是 comp.title)

        流程(文档 ~/zfb.md):
        1. 定位合集 select 搜索框 ``input[id$='_compilationInfo']``
        2. fill compilation_name 触发 queryCompilationsByPublicId.json
           (用 page.expect_response 同步等待,确保列表已返回)
        3. 等 ``[role="option"]`` 渲染
        4. 按 title 精确匹配 → title 模糊包含 → 兜底放弃

        本方法与 ``alipay_bp.search_compilation`` 共享同一个支付宝接口,
        但职责不同:bp 是"搜索预览",这里是"真实点选"。
        """
        if not compilation_name:
            return

        compilation_input = page.locator(
            "input[id$='_compilationInfo']"
        ).first
        try:
            await compilation_input.wait_for(
                state="visible", timeout=10000
            )
        except Exception as e:
            logger.warning("[上传视频] 未找到合集输入框: %s", e)
            return

        # 监听 queryCompilationsByPublicId.json + fill 触发搜索
        try:
            async with page.expect_response(
                lambda r: "queryCompilationsByPublicId.json" in r.url,
                timeout=10000,
            ):
                await compilation_input.click()
                await compilation_input.fill(compilation_name)
                logger.info(
                    "[上传视频] 已输入合集名「%s」,等待接口响应",
                    compilation_name,
                )
        except Exception as e:
            logger.info(
                "[上传视频] 未捕获到 queryCompilationsByPublicId 响应(%s),"
                "直接等 DOM 渲染",
                e,
            )

        # 等 option 渲染
        try:
            await page.locator(
                "div.antd5-select-item-option"
            ).first.wait_for(state="visible", timeout=10000)
        except Exception as e:
            logger.warning(
                "[上传视频] 合集下拉未渲染(可能无匹配合集「%s」): %s",
                compilation_name, e,
            )
            return

        # 合集 option 实测 DOM(~/zfb.md 用户反馈):
        #   <div class="antd5-select-item-option">
        #     <div class="antd5-select-item-option-content">
        #       <div class="collectionItem___xxx"><span>一键分发系统</span><span>1</span></div>
        #     </div>
        #   </div>
        # 注意:option 没有 title 属性!文字在 collectionItem > span:first-child
        # 用 JS 遍历所有 option,按 collectionItem 内首个 span 文本匹配后点击
        clicked = await page.evaluate(
            """(name) => {
                const options = document.querySelectorAll(
                    'div.antd5-select-item-option'
                );
                // ① 精确匹配
                for (const opt of options) {
                    const span = opt.querySelector(
                        'div[class*="collectionItem"] span:first-child'
                    );
                    if (span && span.textContent.trim() === name) {
                        opt.click();
                        return 'exact';
                    }
                }
                // ② 模糊包含
                for (const opt of options) {
                    const span = opt.querySelector(
                        'div[class*="collectionItem"] span:first-child'
                    );
                    if (span && span.textContent.includes(name)) {
                        opt.click();
                        return 'fuzzy:' + span.textContent.trim();
                    }
                }
                return '';
            }""",
            compilation_name,
        )
        if clicked:
            logger.info(
                "[上传视频] 已选合集(%s): %s",
                "精确" if clicked == "exact" else "模糊",
                compilation_name if clicked == "exact" else clicked,
            )
        else:
            logger.warning(
                "[上传视频] 未找到匹配的合集「%s」,跳过合集设置",
                compilation_name,
            )
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

        await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # Helper: set author statement (作者声明,必填)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_author_statement(page, statement: str):
        """选择作者声明(必填,文档 ~/zfb.md 行 76-81)。

        6 个选项:内容无需标注 / 个人观点,仅供参考 / 内容由AI生成 /
        内容虚构演绎,仅供娱乐 / 内容含营销信息 / 内容为转载

        DOM(2026-06-24 实测):
        - 搜索 input: ``input[id$='_tagList']`` (ID 有随机前缀,后缀稳定)
          属性: role=combobox, readonly, aria-required=true
        - select 容器: input 的祖先中 role=combobox 或含 arrow 的 div
        - option: ``[role='option'][title="内容由AI生成"]`` (title 稳定)

        **禁止用 class 定位**(antd5 + CSS modules hash 会漂移)。

        流程:
        1. 通过 input[id$='_tagList'] 定位搜索框
        2. 点其父级展开下拉
        3. 点 [role='option'][title="..."] 精确匹配
        """
        if not statement:
            logger.warning(
                "[上传视频] 作者声明为空,支付宝要求必填,后续发布可能失败"
            )
            return

        # 1. 通过 input[id$='_tagList'] 定位搜索框(input 有 role=combobox)
        search_input = page.locator(
            "input[id$='_tagList'][role='combobox']"
        ).first
        try:
            await search_input.wait_for(state="visible", timeout=10000)
        except Exception as e:
            logger.warning("[上传视频] 未找到作者声明搜索框: %s", e)
            return

        # 2. 点搜索框展开下拉(它 readonly,点击会冒泡到父级 select 触发展开)
        try:
            await search_input.click()
            await asyncio.sleep(0.8)
            logger.info("[上传视频] 已点击作者声明搜索框,等待下拉")
        except Exception as e:
            logger.warning("[上传视频] 点击作者声明搜索框失败: %s", e)
            return

        # 3. 等 option 渲染,点 title 精确匹配项
        #    选项 DOM: <div aria-selected="false" title="内容由AI生成">...</div>
        #    没有 role='option',只用 title 属性定位(稳定,不依赖 class)
        target_opt = page.locator(
            f"[title='{statement.strip()}']"
        ).first
        try:
            await target_opt.wait_for(state="visible", timeout=10000)
            await target_opt.click()
            logger.info("[上传视频] 已选作者声明: %s", statement)
            await asyncio.sleep(0.5)
            return
        except Exception as e:
            logger.warning(
                "[上传视频] 未找到作者声明选项「%s」: %s", statement, e
            )

        # 兜底:列出所有带 title 的下拉项辅助排查
        try:
            titles = await page.evaluate("""() => {
                const holder = document.querySelector(".rc-virtual-list-holder-inner");
                if (!holder) return [];
                return Array.from(holder.children)
                    .map(o => o.getAttribute('title'))
                    .filter(Boolean);
            }""")
            logger.info("[上传视频] 当前下拉可选项: %s", titles)
        except Exception:
            pass

        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Helper: set schedule time (定时发布)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_schedule_time(page, schedule_time_str: str):
        """设置定时发布(文档行 67-74)。

        流程:
        1. 点击"定时发布" radio(``input[name="publishType"][value="regularly"]``)
        2. 等日期时间选择器出现
        3. 直接填 ``input#*_scheduleTime``(antd5-picker 的输入框)
        4. 点"确定"按钮关闭 picker

        antd5-picker 的原生日历点选很脆,这里优先用直接 fill input 的方式
        (picker 的输入框支持手输 ``YYYY-MM-DD HH:MM``)。
        """
        # 解析时间字符串 → "YYYY-MM-DD HH:MM"
        dt = _parse_schedule_dt(schedule_time_str)
        if not dt:
            logger.warning(
                "[上传视频] 无法解析定时时间「%s」,跳过定时设置",
                schedule_time_str,
            )
            return
        time_str = dt.strftime("%Y-%m-%d %H:%M")

        # 1. 切换到"定时发布" radio
        try:
            regularly_radio = page.locator(
                'input[name="publishType"][value="regularly"]'
            ).first
            await regularly_radio.wait_for(state="attached", timeout=10000)
            # radio 可能在 label 内,用 click label 父级
            label = regularly_radio.locator("xpath=ancestor::label[1]")
            await label.click(force=True)
            logger.info("[上传视频] 已切换到「定时发布」")
            await asyncio.sleep(0.8)
        except Exception as e:
            logger.warning("[上传视频] 切换定时发布失败: %s", e)
            return

        # 2. 直接填 picker 输入框
        schedule_input = page.locator(
            "input[id$='_scheduleTime']"
        ).first
        try:
            await schedule_input.wait_for(state="visible", timeout=10000)
            await schedule_input.click()
            await asyncio.sleep(0.3)
            # 清空再填
            await schedule_input.fill("")
            await schedule_input.type(time_str, delay=50)
            await asyncio.sleep(0.5)
            logger.info("[上传视频] 已填定时时间: %s", time_str)
        except Exception as e:
            logger.warning("[上传视频] 填定时时间失败: %s", e)
            return

        # 3. 点"确定"按钮关闭 picker
        try:
            ok_btn = page.get_by_role("button", name="确 定", exact=True).first
            if await ok_btn.count() > 0:
                await ok_btn.click()
                logger.info("[上传视频] 已点击 picker「确定」")
                await asyncio.sleep(0.5)
        except Exception as e:
            logger.info("[上传视频] 点击 picker 确定失败(可能已关): %s", e)
            try:
                await page.keyboard.press("Enter")
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Helper: click publish button
    # ------------------------------------------------------------------

    @staticmethod
    async def _click_publish(page):
        """点击「确认发布」按钮(文档行 11 末尾)。"""
        publish_btn = page.get_by_role(
            "button", name="确认发布", exact=True
        ).first
        try:
            await publish_btn.wait_for(state="visible", timeout=15000)
        except Exception as e:
            raise RuntimeError(f"[上传视频] 未找到「确认发布」按钮: {e}")

        # 轮询 disabled(最长 60s),等表单就绪
        for _ in range(60):
            disabled = await publish_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError(
                "[上传视频] 「确认发布」按钮一直 disabled,表单未就绪"
                "(检查作者声明等必填项)"
            )

        await publish_btn.click()
        logger.info("[上传视频] 已点击「确认发布」按钮")

    # ------------------------------------------------------------------
    # Helper: wait for publish success signal
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_publish_success(page, timeout_s: int = 90, page_type: str = "video"):
        """等待发布完成信号,并处理两种弹窗。

        点完「确认发布」后,支付宝可能弹出两种弹窗:

        1. 「发布请注意」优化提示弹窗(antd5-modal)
           - ``返回更换``(antd5-btn-primary) — 中止
           - ``继续发布``(antd5-btn-default) — 跳过提示继续发布

        2. 「发布请注意」确认弹窗(ant-modal-confirm)
           - DOM: div.ant-modal.ant-modal-confirm
           - ``取 消``(ant-btn-default)
           - ``确认发布``(ant-btn-primary) — 点这个继续

        成功判据(OR):
        1. URL 跳转离开当前发布页(最可靠)
        2. 检测到"发布成功"文案

        90s 内任一成功判据命中即视为成功。
        """
        publish_path = (
            "publish/short-content" if page_type == "image"
            else "publish/short-video"
        )
        deadline = asyncio.get_event_loop().time() + timeout_s
        original_url = page.url
        modal_handled = False

        while asyncio.get_event_loop().time() < deadline:
            # ---- 弹窗 1:「发布请注意」优化提示弹窗(antd5-modal) ----
            if not modal_handled:
                try:
                    modal = page.locator(
                        'div.antd5-modal[aria-modal="true"]:has-text("发布请注意")'
                    )
                    if await modal.count() > 0 and await modal.first.is_visible():
                        logger.info(
                            "[上传视频] 检测到「发布请注意」优化提示弹窗,"
                            "尝试点击「继续发布」"
                        )
                        # 点「继续发布」按钮(antd5-btn-default,非 primary)
                        continue_btn = modal.locator(
                            "button.antd5-btn-default:has-text('继续发布')"
                        ).first
                        await continue_btn.click()
                        modal_handled = True
                        logger.info("[上传视频] 已点击「继续发布」,等待跳转")
                        await asyncio.sleep(1)
                        continue
                except Exception as e:
                    logger.debug("[上传视频] 检测弹窗1异常(忽略): %s", e)

            # ---- 弹窗 2:「发布请注意」确认弹窗(ant-modal-confirm) ----
            if not modal_handled:
                try:
                    confirm_modal = page.locator(
                        'div.ant-modal.ant-modal-confirm:has-text("发布请注意")'
                    )
                    if await confirm_modal.count() > 0 and await confirm_modal.first.is_visible():
                        logger.info(
                            "[上传视频] 检测到「发布请注意」确认弹窗,"
                            "尝试点击「确认发布」"
                        )
                        # 点「确认发布」按钮(ant-btn-primary)
                        confirm_btn = confirm_modal.locator(
                            "button.ant-btn-primary:has-text('确认发布')"
                        ).first
                        await confirm_btn.click()
                        modal_handled = True
                        logger.info("[上传视频] 已点击弹窗「确认发布」,等待跳转")
                        await asyncio.sleep(1)
                        continue
                except Exception as e:
                    logger.debug("[上传视频] 检测弹窗2异常(忽略): %s", e)

            # ---- 成功判据 1: URL 跳转离开发布页(最可靠) ----
            try:
                current_url = page.url
                if (
                    current_url != original_url
                    and publish_path not in current_url
                ):
                    logger.info("[上传视频] 发布成功(URL 已跳转: %s)", current_url)
                    return
            except Exception:
                pass

            # ---- 成功判据 2: 「发布成功」文案 ----
            try:
                if await page.get_by_text("发布成功", exact=True).count() > 0:
                    logger.info("[上传视频] 发布成功(检测到「发布成功」文案)")
                    return
            except Exception:
                pass

            await asyncio.sleep(2)

        raise RuntimeError(
            f"[上传视频] 等待发布完成超时({timeout_s}s),"
            f"是否处理过弹窗: {modal_handled}"
        )


# ---------------------------------------------------------------------------
# Schedule time parser (轻量版,仅解析为 datetime)
# ---------------------------------------------------------------------------

def _parse_schedule_dt(schedule_time_str: str):
    """解析前端传入的时间字符串为 datetime(本地时区)。

    兼容:
    - ISO UTC: ``2026-06-22T13:00:00.000Z`` / ``2026-06-22T13:00:00+08:00``
    - 本地: ``2026-06-22 13:00:00`` / ``2026-06-22 13:00`` / ``2026-06-22T13:00``
    """
    from datetime import timedelta

    if not schedule_time_str:
        return None
    try:
        raw = str(schedule_time_str)
        is_utc = raw.endswith("Z") or "+00:00" in raw
        raw_clean = raw.replace("+08:00", "").replace("+00:00", "")

        for fmt in (
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ):
            try:
                dt = datetime.strptime(raw_clean, fmt)
                if is_utc:
                    dt = dt + timedelta(hours=8)
                return dt
            except ValueError:
                continue
    except Exception as e:
        logger.info("[上传视频] 解析定时时间失败: %s", e)
    return None
