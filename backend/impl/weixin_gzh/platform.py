"""
微信公众号平台实现 — 100% CloakBrowser。

所有浏览器操作通过 ``BasePlatform.create_browser()`` /
``BasePlatform.create_context()`` 委托给 CloakBrowser（隐身 Chromium）。

创作中心地址：https://mp.weixin.qq.com/

公众号的特殊点：登录成功后跳转的 URL 形如
  https://mp.weixin.qq.com/cgi-bin/home?t=home/index&lang=zh_CN&token=124257639
其中的 ``token`` 是本次会话的临时令牌，所有后续功能（同步、状态检查、
创作中心跳转）都要带上。token 每次会话会变，因此**不存储陈旧 token**，
而是每次操作都先访问 ``https://mp.weixin.qq.com/``，让 cookie 自动触发跳转
到 ``/cgi-bin/home?...&token=XXX``，再从 URL 解析出最新 token 使用。
"""

import asyncio
import json
import re
import threading
import time
from pathlib import Path
from queue import Queue

from util._logger import get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    save_login_result,
    scrape_weixin_gzh_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("weixin_gzh")

# 公众号首页入口（不带 token，访问后由 cookie 触发自动跳转到带 token 的 home）
_LOGIN_URL = "https://mp.weixin.qq.com/"
_HOME_PATH = "/cgi-bin/home"
_TOKEN_RE = re.compile(r"[?&]token=(\d+)")

# Cookie 失效时公众号会跳转/渲染的登录页或失效提示标记。
# 任一命中即视为失效，不再依赖单一精确业务登录 URL。
_COOKIE_INVALID_URL_MARKERS = (
    "/cgi-bin/bizlogin",
    "/cgi-bin/loginpage",
)


