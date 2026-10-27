"""平台数据源接口的进程内 TTL 缓存(合集列表这类低频变化数据)。

背景:部分平台的合集/话题列表接口仍走浏览器 UI 解析(上传测试视频触发
表单渲染),单次 15-60s;而前端下拉每次展开都会调一次接口。对变化频率
极低(天级)的列表数据,进程内 TTL 缓存可让重复展开秒回。

单进程(Waitress)内存缓存,重启即失效 —— 数据源本身就是低频变化数据,
无需持久化。只缓存成功结果,失败不缓存(下次重试)。
"""
from __future__ import annotations

import time

# {key: (expire_at, payload)}
_store: dict = {}

DEFAULT_TTL_SECONDS = 300  # 5 分钟


def get_cached(key: str):
    """命中且未过期返回缓存 payload,否则 None(并清理过期项)。"""
    hit = _store.get(key)
    if hit is None:
        return None
    expire_at, payload = hit
    if time.time() > expire_at:
        _store.pop(key, None)
        return None
    return payload


def set_cached(key: str, payload, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    """写入缓存(只应缓存成功结果)。"""
    _store[key] = (time.time() + ttl, payload)
