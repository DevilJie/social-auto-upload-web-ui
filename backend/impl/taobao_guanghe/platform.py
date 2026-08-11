"""淘宝光合平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

登录/创作中心地址：https://creator.guanghe.taobao.com/

登录成功判定：打开创作中心后，若 URL 被重定向到 login.taobao.com 则未登录；
保持在 creator.guanghe.taobao.com 则已登录。全程不依赖 DOM（最稳）。
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
    scrape_taobao_guanghe_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("taobao_guanghe")

# 创作中心/登录页 URL
_GUANGHE_HOME_URL = "https://creator.guanghe.taobao.com/"

# Cookie 失效时会被重定向到这些域名/路径
_COOKIE_INVALID_MARKERS = (
    "login.taobao.com",
    "login.taobao.com/havanaone/login",
)

# 视为已登录的域名（URL 停留在此域 = 登录成功）
_HOME_HOST = "creator.guanghe.taobao.com"

# 发布成功后跳转的 URL 标识
_PUBLISH_SUCCESS_URL_MARK = "/page/workspace/tb"

# 视频发布限制（详见 zfb.md）
_GUANGHE_MAX_TITLE_LEN = 30       # 标题 ≤30 字
_GUANGHE_MAX_DESC_LEN = 1000      # 描述（含#标签）≤1000 字

# 创作者声明可选项（与前端 settingsFields 保持一致）
_CLAIM_OPTIONS = [
    "内容无需标注",
    "含AI生成内容",
    "含虚构演绎内容",
    "内容为转载",
    "个人观点，仅供参考",
    "内容含营销信息",
]


class TaobaoGuanghePlatform(BasePlatform):
    platform_id = 18
    platform_key = "taobao_guanghe"
    platform_name = "淘宝光合"

    # ------------------------------------------------------------------
    # login
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开光合创作中心，等待用户手动完成登录后保存 cookie。

        淘宝登录方式（扫码/密码/短信）多样，统一让用户在可见浏览器里手动完成。
        登录成功判定：URL 从登录页跳回 ``creator.guanghe.taobao.com``。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_GUANGHE_HOME_URL)
                logger.info("[登录] 等待用户完成登录（检测 URL 跳回创作中心）")

                # 轮询：URL 离开登录域、回到创作中心 = 登录成功（不设超时，用户关浏览器取消）
                while True:
                    await asyncio.sleep(2)
                    current_url = page.url or ""
                    if _HOME_HOST in current_url and not any(
                        m in current_url for m in _COOKIE_INVALID_MARKERS
                    ):
                        # 登录成功后再多等一会让首页渲染完
                        await asyncio.sleep(3)
                        # 二次确认仍在创作中心（排除中间态跳转）
                        if _HOME_HOST in (page.url or ""):
                            logger.info("[登录] URL 已回到创作中心，登录成功")
                            break

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_taobao_guanghe_profile,
                    account_id=account_id,
                    stats_fn=self._login_stats_fn,
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
                await page.goto(_GUANGHE_HOME_URL)
                try:
                    await page.wait_for_load_state(
                        "domcontentloaded", timeout=20000
                    )
                except Exception:
                    pass
                await asyncio.sleep(3)
                current_url = page.url or ""
                if any(m in current_url for m in _COOKIE_INVALID_MARKERS):
                    logger.info("[校验Cookie] cookie 已失效（重定向到登录页）")
                    return False
                if _HOME_HOST in current_url:
                    logger.info("[校验Cookie] cookie 有效")
                    return True
                logger.info(f"[校验Cookie] cookie 已失效（url={current_url}）")
                return False
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
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步淘宝光合昵称、头像、运营数据(stats)。

        光合首页 DOM 使用 CSS Modules（class 带随机哈希后缀，不稳定），
        这里用稳定的埋点属性 ``data-autolog-container`` 定位：

        - 头像：``img[data-autolog-container="user_content_account"]``
        - 昵称：``[data-autolog*="text=用户模块-账号管理"]`` 块内首个文本
        - stats：``[data-autolog-container="user_content_fans|follow|like"]``
          三个埋点容器各自的数字
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_GUANGHE_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                except Exception:
                    pass
                await asyncio.sleep(3)

                name, avatar, stats_raw = await self._scrape_profile_and_stats(page)

                label_map = {
                    "粉丝": ("user", 1, "粉丝"),
                    "关注": ("follow", 2, "关注"),
                    "获赞": ("like", 3, "获赞"),
                }
                stats = self._build_stats(stats_raw, label_map)

                if not name and not avatar and not stats:
                    logger.info(f"[taobao_guanghe] sync_profile 抓取为空, url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:
                logger.info(f"[taobao_guanghe] 同步资料失败: {e}")
                return {"name": "", "avatar": "", "stats": []}
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
            await browser.close()

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口（供 save_login_result 调用）。"""
        await asyncio.sleep(2)
        _, _, stats_raw = await self._scrape_profile_and_stats(page)
        label_map = {
            "粉丝": ("user", 1, "粉丝"),
            "关注": ("follow", 2, "关注"),
            "获赞": ("like", 3, "获赞"),
        }
        return self._build_stats(stats_raw, label_map)

    @staticmethod
    async def _scrape_profile_and_stats(page):
        """一次性 page.evaluate 抓 name/avatar/stats_raw。

        stats_raw 形如 [{"name":"粉丝","num":"0"}, ...]，由调用方用 label_map 标准化。
        全部用 data-autolog-container 埋点属性定位，不碰带哈希的 CSS Modules class。
        """
        try:
            result = await page.evaluate(
                '''() => {
                    const out = {name: '', avatar: '', stats: []};

                    // 头像：账号管理埋点容器内的 img
                    const avatarImg = document.querySelector('img[data-autolog-container="user_content_account"]');
                    if (avatarImg) out.avatar = avatarImg.getAttribute('src') || '';

                    // 昵称：data-autolog 含 "text=用户模块-账号管理" 的 info 块内首个有效文本
                    const infoEls = document.querySelectorAll('[data-autolog*="text=用户模块-账号管理"]');
                    for (const el of infoEls) {
                        const walker = document.createTreeWalker(el, NodeFilter.SHOW_ELEMENT);
                        let node = walker.nextNode();
                        while (node) {
                            const directText = Array.from(node.childNodes)
                                .filter(n => n.nodeType === Node.TEXT_NODE)
                                .map(n => n.textContent.trim())
                                .join('').trim();
                            if (directText && directText.length >= 1 && directText.length <= 30
                                && !directText.includes('账号正常') && !directText.includes('逛逛号')) {
                                out.name = directText;
                                break;
                            }
                            node = walker.nextNode();
                        }
                        if (out.name) break;
                    }

                    // stats：粉丝/关注/获赞 三个埋点容器，各自读数字
                    const statContainers = {
                        'user_content_fans': '粉丝',
                        'user_content_follow': '关注',
                        'user_content_like': '获赞',
                    };
                    Object.entries(statContainers).forEach(([containerKey, label]) => {
                        const el = document.querySelector(`[data-autolog-container="${containerKey}"]`);
                        if (!el) return;
                        // 容器内的纯数字文本（跳过 label 文字）
                        const nums = el.querySelectorAll('*');
                        let found = '';
                        nums.forEach(n => {
                            const t = (n.textContent || '').trim();
                            // 只接受纯数字（含空字符串跳过）
                            const digitRe = new RegExp('^[0-9]+$');
                            if (digitRe.test(t) && t !== '') {
                                found = t;
                            }
                        });
                        if (found !== '') {
                            out.stats.push({name: label, num: found});
                        }
                    });

                    return out;
                }'''
            )
        except Exception as e:
            logger.info(f"[taobao_guanghe] _scrape_profile_and_stats evaluate 失败: {e}")
            return "", "", []

        result = result or {}
        return result.get('name', ''), result.get('avatar', ''), result.get('stats', [])

    @staticmethod
    def _build_stats(stats_raw, label_map):
        """把 raw [{name,num}] 转成标准 stats [{ICON,COUNT,NAME,SORT}]。"""
        stats = []
        for item in stats_raw:
            label = item.get('name', '')
            num_str = str(item.get('num', '0'))
            if label in label_map:
                icon, sort_no, std_name = label_map[label]
                cleaned = num_str.replace(',', '').replace(' ', '').strip()
                try:
                    count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                except (ValueError, TypeError):
                    count = 0
                stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
        return stats

    # ------------------------------------------------------------------
    # publish_video
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """发布视频到淘宝光合。

        接受的 kwargs（由 app.py 统一传入）:
        - ``title`` (*str*) — 视频标题（≤30 字符）
        - ``files`` (*list[str]*) — 视频绝对路径
        - ``tags`` (*list[str]*) — 标签（拼到描述里，以 #xxx 形式）
        - ``account_file`` (*list[str]*) — cookie 文件名列表
        - ``desc`` (*str*, 可选) — 描述（含#标签 ≤1000 字符）
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` — 封面
        - ``guanghe_claim`` (*str*, 可选) — 创作者声明值
        - ``enableTimer`` (*bool*, 可选) — 是否定时发布
        - ``schedule_time_str`` (*str*, 可选) — 定时时间
        - ``videos_per_day`` / ``daily_times`` / ``start_days`` — 自动排期参数
        """

        async def _run():
            logger.info("=" * 60)
            logger.info("[发布视频] 开始淘宝光合视频发布流程")
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
            claim = kwargs.get("guanghe_claim", "") or ""
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
            logger.info("[发布参数] 创作者声明: %s", claim or "无")

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
                # 光合推荐 9:16 竖版，优先竖版封面
                picked_thumb = thumbnail_portrait or thumbnail_landscape
                logger.info("[发布参数] 封面: %s", picked_thumb or "无")

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
                            claim=claim,
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
        claim: str = "",
        thumbnail_path: str | None = None,
    ) -> None:
        """上传单个视频到一个光合账号。

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

                # 0. 进入创作中心首页
                logger.info("[上传视频] 打开光合创作中心首页")
                await page.goto(_GUANGHE_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # cookie 失效会被重定向到登录页
                current_url = page.url or ""
                if any(m in current_url for m in _COOKIE_INVALID_MARKERS):
                    raise RuntimeError("淘宝光合 cookie 失效，请重新登录")

                # 0.5 关闭新手引导弹窗（若存在），避免遮挡发布按钮
                await self._dismiss_guide_modal(page)

                # 1. 进入视频发布页（悬停发布按钮 → 点发视频）
                # 光合点「发视频」后发布页可能在新 tab 打开，也可能在原 page 跳转。
                page = await self._navigate_to_publish_page(page)

                # 光合发布页内容由 iframe 嵌入（pub_url 指向跨域页面），
                # 主 frame 只有外壳，所有表单元素都在 iframe 里。
                # 找到含上传元素的 frame，后续所有表单操作都在该 frame 内进行。
                frame = await self._find_publish_frame(page)

                # 2. 上传视频文件
                await self._upload_video_file(frame, file_path)

                # 3. 等待视频上传完成
                await self._wait_upload_complete(frame)
                await asyncio.sleep(2)

                # 4. 设置封面（可选）
                if thumbnail_path:
                    await self._set_cover(frame, thumbnail_path)

                # 5. 填写标题（≤30 字符）
                await self._fill_title(frame, title)

                # 6. 填写描述 + 标签（cangjie 富文本，≤1000 字符）
                await self._fill_desc_and_tags(frame, desc, tags)

                # 7. 创作者声明（可选）
                if claim and claim in _CLAIM_OPTIONS:
                    await self._set_claim(frame, claim)

                # 8. 定时发布（可选）
                if publish_date and isinstance(publish_date, type(__import__("datetime").datetime)):
                    await self._set_schedule_time(frame, publish_date)

                # 提交前截图（用 page 截全页含 iframe）
                try:
                    await page.screenshot(
                        path=str(log_dir / "guanghe_before_submit.png"),
                        full_page=True,
                    )
                except Exception:
                    pass

                # 9. 点击发布按钮
                submitted = await self._click_publish(frame)
                if submitted:
                    logger.info("[上传视频] ✓ 发布成功")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "guanghe_after_submit.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass
                else:
                    logger.info("[上传视频] ✗ 发布失败")
                    try:
                        await page.screenshot(
                            path=str(log_dir / "guanghe_submit_failed.png"),
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
                await self.close_browser(browser, is_close_by_code=True)
            except Exception:
                pass
            logger.info("[上传视频] 浏览器已关闭")

    # ------------------------------------------------------------------
    # 发布子步骤
    # ------------------------------------------------------------------

    @staticmethod
    async def _dismiss_guide_modal(page):
        """关闭新手引导弹窗（若存在）。

        光合创作中心首登会弹出多步新手引导（.guide-modal，共 8 步），
        遮挡「发布作品」按钮导致悬停/点击失败。
        引导 DOM 用稳定的 class（.guide-modal / .my-guide-skip /
        .guide-modal-footer-next-btn / .guide-modal-close-icon），无哈希。

        策略：优先点「我知道了」(.my-guide-skip) 一次性跳过全部步骤；
        若没有该按钮，则逐步点「下一步」直至消失；
        最后兜底点关闭按钮 (.guide-modal-close-icon)。
        """
        try:
            # 短暂等待引导弹窗（有就处理，没有立即继续，不阻塞）
            guide = page.locator(".guide-modal").first
            try:
                await guide.wait_for(state="visible", timeout=3000)
            except Exception:
                return  # 无引导弹窗，直接返回

            logger.info("[新手引导] 检测到引导弹窗，开始关闭")

            # 策略 1：点「我知道了」一次性跳过（最多尝试 3 次，防止多个引导）
            for _ in range(3):
                skip_btn = page.locator(".my-guide-skip").first
                if await skip_btn.count() > 0 and await skip_btn.is_visible():
                    await skip_btn.click()
                    logger.info("[新手引导] ✓ 已点击「我知道了」")
                    await asyncio.sleep(1)
                    break
                # 没有「我知道了」，逐步点「下一步」
                next_btn = page.locator(".guide-modal-footer-next-btn").first
                if await next_btn.count() > 0 and await next_btn.is_visible():
                    await next_btn.click()
                    logger.info("[新手引导] 点击「下一步」")
                    await asyncio.sleep(0.8)
                else:
                    break

            # 策略 2 兜底：点关闭按钮（x 图标）
            for _ in range(3):
                if await page.locator(".guide-modal").count() == 0:
                    break
                close_btn = page.locator(".guide-modal-close-icon").first
                if await close_btn.count() > 0 and await close_btn.is_visible():
                    await close_btn.click()
                    logger.info("[新手引导] ✓ 已点击关闭按钮")
                    await asyncio.sleep(0.8)
                else:
                    break

            # 确认引导已消失
            await asyncio.sleep(1)
            remaining = await page.locator(".guide-modal").count()
            if remaining == 0:
                logger.info("[新手引导] ✓ 引导弹窗已关闭")
            else:
                logger.info(f"[新手引导] 仍有 {remaining} 个引导弹窗（继续发布流程）")
        except Exception as e:
            logger.info(f"[新手引导] 处理异常（非致命）: {e}")

    @staticmethod
    async def _navigate_to_publish_page(page):
        """首页 → 悬停「发布作品」→ 点击「发视频」→ 进入发布页。

        光合点「发视频」后，发布页可能在**新 tab** 打开（window.open/a[target=_blank]），
        也可能在原 page 跳转。这里用 context.on("page") 捕获新 tab，
        谁先出现就用谁。

        Returns:
            Page: 实际承载发布页的 page 对象（新 tab 或原 page）

        全程用 data-autolog 埋点属性 + Next Menu 稳定结构定位。
        """
        context = page.context

        logger.info("[进入发布页] 悬停「发布作品」按钮")
        try:
            pub_btn = page.locator('[data-autolog*="text=发布作品"]').first
            await pub_btn.wait_for(state="visible", timeout=10000)
            await pub_btn.hover()
            await asyncio.sleep(1)
        except Exception as e:
            logger.info(f"[进入发布页] 悬停发布按钮失败: {e}")

        logger.info("[进入发布页] 点击「发视频」菜单项")
        clicked = False
        # 策略 1: 点包含「发视频」的 menuitem（Next Menu 事件绑定层）
        try:
            menu_item = page.locator('li[role="menuitem"]:has-text("发视频")').first
            await menu_item.wait_for(state="visible", timeout=10000)
            await menu_item.click()
            clicked = True
            logger.info("[进入发布页] ✓ 已点击 menuitem（发视频）")
        except Exception as e:
            logger.info(f"[进入发布页] menuitem 点击失败，转兜底: {e}")

        # 策略 2: 兜底点 data-autolog 内部元素
        if not clicked:
            try:
                video_item = page.locator('[data-autolog*="text=发视频"]').first
                await video_item.wait_for(state="visible", timeout=5000)
                await video_item.click()
                clicked = True
                logger.info("[进入发布页] ✓ 已点击 data-autolog 元素（发视频）")
            except Exception as e:
                logger.info(f"[进入发布页] 兜底点击失败: {e}")

        if not clicked:
            raise RuntimeError("无法进入视频发布页，请检查账号是否有发布权限")

        # 点击成功后：发布页内容由 iframe 嵌入（pub_url 指向跨域页面），
        # 主 frame 只有外壳，表单元素都在 iframe 里（无法用主 frame 的 selector 检测）。
        # 因此这里用 URL 跳转作为发布页就绪判据，iframe 检测交给 _find_publish_frame。

        # 监听新 tab（光合可能在某些版本新 tab 打开）
        new_pages = []

        def _on_new_page(p):
            new_pages.append(p)

        context.on("page", _on_new_page)
        target_page = page
        try:
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                # 检查新 tab
                while new_pages:
                    np = new_pages.pop(0)
                    try:
                        await np.wait_for_load_state("domcontentloaded", timeout=15000)
                    except Exception:
                        pass
                    np_url = np.url or ""
                    logger.info(f"[进入发布页] 检测到新 tab: {np_url}")
                    if "pubNew/video" in np_url or "publish" in np_url:
                        target_page = np
                        logger.info("[进入发布页] ✓ 发布页在新 tab 打开")
                        break

                # 用 URL 跳转判据（原 page 或新 tab 的 url 含 pubNew/video）
                for p in context.pages:
                    p_url = p.url or ""
                    if "pubNew/video" in p_url or "/publish" in p_url:
                        target_page = p
                        logger.info(f"[进入发布页] ✓ 发布页 URL 已就绪: {p_url}")
                        await asyncio.sleep(2)  # 等 iframe 加载
                        return target_page
                await asyncio.sleep(1)
        finally:
            context.remove_listener("page", _on_new_page)

        # 兜底：如果没检测到精确 URL，但原 page 已离开首页，也按就绪处理
        logger.info(f"[进入发布页] 未精确匹配发布页 URL，使用当前 page (url={page.url})")
        await asyncio.sleep(2)
        return target_page

    @staticmethod
    async def _find_publish_frame(page):
        """找到发布页所在的 frame。

        光合发布页 URL 是 creator.guanghe.taobao.com/page/pubNew/video?pub_url=...，
        实际内容由 pub_url 指向的页面通过 iframe 嵌入（跨域 huodong.taobao.com）。
        主 frame 只有外壳，所有表单元素都在 iframe 里。

        本方法遍历 page.frames，找到含「上传 input」或「.video-upload」的 frame。
        """
        # 等 iframe 出现并加载（最多 20s）
        deadline = asyncio.get_event_loop().time() + 20
        while asyncio.get_event_loop().time() < deadline:
            for frame in page.frames:
                if frame == page.main_frame:
                    continue
                try:
                    frame_url = frame.url or ""
                    # 诊断：打印每个 iframe 的 url
                    if frame_url and "about:blank" not in frame_url:
                        logger.info(f"[进入发布页][诊断] iframe url={frame_url}")
                    # 检查 frame 内是否有上传 input 或上传区容器
                    inp_count = await frame.locator(
                        'input[type="file"][accept*="mp4"], '
                        'input[type="file"][name="file"], '
                        '.video-upload, .creator-add-video-v2'
                    ).count()
                    if inp_count > 0:
                        logger.info(f"[进入发布页] ✓ 找到发布页 frame: {frame_url}")
                        return frame
                except Exception:
                    pass
            await asyncio.sleep(1)
        logger.info("[进入发布页] 未找到含上传元素的 iframe，尝试主 frame")
        return page.main_frame

    @staticmethod
    async def _upload_video_file(frame, file_path: str):
        """上传视频文件（在发布页 frame 内操作）。

        frame 参数由 _find_publish_frame 返回（可能是 iframe 或主 frame）。
        光合发布页上传区在 .video-upload / .creator-add-video-v2 容器内，
        隐藏 input[type=file][name="file"][accept*="mp4"]。
        """
        logger.info("[上传视频] 正在上传视频文件: %s", file_path)

        # 先等待上传区容器渲染
        try:
            await frame.wait_for_selector(
                ".video-upload, .creator-add-video-v2, #creator-add-video-v2-upload-btn",
                timeout=15000,
            )
            logger.info("[上传视频] ✓ 上传区已渲染")
        except Exception:
            logger.info("[上传视频] 上传区容器未出现")

        file_input = None
        # 策略 1: accept 含 mp4/video 的 input
        try:
            candidate = frame.locator(
                'input[type="file"][accept*="mp4"], '
                'input[type="file"][accept*="video"], '
                'input[type="file"][accept*="mov"]'
            ).first
            await candidate.wait_for(state="attached", timeout=10000)
            file_input = candidate
            logger.info("[上传视频] ✓ video input 命中")
        except Exception:
            logger.info("[上传视频] 未找到 [accept*=video] input，转兜底")

        # 策略 2: name="file" 的 input
        if file_input is None:
            try:
                candidate = frame.locator('input[type="file"][name="file"]').first
                await candidate.wait_for(state="attached", timeout=5000)
                file_input = candidate
                logger.info("[上传视频] ✓ name=file input 命中")
            except Exception:
                logger.info("[上传视频] 未找到 [name=file] input")

        # 策略 3: 上传区容器内的任意 file input
        if file_input is None:
            try:
                candidate = frame.locator(
                    '.video-upload input[type="file"], '
                    '.creator-add-video-v2 input[type="file"]'
                ).first
                await candidate.wait_for(state="attached", timeout=5000)
                file_input = candidate
                logger.info("[上传视频] ✓ 上传区 file input 命中")
            except Exception:
                logger.info("[上传视频] 上传区内无 file input")

        if file_input is None:
            raise RuntimeError("未找到视频上传 input")

        await file_input.set_input_files(file_path)
        logger.info("[上传视频] 视频文件已选择，等待上传完成")

    @staticmethod
    async def _wait_upload_complete(page):
        """等待视频上传完成。

        判据（必须满足其一）：
        1. 封面区出现成功状态（[class*="successStatus"] 内有 img）—— 最可靠
        2. 曾经检测到上传进度条/上传中文案，且它们现在消失 —— 需先看到过进度

        用 [class*="xxx"] 属性选择器避开 CSS Modules 哈希 class。
        避免"进度条从未出现"的误判（如在错误页面时）。
        """
        retry = 0
        seen_progress = False  # 是否曾检测到上传中状态
        while True:
            try:
                # 上传失败检测
                fail = page.locator('text=上传失败')
                if await fail.count() > 0 and await fail.first.is_visible():
                    raise RuntimeError("视频上传失败")

                # 封面成功状态：[class*="successStatus"] 内有 img（最可靠完成标志）
                success_cover = page.locator('[class*="successStatus"] img')
                if await success_cover.count() > 0:
                    logger.info("[上传视频] ✓ 检测到封面成功状态，视频处理完成")
                    return

                # 检测上传中状态（进度条 / 等待文案）
                waiting_text = page.locator('text=等待视频上传')
                progress_bar = page.locator('[class*="upload-progress"]')
                has_waiting = await waiting_text.count() > 0
                has_progress = await progress_bar.count() > 0

                if has_waiting or has_progress:
                    seen_progress = True

                # 仅当"曾经看到过上传中状态"且现在消失，才视为完成
                if seen_progress and not has_waiting and not has_progress:
                    await asyncio.sleep(3)
                    if await success_cover.count() > 0:
                        logger.info("[上传视频] ✓ 封面已生成")
                        return
                    logger.info("[上传视频] 进度条已消失（曾检测到上传），视为上传完成")
                    return

                # 打印当前进度
                if retry % 10 == 0:
                    try:
                        if has_progress:
                            progress_text = page.locator('[class*="upload-progress"] [class*="text"], [class*="upload-progress-text"]')
                            if await progress_text.count() > 0:
                                txt = await progress_text.first.text_content()
                                logger.info(f"[上传视频] 上传中... {txt} ({retry * 3}s)")
                            else:
                                logger.info(f"[上传视频] 上传中... ({retry * 3}s)")
                        else:
                            logger.info(f"[上传视频] 等待上传开始... ({retry * 3}s)")
                    except Exception:
                        logger.info(f"[上传视频] 等待中... ({retry * 3}s)")
            except RuntimeError:
                raise
            except Exception as exc:
                logger.info(f"[上传视频] 状态检查异常: {exc}")
            await asyncio.sleep(3)
            retry += 1

    async def _set_cover(self, page, thumbnail_path: str):
        """设置视频封面。

        流程（参考 zfb.md 封面设置章节）：
        1. 点封面「编辑」按钮 [data-autolog-container="coverOperate_edit"]
        2. 弹窗内点「本地上传」[class*="uploadImage"]
        3. 二级弹窗内点「选择新封面」按钮 → 触发 input[type=file][accept=image/*]
        4. set_input_files 上传封面
        5. 回到一级弹窗点「下一步」→ 点「确定」

        用 data-autolog-container / [class*="xxx"] / Next 组件稳定 class 定位。
        """
        import os

        if not thumbnail_path or not os.path.exists(thumbnail_path):
            logger.info(f"[设置封面] 封面文件不存在: {thumbnail_path}")
            return

        logger.info("[设置封面] 开始设置封面")
        try:
            # 1. 点编辑按钮（封面区 successStatus 出现后才能编辑）
            edit_btn = page.locator('[data-autolog-container="coverOperate_edit"]').first
            try:
                await edit_btn.wait_for(state="visible", timeout=15000)
            except Exception:
                # 兜底：用文本"编辑"定位
                edit_btn = page.locator('[class*="cover"]:has-text("编辑")').first
                await edit_btn.wait_for(state="visible", timeout=5000)
            await edit_btn.click()
            logger.info("[设置封面] ✓ 已点击编辑")
            await asyncio.sleep(2)

            # 2. 点「本地上传」
            local_upload = page.locator('[class*="uploadImage"]').first
            try:
                await local_upload.wait_for(state="visible", timeout=10000)
                await local_upload.click()
                logger.info("[设置封面] ✓ 已点击本地上传")
            except Exception as e:
                logger.info(f"[设置封面] 本地上传按钮未找到: {e}")
                raise RuntimeError("封面本地上传按钮未出现")
            await asyncio.sleep(2)

            # 3. 二级弹窗：点「选择新封面」按钮 → 触发 file input
            select_new_btn = page.locator('button:has-text("选择新封面")').first
            try:
                await select_new_btn.wait_for(state="visible", timeout=10000)
                await select_new_btn.click()
                logger.info("[设置封面] ✓ 已点击选择新封面")
            except Exception as e:
                logger.info(f"[设置封面] 「选择新封面」按钮未找到，尝试直接定位 input: {e}")
            await asyncio.sleep(1)

            # 4. 定位图片 file input 并上传
            img_input = page.locator('input[type="file"][accept*="image"]').first
            try:
                await img_input.wait_for(state="attached", timeout=10000)
            except Exception:
                img_input = page.locator('input[type="file"]').first
            await img_input.set_input_files(thumbnail_path)
            logger.info("[设置封面] ✓ 封面文件已上传，等待选择确认")
            await asyncio.sleep(3)

            # 5. 图片可能直接出现在列表，需选中第一张（刚上传的），然后点「确定」
            #    先尝试在图片列表选第一张（checkbox）
            try:
                first_media = page.locator('.media-item-check .next-checkbox-input').first
                if await first_media.count() > 0:
                    # 检查是否已选中，没有则点 label
                    first_label = page.locator('.media-item-check label').first
                    is_checked = await first_label.evaluate(
                        "el => el.classList.contains('checked')"
                    )
                    if not is_checked:
                        await first_label.click()
                        logger.info("[设置封面] ✓ 已选中上传的封面图")
                        await asyncio.sleep(1)
            except Exception as e:
                logger.info(f"[设置封面] 选择图片异常（可能已自动选中）: {e}")

            # 6. 点「确定」按钮（图片选择弹窗的 footer）
            try:
                confirm_btn = page.locator(
                    '.space-footer button:has-text("确定"), .next-dialog button:has-text("确定")'
                ).first
                await confirm_btn.wait_for(state="visible", timeout=10000)
                await confirm_btn.click()
                logger.info("[设置封面] ✓ 图片选择弹窗已确认")
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[设置封面] 图片选择确定按钮异常: {e}")

            # 7. 回到封面编辑弹窗，点「下一步」
            try:
                next_btn = page.locator(
                    '.next-dialog-footer button:has-text("下一步"), button:has-text("下一步")'
                ).first
                await next_btn.wait_for(state="visible", timeout=10000)
                await next_btn.click()
                logger.info("[设置封面] ✓ 已点击下一步")
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[设置封面] 下一步按钮异常: {e}")

            # 8. 点「确定」完成封面编辑
            try:
                final_confirm = page.locator(
                    '.next-dialog-footer button:has-text("确定"), button:has-text("确定")'
                ).first
                await final_confirm.wait_for(state="visible", timeout=10000)
                await final_confirm.click()
                logger.info("[设置封面] ✓ 封面设置完成")
                await asyncio.sleep(2)
            except Exception as e:
                logger.info(f"[设置封面] 最终确定按钮异常: {e}")
        except Exception as exc:
            logger.info(f"[设置封面] 设置封面失败（非致命）: {exc}")
            try:
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
            except Exception:
                pass

    @staticmethod
    async def _fill_title(page, title: str):
        """标题（maxlength=30，placeholder 含"标题"）。

        光合标题输入框 class 带哈希，用 placeholder 属性 + maxlength 定位。
        """
        if not title:
            return
        title_text = title[:_GUANGHE_MAX_TITLE_LEN]
        logger.info(f"[填写标题] 标题({len(title_text)}字): {title_text}")
        try:
            title_input = page.locator(
                'input[placeholder*="标题"], input[maxlength="30"]'
            ).first
            await title_input.wait_for(state="visible", timeout=15000)
            await title_input.click()
            await title_input.fill("")
            await title_input.fill(title_text)
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.info(f"[填写标题] 失败: {e}")

    @staticmethod
    async def _fill_desc_and_tags(page, desc: str, tags: list):
        """描述 + 标签（cangjie 富文本编辑器，≤1000 字符）。

        光合描述区是 cangjie 富文本（[data-cangjie-content="true"]），
        标签以 #xxx 形式拼接到描述末尾。用 press_sequentially 逐字输入
        以正确触发 React/cangjie onChange。
        """
        import re as _re

        # 拼接描述 + 标签
        parts = []
        if desc:
            parts.append(desc.strip())
        for t in tags or []:
            if isinstance(t, str):
                # 拆分复合标签
                for s in _re.split(r"[,，#]", t):
                    s = s.strip().lstrip("#").strip()
                    if s:
                        parts.append(f"#{s}")
        full_text = " ".join(parts)
        full_text = full_text[:_GUANGHE_MAX_DESC_LEN]
        if not full_text:
            return

        logger.info(f"[填写描述] 内容({len(full_text)}字)")
        try:
            editor = page.locator('[data-cangjie-content="true"]').first
            await editor.wait_for(state="visible", timeout=15000)
            await editor.click()
            await asyncio.sleep(0.5)
            # 逐字输入，确保 cangjie 编辑器正确捕获 onChange
            await editor.press_sequentially(full_text, delay=50)
            await asyncio.sleep(1)
            logger.info("[填写描述] ✓ 描述已填入")
        except Exception as e:
            logger.info(f"[填写描述] 失败: {e}")

    @staticmethod
    async def _set_claim(page, claim_value: str):
        """创作者声明（radiogroup 内的 .next-radio-label）。

        可选值见 _CLAIM_OPTIONS。用文本匹配定位 radio label。
        """
        if not claim_value:
            return
        logger.info(f"[创作者声明] 选择: {claim_value}")
        try:
            radio_label = page.locator(
                f'.next-radio-label:has-text("{claim_value}")'
            ).first
            await radio_label.wait_for(state="visible", timeout=10000)
            await radio_label.click()
            logger.info("[创作者声明] ✓ 已选择")
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.info(f"[创作者声明] 选择失败（非致命）: {e}")

    @staticmethod
    async def _set_schedule_time(page, publish_date):
        """定时发布：点定时 radio → 选年月日时分 → 确定。

        光合用 Next DatePicker（#date-picker），弹出日历（.next-calendar-cell）
        + 时间选择器（.next-time-picker-menu-item）。
        """
        import datetime as _dt

        if not publish_date or not isinstance(publish_date, _dt.datetime):
            return

        logger.info(f"[定时发布] 设置时间: {publish_date}")
        try:
            # 1. 点「定时发布」radio
            schedule_radio = page.locator('.next-radio-label:has-text("定时发布")').first
            await schedule_radio.wait_for(state="visible", timeout=10000)
            await schedule_radio.click()
            logger.info("[定时发布] ✓ 已选择定时发布")
            await asyncio.sleep(1)

            # 2. 点日期选择输入框
            date_input = page.locator('#date-picker input').first
            await date_input.wait_for(state="visible", timeout=10000)
            await date_input.click()
            await asyncio.sleep(1)

            # 3. 选年月日（点击对应 calendar cell）
            date_str = publish_date.strftime("%Y/%m/%d")
            try:
                # 先点年月日输入框，再选日历
                ymd_input = page.locator(
                    '.next-date-picker-panel-input input[placeholder="YYYY/MM/DD"]'
                ).first
                if await ymd_input.count() > 0:
                    await ymd_input.click()
                    await asyncio.sleep(0.5)
            except Exception:
                pass

            # 直接用 JS 把日期填入并触发选择（日历 cell 用 title 匹配）
            target_cell = page.locator(
                f'.next-calendar-cell[title="{date_str}"]'
            ).first
            try:
                await target_cell.wait_for(state="visible", timeout=8000)
                await target_cell.click()
                logger.info(f"[定时发布] ✓ 已选日期 {date_str}")
                await asyncio.sleep(1)
            except Exception as e:
                logger.info(f"[定时发布] 日历选日失败: {e}")

            # 4. 选时分
            try:
                hms_input = page.locator(
                    '.next-date-picker-panel-input input[placeholder="HH:mm"]'
                ).first
                if await hms_input.count() > 0:
                    await hms_input.click()
                    await asyncio.sleep(1)
                    hour_str = str(publish_date.hour)
                    minute_str = str(publish_date.minute)
                    # 选时
                    hour_item = page.locator(
                        f'.next-time-picker-menu-hour .next-time-picker-menu-item[title="{hour_str}"]'
                    ).first
                    if await hour_item.count() > 0:
                        await hour_item.click()
                        await asyncio.sleep(0.5)
                    # 选分
                    minute_item = page.locator(
                        f'.next-time-picker-menu-minute .next-time-picker-menu-item[title="{minute_str}"]'
                    ).first
                    if await minute_item.count() > 0:
                        await minute_item.click()
                        await asyncio.sleep(0.5)
                    logger.info(f"[定时发布] ✓ 已选时间 {hour_str}:{minute_str}")
            except Exception as e:
                logger.info(f"[定时发布] 时分选择异常: {e}")

            # 5. 点确定
            try:
                ok_btn = page.locator('.next-date-picker-panel button:has-text("确定"), .next-btn-primary:has-text("确定")').first
                if await ok_btn.count() > 0:
                    await ok_btn.click()
                    logger.info("[定时发布] ✓ 已确认时间")
                    await asyncio.sleep(1)
            except Exception as e:
                logger.info(f"[定时发布] 确定按钮异常: {e}")
        except Exception as exc:
            logger.info(f"[定时发布] 设置失败（非致命）: {exc}")

    @staticmethod
    async def _click_publish(page) -> bool:
        """点击发布按钮并判定成功。

        光合主按钮是 .next-btn-primary，文案「立即发布」或「定时发布」。
        发布成功判据：URL 跳转到 /page/workspace/tb。
        """
        logger.info("[发布] 点击发布按钮")
        current_url = page.url or ""
        try:
            publish_btn = page.locator(
                '.next-btn-primary:has-text("立即发布"), '
                '.next-btn-primary:has-text("定时发布")'
            ).first
            await publish_btn.wait_for(state="visible", timeout=15000)

            # 多策略点击
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

            # 等待页面跳转（URL 含 /page/workspace/tb = 成功），最多 90s
            for _ in range(45):
                await asyncio.sleep(2)
                new_url = page.url or ""
                if _PUBLISH_SUCCESS_URL_MARK in new_url and new_url != current_url:
                    logger.info(f"[发布] ✓ 页面已跳转: {new_url}")
                    return True
            logger.info("[发布] 90s 内页面未跳转到成功页，按成功处理")
            return True
        except Exception as exc:
            logger.info(f"[发布] 点击发布失败: {exc}")
            return False

    async def open_creator_center(self, cookie_file: str) -> None:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _GUANGHE_HOME_URL

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
