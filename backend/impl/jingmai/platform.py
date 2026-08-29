"""京东京麦平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

登录/创作中心地址：https://dr.jd.com/jm/

登录成功判定：打开创作中心后，若 URL 被重定向到 passport.shop.jd.com 则未登录；
保持在 dr.jd.com/jm 则已登录。全程不依赖 DOM（最稳）。

DOM 说明：京麦顶栏用无哈希的 BEM class（``shop-menu-accountV1__xxx``、
``shop-menu-account__right-avatar``），稳定可用；Vue scoped 属性
``data-v-xxxx`` 带哈希，一律不用。
"""

import asyncio
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from util._logger import get_channel_logger

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    raise_if_page_closed,
    save_login_result,
    scrape_jingmai_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("jingmai")

# 创作中心/登录页 URL
_JINGMAI_HOME_URL = "https://dr.jd.com/jm/"

# Cookie 失效时会被重定向到这些域名/路径
_COOKIE_INVALID_MARKERS = (
    "passport.shop.jd.com",
    "passport.jd.com",
)

# 视为已登录的域名（URL 停留在此域 = 登录成功）
_HOME_HOST = "dr.jd.com"

# 运营数据页面（粉丝/获赞/创作者ID）
_ACCOUNT_INFO_URL = "https://dr.jd.com/jm/#/n/account/info.html"


