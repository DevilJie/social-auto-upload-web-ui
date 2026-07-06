"""视频校验规则单元测试"""
import math
from util.video_limits import (
    VIDEO_LIMITS, validate_video_for_platform, validate_title_for_platform,
    _format_size, _format_duration,
)


# ----- 平台规则完整性 -----

def test_all_platforms_have_limits():
    """恰好 12 个平台，不多不少"""
    expected_keys = {
        "tencent_video", "iqiyi", "douyin", "baijiahao", "weibo",
        "kuaishou", "bilibili", "xiaohongshu", "channels",
        "tiktok", "youtube", "alipay",
    }
    assert set(VIDEO_LIMITS.keys()) == expected_keys


def test_tencent_video_rules():
    limit = VIDEO_LIMITS["tencent_video"]
    assert limit["min_duration"] == 5
    assert limit["max_duration"] == 5400  # 90 * 60
    assert limit["max_size"] == 20 * 1024**3
    assert limit["max_title_length"] == 80  # 腾讯视频标题 ≤ 80 字


def test_validate_title_tencent_video_ok():
    ok, msg = validate_title_for_platform("tencent_video", "a" * 80)
    assert ok is True
    assert msg == ""


def test_validate_title_tencent_video_over_80():
    ok, msg = validate_title_for_platform("tencent_video", "a" * 81)
    assert ok is False
    assert "80" in msg
    assert "81" in msg


def test_baijiahao_unlimited_duration():
    """百家号最大时长为无限大"""
    assert VIDEO_LIMITS["baijiahao"]["max_duration"] == math.inf


def test_weibo_no_min_duration():
    """微博无最小时长限制"""
    assert VIDEO_LIMITS["weibo"]["min_duration"] == 0


# ----- validate_video_for_platform 逻辑 -----

def test_validate_ok_within_range():
    ok, msg = validate_video_for_platform("douyin", 30, 100 * 1024**2)
    assert ok is True
    assert msg == ""


def test_validate_fail_below_min_duration():
    """微博已放开最小时长,改用有最低时长限制的平台(抖音 min=5)测"""
    ok, msg = validate_video_for_platform("douyin", 3, 100 * 1024**2)
    assert ok is False
    assert "抖音" in msg


def test_validate_fail_above_max_duration():
    ok, msg = validate_video_for_platform("douyin", 4000, 100 * 1024**2)
    assert ok is False
    assert "抖音" in msg
    assert "1 小时" in msg  # 抖音最大 60 分钟 = 1 小时 0 分 0 秒


def test_validate_fail_above_max_size():
    ok, msg = validate_video_for_platform("douyin", 30, 20 * 1024**3)
    assert ok is False
    assert "抖音" in msg
    assert "G" in msg  # 大小单位


def test_validate_baijiahao_unlimited_max_duration():
    """百家号：超过任何时长都不应超时长限制（但会超大文件限制）"""
    ok, msg = validate_video_for_platform("baijiahao", 3600 * 24, 1 * 1024**3)
    assert ok is True


def test_validate_unknown_platform_returns_ok():
    """未配置的平台：放行（不阻塞新平台接入）"""
    ok, msg = validate_video_for_platform("unknown_platform", 999, 999)
    assert ok is True
    assert msg == ""


# ----- 格式化辅助 -----

def test_format_size_bytes():
    assert _format_size(500) == "500.0 B"


def test_format_size_mb():
    assert _format_size(50 * 1024**2) == "50.0 MB"


def test_format_size_gb():
    result = _format_size(2.5 * 1024**3)
    assert "GB" in result


def test_format_duration_seconds_only():
    assert _format_duration(45) == "45 秒"


def test_format_duration_minutes():
    assert _format_duration(125) == "2 分 5 秒"


def test_format_duration_hours():
    result = _format_duration(3725)
    assert "1 小时" in result
    assert "2 分" in result


def test_format_size_inf_returns_unknown():
    assert _format_size(float("inf")) == "未知"


def test_format_size_negative_returns_unknown():
    assert _format_size(-100) == "未知"


def test_format_duration_inf_returns_unknown():
    """inf/nan/负数 安全返回，不会触发 int(inf) OverflowError"""
    assert _format_duration(float("inf")) == "未知"
    assert _format_duration(float("nan")) == "未知"
    assert _format_duration(-10) == "未知"


# ----- 标题长度校验 -----

def test_xiaohongshu_title_max_20():
    """小红书标题最多 20 字"""
    assert VIDEO_LIMITS["xiaohongshu"]["max_title_length"] == 20


def test_validate_title_xiaohongshu_ok():
    ok, msg = validate_title_for_platform("xiaohongshu", "a" * 20)
    assert ok is True
    assert msg == ""


def test_validate_title_xiaohongshu_over_20():
    ok, msg = validate_title_for_platform("xiaohongshu", "a" * 21)
    assert ok is False
    assert "20" in msg
    assert "21" in msg


def test_validate_title_xiaohongshu_empty():
    ok, msg = validate_title_for_platform("xiaohongshu", "")
    assert ok is True


def test_validate_title_other_platform_unlimited():
    """未限制标题长度的平台(除小红书外)默认放行"""
    for k in ("douyin", "weibo", "kuaishou", "alipay"):
        ok, _ = validate_title_for_platform(k, "a" * 500)
        assert ok is True, f"{k} 应该有无限标题长度"


def test_validate_title_unknown_platform_ok():
    """未配置的平台:放行"""
    ok, msg = validate_title_for_platform("unknown_platform", "a" * 999)
    assert ok is True
    assert msg == ""


# ----- 字符计数 emoji=3 规则 -----

def test_validate_title_emoji_counts_3_per_char():
    """emoji 每个计 3 字:7 个 emoji = 21 字,小红书 20 字限制应拦截"""
    # 🎉 是非 BMP 字符(codepoint 0x1F389,> 0xFFFF)
    title = "🎉" * 7  # 实际长度 21 字(7×3)
    ok, msg = validate_title_for_platform("xiaohongshu", title)
    assert ok is False
    assert "21" in msg
    assert "20" in msg


def test_validate_title_mixed_ascii_emoji():
    """6 个 ASCII + 5 个 emoji = 6 + 15 = 21 字,小红书 20 字限制应拦截"""
    title = "a" * 6 + "🎉" * 5  # 21 字
    ok, msg = validate_title_for_platform("xiaohongshu", title)
    assert ok is False
    assert "21" in msg


def test_validate_title_emoji_exactly_at_limit():
    """6 个 ASCII + 4 个 emoji = 6 + 12 = 18 字,应通过"""
    title = "a" * 6 + "🎉" * 4  # 18 字
    ok, msg = validate_title_for_platform("xiaohongshu", title)
    assert ok is True


def test_validate_title_tencent_emoji_count():
    """腾讯视频:80 字限制,75 个 ASCII + 2 个 emoji = 75+6=81,应拦截"""
    title = "a" * 75 + "🎉" * 2  # 81 字
    ok, msg = validate_title_for_platform("tencent_video", title)
    assert ok is False
    assert "81" in msg


def test_validate_title_tencent_emoji_ok():
    """腾讯视频:80 字限制,74 个 ASCII + 2 个 emoji = 74+6=80,刚好通过"""
    title = "a" * 74 + "🎉" * 2  # 80 字
    ok, msg = validate_title_for_platform("tencent_video", title)
    assert ok is True
