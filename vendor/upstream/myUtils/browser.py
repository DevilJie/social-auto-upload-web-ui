# vendor/upstream/myUtils/browser.py
"""统一浏览器启动入口 — 基于 Patchright 反检测机制

Patchright 内置反检测机制：
- CDP 层：Runtime.enable leak、Console leak、Command Flags 等
- 注意：stealth.min.js 与 Patchright 的 init script 机制冲突，不能叠加使用
  （会导致 net::ERR_CONNECTION_CLOSED）

浏览器优先级：LOCAL_CHROME_PATH > 系统 Chrome > Patchright 自带 Chromium。
"""
import logging

from patchright.async_api import Playwright, Browser, BrowserContext
from patchright.sync_api import Playwright as SyncPlaywright, Browser as SyncBrowser, BrowserContext as SyncBrowserContext
from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS, LOGIN_HEADLESS

logger = logging.getLogger(__name__)


def _build_launch_args(extra_args: list | None = None) -> list:
    """构建浏览器启动参数（Patchright 已内置反检测 args，无需手动添加）"""
    args = ['--lang=zh-CN', '--disable-infobars', '--start-maximized']
    if extra_args:
        args.extend(extra_args)
    return args


def _get_browser_opts() -> dict:
    """
    浏览器优先级：
    1. LOCAL_CHROME_PATH 指定的 Chrome/Chromium
    2. 系统 Chrome（channel='chrome'）
    3. Patchright 自带的 Chromium（兜底，不传 channel 和 executable_path）
    """
    if LOCAL_CHROME_PATH:
        return {'executable_path': LOCAL_CHROME_PATH}
    return {'channel': 'chrome'}


async def create_browser(
    playwright: Playwright,
    headless: bool | None = None,
    login_mode: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
) -> Browser:
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS

    opts = {
        'headless': headless,
        'args': _build_launch_args(extra_args),
    }
    opts.update(_get_browser_opts())
    if proxy:
        opts['proxy'] = proxy

    try:
        return await playwright.chromium.launch(**opts)
    except Exception:
        fallback = {k: v for k, v in opts.items() if k not in ('channel', 'executable_path')}
        logger.warning("系统 Chrome 不可用，降级到 Patchright 内置 Chromium")
        return await playwright.chromium.launch(**fallback)


async def create_context(
    browser: Browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
    viewport: dict | None = None,
) -> BrowserContext:
    opts = {}
    if storage_state:
        opts['storage_state'] = storage_state
    if user_agent:
        opts['user_agent'] = user_agent
    if viewport:
        opts['viewport'] = viewport
    return await browser.new_context(**opts)


async def create_persistent_context(
    playwright: Playwright,
    user_data_dir: str,
    headless: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
) -> BrowserContext:
    opts = {
        'user_data_dir': user_data_dir,
        'headless': headless,
        'args': _build_launch_args(extra_args),
    }
    opts.update(_get_browser_opts())
    if proxy:
        opts['proxy'] = proxy

    try:
        return await playwright.chromium.launch_persistent_context(**opts)
    except Exception:
        fallback = {k: v for k, v in opts.items() if k not in ('channel', 'executable_path')}
        logger.warning("系统 Chrome 不可用，降级到 Patchright 内置 Chromium")
        return await playwright.chromium.launch_persistent_context(**fallback)


# ── Sync API（用于 xhs_uploader/sign_local、sau_backend 等同步场景）──

def create_browser_sync(
    playwright: SyncPlaywright,
    headless: bool = True,
    extra_args: list | None = None,
) -> SyncBrowser:
    opts = {
        'headless': headless,
        'args': _build_launch_args(extra_args),
    }
    opts.update(_get_browser_opts())

    try:
        return playwright.chromium.launch(**opts)
    except Exception:
        fallback = {k: v for k, v in opts.items() if k not in ('channel', 'executable_path')}
        logger.warning("系统 Chrome 不可用，降级到 Patchright 内置 Chromium")
        return playwright.chromium.launch(**fallback)


def create_context_sync(
    browser: SyncBrowser,
    storage_state: str | None = None,
) -> SyncBrowserContext:
    opts = {}
    if storage_state:
        opts['storage_state'] = storage_state
    return browser.new_context(**opts)
