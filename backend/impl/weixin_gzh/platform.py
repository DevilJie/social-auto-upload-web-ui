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
import os
import re
import threading
import time
from pathlib import Path
from queue import Queue

from util._logger import bind_account_name, get_channel_logger

from conf import BASE_DIR

from .._browser import create_browser_sync, create_context_sync
from .._utils import (
    clear_input,
    get_account_name_by_cookie_file,
    parse_schedule_time,
    raise_if_page_closed,
    save_login_result,
    scrape_weixin_gzh_profile,
)
from ..base_platform import BasePlatform

logger = get_channel_logger("weixin_gzh")

# 公众号首页入口（不带 token，访问后由 cookie 触发自动跳转到带 token 的 home）
_LOGIN_URL = "https://mp.weixin.qq.com/"
_HOME_PATH = "/cgi-bin/home"
_TOKEN_RE = re.compile(r"[?&]token=(\d+)")

# Dry-run 开关:WEIXIN_GZH_DRY_RUN_PUBLISH=1 时,平台流程停在发表按钮之前不真实发布。
# 用于 picker / 自动化数据填写准确性验证。
import os as _os_wx_dry
_DRY_RUN_PUBLISH = _os_wx_dry.environ.get("WEIXIN_GZH_DRY_RUN_PUBLISH", "1") == "1"

# 素材上传页（token 由 _resolve_token 拼装）。
# 对应文档：cgi-bin/appmsg?t=media/videomsg_edit&action=video_edit&type=15&isNew=1
_MATERIAL_UPLOAD_PATH = (
    "https://mp.weixin.qq.com/cgi-bin/appmsg"
    "?t=media/videomsg_edit&action=video_edit&type=15&isNew=1"
    "&token={token}&lang=zh_CN"
)
# 合集管理页（合集数据来源，type=5 为视频合集），token 由 _resolve_token 拼装。
_ALBUM_MGR_PATH = (
    "https://mp.weixin.qq.com/cgi-bin/appmsgalbummgr"
    "?action=list&token={token}&lang=zh_CN&type=5"
)