class WeixinGzhPlatform(BasePlatform):
    platform_id = 17
    platform_key = "weixin_gzh"
    platform_name = "微信公众号"

    # 支持 cookie 字符串导入账号
    supports_cookie_import = True
    # 微信系 cookie 全部由 mp.weixin.qq.com 下发，通配 .qq.com 后对公众号
    # 创作中心及子域都生效（视频号 channels 同样用 .qq.com，cookie 文件
    # 各自独立存储，互不影响）。
    platform_cookie_domain = ".qq.com"

    # ------------------------------------------------------------------
    # helpers — token 提取与首页 URL 拼装
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_token(page) -> str:
        """从 page.url 解析 token，返回 token 字符串（解析失败返回空串）。"""
        try:
            url = page.url or ""
        except Exception:
            return ""
        m = _TOKEN_RE.search(url)
        return m.group(1) if m else ""

    @staticmethod
    def _build_home_url(token: str) -> str:
        """拼装带 token 的公众号首页 URL。"""
        if token:
            return (
                "https://mp.weixin.qq.com/cgi-bin/home"
                f"?t=home/index&lang=zh_CN&token={token}"
            )
        return _LOGIN_URL

    def _parse_cookie_to_storage_state(
        self, cookie_str: str
    ) -> tuple[list[dict], list[dict]]:
        """把 'k=v; k=v' 解析为 Playwright storage_state 的 (cookies, origins)。

        - 全部 cookie 归属 ``platform_cookie_domain`` (.qq.com)
        - expires 给 7 天保守占位，sync_profile 跑完后 storage_state 会被
          回写为真实的 cookie（含真实 expires + localStorage）
        - localStorage 留空，由 sync_profile 自然补全
        """
        cookies: list[dict] = []
        expires = time.time() + BasePlatform._IMPORT_COOKIE_EXPIRES_SECONDS
        for pair in cookie_str.split(";"):
            pair = pair.strip()
            if not pair or "=" not in pair:
                continue
            name, _, value = pair.partition("=")
            cookies.append({
                "name": name.strip(),
                "value": value.strip(),
                "domain": self.platform_cookie_domain,
                "path": "/",
                "expires": expires,
                "httpOnly": True,
                "secure": False,
                "sameSite": "Lax",
            })
        logger.info(
            f"[weixin_gzh] cookie 解析: {len(cookies)} 条, domain={self.platform_cookie_domain}"
        )
        return cookies, []

    # ------------------------------------------------------------------
    # login — QR code scan via CloakBrowser
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """微信公众号扫码登录。

        打开 ``https://mp.weixin.qq.com/``，把页面二维码图片推送给前端；
        轮询 URL 检测登录成功（跳到 ``/cgi-bin/home`` 且带 ``token=``），
        成功后从 URL 提取最新 token 跳转到首页，再抓昵称/头像/运营数据写库。
        """
        logger.info("=" * 60)
        logger.info("[登录] 开始微信公众号登录流程")
        logger.info("=" * 60)

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                logger.info("[登录] 正在打开微信公众号主页...")
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # 提取页面二维码图片推给前端展示
                src = None
                qr_selectors = [
                    'img[class*="qrcode"]',
                    'img[class*="qr_code"]',
                    'img[class*="QRCode"]',
                    'img[id*="qr"]',
                    'div[class*="qrcode"] img',
                    'div.login_box img',
                    'img.weui-desktop-account__img',
                ]
                for selector in qr_selectors:
                    try:
                        img_locator = page.locator(selector).first
                        if await img_locator.count():
                            src = await img_locator.get_attribute("src")
                            if src and (src.startswith("http") or src.startswith("data:")):
                                logger.info("[登录] 找到二维码图片，选择器: %s", selector)
                                break
                            src = None
                    except Exception:
                        continue

                if src:
                    logger.info("[登录] 二维码图片已发送到前端")
                    status_queue.put(src)
                else:
                    logger.warning("[登录] 未找到二维码图片（用户可在打开的浏览器中手动扫码）")
                    status_queue.put(json.dumps({"error": "无法找到登录二维码，请在打开的浏览器中手动扫码"}))

                # 等待登录：URL 跳到 /cgi-bin/home 且带 token=
                logger.info("[登录] 等待用户扫码...")
                max_wait = 300  # 5 minutes
                start_time = asyncio.get_event_loop().time()
                logged_in = False
                while (asyncio.get_event_loop().time() - start_time) < max_wait:
                    try:
                        current_url = page.url or ""
                        if _HOME_PATH in current_url and "token=" in current_url:
                            logger.info("[登录] 检测到页面跳转到首页，登录成功!")
                            logged_in = True
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(1)

                if not logged_in:
                    logger.warning("[登录] 登录等待超时（5 分钟），未检测到登录成功")
                    return

                # 跳转到带 token 的首页，确保 DOM 完整渲染用于抓取
                token = self._extract_token(page)
                home_url = self._build_home_url(token)
                logger.info("[登录] 跳转到首页: %s", home_url)
                try:
                    await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                except Exception as e:
                    logger.info("[登录] 跳转首页超时(忽略，继续抓取): %s", e)
                await asyncio.sleep(3)

                # 抓昵称/头像并保存登录结果，登录后补抓 stats
                logger.info("[登录] 正在获取用户信息...")
                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_weixin_gzh_profile,
                    account_id=account_id,
                    stats_fn=self._login_stats_fn,
                )
                logger.info("[登录] 登录流程完成!")
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """校验公众号 cookie 是否有效。

        用 cookie 打开 ``https://mp.weixin.qq.com/``，等待自动跳转：
        - 跳到失效 marker（/cgi-bin/bizlogin、/cgi-bin/loginpage）→ 失效
        - 跳到 ``/cgi-bin/home`` 且带 token= → 有效
        - 其他 → 失效
        """
        logger.info("[Cookie检查] 开始检查cookie有效性: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
                await asyncio.sleep(3)

                current_url = page.url or ""
                # 失效 marker 命中即视为失效
                for marker in _COOKIE_INVALID_URL_MARKERS:
                    if marker in current_url:
                        logger.info("[Cookie检查] Cookie无效，跳转到登录页 (matched: %s)", marker)
                        return False
                # 跳到首页且带 token 视为有效
                if _HOME_PATH in current_url and "token=" in current_url:
                    logger.info("[Cookie检查] Cookie有效，已跳转到首页")
                    return True

                logger.warning("[Cookie检查] Cookie无效，当前 URL: %s", current_url)
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — refresh user name / avatar / stats
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> dict:
        """同步公众号昵称、头像、运营数据(stats)。

        用 cookie 打开 ``https://mp.weixin.qq.com/`` 自动跳转到带 token 的
        首页，从首页 DOM 抓取：
          - 昵称：.weui-desktop_name
          - 头像：.weui-desktop-account__img 的 src
          - 运营数据：原创内容(.original_cnt span)、总用户数(.weui-desktop-user_num
            .weui-desktop-user_sum span)
        """
        logger.info("[同步资料] 开始同步用户资料: %s", cookie_file)
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 跳转到带 token 的首页（cookie 触发自动跳转后 token 已在 URL）
                token = self._extract_token(page)
                home_url = self._build_home_url(token)
                logger.info("[同步资料] 跳转到首页: %s", home_url)
                try:
                    await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
                await asyncio.sleep(3)

                # 抓昵称/头像
                name, avatar = await scrape_weixin_gzh_profile(page)
                logger.info(
                    "[同步资料] 获取到用户信息 - 昵称: %s, 头像: %s",
                    name, avatar[:50] if avatar else "无"
                )

                # 抓运营数据
                stats = await self._scrape_stats(page)

                if not name and not avatar and not stats:
                    logger.info(f"[weixin_gzh] sync_profile 抓取为空, url={page.url}")

                return {"name": name, "avatar": avatar, "stats": stats}
            finally:
                await context.close()
        finally:
            await browser.close()

    async def _scrape_stats(self, page) -> list:
        """从公众号首页 DOM 抓取运营数据。

        DOM 结构（用户提供）：
          <div class="weui-desktop-content">原创内容
            <div class="weui-desktop-user_sum original_cnt"><span>2</span></div>
          </div>
          <div class="weui-desktop-user_num">总用户数
            <div class="weui-desktop-user_sum"><span>11</span></div>
          </div>
        """
        try:
            current_url = ""
            try:
                current_url = page.url or ""
            except Exception:
                pass
            logger.info("[stats] 开始抓取运营数据, 当前页面: %s", current_url)

            try:
                await page.wait_for_selector(".weui-desktop-user_sum", timeout=8000)
                logger.info("[stats] .weui-desktop-user_sum 元素已就绪")
            except Exception as e:
                logger.warning("[stats] 等待 .weui-desktop-user_sum 超时: %s", e)

            result = await page.evaluate(
                '''() => {
                    const out = [];
                    // 原创内容数
                    const originalEl = document.querySelector('.original_cnt span')
                        || document.querySelector('.original_cnt');
                    if (originalEl) {
                        out.push({title: '原创内容', num: (originalEl.textContent || '').trim()});
                    }
                    // 总用户数
                    const userNumWrap = document.querySelector('.weui-desktop-user_num');
                    if (userNumWrap) {
                        const numEl = userNumWrap.querySelector('.weui-desktop-user_sum span')
                            || userNumWrap.querySelector('.weui-desktop-user_sum');
                        if (numEl) {
                            out.push({title: '总用户数', num: (numEl.textContent || '').trim()});
                        }
                    }
                    return out;
                }'''
            )
            logger.info("[stats] DOM 抓取原始结果: %s", result)

            # label_map: 标题文 -> (ICON, SORT, 标准化 NAME)
            label_map = {
                "原创内容": ("edit", 1, "原创内容"),
                "总用户数": ("user",  2, "总用户数"),
            }
            stats = []
            for item in (result or []):
                title = item.get('title', '')
                num_str = str(item.get('num', '0'))
                if title in label_map:
                    icon, sort_no, std_name = label_map[title]
                    cleaned = num_str.replace(',', '').replace(' ', '').strip()
                    try:
                        count = int(float(cleaned)) if '.' in cleaned else int(cleaned) if cleaned else 0
                    except (ValueError, TypeError):
                        count = 0
                    stats.append({"ICON": icon, "COUNT": count, "NAME": std_name, "SORT": sort_no})
            logger.info("[stats] 解析得到 %d 项运营数据: %s", len(stats), stats)
            return stats
        except Exception as e:
            logger.error("[stats] 抓取运营数据异常: %s", e, exc_info=True)
            return []

    async def _login_stats_fn(self, page, account_id) -> list:
        """登录成功后的 stats 抓取入口（供 save_login_result 调用）。

        与 sync_profile._scrape_stats 共用同一份抓取逻辑，保证登录后同步
        与同步按钮看到的运营数据一致。
        """
        logger.info("[登录stats] 开始补抓运营数据, account_id=%s", account_id)
        try:
            # 登录路径下页面已在首页，但有时 DOM 还未渲染完，额外等待兜底
            await asyncio.sleep(2)
            stats = await self._scrape_stats(page)
            logger.info("[登录stats] 补抓完成, 共 %d 项", len(stats))
            return stats
        except Exception as e:
            logger.error("[登录stats] 补抓异常: %s", e, exc_info=True)
            return []

    # ------------------------------------------------------------------
    # open_creator_center — visible browser window
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """用可见浏览器打开微信公众号创作中心首页。

        cookie 自动带上，访问 ``https://mp.weixin.qq.com/`` 后会自动跳转到
        带 token 的首页。
        """
        logger.info("[打开创作中心] 正在打开创作中心...")
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _LOGIN_URL

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
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
    # publish_video — 暂未实现（公众号以图文为主，发布流程另开任务）
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        raise NotImplementedError("微信公众号发布功能暂未实现")
