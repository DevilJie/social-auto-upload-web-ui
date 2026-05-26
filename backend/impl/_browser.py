"""CloakBrowser stealth browser factory.

All browser creation goes through this module.
"""

from conf import LOGIN_HEADLESS, LOCAL_CHROME_HEADLESS
from util._logger import get_channel_logger

logger = get_channel_logger("browser")


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

    from cloakbrowser import launch_async
    return await launch_async(headless=headless, proxy=proxy, args=extra_args)


async def create_context(
    browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
    viewport: dict | None = None,
):
    """Create a browser context with optional auth state."""
    return await browser.new_context(
        storage_state=storage_state,
        user_agent=user_agent,
        viewport=viewport,
    )


async def create_persistent_context(
    user_data_dir: str,
    headless: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
):
    """Create a persistent browser context with a local user data dir."""
    from cloakbrowser import launch_persistent_context_async
    return await launch_persistent_context_async(
        user_data_dir,
        headless=headless,
        proxy=proxy,
        args=extra_args,
    )


def create_browser_sync(
    headless: bool = False,
    extra_args: list | None = None,
):
    """Synchronous browser launch (for ``open_creator_center``)."""
    from cloakbrowser import launch
    return launch(headless=headless, args=extra_args)
