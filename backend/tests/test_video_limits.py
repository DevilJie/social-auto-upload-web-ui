"""视频校验规则单元测试"""
import math
from util.video_limits import VIDEO_LIMITS, validate_video_for_platform, _format_size, _format_duration


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


def test_baijiahao_unlimited_duration():
    """百家号最大时长为无限大"""
    assert VIDEO_LIMITS["baijiahao"]["max_duration"] == math.inf


def test_weibo_min_15_seconds():
    """微博最小 15 秒"""
    assert VIDEO_LIMITS["weibo"]["min_duration"] == 15


# ----- validate_video_for_platform 逻辑 -----

def test_validate_ok_within_range():
    ok, msg = validate_video_for_platform("douyin", 30, 100 * 1024**2)
    assert ok is True
    assert msg == ""


def test_validate_fail_below_min_duration():
    ok, msg = validate_video_for_platform("weibo", 10, 100 * 1024**2)
    assert ok is False
    assert "微博" in msg
    assert "15" in msg


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
