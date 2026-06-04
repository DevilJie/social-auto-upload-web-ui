"""CloakBrowser stealth browser factory — unified entry point.

所有打开浏览器的入口都集中在这里。调用方不要直接调 browser.new_context
或 cloakbrowser.launch_*，避免东一套西一套。

所有 context 使用 no_viewport=True，页面内容跟随窗口大小自动 reflow。
"""

import os

from conf import LOGIN_HEADLESS, LOCAL_CHROME_HEADLESS
from util._logger import get_channel_logger

logger = get_channel_logger("browser")


def _download_binary():
    """Download CloakBrowser stealth binary."""
    from cloakbrowser import ensure_binary
    ensure_binary()


def init():
    """Pre-download CloakBrowser binary at startup."""
    try:
        _download_binary()
        logger.info("CloakBrowser stealth binary ready")
    except Exception as e:
        logger.warning("CloakBrowser unavailable (%s)", e)


# ──────────── 异步入口 ────────────

async def create_browser(
    headless: bool | None = None,
    login_mode: bool = False,
):
    """异步入口：创建 stealth Chromium 浏览器。

    不接 proxy / extra_args —— 历史代理配置已废弃。
    """
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS
    from cloakbrowser import launch_async
    return await launch_async(headless=headless)


async def create_context(
    browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
):
    """异步入口：创建 browser context（no_viewport，跟随窗口自适应）。"""
    return await browser.new_context(
        storage_state=storage_state,
        user_agent=user_agent,
        no_viewport=True,
    )


async def create_persistent_context(
    user_data_dir: str,
    headless: bool = False,
):
    """异步入口：登录扫码用持久化 context（no_viewport，跟随窗口自适应）。"""
    from cloakbrowser import launch_persistent_context_async
    return await launch_persistent_context_async(
        user_data_dir,
        headless=headless,
        no_viewport=True,
        args=["--window-size=1920,1080"],
    )


# ──────────── 同步入口 ────────────

def create_browser_sync(headless: bool = False):
    """同步入口：创建 stealth Chromium 浏览器。"""
    from cloakbrowser import launch
    return launch(headless=headless)


def create_context_sync(
    browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
):
    """同步入口：创建 browser context（no_viewport，跟随窗口自适应）。

    平台层不要直接调 browser.new_context()，统一走这个入口。
    """
    return browser.new_context(
        storage_state=storage_state,
        user_agent=user_agent,
        no_viewport=True,
    )
