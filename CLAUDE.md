# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

社交媒体自动上传桌面工具，支持 10 个平台：小红书、视频号、抖音、快手、百家号、B站、TikTok、YouTube、腾讯视频、爱奇艺。通过 Tauri 2 打包为 Windows 桌面应用，内嵌 Python 后端和 Vue 前端。

## 架构

**三层结构：** Tauri 桌面壳 → Vue 前端 → Flask API → 平台自动化（Playwright + CloakBrowser）

### 后端 (`backend/`)

- **框架：** Flask，生产环境用 Waitress 托管，端口 5409
- **入口：** `backend/app.py` — 包含大部分路由（文件上传、账号 CRUD、SSE 登录、发布调度），注册两个 Blueprint：`ext_api`（任务队列）和 `frames_bp`（抽帧管理）
- **数据库：** SQLite `data/db/database.db`，schema 在 `backend/init_db.py` 定义，表包括 `user_info`、`file_records`、`publish_tasks`、`publish_logs`、`settings`、`drafts`
- **配置：** `backend/conf.py` — `BASE_DIR` 指向 `data/`（打包模式通过 `SAU_DATA_DIR` 环境变量覆盖），Chrome 路径自动检测
- **日志：** `backend/util/_logger.py` — `get_channel_logger()` 工厂函数

### 平台实现（Registry 模式）

`backend/impl/registry.py` 维护 platform_id → class 的映射，通过延迟导入注册。每个平台在 `backend/impl/<平台名>/platform.py` 中实现，继承 `BasePlatform`（`backend/impl/base_platform.py`）。

**抽象方法：** `login`、`check_cookie`、`open_creator_center`、`sync_profile`、`publish_video`

**平台 ID：** 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺

浏览器自动化通过 `backend/impl/_browser.py` 的 CloakBrowser（隐匿 Chromium）实现。

### 前端 (`frontend/`)

- **框架：** Vue 3 + Vite + Element Plus + Pinia + Vue Router
- **端口：** 5173（dev）
- **主视图：** `PublishCenter.vue`（核心发布界面）、`AccountManagement.vue`、`Dashboard.vue`、`Settings.vue`
- **状态管理：** `frontend/src/stores/`（app.js、account.js、user.js）
- **API 层：** `frontend/src/api/` — 按模块拆分（accounts、drafts、frames、materials、users）

### Tauri 桌面应用 (`src-tauri/`)

- Tauri 2 + Rust，`src-tauri/tauri.conf.json` 配置打包资源（Python 后端、前端 dist、CloakBrowser 二进制）
- `src-tauri/src/lib.rs` — WebView2 检测、数据目录管理、资源同步
- 目标平台：Windows NSIS 安装包

## 常用命令

### 启动前检查

端口被占用时先 kill：
```bash
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
lsof -i :5173 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
```

### 后端

```bash
cd backend && python3 app.py          # 启动开发服务器 (端口 5409)
pip install -r backend/requirements.txt  # 安装 Python 依赖
python backend/init_db.py              # 初始化/迁移数据库
```

### 前端

```bash
cd frontend && npm run dev             # 启动开发服务器 (端口 5173)
cd frontend && npm run build           # 构建生产版本
```

### Tauri 桌面应用

```bash
cd src-tauri && cargo tauri dev        # 开发模式
cd src-tauri && cargo tauri build      # 构建桌面安装包
```

## 开发注意事项

- 后端 `app.py` 是单文件路由（~900 行），新增路由优先考虑放到 Blueprint 中
- 平台实现使用 Registry 模式，新增平台需在 `registry.py` 的 `_populate_registry()` 中注册
- 前端 `PublishCenter.vue` 是最复杂的组件（86KB），修改需谨慎
- 数据目录 `data/` 包含运行时数据（数据库、cookies、视频、日志），不要提交到 git
- 所有 git commit message 必须使用中文
