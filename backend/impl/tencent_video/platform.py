"""
Tencent Video (腾讯视频) platform implementation — CloakBrowser.

Login URL: https://mp.v.qq.com/
Profile page: https://mp.v.qq.com/homepage
Publish URL: https://mp.v.qq.com/publishVideo/video
"""

import asyncio
import json
import logging
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._utils import parse_schedule_time, save_login_result
from ..base_platform import BasePlatform

logger = logging.getLogger(__name__)

_LOGIN_URL = "https://mp.v.qq.com/"
_HOME_URL = "https://mp.v.qq.com/homepage"
_PUBLISH_URL = "https://mp.v.qq.com/publishVideo/video"

# ---------------------------------------------------------------------------
# Creation declaration options (matches the platform checkboxes)
# ---------------------------------------------------------------------------
CREATION_DECLARATIONS = [
    "剧情演绎，仅供娱乐",
    "取材网络，谨慎甄别",
    "个人观点，仅供参考",
    "未成年人请勿学习模仿",
    "内容由AI生成",
]


async def _scrape_tencent_video_profile(page) -> tuple[str, str]:
    """Scrape nickname and avatar from mp.v.qq.com/homepage.

    DOM structure (CSS Module classes with hash suffixes — use partial matches):
      - Avatar:  div[class*="userAvatar"] img  → src
      - Nickname: a[href*="videoplus"][class*="name"]  → text
    """
    name = ""
    avatar = ""

    try:
        # Wait for the user info section to render
        await page.wait_for_selector('div[class*="userInfo"]', timeout=10000)
    except Exception:
        logger.warning("userInfo section not found")

    try:
        name_el = page.locator('a[href*="videoplus"][class*="name"]').first
        if await name_el.count() > 0:
            name = (await name_el.text_content() or "").strip()
    except Exception as e:
        logger.warning("Failed to scrape nickname: %s", e)

    try:
        avatar_el = page.locator('div[class*="userAvatar"] img').first
        if await avatar_el.count() > 0:
            avatar = (await avatar_el.get_attribute("src") or "").strip()
    except Exception as e:
        logger.warning("Failed to scrape avatar: %s", e)

    return name, avatar


class TencentVideoPlatform(BasePlatform):
    platform_id = 9
    platform_key = "tencent_video"
    platform_name = "腾讯视频"

    # ------------------------------------------------------------------
    # login — open browser, wait for user to log in manually
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue) -> None:
        url_changed_event = asyncio.Event()

        async def _on_url_change():
            if "homepage" in page.url:
                url_changed_event.set()

        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                await page.goto(_LOGIN_URL)

                page.on(
                    "framenavigated",
                    lambda frame: asyncio.create_task(_on_url_change())
                    if frame == page.main_frame
                    else None,
                )

                # Wait up to 300s for the user to complete login and land on homepage
                try:
                    await asyncio.wait_for(url_changed_event.wait(), timeout=300)
                    logger.info("Homepage detected — login successful")
                except asyncio.TimeoutError:
                    logger.warning("Login timed out (300 s)")
                    status_queue.put("500")
                    return

                await save_login_result(
                    context,
                    page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=_scrape_tencent_video_profile,
                )
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # check_cookie — verify stored cookie is still valid
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_HOME_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")

                try:
                    await page.wait_for_selector('div[class*="userInfo"]', timeout=5000)
                    return True
                except Exception:
                    return False
            finally:
                await context.close()
        except Exception as e:
            logger.warning("check_cookie failed: %s", e)
            return False
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # sync_profile — scrape user name and avatar
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple[str, str]:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            try:
                page = await context.new_page()
                await page.goto(_HOME_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")
                return await _scrape_tencent_video_profile(page)
            finally:
                await context.close()
        except Exception as e:
            logger.warning("sync_profile failed: %s", e)
            return "", ""
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center — open visible browser with stored cookies
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        browser = await self.create_browser(login_mode=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            await page.goto(_HOME_URL)
            try:
                await page.wait_for_event("close", timeout=0)
            except Exception:
                pass
        finally:
            try:
                await browser.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # publish_video — stub (TODO)
    # ------------------------------------------------------------------

    async def publish_video(self, **kwargs):
        raise NotImplementedError("腾讯视频发布功能尚未实现")
