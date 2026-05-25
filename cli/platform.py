PLATFORM_NAMES: dict[int, str] = {
    1: "小红书",
    2: "视频号",
    3: "抖音",
    4: "快手",
    5: "B站",
    6: "百家号",
    7: "TikTok",
    8: "YouTube",
    9: "腾讯视频",
    10: "爱奇艺",
}

PLATFORM_KEYS: dict[int, str] = {
    1: "xiaohongshu",
    2: "channels",
    3: "douyin",
    4: "kuaishou",
    5: "bilibili",
    6: "baijiahao",
    7: "tiktok",
    8: "youtube",
    9: "tencent_video",
    10: "iqiyi",
}

_NAME_TO_ID: dict[str, int] = {v: k for k, v in PLATFORM_NAMES.items()}
_KEY_TO_ID: dict[str, int] = {v: k for k, v in PLATFORM_KEYS.items()}


def resolve_platform(name_or_key: str) -> int | None:
    key_lower = name_or_key.lower()
    if key_lower in _KEY_TO_ID:
        return _KEY_TO_ID[key_lower]
    if name_or_key in _NAME_TO_ID:
        return _NAME_TO_ID[name_or_key]
    return None


def get_platform_name(platform_id: int) -> str:
    return PLATFORM_NAMES.get(platform_id, f"未知平台({platform_id})")
