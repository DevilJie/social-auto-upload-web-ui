"""
Platform registry and factory.

All platform classes are registered at module load time via late imports
so that the registry package is self-contained even when individual platform
modules do not yet exist (they will be added in later tasks).
"""

from .base_platform import BasePlatform

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
        (1, ".xiaohongshu.uploader", "XiaohongshuPlatform"),
        (2, ".channels.uploader", "ChannelsPlatform"),
        (3, ".douyin.uploader", "DouyinPlatform"),
        (4, ".kuaishou.uploader", "KuaishouPlatform"),
        (5, ".bilibili.uploader", "BilibiliPlatform"),
        (6, ".baijiahao.uploader", "BaijiahaoPlatform"),
        (7, ".tiktok.uploader", "TiktokPlatform"),
        (8, ".youtube.uploader", "YoutubePlatform"),
    ]

    for pid, mod_path, cls_name in imports:
        try:
            mod = __import__(mod_path, fromlist=[cls_name], package=__package__)
            cls = getattr(mod, cls_name)
            register(pid, cls)
        except (ImportError, AttributeError):
            pass  # Module not yet created -- will be populated later


_populate_registry()
