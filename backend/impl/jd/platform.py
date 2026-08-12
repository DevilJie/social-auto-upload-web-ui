"""京东平台发布实现。

参考 backend/impl/taobao_guanghe/platform.py(架构平行,具体 DOM 不同)。

平台信息:
- platform_id: 20
- platform_key: 'jd'
- platform_name: '京东'
- creator_center: https://dr.jd.com/jm/
- publish_url: https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop
"""

import asyncio
import logging
import os
import sqlite3
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR
from util._logger import get_channel_logger

from .._utils import save_login_result
from ..base_platform import BasePlatform

logger = get_channel_logger("jd")

JD_PUBLISH_URL = "https://dr.jd.com/jm/#/n/publish-video.html?platform=jm-pop"
JD_CREATOR_CENTER_URL = "https://dr.jd.com/jm/"

# Cookie 失效/未登录时会被重定向到这些域
JD_COOKIE_INVALID_MARKERS = (
    "passport.jd.com",
    "passport.shop.jd.com",
)

# 视为已登录的域名
JD_HOME_HOST = "dr.jd.com"

JD_DRY_RUN = os.environ.get("JD_DRY_RUN", "").lower() in ("1", "true", "yes")


def _resolve_cookie_filename(account_id: str | None) -> str | None:
    """根据 user_info.id 取 cookiesFile 路径(参考 jingmai/picker.py 的实现)。"""
    if not account_id:
        return None
    db_path = Path(BASE_DIR / "db" / "database.db")
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute(
                "SELECT filePath FROM user_info WHERE id = ?", (account_id,)
            ).fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning("查询 cookie 文件名失败 (account_id=%s): %s", account_id, e)
        return None


def _resolve_cookie_path(cookie_filename: str | None) -> Path | None:
    """把 cookiesFile 名字解析为绝对路径,文件不存在返回 None。"""
    if not cookie_filename:
        return None
    p = Path(BASE_DIR / "cookiesFile") / cookie_filename
    return p if p.exists() else None


