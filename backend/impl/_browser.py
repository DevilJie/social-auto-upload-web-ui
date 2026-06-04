"""CloakBrowser stealth browser factory.

All browser creation goes through this module.
"""

import os

from conf import LOGIN_HEADLESS, LOCAL_CHROME_HEADLESS
from util._logger import get_channel_logger

logger = get_channel_logger("browser")

# 初始窗口大小（用户可自由缩放，no_viewport=True 让页面跟随）
INITIAL_WINDOW_SIZE = "1920,1080"


def _download_binary():
    """Download CloakBrowser stealth binary, bypassing system SOCKS proxy."""
    saved = {}
    for var in ("all_proxy", "http_proxy", "https_proxy",
                "ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "no_proxy"):
        if var in os.environ:
            saved[var] = os.environ.pop(var)

    from cloakbrowser import ensure_binary
    try:
        ensure_binary()
    finally:
        os.environ.update(saved)


def init():
    """Pre-download CloakBrowser binary at startup."""
    try:
        _download_binary()
        logger.info("CloakBrowser stealth binary ready")
    except Exception as e:
        logger.warning("CloakBrowser unavailable (%s)", e)


async def create_browser(
    headless: bool | None = None,
    login_mode: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
):
    """Create a stealth Chromium browser via CloakBrowser."""
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS

    # CloakBrowser 不支持 socks 代理协议，临时清除 env 中的 socks 配置
    _socks_all = None
    _socks_All = None
    if "all_proxy" in os.environ and "socks" in os.environ["all_proxy"]:
        _socks_all = os.environ.pop("all_proxy")
    if "ALL_PROXY" in os.environ and "socks" in os.environ["ALL_PROXY"]:
        _socks_All = os.environ.pop("ALL_PROXY")

    # 代理仅由各平台自行决定（TikTok/YouTube 从 settings.json 读取），
    # 国内平台不传 proxy，直接连接，不做环境变量 fallback

    from cloakbrowser import launch_async
    try:
        return await launch_async(headless=headless, proxy=proxy, args=extra_args)
    finally:
        if _socks_all:
            os.environ["all_proxy"] = _socks_all
        if _socks_All:
            os.environ["ALL_PROXY"] = _socks_All


async def create_context(
    browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
):
    """Create a browser context with resizable window.

    no_viewport=True 让页面内容跟随窗口大小变化（不像 Playwright
    默认 viewport 写死）。用户拖动/最大化浏览器时页面会 reflow
    适配新尺寸。
    """
    return await browser.new_context(
        storage_state=storage_state,
        user_agent=user_agent,
        no_viewport=True,
    )


async def create_persistent_context(
    user_data_dir: str,
    headless: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
):
    """Create a persistent browser context with a local user data dir.

    no_viewport=True 让窗口内容跟随大小变化；--window-size 给个
    合理初始尺寸（用户可自由缩放）。
    """
    from cloakbrowser import launch_persistent_context_async
    args = list(extra_args or [])
    if not any(a.startswith("--window-size=") for a in args):
        args.append(f"--window-size={INITIAL_WINDOW_SIZE}")
    return await launch_persistent_context_async(
        user_data_dir,
        headless=headless,
        proxy=proxy,
        args=args,
        no_viewport=True,
    )


def create_browser_sync(
    headless: bool = False,
    extra_args: list | None = None,
):
    """Synchronous browser launch (for ``open_creator_center``)."""
    from cloakbrowser import launch
    return launch(headless=headless, args=extra_args)
