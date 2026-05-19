# AI Social Auto Upload / AI 社交媒体自动上传

[English](#english) | [中文](#中文)

---

## English

### Project Introduction

A modern **Web-UI interface** for multi-platform social media content auto-publishing. Built on [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) with a completely redesigned frontend, providing a seamless, visual publishing experience across multiple platforms.

### Features

- **多平台支持 / Multi-Platform**: Xiaohongshu (小红书), Douyin (抖音), Bilibili (B站), Kuaishou (快手), WeChat Video (视频号), YouTube
- **批量发布 / Batch Publishing**: Publish to multiple platforms simultaneously in one operation
- **智能账号管理 / Account Management**: Cookie-based authentication, visual login capture via browser automation
- **素材管理 / Material Management**: Unified video/image library with cover editor for Bilibili
- **任务中心 / Task Center**: Real-time publishing status tracking with async task queue
- **定时发布 / Scheduled Publishing**: Calendar-based scheduling for future release
- **浏览器工厂 / Browser Factory**: Auto-fallback from Chrome to Patchright's built-in Chromium when Chrome is unavailable
- **封面编辑器 / Cover Editor**: Visual cover selector with multi-aspect-ratio support for Bilibili
- **跨平台兼容 / Cross-Platform**: Web deployment + Tauri desktop app for Windows

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | Vue 3 + Vite + Element Plus + Pinia + Vue Router |
| Backend | Python Flask + flask-async + Waitress |
| Browser Automation | Patchright + Playwright |
| Desktop | Tauri (Rust) |
| Image Processing | OpenCV |

### Prerequisites

- **Python 3.10+**
- **Node.js 18+**
- **npm** or **yarn**
- **Chrome/Chromium** (optional, Patchright built-in Chromium as fallback)

### Local Development Setup

#### 1. Backend

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start backend server (http://localhost:8000)
python app.py
```

#### 2. Frontend

```bash
cd frontend

npm install

npm run dev
```

#### 3. Access

Open **http://localhost:5173** in your browser.

### Building Desktop App (Windows)

```bash
# Install Rust from https://rustup.rs/

cd src-tauri
cargo tauri build
```

Built executable: `src-tauri/target/release/`

### Building Web Only

```bash
cd frontend
npm run build
```

Output in `frontend/dist/`, deployable to any web server.

---

## 中文

### 项目介绍

现代化的**网页界面**社交媒体自动发布工具。基于 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload) 开发，完全重写了前端交互，提供跨多平台的视觉化发布体验。

### 功能特性

- **多平台支持**：小红书、抖音、B站、快手、视频号、YouTube
- **批量发布**：一次操作，同时发布内容到多个平台
- **智能账号管理**：基于 Cookie 的认证体系，浏览器自动化可视化登录
- **素材管理**：统一的视频/图片素材库，支持 B站封面编辑器
- **任务中心**：实时发布状态追踪，异步任务队列
- **定时发布**：日历式定时排程，灵活设置发布时间
- **浏览器工厂**：Chrome 不可用时自动降级到 Patchright 内置 Chromium
- **封面编辑器**：可视化封面选择，支持 B站多比例画幅
- **跨平台兼容**：Web 部署 + Tauri 桌面应用（Windows）

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite + Element Plus + Pinia + Vue Router |
| 后端 | Python Flask + flask-async + Waitress |
| 浏览器自动化 | Patchright + Playwright |
| 桌面应用 | Tauri (Rust) |
| 图片处理 | OpenCV |

### 准备工作

- **Python 3.10+**
- **Node.js 18+**
- **npm** 或 **yarn**
- **Chrome/Chromium**（可选，Patchright 内置 Chromium 作为备选）

### 本地启动

#### 1. 后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动后端服务 (http://localhost:8000)
python app.py
```

#### 2. 前端

```bash
cd frontend

npm install

npm run dev
```

#### 3. 访问应用

打开浏览器访问：**http://localhost:5173**

### 打包桌面应用（Windows）

```bash
# 从 https://rustup.rs/ 安装 Rust

cd src-tauri
cargo tauri build
```

构建产物：`src-tauri/target/release/`

### 仅构建 Web 版本

```bash
cd frontend
npm run build
```

构建产物在 `frontend/dist/`，可部署到任意 Web 服务器。

---

## 项目结构

```
social-auto-upload-web-ui/
├── frontend/              # Vue 3 前端应用
│   ├── src/
│   │   ├── views/        # 页面组件（仪表盘、账号管理、素材管理等）
│   │   ├── components/    # 通用组件
│   │   ├── router/        # 路由配置
│   │   └── stores/         # Pinia 状态管理
│   └── package.json
├── backend/               # Python Flask 后端
│   ├── app.py            # 主应用入口
│   ├── playwright/       # 浏览器自动化（登录抓取）
│   ├── ext_api/          # 平台 API 集成
│   └── requirements.txt
├── src-tauri/            # Tauri 桌面应用
├── changelog/            # 更新日志
└── data/                 # 工作数据（cookies、日志、视频文件）
```

---

## 许可证 / License

MIT License

---

## Star History

如果这个项目对您有帮助，请给一个 ⭐ Star 以表示支持！

If this project is helpful to you, please give a ⭐ Star to show your support!

[![Star History Chart](https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Timeline)](https://star-history.com/#DevilJie/social-auto-upload-web-ui&Timeline)

---

## 致谢 / Acknowledgments

### 原项目作者 / Original Project Author

[@dreammis](https://github.com/dreammis) - [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload)

<img src="https://github.com/dreammis.png" width="150" height="150" alt="dreammis QR Code" style="border: 1px solid #ddd; border-radius: 8px;">

### 本项目维护者 / Project Maintainer

[@程序员老蔡](https://github.com/DevilJie)

<img src="qrcode.png" width="150" height="150" alt="Maintainer QR Code" style="border: 1px solid #ddd; border-radius: 8px;">