class JdPlatform(BasePlatform):
    """京东平台发布实现。

    当前 Task 10 只交付基础类结构 + login。其余抽象方法(check_cookie /
    open_creator_center / sync_profile / publish_video)在后续 Task 11-17 实现,
    本类先以 NotImplementedError 占位,保证 class 可实例化、registry 可注册。
    """

    platform_id = 20
    platform_key = "jd"
    platform_name = "京东"

    def __init__(self):
        self.browser = None
        self.page = None

    # ---------- 抽象方法:登录 ----------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """打开京东创作中心,等待用户扫码/手动登录后保存 cookie。

        Args:
            id: 账号唯一标识(同 account_id)
            status_queue: 进度队列
            account_id: 数据库账号 ID(可选)
        """
        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(JD_CREATOR_CENTER_URL)
                logger.info("[jd][登录] 等待用户完成登录(检测 URL 跳回创作中心)")

                # 轮询:URL 离开登录域、回到创作中心 = 登录成功。
                while True:
                    await asyncio.sleep(2)
                    current_url = page.url or ""
                    if JD_HOME_HOST in current_url and not any(
                        m in current_url for m in JD_COOKIE_INVALID_MARKERS
                    ):
                        # 二次确认仍在创作中心(排除中间态跳转)
                        await asyncio.sleep(3)
                        if JD_HOME_HOST in (page.url or ""):
                            logger.info("[jd][登录] URL 已回到创作中心,登录成功")
                            break

                # 登录后后台还在做 token 交换/重定向,登录态 cookie 可能尚未完全建立。
                # 主动重新导航首页,确保关键 cookie 已写入,供 storage_state 保存完整。
                logger.info("[jd][登录] 等待首页稳定(确保登录态完整)")
                try:
                    await page.goto(
                        JD_CREATOR_CENTER_URL, wait_until="domcontentloaded", timeout=30000
                    )
                except Exception as e:
                    logger.info(f"[jd][登录] 首页导航超时(忽略): {e}")
                await asyncio.sleep(2)

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=_scrape_jd_profile,
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

    # ---------- 占位:后续 Task 实现 ----------

    async def check_cookie(self, cookie_file: str) -> bool:
        """检测 cookie 是否有效。

        策略:用 cookie 打开创作中心,如果被重定向到 passport.* → 无效。
        """
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            return False

        browser = await self.create_browser(headless=True)
        try:
            ctx = await self.create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            try:
                await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
                await asyncio.sleep(2)
                url = page.url or ""
                for invalid_host in JD_COOKIE_INVALID_MARKERS:
                    if invalid_host in url:
                        logger.warning(f"京东 cookie 失效: 当前 URL {url}")
                        return False
                return True
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await ctx.close()
                except Exception:
                    pass
        finally:
            await browser.close()

    async def sync_profile(self, cookie_file: str):
        """同步账号昵称/头像。

        Returns:
            {"name": str, "avatar": str} 或 None(失败时)
        """
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            return None

        browser = await self.create_browser(headless=True)
        try:
            ctx = await self.create_context(browser, storage_state=str(cookie_path))
            page = await ctx.new_page()
            try:
                await page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
                await asyncio.sleep(3)

                # 复用 jd 专用 scraper(顶栏 BEM class,无哈希)
                name, avatar = await _scrape_jd_profile(page)

                if name:
                    return {"name": name, "avatar": avatar}
                return None
            except Exception as e:
                logger.warning(f"sync_profile 失败: {e}")
                return None
            finally:
                try:
                    await page.close()
                except Exception:
                    pass
                try:
                    await ctx.close()
                except Exception:
                    pass
        finally:
            await browser.close()

    async def open_creator_center(self, cookie_file: str) -> None:
        """异步入口:打开创作中心(后台线程保持浏览器)。"""
        cookie_path = Path(BASE_DIR / "cookiesFile" / cookie_file)
        if not cookie_path.exists():
            raise FileNotFoundError(f"cookie 文件不存在: {cookie_file}")

        def _launch():
            from .._browser import create_browser_sync, create_context_sync
            browser = create_browser_sync(headless=False)
            try:
                ctx = create_context_sync(browser, storage_state=str(cookie_path))
                page = ctx.new_page()
                page.goto(JD_CREATOR_CENTER_URL, wait_until="domcontentloaded")
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

    def publish_video(self, **kwargs) -> bool:
        """视频发布(TODO: Task 12-17 实现)。"""
        raise NotImplementedError("京东平台暂未实现 publish_video")


# ---------- profile scraper ----------


async def _scrape_jd_profile(page) -> tuple[str, str]:
    """京东专用 profile 抓取器(顶栏头像/昵称,无哈希 BEM class)。

    DOM 与京东京麦相同 — 复用同一组 class(``shop-menu-account__right-avatar``、
    ``shop-menu-accountV1__right-account-top-name``)。如果未来两者视觉层不同,
    再拆出独立 scraper。

    Returns:
        tuple[name, avatar]
    """
    name, avatar = "", ""
    try:
        await asyncio.sleep(2)

        try:
            avatar_el = page.locator(".shop-menu-account__right-avatar").first
            if await avatar_el.count() > 0:
                avatar = (await avatar_el.get_attribute("src") or "").strip()
                if avatar.startswith("//"):
                    avatar = "https:" + avatar
        except Exception as e:
            logger.info(f"[jd] 头像抓取失败: {e}")

        try:
            name_el = page.locator(
                ".shop-menu-accountV1__right-account-top-name"
            ).first
            if await name_el.count() > 0:
                name = (await name_el.get_attribute("title") or "").strip()
                if not name:
                    name = (await name_el.text_content() or "").strip()
        except Exception as e:
            logger.info(f"[jd] 昵称抓取失败: {e}")

        logger.info(
            f"[jd] profile scraped - name={name!r} avatar={avatar[:80] if avatar else 'None'}"
        )
    except Exception as e:
        logger.info(f"[jd] profile scrape error: {e}")

    return name, avatar