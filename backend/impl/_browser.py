"""New engine browser factory — CloakBrowser stealth layer.

All browser creation goes through this module.

Falls back to standard Playwright when CloakBrowser binary is unavailable
(e.g. during development without a bundled binary).
"""

import logging
import os

from conf import LOCAL_CHROME_HEADLESS, LOGIN_HEADLESS

logger = logging.getLogger(__name__)

# Set to True after successful CloakBrowser binary download
_using_cloakbrowser = False


def _download_binary():
    """Download CloakBrowser stealth binary, bypassing system SOCKS proxy.

    httpx does not natively support SOCKS proxies unless ``socksio`` is
    installed.  Since most users won't have that package, temporarily clear
    proxy env vars so the binary download uses a direct connection.
    """
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
    """Pre-download CloakBrowser binary at startup.

    Should be called once during backend startup (in ``app.py``).
    Logs whether CloakBrowser or Playwright fallback will be used.
    """
    global _using_cloakbrowser

    try:
        _download_binary()
        _using_cloakbrowser = True
        logger.info("CloakBrowser stealth binary ready")
    except Exception as e:
        _using_cloakbrowser = False
        logger.warning(
            "CloakBrowser unavailable (%s), will use Playwright fallback", e
        )


def _patch_close(browser, pw):
    """Patch browser.close() to also stop the Playwright instance.

    Matches CloakBrowser's behavior so callers don't need to manage
    the Playwright lifecycle separately.
    """
    original_close = browser.close

    def _close():
        try:
            original_close()
        finally:
            pw.stop()

    browser.close = _close
    return browser


async def _patch_close_async(browser, pw):
    """Async version of _patch_close."""
    original_close = browser.close

    async def _close():
        try:
            await original_close()
        finally:
            await pw.stop()

    browser.close = _close
    return browser


async def create_browser(
    headless: bool | None = None,
    login_mode: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
):
    """Create a stealth Chromium browser via CloakBrowser.

    Falls back to standard Playwright when CloakBrowser binary is
    unavailable (e.g. no bundled binary, download fails).

    Args:
        headless: Run headless.  Defaults to ``LOGIN_HEADLESS`` when
            *login_mode* is True, else ``LOCAL_CHROME_HEADLESS``.
        login_mode: If True, use login headless default (visible).
        proxy: Proxy config (dict or URL string).
        extra_args: Additional Chromium CLI arguments.
    """
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS

    try:
        from cloakbrowser import launch_async

        return await launch_async(headless=headless, proxy=proxy, args=extra_args)
    except Exception as e:
        logger.warning("CloakBrowser unavailable (%s), falling back to Playwright", e)

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    opts = {"headless": headless}
    if extra_args:
        opts["args"] = extra_args
    if proxy:
        opts["proxy"] = proxy
    browser = await pw.chromium.launch(**opts)
    return await _patch_close_async(browser, pw)


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
    """Create a persistent browser context with a local user data dir.

    Falls back to standard Playwright when CloakBrowser binary is unavailable.
    """
    try:
        from cloakbrowser import launch_persistent_context_async

        return await launch_persistent_context_async(
            user_data_dir,
            headless=headless,
            proxy=proxy,
            args=extra_args,
        )
    except Exception as e:
        logger.warning("CloakBrowser unavailable (%s), falling back to Playwright", e)

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    opts = {
        "user_data_dir": user_data_dir,
        "headless": headless,
    }
    if extra_args:
        opts["args"] = extra_args
    if proxy:
        opts["proxy"] = proxy
    context = await pw.chromium.launch_persistent_context(**opts)

    # Patch context.close() to also stop Playwright
    original_close = context.close

    async def _close():
        try:
            await original_close()
        finally:
            await pw.stop()

    context.close = _close
    return context


def create_browser_sync(
    headless: bool = False,
    extra_args: list | None = None,
):
    """Synchronous browser launch (for ``open_creator_center``).

    Falls back to standard Playwright when CloakBrowser binary is unavailable.
    """
    try:
        from cloakbrowser import launch

        return launch(headless=headless, args=extra_args)
    except Exception as e:
        logger.warning("CloakBrowser unavailable (%s), falling back to Playwright", e)

    from playwright.sync_api import sync_playwright

    pw = sync_playwright().start()
    opts = {"headless": headless}
    if extra_args:
        opts["args"] = extra_args
    browser = pw.chromium.launch(**opts)
    return _patch_close(browser, pw)
