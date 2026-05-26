# CLI Mode Design Spec

> 日期: 2026-05-26
> 状态: Draft
> 方案: Direct Import CLI

## 概述

为 social-auto-upload-web-ui 项目新增纯 CLI 模式，作为本地开发者工具替代 Web UI。CLI 直接 import 现有 backend 模块，使用 Typer 框架构建，通过 pip 安装。

## 技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| CLI 框架 | Typer | 类型提示驱动，自动生成 help，Pythonic |
| 终端美化 | Rich | 表格、进度条、颜色、Live 更新 |
| 登录 | 浏览器窗口扫码 | QR 在原始网页最清晰，终端 ASCII 不可靠 |
| 分发 | pip 包 | `pip install sau-cli` 全局安装 |
| 数据存储 | 复用现有 SQLite + data/ 目录 | 与 Web UI 共享数据，零迁移 |

## 架构

```
social-auto-upload-web-ui/
├── backend/          # 现有代码不动
├── frontend/         # 现有代码不动
├── cli/              # 新增 CLI 入口
│   ├── __init__.py
│   ├── main.py       # Typer app 入口 + 根命令
│   ├── commands/     # 各子命令模块
│   │   ├── __init__.py
│   │   ├── login.py      # sau login <platform>
│   │   ├── publish.py    # sau publish <video>
│   │   ├── account.py    # sau accounts <sub>
│   │   ├── material.py   # sau materials <sub>
│   │   ├── draft.py      # sau drafts <sub>
│   │   └── config.py     # sau config <sub>
│   └── output.py         # Rich 输出工具函数
├── pyproject.toml    # 项目配置 + CLI 入口点
└── data/             # 共享数据目录（不变）
```

### 依赖关系

```
cli/  ──import──>  backend.impl.registry    # 平台实现注册表
      ──import──>  backend.impl._browser    # CloakBrowser 封装
      ──import──>  backend.impl._utils      # 共享工具函数
      ──import──>  backend.init_db          # 数据库初始化
      ──import──>  backend.conf             # 配置加载
      ──import──>  backend.ext_api.task_queue  # 任务队列逻辑
```

CLI 不启动 Flask 服务器，不使用 HTTP，直接调用 Python 函数。

## 命令设计

### `sau login <platform>`

扫码登录指定平台。

**流程：**
1. 校验平台名称，解析为平台 ID
2. 调用 `backend.impl.registry.get_platform(platform_id)` 获取平台实现
3. 调用 `platform.login()` 启动 CloakBrowser 可见窗口
4. 终端显示 Rich 进度指示器 "请用手机扫码登录..."
5. 平台实现内部轮询检测登录成功（URL 变化）
6. 成功后：抓取昵称/头像 → 保存 cookie 到 `data/cookiesFile/` → 写入 `user_info` 表
7. 终端显示绿色确认信息

**输出：**
```
$ sau login douyin
🔐 正在打开抖音登录页面...

请用手机抖音扫描浏览器中的二维码登录
⠋ 等待扫码... (Ctrl+C 取消)

✅ 登录成功: 用户昵称 (抖音)
   Cookie 已保存，可开始发布
```

**注意：** 需要适配现有 `login()` 方法，目前它依赖 Flask SSE 流式响应。CLI 场景下需要直接调用核心逻辑，绕过 SSE。

### `sau accounts`

账号管理子命令组。

#### `sau accounts list`

列出所有账号，Rich 表格展示。

```
$ sau accounts list
  ID   平台       昵称         状态
  ─── ────────── ──────────── ──────
  1    抖音       用户A        ✅ 有效
  2    小红书     用户B        ❌ 过期
  3    B站        用户C        ✅ 有效
```

#### `sau accounts check <account_id>`

检查指定账号 cookie 有效性。调用 `platform.check_cookie()`。

#### `sau accounts sync <account_id>`

同步账号昵称/头像。调用 `platform.sync_profile()`。

#### `sau accounts delete <account_id>`

删除账号及其 cookie 文件。需二次确认。

### `sau publish <video_path>`

发布视频到指定平台/账号。

