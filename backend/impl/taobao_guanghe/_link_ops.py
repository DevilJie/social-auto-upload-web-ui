"""淘宝光合「关联商品/店铺」DOM 操作工具函数(纯函数,参数为 frame)。

picker.py 和 platform.py 共用同一份 DOM 操作代码,保证选品/发布两条路径行为一致。

设计原则:
- 所有函数都接受 frame 作为第一个参数(发布页 iframe 或主 frame)
- 不持有任何会话状态,纯 DOM 操作
- 失败时抛异常或返回空,由调用方决定如何处理
"""

from __future__ import annotations

import asyncio

# 类型常量
TYPE_PRODUCT = "product"
TYPE_SHOP = "shop"

# tab 常量(商品模式)
TAB_BOUGHT = "bought"
TAB_PREFERRED = "preferred"

# 光合发布页 URL
GUANGHE_PUBLISH_URL = (
    "https://creator.guanghe.taobao.com/page/pubNew/video"
    "?pub_url=https%3A%2F%2Fhuodong.taobao.com%2Fwow%2Fz%2Fguang%2Fgg_publish%2Fgg-video"
    "%3Fugc_scene%3Dpc_newcreator_video%26pageType%3Dvideo%26site%3Dguangguang"
    "&pub_scene=gg"
)


def trace_signature(trace: dict) -> tuple:
    """计算 trace 签名,用于发布时按状态分组复用。

    signature = (tab, keyword, rule, category)
    缺失字段视为空字符串,旧数据/店铺模式也能正常分组。
    """
    return (
        trace.get("tab", ""),
        trace.get("keyword", ""),
        trace.get("rule", ""),
        trace.get("category", ""),
    )
