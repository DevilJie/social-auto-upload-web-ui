"""抖音发布前置校验单元测试:话题总数 ≤ 5(描述 #xxx + 标签 + 官方活动)。

只测纯函数 ``_count_hashtags`` / ``_validate_publish_params``,
不触发浏览器/CloakBrowser 流程。
"""
import sys
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.douyin.platform import DouyinPlatform  # noqa: E402


# ----- _count_hashtags: 描述文本里独立 #xxx 计数 -----

def test_count_hashtags_empty():
    assert DouyinPlatform._count_hashtags("") == 0
    assert DouyinPlatform._count_hashtags(None) == 0


def test_count_hashtags_basic():
    assert DouyinPlatform._count_hashtags("你好 #话题1 #话题2") == 2


def test_count_hashtags_leading_hash():
    """行首的 # 也算话题"""
    assert DouyinPlatform._count_hashtags("#话题1 描述 #话题2") == 2


def test_count_hashtags_five_ok():
    """5 个话题"""
    text = "#a #b #c #d #e"
    assert DouyinPlatform._count_hashtags(text) == 5


def test_count_hashtags_six():
    """6 个话题"""
    text = "#a #b #c #d #e #f"
    assert DouyinPlatform._count_hashtags(text) == 6


def test_count_hashtags_inline_not_counted():
    """a#b 这种粘连的不算独立话题"""
    assert DouyinPlatform._count_hashtags("a#b c#d") == 0


def test_count_hashtags_url_anchor_not_counted():
    """http://x#anchor 这种 # 前面不是空白,不算"""
    assert DouyinPlatform._count_hashtags("http://example.com#section 看这个") == 0


def test_count_hashtags_double_hash_not_counted():
    """## 开头(# 后紧跟 #)不算"""
    assert DouyinPlatform._count_hashtags("## 标题 #正常") == 1


def test_count_hashtags_isolated_hash_not_counted():
    """孤立 # 不算"""
    assert DouyinPlatform._count_hashtags("单独 # 一个") == 0


def test_count_hashtags_multiline():
    """多行:每行行首的 # 都算"""
    text = "#第一行\n#第二行\n普通文字 #第三行"
    assert DouyinPlatform._count_hashtags(text) == 3


# ----- _validate_publish_params: 合并计数 ≤ 5 -----

def test_validate_desc_only_5_ok():
    desc = "#a #b #c #d #e"
    ok, msg = DouyinPlatform._validate_publish_params(desc, [], [])
    assert ok is True
    assert msg == ""


def test_validate_desc_only_6_fail():
    desc = "#a #b #c #d #e #f"
    ok, msg = DouyinPlatform._validate_publish_params(desc, [], [])
    assert ok is False
    assert "6" in msg
    assert "5" in msg


def test_validate_desc3_tags2_ok():
    """描述 3 + 标签 2 = 5,刚好通过"""
    desc = "#a #b #c"
    ok, msg = DouyinPlatform._validate_publish_params(desc, ["x", "y"], [])
    assert ok is True
    assert msg == ""


def test_validate_desc3_tags3_fail():
    """描述 3 + 标签 3 = 6,拦截"""
    desc = "#a #b #c"
    ok, msg = DouyinPlatform._validate_publish_params(desc, ["x", "y", "z"], [])
    assert ok is False
    assert "6" in msg


def test_validate_desc2_activity2_tags2_fail():
    """描述 2 + 官方活动 2 + 标签 2 = 6,拦截"""
    desc = "#a #b"
    ok, msg = DouyinPlatform._validate_publish_params(desc, ["x", "y"], ["act1", "act2"])
    assert ok is False
    assert "6" in msg


def test_validate_all_sources_exactly_5_ok():
    """描述 2 + 活动 2 + 标签 1 = 5,刚好通过"""
    desc = "#a #b"
    ok, msg = DouyinPlatform._validate_publish_params(desc, ["x"], ["act1", "act2"])
    assert ok is True
    assert msg == ""


def test_validate_empty_all_ok():
    """全空:通过"""
    ok, msg = DouyinPlatform._validate_publish_params("", [], [])
    assert ok is True
    assert msg == ""


def test_validate_none_args_ok():
    """None 参数容错:通过"""
    ok, msg = DouyinPlatform._validate_publish_params(None, None, None)
    assert ok is True
    assert msg == ""


def test_validate_message_contains_breakdown():
    """错误消息包含三项明细(描述/标签/官方活动数量),便于用户定位"""
    desc = "#a #b"
    ok, msg = DouyinPlatform._validate_publish_params(desc, ["x", "y", "z"], ["act1", "act2"])
    assert ok is False
    assert "标签" in msg
    assert "官方活动" in msg
