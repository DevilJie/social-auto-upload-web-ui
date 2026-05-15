# vendor/upstream/myUtils/browser.py
"""统一浏览器启动入口 — 基于 Patchright 反检测机制

双层防检测策略：
1. Patchright：CDP 驱动层反检测（Runtime.enable leak、Console leak、Command Flags）
2. stealth.min.js：JS 层指纹修补（navigator.webdriver、chrome 对象等）

浏览器优先级：系统 Chrome/Chromium > Patchright 自带 Chromium。
"""
from pathlib import Path

from patchright.async_api import Playwright, Browser, BrowserContext
from conf import LOCAL_CHROME_PATH, LOCAL_CHROME_HEADLESS, LOGIN_HEADLESS

_STEALTH_JS_PATH = Path(__file__).parent.parent / "utils" / "stealth.min.js"


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

    自动注入 stealth.min.js 作为 JS 层额外防检测（与 Patchright CDP 层互补）。

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
    context = await browser.new_context(**opts)
    # 注入 stealth.js 作为 JS 层额外防检测
    if _STEALTH_JS_PATH.exists():
        await context.add_init_script(path=str(_STEALTH_JS_PATH))
    return context