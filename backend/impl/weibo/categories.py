"""微博视频分类(频道 → 子分类)静态数据。

数据源: 微博上传页 https://weibo.com/upload/channel 的
``/ajax/contribution`` 接口返回的 ``contribution.details`` 结构,
2026-06-15 抓取。共 25 个频道 / 255 个子分类。

随平台调整可能过期,届时重新拉取并覆盖 ``_categories.json`` 即可。
"""

import json
from pathlib import Path
from typing import Optional

_DATA_PATH = Path(__file__).parent / "_categories.json"
with _DATA_PATH.open(encoding="utf-8") as _f:
    _DATA = json.load(_f)

#: 顶层频道列表,顺序与微博页面一致
CHANNELS = _DATA["channels"]


def find_channel(name: str) -> Optional[dict]:
    """按频道名(如 ``"VLOG"`` / ``"生活"``)查找,返回频道 dict 或 None。"""
    for ch in CHANNELS:
        if ch["name"] == name:
            return ch
    return None


def lookup_sub_channel(channel_name: str, sub_name: str) -> Optional[dict]:
    """根据频道名 + 子分类名查找完整记录。

    返回 dict::

        {
            "channel_name": "VLOG",
            "channel_id": "4379162597598697",
            "sub_name": "旅行",
            "sub_channel_id": "4379162597598701",
        }

    找不到时返回 None。
    """
    ch = find_channel(channel_name)
    if not ch:
        return None
    for sc in ch["sub_channels"]:
        if sc["name"] == sub_name:
            return {
                "channel_name": ch["name"],
                "channel_id": ch["channel_id"],
                "sub_name": sc["name"],
                "sub_channel_id": sc["sub_channel_id"],
            }
    return None
