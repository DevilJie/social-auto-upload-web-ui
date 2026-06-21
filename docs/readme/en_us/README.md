<div align="center">

# QianFan Sync · 千帆云递

**One-Stop Multi-Platform Social Media Auto-Publisher** · One interface, distribute everywhere

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](../../../LICENSE)
[![Version](https://img.shields.io/badge/version-0.9.1-42b883.svg)](../../../changelog)
[![Platforms](https://img.shields.io/badge/platforms-11-ff6b6b.svg)](#-supported-platforms)
[![Tauri](https://img.shields.io/badge/Tauri-2-FFC131.svg)](https://tauri.app/)

🇺🇸 English ｜ 🇨🇳 [简体中文](../../../README.md)

</div>

---

## 📖 Project Overview

**QianFan Sync (千帆云递)** is a modern multi-platform social media auto-publishing tool that solves the "post once, publish everywhere" problem for content creators.

Whether you are an individual blogger, an MCN agency, or a corporate social-media operator, you likely bounce between 10+ platforms repeatedly — copy-pasting, re-uploading, re-formatting. QianFan Sync collapses all of that into **one interface**: drop in a video/image set → pick platforms and accounts → fill in title/tags/cover once → hit publish, and let automation handle the rest.

The project is built on top of the open-source project [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload). While keeping its Playwright automation engine, we **completely rewrote the frontend experience** to deliver a visual, batch-capable, schedulable publishing workflow. It adopts a three-layer architecture: **Vue 3 frontend + Python Flask backend + TypeScript MCP service**, runs as a local web service, and keeps all data on your machine.

### ✨ Key Features

| Capability | Description |
|------------|-------------|
| 🚀 **One-click multi-platform publishing** | 11 mainstream platforms supported; publish to multiple accounts in one operation |
| 🏷️ **Account tag system** | Multi-tag management; filter target accounts by tag and channel |
| 📅 **Scheduled publishing** | Calendar-based scheduling with full/incremental batch apply modes |
| 🎬 **Video + Image-set dual mode** | Supports both video publishing and image-set/photo publishing |
| 🖼️ **Visual cover editor** | Bilibili cover editor, multi-aspect-ratio, auto thumbnail generation |
| 📊 **Task center** | Real-time publish status tracking, async task queue, retry on failure |
| 🗂️ **Material center** | Unified video/image library, organized by platform |
| 🛡️ **Channel blacklist** | Globally disable unused platforms, filtered across all modules |
| 🔍 **Video validation** | Duration/size detection on upload, dual front-end/back-end validation |
| 🕵️ **Anti-detection automation** | CloakBrowser stealth Chromium reduces detection risk |
| 🤖 **AI Agent startup** | Start the project with natural language via an AI Agent (e.g. Claude / ZCode) |

---

## 🌐 Supported Platforms

Currently **11** mainstream platforms are integrated:

<table>
  <tr>
    <td align="center"><img src="../../../frontend/src/assets/logos/xiaohongshu.png" width="40" /><br>Xiaohongshu</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/shipinhao.png" width="40" /><br>WeChat Channels</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/douyin.png" width="40" /><br>Douyin</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/kuaishou.png" width="40" /><br>Kuaishou</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/bilibili.png" width="40" /><br>Bilibili</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/baijiahao.png" width="40" /><br>Baijiahao</td>
  </tr>
  <tr>
    <td align="center"><img src="../../../frontend/src/assets/logos/tiktok.png" width="40" /><br>TikTok</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/youtube.png" width="40" /><br>YouTube</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/tengxunshipin.png" width="40" /><br>Tencent Video</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/aiqiyi.png" width="40" /><br>iQIYI</td>
    <td align="center"><img src="../../../frontend/src/assets/logos/weibo.png" width="40" /><br>Weibo</td>
    <td align="center"></td>
  </tr>
</table>

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Vue 3 · Vite · Element Plus · Pinia · Vue Router |
| **Backend** | Python Flask · flask-async · Waitress · SQLite |
| **Browser Automation** | Playwright · CloakBrowser (stealth Chromium) |
| **MCP Service** | TypeScript · Model Context Protocol SDK |
| **Media Processing** | OpenCV · FFmpeg / FFprobe |

---

## 📦 Download & Install

### Option 1: Pre-built bundle via cloud storage (recommended)

Bundled packages for **Windows / Linux / macOS** are available on the cloud drives below. Just download, extract, and run the matching startup script — **no Python / Node setup required**, the runtime and stealth browser are bundled.

**[Cloud Storage Resources]**

| Drive | Link | Passcode |
|-------|------|----------|
| ☁️ **Quark Drive** | https://pan.quark.cn/s/43dd01b87817?pwd=aEiz | `aEiz` |
| 🔍 **Baidu Netdisk** | https://pan.baidu.com/s/1eWvJX6L74BFd8Bjuy6iQWw?pwd=7cx9 | `7cx9` |

> 📌 Startup scripts per OS: Windows → `start.bat`, Linux → `start.sh`, macOS → `start-macos.sh`.

### Option 2: Build from source (developers)

See the [🚀 Local Start](#-local-start) section below.

---

## 🚀 Local Start

### Prerequisites

- **Python 3.10+** (uses `X | Y` union syntax)
- **Node.js 18+**
- **FFmpeg / FFprobe** (video duration detection and frame extraction)

### Option 1: Start via AI Agent in natural language (recommended ✨)

We recommend starting the project with an AI coding assistant (e.g. **Claude Code / ZCode / Cursor** or any Agent that supports MCP or a local terminal). **A single sentence runs the whole pipeline** — no manual commands needed.

Just say this to the AI Agent in the project root:

> "Help me start the QianFan Sync project: install the dependencies, bring up the frontend and backend, then tell me the access URL."

The AI Agent will automatically: free up occupied ports → install Python/Node deps → start the backend (5409), frontend (5173), and MCP (5410) → open the browser and return the access URL. The entire flow is fully automated and can even self-diagnose and retry on errors.

### Option 2: One-click script

A one-click startup script is provided for each OS at the project root. It cleans ports, installs deps, and starts all three services:

```bash
./start.sh          # Linux
./start-macos.sh    # macOS
start.bat           # Windows
```

### Option 3: Manual start

#### 1. Backend (Flask, port 5409)

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py                                        # http://localhost:5409
```

#### 2. Frontend (Vite, port 5173)

```bash
cd frontend
npm install
npm run dev                                          # http://localhost:5173
```

#### 3. MCP service (TypeScript, port 5410, optional)

```bash
cd backend-mcp
npm install
npm run dev                                          # tsx watch (dev mode)
```

#### 4. Open the app

Open **http://localhost:5173** in your browser.

> ℹ️ The Vite dev server proxies all `/api`, `/login`, `/upload`, `/postVideo` requests to `localhost:5409` automatically.

---

## 📂 Project Structure

```
social-auto-upload-web-ui/
├── frontend/              # Vue 3 frontend app
│   └── src/
│       ├── views/         # Pages: publish center, account mgmt, material center, dashboard
│       ├── components/    # Reusable components
│       ├── api/           # Axios API layer (split by module)
│       ├── stores/        # Pinia state management
│       └── router/        # Routing (hash history)
├── backend/               # Python Flask backend
│   ├── app.py             # Main app entry
│   ├── impl/              # Platform automation (Registry pattern, per-platform dirs)
│   ├── blueprints/        # Flask blueprints (image publish, materials, etc.)
│   ├── ext_api/           # Async task queue
│   ├── services/          # Draft merge, FFmpeg service
│   └── init_db.py         # SQLite schema & migrations
├── backend-mcp/           # TypeScript MCP service (LLM / AI Agent integration)
├── changelog/             # Release changelogs (HTML)
├── data/                  # Runtime data (gitignored): DB, cookies, logs, media
└── scripts/               # Build & helper scripts
```

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                 Vue 3 Frontend  (Element Plus)           │
│   Publish center · accounts · materials · tasks · dash  │
├─────────────────────────────────────────────────────────┤
│              Python Flask Backend (Waitress)             │
│   Routes · SSE login · async task queue · SQLite        │
├─────────────────────────────────────────────────────────┤
│       Platform Automation (Playwright + CloakBrowser)   │
│   Xiaohongshu · Douyin · Bilibili · Kuaishou · ...      │
└─────────────────────────────────────────────────────────┘
```

Platform implementations use the **Registry pattern**: `backend/impl/registry.py` maps `platform_id → class`. To add a new platform, create `impl/<name>/platform.py` extending `BasePlatform` and register it.

---

## 🧪 Tests

```bash
cd backend && python -m pytest tests/             # backend tests
cd backend-mcp && npm test                        # MCP service tests (vitest)
```

---

## 📝 Changelog

Full release notes are in the [`changelog/`](../../../changelog) directory.

**v0.9.1** (2026.06.21) — Auto-repair video durations on startup: scans the database for video materials with duration 0, recognizes them one by one in a background thread and writes back to the DB (local/S3 unified), printing progress logs throughout, with an additional synchronous fallback at publish-submit time, fully resolving the issue where draft/history restoration bypasses duration detection and invalidates validation.

**v0.9.0** (2026.06.19) focuses on three directions:

- 🏷️ **Account tag system** — multi-tag management, random colors, full batch-set pipeline
- 🔍 **Video/image-set tag filtering** — tag filtering on both ends, three-column multi-select for precise targeting
- ✨ **UI refresh** — redesigned login dialog, required-field markers, three-column layout

---

## ⭐ Star History

If this project helps you, a ⭐ Star is greatly appreciated!

<a href="https://star-history.com/#DevilJie/social-auto-upload-web-ui&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=DevilJie/social-auto-upload-web-ui&type=Date" />
  </picture>
</a>

---

## 🙏 Acknowledgments

This project is built on top of an open-source project. Many thanks to the original author:

- **Original author**: [@dreammis](https://github.com/dreammis) — [dreammis/social-auto-upload](https://github.com/dreammis/social-auto-upload)

---

## 📄 License

[MIT License](../../../LICENSE)

This project is for learning and personal use only. Users assume all risks and responsibilities arising from automated operations, and must comply with the relevant terms of service of each platform.
