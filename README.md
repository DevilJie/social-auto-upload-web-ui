<div align="center">

# 千帆云递 · QianFan Sync

**一站式多平台社交媒体自动发布工具** · 一个界面，把内容分发到全网

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](./LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.1-42b883.svg)](./changelog)
[![Platforms](https://img.shields.io/badge/platforms-11-ff6b6b.svg)](#-支持平台)
[![Tauri](https://img.shields.io/badge/Tauri-2-FFC131.svg)](https://tauri.app/)

🇨🇳 简体中文 ｜ 🇺🇸 [English](./docs/readme/en_us/README.md)

</div>

---

## 📖 项目简介

**千帆云递（QianFan Sync）** 是一款现代化的多平台社交媒体自动发布工具，专注解决内容创作者「**一份素材、多端分发**」的痛点。

无论你是个人博主、MCN 机构、企业新媒体运营，都需要在 10+ 个平台之间反复切换、重复粘贴上传——千帆云递把这一切收敛到**一个界面**：拖入视频/图集 → 勾选平台与账号 → 填写一次标题/标签/封面 → 一键发布，剩下的交给自动化。

项目源自开源项目 [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload)，在其 Playwright 自动化能力基础上**完全重写了前端交互**，提供可视化、可批量、可定时的发布体验。整体采用 **Vue 3 前端 + Python Flask 后端 + TypeScript MCP 服务** 的三层架构，以本地 Web 服务形式运行，数据全部留在本地。

### ✨ 核心特性

| 能力 | 说明 |
|------|------|
| 🚀 **多平台一键发布** | 支持 11 个国内外主流平台，一次操作同步分发到多个账号 |
| 🏷️ **账号标签体系** | 账号支持多标签管理，按标签/渠道多维度筛选目标账号 |
| 📅 **定时发布** | 日历式排程，支持全量/增量两种批量定时应用模式 |
| 🎬 **视频 + 图集双形态** | 既支持视频发布，也支持图文/图集发布（小红书、抖音等） |
| 🖼️ **可视化封面编辑** | B站封面编辑器、多比例画幅、自动生成缩略图 |
| 📊 **任务中心** | 实时发布状态追踪，异步任务队列，失败重试 |
| 🗂️ **素材中心** | 统一的视频/图片素材库，按平台分类管理 |
| 🛡️ **渠道黑名单** | 全局屏蔽不使用的平台，多端联动过滤 |
| 🔍 **视频校验** | 上传即识别时长/大小，前后端双重校验避免发布失败 |
| 🕵️ **反检测自动化** | CloakBrowser 隐身 Chromium，降低被识别风险 |
| 🤖 **AI Agent 启动** | 支持通过自然语言驱动 AI Agent（如 Claude / ZCode）一键启动项目 |

---

## 🌐 支持平台

目前接入 **11 个**主流平台：

<table>
  <tr>
    <td align="center"><img src="./frontend/src/assets/logos/xiaohongshu.png" width="40" /><br>小红书</td>
    <td align="center"><img src="./frontend/src/assets/logos/shipinhao.png" width="40" /><br>视频号</td>
    <td align="center"><img src="./frontend/src/assets/logos/douyin.png" width="40" /><br>抖音</td>
    <td align="center"><img src="./frontend/src/assets/logos/kuaishou.png" width="40" /><br>快手</td>
    <td align="center"><img src="./frontend/src/assets/logos/bilibili.png" width="40" /><br>哔哩哔哩</td>
    <td align="center"><img src="./frontend/src/assets/logos/baijiahao.png" width="40" /><br>百家号</td>
  </tr>
  <tr>
    <td align="center"><img src="./frontend/src/assets/logos/tiktok.png" width="40" /><br>TikTok</td>
    <td align="center"><img src="./frontend/src/assets/logos/youtube.png" width="40" /><br>YouTube</td>
    <td align="center"><img src="./frontend/src/assets/logos/tengxunshipin.png" width="40" /><br>腾讯视频</td>
    <td align="center"><img src="./frontend/src/assets/logos/aiqiyi.png" width="40" /><br>爱奇艺</td>
    <td align="center"><img src="./frontend/src/assets/logos/weibo.png" width="40" /><br>微博</td>
    <td align="center"></td>
  </tr>
</table>

---

## 🛠️ 技术栈

| 层级 | 技术方案 |
|------|----------|
| **前端** | Vue 3 · Vite · Element Plus · Pinia · Vue Router |
| **后端** | Python Flask · flask-async · Waitress · SQLite |
| **浏览器自动化** | Playwright · CloakBrowser（隐身 Chromium） |
| **MCP 服务** | TypeScript · Model Context Protocol SDK |
| **媒体处理** | OpenCV · FFmpeg / FFprobe |

---

## 📦 下载安装

### 方式一：网盘下载整合包（推荐普通用户）

已将 **Windows / Linux / macOS** 三端的整合包上传到以下网盘，下载解压后双击对应启动脚本即可运行，**无需配置 Python / Node 环境**，内嵌了运行时和隐身浏览器。

**【网盘资源】**

| 网盘 | 地址 | 提取码 |
|------|------|--------|
| ☁️ **夸克网盘** | https://pan.quark.cn/s/43dd01b87817?pwd=aEiz | `aEiz` |
| 🔍 **百度网盘** | https://pan.baidu.com/s/1eWvJX6L74BFd8Bjuy6iQWw?pwd=7cx9 | `7cx9` |

> 📌 各端启动脚本：Windows 用 `start.bat`，Linux 用 `start.sh`，macOS 用 `start-macos.sh`。

### 方式二：从源码构建（开发者）

详见下方 [🚀 本地启动](#-本地启动) 章节。

---

## 🚀 本地启动

### 环境要求

- **Python 3.10+**（使用 `X | Y` union 语法）
- **Node.js 18+**
- **FFmpeg / FFprobe**（视频时长识别与帧抽取）

### 方式一：AI Agent 自然语言启动（推荐 ✨）

推荐使用 AI 编程助手（如 **Claude Code / ZCode / Cursor** 等支持 MCP 或本地终端的 Agent）来启动本项目，**用一句话即可完成全部流程**，无需手动敲命令。

只需在项目根目录对 AI Agent 说：

> 「帮我启动千帆云递项目，安装好依赖，把前后端都跑起来，然后告诉我访问地址。」

AI Agent 会自动完成：清理被占用的端口 → 安装 Python/Node 依赖 → 启动后端 (5409)、前端 (5173)、MCP (5410) → 拉起浏览器并返回访问地址。整个流程全自动，遇到报错还能自我排查重试。

### 方式二：一键脚本启动

项目根目录提供了各平台的一键启动脚本，会自动清理端口、安装依赖、启动三个服务：

```bash
./start.sh          # Linux
./start-macos.sh    # macOS
start.bat           # Windows
```

### 方式三：手动启动

#### 1. 后端（Flask，端口 5409）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                                        # http://localhost:5409
```

#### 2. 前端（Vite，端口 5173）

```bash
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

#### 3. MCP 服务（TypeScript，端口 5410，可选）

```bash
cd backend-mcp
npm install
npm run dev                                          # tsx watch 开发模式
```

#### 4. 访问应用

浏览器打开 **http://localhost:5173** 即可。

> ℹ️ 前端 Vite 已配置代理，所有 `/api`、`/login`、`/upload`、`/postVideo` 等请求会自动转发到 `localhost:5409`。

---

## 📂 项目结构

```
social-auto-upload-web-ui/
├── frontend/              # Vue 3 前端应用
│   └── src/
│       ├── views/         # 页面：发布中心、账号管理、素材中心、仪表盘等
│       ├── components/    # 通用组件
│       ├── api/           # Axios API 层（按模块拆分）
│       ├── stores/        # Pinia 状态管理
│       └── router/        # 路由配置（hash history）
├── backend/               # Python Flask 后端
│   ├── app.py             # 主应用入口
│   ├── impl/              # 平台自动化实现（Registry 模式，按平台分目录）
│   ├── blueprints/        # Flask 蓝图（图集发布、素材、图片发布）
│   ├── ext_api/           # 异步任务队列
│   ├── services/          # 草稿合并、FFmpeg 服务
│   └── init_db.py         # SQLite schema 与迁移
├── backend-mcp/           # TypeScript MCP 服务（对接 LLM / AI Agent）
├── changelog/             # 版本更新日志（HTML）
├── data/                  # 运行时数据（gitignored）：DB、cookies、日志、素材
└── scripts/               # 构建与辅助脚本
```

### 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                 Vue 3 前端  (Element Plus)               │
│   发布中心 · 账号管理 · 素材中心 · 任务中心 · 仪表盘   │
├─────────────────────────────────────────────────────────┤
│              Python Flask 后端 (Waitress)                │
│   路由 · SSE 登录 · 异步任务队列 · SQLite               │
├─────────────────────────────────────────────────────────┤
│        平台自动化层 (Playwright + CloakBrowser)         │
│   小红书 · 抖音 · B站 · 快手 · 视频号 · ...             │
└─────────────────────────────────────────────────────────┘
```

平台实现采用 **Registry 模式**：`backend/impl/registry.py` 维护 platform_id → class 的映射，新增平台只需创建 `impl/<name>/platform.py` 并继承 `BasePlatform` 即可。

---

## 🧪 测试

```bash
cd backend && python -m pytest tests/             # 后端测试
cd backend-mcp && npm test                        # MCP 服务测试（vitest）
```

---

## 📝 更新日志

完整的版本更新日志见 [`changelog/`](./changelog) 目录。

**v0.9.1**（2026.06.21）— 启动时自动补全存量视频时长：扫描数据库中时长为 0 的视频素材，后台逐条识别并写库（本地/S3 统一处理），全程打印进度日志，发布提交时再加一道同步兜底，彻底解决草稿/历史恢复绕过时长识别导致校验失效的问题。

**v0.9.0**（2026.06.19）核心聚焦三大方向：

- 🏷️ **账号标签体系** — 多标签管理、颜色随机、批量设置全链路打通
- 🔍 **视频/图集标签过滤** — 双端接入标签筛选，三栏多选精确定位账号
- ✨ **UI 界面焕新** — 登录弹窗重设计、必填字段标记、三栏布局改造

---

## ⭐ Star History

如果这个项目对你有帮助，欢迎点个 ⭐ Star 支持一下！

<a href="https://star-history.com/#DevilJie/social-auto-upload-web-ui&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Date" />
  </picture>
</a>

---

## 🙏 致谢

本项目基于开源项目二次开发，感谢原项目作者的贡献：

- **原项目作者**：[@dreammis](https://github.com/dreammis) — [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload)

---

## 📄 许可证

[MIT License](./LICENSE)

本项目仅供学习和个人使用，使用者需自行承担因自动化操作产生的一切风险与责任，请遵守各平台的相关使用条款。
