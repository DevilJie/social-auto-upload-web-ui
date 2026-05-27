# 一键启动脚本设计

## 概述

为项目创建跨平台一键启动脚本，自动检测环境、安装依赖、启动服务并显示访问入口。

## 脚本结构

```
项目根目录/
├── start.sh          # Linux + macOS 一键启动
└── start.bat         # Windows 一键启动
```

- `start.sh` 通过 `uname -s` 检测 OS，区分包管理器差异（Linux 用 apt/dnf，macOS 用 brew）
- `start.bat` 使用原生 CMD 命令，不依赖 PowerShell
- 脚本通过自身路径解析项目根目录（`SCRIPT_DIR`），支持从任意目录执行

## 启动流程（6 步）

### Step 1：检查运行时环境

- `python3 --version` → 未安装则提示并退出
- `node --version` && `npm --version` → 未安装则提示并退出
- 仅检查 + 提示，不自动安装运行时

### Step 2：处理端口冲突

- 检查 5409（后端）→ 有进程占用则自动 kill
- 检查 5173（前端）→ 有进程占用则自动 kill
- kill 后再次检查端口，若仍被占用则报错退出
- kill 失败不阻断（进程可能已退出）

### Step 3：准备后端环境

- 检查 `backend/.venv` 是否存在
- 不存在 → `python3 -m venv backend/.venv` → `pip install -r requirements.txt`
- 已存在 → 检查 `backend/` 目录 git 变更
  - 有变更 → `pip install -r requirements.txt`
  - 无变更 → 跳过

### Step 4：准备前端环境

- 检查 `frontend/node_modules` 是否存在
- 不存在 → `npm install`
- 已存在 → 检查 `frontend/` 目录 git 变更
  - 有变更 → `npm install`
  - 无变更 → 跳过

### Step 5：启动服务

- 后端：`cd backend && .venv/bin/python3 app.py`（后台运行，日志输出到 `backend.log`）
- 前端：`cd frontend && npm run dev`（后台运行，日志输出到 `frontend.log`）

### Step 6：等待服务就绪并显示入口

- 轮询 `http://127.0.0.1:5409` 直到响应 200
- 轮询 `http://127.0.0.1:5173` 直到响应 200
- 显示访问入口

```
============================================
  前端界面: http://localhost:5173
  后端 API: http://localhost:5409
============================================
```

## 依赖变更检测

使用 git log 检测目录变更：

- 执行 `git log -1 --format=%H -- frontend/` 获取最近一次 frontend 目录变更的 commit hash
- 与 `.frontend_deps_hash` 文件中记录的上次 hash 对比
- 不同则执行 `npm install` 并更新记录
- 后端同理，检查 `backend/` 目录的 git 变更，记录到 `.backend_deps_hash`

## 错误处理

- 每个关键步骤遇错即停（bash 用 `set -e`，bat 用 `errorlevel`）
- 端口 kill 失败不阻断
- venv 创建或 pip install 失败时输出错误日志并退出
- 前后端启动失败时输出 `backend.log` / `frontend.log` 的最后 20 行
- Ctrl+C 时同时停止前后端进程，避免僵尸进程

## 终端输出风格

```
[1/6] 检查运行时环境...
  ✓ Python 3.12.0
  ✓ Node v20.11.0 / npm 10.2.4

[2/6] 处理端口冲突...
  ✓ 端口 5409 空闲
  ✓ 端口 5173 空闲

[3/6] 准备后端环境 (venv)...
  ✓ venv 已存在，依赖无变更，跳过

[4/6] 准备前端环境 (npm)...
  ✓ 检测到 frontend/ 有新提交，正在 npm install...
  ✓ 依赖安装完成

[5/6] 启动服务...
  ✓ 后端已启动 (PID: 12345)
  ✓ 前端已启动 (PID: 12346)

[6/6] 等待服务就绪...
  ✓ 后端就绪
  ✓ 前端就绪

============================================
  前端界面: http://localhost:5173
  后端 API: http://localhost:5409
============================================
```

## 技术约束

- Python venv 路径：`backend/.venv`
- 依赖 hash 文件：`.frontend_deps_hash`、`.backend_deps_hash`（gitignore）
- 日志文件：`backend.log`、`frontend.log`（gitignore）
- Windows 下 venv 的 Python 路径：`backend\.venv\Scripts\python.exe`
- Unix 下 venv 的 Python 路径：`backend/.venv/bin/python3`
