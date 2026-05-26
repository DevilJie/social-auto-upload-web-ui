# 日志打印体系设计

## 1. 概述

重构后端日志系统，实现：
- 统一使用 `logging` 模块，禁止 `print()`
- 所有日志同时写入总日志 `backend.log` 和对应渠道日志文件
- 日志格式统一：`{date} {time} [backend][{channel}] {level:8s} {message}`
- 日志级别可通过 `settings.json` 配置

## 2. 日志文件结构

```
data/logs/{yyyy-MM-dd}/
├── backend.log      ← 所有日志汇总
├── bilibili.log    ← bilibili 渠道日志
├── douyin.log
├── kuaishou.log
├── xiaohongshu.log
├── iqiyi.log
├── tencent_video.log
├── youtube.log
├── baijiahao.log
└── tiktok.log
```

## 3. 日志格式

```
2026-05-26 14:30:15 [backend][bilibili] INFO     uploading: test.mp4
2026-05-26 14:30:15 [backend][douyin]  WARNING  cookie invalid — login page shown
2026-05-26 14:30:15 [backend][backend] INFO     [Startup] Python 3.x.x starting...
```

- `backend` 渠道名用于 backend.py 等非渠道模块的日志

## 4. 日志工具模块

**文件：** `backend/util/_logger.py`

- `init_logger()` — 初始化根 logger，写入 `backend.log` 和所有渠道日志文件，读取 `settings.json` 的 `logLevel` 配置（默认 DEBUG）
- `get_channel_logger(channel_name)` — 返回对应渠道 logger，日志自动带 `[backend][{channel}]` 前缀

**配置项**（`settings.json`）：
```json
{
  "logLevel": "DEBUG"
}
```
可选值：`DEBUG` / `INFO` / `WARNING` / `ERROR`

## 5. 渠道改造

各渠道 `platform.py` 替换 logger 初始化方式：

```python
# 旧
import logging
logger = logging.getLogger(__name__)

# 新
from util._logger import get_channel_logger
logger = get_channel_logger("bilibili")
```

原有 `logger.info(...)` 等调用保持不变。

## 6. 需改造的渠道

- `backend/impl/bilibili/platform.py`
- `backend/impl/douyin/platform.py`
- `backend/impl/kuaishou/platform.py`
- `backend/impl/xiaohongshu/platform.py`（额外移除 `logging.basicConfig()`）
- `backend/impl/iqiyi/platform.py`
- `backend/impl/tencent_video/platform.py`
- `backend/impl/youtube/platform.py`
- `backend/impl/baijiahao/platform.py`
- `backend/impl/tiktok/platform.py`
- `backend/impl/registry.py`
- `backend/impl/_utils.py`
- `backend/impl/_browser.py`
- `backend/impl/channels/platform.py`
- `backend/app.py`
- `backend/ext_api/task_queue.py`
- `backend/init_db.py`

## 7. app.py 特殊处理

`backend/app.py` 中的 startup 日志是后端自身日志（非渠道），应使用 `get_channel_logger("backend")`。

## 8. 实现步骤

1. 新建 `backend/util/__init__.py`
2. 新建 `backend/util/_logger.py`，实现 `init_logger()` 和 `get_channel_logger()`
3. 改造 `app.py`，替换 startup 日志 logger
4. 改造所有渠道 `platform.py`，替换 logger 初始化
5. 移除 `xiaohongshu/platform.py` 的 `logging.basicConfig()`
6. 改造 `registry.py`、`_utils.py`、`_browser.py`、`channels/platform.py`、`task_queue.py`、`init_db.py`