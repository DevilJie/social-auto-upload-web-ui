"""
Abstract base class for all social media platform implementations.

Each platform (Douyin, Xiaohongshu, Bilibili, etc.) must subclass BasePlatform
and implement the abstract methods. Browser entry points delegate to the
existing myUtils/browser.py factories.
"""

from abc import ABC, abstractmethod
from queue import Queue

from patchright.async_api import Playwright, Browser, BrowserContext


class BasePlatform(ABC):
    """Abstract base for platform-specific automation logic."""

    platform_id: int = 0
    platform_key: str = ""
    platform_name: str = ""

    # ------------------------------------------------------------------
    # Unified browser entry points (delegate to myUtils/browser.py)
    # ------------------------------------------------------------------

    async def create_browser(
        self,
        playwright: Playwright,
        headless: bool | None = None,
        login_mode: bool = False,
        proxy: dict | None = None,
        extra_args: list | None = None,
    ) -> Browser:
        """Create a Playwright browser instance.

        Delegates to ``myUtils.browser.create_browser`` which handles
        Chrome discovery (LOCAL_CHROME_PATH / system Chrome / built-in
        Chromium) and Patchright anti-detection args.
        """
        from myUtils.browser import create_browser as _create_browser

        return await _create_browser(
            playwright,
            headless=headless,
            login_mode=login_mode,
            proxy=proxy,
            extra_args=extra_args,
        )

    async def create_context(
        self,
        browser: Browser,
        storage_state: str | None = None,
        user_agent: str | None = None,
        viewport: dict | None = None,
    ) -> BrowserContext:
        """Create a browser context (optionally with stored auth state)."""
        from myUtils.browser import create_context as _create_context

        return await _create_context(
            browser,
            storage_state=storage_state,
            user_agent=user_agent,
            viewport=viewport,
        )

    async def create_persistent_context(
        self,
        playwright: Playwright,
        user_data_dir: str,
        headless: bool = False,
        proxy: dict | None = None,
        extra_args: list | None = None,
    ) -> BrowserContext:
        """Create a persistent browser context with a local user data dir."""
        from myUtils.browser import create_persistent_context as _create_persistent_context

        return await _create_persistent_context(
            playwright,
            user_data_dir=user_data_dir,
            headless=headless,
            proxy=proxy,
            extra_args=extra_args,
        )

    # ------------------------------------------------------------------
    # Abstract operations (every platform must implement)
    # ------------------------------------------------------------------

    @abstractmethod
    async def login(self, id: str, status_queue: Queue) -> None:
        """Perform platform login, pushing progress updates to *status_queue*."""
        ...

    @abstractmethod
    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        ...

    @abstractmethod
    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the platform creator / upload centre page."""
        ...

    @abstractmethod
    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile information from the platform.

        Returns a ``(display_name, avatar_url)`` tuple, or ``("", "")``
        on failure.
        """
        ...

    @abstractmethod
    def publish_video(self, **kwargs) -> bool:
        """Publish a video to the platform.  Returns True on success."""
        ...

    # ------------------------------------------------------------------
    # Optional stubs (override if the platform supports these)
    # ------------------------------------------------------------------

    async def publish_note(self, **kwargs) -> bool:
        """Publish an image note (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support note publishing"
        )

    async def get_statistics(self, **kwargs) -> dict:
        """Fetch account statistics (default: not supported)."""
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support statistics"
        )
