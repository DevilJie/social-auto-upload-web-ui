"""Platform registry and factory."""
import logging

from .base_platform import BasePlatform

logger = logging.getLogger(__name__)

_registry: dict[int, type[BasePlatform]] = {}


def register(platform_id: int, cls: type[BasePlatform]) -> None:
    """Register a platform implementation under *platform_id*."""
    _registry[platform_id] = cls


def get_platform(platform_id: int) -> BasePlatform | None:
    """Return an *instance* of the registered platform, or *None*."""
    cls = _registry.get(platform_id)
    return cls() if cls is not None else None


def get_platform_by_key(key: str) -> BasePlatform | None:
    """Return an *instance* of the platform matching *key*, or *None*."""
    for cls in _registry.values():
        if cls.platform_key == key:
            return cls()
    return None


def is_supported(platform_id: int) -> bool:
    """Return True if *platform_id* has a registered implementation."""
    return platform_id in _registry


# ---------------------------------------------------------------------------
# Populate registry -- late imports so modules can be added incrementally.
# ---------------------------------------------------------------------------

def _populate_registry() -> None:
    imports = [
        (1, ".xiaohongshu.platform", "XiaohongshuPlatform"),
        (2, ".channels.platform", "ChannelsPlatform"),
        (3, ".douyin.platform", "DouyinPlatform"),
        (4, ".kuaishou.platform", "KuaishouPlatform"),
        (5, ".bilibili.platform", "BilibiliPlatform"),
        (6, ".baijiahao.platform", "BaijiahaoPlatform"),
        (7, ".tiktok.platform", "TiktokPlatform"),
        (8, ".youtube.platform", "YoutubePlatform"),
        (9, ".tencent_video.platform", "TencentVideoPlatform"),
        (10, ".iqiyi.platform", "IqiyiPlatform"),
    ]

    import importlib

    for pid, mod_path, cls_name in imports:
        try:
            mod = importlib.import_module(mod_path, package=__package__)
            cls = getattr(mod, cls_name)
            register(pid, cls)
        except (ImportError, AttributeError) as e:
            logger.warning("Platform %d (%s) skipped: %s", pid, mod_path, e)


_populate_registry()
