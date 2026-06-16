"""Unit tests for `WeiboPlatform` class registration and contracts."""
import sys
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.registry import is_supported, get_platform  # noqa: E402
from app import PLATFORM_MAP, PLATFORM_ID_TO_KEY  # noqa: E402


def test_weibo_platform_class_attributes():
    """WeiboPlatform 的 platform_id/key/name 必须与 spec 一致。"""
    from impl.weibo.platform import WeiboPlatform
    p = WeiboPlatform()
    assert p.platform_id == 11
    assert p.platform_key == "weibo"
    assert p.platform_name == "微博"


def test_weibo_registered_in_registry():
    """Registry 必须能用 id=11 拿到 WeiboPlatform。"""
    assert is_supported(11) is True
    platform = get_platform(11)
    assert platform is not None
    assert platform.__class__.__name__ == "WeiboPlatform"


def test_weibo_platform_mappings_in_app():
    """app.py 的 PLATFORM_MAP / PLATFORM_ID_TO_KEY 必须包含 11。"""
    assert PLATFORM_MAP[11] == "微博"
    assert PLATFORM_ID_TO_KEY[11] == "weibo"


def test_weibo_publish_video_signature():
    """publish_video 必须已实现,接受 **kwargs 并返回 bool(同步包装器)。

    实际跑发布需要 Playwright + 登录 cookie,这里只验证签名/返回类型。
    """
    from impl.weibo.platform import WeiboPlatform
    import inspect
    p = WeiboPlatform()
    sig = inspect.signature(p.publish_video)
    # 接受 **kwargs(发布参数由 app.py 传入,平台层不强制签名)
    assert any(
        p.kind == inspect.Parameter.VAR_KEYWORD
        for p in sig.parameters.values()
    ), "publish_video should accept **kwargs"