# 创作来源声明：前端文案 → 公众号弹窗内 radio 的 value。
# 文档要求「素材来源官方媒体/网络新闻」(value=2) 暂时从选项里移除，故不在此映射。
_CLAIM_SOURCE_MAP = {
    "内容由AI生成": "1",
    "内容剧情演绎，仅供娱乐": "3",
    "个人观点，仅供参考": "4",
    "健康医疗分享，仅供参考": "5",
    "投资观点，仅供参考": "6",
    "无需声明": "0",
}

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

    @staticmethod
    async def _resolve_token(page) -> str:
        """访问公众号首页，等待 cookie 触发跳转，解析并返回最新 token。

        所有带 token 的功能 URL（素材上传、合集管理）都必须用这个方法
        获取当前会话的有效 token —— token 每次会话会变，不能复用历史值。
        """
        await page.goto(_LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        # cookie 触发自动跳转到 /cgi-bin/home?...&token=XXX 需要一点时间
        deadline = asyncio.get_event_loop().time() + 15
        token = ""
        while asyncio.get_event_loop().time() < deadline:
            token = WeixinGzhPlatform._extract_token(page)
            if token:
                break
            await asyncio.sleep(0.5)
        if not token:
            logger.warning("[token] 未能从首页 URL 解析到 token, 当前 URL: %s", page.url)
        return token

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
    # publish_video — 公众号视频发布（同步入口）
    # ------------------------------------------------------------------

    def publish_video(self, **kwargs) -> bool:
        """Publish a video to WeChat Official Account (sync wrapper).

        Accepted keyword arguments (与其它平台保持一致):

        - ``title`` (*str*) -- 视频标题(≤64 字)
        - ``files`` (*list[str]*) -- 视频绝对路径(app.py 解析过)
        - ``tags`` (*list[str]*) -- 话题,拼成 #话题 写进描述(占位)
        - ``account_file`` (*list[str]*) -- cookie 文件名列表
        - ``thumbnail_landscape_169_path`` (*str*, optional) -- 16:9 封面(公众号固定用 16:9)
        - ``thumbnail_landscape_path`` / ``thumbnail_portrait_path`` -- 兜底封面
        - ``desc`` (*str*, optional) -- 视频介绍(≤300 字, 含 # 标签)
        - ``is_original`` (*bool*, optional) -- 声明原创
        - ``gzh_collection_name`` (*str*, optional) -- 合集名
        - ``gzh_claim_source`` (*str*, optional) -- 创作来源(文案)
        - ``enableTimer`` (*bool*, optional) -- 定时发布
        - ``schedule_time_str`` (*str*, optional) -- 定时时间
        """
        asyncio.run(self._upload_all(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal: upload all (files × accounts)
    # ------------------------------------------------------------------

    async def _upload_all(self, **kwargs):
        """files × accounts 笛卡尔积编排(与微博保持一致)。"""
        logger.info("=" * 60)
        logger.info("[发布视频] 开始微信公众号视频发布流程")
        logger.info("=" * 60)

        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        thumbnail_169 = kwargs.get("thumbnail_landscape_169_path")
        thumbnail_landscape = kwargs.get("thumbnail_landscape_path")
        thumbnail_portrait = kwargs.get("thumbnail_portrait_path")
        desc = kwargs.get("desc", "") or ""
        is_original = kwargs.get("is_original", False)
        gzh_collection_name = kwargs.get("gzh_collection_name", "") or ""
        gzh_claim_source = kwargs.get("gzh_claim_source", "") or ""
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")

        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 文件数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 16:9 封面: %s", thumbnail_169 or "无")
        logger.info("[发布参数] 横版封面: %s", thumbnail_landscape or "无")
        logger.info("[发布参数] 竖版封面: %s", thumbnail_portrait or "无")
        logger.info("[发布参数] 原创: %s", is_original)
        logger.info("[发布参数] 合集: %s", gzh_collection_name or "无")
        logger.info("[发布参数] 创作来源: %s", gzh_claim_source or "无")
        logger.info("[发布参数] 定时发布: %s", enable_timer)

        # 公众号封面固定使用 16:9;前端没传 169 时用横版兜底
        cover_path = thumbnail_169 or thumbnail_landscape or thumbnail_portrait

        account_paths = [str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file]
        file_paths = [str(f) for f in files]
        if cover_path:
            cover_path = str(cover_path)

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
                        cover_path=cover_path,
                        desc=desc,
                        is_original=is_original,
                        gzh_collection_name=gzh_collection_name,
                        gzh_claim_source=gzh_claim_source,
                        enable_timer=enable_timer,
                        schedule_time_str=schedule_time_str,
                        files_count=len(file_paths),
                    )

        logger.info("=" * 60)
        logger.info("[发布视频] 视频发布流程完成!")
        logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Internal: upload one video to one account (two-stage flow)
    # ------------------------------------------------------------------

    async def _upload_one_video(
        self,
        title: str,
        file_path: str,
        tags: list,
        account_file: str,
        cover_path=None,
        desc="",
        is_original=False,
        gzh_collection_name="",
        gzh_claim_source="",
        enable_timer=False,
        schedule_time_str="",
        files_count=1,
    ):
        """单视频单账号完整两阶段发布。

        阶段① 素材上传页 videomsg_edit: 传视频→封面→标题→原创→服务规则→保存并发表
        阶段② 发布编辑页 appmsg_edit_v2(新 tab): 标题/描述→合集→创作来源→发表/定时
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

                # 解析当前会话 token
                token = await self._resolve_token(page)
                if not token:
                    raise RuntimeError("[发布] 未能获取 token,cookie 可能已失效")
                logger.info("[发布] 获取到 token: %s", token)

                # ===== 阶段① 素材上传页 =====
                material_url = _MATERIAL_UPLOAD_PATH.format(token=token)
                logger.info("[阶段①] 打开素材上传页: %s", material_url)
                await page.goto(material_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 1. 上传视频文件
                logger.info("[阶段①] 上传视频文件: %s", os.path.basename(file_path))
                await self._upload_video_file(page, file_path)

                # 2. 等待视频上传完成
                logger.info("[阶段①] 等待视频上传完成...")
                await self._wait_for_video_uploaded(page)
                logger.info("[阶段①] 视频上传成功!")

                # 3. 封面(公众号固定 16:9)
                if cover_path:
                    logger.info("[阶段①] 开始设置封面...")
                    await self._set_cover(page, cover_path)
                    logger.info("[阶段①] 封面设置完成")
                else:
                    logger.info("[阶段①] 未提供封面,跳过")

                # 4. 标题
                logger.info("[阶段①] 填写标题: %s", title)
                await self._fill_material_title(page, title)

                # 5. 原创声明
                if is_original:
                    logger.info("[阶段①] 开启原创声明...")
                    await self._set_original(page)
                else:
                    logger.info("[阶段①] 未开启原创,跳过")

                # 6. 勾选服务规则
                logger.info("[阶段①] 勾选服务规则...")
                await self._check_service_rule(page)

                # 7. 保存并发表(打开新 tab 进入阶段②)
                logger.info("[阶段①] 点击「保存并发表」,等待新页面打开...")
                page2 = await self._click_save_and_send(page, context)
                logger.info("[阶段②] 新页面已打开: %s", page2.url)

                # ===== 阶段② 发布编辑页 =====
                await page2.wait_for_load_state("domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 0. 关闭教育弹窗(「支持添加话题卡片」等引导,按钮=我知道了)
                #    弹窗 DOM: div.weui-desktop-dialog > ... > button.weui-desktop-btn_primary
                #    不点掉会遮挡后续填写/发表操作。短时轮询,点不到不阻塞流程。
                await self._dismiss_education_dialog(page2)

                # 1. 再次填标题(发布页标题独立于素材标题)
                logger.info("[阶段②] 填写发布页标题: %s", title)
                await self._fill_publish_title(page2, title)

                # 2. 描述(含 # 标签)
                logger.info("[阶段②] 填写描述/标签...")
                await self._fill_description(page2, desc, title, tags)

                # 3. 合集
                if gzh_collection_name:
                    logger.info("[阶段②] 选择合集: %s", gzh_collection_name)
                    await self._set_collection(page2, gzh_collection_name)
                else:
                    logger.info("[阶段②] 未选择合集,跳过")

                # 4. 创作来源
                if gzh_claim_source:
                    logger.info("[阶段②] 设置创作来源: %s", gzh_claim_source)
                    await self._set_claim_source(page2, gzh_claim_source)
                else:
                    logger.info("[阶段②] 未设置创作来源,跳过")

                # 5. 发表(立即 / 定时) — Dry-run 模式下停在按钮前不真实发布
                if _DRY_RUN_PUBLISH:
                    logger.info(
"[阶段②] 🐛 DRY_RUN=1 跳过点击发布, 浏览器保持打开供人工核对数据填写",
                    )
                    logger.info("[阶段②] 🐛 当前状态: 标题/描述/标签/封面/创作者声明/合集/创作来源 已填好")
                    try:
                        await page2.screenshot(
                            path=str(log_dir / "weixin_gzh_dry_run.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass
                    # 阻塞在这里,直到用户手动关闭浏览器,方便反复查看
                    try:
                        logger.info("[阶段②] 🐛 等待浏览器关闭(请手动关闭或确认后关闭)...")
                        await page2.wait_for_event("close", timeout=0)
                    except Exception:
                        pass
                else:
                    if enable_timer and schedule_time_str:
                        publish_dt = self._build_publish_datetime(schedule_time_str, files_count)
                        if publish_dt and not (isinstance(publish_dt, int) and publish_dt == 0):
                            logger.info("[阶段②] 定时发布: %s", publish_dt)
                            await self._publish_scheduled(page2, publish_dt)
                        else:
                            logger.info("[阶段②] 定时时间解析失败,改为立即发表")
                            await self._publish_immediate(page2)
                    else:
                        logger.info("[阶段②] 立即发表...")
                        await self._publish_immediate(page2)

                logger.info("[发布] 视频发布成功!")

                # 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[发布] Cookie 状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    # ------------------------------------------------------------------
    # Helper: parse schedule datetime
    # ------------------------------------------------------------------

    @staticmethod
    def _build_publish_datetime(schedule_time_str, total_files):
        """解析定时发布时间为本地 datetime,失败返回 0。

        公众号定时只能选最近 7 天(含当天),且时间必须 > 当前 + 1 小时,
        交给 _publish_scheduled 在选择时处理;此处仅做解析。
        """
        result = parse_schedule_time(
            schedule_time_str, total_files, True, None, None, None,
        )
        if result:
            return result[0]
        return 0

    # ------------------------------------------------------------------
    # Stage ① helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_video_file(page, file_path: str):
        """上传视频主文件。

        素材上传页的 file input 形如:
          <input title="上传视频" name="vid" type="file" accept="video/*"
                 class="weui-desktop-upload-input">
        直接 set_input_files 即可(与微博不同,公众号的上传 input 在 DOM 中常驻)。
        """
        file_size = os.path.getsize(file_path)
        logger.info(
            "[阶段①] 准备上传视频: %s (%.1f MB)",
            os.path.basename(file_path), file_size / 1024 / 1024,
        )
        upload_input = page.locator("input[type='file'][name='vid']").first
        await upload_input.wait_for(state="attached", timeout=15000)
        await upload_input.set_input_files(file_path)
        logger.info("[阶段①] 视频文件已提交,等待上传...")

    @staticmethod
    async def _wait_for_video_uploaded(page, timeout_s: int = 14400):
        """等待视频上传完成。

        权威信号: ``.weui-desktop-upload__file__extra-info`` 内出现
        「视频上传成功」文本(DOM 见需求文档):
          <p class="tips_global">视频上传成功，你可以继续编辑其它信息保存提交</p>

        上传过程中有进度 DOM(剩余时间/速度/已上传百分比),打印进度的旁证日志。
        失败信号:「转码失败」。

        **可见性是关键**: 公众号页面初始 DOM 里就常驻「视频上传成功」「转码失败」
        两段模板文案(包在 ``display:none`` 的 mask/tips 容器里),只有对应状态触发
        时容器才显示。因此必须用 JS 判断元素真正可见(offsetParent != null),
        否则一进上传就误判成功/失败。

        默认超时 4 小时(大视频 + 慢网络留余量)。
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        last_progress = ""
        while asyncio.get_event_loop().time() < deadline:
            raise_if_page_closed(page)
            # 成功信号: 文本「视频上传成功」且元素可见
            try:
                success_visible = await page.evaluate(
                    """() => {
                        const all = Array.from(document.querySelectorAll('*'));
                        const hit = all.find(el =>
                            el.children.length === 0 &&
                            (el.textContent || '').indexOf('视频上传成功') !== -1 &&
                            el.offsetParent !== null
                        );
                        return !!hit;
                    }"""
                )
                if success_visible:
                    logger.info("[阶段①] 检测到「视频上传成功」")
                    return
            except Exception:
                pass
            # 失败信号: 文本「转码失败」且其 mask 容器可见
            try:
                fail_visible = await page.evaluate(
                    """() => {
                        const masks = document.querySelectorAll(
                            '.weui-desktop-mask_status, .weui-desktop-mask_msg'
                        );
                        for (const m of masks) {
                            if (m.offsetParent === null) continue;
                            if ((m.textContent || '').indexOf('转码失败') !== -1) {
                                return true;
                            }
                        }
                        return false;
                    }"""
                )
                if fail_visible:
                    raise RuntimeError("[阶段①] 视频转码失败,无法继续")
            except RuntimeError:
                raise
            except Exception:
                pass
            # 进度旁证
            try:
                pct = await page.locator(
                    ".weui-desktop-upload__file__extra-info__item"
                ).all_inner_texts()
                progress = " | ".join(t.strip() for t in pct if t.strip())
                if progress and progress != last_progress:
                    logger.info("[阶段①] 上传进度: %s", progress)
                    last_progress = progress
            except Exception:
                pass
            await asyncio.sleep(5)
        raise RuntimeError(f"[阶段①] 视频上传等待超时({timeout_s}s)")

    @staticmethod
    async def _set_cover(page, cover_path: str):
        """设置视频封面(固定 16:9)。

        流程(文档):
          1. 上传视频后出现 ``.cover__options__item_empty``(从图片库选择),点击
          2. 弹窗内出现隐藏的 ``input[type=file][accept*='image']``,set_input_files
          3. 等「下一步」按钮去掉 weui-desktop-btn_disabled 后点击
          4. 等「完成」按钮可点后点击,完成封面设置
        """
        # 1. 点击「从图片库选择」空位
        empty_item = page.locator(".cover__options__item_empty").first
        await empty_item.wait_for(state="visible", timeout=15000)
        await asyncio.sleep(1)
        await empty_item.click()
        logger.info("[阶段①] 已点击「从图片库选择」,等待封面上传弹窗...")

        # 2. 上传封面文件(弹窗内的隐藏 input)
        cover_input = page.locator("input[type='file'][accept*='image']").first
        await cover_input.wait_for(state="attached", timeout=15000)
        await cover_input.set_input_files(cover_path)
        logger.info("[阶段①] 封面文件已提交: %s", os.path.basename(cover_path))
        await asyncio.sleep(3)

        # 3. 等「下一步」按钮可点后点击
        await WeixinGzhPlatform._click_primary_when_enabled(
            page, "下一步", timeout_s=60,
        )
        logger.info("[阶段①] 已点击「下一步」,等待「完成」按钮...")

        # 4. 等「完成」按钮可点后点击
        await asyncio.sleep(2)
        await WeixinGzhPlatform._click_primary_when_enabled(
            page, "完成", timeout_s=60,
        )
        logger.info("[阶段①] 已点击「完成」,封面设置完成")
        await asyncio.sleep(2)

    @staticmethod
    async def _click_primary_when_enabled(page, button_text: str, timeout_s: int = 60):
        """等某个 ``weui-desktop-btn_primary`` 按钮去掉 ``weui-desktop-btn_disabled``
        后点击(公众号按钮禁用态靠加 disabled class 实现)。

        通过 JS 判断:该按钮同时含 primary 且不含 disabled class。
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            clicked = await page.evaluate(
                """(text) => {
                    const btns = document.querySelectorAll(
                        'button.weui-desktop-btn_primary:not(.weui-desktop-btn_disabled)'
                    );
                    for (const b of btns) {
                        if ((b.textContent || '').trim().indexOf(text) !== -1) {
                            b.click();
                            return true;
                        }
                    }
                    return false;
                }""",
                button_text,
            )
            if clicked:
                return
            await asyncio.sleep(1)
        raise RuntimeError(
            f"[阶段①] 「{button_text}」按钮在 {timeout_s}s 内未变为可点击状态"
        )

    @staticmethod
    async def _fill_material_title(page, title: str):
        """素材上传页标题:``input[name='title']``,≤64 字。"""
        title_input = page.locator("input[name='title']").first
        await title_input.wait_for(state="visible", timeout=10000)
        await title_input.fill((title or "")[:64])
        logger.info("[阶段①] 素材标题已填写(%d 字)", len((title or "")[:64]))

    @staticmethod
    async def _set_original(page):
        """开启原创声明。

        流程(实测,2026 新版 DOM):
        1. **判定当前账号是否有原创权益**: 检测 ``.declare-original-checkbox``
           是否存在。存在 = 该账号支持原创声明;不存在 = 跳过整个流程
           (没权益的账号点了也无效,反而弹窗流程会卡)。
        2. 点 checkbox 开关 ``.declare-original-checkbox .ant-checkbox-wrapper``
           → 触发 .declare-original-dialog 弹窗(默认 display:none → 显现)。
        3. 弹窗里勾选协议 checkbox: ``.original-proto-wrapper .ant-checkbox-wrapper``
           (勾上后「声明原创」按钮的 _disabled 类才会去掉)。
        4. 等「声明原创」按钮去掉 ``weui-desktop-btn_disabled`` 后点击。
        5. 兜底关弹窗。

        DOM 参考:
          开关区: ``.declare-original-checkbox > label.ant-checkbox-wrapper``
          协议弹窗: ``.declare-original-dialog .weui-desktop-dialog``
          协议勾选: ``.original-proto-wrapper .ant-checkbox-wrapper``
          确认按钮: ``.declare-original-dialog button.weui-desktop-btn_primary``
          取消按钮: ``.declare-original-dialog button.weui-desktop-btn_default``
        """
        # 1. 检测账号是否有原创权益(开关区存在性)
        declare_checkbox = page.locator(".declare-original-checkbox").first
        try:
            await declare_checkbox.wait_for(state="visible", timeout=10000)
        except Exception:
            logger.warning(
                "[阶段①] 当前账号没有原创权益(.declare-original-checkbox 不存在),跳过原创声明"
            )
            return

        # 2. 点 checkbox 打开协议弹窗
        wrap = declare_checkbox.locator("label.ant-checkbox-wrapper").first
        try:
            await wrap.wait_for(state="visible", timeout=5000)
            await wrap.click()
        except Exception as exc:
            logger.warning("[阶段①] 找不到/点不到原创声明 checkbox: %s", exc)
            return
        logger.info("[阶段①] 已点击原创声明 checkbox,等待协议弹窗...")
        await asyncio.sleep(1.5)

        # 3. 等协议弹窗内的勾选出现
        proto_wrap = page.locator(".declare-original-dialog .original-proto-wrapper label.ant-checkbox-wrapper").first
        try:
            await proto_wrap.wait_for(state="visible", timeout=10000)
        except Exception as exc:
            logger.warning("[阶段①] 未出现原创协议勾选框,可能该账号无权益: %s", exc)
            return

        # 4. 勾选协议
        try:
            await proto_wrap.click()
        except Exception as exc:
            logger.warning("[阶段①] 勾选原创协议失败: %s", exc)
            return
        logger.info("[阶段①] 已勾选原创协议,等待「声明原创」按钮可点击...")
        await asyncio.sleep(0.5)

        # 5. 等「声明原创」按钮 enabled 后点击
        confirm_btn = page.locator(
            ".declare-original-dialog button.weui-desktop-btn_primary"
        ).first
        deadline = asyncio.get_event_loop().time() + 15
        clicked = False
        while asyncio.get_event_loop().time() < deadline:
            try:
                if await confirm_btn.count() > 0 and await confirm_btn.is_visible():
                    disabled = await confirm_btn.evaluate(
                        "el => el.classList.contains('weui-desktop-btn_disabled')"
                    )
                    if not disabled:
                        await confirm_btn.click()
                        clicked = True
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        if clicked:
            logger.info("[阶段①] 已点击「声明原创」,原创声明流程完成")
        else:
            logger.warning("[阶段①] 「声明原创」按钮 15s 内未启用")
        await asyncio.sleep(1)

        # 6. 兜底关弹窗(若还开着)
        try:
            close_btn = page.locator(
                ".declare-original-dialog .weui-desktop-dialog__close-btn"
            ).first
            if await close_btn.count() > 0 and await close_btn.is_visible():
                await close_btn.click()
                logger.info("[阶段①] 已关闭原创协议弹窗")
        except Exception:
            pass

    @staticmethod
    async def _check_service_rule(page):
        """勾选 footer 的《公众平台视频上传服务规则》checkbox。

        DOM(文档): ``.video-setting__footer-link input.weui-desktop-form__checkbox``
        """
        cb = page.locator(
            ".video-setting__footer-link input.weui-desktop-form__checkbox"
        ).first
        try:
            await cb.wait_for(state="attached", timeout=10000)
        except Exception:
            logger.warning("[阶段①] 未找到服务规则 checkbox,跳过")
            return
        # 仅在未勾选时勾选
        try:
            checked = await cb.is_checked()
        except Exception:
            checked = False
        if not checked:
            # checkbox 常被 label 遮挡,用 JS 直接勾选
            await cb.evaluate("el => { if (!el.checked) el.click(); }")
            logger.info("[阶段①] 已勾选服务规则")
        await asyncio.sleep(0.5)

    @staticmethod
    async def _click_save_and_send(page, context):
        """点击「保存并发表」,返回打开的发布编辑页(新 tab)。

        DOM(文档): ``.video-save-send-btn button``

        流程:
          1. 点「保存并发表」
          2. 未声明原创时会弹「提交视频」确认框,需点「继续提交」才会开新 tab
             (声明了原创则可能直接开新 tab)
          3. 浏览器打开新 tab(发布编辑页 appmsg_edit_v2)

        **关键坑(实测)**: 不能用 ``context.expect_page`` 抢第一个新 tab ——
        公众号页面会先弹一个 ``about:blank`` 的广告/统计 tab,expect_page 会
        把它误当成目标页,导致真正的「继续提交」弹窗没人点、流程卡死、
        最终 watchdog 关闭浏览器。

        正确做法:
          - 用 ``context.on("page", ...)`` 收集所有新 tab,但只接受 URL 含
            ``appmsg_edit`` 的(过滤掉 about:blank 广告页);
          - 显式轮询点击可见的「继续提交」/「继续发布」确认弹窗;
          - 新 tab 的 URL 一开始可能是 about:blank,要等它导航到 appmsg_edit。
        """
        # 监听所有新 tab,记录"可能的目标页"(URL 含 appmsg_edit 的)
        candidate_holder = {"page": None}

        def _on_new_page(new_page):
            try:
                url = new_page.url or ""
            except Exception:
                url = ""
            logger.info("[阶段①] 检测到新 tab: %s", url or "(about:blank)")
            # 只认发布编辑页;about:blank/广告页忽略(发布页 URL 含 appmsg_edit)
            if "appmsg_edit" in url:
                candidate_holder["page"] = new_page

        context.on("page", _on_new_page)

        try:
            save_send_btn = page.locator(".video-save-send-btn button").first
            await save_send_btn.wait_for(state="visible", timeout=15000)

            # 「保存并发表」初始可能 disabled,等其可点后点击
            deadline = asyncio.get_event_loop().time() + 60
            clicked = False
            while asyncio.get_event_loop().time() < deadline:
                disabled = await save_send_btn.evaluate(
                    "el => el.classList.contains('weui-desktop-btn_disabled')"
                )
                if not disabled:
                    await save_send_btn.click()
                    clicked = True
                    break
                await asyncio.sleep(1)
            if not clicked:
                await save_send_btn.click(force=True)
            logger.info("[阶段①] 已点击「保存并发表」,等待弹窗/新页面...")

            # 轮询: 处理确认弹窗 + 等待目标新 tab 导航到 appmsg_edit
            #
            # **可见性是关键**: 页面初始 DOM 里常驻多个 display:none 弹窗模板
            # (提交视频/视频发布/原创须知),只点 offsetParent !== null 的按钮。
            #
            # **导航销毁异常**: 点完「继续提交」后旧页面会发生导航跳转,context
            # 被销毁,此后对该 page 的 evaluate 会抛 "Execution context was
            # destroyed"。这恰恰说明弹窗确认生效、正在跳转,应捕获后转去等目标页。
            wait_deadline = asyncio.get_event_loop().time() + 120
            handled_dialogs = set()
            target_page = None
            while asyncio.get_event_loop().time() < wait_deadline:
                # 新 tab 可能已出现但 URL 还是 about:blank,补查它的最新 URL
                if candidate_holder["page"] is not None:
                    target_page = candidate_holder["page"]
                    break
                # 也可在 context.pages 里找已导航到 appmsg_edit 的 tab
                for p in context.pages:
                    try:
                        if p is page:
                            continue
                        if "appmsg_edit" in (p.url or ""):
                            target_page = p
                            candidate_holder["page"] = p
                            break
                    except Exception:
                        continue
                if target_page is not None:
                    break

                # 处理「继续提交」(提交视频弹窗,未声明原创时出现) / 「继续发布」
                try:
                    for btn_text in ("继续提交", "继续发布", "继续"):
                        if btn_text in handled_dialogs:
                            continue
                        clicked_dialog = await page.evaluate(
                            """(text) => {
                                const btns = document.querySelectorAll(
                                    '.weui-desktop-dialog button.weui-desktop-btn_primary'
                                );
                                for (const b of btns) {
                                    if ((b.textContent || '').trim().indexOf(text) === -1) continue;
                                    // 按钮自身必须可见(排除 display:none 模板里的按钮)
                                    if (b.offsetParent === null) continue;
                                    b.click();
                                    return true;
                                }
                                return false;
                            }""",
                            btn_text,
                        )
                        if clicked_dialog:
                            logger.info("[阶段①] 已点击中间确认弹窗「%s」", btn_text)
                            handled_dialogs.add(btn_text)
                            await asyncio.sleep(1.5)
                            break
                    else:
                        await asyncio.sleep(1)
                except Exception as e:
                    # 旧页面导航/context 销毁(点了继续提交后跳转),不是错误,
                    # 转去等目标新 tab 导航到 appmsg_edit
                    logger.info("[阶段①] 弹窗处理后页面已导航(预期行为): %s", str(e)[:80])
                    break

            # 等目标页出现并导航到 appmsg_edit(点了继续提交后新 tab 才会跳转)
            if target_page is None:
                # 轮询结束时还没拿到,再从 context.pages 兜底找一次
                for _ in range(30):
                    for p in context.pages:
                        try:
                            if p is page:
                                continue
                            if "appmsg_edit" in (p.url or ""):
                                target_page = p
                                candidate_holder["page"] = p
                                break
                        except Exception:
                            continue
                    if target_page is not None:
                        break
                    await asyncio.sleep(1)

            if target_page is None:
                raise RuntimeError(
                    "[阶段①] 点击「保存并发表」后未捕获到发布编辑页新 tab"
                )

            # 新 tab 可能还在 about:blank,等它导航到 appmsg_edit
            try:
                await target_page.wait_for_url(
                    "**/appmsg_edit*", timeout=30000,
                )
            except Exception as e:
                logger.info("[阶段①] 新 tab URL 等待(非致命): %s, 当前: %s", e, target_page.url)
            await target_page.bring_to_front()
            return target_page
        finally:
            context.remove_listener("page", _on_new_page)

    # ------------------------------------------------------------------
    # Stage ② helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _dismiss_education_dialog(page, timeout_s: int = 10):
        """关闭发布编辑页(阶段②)可能弹出的教育引导弹窗。

        实测 DOM（宽度 960px 的 weui-desktop-dialog）:
        ``div.weui-desktop-dialog > div.weui-desktop-dialog__ft >
        button.weui-desktop-btn.weui-desktop-btn_primary``(文本=我知道了)
        另有右上角关闭按钮 ``weui-desktop-dialog__close-btn`` 可兜底。
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                known_btn = page.locator(
                    "div.weui-desktop-dialog button.weui-desktop-btn_primary"
                ).filter(has_text="我知道了").first
                if await known_btn.is_visible():
                    await known_btn.click()
                    logger.info("[阶段②] 已点击教育弹窗「我知道了」")
                    await asyncio.sleep(0.5)
                    return
                close_btn = page.locator(
                    "div.weui-desktop-dialog .weui-desktop-dialog__close-btn"
                ).first
                if await close_btn.is_visible():
                    await close_btn.click()
                    logger.info("[阶段②] 已点教育弹窗关闭按钮(X)")
                    await asyncio.sleep(0.5)
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)
        logger.info("[阶段②] 未检测到教育弹窗,继续")

    @staticmethod
    async def _fill_publish_title(page, title: str, max_len: int = 64):
        """发布编辑页标题。

        - 视频版: ``#title textarea.js_title`` 可见,直接 fill。
        - 图集版(贴图): 同 id 的 textarea 被 ``visibility:hidden`` 隐藏,真正可编辑的是
          ProseMirror 覆盖层 ``.title-editor-overlay .ProseMirror``(contenteditable)。
          检测到 textarea 不可见时,改用 press_sequentially 往 ProseMirror 输入。

        max_len 默认 64(视频),图集传 20。
        """
        text = (title or "")[:max_len]
        title_textarea = page.locator("#title.js_title").first
        if await title_textarea.count() == 0:
            title_textarea = page.locator("textarea.js_title").first

        # 图集版: textarea 隐藏 → 用 ProseMirror 覆盖层(contenteditable)
        textarea_visible = False
        try:
            textarea_visible = await title_textarea.is_visible()
        except Exception:
            textarea_visible = False

        if textarea_visible:
            # 视频版: 直接 fill textarea
            await title_textarea.fill(text)
            logger.info("[阶段②] 发布页标题已填写(%d 字, textarea fill)", len(text))
            return

        # 图集版: 找 ProseMirror 覆盖层,press_sequentially 逐字符输入
        pm = page.locator(".title-editor-overlay .ProseMirror").first
        await pm.wait_for(state="visible", timeout=10000)
        try:
            await pm.click()
        except Exception:
            pass
        await pm.press_sequentially(text, delay=30)
        await asyncio.sleep(0.5)
        logger.info("[阶段②] 发布页标题已填写(%d 字, ProseMirror)", len(text))

    @staticmethod
    async def _fill_description(page, desc: str, title: str, tags: list, max_len: int = 300):
        """填写描述(contenteditable ProseMirror),含 # 标签。

        DOM(文档): ``#guide_words_main .ProseMirror``(contenteditable)
        desc 为空时保持为空(不回落 title);tags 拼成 ``#话题`` 追加。
        按 CLAUDE.md: contenteditable 用 press_sequentially 逐字符输入,
        比剪贴板粘贴/keyboard.type 更可靠地触发 React onChange。
        max_len 默认 300(视频),图集传 1000。
        """
        editor = page.locator("#guide_words_main .ProseMirror").first
        await editor.wait_for(state="visible", timeout=15000)

        # 组装最终文本: desc + # 话题（描述为空不回落标题）
        base = (desc or "").strip()
        tag_parts = [f"#{t.strip()}" for t in (tags or []) if str(t).strip()]
        tag_text = " ".join(tag_parts)
        full = f"{base} {tag_text}".strip() if tag_text else base
        # 截断到 max_len 字(含 # 标签,文档要求)
        full = full[:max_len]
        if not full:
            logger.info("[阶段②] 描述为空,跳过")
            return

        # 先清空(contenteditable: 点击聚焦 + 全选 + 删除)
        await clear_input(page, element=editor)
        # press_sequentially: 自动 focus + 逐字符触发 onChange/drop 事件
        await editor.press_sequentially(full, delay=30)
        await asyncio.sleep(0.5)
        logger.info("[阶段②] 描述已填写(%d 字)", len(full))

    @staticmethod
    async def _set_collection(page, collection_name: str):
        """设置合集(发布编辑页)。

        流程(文档):
          1. 点 ``#js_article_tags_area .js_article_tags_label``(未添加区域)
          2. 弹窗内点 ``input[placeholder='请选择合集']`` 展开下拉
          3. 下拉 ``li.select-opt-li`` 匹配合集名后点击
          4. 点弹窗「确认」(``.weui-desktop-dialog__ft`` 内 primary)
        """
        # 1. 点击「未添加」入口
        entry = page.locator("#js_article_tags_area .js_article_tags_label").first
        await entry.wait_for(state="visible", timeout=10000)
        await entry.click()
        logger.info("[阶段②] 已点击合集入口,等待弹窗...")
        await asyncio.sleep(1.5)

        # 2. 展开合集下拉
        select_input = page.locator("input[placeholder='请选择合集']").first
        try:
            await select_input.wait_for(state="visible", timeout=10000)
            await select_input.click()
        except Exception as e:
            logger.warning("[阶段②] 未找到合集选择输入框: %s", e)
            return
        await asyncio.sleep(1)

        # 3. 匹配并点击合集项
        matched = await page.evaluate(
            """(name) => {
                const opts = document.querySelectorAll('li.select-opt-li');
                for (const li of opts) {
                    if ((li.textContent || '').trim() === name) {
                        li.click();
                        return true;
                    }
                }
                return false;
            }""",
            collection_name,
        )
        if matched:
            logger.info("[阶段②] 已选中合集: %s", collection_name)
        else:
            logger.warning("[阶段②] 未找到合集「%s」", collection_name)
        await asyncio.sleep(1)

        # 4. 点「确认」
        await WeixinGzhPlatform._click_dialog_primary(page, "确认")
        logger.info("[阶段②] 合集设置完成")
        await asyncio.sleep(1)

    @staticmethod
    async def _set_claim_source(page, claim_source: str):
        """设置创作来源(发布编辑页)。

        流程(文档):
          1. 点 ``#js_claim_source_area``(未添加区域)
          2. 弹窗内点对应声明类型 radio(value 见 _CLAIM_SOURCE_MAP)
          3. 点弹窗「确认」

        注:文档要求「素材来源官方媒体/网络新闻」(value=2)暂从选项移除,
        因此 _CLAIM_SOURCE_MAP 不含该项。
        """
        value = _CLAIM_SOURCE_MAP.get(claim_source)
        if not value:
            # 兜底:按文案模糊匹配
            for label, v in _CLAIM_SOURCE_MAP.items():
                if claim_source in label or label in claim_source:
                    value = v
                    break
        if not value:
            logger.warning("[阶段②] 未知创作来源「%s」,跳过", claim_source)
            return

        # 1. 点击入口
        # 点「未添加」可点击区域(.js_claim_source_desc),不是整个容器 #js_claim_source_area
        # —— 后者点的是 label,只会勾选 checkbox 而不会弹出设置弹窗。
        entry = page.locator("#js_claim_source_area .js_claim_source_desc").first
        if await entry.count() == 0:
            entry = page.locator("#js_claim_source_area").first
        await entry.wait_for(state="visible", timeout=10000)
        await entry.click()
        logger.info("[阶段②] 已点击创作来源入口,等待弹窗...")
        await asyncio.sleep(1.5)

        # 2. 点对应 radio —— 用文案精确定位(比 value 更稳,文案与用户选择直接对应)
        #    DOM: .weui-desktop-form__check-label > span.weui-desktop-form__check-content(文案)
        #         同一 label 内 input.weui-desktop-form__radio[value=N]
        target_label = claim_source
        radio_clicked = await page.evaluate(
            """(label) => {
                const labels = document.querySelectorAll(
                    '.claim-source_dialog_panel .weui-desktop-form__check-label'
                );
                for (const lab of labels) {
                    const span = lab.querySelector('.weui-desktop-form__check-content');
                    if (span && (span.textContent || '').trim() === label) {
                        lab.click();
                        return true;
                    }
                }
                return false;
            }""",
            target_label,
        )
        if radio_clicked:
            logger.info("[阶段②] 已选择创作来源: %s (value=%s)", claim_source, value)
        else:
            logger.warning("[阶段②] 未找到创作来源「%s」(value=%s)", claim_source, value)
        await asyncio.sleep(1)

        # 3. 点「确认」(初始 disabled,选中 radio 后启用)
        await WeixinGzhPlatform._click_dialog_primary(page, "确认", timeout_s=15)
        logger.info("[阶段②] 创作来源设置完成")
        await asyncio.sleep(1)

    @staticmethod
    async def _click_dialog_primary(page, button_text: str, timeout_s: int = 30):
        """点击当前可见弹窗(weui-desktop-dialog)内的 primary 按钮(等其去掉 disabled)。

        定位: ``.weui-desktop-dialog:not([style*='display: none']) .weui-desktop-btn_primary``
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            clicked = await page.evaluate(
                """(text) => {
                    const dialogs = document.querySelectorAll('.weui-desktop-dialog');
                    for (const d of dialogs) {
                        const wrp = d.closest('.weui-desktop-dialog__wrp');
                        if (wrp && wrp.style && wrp.style.display === 'none') continue;
                        const btns = d.querySelectorAll(
                            'button.weui-desktop-btn_primary:not(.weui-desktop-btn_disabled)'
                        );
                        for (const b of btns) {
                            if ((b.textContent || '').trim().indexOf(text) !== -1) {
                                b.click();
                                return true;
                            }
                        }
                    }
                    return false;
                }""",
                button_text,
            )
            if clicked:
                return
            await asyncio.sleep(1)
        logger.warning("[阶段②] 「%s」按钮在 %ds 内未可点", button_text, timeout_s)

    @staticmethod
    async def _publish_immediate(page):
        """立即发表。

        流程:
          1. 点页面「发表」(#js_send) → 弹出 .mass-send 发表弹窗
             (含群发通知/定时发表选项,立即发表不碰定时开关)
          2. 直接点弹窗底部「发表」按钮(.mass-send__footer 内 primary)
          3. 弹出二次确认弹窗 → 点「继续发表」
          4. 二次确认后弹扫码确认(用户微信扫码) → 等页面跳转首页

        成功信号: URL 跳转到 /cgi-bin/home
        """
        # 1. 点页面「发表」打开发表弹窗
        send_btn = page.locator("#js_send .mass_send").first
        await send_btn.wait_for(state="visible", timeout=15000)
        await send_btn.click()
        logger.info("[阶段②] 已点击「发表」,等待发表弹窗...")
        await asyncio.sleep(2)

        # 2. 点弹窗底部「发表」(不开定时开关,直接发)
        await WeixinGzhPlatform._click_dialog_primary(page, "发表", timeout_s=15)
        logger.info("[阶段②] 已点击弹窗「发表」,等待确认...")

        # 3. 二次确认弹窗「继续发表」(若有)
        await asyncio.sleep(2)
        await WeixinGzhPlatform._click_dialog_primary(page, "继续发表", timeout_s=15)
        logger.info("[阶段②] 已点击「继续发表」,等待跳转首页...")

        # 4. 二次确认后公众号会弹扫码确认(管理员微信扫码),扫码通过后页面才跳转。
        #    这里只等页面跳转到首页/成功页,不点任何按钮 —— 扫码是用户线下动作。
        #    给 10 分钟供用户扫码。
        await WeixinGzhPlatform._wait_for_home(page, timeout_s=600)

    @staticmethod
    async def _publish_scheduled(page, publish_dt):
        """定时发表。

        DOM(文档):
          发表按钮点开后弹窗,内有定时开关 ``.mass-send__timer-wrp .weui-desktop-switch``
          日期下拉 ``.weui-desktop-form__dropdown``,时间选择 ``.weui-desktop-picker__time``
          发表: ``.weui-desktop-btn_primary``(弹窗内「发表」,在 .mass-send__footer)

        **重要(实测)**: 发表弹窗里有两个开关:
          - 群发通知开关(.mass-send__td 下的 .mass-send__timer-wrp):常 disabled
            (今天没有通知次数),不要碰它;
          - 定时发表开关(.mass-send__td-setting 下的 .mass-send__timer-wrp):
            这个是要点的,点开后展开日期/时间选择。
        两个开关都常驻 ``weui-desktop-switch_loading`` 类(weui 组件固定样式,
        不是"加载中"含义)。**不需要扫码确认** —— 之前误判成扫码是错的。

        约束(文档): 系统设置的发布日期只能选最近 7 天(含当天),
        且时间必须 > 当前时间至少 1 小时。
        """
        # 1. 点「发表」打开弹窗
        send_btn = page.locator("#js_send .mass_send").first
        await send_btn.wait_for(state="visible", timeout=15000)
        await send_btn.click()
        logger.info("[阶段②] 已点击「发表」,等待定时弹窗...")
        await asyncio.sleep(2)

        # 2. 开启「定时发表」开关
        #    弹窗里有两个开关:群发通知(input 带 disabled)、定时发表(可用)。
        #    取「input 未 disabled 且当前未勾选」的开关点击。
        #    **关键(实测根因)**: 点完必须校验 input.checked===true 且时间选择器
        #    dl 不再 display:none —— 否则后续选时分全无效(dl 隐藏,点不到)。
        #    之前只 return 'ok' 不校验,导致开关没真开就往下走。
        #
        # **校验判据修正(实测根因)**: 必须同时满足 ① 定时开关 checked ② 时间选择器
        # dl 真实存在(dlExists=true)。之前 dlExists=False 时因 dlHidden 也为 false
        # 被误判通过 —— dl 不存在不等于"可见",必须 dlExists 强制为真。
        switched = False
        sw_deadline = asyncio.get_event_loop().time() + 20
        attempt = 0
        while asyncio.get_event_loop().time() < sw_deadline:
            res = await page.evaluate(
                """() => {
                    // 只取「定时发表」开关 —— 它在 .mass-send__td-setting.timer_setting 区块下。
                    // **绝不能**用 .mass-send__td-setting 作选择器 —— 「分组通知」开关也在
                    // .mass-send__td-setting(group_setting)下,两者结构一样,只有第二个 class 不同:
                    //   分组通知: .mass-send__td-setting.group_setting
                    //   定时发表: .mass-send__td-setting.timer_setting
                    // 之前用 .mass-send__td-setting 选到了第一个(分组通知)并误开它。
                    const wraps = document.querySelectorAll(
                        '.mass-send__td-setting.timer_setting .mass-send__timer-wrp .weui-desktop-switch'
                    );
                    const out = {clicked: false, checked: false, reason: 'none', count: wraps.length};
                    for (const sw of wraps) {
                        const input = sw.querySelector('input.weui-desktop-switch__input');
                        if (!input) continue;
                        if (input.disabled) { out.reason = 'disabled'; continue; }
                        if (input.checked) { out.checked = true; out.reason = 'already-on'; continue; }
                        sw.click();
                        out.clicked = true;
                        out.reason = 'clicked';
                        break;
                    }
                    return out;
                }"""
            )
            await asyncio.sleep(0.8)
            # 校验: 定时开关 checked 且 时间选择器 dl 真实存在且可见
            verify = await page.evaluate(
                """() => {
                    // 与点击逻辑一致:只看「定时发表」开关(.timer_setting),不看「分组通知」(.group_setting)
                    const wraps = document.querySelectorAll(
                        '.mass-send__td-setting.timer_setting .mass-send__timer-wrp .weui-desktop-switch'
                    );
                    let on = false;
                    for (const sw of wraps) {
                        const input = sw.querySelector('input.weui-desktop-switch__input');
                        if (input && !input.disabled && input.checked) { on = true; break; }
                    }
                    const dl = document.querySelector('dl.weui-desktop-picker__time');
                    let dlVisible = false;
                    if (dl) {
                        const styleAttr = dl.getAttribute('style') || '';
                        const computed = window.getComputedStyle(dl).display;
                        const inlineHidden = styleAttr.replace(' ', '').indexOf('display:none') !== -1;
                        dlVisible = !inlineHidden && computed !== 'none';
                    }
                    return {on, dlExists: !!dl, dlVisible};
                }"""
            )
            logger.info(
                "[阶段②][开关] 第%d次 res=%s verify=%s", attempt, res, verify
            )
            # 必须开关已开 + 时间选择器真实存在且可见(dlVisible) 才算成功
            if verify.get("on") and verify.get("dlVisible"):
                switched = True
                break
            attempt += 1
        if switched:
            logger.info("[阶段②] 已开启「定时发表」开关(校验通过: dl 已存在且可见)")
        else:
            logger.error(
                "[阶段②] 定时开关校验失败:开关未开或时间选择器未出现 verify=%s", verify
            )
        await asyncio.sleep(1.0)

        # 3. 选择日期(最近 7 天的下拉,按目标日期匹配)
        target_date_label = WeixinGzhPlatform._resolve_date_label(publish_dt)
        await WeixinGzhPlatform._select_schedule_date(page, target_date_label)

        # 4. 选择时间(时/分滚轮)
        target_hour = publish_dt.strftime("%H")
        target_minute = publish_dt.strftime("%M")
        await WeixinGzhPlatform._select_schedule_time(page, target_hour, target_minute)

        # 5. 点弹窗内「发表」(.mass-send__footer 内 primary)
        await WeixinGzhPlatform._click_dialog_primary(page, "发表", timeout_s=15)
        logger.info("[阶段②] 已点击定时「发表」,等待确认...")

        # 6. 二次确认「继续发表」(若有)
        await asyncio.sleep(2)
        await WeixinGzhPlatform._click_dialog_primary(page, "继续发表", timeout_s=15)
        logger.info("[阶段②] 已点击「继续发表」,等待定时发布提交...")
        # 二次确认后公众号会弹扫码确认(管理员微信扫码),扫码通过后页面才跳转。
        # 这里只等页面跳转到首页/成功页,不点任何按钮 —— 扫码是用户线下动作。
        await WeixinGzhPlatform._wait_for_home(page, timeout_s=600)

    @staticmethod
    def _resolve_date_label(publish_dt):
        """把目标日期映射到公众号下拉的文案(今天/明天/M月D日)。

        公众号下拉只提供最近 7 天的选项,文案为「今天」「明天」或「M月D日」。
        """
        from datetime import date
        today = date.today()
        target = publish_dt.date()
        delta = (target - today).days
        if delta == 0:
            return "今天"
        if delta == 1:
            return "明天"
        return f"{target.month}月{target.day}日"

    @staticmethod
    async def _select_schedule_date(page, date_label: str):
        """选择定时日期:点开日期下拉,匹配文案。"""
        # 点日期下拉 trigger
        dropdown = page.locator(".mass-send__timer .weui-desktop-form__dropdown").first
        try:
            await dropdown.wait_for(state="visible", timeout=5000)
            await dropdown.click()
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.warning("[阶段②] 未找到日期下拉: %s", e)
            return
        # 点匹配的选项
        matched = await page.evaluate(
            """(label) => {
                const items = document.querySelectorAll(
                    '.weui-desktop-dropdown__list-ele .weui-desktop-dropdown__list-ele__text'
                );
                for (const it of items) {
                    if ((it.textContent || '').trim() === label) {
                        it.closest('.weui-desktop-dropdown__list-ele').click();
                        return true;
                    }
                }
                return false;
            }""",
            date_label,
        )
        if matched:
            logger.info("[阶段②] 已选择定时日期: %s", date_label)
        else:
            logger.warning("[阶段②] 未找到定时日期选项「%s」", date_label)
        await asyncio.sleep(0.5)

    @staticmethod
    def _find_visible_picker_dl_js() -> str:
        """JS 片段: 返回当前可见(非 display:none)的那个 ``dl.weui-desktop-picker__time``。

        页面上常驻两个该选择器 dl(实测 input_count=2):
          - 一个 ``style="display: none"`` 的废弃/模板 dl;
          - 一个真正可见、要操作的 dl(开关打开后才渲染)。
        旧代码用 ``querySelector`` 永远取到第一个(恰好是隐藏的),导致时分一直点不到。
        这里遍历全部 dl,挑出 ``getComputedStyle().display !== 'none'`` 的那个返回,
        返回 DOM 元素引用(供后续 JS 复用)。
        """
        return (
            "() => {"
            "  const dls = Array.from(document.querySelectorAll('dl.weui-desktop-picker__time'));"
            "  const vis = dls.filter(d => window.getComputedStyle(d).display !== 'none');"
            "  return vis.length ? vis[0] : (dls.length ? dls[0] : null);"
            "}"
        )

    @staticmethod
    async def _select_schedule_time(page, hour: str, minute: str):
        """选择定时时间:展开时分面板 → 选时/分 → 点外部关闭。

        交互(用户实测确认):
          1. 点击时间选择器 ``<dl.weui-desktop-picker__time>`` 的触发区(dt 内的
             input「请选择时间」/dt 本身) → dl 获得 ``weui-desktop-picker__focus``,
             下方原本隐藏的 ``dd`` 时分面板随之显示出来;
          2. 在 hour 列表(``ol.weui-desktop-picker__time__hour``)点目标小时 li,
             在 minute 列表(``ol.weui-desktop-picker__time__minute``)点目标分钟 li;
             li 文本为纯数字('00'..'23'/'00'..'59'),禁用项带
             ``weui-desktop-picker__disabled``,选中项带 ``weui-desktop-picker__selected``;
          3. 点击组件外页面其他位置 → 关闭面板,时分选择生效。

        **关键坑(定时时间一直选不上的真正根因)**:
          页面上常驻 **两个** ``dl.weui-desktop-picker__time``(实测 input_count=2):
          一个 ``display:none`` 的废弃 dl,一个可见、要操作的 dl。
          旧代码/Playwright ``querySelector``/``locator(...).first`` 永远取到第一个
          (恰好是隐藏的),所以触发区点击 ``scroll_into_view_if_needed`` 必然超时、
          时分 li 也根本点不到。本方法所有 DOM 操作都基于「**可见的那个 dl**」:
          先用 JS 遍历挑出可见 dl,再在它内部点触发区/选时分。
        """
        hour = str(hour).zfill(2)
        minute = str(minute).zfill(2)
        logger.info("[阶段②][时间] 进入 _select_schedule_time, 目标 %s:%s", hour, minute)

        # 0. 探测页面 dl/input 现状 —— 关键: 遍历所有 dl, 区分可见/隐藏, 找出目标 dl。
        probe = await page.evaluate(
            """() => {
                const dls = Array.from(document.querySelectorAll('dl.weui-desktop-picker__time'));
                const inputs = Array.from(document.querySelectorAll('input[placeholder="请选择时间"]'));
                const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect();
                    return {x:Math.round(b.x), y:Math.round(b.y), w:Math.round(b.width), h:Math.round(b.height),
                            visible: b.width>0 && b.height>0,
                            style: el.getAttribute('style') || '',
                            display: window.getComputedStyle(el).display}; };
                return {
                    dl_total: dls.length,
                    dl_visible_count: dls.filter(d => window.getComputedStyle(d).display !== 'none').length,
                    dls: dls.map((d,i)=>({i, focus: d.classList.contains('weui-desktop-picker__focus'), box:r(d)})),
                    input_total: inputs.length,
                    input_visible_count: inputs.filter(inp => window.getComputedStyle(inp).display !== 'none').length,
                    inputs: inputs.map((inp,i)=>({i, box:r(inp)})),
                };
            }"""
        )
        logger.info("[阶段②][时间] DOM 探测: %s", probe)

        # 1. 点击触发区展开面板 —— 全部基于「可见 dl」内部元素。
        #    展开的权威信号: 可见 dl 出现 weui-desktop-picker__focus。
        #    候选触发点(都在目标 dl 内部): input → dt → 时钟图标 → dl 本身。
        #    用一段 JS 同时完成「找可见 dl + 点指定候选」,避开 Playwright
        #    locator.first 永远命中隐藏 dl 的问题。
        FIND_DL = WeixinGzhPlatform._find_visible_picker_dl_js()

        async def _is_focused():
            """返回可见 dl 当前是否带 __focus。"""
            return await page.evaluate(
                "() => {"
                " const dl = (" + FIND_DL + ")();"
                " return !!(dl && dl.classList.contains('weui-desktop-picker__focus'));"
                "}"
            )

        # innerSel 候选: '' 表示点 dl 本身; 否则在 dl 内 querySelector
        candidates = [
            ("input", "input[placeholder='请选择时间']"),
            ("dt",    "dt.weui-desktop-picker__dt"),
            ("icon",  ".weui-desktop-icon__time"),
            ("dl-self", ""),
        ]

        opened = False
        op_deadline = asyncio.get_event_loop().time() + 10
        attempt = 0
        while asyncio.get_event_loop().time() < op_deadline:
            before = await _is_focused()
            if before:
                opened = True
                break
            name, inner_sel = candidates[attempt % len(candidates)]
            clicked = await page.evaluate(
                """(innerSel) => {
                    const dl = (""" + FIND_DL + """)();
                    if (!dl) return {ok:false, reason:'no-visible-dl'};
                    const target = innerSel === '' ? dl : dl.querySelector(innerSel);
                    if (!target) return {ok:false, reason:'no-target', innerSel};
                    const b = target.getBoundingClientRect();
                    if (b.width === 0 && b.height === 0) return {ok:false, reason:'target-not-visible', box:{w:b.width,h:b.height}};
                    target.click();
                    return {ok:true, box:{x:Math.round(b.x),y:Math.round(b.y),w:Math.round(b.width),h:Math.round(b.height)}};
                }""",
                inner_sel,
            )
            await asyncio.sleep(0.6)
            after = await _is_focused()
            logger.info(
                "[阶段②][时间] 第%d次 点可见dl内「%s」 result=%s focus:%s->%s",
                attempt, name, clicked, before, after,
            )
            if after:
                opened = True
                break
            attempt += 1
            await asyncio.sleep(0.3)
        if not opened:
            final_probe = await page.evaluate(
                """() => {
                    const dls = Array.from(document.querySelectorAll('dl.weui-desktop-picker__time'));
                    return dls.map((d,i)=>({i, focus:d.classList.contains('weui-desktop-picker__focus'),
                        display: window.getComputedStyle(d).display,
                        style: d.getAttribute('style') || '',
                        head: d.outerHTML.slice(0,160)}));
                }"""
            )
            logger.warning(
                "[阶段②][时间] 时分选择面板未展开(__focus 未出现),放弃选择时间. 全部 dl: %s",
                final_probe,
            )
            return
        logger.info("[阶段②][时间] 时分选择面板已展开(尝试 %d 次)", attempt + 1)

        # 2. 选小时(在可见 dl 内部,跳过禁用项,文本 trim 后匹配;校验是否真选中)
        logger.info("[阶段②][时间] 开始选小时 %s", hour)
        h_ok = await WeixinGzhPlatform._click_time_wheel_item(
            page, "hour", hour
        )
        logger.info("[阶段②][时间] 选小时 %s: %s", hour, "成功" if h_ok else "未找到")

        # 3. 选分钟
        logger.info("[阶段②][时间] 开始选分钟 %s", minute)
        m_ok = await WeixinGzhPlatform._click_time_wheel_item(
            page, "minute", minute
        )
        logger.info("[阶段②][时间] 选分钟 %s: %s", minute, "成功" if m_ok else "未找到")
        await asyncio.sleep(0.5)

        # 4. 点击组件外部 → 关闭面板,选择生效
        try:
            await page.mouse.click(10, 10)
            await asyncio.sleep(0.5)
            still_open = await _is_focused()
            if still_open:
                logger.info("[阶段②][时间] 点(10,10)未关闭面板,补按 Escape")
                await page.keyboard.press("Escape")
                await asyncio.sleep(0.3)
        except Exception as e:
            logger.warning("[阶段②][时间] 关闭面板异常: %s, 尝试 Escape", str(e)[:100])
            try:
                await page.keyboard.press("Escape")
            except Exception:
                pass

        # 5. 校验 可见 dl 内 input 显示值是否真的变成 HH:MM(选择生效铁证)
        final_value = await page.evaluate(
            "() => {"
            " const dl = (" + FIND_DL + ")();"
            " if (!dl) return {value: null, reason: 'no-visible-dl'};"
            " const inp = dl.querySelector('input[placeholder=\"请选择时间\"]');"
            " return {value: inp ? (inp.value || '') : null};"
            "}"
        )
        logger.info(
            "[阶段②][时间] 完成设置, 目标 %s:%s, 可见dl input 实际值=%r",
            hour, minute, final_value,
        )

    @staticmethod
    def _wheel_items_js_body(kind: str) -> str:
        """生成 JS 片段(不带外层函数): 取「可见 dl」内 hour/minute 滚轮的所有 li。

        kind 为 'hour' 或 'minute',对应 ol.weui-desktop-picker__time__hour / __minute。
        关键: 只在「可见 dl」内查 ol,避免命中页面里另一个 display:none 的废弃 dl。
        """
        suffix = "hour" if kind == "hour" else "minute"
        return (
            "const dl = (" + WeixinGzhPlatform._find_visible_picker_dl_js() + ")();"
            " const items = dl ? dl.querySelectorAll('.weui-desktop-picker__time__" + suffix + " li') : [];"
        )

    @staticmethod
    async def _click_time_wheel_item(page, kind: str, value: str) -> bool:
        """点击时分滚轮里目标值的 li(在可见 dl 内部),并校验是否真的选中。

        kind: 'hour' 或 'minute'。
        - 先用 JS ``li.click()`` 选值(同步、便于处理带空白的文本);
        - 点击后检查该 li 是否获得 ``weui-desktop-picker__selected``;
        - 若 JS click 未生效,改用真实鼠标点击该 li 的中心坐标再校验一次。
        """
        body = WeixinGzhPlatform._wheel_items_js_body(kind)

        # 先探测滚轮里 li 数量、目标值是否存在、是否被禁用
        info = await page.evaluate(
            "(val) => { " + body +
            " let total=items.length, disabled=0, found=false, found_disabled=false;"
            " for (const li of items) {"
            "  if (li.classList.contains('weui-desktop-picker__disabled')) { disabled++; if ((li.textContent||'').trim()===val) found_disabled=true; continue; }"
            "  if ((li.textContent||'').trim()===val) found=true;"
            " }"
            " return {total, disabled, found, found_disabled}; }",
            value,
        )
        logger.info("[阶段②][时间] %s 目标值 %s 探测: %s", kind, value, info)
        if not info or not info.get("found"):
            return False

        # 尝试 1: JS 直接 click 匹配的 li
        await page.evaluate(
            "(val) => { " + body +
            " for (const li of items) {"
            "  if (li.classList.contains('weui-desktop-picker__disabled')) continue;"
            "  if ((li.textContent||'').trim()===val) { li.click(); }"
            " } }",
            value,
        )
        await asyncio.sleep(0.3)
        sel1 = await WeixinGzhPlatform._is_wheel_item_selected(page, kind, value)
        logger.info("[阶段②][时间] %s JS click 后 selected=%s", kind, sel1)
        if sel1:
            return True

        # 尝试 2: 真实鼠标点击该 li 的中心坐标(仅在面板展开、li 可见时有效)
        center = await page.evaluate(
            "(val) => { " + body +
            " for (const li of items) {"
            "  if (li.classList.contains('weui-desktop-picker__disabled')) continue;"
            "  if ((li.textContent||'').trim()!==val) continue;"
            "  const r = li.getBoundingClientRect();"
            "  if (r.width===0 && r.height===0) return null;"
            "  return {x: r.left + r.width/2, y: r.top + r.height/2};"
            " } return null; }",
            value,
        )
        if center:
            logger.info("[阶段②][时间] %s 鼠标兜底点击坐标 %s", kind, center)
            try:
                await page.mouse.click(center["x"], center["y"])
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.warning("[阶段②][时间] %s 鼠标点击异常: %s", kind, str(e)[:100])
        else:
            logger.warning("[阶段②][时间] %s 无法取到 li 中心坐标(可能未展开)", kind)
        sel2 = await WeixinGzhPlatform._is_wheel_item_selected(page, kind, value)
        logger.info("[阶段②][时间] %s 鼠标 click 后 selected=%s", kind, sel2)
        return sel2

    @staticmethod
    async def _is_wheel_item_selected(page, kind: str, value: str) -> bool:
        """检查目标值的 li(在可见 dl 内部)是否已获得 ``weui-desktop-picker__selected``。"""
        body = WeixinGzhPlatform._wheel_items_js_body(kind)
        return await page.evaluate(
            "(val) => { " + body +
            " for (const li of items) {"
            "  if ((li.textContent||'').trim()===val) {"
            "   return li.classList.contains('weui-desktop-picker__selected');"
            "  }"
            " } return false; }",
            value,
        )

    @staticmethod
    async def _wait_for_home(page, timeout_s: int = 120):
        """等待发表成功的信号。

        成功信号有两种：
        1. URL 跳转到首页(/cgi-bin/home + token=) —— 正常路径，扫码后跳转;
        2. 弹出「已发送操作申请」对话框(用户消息:等待管理员验证后发表，
           30 分钟后过期) —— 部分公众号开了「管理员扫码验证」策略，
           点完「继续发表」后会停在这种弹窗，不会跳转首页，
           但申请已提交，应视为成功。点「我知道了」关闭即可。

        DOM: ``.page_msg`` 内 ``h4`` 文案为「已发送操作申请」,
        对话框 footer 有「我知道了」按钮 ``.btn.btn_default``。
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            try:
                url = page.url or ""
                if _HOME_PATH in url and "token=" in url:
                    logger.info("[阶段②] 已跳转首页,发表成功")
                    return
                # 「已发送操作申请」弹窗（管理员验证策略）
                page_msg = page.locator(".page_msg")
                if await page_msg.count() > 0:
                    h4 = page_msg.locator("h4").first
                    if await h4.count() > 0:
                        h4_text = (await h4.text_content() or "").strip()
                        if "已发送操作申请" in h4_text:
                            # 点「我知道了」关掉对话框（申请已提交）
                            know_btn = page.locator(
                                ".dialog .btn.btn_default", has_text="我知道了"
                            ).first
                            try:
                                if await know_btn.count() > 0:
                                    await know_btn.click()
                            except Exception:
                                pass
                            logger.info(
                                "[阶段②] 检测到「已发送操作申请」弹窗(管理员验证策略)，申请已提交，视为发表成功"
                            )
                            return
            except Exception:
                pass
            await asyncio.sleep(2)
        logger.warning("[阶段②] %ds 内未检测到成功信号(发表可能仍在处理)", timeout_s)

    # ==================================================================
    # publish_image — 图集(贴图)发布
    # ==================================================================

    # 贴图菜单:创作中心首页的「贴图」入口。
    # DOM(用户文档): ``.new-creation__menu-item`` 内文字含「贴图」。
    _IMAGE_MENU_TEXT = "贴图"
    # 图集标题/描述上限(与视频不同:视频 64/300, 图集 20/1000)
    _IMAGE_TITLE_MAX = 20
    _IMAGE_DESC_MAX = 1000

    def publish_image(self, **kwargs) -> bool:
        """发布图集(贴图)到公众号(同步入口)。

        流程: 创作中心首页点「贴图」→ 新 tab(appmsg_edit_v2 type=77)
        → 上传多图 → 复用 video 的标题/描述/合集/创作来源/发表 helpers。

        入口仅做 dry-run 早返回 + 调 _upload_all_images。
        """
        dry_run = kwargs.get("dry_run", False)
        if dry_run:
            logger.info("[发布图集] dry-run 模式, 跳过实际发布 (publish_image)")
            return True
        asyncio.run(self._upload_all_images(**kwargs))
        return True

    async def _upload_all_images(self, **kwargs):
        """图集编排:**单层账号循环**(一账号一次发完所有图),非笛卡尔积。"""
        logger.info("=" * 60)
        logger.info("[发布图集] 开始微信公众号图集发布流程")
        logger.info("=" * 60)

        logger.info("[发布参数] 接收到的所有参数:")
        for key, value in kwargs.items():
            logger.info("[发布参数]   %s = %s (类型: %s)", key, value, type(value).__name__)

        files = kwargs.get("files", []) or []
        account_file = kwargs.get("account_file", []) or []
        title = kwargs.get("title", "")
        tags = kwargs.get("tags", []) or []
        desc = kwargs.get("desc", "") or ""
        is_original = kwargs.get("is_original", False)
        gzh_collection_name = kwargs.get("gzh_collection_name", "") or ""
        gzh_claim_source = kwargs.get("gzh_claim_source", "") or ""
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")

        # 忽略字段(公众号图集不支持)
        _ = kwargs.get("cover_path")  # noqa
        _ = kwargs.get("music_name")  # noqa
        _ = kwargs.get("ai_content")  # noqa

        logger.info("[发布参数] 标题: %s", title)
        logger.info("[发布参数] 图片数量: %d", len(files))
        logger.info("[发布参数] 标签: %s", tags)
        logger.info("[发布参数] 描述: %s", desc[:50] if desc else "无")
        logger.info("[发布参数] 账号数量: %d", len(account_file))
        logger.info("[发布参数] 原创: %s", is_original)
        logger.info("[发布参数] 合集: %s", gzh_collection_name or "无")
        logger.info("[发布参数] 创作来源: %s", gzh_claim_source or "无")

        file_path_list = [str(f) for f in files]
        account_paths = [str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file]

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
                    is_original=is_original,
                    gzh_collection_name=gzh_collection_name,
                    gzh_claim_source=gzh_claim_source,
                    enable_timer=enable_timer,
                    schedule_time_str=schedule_time_str,
                )

        logger.info("=" * 60)
        logger.info("[发布图集] 图集发布流程完成!")
        logger.info("=" * 60)

    async def _upload_one_image(
        self,
        title: str,
        file_path_list: list,
        tags: list,
        account_file: str,
        desc: str = "",
        is_original: bool = False,
        gzh_collection_name: str = "",
        gzh_claim_source: str = "",
        enable_timer: bool = False,
        schedule_time_str: str = "",
    ):
        """单账号图集发布完整流程。

        与 video 的区别:图集只有一阶段 —— 创作中心首页点「贴图」直接进
        appmsg_edit_v2(type=77)编辑页,在该页上传图片 + 填写 + 发表。
        video 的素材上传页(videomsg_edit)→保存并发表→新 tab 两阶段,
        图集直接进编辑页,更简单。

        复用 video 的阶段②helpers(标题/描述/合集/创作来源/发表/定时)。
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

                # 1. 解析 token + 进创作中心首页
                token = await self._resolve_token(page)
                if not token:
                    raise RuntimeError("[发布图集] 未能获取 token,cookie 可能已失效")
                logger.info("[发布图集] 获取到 token: %s", token)
                home_url = self._build_home_url(token)
                logger.info("[发布图集] 打开创作中心首页: %s", home_url)
                await page.goto(home_url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(3)

                # 2. 点击「贴图」菜单 → 捕获新 tab
                page2 = await self._click_image_menu(page, context)
                logger.info("[发布图集] 贴图编辑页已打开: %s", page2.url)
                await page2.wait_for_load_state("domcontentloaded", timeout=30000)
                await asyncio.sleep(2)

                # 3. 上传多图
                logger.info("[发布图集] 开始上传 %d 张图片...", len(file_path_list))
                await self._upload_images(page2, file_path_list)
                logger.info("[发布图集] 图片上传完成!")

                # 4. 标题(图集≤20字)
                logger.info("[发布图集] 填写标题: %s", title)
                await self._fill_publish_title(page2, title, max_len=self._IMAGE_TITLE_MAX)

                # 5. 描述(图集≤1000字)
                logger.info("[发布图集] 填写描述/标签...")
                await self._fill_description(
                    page2, desc, title, tags, max_len=self._IMAGE_DESC_MAX,
                )

                # 6. 合集(可选)
                if gzh_collection_name:
                    logger.info("[发布图集] 选择合集: %s", gzh_collection_name)
                    await self._set_collection(page2, gzh_collection_name)
                else:
                    logger.info("[发布图集] 未选择合集,跳过")

                # 7. 创作来源(可选)
                if gzh_claim_source:
                    logger.info("[发布图集] 设置创作来源: %s", gzh_claim_source)
                    await self._set_claim_source(page2, gzh_claim_source)
                else:
                    logger.info("[发布图集] 未设置创作来源,跳过")

                # 8. 发表(立即/定时,与视频完全一致) — Dry-run 模式同视频
                if _DRY_RUN_PUBLISH:
                    logger.info("[发布图集] 🐛 DRY_RUN=1 跳过点击发布,浏览器保持打开供人工核对")
                    try:
                        await page2.screenshot(
                            path=str(log_dir / "weixin_gzh_image_dry_run.png"),
                            full_page=True,
                        )
                    except Exception:
                        pass
                    try:
                        await page2.wait_for_event("close", timeout=0)
                    except Exception:
                        pass
                else:
                    if enable_timer and schedule_time_str:
                        publish_dt = self._build_publish_datetime(schedule_time_str, 1)
                        if publish_dt and not (isinstance(publish_dt, int) and publish_dt == 0):
                            logger.info("[发布图集] 定时发布: %s", publish_dt)
                            await self._publish_scheduled(page2, publish_dt)
                        else:
                            logger.info("[发布图集] 定时时间解析失败,改为立即发表")
                            await self._publish_immediate(page2)
                    else:
                        logger.info("[发布图集] 立即发表...")
                        await self._publish_immediate(page2)

                logger.info("[发布图集] 图集发布成功!")

                # 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[发布图集] Cookie 状态已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await self.close_browser(browser, is_close_by_code=True)

    async def _click_image_menu(self, page, context):
        """点击创作中心首页的「贴图」菜单,返回打开的新 tab page。

        DOM(用户文档): ``.new-creation__menu-item`` 内 ``.new-creation__menu-title``
        文字为「贴图」。点击后打开新 tab(appmsg_edit_v2 type=77 createType=8)。
        用 context.on("page") 捕获新 tab,过滤 about:blank。
        """
        new_page_holder = {"page": None}

        def _on_new_page(new_page):
            try:
                url = new_page.url or ""
            except Exception:
                url = ""
            logger.info("[发布图集] 检测到新 tab: %s", url or "(about:blank)")
            if "appmsg_edit" in url:
                new_page_holder["page"] = new_page

        context.on("page", _on_new_page)
        try:
            # 找「贴图」菜单项(用文案定位,避免 svg 路径匹配)
            # 定位含「贴图」文案的菜单标题元素,再点它(或其父级 menu-item)
            menu_title = page.locator(
                ".new-creation__menu-title",
                has_text=self._IMAGE_MENU_TEXT,
            ).first
            await menu_title.wait_for(state="visible", timeout=15000)
            # 点击 menu-title 的父级 menu-item(整个卡片可点)
            menu = menu_title.locator("xpath=ancestor::div[contains(@class,'new-creation__menu-item')][1]")
            await menu.wait_for(state="visible", timeout=15000)
            await menu.click()
            logger.info("[发布图集] 已点击「贴图」菜单,等待新 tab...")

            # 轮询等待目标新 tab 导航到 appmsg_edit
            deadline = asyncio.get_event_loop().time() + 30
            target_page = None
            while asyncio.get_event_loop().time() < deadline:
                if new_page_holder["page"] is not None:
                    target_page = new_page_holder["page"]
                    break
                # 兜底:从 context.pages 找已导航到 appmsg_edit 的 tab
                for p in context.pages:
                    try:
                        if p is page:
                            continue
                        if "appmsg_edit" in (p.url or ""):
                            target_page = p
                            new_page_holder["page"] = p
                            break
                    except Exception:
                        continue
                if target_page is not None:
                    break
                await asyncio.sleep(1)

            if target_page is None:
                raise RuntimeError("[发布图集] 点击「贴图」后未捕获到编辑页新 tab")
            try:
                await target_page.wait_for_url("**/appmsg_edit*", timeout=30000)
            except Exception as e:
                logger.info("[发布图集] 新 tab URL 等待(非致命): %s, 当前: %s", e, target_page.url)
            await target_page.bring_to_front()
            return target_page
        finally:
            context.remove_listener("page", _on_new_page)

    @staticmethod
    async def _upload_images(page, file_path_list: list):
        """上传多张图片(一次性 set_input_files)。

        贴图编辑页(appmsg_edit_v2 type=77)的图片上传 input(DOM 实测):
          ``.js_upload_btn_container input[type='file'][accept*='image']``
          (带 multiple, style display:none 隐藏但 set_input_files 仍可用)

        一次性把所有图片路径传进去,再等待上传完成(轮询图片预览项数量)。
        """
        if not file_path_list:
            logger.warning("[发布图集] 无图片可上传")
            return

        # 找图片上传 input —— 多选择器兜底
        input_selectors = [
            ".js_upload_btn_container input[type='file']",
            "input[type='file'][accept*='image']",
            "input[type='file'][multiple]",
        ]
        img_input = None
        for sel in input_selectors:
            loc = page.locator(sel).first
            try:
                await loc.wait_for(state="attached", timeout=8000)
                img_input = loc
                logger.info("[发布图集] 找到图片上传 input, 选择器: %s", sel)
                break
            except Exception:
                continue
        if img_input is None:
            raise RuntimeError("[发布图集] 未找到图片上传 input")

        await img_input.set_input_files(file_path_list)
        logger.info("[发布图集] 已提交 %d 张图片,等待上传...", len(file_path_list))

        # 等待上传完成:已上传的图片项数量达到预期(轮询,最多 5 分钟)
        # 贴图编辑页每张图会生成一个预览项(li/div 含 img 或上传进度条)
        target_count = len(file_path_list)
        deadline = asyncio.get_event_loop().time() + 300
        last_info = ""
        while asyncio.get_event_loop().time() < deadline:
            info = await page.evaluate(
                """(target) => {
                    // 已上传图片的预览项(公众号贴图页多种可能结构)
                    // 1. 含已上传缩略图的列表项
                    // 2. 上传进度项(上传中)/ 完成项
                    const sels = [
                        '.appmsg_edit_item img',
                        '.js_appmsg_list img',
                        '.weui-desktop-card .appmsg_edit_item',
                        'img[data-src]',
                        '.upload_item',
                    ];
                    let best = 0;
                    for (const sel of sels) {
                        const els = document.querySelectorAll(sel);
                        let visible = 0;
                        for (const el of els) {
                            const r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) visible++;
                        }
                        if (visible > best) best = visible;
                    }
                    // 上传中检测:是否有进度条/上传中文案
                    const uploading = document.querySelectorAll(
                        '.weui-desktop-upload__file__progress, [class*="upload"][class*="progress"]'
                    ).length;
                    return {best, uploading, target};
                }""",
                target_count,
            )
            cur = f"已上传预览={info.get('best', 0)}/目标={target_count} 上传中={info.get('uploading', 0)}"
            if cur != last_info:
                logger.info("[发布图集] 上传进度: %s", cur)
                last_info = cur
            # 完成: 预览数达到目标;或(有预览且无上传中=上传已结束)
            best = info.get("best", 0)
            uploading = info.get("uploading", 0)
            if best >= target_count:
                logger.info("[发布图集] 全部 %d 张图片已上传", target_count)
                return
            if best > 0 and uploading == 0:
                logger.info("[发布图集] 上传已结束(预览 %d 张,目标 %d)", best, target_count)
                return
            await asyncio.sleep(3)
        logger.warning("[发布图集] 图片上传等待超时(可能部分未完成),继续后续操作")