**参数：**
| 参数 | 必填 | 说明 |
|------|------|------|
| `video_path` | 是 | 视频文件本地路径 |
| `--title` | 是 | 视频标题 |
| `--desc` | 否 | 视频描述 |
| `--tags` | 否 | 标签，逗号分隔 |
| `--cover` | 否 | 封面图路径 |
| `--platforms` | 否 | 目标平台，逗号分隔（不指定则需 `--accounts`） |
| `--accounts` | 否 | 指定账号 ID，逗号分隔 |
| `--schedule` | 否 | 定时发布时间 "YYYY-MM-DD HH:MM" |
| `--draft` | 否 | 仅保存为草稿，不实际发布 |
| `--settings` | 否 | 平台特定设置 `key=value,key2=value2` |

**逻辑：**
1. 校验视频文件存在
2. 校验平台/账号有效
3. 如果指定 `--platforms`，查找该平台所有有效账号
4. 如果指定 `--accounts`，使用指定账号
5. 如果 `--draft`，保存到 `drafts` 表并退出
6. 遍历 (平台, 账号) 组合，调用 `platform.publish_video()`
7. Rich Live 实时更新状态表格
8. 完成输出摘要

**输出：**
```
$ sau publish demo.mp4 --title "测试视频" --platforms douyin

📤 正在发布到 抖音 (2个账号)...

  账号             状态        耗时
  ─────────────── ────────── ──────
  用户A            ✅ 成功     32s
  用户B            ❌ 失败     15s    Cookie 过期

发布完成: 1 成功, 1 失败
```

**错误处理：**
- 视频文件不存在 → 红色错误提示
- 无有效账号 → 黄色警告 "请先登录"
- 部分失败 → 继续其余账号，最终汇总
- 单账号失败详情 → 显示平台返回的错误信息

### `sau materials`

素材管理子命令组。

#### `sau materials upload <file_path>`

上传文件到 `data/videoFile/`，写入 `file_records` 表。

#### `sau materials list`

列出所有素材，Rich 表格（ID、文件名、大小、上传时间）。

#### `sau materials delete <file_id>`

删除素材文件 + 数据库记录。需二次确认。

### `sau drafts`

草稿箱子命令组。

#### `sau drafts list`

列出所有草稿，Rich 表格。

#### `sau drafts show <draft_id>`

显示草稿完整配置（标题、描述、标签、平台设置等）。

#### `sau drafts publish <draft_id>`

从草稿发布。读取草稿配置 → 调用发布流程。

#### `sau drafts delete <draft_id>`

删除草稿。需二次确认。

### `sau config`

配置管理子命令组。

#### `sau config init`

首次使用初始化。创建 `data/` 目录结构 + SQLite 数据库。

#### `sau config show`

显示当前配置（数据目录、代理地址、浏览器状态）。

#### `sau config set <key> <value>`

设置配置项（proxy_url 等）。

## 关键实现细节

### 1. 适配 Login 方法

现有 `platform.login()` 方法依赖 Flask SSE 响应（`yield` 生成器）。

**选定方案：** 给 `login()` 方法增加可选回调参数 `on_qr_ready: Callable[[str], None]` 和 `on_status: Callable[[str], None]`。

- **Web UI 调用：** 保持现有 SSE 逻辑不变（回调参数为 None 时走原有 yield 路径）。
- **CLI 调用：** 传入回调函数，回调中用 Rich 打印状态到终端。

这样只修改 login() 的签名，不改行为逻辑，Web UI 零影响。

### 2. 数据目录发现

按以下顺序查找数据目录：
1. `--data-dir` 命令行参数
2. `SAU_DATA_DIR` 环境变量
3. 项目根目录下的 `data/`（开发模式）
4. `~/.sau/data/`（默认用户数据目录）

### 3. Pyproject.toml 入口点

```toml
[project]
name = "sau-cli"
version = "0.1.0"

[project.scripts]
sau = "cli.main:app"

[project.optional-dependencies]
cli = ["typer>=0.12", "rich>=13.0"]
```

### 4. 与 Web UI 数据共享

CLI 和 Web UI 共享同一个 SQLite 数据库和 `data/` 目录。可以同时使用，数据互通。但同一账号的并发发布需要考虑锁机制（复用现有 task_queue 的并发控制）。

## 不包含在本次范围

- 终端 ASCII 二维码登录（后续可加）
- 远程服务器模式（方案 2 的能力）
- 视频帧提取 CLI（可后续扩展 `sau frames <video>`）
- 自动更新/版本管理
- Shell 自动补全生成（Typer 支持，但后续再加）
- 配置文件模板导入/导出
