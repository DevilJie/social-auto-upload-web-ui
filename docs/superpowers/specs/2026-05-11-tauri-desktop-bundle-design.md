# Tauri 桌面应用打包设计

**日期：** 2026-05-11
**项目：** AI Social Auto Upload — Windows 一键安装包

---

## 1. 目标

将整个前后端项目（含 Python 环境、所有依赖）打包成一个 Windows 安装包，用户下载后双击即可运行，无需安装任何额外依赖。

---

## 2. 技术选型

| 组件 | 技术 | 说明 |
|------|------|------|
| 桌面壳 | Tauri 2.x | WebView2 内嵌，无须 Chromium |
| 后端运行时 | Python 3.12 + venv | 绿色解压到安装目录 |
| 后端框架 | Flask | 现有项目不变 |
| 前端构建 | Vite | 现有项目 build 后嵌入 |
| 数据库 | SQLite | 现有项目不变 |
| 安装程序 | Tauri 内置 NSIS | 单文件安装包 |

---

## 3. 架构

```
安装包内容 (Program Files 下)
└── AI Social Auto Upload/
    ├── tauri.exe                    # Tauri 启动器 (~5MB)
    ├── python/                      # Python 3.12 绿色运行时 (~50MB)
    ├── venv/                        # Python 虚拟环境 + 依赖
    ├── backend/                    # 后端代码 (Flask app)
    │   ├── app.py
    │   ├── ext_api/
    │   └── requirements.txt
    ├── frontend-dist/               # 前端构建产物
    └── resources/                   # 静态资源

用户数据目录 (%LOCALAPPDATA%\AI Social Auto Upload\)
├── db/
│   └── database.db                 # SQLite 数据库
├── cookies/                        # 平台账号登录 cookie
└── config.json                     # 用户配置
```

---

## 4. 启动流程

1. **安装**：用户双击 exe → NSIS 安装向导 → 选择安装路径 → 完成
2. **首次启动**：
   - Tauri 进程启动
   - 启动 Python venv 中的 Flask 后端（端口 5409）
   - 等待后端就绪
   - 打开本地 WebView 窗口，加载 `http://localhost:5409`
3. **后续启动**：直接双击桌面快捷方式，流程同上

---

## 5. 关键实现

### 5.1 Python 环境打包

- 使用 `pyinstaller` 或手动 `venv` 打包 Python 运行时
- 依赖通过 `requirements.txt` 预安装
- 后端入口：`python backend/app.py`

### 5.2 Tauri 配置

- `tauri.conf.json` 配置：
  - 窗口标题、大小、图标
  - 启动脚本（shell 调用 Python 后端）
  - 打包目标：`nsis`
- 打包时运行预热脚本：构建前端 + 安装 Python 依赖

### 5.3 数据目录

- 通过 `tauri::api::path` 获取 `%LOCALAPPDATA%` 路径
- 初始化时自动创建 `db/`、`cookies/` 目录
- 运行时后端 `DB_PATH` 指向用户数据目录

### 5.4 启动脚本

```bat
@echo off
cd /d "%~dp0"
start /b python\python.exe -m venv venv
call venv\Scripts\activate.bat
pip install -r backend\requirements.txt
python backend\app.py
```

实际使用 Tauri Rust 代码启动子进程，等待后端就绪后打开窗口。

---

## 6. 构建步骤

1. `cd frontend && npm install && npm run build`
2. `cd backend && python -m venv ../.venv && source ../.venv/bin/activate && pip install -r requirements.txt`
3. `cd .. && npm install -D @tauri-apps/cli`
4. `npx tauri init` — 初始化 Tauri 项目
5. 配置 `src-tauri/tauri.conf.json`
6. 配置 `src-tauri/src/main.rs` 启动逻辑
7. `npx tauri build` — 触发 NSIS 打包

---

## 7. 待确认

- [ ] 图标：是否需要自定义 exe 图标？
- [ ] 自动更新：是否需要内置更新功能？
- [ ] 多平台账号隔离：是否需要支持多用户配置？