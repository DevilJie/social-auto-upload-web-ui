"""视频发布校验规则（单点数据源）"""

import math


# 单位：秒 / bytes
# 数字必须与 docs/superpowers/specs/2026-06-19-video-validation-and-required-fields-design.md 第 2 节一致
VIDEO_LIMITS: dict[str, dict] = {
    "tencent_video": {"min_duration": 5,    "max_duration": 5400,             "max_size": 20 * 1024**3, "max_title_length": 80},           # 5s~90min,  20G,标题≤80字
    "iqiyi":         {"min_duration": 5,    "max_duration": 3600,             "max_size": 16 * 1024**3, "max_title_length": math.inf},  # 5s~60min,  16G
    "douyin":        {"min_duration": 5,    "max_duration": 3600,             "max_size": 16 * 1024**3, "max_title_length": math.inf},  # 5s~60min,  16G
    "baijiahao":     {"min_duration": 5,    "max_duration": math.inf,         "max_size": 12 * 1024**3, "max_title_length": math.inf},  # 5s~无,   12G
    "weibo":         {"min_duration": 0,    "max_duration": math.inf,         "max_size": 15 * 1024**3, "max_title_length": math.inf},  # 无时长下限,  15G
    "kuaishou":      {"min_duration": 5,    "max_duration": 3600,             "max_size": 12 * 1024**3, "max_title_length": math.inf},  # 5s~60min,  12G
    "bilibili":      {"min_duration": 5,    "max_duration": 36000,            "max_size": 16 * 1024**3, "max_title_length": 80, "max_desc_length": 2000},  # 5s~600min,16G,标题≤80字,简介≤2000字(emoji=3)
    "xiaohongshu":   {"min_duration": 5,    "max_duration": 14400,            "max_size": 20 * 1024**3, "max_title_length": 20},          # 5s~240min,20G,标题≤20字
    "channels":      {"min_duration": 5,    "max_duration": 28800,            "max_size": 20 * 1024**3, "max_title_length": math.inf},  # 5s~480min,20G
    "tiktok":        {"min_duration": 5,    "max_duration": 3600,             "max_size": 16 * 1024**3, "max_title_length": math.inf},  # 5s~60min,  16G
    "youtube":       {"min_duration": 5,    "max_duration": 36000,            "max_size": 16 * 1024**3, "max_title_length": math.inf},  # 5s~600min,16G
    "alipay":        {"min_duration": 5,    "max_duration": math.inf,         "max_size": 8 * 1024**3,  "max_title_length": math.inf},   # 5s~无,    8G(文档:≤8G,时长不限)
    "zhihu":         {"min_duration": 0,    "max_duration": math.inf,         "max_size": math.inf,     "max_title_length": math.inf},   # 文档:时长大小不限
}


_PLATFORM_NAMES = {
    "tencent_video": "腾讯视频",
    "iqiyi": "爱奇艺",
    "douyin": "抖音",
    "baijiahao": "百家号",
    "weibo": "微博",
    "kuaishou": "快手",
    "bilibili": "B站",
    "xiaohongshu": "小红书",
    "channels": "视频号",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "alipay": "支付宝",
    "zhihu": "知乎",
}


def _format_size(size_bytes: float) -> str:
    """自适应单位：B/KB/MB/GB。inf/nan/负数返回"未知"。"""
    if size_bytes is None or math.isnan(size_bytes) or math.isinf(size_bytes) or size_bytes < 0:
        return "未知"
    if size_bytes < 1024:
        return f"{size_bytes:.1f} B"
    if size_bytes < 1024**2:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024**3:
        return f"{size_bytes / 1024**2:.1f} MB"
    return f"{size_bytes / 1024**3:.1f} GB"


def _format_duration(seconds: float) -> str:
    """自适应单位：秒 / 分秒 / 时分秒。inf/nan/负数返回"未知"。"""
    if seconds is None or math.isnan(seconds) or math.isinf(seconds) or seconds < 0:
        return "未知"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} 秒"
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h} 小时 {m} 分 {s} 秒"
    return f"{m} 分 {s} 秒"


def _format_max_duration(max_duration: float) -> str:
    if max_duration == math.inf:
        return "无限制"
    return _format_duration(max_duration)


def validate_video_for_platform(platform_key: str, duration_sec: float, size_bytes: float) -> tuple[bool, str]:
    """校验视频时长和大小是否符合平台限制。

    Args:
        platform_key: 平台 key（如 "douyin"）
        duration_sec: 时长（秒）
        size_bytes: 大小（bytes）

    Returns:
        (ok, error_msg). error_msg 为空时表示通过。
        未配置的平台默认放行（新平台不阻塞）。
    """
    limits = VIDEO_LIMITS.get(platform_key)
    if limits is None:
        return True, ""

    name = _PLATFORM_NAMES.get(platform_key, platform_key)

    if duration_sec < limits["min_duration"]:
        return False, (
            f"{name}：时长 {_format_duration(duration_sec)} "
            f"小于最小值 ({_format_duration(limits['min_duration'])})"
        )
    if duration_sec > limits["max_duration"]:
        return False, (
            f"{name}：时长 {_format_duration(duration_sec)} "
            f"超出最大值 ({_format_max_duration(limits['max_duration'])})"
        )
    if size_bytes > limits["max_size"]:
        return False, (
            f"{name}：大小 {_format_size(size_bytes)} "
            f"超出限制 (最大 {_format_size(limits['max_size'])})"
        )
    return True, ""


def validate_title_for_platform(platform_key: str, title: str) -> tuple[bool, str]:
    """校验视频标题是否符合平台限制(如小红书 ≤ 20 字)。

    Args:
        platform_key: 平台 key
        title: 标题

    Returns:
        (ok, error_msg). error_msg 为空时表示通过。
        未配置的平台默认放行(无标题长度限制)。

    字符计算规则:BMP 字符 = 1,emoji 等非 BMP 字符 = 3。
    """
    limits = VIDEO_LIMITS.get(platform_key)
    if limits is None:
        return True, ""

    name = _PLATFORM_NAMES.get(platform_key, platform_key)
    max_len = limits.get("max_title_length", math.inf)
    if max_len == math.inf:
        return True, ""

    # 按 emoji=3 规则计算字符数
    title_len = 0
    for ch in (title or ""):
        title_len += 3 if ord(ch) > 0xFFFF else 1

    if title_len > max_len:
        return False, (
            f"{name}：标题 {title_len} 字超过限制 (最多 {max_len} 字,emoji 按 3 算)"
        )
    return True, ""


def validate_desc_for_platform(platform_key: str, desc: str) -> tuple[bool, str]:
    """校验视频简介是否符合平台限制(如 B 站 ≤ 2000 字,emoji 按 3 算)。

    Args:
        platform_key: 平台 key
        desc: 简介内容

    Returns:
        (ok, error_msg). error_msg 为空时表示通过。
        未配置的平台默认放行。
    """
    limits = VIDEO_LIMITS.get(platform_key)
    if limits is None:
        return True, ""

    name = _PLATFORM_NAMES.get(platform_key, platform_key)
    max_len = limits.get("max_desc_length", math.inf)
    if max_len == math.inf:
        return True, ""

    # 按 emoji=3 规则计算字符数
    desc_len = 0
    for ch in (desc or ""):
        desc_len += 3 if ord(ch) > 0xFFFF else 1

    if desc_len > max_len:
        return False, (
            f"{name}：简介 {desc_len} 字超过限制 (最多 {max_len} 字,emoji 按 3 算)"
        )
    return True, ""