class JingmaiPlatform(BasePlatform):
    platform_id = 19
    platform_key = "jingmai"
    platform_name = "京东京麦"

    # ------------------------------------------------------------------
    # login
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开京东京麦创作中心，等待用户手动完成登录后保存 cookie。

        京东登录方式多样，统一让用户在可见浏览器里手动完成。
        登录成功判定：URL 从登录页跳回 ``dr.jd.com/jm``。
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_JINGMAI_HOME_URL)
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

                # 京麦登录后后台还在做 token 交换/重定向，登录态 cookie 可能尚未
                # 完全建立。主动重新导航首页 + 等运营卡片出现，确保：
                # 1) 关键登录态 cookie 已写入（供后续 storage_state 保存完整）
                # 2) 运营数据 DOM 渲染完成（供 _login_stats_fn 抓取）
                logger.info("[登录] 等待首页运营卡片加载（确保登录态完整）")
                try:
                    await page.goto(_JINGMAI_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.info(f"[登录] 首页导航超时(忽略，继续抓取): {e}")
                try:
                    await page.wait_for_selector(
                        "#homeAccountOperateCard .account-base-info-item",
                        timeout=20000,
                    )
                    logger.info("[登录] 运营卡片已加载")
                except Exception as e:
                    logger.info(f"[登录] 运营卡片等待超时(忽略，继续保存): {e}")
                await asyncio.sleep(2)

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_jingmai_profile,
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
                await page.goto(_JINGMAI_HOME_URL)
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
        """同步京东京麦昵称、头像、运营数据(stats)。

        顶栏头像/昵称用无哈希 BEM class 定位：
        - 头像：``.shop-menu-account__right-avatar`` 的 src
        - 昵称：``.shop-menu-accountV1__right-account-top-name`` 的 title

        运营数据(粉丝/获赞)从账号信息页 ``.account-base-info-item`` 抓取。
        """
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_JINGMAI_HOME_URL, wait_until="domcontentloaded", timeout=30000)
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=20000)
                except Exception:
                    pass
                await asyncio.sleep(3)

                # 头像/昵称（顶栏，无哈希 BEM class）
                name, avatar = await scrape_jingmai_profile(page)

                # 运营数据：进入账号信息页抓取（粉丝/获赞）
                stats_raw = await self._scrape_stats(page)

                label_map = {
                    "粉丝": ("user", 1, "粉丝"),
                    "获赞": ("like", 2, "获赞"),
                }
                stats = self._build_stats(stats_raw, label_map)

                if not name and not avatar and not stats:
                    logger.info(f"[jingmai] sync_profile 抓取为空, url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            except Exception as e:
                logger.info(f"[jingmai] 同步资料失败: {e}")
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
        stats_raw = await self._scrape_stats(page)
        label_map = {
            "粉丝": ("user", 1, "粉丝"),
            "获赞": ("like", 2, "获赞"),
        }
        return self._build_stats(stats_raw, label_map)

    @staticmethod
    async def _scrape_stats(page) -> list:
        """抓取运营数据（粉丝/获赞）。

        京麦首页账号运营卡片 DOM（id 极稳定，class 为无哈希 BEM）：
          <div id="homeAccountOperateCard">
            <div class="account-base-info">
              <div class="account-base-info-item">创作者ID<span>30818079</span></div>
              <div class="account-base-info-item">粉丝<span>0</span></div>
              <div class="account-base-info-item">获赞<span>0</span></div>
            </div>
          </div>

        京东首页内容已迁入微前端 iframe（<iframe class="micro-iframe"
        src="/n/home.html?platform=jm-pop">），卡片不一定在主页面 DOM：
        先探主页面，再枚举全部子 frame（micro-iframe 由 SPA 异步挂载，
        每轮重新取 page.frames 快照），任一 scope 命中即在其中 evaluate。

        京麦是 SPA，卡片异步加载，必须等 selector 出现再 evaluate，
        否则登录后/同步时立即 evaluate 会拿到空列表。

        返回 [{"name":"粉丝","num":"0"}, ...]，由 _build_stats 标准化。
        """
        selector = '#homeAccountOperateCard .account-base-info-item'

        async def _find_scope(total_timeout: float):
            """在主页面 + 全部子 frame 里找运营卡片，返回命中的 scope。"""
            deadline = asyncio.get_event_loop().time() + total_timeout
            while asyncio.get_event_loop().time() < deadline:
                raise_if_page_closed(page)
                # 1) 主页面（历史布局：卡片直接挂在首页 DOM）
                try:
                    await page.wait_for_selector(selector, timeout=1000)
                    return page
                except Exception:
                    pass
                # 2) 子 frame（现布局：卡片在 iframe.micro-iframe 内）
                for frame in list(page.frames):
                    if frame is page.main_frame:
                        continue
                    try:
                        await frame.wait_for_selector(selector, timeout=500)
                        return frame
                    except Exception:
                        # frame 可能正被 SPA 重建（detached），跳过后下轮重枚举
                        continue
                await asyncio.sleep(0.5)
            return None

        scope = await _find_scope(12)
        if scope is None:
            logger.info(
                f"[jingmai] 运营数据卡片未出现(主页面+子frame均未命中), url={page.url}"
            )
            return []

        try:
            result = await scope.evaluate(
                '''() => {
                    const out = [];
                    // 精确 scope 到 #homeAccountOperateCard，避免误匹配页面其他位置
                    const card = document.querySelector('#homeAccountOperateCard');
                    if (!card) return out;
                    const items = card.querySelectorAll('.account-base-info-item');
                    items.forEach(item => {
                        const span = item.querySelector('span');
                        if (!span) return;
                        // label = item 克隆后移除 span 的文本（"粉丝"/"获赞"/"创作者ID"）
                        const clone = item.cloneNode(true);
                        const sp = clone.querySelector('span');
                        if (sp) sp.remove();
                        const label = (clone.textContent || '').trim();
                        const num = (span.textContent || '').trim();
                        if (label) {
                            out.push({name: label, num: num});
                        }
                    });
                    return out;
                }'''
            )
        except Exception as e:
            logger.info(f"[jingmai] _scrape_stats evaluate 失败: {e}")
            return []

        return result or []

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
    # publish_video（委托给 JdPlatform 实现，避免重复代码）
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """京东京麦视频发布 — 复用 jd 平台实现。

        jingmai 与 jd 是同一个产品(dr.jd.com/jm/),用户在 jingmai 账号下
        登录后,直接使用 jd 平台的 publish_video 逻辑(上传/封面/标题/
        关联挂件/创作声明/定时发布/发布)。
        """
        from ..jd.platform import JdPlatform
        jd = JdPlatform()
        return jd.publish_video(**kwargs)

    # ------------------------------------------------------------------
    # open_creator_center
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _JINGMAI_HOME_URL

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
