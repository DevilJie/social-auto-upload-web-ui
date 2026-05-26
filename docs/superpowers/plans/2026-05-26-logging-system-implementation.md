# 日志打印体系实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构后端日志系统，所有日志写入 `data/logs/{yyyy-MM-dd}/backend.log` 和对应渠道日志文件，格式统一，日志级别可配置。

**Architecture:** 新建 `backend/util/_logger.py` 提供 `init_logger()` 和 `get_channel_logger()`；各渠道 `platform.py` 替换 logger 初始化方式；移除 `xiaohongshu/platform.py` 的独立 `logging.basicConfig()`。

**Tech Stack:** Python logging 模块 + settings.json

---

## 文件结构

```
backend/util/__init__.py      ← 新建
backend/util/_logger.py       ← 新建
backend/app.py                ← 修改
backend/impl/bilibili/platform.py
backend/impl/douyin/platform.py
backend/impl/kuaishou/platform.py
backend/impl/xiaohongshu/platform.py
backend/impl/iqiyi/platform.py
backend/impl/tencent_video/platform.py
backend/impl/youtube/platform.py
backend/impl/baijiahao/platform.py
backend/impl/tiktok/platform.py
backend/impl/registry.py
backend/impl/_utils.py
backend/impl/_browser.py
backend/impl/channels/platform.py
backend/ext_api/task_queue.py
backend/init_db.py
```

---

## Task 1: 创建 `backend/util/__init__.py`

**Files:**
- Create: `backend/util/__init__.py`

- [ ] **Step 1: 创建空文件**

```python
# backend/util/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add backend/util/__init__.py
git commit -m "feat: 创建 util 目录"
```

---

## Task 2: 创建 `backend/util/_logger.py`

**Files:**
- Create: `backend/util/_logger.py`

- [ ] **Step 1: 编写日志工具模块**

```python
import logging
import os
import sys
from datetime import date, datetime
from pathlib import Path

# BASE_DIR = 项目根目录的 backend
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "data" / "logs"

# 渠道列表
CHANNELS = [
    "backend",
    "bilibili",
    "douyin",
    "kuaishou",
    "xiaohongshu",
    "iqiyi",
    "tencent_video",
    "youtube",
    "baijiahao",
    "tiktok",
]

# 日志格式
LOG_FORMAT = "%(asctime)s [backend][%(channel)s] %(levelname)-8s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def _get_log_level() -> int:
    """从 settings.json 读取日志级别，默认 DEBUG"""
    try:
        import json
        settings_file = BASE_DIR / "settings.json"
        if settings_file.exists():
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            level = settings.get("logLevel", "DEBUG").upper()
            return getattr(logging, level, logging.DEBUG)
    except Exception:
        pass
    return logging.DEBUG


def init_logger():
    """初始化根 logger，写入 backend.log 和所有渠道日志文件"""
    log_level = _get_log_level()
    today = date.today()
    day_log_dir = LOGS_DIR / today.strftime("%Y-%m-%d")
    day_log_dir.mkdir(parents=True, exist_ok=True)

    # 避免重复初始化
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.DEBUG)

    for channel in CHANNELS:
        log_file = day_log_dir / f"{channel}.log"
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setLevel(log_level)
        formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # StreamHandler 输出到 stderr，方便控制台查看
    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(log_level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)


def get_channel_logger(channel_name: str) -> logging.Logger:
    """获取指定渠道的 logger，日志自动带 [backend][channel] 前缀"""
    logger = logging.getLogger(channel_name)
    # 通过 adapter 注入 channel 到格式
    class ChannelAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            return msg, kwargs

    adapter = ChannelAdapter(logger, {"channel": channel_name})
    return adapter


# 主动初始化
init_logger()
```

- [ ] **Step 2: Commit**

```bash
git add backend/util/__init__.py backend/util/_logger.py
git commit -m "feat: 添加日志工具模块 util/_logger.py"
```

---

## Task 3: 改造 `backend/app.py`

**Files:**
- Modify: `backend/app.py:17`（替换 startup logger）

- [ ] **Step 1: 修改 app.py 导入和 logger 初始化**

第1步：在 `app.py` 顶部 import 区添加：
```python
from util._logger import get_channel_logger
```

第2步：第17行 `logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("backend")
```

第3步：删除顶部的 `import logging`（如果仅用于 logger 初始化）

- [ ] **Step 2: Commit**

```bash
git add backend/app.py
git commit -m "refactor: app.py 使用 get_channel_logger"
```

---

## Task 4: 改造 bilibili

**Files:**
- Modify: `backend/impl/bilibili/platform.py:19`

- [ ] **Step 1: 替换 logger 初始化**

第1步：导入改为：
```python
from impl._logger import get_channel_logger
```

第2步：`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("bilibili")
```

第3步：删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/bilibili/platform.py
git commit -m "refactor: bilibili 使用渠道 logger"
```

---

## Task 5: 改造 douyin

**Files:**
- Modify: `backend/impl/douyin/platform.py:21`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("douyin")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/douyin/platform.py
git commit -m "refactor: douyin 使用渠道 logger"
```

---

## Task 6: 改造 kuaishou

