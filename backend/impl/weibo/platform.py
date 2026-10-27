"""Weibo platform implementation — CloakBrowser."""

import asyncio
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._manual_review import manual_review_enabled, wait_for_manual_publish
from .._utils import (
    clear_and_type,
    get_account_name_by_cookie_file,
    raise_if_page_closed,
    save_login_result,
    scrape_weibo_profile,
)
from ..base_platform import BasePlatform
from util._logger import bind_account_name, get_channel_logger

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

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    platform_cookie_domain = ".weibo.com"

    def _parse_cookie_to_storage_state(self, cookie_str):
        cookies = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair: continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(), "value": value.strip(),
                "domain": self.platform_cookie_domain, "path": "/",
                "expires": expires, "httpOnly": True, "secure": False, "sameSite": "Lax",
            })
        return cookies, []

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
                    # 登录成功后在同一个 session 内补抓 stats(粉丝/关注/转评赞),
                    # 与 sync_profile 共用同一份抓取逻辑
                    stats_fn=self._login_stats_fn,
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

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步微博昵称、头像、运营数据(stats)。

        抓取流程:
        1. 访问 weibo.com 首页,点击右上角头像 → 跳转到个人主页 weibo.com/u/<id>
        2. 在个人主页抓 name/avatar/stats(粉丝/关注/转评赞)

        与 login 路径(使用 scrape_weibo_profile)独立,stats 不在原 scraper 里,
        这里新实现抓取。从个人主页一个 DOM 一次抓全 3 项 stats + 昵称头像。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                # 1. 访问微博首页
                await page.goto("https://weibo.com/", wait_until="domcontentloaded", timeout=20000)
                try:
                    await page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                await asyncio.sleep(1)

                # 2. 点击右上角用户头像 → 跳转到个人主页
                try:
                    avatar_btn = page.locator('.woo-badge-box img').first
                    await avatar_btn.wait_for(state="visible", timeout=8000)
                    await avatar_btn.click()
                    # 等跳转到 /u/<id>
                    await page.wait_for_url("**/u/**", timeout=10000)
                except Exception as exc:
                    logger.info(f"[weibo] 点击头像跳转个人主页失败: {exc}")

                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=10000)
                except Exception:
                    pass
                await asyncio.sleep(1)

                # 3. 抓 name/avatar/stats(都在同一个 ._h3_/._h4_ 区块附近)
                result = await page.evaluate(
                    '''() => {
                        const out = {name: '', avatar: '', stats: []};
                        // 头像:.woo-avatar-img
                        const av = document.querySelector('.woo-avatar-img');
                        if (av) out.avatar = av.getAttribute('src') || '';
                        // 昵称:._name_1yc79_291(后端 hash 改了,用 [class*="_name_"] 兜底)
                        const nameEl = document.querySelector('[class*="_name_"]');
                        if (nameEl) out.name = (nameEl.textContent || '').trim();
                        // stats:3 个 _h5_ span,分别是 粉丝 / 关注 / 转评赞
                        document.querySelectorAll('[class*="_h5_"]').forEach(el => {
                            const numEl = el.querySelector('span');
                            const text = (el.textContent || '').trim();
                            if (!numEl) return;
                            const num = (numEl.textContent || '').trim();
                            // label 在 num 之后的文本里(例如 "2粉丝" 或 "粉丝 2")
                            // 简单规则:含"粉丝"→粉丝;含"关注"→关注;含"转评赞"→转评赞
                            if (text.includes('粉丝')) {
                                out.stats.push({name: '粉丝', num});
                            } else if (text.includes('转评赞')) {
                                out.stats.push({name: '转评赞', num});
                            } else if (text.includes('关注')) {
                                out.stats.push({name: '关注', num});
                            }
                        });
                        return out;
                    }'''
                )
                name = (result or {}).get('name', '')
                avatar = (result or {}).get('avatar', '')
                stats_raw = (result or {}).get('stats', [])

                # 组装 stats JSON
                stats = []
                label_map = {
                    "粉丝":   ("user",   1, "粉丝"),
                    "关注":   ("follow", 2, "关注"),
                    "转评赞": ("like",   3, "转评赞"),
                }
                for item in stats_raw:
                    label = item.get('name', '')
                    num = item.get('num', '0')
                    if label in label_map:
                        icon, sort_no, std_name = label_map[label]
                        try:
                            count = int(str(num).replace(',', '').replace(' ', '') or '0')
                        except (ValueError, TypeError):
                            count = 0
                        stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})

                if not name and not avatar and not stats:
                    logger.info(f"[weibo] sync_profile 抓取为空,url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:
                logger.info(f"[weibo] sync profile failed: {e}")
                return {"name": "", "avatar": "", "stats": []}
            finally:
                await context.close()
        finally:
            await browser.close()

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口(供 save_login_result 调用)。

        与 sync_profile 内部共用同一套 js evaluate 抓取逻辑。
        """
        try:
            await asyncio.sleep(1)
            result = await page.evaluate(
                '''() => {
                    const out = [];
                    document.querySelectorAll('[class*="_h5_"]').forEach(el => {
                        const numEl = el.querySelector('span');
                        const text = (el.textContent || '').trim();
                        if (!numEl) return;
                        const num = (numEl.textContent || '').trim();
                        if (text.includes('粉丝')) out.push({name:'粉丝', num});
                        else if (text.includes('转评赞')) out.push({name:'转评赞', num});
                        else if (text.includes('关注')) out.push({name:'关注', num});
                    });
                    return out;
                }'''
            )
            label_map = {
                "粉丝":   ("user",   1, "粉丝"),
                "关注":   ("follow", 2, "关注"),
                "转评赞": ("like",   3, "转评赞"),
            }
            stats = []
            for item in (result or []):
                label = item.get('name', '')
                num = item.get('num', '0')
                if label in label_map:
                    icon, sort_no, std_name = label_map[label]
                    try:
                        count = int(str(num).replace(',', '').replace(' ', '') or '0')
                    except (ValueError, TypeError):
                        count = 0
                    stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
            return stats
        except Exception as exc:
            logger.info(f"[weibo login] _login_stats_fn 抓取失败: {exc}")
            return [] 

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
            logger.info("[发布图集] dry-run 模式, 跳过实际发布 (publish_image)")
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
        logger.info("=" * 60)
        logger.info("[发布图集] 开始微博图集发布流程")
        logger.info("=" * 60)

        # 打印所有接收到的参数
        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        files = kwargs.get("files", []) or []
        account_file = kwargs.get("account_file", []) or []
        title = kwargs.get("title", "")
        tags = kwargs.get("tags", []) or []
        desc = kwargs.get("desc", "") or ""
        ai_content = kwargs.get("ai_content", "") or ""
        content_statement = kwargs.get("content_statement", "") or ""
        content_statement2 = kwargs.get("content_statement2", "") or ""
        content_statement2_optional = kwargs.get("content_statement2_optional", "") or ""
        # 忽略字段(微博图集不支持)
        # is_original / enableTimer / schedule_time_str / cover_path
        _ = kwargs.get("is_original")  # noqa
        _ = kwargs.get("enableTimer")  # noqa
        _ = kwargs.get("schedule_time_str")  # noqa
        _ = kwargs.get("cover_path")  # noqa

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 图片数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 类型声明: %s", ai_content or "无")

        # 入口校验:微博图集服务端硬上限 18 张
        if len(files) > 18:
            raise ValueError(
                f"[发布图集] 图集最多 18 张,当前 {len(files)} 张"
            )

        file_path_list = [str(f) for f in files]
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]

        # 单层账号循环(不是笛卡尔积!)
        for cookie_index, cookie_path in enumerate(account_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info("[发布进度] 发布到第 %d/%d 个账号 (%s)", cookie_index + 1, len(account_paths), nick or "未知")
                await self._upload_one_image(
                    title=title,
                    file_path_list=file_path_list,
                    tags=tags,
                    account_file=cookie_path,
                    desc=desc,
                    ai_content=ai_content,
                    content_statement=content_statement,
                    content_statement2=content_statement2,
                    content_statement2_optional=content_statement2_optional,
                )

        logger.info("=" * 60)
        logger.info("[发布图集] 图集发布流程完成!")
        logger.info("=" * 60)

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
        content_statement: str = "",
        content_statement2: str = "",
        content_statement2_optional: str = "",
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
        logger.info("[上传图集] 开始上传图集 (%d 张图片)", len(file_path_list))
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
                        f"[发布图集] 创作卡片未渲染(cookie 失效/未登录?): {e}"
                    )
                await asyncio.sleep(2)  # 等图片工具/声明 trigger 完全渲染

                # 1. 上传图片
                logger.info("[上传图集] 开始上传图片...")
                await self._upload_images(page, file_path_list)

                # 2. 填正文 + 标签
                logger.info("[填写简介] 开始填写微博正文...")
                await self._set_description(page, desc, title, tags)

                # 3. 内容声明 (复用 video 版,自动探测版本1/版本2 UI)
                # 版本1:优先用 content_statement(前端下拉),为空时回退到
                # ai_content(兼容旧图集流程把类型声明当内容声明用的历史行为)
                v1_stmt = content_statement or ai_content
                logger.info(
                    "[内容声明] 开始设置内容声明: 版本1=%s, 版本2必选=%s, 版本2可选=%s",
                    v1_stmt or "无", content_statement2 or "无", content_statement2_optional or "无",
                )
                await self._set_content_statement(
                    page, v1_stmt, content_statement2, content_statement2_optional
                )

                # 4. 发送
                if manual_review_enabled('weibo', 'image'):
                    # 人工验收：保留表单，等待用户亲自点击「发送」
                    async def _manual_image_success(page):
                        # 与自动分支判据一致：textarea 清空或「发送」重新 disabled
                        try:
                            if await page.locator(
                                "textarea[placeholder*='有什么新鲜事']"
                            ).first.input_value() == "":
                                return True
                        except Exception:
                            pass
                        try:
                            return await page.get_by_role(
                                "button", name="发送", exact=True
                            ).first.get_attribute("disabled") is not None
                        except Exception:
                            return False
                    await wait_for_manual_publish(
                        page, 'weibo', success_check=_manual_image_success
                    )
                else:
                    logger.info("[发布] 正在点击发送按钮...")
                    await self._click_send(page)

                # 5. 等成功信号
                await self._wait_for_image_publish_success(page)
                logger.info("[发布] 图集发布成功!")

                # 6. 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

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
            logger.warning("[上传图集] 无图片可上传")
            return

        logger.info("[上传图集] 准备上传 %d 张图片", len(files))

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
        logger.info("[发布] img patch status: %s", patch_status)

        # 2. 找「图片」trigger
        # selector:文本 "图片" 在 woo-pop-wrap 内,且 sibling 包含 image upload input
        img_trigger = page.get_by_text("图片", exact=True).first
        if await img_trigger.count() == 0:
            raise RuntimeError("[发布] 未找到「图片」工具图标")

        # 3. 优先直接 set_input_files(接受 hidden input)
        target_input_sel = (
            "input[type='file'][accept^='image/'][multiple]"
        )
        try:
            target_input = page.locator(target_input_sel).first
            await target_input.wait_for(state="attached", timeout=10000)
            await target_input.set_input_files(files)
            logger.info("[发布] 已通过 set_input_files 提交 %d 张图", len(files))
        except Exception as e:
            logger.info("[发布] 直接 set_input_files 失败: %s", e)

            # 兜底 1: expect_file_chooser + 点击 trigger
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await img_trigger.click(force=True)
                fc = await fc_info.value
                await fc.set_files(files)
                logger.info("[发布] 已通过 expect_file_chooser 提交")
            except Exception as e2:
                logger.info("[发布] expect_file_chooser 失败: %s", e2)
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
                    logger.info("[发布] 已通过 patched input 提交")
                else:
                    raise RuntimeError(
                        f"[发布] 30s 内未找到可用的 file input"
                    )

        # 4. 等待上传完成 — 轮询「发送」按钮 enabled(最稳判定)
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        deadline = asyncio.get_event_loop().time() + 300  # 5 分钟
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page)
            try:
                disabled = await send_btn.get_attribute("disabled")
                if disabled is None:
                    logger.info("[发布] 图片已上传,发送按钮已启用")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)

        raise RuntimeError("[发布] 5 分钟内图片未上传完成(发送按钮未启用)")

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
            raise RuntimeError(f"[发布] 未找到「发送」按钮: {e}")

        # 轮询 disabled(最长 60s)
        for _ in range(60):
            disabled = await send_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[发布] 「发送」按钮一直 disabled,表单未就绪")

        await send_btn.click()
        logger.info("[发布] 已点击「发送」按钮")

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
            raise_if_page_closed(page)
            try:
                # 条件 1: textarea 清空
                textarea_empty = await textarea.input_value() == ""
                # 条件 2: 发送按钮重新 disabled
                disabled = await send_btn.get_attribute("disabled")
                send_disabled = disabled is not None
                if textarea_empty or send_disabled:
                    logger.info("[发布] 图集发布成功(textarea 空=%s, send 禁用=%s)",
                                textarea_empty, send_disabled)
                    return
            except Exception:
                pass
            await asyncio.sleep(2)

        raise RuntimeError(
            f"[发布] 等待图集发布完成超时({timeout_s}s)"
        )

    # ------------------------------------------------------------------
    # Internal: orchestrate all file × account uploads
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """Create a browser per file+account combo and upload."""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始微博视频发布流程")
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
        # 16:9 / 9:16 封面(微博封面框实际比例,优先于 4:3 / 3:4 使用)
        thumbnail_landscape_169_path = kwargs.get("thumbnail_landscape_169_path")
        thumbnail_portrait_916_path = kwargs.get("thumbnail_portrait_916_path")
        desc = kwargs.get("desc", "") or ""
        category = kwargs.get("category")
        ai_content = kwargs.get("ai_content", "") or ""
        content_statement = kwargs.get("content_statement", "") or ""
        content_statement2 = kwargs.get("content_statement2", "") or ""
        content_statement2_optional = kwargs.get("content_statement2_optional", "") or ""
        weibo_collection = kwargs.get("weibo_collection", "") or ""

        # 打印发布参数摘要
        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 视频简介: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape_path or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait_path or "无")
        logger.info("[发布参数] 分类: %s", category or "无")
        logger.info("[发布参数] 类型声明: %s", ai_content or "无")
        logger.info("[发布参数] 内容声明: %s", content_statement or "无")
        logger.info("[发布参数] 微博合集: %s", weibo_collection or "无")
        logger.info("[发布策略] 发布策略: immediate")

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
                        thumbnail_landscape_169_path=thumbnail_landscape_169_path,
                        thumbnail_portrait_916_path=thumbnail_portrait_916_path,
                        desc=desc,
                        category=category,
                        ai_content=ai_content,
                        content_statement=content_statement,
                        content_statement2=content_statement2,
                        content_statement2_optional=content_statement2_optional,
                        weibo_collection=weibo_collection,
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

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
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
        desc="",
        category=None,
        ai_content="",
        content_statement="",
        content_statement2="",
        content_statement2_optional="",
        weibo_collection="",
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
                logger.info("[上传视频] 开始上传视频: %s", title)

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
                            "[上传视频] ▲ 请求 #%d %s %s",
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
                            "[上传视频] ▼ 响应 #%d status=%d body=%s",
                            upload_resp_count["n"], response.status,
                            body_preview,
                        )

                page.on("request", _on_upload_request)
                page.on("response", _on_upload_response)

                # 上传视频文件
                logger.info("[上传视频] 正在上传视频文件...")
                await self._upload_video_file(page, file_path)

                # 等待视频真正上传完成(「上传中」spinner DOM 消失 = 上传完成)
                await self._wait_for_upload_form(page)
                logger.info("[上传视频] 视频上传成功!")

                # 类型(原创/二创/转载)
                logger.info("[类型声明] 开始设置类型(原创/二创/转载): %s", ai_content or "无")
                await self._set_video_type(page, ai_content)

                # 标题
                logger.info("[填写标题] 开始填写标题: %s", title)
                await self._set_title(page, title)
                logger.info("[填写标题] 标题填写完成")

                # 封面(ESC 关闭原生选择器 + 隐藏 input)
                logger.info("[设置封面] 开始设置视频封面...")
                await self._set_cover(
                    page,
                    thumbnail_landscape_path,
                    thumbnail_portrait_path,
                    thumbnail_landscape_169_path,
                    thumbnail_portrait_916_path,
                )
                logger.info("[设置封面] 封面设置完成")

                # 分类(两级级联)
                logger.info("[设置分类] 开始设置分类: %s", category or "无")
                await self._set_category(page, category)

                # 合集(可选):切换「加入合集」开关 + 勾选对应合集项
                if weibo_collection:
                    logger.info("[设置合集] 开始选择微博合集: %s", weibo_collection)
                    await self._set_collection(page, weibo_collection)
                else:
                    logger.info("[设置合集] 未选择合集,跳过")

                # 微博正文
                logger.info("[填写简介] 开始填写微博正文...")
                await self._set_description(page, desc, title, tags)

                # 内容声明(可选):自动探测版本1弹窗 / 版本2必选+可选下拉
                logger.info(
                    "[内容声明] 开始设置内容声明: 版本1=%s, 版本2必选=%s, 版本2可选=%s",
                    content_statement or "无", content_statement2 or "无", content_statement2_optional or "无",
                )
                await self._set_content_statement(
                    page, content_statement, content_statement2, content_statement2_optional
                )

                # 点发布
                if manual_review_enabled('weibo', 'video'):
                    # 人工验收：保留表单，等待用户亲自点击平台发布按钮
                    async def _manual_video_success(page):
                        # 与自动分支判据一致：「视频已上传成功」toast
                        # 或 URL 跳离 /upload/channel
                        try:
                            if await page.locator(
                                "text=视频已上传成功"
                            ).first.is_visible():
                                return True
                        except Exception:
                            pass
                        return "weibo.com/upload/channel" not in (page.url or "")

                    await wait_for_manual_publish(
                        page, 'weibo', success_check=_manual_video_success
                    )
                else:
                    logger.info("[发布] 正在点击发布按钮...")
                    await self._click_publish(page)

                # 等待发布成功标志
                await self._wait_for_publish_success(page)
                logger.info("[发布] 视频发布成功!")

                # 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

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
            "[上传视频] 准备上传视频: %s (%.1f MB)",
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
        logger.info("[上传视频] patch status: %s", patch_status)

        # 2. 找上传按钮
        upload_btn = page.locator("button[id^='video_button_upload']").first
        if await upload_btn.count() == 0:
            upload_btn = page.get_by_role(
                "button", name="上传视频", exact=True,
            ).first
        if await upload_btn.count() == 0:
            raise RuntimeError("[上传视频] 未找到「上传视频」按钮")

        await upload_btn.wait_for(state="visible", timeout=10000)

        # 3. 触发按钮 — 多重尝试,任一成功即可
        triggered = False

        # 方式 A: expect_file_chooser 优先(原生 Playwright API)
        try:
            async with page.expect_file_chooser(timeout=5000) as fc_info:
                await upload_btn.click(force=True)
            fc = await fc_info.value
            await fc.set_files(file_path)
            logger.info("[上传视频] 已通过 expect_file_chooser 提交视频")
            triggered = True
        except Exception as e:
            logger.info("[上传视频] expect_file_chooser 方式失败: %s", e)

        # 方式 B: 普通 click + 等带标记 input (patch 命中)
        if not triggered:
            try:
                await upload_btn.click(force=True)
                logger.info("[上传视频] 已点击「上传视频」按钮(force=True)")
            except Exception as e:
                logger.warning("[上传视频] force=True click 失败: %s", e)
                await upload_btn.evaluate("el => el.click()")
                logger.info("[上传视频] 已点击「上传视频」按钮(JS .click())")

        # 4. 等带标记的 input 出现(patch 命中 或 MutationObserver 命中)
        marked_sel = (
            "input[type='file'][data-weibo-upload='1'],"
            "input[type='file'][data-weibo-new='1']"
        )
        deadline = asyncio.get_event_loop().time() + 30
        found_input = None
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page)
            try:
                count = await page.locator(marked_sel).count()
                if count > 0:
                    found_input = page.locator(marked_sel).first
                    logger.info("[上传视频] 检测到标记的 file input(count=%d)", count)
                    break
            except Exception as e:
                logger.warning("[上传视频] locator count 异常: %s", e)
            await asyncio.sleep(0.5)

        if found_input is not None:
            await found_input.set_input_files(file_path)
            logger.info(
                "[上传视频] 视频文件已通过 patched input 提交: %s",
                os.path.basename(file_path),
            )
            return

        # 5. 三重都失败
        all_count = await page.locator("input[type='file']").count()
        raise RuntimeError(
            "[上传视频] 30s 内未检测到带标记的 file input。"
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
            # 0. 浏览器/页面被用户关闭 → 立即判发布失败。
            #    下方 except Exception: pass 会把关闭后的所有 Playwright 异常
            #    吞掉空转,任务在队列里卡「发布中」直到 4 小时超时。
            raise_if_page_closed(page)

            # 1. 「上传中」DOM 消失 或 发布按钮可见(文字已从「自动发布」变成「发布」)
            try:
                uploading_gone = await uploading_locator.count() == 0
                publish_visible = await publish_btn.is_visible()
                if uploading_gone or publish_visible:
                    if uploading_gone and publish_visible:
                        logger.info(
                            "[发布] 「上传中」DOM 已消失且「发布」按钮可见,"
                            "上传完成、表单可交互"
                        )
                    elif uploading_gone:
                        logger.info(
                            "[发布] 「上传中」DOM 已消失,上传完成"
                        )
                    else:
                        logger.info(
                            "[发布] 「上传中」DOM 仍存在,但「发布」按钮已可见,"
                            "视为上传完成、表单可交互(转码阶段 spinner 暂未消失)"
                        )
                    return
            except Exception:
                pass

            # 2. 上传失败检测
            try:
                if await page.get_by_text("上传失败", exact=True).count() > 0:
                    raise RuntimeError(
                        "[发布] 视频上传失败(页面检测到「上传失败」文本)"
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
                        "[发布] 等待「上传中」消失或「发布」按钮可见... "
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
            f"[发布] 等待视频上传完成超时({timeout_s}s = "
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
            logger.warning("[发布] 未知类型声明值: %s,跳过", ai_content)
            return
        # DOM: <label><input type="radio"><span>原创</span></label>
        # 标签内的 radio 的无障碍名取自兄弟 span 文本
        radio = page.get_by_role("radio", name=target, exact=True).first
        try:
            await radio.wait_for(state="visible", timeout=5000)
            await radio.click(force=True)
            logger.info("[发布] 已选类型: %s", target)
        except Exception as e:
            logger.warning("[发布] 选择类型失败(%s): %s", target, e)

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
        logger.info("[发布] 已填标题: %s", truncated)

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
            logger.warning("[发布] 等「上传封面」链接超时: %s", e)

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
            logger.warning("[发布] 等封面 picture(img) 超时: %s", e)

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
            logger.warning("[发布] 读取封面区域宽高比失败: %s", e)
            aspect = None
            debug = None

        if debug:
            logger.info("[发布] 封面宽高比调试: %s", debug)

        if aspect is None:
            logger.info("[发布] 读不到封面框宽高比,默认横版")
            return landscape_path or portrait_path

        if aspect < 100:
            logger.info(
                "[发布] 封面框为横版(padding-bottom=%.2f%%),用横版封面",
                aspect,
            )
            return landscape_path or portrait_path
        else:
            logger.info(
                "[发布] 封面框为竖版(padding-bottom=%.2f%%),用竖版封面",
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
        thumbnail_landscape_169_path=None,
        thumbnail_portrait_916_path=None,
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

        封面尺寸优先级:微博封面框实际是 16:9 / 9:16,优先用
        ``thumbnail_landscape_169_path``(16:9) / ``thumbnail_portrait_916_path``
        (9:16);没有时回退到 4:3 / 3:4。
        """
        cover_path = await WeiboPlatform._pick_cover_by_aspect(
            page,
            landscape_path=thumbnail_landscape_169_path or thumbnail_landscape_path,
            portrait_path=thumbnail_portrait_916_path or thumbnail_portrait_path,
        )
        if not cover_path or not os.path.exists(cover_path):
            logger.info("[发布] 无封面文件,跳过封面上传")
            return

        # 1. 点击「上传封面」(注意 a 标签无 href,用文本匹配)
        upload_cover_link = page.get_by_text("上传封面").first
        try:
            await upload_cover_link.wait_for(state="visible", timeout=10000)
        except Exception:
            logger.warning("[发布] 未找到「上传封面」入口,跳过封面")
            return

        # 2. 点击 + 立即 ESC 关掉原生选择器(spec 强调此坑)
        await upload_cover_link.click()
        await asyncio.sleep(0.5)
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.8)
        logger.info("[发布] 已点击上传封面并 ESC 关闭原生选择器")

        # 3. 等待「编辑封面」弹层出现
        try:
            await page.get_by_text("编辑封面").first.wait_for(
                state="visible", timeout=10000
            )
            logger.info("[发布] 封面编辑弹层已出现")
        except Exception as e:
            logger.warning("[发布] 等待封面弹层超时: %s", e)
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
            logger.warning("[发布] 封面弹层未找到 input[type=file][accept^='.jpg']")
            return
        logger.info("[发布] 找到 %d 个封面 file input", count)
        await file_inputs.first.set_input_files(cover_path)
        logger.info("[发布] 已上传封面文件: %s", os.path.basename(cover_path))
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
            logger.info("[发布] 已点击封面完成按钮")
        except Exception as e:
            logger.warning("[发布] 点击封面完成按钮失败: %s", e)

        # 6. 关键: 等待「编辑封面」弹层真正关闭,否则它会盖住下面的
        #    「请选择合适的频道」下拉触发器和微博正文 textarea,导致后续步骤
        #    全部因元素 hidden 而失败。
        try:
            await page.get_by_text(
                "编辑封面", exact=True,
            ).first.wait_for(state="hidden", timeout=15000)
            logger.info("[发布] 封面编辑弹层已关闭")
        except Exception as e:
            logger.warning(
                "[发布] 等待封面弹层关闭超时,尝试 ESC 强制关闭: %s", e,
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
            logger.info("[发布] 未传分类,使用默认")
            return

        if isinstance(category, str):
            parts = [p.strip() for p in category.split("|")]
            if len(parts) != 2:
                logger.warning("[发布] 分类字符串格式错误: %s", category)
                return
            channel_name, sub_name = parts
        elif isinstance(category, (list, tuple)) and len(category) == 2:
            channel_name, sub_name = category[0], category[1]
        else:
            logger.warning("[发布] 分类参数无法识别: %r", category)
            return

        # 查表验证
        found = _weibo_categories.lookup_sub_channel(channel_name, sub_name)
        if not found:
            logger.warning(
                "[发布] 分类未在静态表里命中: %s/%s,仍尝试在页面上点",
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
            logger.warning("[发布] 未找到分类下拉触发器(占位文本): %s", e)
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
            logger.info("[发布] 已选一级频道: %s", channel_name)
            await asyncio.sleep(0.5)

            # 3. 等子分类列渲染: 目标 sub_name 应可见
            # 取 last: 子分类列在频道列之后,避免点到同名的频道
            sub_locator = page.get_by_text(sub_name, exact=True)
            await sub_locator.last.wait_for(state="visible", timeout=5000)
            await sub_locator.last.click()
            logger.info("[发布] 已选二级子分类: %s", sub_name)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(
                "[发布] 级联选择失败(channel=%s sub=%s): %s",
                channel_name, sub_name, e,
            )
            # ESC 关掉下拉避免挡住后续操作
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

    # ------------------------------------------------------------------
    # Helper: select 合集 (switch on + check the matching album)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_collection(page, collection_name: str):
        """选择微博视频合集。

        DOM(参考 weibo_bp.py 合集列表解析):
          - 合集开关: label.woo-switch-main(默认关闭,需点击开启)
            注意:页面有多个 woo-switch-main(允许划重点/允许他人剪辑/关联原视频等),
            合集开关是「合集」标题旁边那个 —— 用文案定位其容器再定位开关。
          - 开启后展开合集列表,每项: div._top2_* > label.woo-checkbox-main
            + input[type=text][value="合集名(共N集)"]

        流程:
          1. 定位「合集」标题所在行 → 找该行内的 woo-switch-main → 点击开启
          2. 等合集列表展开(input[type=text][value*="集"] 出现)
          3. 遍历合集项,找到 value 匹配 collection_name 的 → 勾选其 checkbox
        """
        # 1. 定位合集开关:在「合集」文案所在的设置行内找 woo-switch-main
        #    合集行的结构:div._switch_* > div(含「合集」文案) + div > label.woo-switch-main
        logger.info("[设置合集] 定位合集开关...")
        switch_clicked = False
        try:
            # 找所有含「合集」文本的行容器,再在其内部找开关
            switch_labels = page.locator("label.woo-switch-main")
            count = await switch_labels.count()
            logger.info("[设置合集] 页面共 %d 个 woo-switch-main 开关", count)
            # 合集开关特征:它的祖先行包含「合集」文案
            for i in range(count):
                label = switch_labels.nth(i)
                # 向上找到包含「合集」文案的容器
                has_collection_text = await label.evaluate(
                    """el => {
                        let node = el;
                        for (let depth = 0; depth < 6 && node; depth++) {
                            if (node.textContent && node.textContent.includes('合集') && !node.textContent.includes('允许')) {
                                return true;
                            }
                            node = node.parentElement;
                        }
                        return false;
                    }"""
                )
                if has_collection_text:
                    await label.click()
                    logger.info("[设置合集] 已点击第 %d 个开关(合集开关)", i)
                    switch_clicked = True
                    break
        except Exception as e:
            logger.warning("[设置合集] 点击合集开关失败: %s", e)

        if not switch_clicked:
            logger.warning("[设置合集] 未找到合集开关,跳过合集设置")
            return

        # 2. 等合集列表展开
        await asyncio.sleep(1.5)
        album_inputs = page.locator('input[type="text"][value*="集"]')
        try:
            await album_inputs.first.wait_for(state="attached", timeout=10000)
        except Exception:
            logger.warning("[设置合集] 切换开关后合集列表未展开,跳过")
            return

        # 3. 遍历合集项,找到名称匹配的勾选其 checkbox
        #    DOM 结构:每个合集项是一个 div._top2_*,内部:
        #      <label class="woo-checkbox-main">...</label>  ← 复选框(第一个子元素)
        #      <div class="woo-box-item-flex">...<input value="合集名(共N集)">...</div>
        #    用 xpath:先定位 value 匹配的 input → 向上找到 _top2_* 行 → 找行内 woo-checkbox-main
        total = await album_inputs.count()
        logger.info("[设置合集] 展开共 %d 个合集,查找: %s", total, collection_name)
        for i in range(total):
            try:
                raw = await album_inputs.nth(i).get_attribute("value")
                if not raw:
                    continue
                # value 形如 "AI(共0集)",取括号前的名称
                name = raw.split("(")[0].split("（")[0].strip() if raw else ""
                if name == collection_name:
                    # 用 xpath 定位同行内的 checkbox:从 input 向上找祖先 _top2_* 行,
                    # 再找该行内的 label.woo-checkbox-main
                    checkbox = album_inputs.nth(i).locator(
                        "xpath=ancestor::div[contains(@class,'_top2_')]"
                        "//label[contains(@class,'woo-checkbox-main')]"
                    ).first
                    await checkbox.click()
                    logger.info("[设置合集] 已勾选合集: %s", collection_name)
                    await asyncio.sleep(0.5)
                    return
            except Exception as e:
                logger.warning("[设置合集] 勾选第 %d 项失败: %s", i, e)
                continue

        logger.warning("[设置合集] 未找到匹配的合集: %s", collection_name)

    # ------------------------------------------------------------------
    # Helper: fill 微博正文 (description + tags as #话题)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_description(page, desc: str, title: str, tags: list):
        """填充微博正文 textarea。

        描述为空时不再回落标题，保持为空；tags 拼成 #话题 形式追加。
        """
        # textarea placeholder: 有什么新鲜事想分享给大家?
        textarea = page.locator(
            "textarea[placeholder*='有什么新鲜事']"
        ).first
        await textarea.wait_for(state="visible", timeout=10000)

        text = (desc or "").strip()
        if tags:
            tag_str = " ".join(f"#{t}" for t in tags)
            text = f"{text} {tag_str}".strip() if text else tag_str
        if not text:
            return

        # 微博 textarea 不是标准 input,fill 不一定生效,用 click+type
        await textarea.click()
        await asyncio.sleep(0.2)
        # 清空后输入(跨平台:Mac 用 Cmd+A,其他用 Ctrl+A)
        await clear_and_type(page, text, delay=30)
        await page.keyboard.press("Space")
        logger.info("[发布] 已填正文(长度=%d)", len(text))

    # ------------------------------------------------------------------
    # Helper: set 内容声明 (内容为自主创作/转载/AI生成/虚构演绎)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_content_statement(page, v1_stmt: str = "", v2_required: str = "", v2_optional: str = ""):
        """选择发布页的「内容声明」。

        微博有两种内容声明 UI,对不同账号/场景展示其中一种,运行时自动探测:

        版本1(老):底部工具栏「内容声明」文本触发弹窗,5 选项单选
            (无/内容为自主创作/内容为转载/内容由AI生成/内容为虚构演绎)。
        版本2(新):「请进行内容声明（必填）」触发下拉,分「必选」6 项 +
            「可选」4 项两组,选完点「确定」。

        前端用 3 个独立下拉分别承载两套声明,后端探测到哪种 UI 就用对应那套值:
        - 版本1 UI → 用 v1_stmt
        - 版本2 UI → 用 v2_required(必选) + v2_optional(可选)

        Args:
            v1_stmt: 版本1 声明值(5 选 1,或「无」/空=不设置)。
            v2_required: 版本2「必选」区声明值(6 选 1)。空或「内容无需标注」
                时点「内容无需标注」(必选区必须选一个)。
            v2_optional: 版本2「可选」区声明值。空=不选。
        """
        # 先探测版本2 trigger「请进行内容声明（必填）」是否存在
        # 注意:不能用 exact=True,实际 DOM 文本可能含全角括号或前后空白,
        # 用 contains 匹配更稳。探测全程打日志,绝不静默吞异常。
        logger.info(
            "[内容声明] 开始探测页面 UI 版本(v2_required=%s)",
            v2_required or "(空)",
        )
        v2_detected = False
        try:
            # 多个候选文本:全角括号 / 半角括号 / 含空白
            v2_trigger = page.get_by_text("请进行内容声明", exact=False).first
            cnt = await v2_trigger.count()
            logger.info("[内容声明] 探测「请进行内容声明」count=%d", cnt)
            if cnt > 0:
                v2_detected = True
        except Exception as e:
            # 探测本身异常:打印详情,不静默吞
            logger.warning("[内容声明] 探测版本2 trigger 异常: %s", e)

        if v2_detected:
            logger.info("[内容声明] ✓ 检测到版本2 UI(必填下拉),走 v2 逻辑")
            try:
                await WeiboPlatform._set_content_statement_v2(
                    page, v2_required, v2_optional
                )
            except Exception as e:
                logger.error(
                    "[内容声明] 版本2 处理异常: %s", e, exc_info=True
                )
            return

        # 否则走版本1(老弹窗)
        logger.info("[内容声明] 未检测到版本2,走版本1(弹窗)逻辑")
        try:
            await WeiboPlatform._set_content_statement_v1(page, v1_stmt)
        except Exception as e:
            logger.error(
                "[内容声明] 版本1 处理异常: %s", e, exc_info=True
            )

    @staticmethod
    async def _set_content_statement_v1(page, statement: str):
        """版本1:底部工具栏「内容声明」弹窗单选。

        spec line 7206: 5 个选项 — 无(默认)、内容为自主创作、内容为转载、
        内容由AI生成、内容为虚构演绎。
        空值或「无」视为不设置(微博默认就是「无」)。
        """
        if not statement or statement.strip() == "无":
            return

        stmt_text = statement.strip()
        # trigger 是「内容声明」文本节点,click 冒泡到父级 woo-pop-ctrl
        # 但父级 <span class="woo-pop-ctrl"> 在 actionability 检查里
        # 会被判为「intercept pointer events」(2026-06-17 实测:50+ 次
        # retry → 页面上下弹),必须 force=True 跳过这个检查。
        trigger = page.get_by_text("内容声明", exact=True).first
        try:
            await trigger.wait_for(state="visible", timeout=5000)
        except Exception as e:
            logger.warning("[发布] 未找到内容声明入口: %s", e)
            return

        await trigger.click(force=True)
        await asyncio.sleep(0.5)

        # 弹窗里的选项是 button,文本就是选项值
        option = page.get_by_role("button", name=stmt_text, exact=True).first
        try:
            await option.wait_for(state="visible", timeout=5000)
            await option.click()
            logger.info("[发布] 已选内容声明(版本1): %s", stmt_text)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning(
                "[发布] 选择内容声明失败(%s): %s", stmt_text, e,
            )
            # ESC 关闭弹出的内容声明面板
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)

    @staticmethod
    async def _set_content_statement_v2(page, required_stmt: str, optional_stmt: str = ""):
        """版本2:「请进行内容声明（必填）」下拉,分必选/可选两组。

        DOM 结构(用户提供):
          trigger: <div class="_triggerText...">请进行内容声明（必填）</div>
          面板: <div class="_panel...">
                   <div class="_sectionTitle">必选</div>
                   <button>...内容无需标注 / 内容为转载 / 含AI生成内容 /
                           含虚构演绎内容 / 个人观点，仅供参考 / 内容含营销信息</button>
                   <div class="_sectionTitle">可选</div>
                   <button>...内容可能引人不适... / 内容含有高危险行为... /
                           请理性适度消费 / 未成年人请在监护人指导下浏览</button>
                   <div class="_footer"><button>确定</button></div>
                </div>

        Args:
            required_stmt: 必选声明值。空或「内容无需标注」时点「内容无需标注」
                (必选区必须选一个)。
            optional_stmt: 可选声明值。空=不选。
        """
        # 必选区:空或「内容无需标注」默认选「内容无需标注」(必选必填一个)
        required_text = (required_stmt or "").strip()
        if not required_text or required_text == "无":
            required_text = "内容无需标注"

        # 点 trigger 展开「必填」下拉(woo-pop-ctrl 同样有 intercept 问题,force)
        # exact=False:实际文本可能含全角括号/前后空白,用包含匹配
        trigger = page.get_by_text("请进行内容声明", exact=False).first
        try:
            await trigger.wait_for(state="visible", timeout=5000)
            logger.info("[内容声明v2] 找到 trigger「请进行内容声明」")
        except Exception as e:
            logger.warning("[内容声明v2] 未找到 trigger 入口: %s", e)
            return

        await trigger.click(force=True)
        logger.info("[内容声明v2] 已点击 trigger,等待面板展开")
        # 面板展开是动画,实测 0.5s 偶尔不够,给 1s 让 _panel 完整渲染
        await asyncio.sleep(1)

        # 校验面板是否真正展开(区分"没展开"和"展开了没点到")
        panel = page.locator("._panel_nsgmr_114, [class*='_panel_']").first
        try:
            await panel.wait_for(state="visible", timeout=3000)
            logger.info("[发布] 内容声明(版本2)面板已展开")
        except Exception as e:
            logger.warning("[发布] 内容声明(版本2)面板未展开(trigger 点击无效?): %s", e)
            return

        # 通用:在弹出面板里点某个选项
        # 关键:不用 get_by_role(button, name=) — 选项 button 内部是
        # <span class="_check"><!----></span> + <span class="_optionLabel">文案</span>,
        # accessible name 计算不稳定。改为用 CSS 类直接定位 _optionLabel 文案,
        # 再点其父级 button。
        async def _click_option(text, timeout=5000):
            """点面板里文案为 text 的选项,返回是否成功。"""
            # 定位文案 span,再点其所在 button(用 force 跳过 intercept)
            label = page.locator(
                f"[class*='_optionLabel']:has-text('{text}')"
            ).first
            try:
                await label.wait_for(state="visible", timeout=timeout)
                # 点 label 的父级 button(label 本身不是可点击区,button 才是)
                btn = label.locator("xpath=ancestor::button[1]")
                if await btn.count() == 0:
                    # 兜底:直接点 label
                    await label.click(force=True)
                else:
                    await btn.first.click(force=True)
                return True
            except Exception as e:
                logger.warning("[发布] 内容声明(版本2)点击选项「%s」失败: %s", text, e)
                return False

        # 选必选项(必选区必须选一个,失败则 ESC 退出)
        ok = await _click_option(required_text, timeout=5000)
        if not ok:
            logger.warning("[发布] 内容声明(版本2)必选项「%s」选择失败,放弃", required_text)
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
            return
        logger.info("[发布] 已选内容声明(版本2必选): %s", required_text)
        await asyncio.sleep(0.4)

        # 选可选项(可选,空则跳过;失败不中断,继续点确定)
        if optional_stmt and optional_stmt.strip():
            opt_text = optional_stmt.strip()
            if await _click_option(opt_text, timeout=3000):
                logger.info("[发布] 已选内容声明(版本2可选): %s", opt_text)
                await asyncio.sleep(0.4)

        # 点「确定」按钮提交选择(必点,否则选择不生效)
        # DOM:<button class="woo-button-..."><span class="woo-button-content"> 确定 </span></button>
        # 用 woo-button-content 文本定位,不依赖 accessible name
        try:
            confirm_btn = page.locator(
                ".woo-button-content:has-text('确定')"
            ).first
            await confirm_btn.wait_for(state="visible", timeout=3000)
            # 点 button(woo-button-content 的父级),force 跳过 intercept
            confirm_button = confirm_btn.locator("xpath=ancestor::button[1]")
            if await confirm_button.count() > 0:
                await confirm_button.first.click(force=True)
            else:
                await confirm_btn.click(force=True)
            logger.info("[发布] 内容声明(版本2)已点确定,选择提交")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning("[发布] 点内容声明(版本2)确定按钮失败: %s", e)
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
            raise RuntimeError(f"[发布] 未找到发布按钮: {e}")

        # 轮询 disabled 属性(最长 60s)
        for _ in range(60):
            disabled = await publish_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[发布] 发布按钮一直 disabled,表单未就绪")

        await publish_btn.click()
        logger.info("[发布] 已点击发布按钮")

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
            logger.info("[发布] 发布成功(检测到「视频已上传成功」toast)")
        except Exception:
            # 兜底: 看 URL 是否跳走
            await asyncio.sleep(3)
            current = page.url
            if "weibo.com/upload/channel" not in current:
                logger.info("[发布] 发布成功(URL 已跳转: %s)", current)
            else:
                raise RuntimeError(
                    f"[发布] 发布后未检测到成功信号,当前 URL: {current}"
                )

    # ==================================================================
    # 头条文章发布(publish_article)
    # ==================================================================
    # 编辑器: https://card.weibo.com/article/v5/editor#/draft
    #   - 标题:  textarea[placeholder*=请输入标题] (≤32 字)
    #   - 导语:  textarea[placeholder*=导语]     (≤44 字, 即 draft.summary)
    #   - 正文:  .tiptap.ProseMirror (ProseMirror, 粘贴 text/html 解析)
    #   - 图片:  图片库弹窗「上传」→ picupload.weibo.com → sinaimg CDN URL
    #            (实现改为页面内 fetch 直传图床, 与前端同接口, 再注册
    #             uploadpic 进文章图片库)
    #   - 封面:  「设置文章封面」弹窗(正文图片 / 图片库) → 下一步 → 16:9 裁剪
    #   - 编辑页「发布设置」区(2026-10 全量实测):
    #       设置封面(16:9) / 专栏设置(加入专栏) / 其他设置:
    #       仅粉丝阅读全文(follow_to_read, 本账号默认开) / 设置推荐文章
    #       (article_recommend) / 同步至新浪新闻(mpkey) / 仅在移动端展示
    #       (only_render_h5) / 付费、V+订阅、单篇付费、赞赏(isreward)
    #       后 5 项均受账号能力位控制(switch/plugins_enable), 本账号不显示
    #   - 草稿:  POST /article/v5/aj/editor/draft/create + /draft/save
    #   - 下一步: 点「下一步」→ POST /draft/save(action=2) 前置校验
    #            可能返回 data.geetest.verifyUrl → 跳转
    #            security.weibo.com/captcha/geetest 身份验证(风控, 需人工处理)
    #            → 通过后弹出发布弹窗(publish-modal)
    #   - 发布弹窗(publish-modal)设置(由编辑器 bundle PublishModal 还原):
    #       * 微博正文 textarea(maxlength=2000, 必填, 空则「发布」disabled;
    #         默认文案「发布了头条文章：《标题》」), 字数按中文1/英文0.5 折算
    #       * 发布范围 WbSetting: 公开(rank=0) / 粉丝(rank=10)
    #       * 内容声明 WbSetting 子菜单: 无(0) / 内容由AI生成(1) /
    #         内容为虚构演绎(2) → 提交字段 mblog_statement
    #       * 定时发布(publish-time 图标, 仅 switch 位掩码 2 可用时显示):
    #         日期(今天~+7天)+时+分, 默认 server_time+15min;
    #         提交走 POST /draft/publishtiming(time="YYYY-MM-DD HH:mm",
    #         timestamp=时区偏移小时), 立即发表走 /draft/publish
    #       * 原创声明 is_original(仅签约自媒体 is_wemedia_memeber 显示,
    #         文案「我同意《微博签约媒体原创认证协议》，并声明本文是原创作品」)
    #       * 关注@头条文章 follow_official(已关注则控件隐藏)
    #       * 同步到微博 sync_wb(仅 super_topic 类型草稿显示, 普通文章无此项)
    #   - 发表:  发布弹窗「发布」按钮 → POST /draft/publish 或 /draft/publishtiming
    #            成功判定: 该接口响应 code == 100000(唯一依据)
    # ------------------------------------------------------------------

    _ARTICLE_EDITOR_URL = "https://card.weibo.com/article/v5/editor#/draft"
    _ARTICLE_TITLE_MAX = 32
    _ARTICLE_SUMMARY_MAX = 44
    _ARTICLE_UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.4324.150 Safari/537.36"
    )
    # 微博接口成功码(草稿保存/图片注册/发表统一)
    _ARTICLE_OK_CODE = 100000
    # 发表时若触发微博身份验证(geetest), 有头浏览器等待人工处理的最长时间
    _ARTICLE_CAPTCHA_TIMEOUT = 300
    # 发布弹窗微博正文硬上限(平台 textarea maxlength=2000)
    _ARTICLE_WEIBO_TEXT_MAX = 2000
    # 定时发布可选日期范围: 今天 ~ 今天+7 天(与平台 date-picker 禁用规则一致)
    _ARTICLE_TIMING_MAX_DAYS = 7

    # 内容声明(发布弹窗 WbSetting)选项 → mblog_statement 编码
    _ARTICLE_STATEMENT_MAP = {
        "无": 0,
        "内容无需标注": 0,
        "内容由AI生成": 1,
        "含AI生成内容": 1,
        "内容为虚构演绎": 2,
        "含虚构演绎内容": 2,
    }

    # 发布范围(发布弹窗 WbSetting)选项 → rank 编码
    _ARTICLE_RANK_MAP = {
        "": 0,
        "公开": 0,
        "粉丝": 10,
        "0": 0,
        "10": 10,
    }

    def publish_article(self, **kwargs) -> bool:
        """发布头条文章到微博(同步入口)。

        kwargs:
            title (*str*) -- 文章标题(≤32 字,超出截断)
            html (*str*) -- 正文 HTML(img src 为本地素材 URL,自动上传
                微博图床后替换为 sinaimg CDN URL)
            account_file (*list[str]*) -- cookie 文件名列表(逐个账号发布)
            cover_path (*str*, optional) -- 封面图本地路径(16:9 建议);
                空则默认取正文首图
            is_draft (*bool*) -- True(默认)= 只保存草稿,不点下一步/发布;
                False = 走完发布弹窗并点「发布」真实发表
            dry_run (*bool*) -- True 时强制 is_draft=True
            schedule_time_str (*str*, optional) -- 定时发布时间
                ("YYYY-MM-DD HH:mm" 等可解析格式); 发表模式下生效,
                提交走 /draft/publishtiming。账号无定时能力时中止
                (不静默改为立即发表, 避免时机错误)
            summary / weibo_summary / digest (*str*, optional) -- 导语(≤44 字)
            weibo_topics / topics (*list[str]*, optional) -- 话题标签,
                以 #话题# 形式追加到正文末尾与发布弹窗微博正文
            weibo_statement (*str*, optional) -- 内容声明:
                无 / 内容由AI生成 / 内容为虚构演绎(发布弹窗设置; 显式传入但
                自动化失败会中止发表, 避免设置丢失)
            weibo_text (*str*, optional) -- 发布弹窗「微博正文」文案;
                空则用平台默认「发布了头条文章：《标题》」(≤2000 字)
            weibo_rank (*str|int*, optional) -- 发布范围: 公开(默认)/粉丝
                (与内容声明互斥: 选内容声明的平台联动会把范围改为公开)
            weibo_is_original (*bool*, optional) -- 原创声明(仅签约自媒体
                账号有该控件; 无控件时告警跳过)
            weibo_follow_official (*bool*, optional) -- 关注@头条文章
                (默认 True; 账号已关注时平台隐藏该控件)
            weibo_follow_to_read (*bool*, optional) -- 编辑页「仅粉丝阅读全文」;
                None(默认)= 保留平台默认, True/False = 显式开关
            weibo_sync_wb (*bool*, optional) -- 发布弹窗「同步到微博」,
                仅 super_topic 类型草稿有该开关, 普通文章忽略
        """
        allowed_keys = (
            "title", "html", "account_file", "cover_path",
            "is_draft", "dry_run", "schedule_time_str",
            "summary", "weibo_summary", "digest",
            "weibo_topics", "topics", "weibo_statement",
            "weibo_text", "weibo_rank", "weibo_is_original",
            "weibo_follow_official", "weibo_follow_to_read",
            "weibo_sync_wb",
        )
        filtered = {k: kwargs[k] for k in allowed_keys if k in kwargs}
        if filtered.get("dry_run", False):
            filtered["is_draft"] = True
        asyncio.run(self._publish_article_all(**filtered))
        return True

    # ------------------------------------------------------------------
    # 编排: 单层账号循环(一账号发完一篇文章)
    # ------------------------------------------------------------------

    async def _publish_article_all(self, **kwargs):
        logger.info("=" * 60)
        logger.info("[文章] 开始微博头条文章发布流程")
        logger.info("=" * 60)

        title = (kwargs.get("title") or "").strip()
        html = kwargs.get("html") or ""
        account_file = kwargs.get("account_file") or []
        cover_path = kwargs.get("cover_path") or ""
        is_draft = kwargs.get("is_draft", True)
        dry_run = bool(kwargs.get("dry_run", False))
        summary = (
            kwargs.get("summary")
            or kwargs.get("weibo_summary")
            or kwargs.get("digest")
            or ""
        )
        topics = kwargs.get("weibo_topics") or kwargs.get("topics") or []
        statement = kwargs.get("weibo_statement") or ""
        schedule_time_str = kwargs.get("schedule_time_str") or ""
        weibo_text = kwargs.get("weibo_text") or ""
        rank_raw = kwargs.get("weibo_rank", "")
        is_original = bool(kwargs.get("weibo_is_original", False))
        follow_official = kwargs.get("weibo_follow_official", True)
        if follow_official is None:
            follow_official = True
        follow_to_read = kwargs.get("weibo_follow_to_read", None)
        sync_wb = kwargs.get("weibo_sync_wb", None)

        if isinstance(topics, str):
            topics = [
                t.strip() for t in topics.replace("，", ",").split(",")
                if t.strip()
            ]
        topics = [str(t).strip() for t in topics if str(t).strip()]

        rank = self._ARTICLE_RANK_MAP.get(str(rank_raw).strip())
        if rank is None:
            logger.warning(
                "[文章参数] 未知发布范围 weibo_rank=%r,按「公开」处理",
                rank_raw,
            )
            rank = 0
        follow_to_read_flag = None
        if follow_to_read is not None:
            follow_to_read_flag = 1 if follow_to_read in (
                True, "true", "True", 1, "1") else 0

        logger.info("[文章参数] 标题: %s", title)
        logger.info("[文章参数] 正文 HTML 长度: %d", len(html))
        logger.info("[文章参数] 导语: %s", (summary or "无")[:44])
        logger.info("[文章参数] 话题标签: %s", topics or "无")
        logger.info("[文章参数] 内容声明: %s", statement or "无")
        logger.info("[文章参数] 微博正文: %s",
                    (weibo_text or "无(平台默认:发布了头条文章：《标题》)")[:120])
        logger.info("[文章参数] 发布范围: %s", "粉丝" if rank == 10 else "公开")
        logger.info("[文章参数] 原创声明: %s", "是" if is_original else "否")
        logger.info("[文章参数] 关注@头条文章: %s",
                    "是" if follow_official else "否")
        logger.info(
            "[文章参数] 仅粉丝阅读全文: %s",
            "保留平台默认" if follow_to_read_flag is None
            else ("开" if follow_to_read_flag == 1 else "关"),
        )
        if sync_wb is not None:
            logger.info(
                "[文章参数] 同步到微博: %s(仅 super_topic 草稿平台才显示)",
                "开" if sync_wb else "关",
            )
        logger.info("[文章参数] 封面: %s", cover_path or "无(取正文首图)")
        logger.info("[文章参数] 账号数量: %d", len(account_file))
        logger.info(
            "[文章参数] 模式: %s",
            "dry-run/存草稿" if dry_run else ("存草稿" if is_draft else "发表"),
        )
        if schedule_time_str:
            if is_draft:
                logger.warning(
                    "[文章参数] 草稿模式忽略定时发布 schedule_time_str=%s",
                    schedule_time_str,
                )
            else:
                logger.info(
                    "[文章参数] 定时发布: %s", schedule_time_str
                )

        if not title:
            raise RuntimeError("[文章][微博] 标题不能为空")
        if not html.strip():
            raise RuntimeError("[文章][微博] 正文不能为空")
        if not account_file:
            raise RuntimeError("[文章][微博] 缺少账号 cookie 配置")

        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]
        for cookie_index, cookie_path in enumerate(account_paths):
            cookie_name = Path(cookie_path).name
            nick = get_account_name_by_cookie_file(cookie_name)
            with bind_account_name(nick or "-"):
                logger.info(
                    "[文章进度] 发布到第 %d/%d 个账号 (%s)",
                    cookie_index + 1, len(account_paths), nick or "未知",
                )
                await self._publish_article_one(
                    title=title,
                    html=html,
                    account_file=cookie_path,
                    summary=summary,
                    topics=topics,
                    statement=statement,
                    cover_path=str(cover_path) if cover_path else "",
                    is_draft=is_draft,
                    dry_run=dry_run,
                    weibo_text=weibo_text,
                    rank=rank,
                    is_original=is_original,
                    follow_official=bool(follow_official),
                    follow_to_read=follow_to_read_flag,
                    sync_wb=sync_wb,
                    schedule_time_str="" if is_draft else schedule_time_str,
                )

        logger.info("=" * 60)
        logger.info("[文章] 微博头条文章发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 单账号完整流程
    # ------------------------------------------------------------------

    async def _publish_article_one(
        self,
        title: str,
        html: str,
        account_file: str,
        summary: str = "",
        topics=None,
        statement: str = "",
        cover_path: str = "",
        is_draft: bool = True,
        dry_run: bool = False,
        weibo_text: str = "",
        rank: int = 0,
        is_original: bool = False,
        follow_official: bool = True,
        follow_to_read=None,
        sync_wb=None,
        schedule_time_str: str = "",
    ):
        """单账号头条文章发布完整流程。

        流程: 打开编辑器 → 写文章建草稿 → 上传正文图片微博图床 →
        粘贴正文 HTML → 标题/导语 → 仅粉丝阅读全文 → 封面 →
        before_submit 截图 → 保存草稿(并核对) →
        (非草稿)下一步 → 发布弹窗(微博正文/发布范围/内容声明/原创声明/
        关注官方/定时发布) → 发布API 判定。
        """
        from services.article_html import (
            extract_img_srcs,
            replace_img_srcs,
            sanitize_article_html,
        )

        topics = topics or []
        logger.info("[文章][微博] 开始单账号文章发布")

        # 正文图片本地路径解析(失败即异常: 图片缺失等于内容损坏)
        clean_html = sanitize_article_html(html)
        srcs = extract_img_srcs(clean_html)
        local_paths = []
        if srcs:
            logger.info(
                "[文章][微博] 正文含 %d 张图片,准备上传微博图床", len(srcs)
            )
            local_paths = [self._resolve_article_image_path(s) for s in srcs]
        else:
            logger.info("[文章][微博] 正文无图片,跳过上传")

        # 话题标签: 以 #话题# 形式写入正文末尾(微博惯例,正文页可见)
        if topics:
            tag_text = " ".join(f"#{t}#" for t in topics)
            clean_html += f"<p>{tag_text}</p>"
            logger.info("[文章][微博] 话题标签已写入正文末尾: %s", tag_text)

        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser,
                storage_state=account_file,
                user_agent=self._ARTICLE_UA,
            )
            try:
                page = await context.new_page()
                # 发布接口结果收集(草稿保存/发表)
                results = {"save": [], "publish": []}

                async def _on_response(resp):
                    try:
                        url = resp.url
                        req = resp.request
                        if req.method != "POST":
                            return
                        if "/aj/editor/draft/save" in url:
                            body = await self._safe_json(resp)
                            results["save"].append(body)
                        elif (
                            "/aj/editor/draft/publish" in url
                            or "/aj/editor/draft/publishtiming" in url
                        ):
                            body = await self._safe_json(resp)
                            results["publish"].append(body)
                    except Exception:
                        pass

                page.on("response", _on_response)

                # 1. 打开编辑器 → 写文章建新草稿
                await self._article_open_editor(page)
                draft_id = await self._article_create_draft(page)
                uid, nick = await self._article_get_uid_nick(page)
                logger.info(
                    "[文章][微博] 草稿已创建: id=%s uid=%s nick=%s",
                    draft_id, uid, nick,
                )

                # 2. 正文图片 → 微博图床 → 替换 CDN URL
                if srcs:
                    mapping = await self._article_upload_images(
                        page, local_paths, uid, nick
                    )
                    clean_html = replace_img_srcs(
                        clean_html, dict(zip(srcs, mapping))
                    )
                    logger.info(
                        "[文章][微博] 正文图片已全部替换为微博 CDN URL"
                    )

                # 3. 封面图上传图床(先传, 稍后在封面弹窗里选)
                cover_pid = ""
                if cover_path and Path(cover_path).exists():
                    try:
                        cover_pid, cover_url = await self._article_upload_image(
                            page, cover_path, uid, nick
                        )
                        logger.info(
                            "[文章][微博] 封面图已上传图床: %s", cover_url
                        )
                    except Exception as e:
                        logger.warning(
                            "[文章][微博] 封面上传失败(跳过,稍后取正文首图): %s",
                            e,
                        )
                        cover_pid = ""
                elif cover_path:
                    logger.warning(
                        "[文章][微博] 封面文件不存在: %s,跳过", cover_path
                    )

                # 4. 标题 / 导语
                await self._article_fill_title(page, title)
                await self._article_fill_summary(page, summary)

                # 5. 正文 HTML 粘贴
                await self._article_paste_html(page, clean_html)

                # 6. 编辑页「仅粉丝阅读全文」(follow_to_read):
                #    None=保留平台默认(本账号默认开), 显式 True/False 才点开关
                if follow_to_read is not None:
                    await self._article_set_follow_to_read(page, follow_to_read)

                # 7. 封面(正文首图 / 刚上传的封面图)
                await self._article_set_cover(page, cover_pid)

                # 8. before_submit 截图(验证证据)
                await self._article_screenshot(
                    page, "weibo_article_before_submit.png"
                )

                # 9. 保存草稿 + 核对
                await self._article_save_draft(page, results)
                await self._article_verify_draft(
                    page, draft_id, title, summary, clean_html,
                    expected_follow_to_read=follow_to_read,
                )

                # 10. 草稿模式到此为止; 发表模式走下一步 + 发布弹窗
                if not is_draft:
                    await self._article_click_next(page)
                    await self._article_publish(
                        page, results, title, summary, topics, statement,
                        weibo_text=weibo_text,
                        rank=rank,
                        is_original=is_original,
                        follow_official=follow_official,
                        sync_wb=sync_wb,
                        schedule_time_str=schedule_time_str,
                    )
                    logger.info("[文章][微博] ✓ 文章发表成功!")

                # 保存 cookie
                try:
                    await context.storage_state(path=account_file)
                    logger.info("[文章][微博] Cookie 状态已更新")
                except Exception as e:
                    logger.warning("[文章][微博] 保存 cookie 失败: %s", e)
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ==================================================================
    # 文章辅助方法
    # ==================================================================

    @staticmethod
    async def _safe_json(resp):
        try:
            return await resp.json()
        except Exception:
            try:
                return {"_raw": (await resp.text())[:500]}
            except Exception:
                return {}

    @staticmethod
    async def _article_screenshot(page, name: str):
        try:
            from conf import BASE_DIR as _BASE_DIR
            shot_dir = Path(_BASE_DIR) / "screenshots"
            shot_dir.mkdir(parents=True, exist_ok=True)
            path = shot_dir / name
            await page.screenshot(path=str(path), full_page=True)
            logger.info("[文章][微博] 截图: %s", path)
        except Exception as e:
            logger.warning("[文章][微博] 截图失败(非致命): %s", e)

    async def _article_open_editor(self, page):
        """打开头条文章编辑器, 等「写文章」按钮就绪(初始加载遮罩消失)。"""
        logger.info("[文章][微博] 打开编辑器: %s", self._ARTICLE_EDITOR_URL)
        await page.goto(
            self._ARTICLE_EDITOR_URL,
            wait_until="domcontentloaded",
            timeout=60000,
        )
        deadline = asyncio.get_event_loop().time() + 60
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            try:
                if await page.locator(
                    'button:has-text("写文章")'
                ).first.is_visible():
                    await asyncio.sleep(1)
                    logger.info("[文章][微博] 编辑器已就绪, url=%s", page.url)
                    return
            except Exception:
                pass
            await asyncio.sleep(1)
        raise RuntimeError("[文章][微博] 编辑器加载超时(未找到「写文章」按钮)")

    async def _article_create_draft(self, page) -> str:
        """点「写文章」创建新草稿, 返回 draft id(URL hash #/draft/<id>)。"""
        import re as _re

        before = page.url
        try:
            await page.locator(
                'button:has-text("写文章")'
            ).first.click(timeout=15000)
        except Exception as e:
            logger.warning("[文章][微博] 「写文章」点击失败,尝试 JS 点击: %s", e)
            await page.evaluate(
                """() => {
                  for (const b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim() === '写文章') {
                      b.click(); return true;
                    }
                  }
                  return false;
                }"""
            )
        deadline = asyncio.get_event_loop().time() + 60
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            url = page.url or ""
            m = _re.search(r"#/draft/(\d+)", url)
            if m and url != before:
                draft_id = m.group(1)
                await asyncio.sleep(2)
                return draft_id
            await asyncio.sleep(1)
        raise RuntimeError(
            f"[文章][微博] 创建草稿超时(当前 URL: {page.url})"
        )

    @staticmethod
    async def _article_get_uid_nick(page):
        """从顶部导航取 uid / 昵称(图床上传参数用)。"""
        info = await page.evaluate(
            """() => {
              let uid = '', nick = '';
              const cands = [
                '.woo-tab-nav a[href^="/u/"]',
                'a[href^="https://weibo.com/u/"]',
                'a[href*="weibo.com/u/"]',
              ];
              for (const sel of cands) {
                const a = document.querySelector(sel);
                if (!a) continue;
                const m = (a.getAttribute('href') || '').match(/\\/u\\/(\\d+)/);
                if (m) {
                  uid = m[1];
                  nick = (a.getAttribute('title') || a.innerText || '').trim();
                  break;
                }
              }
              return {uid, nick};
            }"""
        )
        return (info or {}).get("uid", ""), (info or {}).get("nick", "")

    # ---------------- 图片 ----------------

    @staticmethod
    def _resolve_article_image_path(src: str) -> str:
        """正文 img src → 本地文件路径(上传微博图床用)。

        支持: 素材库 URL(/api/materials/file/<stored_path>)、本地绝对路径、
        data: URL(写临时文件)、外链 http(s)(下载到临时文件)。
        """
        import base64
        import mimetypes
        import tempfile
        from urllib.parse import unquote, urlparse

        from storage import get_storage

        if src.startswith("data:"):
            head, _, b64 = src.partition(",")
            mime = head[5:].split(";")[0] or "image/png"
            ext = mimetypes.guess_extension(mime) or ".png"
            fd, path = tempfile.mkstemp(suffix=ext)
            with os.fdopen(fd, "wb") as f:
                f.write(base64.b64decode(b64))
            return path

        parsed = urlparse(src)
        marker = "/api/materials/file/"
        stored = ""
        if marker in src:
            stored = unquote(src.split(marker, 1)[1].split("?")[0])
        elif parsed.path and marker in parsed.path:
            stored = unquote(parsed.path.split(marker, 1)[1])

        if stored:
            local = get_storage().get_local_path(stored)
            if local and Path(local).exists():
                return local
            full_url = src if src.startswith("http") else (
                f"http://127.0.0.1:5409{src}"
            )
            return WeiboPlatform._download_to_temp(
                full_url, stored.split("/")[-1]
            )

        if src.startswith(("http://", "https://")):
            return WeiboPlatform._download_to_temp(
                src, Path(parsed.path).name or "img.png"
            )

        p = Path(src)
        if p.exists():
            return str(p)
        raise RuntimeError(f"[文章][微博] 无法解析正文图片 src: {src}")

    @staticmethod
    def _download_to_temp(url: str, filename: str = "img.png") -> str:
        import tempfile
        import urllib.request

        resp = urllib.request.urlopen(url, timeout=30)
        data = resp.read()
        suffix = Path(filename).suffix or ".png"
        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return path

    async def _article_upload_images(self, page, local_paths, uid, nick):
        """逐张上传本地图片到微博图床, 返回 CDN URL 列表(顺序一致)。

        走编辑器同款接口: POST picupload.weibo.com/interface/pic_upload.php
        (页面内 fetch, 自动带 cookie/水印参数), 再 POST
        /article/v5/aj/editor/plugins/uploadpic 注册进文章图片库。
        任一张失败 → 抛异常(正文图片缺失等于内容损坏)。
        """
        urls = []
        for i, path in enumerate(local_paths):
            try:
                pid, url = await self._article_upload_image(page, path, uid, nick)
                urls.append(url)
                logger.info(
                    "[文章][微博] 图片 %d/%d 已上传图床: %s",
                    i + 1, len(local_paths), url[:90],
                )
            except Exception as e:
                raise RuntimeError(
                    f"[文章][微博] 正文图片上传失败({Path(path).name}): {e}"
                )
        return urls

    async def _article_upload_image(self, page, local_path, uid, nick):
        """单张图片上传微博图床 + 注册, 返回 (pid, CDN URL)。"""
        import base64
        import mimetypes

        data = Path(local_path).read_bytes()
        name = Path(local_path).name
        mime = mimetypes.guess_type(name)[0] or "image/jpeg"
        b64 = base64.b64encode(data).decode()
        ext = "gif" if mime == "image/gif" else "jpg"

        result = await page.evaluate(
            """async (payload) => {
              const bin = atob(payload.b64);
              const arr = new Uint8Array(bin.length);
              for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
              const blob = new Blob([arr], {type: payload.mime});
              const q = new URLSearchParams({
                app: 'miniblog', s: 'json', p: '1', data: '1',
                file_source: '4',
                url: 'weibo.com/u/' + payload.uid,
                markpos: '1', logo: '1', nick: payload.nick || '',
              });
              let resp;
              try {
                resp = await fetch(
                  'https://picupload.weibo.com/interface/pic_upload.php?'
                  + q.toString(),
                  {
                    method: 'POST', body: blob, credentials: 'include',
                    headers: {'Content-Type': payload.mime},
                  },
                );
              } catch (e) {
                return {ok: false, err: 'fetch:' + String(e)};
              }
              let js = null;
              try { js = await resp.json(); } catch (e) {
                return {ok: false, err: 'json:' + String(e),
                        status: resp.status};
              }
              const pid = (js && js.pics && js.pics.pic_1 &&
                           js.pics.pic_1.pid)
                || (js && js.data && js.data.pics && js.data.pics.pic_1 &&
                    js.data.pics.pic_1.pid) || '';
              return {ok: !!pid, pid, code: js && js.code,
                      raw: JSON.stringify(js).slice(0, 300)};
            }""",
            {"b64": b64, "mime": mime, "uid": uid, "nick": nick},
        )
        if not result or not result.get("ok"):
            raise RuntimeError(
                f"图床上传失败 code={((result or {}).get('code'))} "
                f"{(result or {}).get('err') or (result or {}).get('raw') or ''}"
            )
        pid = result["pid"]
        cdn_url = f"https://wx3.sinaimg.cn/large/{pid}.{ext}"

        # 注册进文章图片库(不注册时正文/封面选图列表里看不到该图)
        reg = await page.evaluate(
            """async (payload) => {
              const body = new URLSearchParams({
                pid: payload.pid, uid: payload.uid,
              });
              try {
                const resp = await fetch(
                  '/article/v5/aj/editor/plugins/uploadpic',
                  {
                    method: 'POST', body,
                    credentials: 'include',
                    headers: {
                      'Content-Type':
                        'application/x-www-form-urlencoded;charset=UTF-8',
                    },
                  },
                );
                const js = await resp.json();
                return {code: js && js.code};
              } catch (e) {
                return {code: -1, err: String(e)};
              }
            }""",
            {"pid": pid, "uid": uid},
        )
        if (reg or {}).get("code") != self._ARTICLE_OK_CODE:
            logger.warning(
                "[文章][微博] 图片注册到文章图片库失败(仍继续): %s", reg
            )
        else:
            # 图片入库/转码需要一点时间(前端实现固定等待 15s, 这里缩短)
            await asyncio.sleep(2)
        return pid, cdn_url

    # ---------------- 标题 / 导语 / 正文 ----------------

    async def _article_fill_title(self, page, title: str):
        text = (title or "").strip()[: self._ARTICLE_TITLE_MAX]
        box = page.locator('textarea[placeholder*="请输入标题"]').first
        await box.wait_for(state="visible", timeout=20000)
        await box.fill(text)
        await asyncio.sleep(0.5)
        logger.info("[文章][微博] 标题已填写(%d 字): %s", len(text), text)

    async def _article_fill_summary(self, page, summary: str):
        text = (summary or "").strip()[: self._ARTICLE_SUMMARY_MAX]
        if not text:
            logger.info("[文章][微博] 未提供导语,跳过")
            return
        box = page.locator('textarea[placeholder*="导语"]').first
        await box.wait_for(state="visible", timeout=15000)
        await box.fill(text)
        await asyncio.sleep(0.5)
        logger.info("[文章][微博] 导语已填写(%d 字): %s", len(text), text)

    async def _article_paste_html(self, page, html: str):
        """把正文 HTML 粘贴进 tiptap/ProseMirror 编辑器。

        实测(2026-10): 通过 ClipboardEvent paste(text/html) 注入,
        h2/p/strong/em/ul/blockquote/img(微博 CDN URL) 均正确解析。
        粘贴后校验正文长度与图片数量。
        """
        from services.article_html import extract_img_srcs

        expect_imgs = len(extract_img_srcs(html))
        length = await page.evaluate(
            """(html) => {
              const ed = document.querySelector('.tiptap.ProseMirror')
                || document.querySelector(
                  '.ProseMirror[contenteditable="true"]');
              if (!ed) return -1;
              ed.focus();
              try {
                const dt = new DataTransfer();
                dt.setData('text/html', html);
                dt.setData('text/plain', html.replace(/<[^>]+>/g, ''));
                ed.dispatchEvent(new ClipboardEvent('paste', {
                  bubbles: true, cancelable: true, clipboardData: dt,
                }));
              } catch (e) {
                return -2;
              }
              return ed.innerHTML.length;
            }""",
            html,
        )
        if length == -1:
            raise RuntimeError("[文章][微博] 未找到正文编辑器(.tiptap.ProseMirror)")
        if length == -2:
            raise RuntimeError("[文章][微博] 正文粘贴事件派发失败")
        await asyncio.sleep(3)
        info = await page.evaluate(
            """() => {
              const ed = document.querySelector('.tiptap.ProseMirror');
              if (!ed) return {html: 0, imgs: 0, text: 0};
              return {
                html: (ed.innerHTML || '').length,
                imgs: ed.querySelectorAll('img').length,
                text: (ed.innerText || '').trim().length,
                imgSrcs: [...ed.querySelectorAll('img')]
                  .map((i) => i.src).slice(0, 20),
              };
            }"""
        )
        logger.info(
            "[文章][微博] 正文已粘贴(innerHTML=%d, 文本=%d, 图片=%d/%d)",
            info.get("html", 0), info.get("text", 0),
            info.get("imgs", 0), expect_imgs,
        )
        if info.get("html", 0) < 20 or info.get("text", 0) < 2:
            raise RuntimeError(
                f"[文章][微博] 正文粘贴后内容过短(innerHTML={info.get('html')}),"
                "粘贴失败"
            )
        if expect_imgs and info.get("imgs", 0) < expect_imgs:
            # 图片可能异步渲染, 再等 5s 复查
            await asyncio.sleep(5)
            imgs2 = await page.evaluate(
                """() => (document.querySelector(
                    '.tiptap.ProseMirror') || {querySelectorAll: () => []})
                  .querySelectorAll('img').length"""
            )
            if imgs2 < expect_imgs:
                raise RuntimeError(
                    f"[文章][微博] 正文图片渲染不完整(期望 {expect_imgs} 张,"
                    f"实际 {imgs2} 张)"
                )
        await asyncio.sleep(1)

    # ---------------- 编辑页设置: 仅粉丝阅读全文 ----------------

    async def _article_set_follow_to_read(self, page, desired_flag: int):
        """编辑页「发布设置 → 其他设置 → 仅粉丝阅读全文」开关。

        该设置保存进 draft.follow_to_read(1=仅粉丝可读全文, 0=公开),
        本账号平台默认=1(开)。失败仅告警(不影响发表), 但会在草稿核对时
        提示实际落库值。
        """
        want = 1 if int(desired_flag) == 1 else 0
        try:
            entry = page.get_by_text("仅粉丝阅读全文", exact=True).first
            if await entry.count() == 0:
                logger.warning(
                    "[文章][微博] 未找到「仅粉丝阅读全文」设置项"
                    "(账号无此能力位),跳过"
                )
                return
            await entry.scroll_into_view_if_needed(timeout=8000)
            state = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const label = [...document.querySelectorAll('*')].find(
                    (el) => vis(el) && el.children.length === 0
                      && (el.innerText || '').trim() === '仅粉丝阅读全文');
                  if (!label) return null;
                  let row = label.parentElement;
                  for (let d = 0; d < 6 && row; d++) {
                    const sw = row.querySelector('.n-switch, .n-checkbox');
                    if (sw) {
                      const r = sw.getBoundingClientRect();
                      return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                              active: sw.classList.contains('n-switch--active')
                                || sw.classList.contains('n-checkbox--checked')
                                || sw.getAttribute('aria-checked') === 'true'
                                || !!sw.querySelector(
                                  '.n-switch__checked, .n-checkbox__checked')};
                    }
                    row = row.parentElement;
                  }
                  return null;
                }"""
            )
            if not state:
                logger.warning(
                    "[文章][微博] 「仅粉丝阅读全文」开关未找到,跳过"
                )
                return
            cur = 1 if state.get("active") else 0
            if cur == want:
                logger.info(
                    "[文章][微博] 仅粉丝阅读全文已是目标值: %s",
                    "开" if want else "关",
                )
                return
            await page.mouse.click(state["x"], state["y"])
            await asyncio.sleep(1.5)
            now_active = await page.evaluate(
                """() => {
                  const label = [...document.querySelectorAll('*')].find(
                    (el) => el.children.length === 0
                      && (el.innerText || '').trim() === '仅粉丝阅读全文');
                  if (!label) return null;
                  let row = label.parentElement;
                  for (let d = 0; d < 6 && row; d++) {
                    const sw = row.querySelector('.n-switch, .n-checkbox');
                    if (sw) {
                      return sw.classList.contains('n-switch--active')
                        || sw.classList.contains('n-checkbox--checked')
                        || sw.getAttribute('aria-checked') === 'true'
                        || !!sw.querySelector(
                          '.n-switch__checked, .n-checkbox__checked');
                    }
                    row = row.parentElement;
                  }
                  return null;
                }"""
            )
            logger.info(
                "[文章][微博] 仅粉丝阅读全文已设置为: %s(当前=%s)",
                "开" if want else "关", now_active,
            )
        except Exception as e:
            logger.warning(
                "[文章][微博] 设置「仅粉丝阅读全文」失败(跳过): %s", e
            )
            await self._article_close_dialogs(page)

    # ---------------- 封面 ----------------

    async def _article_set_cover(self, page, cover_pid: str = ""):
        """设置文章封面(失败仅告警: 平台会自动取上一篇封面兜底)。

        cover_pid: 已上传图床的封面图 pid; 空则取正文首图。
        流程: 点「设置文章封面」→ 图片选择弹窗(正文图片/图片库)
              → 选图 → 「下一步」→ 弹窗关闭即封面已设置。
        """
        try:
            entry = page.get_by_text("设置文章封面", exact=False).first
            if await entry.count() == 0:
                entry = page.get_by_text("替换封面图", exact=False).first
            await entry.scroll_into_view_if_needed(timeout=8000)
            await entry.click(timeout=10000)
            await asyncio.sleep(3)

            # 等图片选择弹窗出现(含「正文图片」「图片库」tab)
            modal_info = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const dialogs = [...document.querySelectorAll(
                      '.n-dialog, .n-modal')].filter(
                    (el) => vis(el) && /正文图片|图片库/.test(el.innerText || ''));
                  return {count: dialogs.length};
                }"""
            )
            if not modal_info.get("count"):
                logger.warning("[文章][微博] 封面弹窗未出现,跳过封面设置")
                return

            if cover_pid:
                # 切到「图片库」tab, 选刚上传的封面图
                clicked_tab = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      for (const el of document.querySelectorAll(
                          '.n-dialog *, .n-modal *')) {
                        if (!vis(el)) continue;
                        if ((el.innerText || '').trim() === '图片库'
                            && el.children.length === 0) {
                          el.click(); return true;
                        }
                      }
                      return false;
                    }"""
                )
                if clicked_tab:
                    await asyncio.sleep(3)
                picked = await page.evaluate(
                    """(pid) => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      const imgs = [...document.querySelectorAll(
                          '.n-dialog img, .n-modal img')].filter(
                        (im) => vis(im) && im.src.includes(pid));
                      if (!imgs.length) return null;
                      const r = imgs[0].getBoundingClientRect();
                      return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }""",
                    cover_pid,
                )
                if not picked:
                    # 兜底: 图片库第一张
                    picked = await page.evaluate(
                        """() => {
                          const vis = (el) => {
                            const r = el.getBoundingClientRect();
                            return r.width > 0 && r.height > 0;
                          };
                          const imgs = [...document.querySelectorAll(
                              '.n-dialog img, .n-modal img')].filter(
                            (im) => vis(im));
                          if (!imgs.length) return null;
                          const r = imgs[0].getBoundingClientRect();
                          return {x: r.x + r.width / 2,
                                  y: r.y + r.height / 2};
                        }"""
                    )
            else:
                # 默认「正文图片」tab, 取第一张
                picked = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      const imgs = [...document.querySelectorAll(
                          '.n-dialog img, .n-modal img')].filter(
                        (im) => vis(im));
                      if (!imgs.length) return null;
                      const r = imgs[0].getBoundingClientRect();
                      return {x: r.x + r.width / 2, y: r.y + r.height / 2};
                    }"""
                )

            if not picked:
                logger.warning("[文章][微博] 封面弹窗内未找到可选图片,跳过封面")
                await self._article_close_dialogs(page)
                return
            await page.mouse.click(picked["x"], picked["y"])
            await asyncio.sleep(2)

            # 点「下一步」确认封面 → 出现「图片裁剪」弹窗 → 点「确定」
            next_btn = page.locator(
                '.n-dialog button:has-text("下一步"), '
                '.n-modal button:has-text("下一步")'
            ).first
            await next_btn.click(timeout=10000)
            await asyncio.sleep(3)
            # 裁剪弹窗(图片裁剪 / 上一步 / 确定)确认; 部分场景无裁剪直接关闭
            crop_confirmed = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const dialogs = [...document.querySelectorAll(
                      '.n-dialog, .n-modal')].filter(
                    (el) => vis(el) && /图片裁剪|裁剪/.test(
                      el.innerText || ''));
                  for (const dlg of dialogs) {
                    for (const b of dlg.querySelectorAll('button')) {
                      if (!vis(b)) continue;
                      if ((b.innerText || '').trim() === '确定'
                          && !b.disabled) {
                        b.click();
                        return true;
                      }
                    }
                  }
                  return false;
                }"""
            )
            if crop_confirmed:
                logger.info("[文章][微博] 已确认封面裁剪")
            await asyncio.sleep(3)
            # 等裁剪弹窗真正关闭(遮罩会拦截后续点击)
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                raise_if_page_closed(page, action="文章发布")
                still = await page.evaluate(
                    """() => [...document.querySelectorAll(
                        '.n-dialog, .n-modal')].some((el) => {
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0
                        && /图片裁剪|正文图片|图片库/.test(el.innerText || '');
                    })"""
                )
                if not still:
                    break
                await asyncio.sleep(1)
            logger.info("[文章][微博] 封面已设置")
            await self._article_close_dialogs(page)
        except Exception as e:
            logger.warning("[文章][微博] 封面设置失败(跳过): %s", e)
            await self._article_close_dialogs(page)

    @staticmethod
    async def _article_close_dialogs(page):
        """关闭可能残留的弹层(遮罩会拦截后续点击)。"""
        for _ in range(3):
            try:
                closed = await page.evaluate(
                    """() => {
                      const vis = (el) => {
                        const r = el.getBoundingClientRect();
                        return r.width > 0 && r.height > 0;
                      };
                      for (const b of document.querySelectorAll(
                          '.n-dialog button, .n-modal button')) {
                        if (!vis(b)) continue;
                        const t = (b.innerText || '').trim();
                        if (t === '取消' || t === '关闭') {
                          b.click(); return true;
                        }
                      }
                      return false;
                    }"""
                )
                if not closed:
                    await page.keyboard.press("Escape")
                await asyncio.sleep(0.6)
                still = await page.evaluate(
                    """() => [...document.querySelectorAll(
                        '.n-dialog, .n-modal')].some((el) => {
                      const r = el.getBoundingClientRect();
                      return r.width > 0 && r.height > 0
                        && /正文图片|图片库|发布/.test(el.innerText || '');
                    })"""
                )
                if not still:
                    return
            except Exception:
                return

    # ---------------- 草稿保存 / 核对 ----------------

    async def _article_save_draft(self, page, results):
        """点「保存草稿」按钮, 等 draft/save 接口返回 code==100000。"""
        results["save"].clear()
        # 先关掉可能残留的弹层(弹层遮罩会拦截按钮点击)
        await self._article_close_dialogs(page)
        btn = page.get_by_role("button", name="保存草稿", exact=True).first
        try:
            await btn.scroll_into_view_if_needed(timeout=8000)
            await btn.click(timeout=15000)
        except Exception as e:
            logger.warning(
                "[文章][微博] 「保存草稿」常规点击失败,改用 JS 点击: %s", e
            )
            clicked = await page.evaluate(
                """() => {
                  for (const b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim() === '保存草稿') {
                      b.click(); return true;
                    }
                  }
                  return false;
                }"""
            )
            if not clicked:
                raise RuntimeError("[文章][微博] 未找到「保存草稿」按钮")
        logger.info("[文章][微博] 已点击「保存草稿」,等待保存接口...")
        deadline = asyncio.get_event_loop().time() + 60
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            if results["save"]:
                body = results["save"][-1]
                code = body.get("code") if isinstance(body, dict) else None
                msg = (body or {}).get("msg", "") if isinstance(body, dict) else ""
                if code == self._ARTICLE_OK_CODE:
                    data = body.get("data") or {}
                    logger.info(
                        "[文章][微博] ✓ 草稿已保存(code=%s, content_length=%s)",
                        code, data.get("content_length"),
                    )
                    await asyncio.sleep(1)
                    return
                raise RuntimeError(
                    f"[文章][微博] 草稿保存失败 code={code} msg={msg}"
                )
            await asyncio.sleep(1)
        raise RuntimeError("[文章][微博] 保存草稿超时(未收到 draft/save 响应)")

    async def _article_verify_draft(self, page, draft_id, title, summary, html,
                                    expected_follow_to_read=None):
        """用草稿加载接口核对标题/导语/正文/封面/仅粉丝阅读全文已落库。"""
        uid, _ = await self._article_get_uid_nick(page)
        try:
            verify = await page.evaluate(
                """async (payload) => {
                  const resp = await fetch(
                    '/article/v5/aj/editor/draft/load?uid='
                    + encodeURIComponent(payload.uid)
                    + '&id=' + encodeURIComponent(payload.id),
                    {credentials: 'include'});
                  return await resp.json();
                }""",
                {"uid": uid, "id": draft_id},
            )
        except Exception as e:
            logger.warning("[文章][微博] 草稿核对请求失败(非致命): %s", e)
            return
        try:
            data = (verify or {}).get("data") or {}
            saved_title = (data.get("title") or "").strip()
            saved_summary = (data.get("summary") or "").strip()
            saved_content = data.get("content") or ""
            logger.info(
                "[文章][微博] 草稿核对: code=%s 标题=%r 导语=%r 正文长度=%d"
                " 封面=%s 仅粉丝阅读全文=%s",
                (verify or {}).get("code"), saved_title[:40],
                saved_summary[:44], len(saved_content),
                (data.get("cover") or "")[:80] or "无",
                data.get("follow_to_read"),
            )
            if saved_title != title[: self._ARTICLE_TITLE_MAX]:
                logger.warning(
                    "[文章][微博] 草稿标题与预期不一致: %r != %r",
                    saved_title, title[: self._ARTICLE_TITLE_MAX],
                )
            if expected_follow_to_read is not None:
                saved_ftr = data.get("follow_to_read")
                try:
                    saved_ftr = int(saved_ftr)
                except (TypeError, ValueError):
                    saved_ftr = None
                if saved_ftr != int(expected_follow_to_read):
                    logger.warning(
                        "[文章][微博] 草稿「仅粉丝阅读全文」与预期不一致: "
                        "预期=%s 实际=%s",
                        int(expected_follow_to_read), saved_ftr,
                    )
                else:
                    logger.info(
                        "[文章][微博] ✓ 草稿「仅粉丝阅读全文」已生效: %s",
                        "开" if saved_ftr == 1 else "关",
                    )
            if not saved_content:
                raise RuntimeError("[文章][微博] 草稿正文为空,保存未生效")
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning("[文章][微博] 草稿核对解析失败(非致命): %s", e)

    # ---------------- 下一步 / 发布弹窗 / 发表 ----------------

    async def _article_click_next(self, page):
        """点「下一步」→ 等发布弹窗;若跳转微博身份验证, 等人工处理。

        平台逻辑(编辑器 bundle DraftFooter):
          1) 首次点击: setDefaultCover() 若自动选了上一篇封面 → 只把页面
             滚到「发布设置」区, 需要再点一次「下一步」;
          2) 第二次: validatePublish → saveDraft(action=2)。该接口可能返回
             data.geetest.verifyUrl → 前端跳 security.weibo.com 身份验证;
          3) 签约自媒体(is_wemedia_memeber)首次发表还会弹「头条文章原创声明」
             协议弹窗, 需点「我同意」后才继续;
          4) 之后才弹出发布弹窗(publish-modal)。
        """
        for attempt in range(3):
            btn = page.get_by_role("button", name="下一步", exact=True).first
            await btn.wait_for(state="visible", timeout=15000)
            await btn.click()
            logger.info("[文章][微博] 已点击「下一步」(第 %d 次)", attempt + 1)

            captcha_waited = False
            deadline = asyncio.get_event_loop().time() + 60
            while asyncio.get_event_loop().time() < deadline:
                raise_if_page_closed(page, action="文章发布")
                url = page.url or ""
                if "security.weibo.com" in url or "/captcha" in url:
                    if captcha_waited:
                        raise RuntimeError(
                            "[文章][微博] 身份验证通过后再次跳转验证页,放弃发表"
                        )
                    captcha_waited = True
                    await self._article_wait_captcha(page)
                    # 验证通过后页面自动回到编辑器并重跑下一步逻辑
                    deadline = asyncio.get_event_loop().time() + 90
                    continue
                # 原创声明协议弹窗(签约自媒体首次发表时出现)
                if await self._article_accept_original_agreement(page):
                    continue
                if await self._article_publish_modal_visible(page):
                    logger.info("[文章][微博] 发布弹窗已出现")
                    return
                await asyncio.sleep(1.5)

            # 未出现弹窗/验证页: 平台可能只是自动选了默认封面并滚动到
            # 发布设置区(setDefaultCover 返回 true), 再点一次「下一步」
            logger.info(
                "[文章][微博] 第 %d 次「下一步」未出现弹窗(可能自动选封面),重试",
                attempt + 1,
            )

        raise RuntimeError(
            "[文章][微博] 点击「下一步」后未出现发布弹窗"
            f"(当前 URL: {page.url})"
        )

    async def _article_accept_original_agreement(self, page) -> bool:
        """处理「头条文章原创声明」协议弹窗(签约自媒体首次发表)。

        出现则点「我同意」并返回 True; 未出现返回 False。
        """
        try:
            clicked = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const dlg = [...document.querySelectorAll(
                      '.n-dialog, .n-modal')].find(
                    (el) => vis(el)
                      && (el.innerText || '').includes('头条文章原创声明'));
                  if (!dlg) return false;
                  for (const b of dlg.querySelectorAll('button')) {
                    if (!vis(b)) continue;
                    if ((b.innerText || '').trim() === '我同意') {
                      b.click();
                      return true;
                    }
                  }
                  return false;
                }"""
            )
            if clicked:
                logger.info("[文章][微博] 已同意「头条文章原创声明」协议")
                await asyncio.sleep(1.5)
                return True
        except Exception:
            pass
        return False

    async def _article_wait_captcha(self, page):
        """微博身份验证(geetest)人工处理等待。

        发表前校验触发风控时, 浏览器会跳转 security.weibo.com 验证页;
        有头浏览器下等待用户完成验证(默认最多 5 分钟), 完成后页面会
        自动跳回编辑器继续。超时如实报失败(风控拦截按失败记录)。
        """
        logger.warning(
            "[文章][微博] ⚠ 触发微博身份验证(风控 geetest),请在有头浏览器"
            "中完成验证(最多等待 %ds)...",
            self._ARTICLE_CAPTCHA_TIMEOUT,
        )
        # 留证: 风控验证页截图(便于排查/汇报)
        await self._article_screenshot(page, "weibo_article_captcha.png")
        start = asyncio.get_event_loop().time()
        last_log = start
        while asyncio.get_event_loop().time() - start < self._ARTICLE_CAPTCHA_TIMEOUT:
            raise_if_page_closed(page, action="文章发布")
            url = page.url or ""
            if "card.weibo.com" in url and "security.weibo.com" not in url:
                logger.info("[文章][微博] 身份验证已通过,继续发表流程")
                await asyncio.sleep(3)
                return
            now = asyncio.get_event_loop().time()
            if now - last_log >= 15:
                last_log = now
                logger.info(
                    "[文章][微博] 仍在等待人工完成身份验证(已等待 %ds)...",
                    int(now - start),
                )
            await asyncio.sleep(2)
        await self._article_screenshot(page, "weibo_article_publish_failed.png")
        raise RuntimeError(
            "[文章][微博] 发表触发微博身份验证(风控 geetest),"
            f"等待人工处理超时({self._ARTICLE_CAPTCHA_TIMEOUT}s) —— 文章未发表"
        )

    @staticmethod
    async def _article_publish_modal_visible(page) -> bool:
        try:
            return await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      '.publish-modal, .n-modal')].some(
                    (el) => vis(el) && (el.innerText || '').includes('发布'));
                }"""
            )
        except Exception:
            return False

    async def _article_publish(self, page, results, title, summary,
                               topics, statement, weibo_text="", rank=0,
                               is_original=False, follow_official=True,
                               sync_wb=None, schedule_time_str=""):
        """发布弹窗内: 填微博正文/发布范围/内容声明/原创/关注/定时 → 点「发布」。

        控件来自编辑器 bundle 的 PublishModal(2026-10 逐项还原):
          textarea(微博正文, 必填, maxlength=2000) / WbSetting(公开·粉丝 +
          内容声明) / publish-time(定时) / 原创声明 / 关注@头条文章 /
          同步到微博(仅 super_topic) / 发布按钮。
        """
        # 1. 微博正文(必填, 空则「发布」按钮 disabled)
        tag_text = " ".join(f"#{t}#" for t in (topics or []) if t)
        if weibo_text:
            base_text = weibo_text.strip()
            if tag_text and tag_text not in base_text:
                base_text = f"{base_text} {tag_text}"
        else:
            base_text = f"发布了头条文章：《{title}》"
            if tag_text:
                base_text = f"{base_text} {tag_text}"
        base_text = base_text[: self._ARTICLE_WEIBO_TEXT_MAX]
        texts = await page.evaluate(
            """(text) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const scope = [...document.querySelectorAll(
                  '.publish-modal, .n-modal')].find(
                (el) => vis(el) && (el.innerText || '').includes('发布'));
              if (!scope) return null;
              const ta = [...scope.querySelectorAll('textarea')]
                .filter(vis)[0];
              if (!ta) return null;
              const setter = Object.getOwnPropertyDescriptor(
                window.HTMLTextAreaElement.prototype, 'value').set;
              setter.call(ta, text);
              ta.dispatchEvent(new Event('input', {bubbles: true}));
              ta.dispatchEvent(new Event('change', {bubbles: true}));
              return {value: ta.value, maxlength: ta.maxLength};
            }""",
            base_text,
        )
        if not texts:
            raise RuntimeError(
                "[文章][微博] 发布弹窗未找到「微博正文」输入框"
            )
        final_text = (texts.get("value") or "").strip()
        logger.info(
            "[文章][微博] 发布弹窗微博正文已填写(%d 字, 上限 %s): %s",
            len(final_text), texts.get("maxlength"), final_text[:120],
        )
        if not final_text:
            raise RuntimeError(
                "[文章][微博] 发布弹窗「微博正文」为空,发布按钮不可用"
            )

        # 2. 发布范围(公开/粉丝) + 内容声明
        #    平台联动: 内容声明只在「公开」项下, 选择内容声明会同时把发布
        #    范围置为公开; 选「粉丝」时内容声明被重置为「无」→ 二者互斥
        statement = (statement or "").strip()
        if statement == "无":
            statement = ""
        if statement or rank:
            await self._article_set_wb_setting(page, statement, rank)

        # 3. 原创声明(仅签约自媒体账号有控件)
        if is_original:
            await self._article_set_original(page, True)

        # 4. 关注@头条文章(默认勾选; 已关注的账号平台隐藏该控件)
        await self._article_set_follow_official(page, follow_official)

        # 5. 同步到微博(仅 super_topic 类型草稿显示该开关)
        if sync_wb is not None:
            changed = await self._article_set_sync_wb(page, bool(sync_wb))
            if not changed:
                logger.info(
                    "[文章][微博] 发布弹窗无「同步到微博」开关"
                    "(仅 super_topic 草稿有), 忽略"
                )

        # 6. 定时发布(账号开关位支持时才显示 publish-time 图标)
        scheduled = False
        if schedule_time_str:
            scheduled = await self._article_set_timing(
                page, schedule_time_str
            )
            if not scheduled:
                raise RuntimeError(
                    "[文章][微博] 请求了定时发布, 但发布弹窗没有「定时发布」"
                    "控件(账号 switch 位不支持或自动化失败), 已中止以免误发表"
                )

        # 7. 点「发布」并监听发表 API
        if manual_review_enabled('weibo', 'article'):
            # 人工验收：保留发布弹窗，等待用户亲自点击「发布」；
            # 成功判定与自动分支一致(发表接口 code==100000)，
            # 回调只读 results(由页面 response 监听器填充)，不做任何点击
            async def _manual_article_success(_page):
                if not results["publish"]:
                    return False
                body = results["publish"][-1]
                return (
                    isinstance(body, dict)
                    and body.get("code") == self._ARTICLE_OK_CODE
                )

            await wait_for_manual_publish(
                page, 'weibo', success_check=_manual_article_success
            )
            return

        await self._article_click_publish(page, results, scheduled=scheduled)

    # ---- 发布弹窗控件定位/操作 ----

    @staticmethod
    async def _article_modal_dismiss_popovers(page):
        """关闭发布弹窗内的浮层(下拉/日历/表情)。

        注意: **不能用 Escape** —— 发布弹窗是 n-modal, 默认 close-on-esc,
        Escape 会把整个发布弹窗关掉(实测踩坑)。改点击遮罩空白处: 该弹窗
        mask-closable=false, 点遮罩不会关弹窗, 但会触发浮层的 clickoutside。
        """
        try:
            await page.mouse.move(5, 5)
            await page.mouse.click(5, 5)
            await asyncio.sleep(0.4)
        except Exception:
            pass

    @staticmethod
    async def _article_modal_wb_trigger(page):
        """发布弹窗 WbSetting 触发器(公开/粉丝)坐标。"""
        return await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const scope = [...document.querySelectorAll(
                  '.publish-modal, .n-modal')].find(
                (el) => vis(el) && (el.innerText || '').includes('发布'));
              if (!scope) return null;
              const el = [...scope.querySelectorAll('*')].find(
                (n) => vis(n) && n.children.length === 0
                  && ['公开', '粉丝'].includes((n.innerText || '').trim()));
              if (!el) return null;
              const r = el.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                      text: (el.innerText || '').trim()};
            }"""
        )

    @staticmethod
    async def _article_dropdown_visible(page):
        try:
            return await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  return [...document.querySelectorAll(
                      '.publish-dropdown, [class*="publish-dropdown"]')]
                    .some((el) => vis(el));
                }"""
            )
        except Exception:
            return False

    @staticmethod
    async def _article_dropdown_item_rect(page, label):
        """WbSetting 下拉项(公开/粉丝)坐标。"""
        return await page.evaluate(
            """(label) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const items = [...document.querySelectorAll(
                  '.publish-dropdown__item')].filter(
                (el) => vis(el)
                  && (el.innerText || '').indexOf(label) === 0);
              if (!items.length) return null;
              const r = items[0].getBoundingClientRect();
              return {x: r.x + 20, y: r.y + r.height / 2};
            }""",
            label,
        )

    @staticmethod
    async def _article_dropdown_extend_rect(page, item_label):
        """WbSetting 下拉项右侧「内容声明」入口坐标(悬停展开子菜单)。"""
        return await page.evaluate(
            """(label) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const items = [...document.querySelectorAll(
                  '.publish-dropdown__item')].filter(
                (el) => vis(el)
                  && (el.innerText || '').indexOf(label) === 0);
              if (!items.length) return null;
              const right = items[0].querySelector('.right');
              if (!right) return null;
              const r = right.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }""",
            item_label,
        )

    @staticmethod
    async def _article_statement_option_rect(page, target):
        """「内容声明」子菜单选项坐标。"""
        return await page.evaluate(
            """(target) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const items = [...document.querySelectorAll(
                  '.extend-box__content__item')].filter(
                (el) => vis(el)
                  && (el.innerText || '').trim() === target);
              if (!items.length) return null;
              const r = items[0].getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }""",
            target,
        )

    @staticmethod
    async def _article_switch_rect(page, label, match="equals"):
        """发布弹窗内「label + 开关」行里的开关坐标/状态。

        label 文案定位到叶子节点后向上找 .n-switch / .n-checkbox。
        match="contains" 用于长文案(原创声明协议)。
        """
        return await page.evaluate(
            """(payload) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const scope = [...document.querySelectorAll(
                  '.publish-modal, .n-modal')].find(
                (el) => vis(el) && (el.innerText || '').includes('发布'));
              if (!scope) return null;
              const eq = payload.match === 'equals';
              const matches = [...scope.querySelectorAll('*')].filter((el) => {
                if (!vis(el)) return false;
                const t = (el.innerText || '').trim();
                if (eq ? t !== payload.label : !t.includes(payload.label)) {
                  return false;
                }
                if (eq) return true;
                // contains 模式取最深匹配(排除其子元素也含该文案的祖先容器),
                // 兼容「我同意《…协议》，并声明本文是原创作品」这种带链接的行
                return ![...el.children].some(
                  (c) => ((c.innerText || '').trim().includes(payload.label)));
              });
              if (!matches.length) return null;
              let row = matches[0].parentElement;
              for (let d = 0; d < 6 && row; d++) {
                const sw = row.querySelector('.n-switch, .n-checkbox');
                if (sw) {
                  const r = sw.getBoundingClientRect();
                  return {
                    x: r.x + r.width / 2, y: r.y + r.height / 2,
                    active: sw.classList.contains('n-switch--active')
                      || sw.classList.contains('n-checkbox--checked')
                      || !!sw.querySelector(
                        '.n-switch__checked, .n-checkbox__checked'),
                  };
                }
                row = row.parentElement;
              }
              return null;
            }""",
            {"label": label, "match": match},
        )

    async def _article_set_wb_setting(self, page, statement: str, rank: int):
        """发布弹窗 WbSetting: 发布范围(公开/粉丝) + 内容声明。

        实测联动(编辑器 bundle wb-setting.vue):
          - 下拉触发器显示当前范围(公开/粉丝), hover 展开;
          - 「内容声明」是「公开」项的二级子菜单, 悬停其右侧入口展开;
          - 选内容声明会把发布范围重置为「公开」; 选「粉丝」则内容声明归零。
        """
        desired_rank = int(rank or 0)
        target_statement = ""
        if statement:
            target_statement = statement
            if target_statement not in self._ARTICLE_STATEMENT_MAP:
                for key in self._ARTICLE_STATEMENT_MAP:
                    if key in target_statement or target_statement in key:
                        target_statement = key
                        break
        if desired_rank == 10 and target_statement:
            logger.warning(
                "[文章][微博] 平台限制: 发布范围「粉丝」与内容声明互斥"
                "(选内容声明会强制公开), 已忽略内容声明=%s", target_statement,
            )
            target_statement = ""
        target_scope = "粉丝" if desired_rank == 10 else "公开"
        logger.info(
            "[文章][微博] 发布弹窗设置: 发布范围=%s 内容声明=%s",
            target_scope, target_statement or "无",
        )

        # 1) hover 触发器展开下拉
        trig = await self._article_modal_wb_trigger(page)
        if not trig:
            raise RuntimeError("未找到发布范围/内容声明入口(公开/粉丝)")
        await page.mouse.move(trig["x"], trig["y"])
        await asyncio.sleep(1.2)
        if not await self._article_dropdown_visible(page):
            # 再 hover 一次(首次 hover 可能只触发了 tooltip 动画)
            await page.mouse.move(trig["x"] + 2, trig["y"] + 2)
            await asyncio.sleep(1.5)
        if not await self._article_dropdown_visible(page):
            raise RuntimeError("发布弹窗 WbSetting 下拉未展开")
        logger.info(
            "[文章][微博] WbSetting 下拉已展开(当前范围=%s)", trig["text"]
        )

        # 2) 发布范围
        if trig["text"] != target_scope:
            item = await self._article_dropdown_item_rect(page, target_scope)
            if not item:
                raise RuntimeError(f"未找到发布范围选项: {target_scope}")
            await page.mouse.move(item["x"], item["y"])
            await asyncio.sleep(0.5)
            await page.mouse.click(item["x"], item["y"])
            await asyncio.sleep(1.2)
            logger.info(
                "[文章][微博] 发布范围已设置为: %s", target_scope
            )
        else:
            logger.info("[文章][微博] 发布范围已是目标值: %s", target_scope)

        # 3) 内容声明(公开项二级子菜单; 设置后发布范围=公开)
        if target_statement:
            if target_scope == "粉丝":
                # 上一步已切到粉丝, 下拉已关闭; 重新 hover 触发器
                pass
            trig2 = await self._article_modal_wb_trigger(page)
            if not trig2:
                raise RuntimeError("未找到发布范围/内容声明入口(公开/粉丝)")
            if not await self._article_dropdown_visible(page):
                await page.mouse.move(trig2["x"], trig2["y"])
                await asyncio.sleep(1.5)
            entry = await self._article_dropdown_extend_rect(page, "公开")
            if not entry:
                raise RuntimeError("未找到内容声明入口(公开项右侧)")
            await page.mouse.move(entry["x"], entry["y"])
            await asyncio.sleep(1.2)
            opt = await self._article_statement_option_rect(
                page, target_statement
            )
            if not opt:
                await asyncio.sleep(1.5)
                opt = await self._article_statement_option_rect(
                    page, target_statement
                )
            if not opt:
                raise RuntimeError(
                    f"未找到内容声明选项: {target_statement}"
                )
            await page.mouse.move(opt["x"], opt["y"])
            await asyncio.sleep(0.3)
            await page.mouse.click(opt["x"], opt["y"])
            await asyncio.sleep(1.0)
            logger.info(
                "[文章][微博] 内容声明已设置为: %s(发布范围联动为公开)",
                target_statement,
            )

        # 4) 关闭下拉, 避免遮罩拦截「发布」点击
        await self._article_modal_dismiss_popovers(page)

    async def _article_set_original(self, page, desired: bool):
        """原创声明(仅签约自媒体 is_wemedia_memeber 显示)。

        文案:「我同意《微博签约媒体原创认证协议》，并声明本文是原创作品」。
        非签约账号无该控件 → 告警跳过(不阻塞发表)。
        """
        await self._article_modal_dismiss_popovers(page)
        state = await self._article_switch_rect(
            page, "并声明本文是原创作品", match="contains"
        )
        if not state:
            logger.warning(
                "[文章][微博] 发布弹窗无「原创声明」控件"
                "(账号非签约自媒体), 跳过原创声明"
            )
            return
        cur = bool(state.get("active"))
        if cur == bool(desired):
            logger.info(
                "[文章][微博] 原创声明已是目标值: %s",
                "开" if desired else "关",
            )
            return
        await page.mouse.click(state["x"], state["y"])
        await asyncio.sleep(1.2)
        logger.info(
            "[文章][微博] 原创声明已设置为: %s", "开" if desired else "关"
        )

    async def _article_set_follow_official(self, page, desired: bool):
        """「关注@头条文章 第一时间获取官方通知」勾选框(默认勾选)。

        账号已关注时平台隐藏该控件 → 视为已满足, 无需操作。
        """
        state = await self._article_switch_rect(
            page, "关注@头条文章", match="contains"
        )
        if not state:
            logger.info(
                "[文章][微博] 发布弹窗无「关注@头条文章」勾选项"
                "(账号已关注, 平台隐藏), 无需设置"
            )
            return
        cur = bool(state.get("active"))
        if cur == bool(desired):
            logger.info(
                "[文章][微博] 关注@头条文章已是目标值: %s",
                "开" if desired else "关",
            )
            return
        await page.mouse.click(state["x"], state["y"])
        await asyncio.sleep(1.0)
        logger.info(
            "[文章][微博] 关注@头条文章已设置为: %s",
            "开" if desired else "关",
        )

    async def _article_set_sync_wb(self, page, desired: bool) -> bool:
        """「同步到微博」开关(仅 super_topic 类型草稿显示)。返回是否有控件。"""
        state = await self._article_switch_rect(
            page, "同步到微博", match="contains"
        )
        if not state:
            return False
        cur = bool(state.get("active"))
        if cur != bool(desired):
            await page.mouse.click(state["x"], state["y"])
            await asyncio.sleep(1.0)
        logger.info(
            "[文章][微博] 同步到微博已设置为: %s",
            "开" if desired else "关",
        )
        return True

    async def _article_set_timing(self, page, schedule_time_str: str) -> bool:
        """发布弹窗「定时发布」: 日期(今~+7天) + 时 + 分。

        平台实现(timing-setting.vue): 日期 n-date-picker(禁用今天之前/
        今天+7天之后) + 时/分 n-select(00-23时 / 00-59分), 默认
        server_time+15min; 输出 "YYYY-MM-DD HH:mm"。发表接口切换为
        /draft/publishtiming, 请求带 time 与 timestamp(时区偏移小时)。
        返回 False 表示弹窗里没有该控件(账号 switch 位不支持)。
        """
        # 解析目标时间
        target_dt = None
        raw = (schedule_time_str or "").strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M",
                    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
            try:
                target_dt = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if target_dt is None:
            logger.warning(
                "[文章][微博] 定时时间格式无法解析(%r), 使用平台默认"
                "(server_time+15min)", raw,
            )
        else:
            now = datetime.now()
            if target_dt < now:
                logger.warning(
                    "[文章][微博] 定时时间(%s)早于当前时间,平台可能拒绝",
                    target_dt.strftime("%Y-%m-%d %H:%M"),
                )
            if target_dt.date() > (now + timedelta(
                    days=self._ARTICLE_TIMING_MAX_DAYS)).date():
                logger.warning(
                    "[文章][微博] 定时时间(%s)超出平台范围(今天~+%d天)",
                    target_dt.strftime("%Y-%m-%d"), self._ARTICLE_TIMING_MAX_DAYS,
                )

        # 1) 点「定时发布」图标
        #    工具栏 .tools-icon 顺序(编辑器 bundle PublishModal 渲染顺序):
        #    表情 / @ / # / 定时(仅账号 switch 位支持时存在)
        tools = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const scope = [...document.querySelectorAll(
                  '.publish-modal, .n-modal')].find(
                (el) => vis(el) && (el.innerText || '').includes('发布'));
              if (!scope) return [];
              return [...scope.querySelectorAll('.tools-icon')].filter(vis)
                .map((el) => {
                  const r = el.getBoundingClientRect();
                  return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                          active: String(el.className).includes('active')};
                });
            }"""
        )
        if len(tools) < 3:
            logger.warning(
                "[文章][微博] 发布弹窗工具栏只有 %d 个图标, 无「定时发布」"
                "图标(账号 switch 位不支持定时)", len(tools),
            )
            return False
        exists = False
        for idx in [3, 2, 1, 0]:
            if idx >= len(tools):
                continue
            await self._article_modal_dismiss_popovers(page)
            await page.mouse.click(tools[idx]["x"], tools[idx]["y"])
            await asyncio.sleep(1.2)
            exists = await page.evaluate(
                """() => {
                  const el = document.querySelector(
                      '.publish-modal .timing-setting, '
                      + '.n-modal .timing-setting');
                  if (!el) return false;
                  const r = el.getBoundingClientRect();
                  return r.width > 0 && r.height > 0;
                }"""
            )
            if exists:
                logger.info(
                    "[文章][微博] 定时发布控件已展开(工具栏图标 index=%d)", idx
                )
                break
        if not exists:
            logger.warning(
                "[文章][微博] 未找到「定时发布」图标/点击后未出现定时控件"
                "(账号 switch 位不支持定时或 UI 改版)"
            )
            return False
        logger.info(
            "[文章][微博] 定时发布控件已展开, 默认时间=%s",
            (await page.evaluate(
                """() => {
                  const el = document.querySelector(
                      '.publish-modal .timing-setting, '
                      + '.n-modal .timing-setting');
                  return el ? (el.innerText || '').replace(/\\s+/g, ' ') : '';
                }"""
            )),
        )

        # 2) 设置日期: naive-ui n-date-picker 输入框不可编辑, 走日历面板
        #    (.n-date-panel) 翻月 + 点日期格子; 平台只允许今天~+7 天
        if target_dt is not None:
            await self._article_pick_date(page, target_dt.date())
            await asyncio.sleep(0.8)

        # 3) 设置时/分(两个 n-select)
        async def _pick_select(index: int, label: str) -> bool:
            boxes = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const el = document.querySelector(
                      '.publish-modal .timing-setting, '
                      + '.n-modal .timing-setting');
                  if (!el) return [];
                  return [...el.querySelectorAll('.n-select')].filter(vis)
                    .map((s) => {
                      const r = s.getBoundingClientRect();
                      return {x: r.x + r.width / 2,
                              y: r.y + r.height / 2,
                              text: (s.innerText || '').trim()};
                    });
                }"""
            )
            if len(boxes) <= index:
                return False
            box = boxes[index]
            if (box.get("text") or "") == label:
                return True
            await page.mouse.click(box["x"], box["y"])
            await asyncio.sleep(1.0)
            picked = await page.evaluate(
                """(label) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const opt = [...document.querySelectorAll(
                      '.n-base-select-option')].filter(
                    (el) => vis(el)
                      && (el.innerText || '').trim() === label)[0];
                  if (!opt) return false;
                  opt.click();
                  return true;
                }""",
                label,
            )
            await asyncio.sleep(0.8)
            return bool(picked)

        if target_dt is not None:
            hour_label = f"{target_dt.hour:02d}时"
            minute_label = f"{target_dt.minute:02d}分"
            ok_h = await _pick_select(0, hour_label)
            ok_m = await _pick_select(1, minute_label)
            if not ok_h or not ok_m:
                logger.warning(
                    "[文章][微博] 定时「时/分」选择失败(时=%s 分=%s),"
                    "将使用平台默认时间", ok_h, ok_m,
                )

        # 4) 读取最终定时值并严格校验(避免时间设置失败却按错误时间发表)
        final = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const el = document.querySelector(
                  '.publish-modal .timing-setting, '
                  + '.n-modal .timing-setting');
              if (!el) return null;
              const inputs = [...el.querySelectorAll('input')]
                .filter(vis).map((i) => i.value);
              const selects = [...el.querySelectorAll('.n-select')]
                .filter(vis).map((s) => (s.innerText || '').trim());
              return {inputs, selects,
                      text: (el.innerText || '').replace(/\\s+/g, ' ')};
            }"""
        )
        if not final:
            raise RuntimeError("[文章][微博] 定时设置控件已消失, 中止发表")
        logger.info(
            "[文章][微博] 定时发布已设置: %s", final.get("text") or final
        )
        if target_dt is not None:
            shown_date = ""
            for v in final.get("inputs") or []:
                if v and re.match(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$", v):
                    shown_date = v.replace("/", "-")
                    break
            expect_date = target_dt.strftime("%Y-%m-%d")
            if shown_date != expect_date:
                raise RuntimeError(
                    "[文章][微博] 定时日期未生效: 期望=%s 实际=%r,"
                    "已中止发表(避免错误时间发表)"
                    % (expect_date, shown_date or (final.get("inputs") or [""])[0])
                )
            shown_sel = " ".join(final.get("selects") or [])
            expect_sel = f"{target_dt.hour:02d}时 {target_dt.minute:02d}分"
            if shown_sel != expect_sel:
                raise RuntimeError(
                    "[文章][微博] 定时时分未生效: 期望=%s 实际=%r,"
                    "已中止发表(避免错误时间发表)" % (expect_sel, shown_sel)
                )
        return True

    async def _article_pick_date(self, page, target_date):
        """在 n-date-picker 日历面板里选目标日期(逐月翻页 + 点日期格)。

        面板结构(naive-ui DatePanel): .n-date-panel > .n-date-panel-calendar >
        .n-date-panel-month(__prev/__next 翻月, PanelHeader 显示 yyyy年M月) +
        .n-date-panel-dates > .n-date-panel-date(当前月日期)。
        """
        # 1) 点日期输入框展开日历面板
        input_rect = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const el = document.querySelector(
                  '.publish-modal .timing-setting, '
                  + '.n-modal .timing-setting');
              if (!el) return null;
              const input = [...el.querySelectorAll('input')].filter(vis)[0];
              if (!input) return null;
              const r = input.getBoundingClientRect();
              return {x: r.x + r.width / 2, y: r.y + r.height / 2};
            }"""
        )
        if not input_rect:
            raise RuntimeError("[文章][微博] 未找到定时日期输入框")
        await page.mouse.click(input_rect["x"], input_rect["y"])
        await asyncio.sleep(1.2)

        # 2) 翻到目标年月
        target_ym = (target_date.year, target_date.month)
        for _ in range(24):
            shown = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const panel = [...document.querySelectorAll(
                      '.n-date-panel')].filter(vis).pop();
                  if (!panel) return null;
                  const month = panel.querySelector('.n-date-panel-month');
                  return month ? (month.innerText || '').trim() : '';
                }"""
            )
            if shown is None:
                raise RuntimeError("[文章][微博] 定时日期日历面板未出现")
            nums = re.findall(r"\d+", shown)
            year = month = None
            for i, n in enumerate(nums):
                if len(n) == 4 and year is None:
                    year = int(n)
                elif len(n) <= 2 and i > 0 and month is None and year is not None:
                    month = int(n)
            if year is None or month is None:
                # locale 文案差异兜底: "2026年10月"
                m = re.search(r"(\d{4})\D+(\d{1,2})", shown)
                if m:
                    year, month = int(m.group(1)), int(m.group(2))
            if year == target_ym[0] and month == target_ym[1]:
                logger.info("[文章][微博] 定时日历已翻到: %s", shown)
                break
            if year is None or month is None:
                raise RuntimeError(
                    f"[文章][微博] 无法解析日历年月: {shown!r}"
                )
            cur = year * 12 + month
            want = target_ym[0] * 12 + target_ym[1]
            sel = ("__next" if want > cur else "__prev")
            moved = await page.evaluate(
                """(sel) => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const panel = [...document.querySelectorAll(
                      '.n-date-panel')].filter(vis).pop();
                  if (!panel) return false;
                  const btn = panel.querySelector(
                      '.n-date-panel-month' + sel);
                  if (!btn) return false;
                  btn.click();
                  return true;
                }""",
                sel,
            )
            if not moved:
                raise RuntimeError("[文章][微博] 无法翻动定时日历月份")
            await asyncio.sleep(0.7)

        # 3) 点目标日期格子(排除非当前月/禁用)
        picked = await page.evaluate(
            """(payload) => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const panel = [...document.querySelectorAll(
                  '.n-date-panel')].filter(vis).pop();
              if (!panel) return {ok: false, err: 'no panel'};
              const cells = [...panel.querySelectorAll('.n-date-panel-date')];
              const target = cells.find((el) => {
                if (!vis(el)) return false;
                const cls = String(el.className || '');
                if (cls.includes('--excluded') || cls.includes('--disabled')) {
                  return false;
                }
                return (el.innerText || '').trim() === String(payload.day);
              });
              if (!target) return {ok: false, err: 'no cell'};
              const r = target.getBoundingClientRect();
              return {ok: true, x: r.x + r.width / 2,
                      y: r.y + r.height / 2};
            }""",
            {"day": target_date.day},
        )
        if not picked or not picked.get("ok"):
            raise RuntimeError(
                "[文章][微博] 定时日历未找到目标日期格子: %s"
                % (picked or {}).get("err")
            )
        await page.mouse.click(picked["x"], picked["y"])
        await asyncio.sleep(1.0)
        logger.info(
            "[文章][微博] 定时日期已选择: %s", target_date.strftime("%Y-%m-%d")
        )


    async def _article_click_publish(self, page, results, scheduled=False):
        """点发布弹窗「发布」, 以 publish/publishtiming 响应 code 判定成功。"""
        results["publish"].clear()
        # 找到弹窗内可见且未禁用的「发布」按钮
        clicked = await page.evaluate(
            """() => {
              const vis = (el) => {
                const r = el.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
              };
              const scope = [...document.querySelectorAll(
                  '.publish-modal, .n-modal')].find(
                (el) => vis(el) && (el.innerText || '').includes('发布'));
              if (!scope) return false;
              for (const b of scope.querySelectorAll('button')) {
                if (!vis(b)) continue;
                if ((b.innerText || '').trim() === '发布' && !b.disabled) {
                  b.click();
                  return true;
                }
              }
              return false;
            }"""
        )
        if not clicked:
            raise RuntimeError(
                "[文章][微博] 发布弹窗内「发布」按钮不可用(微博正文可能为空)"
            )
        logger.info(
            "[文章][微博] 已点击发布弹窗「发布」(%s),等待发表接口...",
            "定时发布 → /draft/publishtiming" if scheduled
            else "立即发布 → /draft/publish",
        )

        deadline = asyncio.get_event_loop().time() + 120
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page, action="文章发布")
            url = page.url or ""
            if "security.weibo.com" in url or "/captcha" in url:
                await self._article_wait_captcha(page)
                # 验证通过后重新点发布
                await self._article_click_publish_retry(page)
            if results["publish"]:
                body = results["publish"][-1]
                code = body.get("code") if isinstance(body, dict) else None
                msg = (
                    (body or {}).get("msg")
                    or (body or {}).get("message")
                    or ""
                ) if isinstance(body, dict) else ""
                if code == self._ARTICLE_OK_CODE:
                    logger.info("[文章][微博] ✓ 发表成功(code=%s)", code)
                    await asyncio.sleep(3)
                    return
                if code is not None:
                    raise RuntimeError(
                        f"[文章][微博] 文章发表失败 code={code} msg={msg}"
                    )
            await asyncio.sleep(1.5)
        # 未收到发表接口响应: 若已跳转到文章页则视为失败(禁止 URL 判定成功)
        raise RuntimeError(
            "[文章][微博] 未监听到发表接口响应,文章未确认发表"
            f"(当前 URL: {page.url})"
        )

    async def _article_click_publish_retry(self, page):
        """身份验证通过后重新点发布弹窗「发布」。"""
        logger.info("[文章][微博] 身份验证通过,重新点击「发布」")
        await asyncio.sleep(3)
        for _ in range(3):
            clicked = await page.evaluate(
                """() => {
                  const vis = (el) => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                  };
                  const scope = [...document.querySelectorAll(
                      '.publish-modal, .n-modal')].find(
                    (el) => vis(el) && (el.innerText || '').includes('发布'));
                  if (!scope) return false;
                  for (const b of scope.querySelectorAll('button')) {
                    if (!vis(b)) continue;
                    if ((b.innerText || '').trim() === '发布'
                        && !b.disabled) {
                      b.click(); return true;
                    }
                  }
                  return false;
                }"""
            )
            if clicked:
                return
            await asyncio.sleep(2)
        raise RuntimeError("[文章][微博] 身份验证后未能重新点击发布按钮")
