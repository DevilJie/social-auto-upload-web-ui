# vendor/upstream/myUtils/browser.py
"""统一浏览器启动入口 — 基于 Patchright 反检测机制

Patchright 内置反检测机制：
- CDP 层：Runtime.enable leak、Console leak、Command Flags 等
- 注意：stealth.min.js 与 Patchright 的 init script 机制冲突，不能叠加使用
  （会导致 net::ERR_CONNECTION_CLOSED）

浏览器优先级：系统 Chrome/Chromium > Patchright 自带 Chromium。
"""
from patchright.async_api import Playwright, Browser, BrowserContext
from patchright.sync_api import Playwright as SyncPlaywright, Browser as SyncBrowser, BrowserContext as SyncBrowserContext
from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS, LOGIN_HEADLESS


def _build_launch_args(extra_args: list | None = None) -> list:
    """构建浏览器启动参数（Patchright 已内置反检测 args，无需手动添加）"""
    args = ['--lang=zh-CN', '--disable-infobars', '--start-maximized']
    if extra_args:
        args.extend(extra_args)
    return args


def _get_channel_or_path() -> dict:
    """
    浏览器优先级：
    1. 系统 Chrome/Chromium（通过 LOCAL_CHROME_PATH 或 channel='chrome'）
    2. Patchright 自带的 Chromium（兜底）
    """
    opts = {}
    if LOCAL_CHROME_PATH:
        opts['executable_path'] = LOCAL_CHROME_PATH
    else:
        opts['channel'] = 'chrome'  # 使用系统 Chrome，找不到则自动降级
    return opts


async def create_browser(
    playwright: Playwright,
    headless: bool | None = None,
    login_mode: bool = False,
    proxy: dict | None = None,
    extra_args: list | None = None,
) -> Browser:
    """
    统一的浏览器启动入口。

    Args:
        playwright: patchright Playwright 实例
        headless: 是否无头模式。None 时根据 login_mode 自动判断
        login_mode: 登录模式（强制有头以便扫码）
        proxy: 代理配置
        extra_args: 额外的浏览器启动参数
    """
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS

    opts = {
        'headless': headless,
        'args': _build_launch_args(extra_args),
    }
    opts.update(_get_channel_or_path())

    if proxy:
        opts['proxy'] = proxy

    return await playwright.chromium.launch(**opts)


async def create_context(
    browser: Browser,
    storage_state: str | None = None,
    user_agent: str | None = None,
    viewport: dict | None = None,
) -> BrowserContext:
    """
    统一的上下文创建入口。

    注意：不注入 stealth.js，因为 stealth.js 与 Patchright 的 Routes 注入机制冲突，
    会导致 net::ERR_CONNECTION_CLOSED。Patchright 自身已提供充分的反检测能力。

    Args:
        browser: Browser 实例
        storage_state: cookie 文件路径
        user_agent: 自定义 UA
        viewport: 视口大小
    """
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
    """
    创建持久化上下文（用于需要代理+有头模式的场景，如 YouTube 登录）。

    Args:
        playwright: patchright Playwright 实例
        user_data_dir: 用户数据目录
        headless: 是否无头模式
        proxy: 代理配置
        extra_args: 额外的浏览器启动参数
    """
    opts = {
        'user_data_dir': user_data_dir,
        'headless': headless,
        'args': _build_launch_args(extra_args),
    }
    opts.update(_get_channel_or_path())
    if proxy:
        opts['proxy'] = proxy
    return await playwright.chromium.launch_persistent_context(**opts)


# ── Sync API（用于 xhs_uploader/sign_local、sau_backend 等同步场景）──

def create_browser_sync(
    playwright: SyncPlaywright,
    headless: bool = True,
    extra_args: list | None = None,
) -> SyncBrowser:
    """同步版本的浏览器启动入口。"""
    opts = {
        'headless': headless,
        'args': _build_launch_args(extra_args),
    }
    opts.update(_get_channel_or_path())
    return playwright.chromium.launch(**opts)


def create_context_sync(
    browser: SyncBrowser,
    storage_state: str | None = None,
) -> SyncBrowserContext:
    """同步版本的上下文创建入口。"""
    opts = {}
    if storage_state:
        opts['storage_state'] = storage_state
    return browser.new_context(**opts)