**Files:**
- Modify: `backend/impl/kuaishou/platform.py:16`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("kuaishou")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/kuaishou/platform.py
git commit -m "refactor: kuaishou 使用渠道 logger"
```

---

## Task 7: 改造 xiaohongshu（额外移除 logging.basicConfig）

**Files:**
- Modify: `backend/impl/xiaohongshu/platform.py:10,14,32`

- [ ] **Step 1: 替换 logger 初始化并移除 basicConfig**

删除第14-15行：
```python
logging.basicConfig(
    level=logging.INFO,
```

同时删除相关的 `stream=sys.stderr` 等配置行。

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("xiaohongshu")
```

删除 `import logging` 和 `import sys`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/xiaohongshu/platform.py
git commit -m "refactor: xiaohongshu 使用渠道 logger，移除独立 logging.basicConfig"
```

---

## Task 8: 改造 iqiyi

**Files:**
- Modify: `backend/impl/iqiyi/platform.py:18`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("iqiyi")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/iqiyi/platform.py
git commit -m "refactor: iqiyi 使用渠道 logger"
```

---

## Task 9: 改造 tencent_video

**Files:**
- Modify: `backend/impl/tencent_video/platform.py:20`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("tencent_video")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/tencent_video/platform.py
git commit -m "refactor: tencent_video 使用渠道 logger"
```

---

## Task 10: 改造 youtube

**Files:**
- Modify: `backend/impl/youtube/platform.py:21`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("youtube")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/youtube/platform.py
git commit -m "refactor: youtube 使用渠道 logger"
```

---

## Task 11: 改造 baijiahao

**Files:**
- Modify: `backend/impl/baijiahao/platform.py:27`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("baijiahao")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/baijiahao/platform.py
git commit -m "refactor: baijiahao 使用渠道 logger"
```

---

## Task 12: 改造 tiktok

**Files:**
- Modify: `backend/impl/tiktok/platform.py:26`

- [ ] **Step 1: 替换 logger 初始化**

导入改为：
```python
from impl._logger import get_channel_logger
```

`logger = logging.getLogger(__name__)` 替换为：
```python
logger = get_channel_logger("tiktok")
```

删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/tiktok/platform.py
git commit -m "refactor: tiktok 使用渠道 logger"
```

---

## Task 13: 改造 registry, _utils, _browser, channels/platform

**Files:**
- Modify: `backend/impl/registry.py:6`
- Modify: `backend/impl/_utils.py:20`
- Modify: `backend/impl/_browser.py:11`
- Modify: `backend/impl/channels/platform.py:16`

- [ ] **Step 1: 替换各文件的 logger 初始化**

各文件都执行：
1. 导入改为 `from impl._logger import get_channel_logger`（如果是 impl 目录下的文件）或 `from util._logger import get_channel_logger`（如果是 backend 根目录文件）
2. `logger = logging.getLogger(__name__)` 替换为 `logger = get_channel_logger("{channel_name}")`
   - registry → "registry"
   - _utils → "utils"
   - _browser → "browser"
   - channels/platform → "channels"
3. 删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/impl/registry.py backend/impl/_utils.py backend/impl/_browser.py backend/impl/channels/platform.py
git commit -m "refactor: registry/_utils/_browser/channels 使用渠道 logger"
```

---

## Task 14: 改造 task_queue 和 init_db

**Files:**
- Modify: `backend/ext_api/task_queue.py:18`
- Modify: `backend/init_db.py:9`

- [ ] **Step 1: 替换 logger 初始化**

task_queue：
- 导入改为 `from util._logger import get_channel_logger`
- `logger = logging.getLogger(__name__)` 替换为 `logger = get_channel_logger("task_queue")`
- 删除 `import logging`

init_db：
- 导入改为 `from util._logger import get_channel_logger`
- `logger = logging.getLogger(__name__)` 替换为 `logger = get_channel_logger("init_db")`
- 删除 `import logging`

- [ ] **Step 2: Commit**

```bash
git add backend/ext_api/task_queue.py backend/init_db.py
git commit -m "refactor: task_queue/init_db 使用渠道 logger"
```

---

## Task 15: 验证日志系统工作正常

**Files:**
- 测试所有渠道的 logger 初始化是否正常

- [ ] **Step 1: 启动后端，检查日志文件是否生成**

```bash
cd backend
python -c "from util._logger import get_channel_logger, init_logger; init_logger(); logger = get_channel_logger('test'); logger.info('test message')"
ls -la data/logs/*/
cat data/logs/*/backend.log
```

预期：`data/logs/{date}/backend.log` 存在且包含 "test message"

- [ ] **Step 2: Commit**

```bash
git add -a
git commit -m "chore: 日志体系实施完成"
```

---

## 自检清单

- [ ] 所有渠道文件都使用了 `get_channel_logger()`
- [ ] `xiaohongshu/platform.py` 的 `logging.basicConfig()` 已移除
- [ ] 无 `print()` 语句引入
- [ ] 日志格式为 `日期 时间 [backend][渠道] 级别 消息`
- [ ] `settings.json` 可配置 `logLevel` 字段
- [ ] `data/logs/{yyyy-MM-dd}/` 目录结构正确