"""CloakBrowser stealth browser factory — unified entry point.

所有打开浏览器的入口都集中在这里。调用方不要直接调 browser.new_context
或 cloakbrowser.launch_*，避免东一套西一套。

所有 context 使用 no_viewport=True，页面内容跟随窗口大小自动 reflow。
"""

import asyncio

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
    humanize: bool = False,
    human_preset: str = "default",
):
    """异步入口：创建 stealth Chromium 浏览器。

    不接 proxy / extra_args —— 历史代理配置已废弃。

    login_mode=True 或 headless=False（有头）时，自动监听浏览器关闭
    事件：**用户手动**关浏览器会 cancel 当前 asyncio task，使 login/发布
    流程立即终止并返回失败。而发布成功后平台代码主动 browser.close()
    的正常收尾不会误触发（内部已 disarm）。

    humanize=True 时启用 CloakBrowser 拟人化操作层（贝塞尔鼠标轨迹、
    逐键打字、平滑滚动等），仅建议在发布动作开启——会让操作明显变慢，
    login/check_cookie/sync_profile 等高频轻量调用保持关闭更稳妥。
    human_preset: 'default'(正常人速度) 或 'careful'(更慢更谨慎)。
    """
    if headless is None:
        headless = LOGIN_HEADLESS if login_mode else LOCAL_CHROME_HEADLESS
    from cloakbrowser import launch_async
    browser = await launch_async(
        headless=headless,
        args=["--start-maximized"],
        humanize=humanize,
        human_preset=human_preset,
    )

    if login_mode or headless is False:
        # login 或有头浏览器（发布场景）：用户主动关浏览器 → cancel 当前 task，
        # 使 login/发布流程立即终止，避免后端 worker 一直阻塞。
        task = asyncio.current_task()
        # 武装状态：仅当「用户意外关闭」时才 cancel。
        # 平台代码在发布成功后会在 finally 里主动 browser.close() 正常收尾，
        # 这种 close 同样会触发 disconnected，必须先 disarm 避免误判成功为失败。
        armed = True

        def _on_browser_closed():
            if armed and task and not task.done():
                logger.info("[browser] 用户关闭了浏览器，取消当前任务")
                task.cancel()

        browser.on("disconnected", _on_browser_closed)

        # 包装 close：代码主动收尾关闭时先 disarm，使 disconnected 回调不再 cancel。
        # Browser.close 是普通 async 实例方法，可实例级覆盖（Playwright 文档已确认）。
        _orig_close = browser.close

        async def _safe_close(*args, **kwargs):
            nonlocal armed
            armed = False  # 同步 disarm，在 await 之前生效
            return await _orig_close(*args, **kwargs)

        browser.close = _safe_close

    return browser


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
        args=["--window-size=1920,1080", "--start-maximized"],
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
