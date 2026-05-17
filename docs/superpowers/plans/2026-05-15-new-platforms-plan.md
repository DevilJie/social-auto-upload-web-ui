# 平台整合实施计划：百家号 + TikTok海外版 + YouTube

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将百家号(id:6)、TikTok海外版(id:7)、YouTube(id:8) 整合到现有系统，前端+后端完整集成。

**Architecture:**
- 后端：上游 `vendor/upstream/uploader/` 已包含 baijiahao、tk youtube_uploader，上游 `myUtils/postVideo.py` 需新增3个post函数
- 前端：`frontend/src/config/platforms.js` 新增3个平台配置
- 新平台ID：百家号=6, TikTok=7, YouTube=8

**Tech Stack:** Python (Flask + Playwright), Vue 3 + Vite + Element Plus

---

## 文件变更总览

| 文件 | 动作 |
|------|------|
| `vendor/upstream/uploader/baijiahao_uploader/main.py` | 已存在（来自上游），后端直接引用 |
| `vendor/upstream/uploader/tk_uploader/main.py` | 已存在（来自上游），后端直接引用 |
| `vendor/upstream/uploader/tk_uploader/main_chrome.py` | 已存在（来自上游） |
| `vendor/upstream/uploader/youtube_uploader/` | **需创建**（从上游克隆，暂未找到，需新建） |
| `vendor/upstream/myUtils/postVideo.py` | 修改：新增3个post函数 |
| `vendor/upstream/sau_backend.py` | 修改：postVideo路由新增3个平台case |
| `backend/app.py` | 修改：PLATFORM_MAP新增3个映射 |
| `frontend/src/config/platforms.js` | 修改：新增BAIJIAHAO、TIKTOK、YOUTUBE配置 |
| `frontend/src/assets/logos/` | 新增：3个SVG logo文件 |

---

## Task 1: 检查/创建 YouTube uploader 目录

**Files:**
- Check: `vendor/upstream/uploader/`
- Create: `vendor/upstream/uploader/youtube_uploader/__init__.py`
- Create: `vendor/upstream/uploader/youtube_uploader/main.py`

- [ ] **Step 1: 检查上游是否有 youtube_uploader 目录**

Run: `ls /home/czy/workspace/ai/social-auto-upload/vendor/upstream/uploader/`
Expected: 确认是否有 youtube 相关目录

- [ ] **Step 2: 如果没有 youtube_uploader，创建目录和基础文件**

由于参考仓库可能没有独立的 YouTube uploader目录，需要参考其他平台（如 bilibili_uploader）的结构创建：
- 基于 `BaseVideoUploader` 创建 YouTube uploader
- 实现 Cookie 认证 + Playwright 自动化上传逻辑

- [ ] **Step 3: Commit**

```bash
git add vendor/upstream/uploader/youtube_uploader/
git commit -m "feat: add youtube uploader scaffold

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Task 2: 新增 postVideo.py 入口函数

**Files:**
- Modify: `vendor/upstream/myUtils/postVideo.py`

- [ ] **Step 1: 读取现有 postVideo.py 末尾**

Run: `tail -20 /home/czy/workspace/ai/social-auto-upload/vendor/upstream/myUtils/postVideo.py`
Expected: 确认文件结尾

- [ ] **Step 2: 新增 post_video_baijiahao 函数**

在 postVideo.py 末尾添加（参考 post_video_ks 格式）:

```python
def post_video_baijiahao(title, files, tags, account_file,
                         enableTimer=False, videos_per_day=1, daily_times=None,
                         start_days=0, thumbnail_path=None, desc='', schedule_time_str=''):
    """百家号视频上传"""
    from uploader.baijiahao_uploader.main import BaijiahaoVideo

    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_path:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = BaijiahaoVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                desc=desc or None,
                thumbnail_path=thumbnail_path,
                headless=False,
            )
            asyncio.run(app.main(), debug=False)
```

- [ ] **Step 3: 新增 post_video_tiktok 函数**

```python
def post_video_tiktok(title, files, tags, account_file,
                      enableTimer=False, videos_per_day=1, daily_times=None,
                      start_days=0, desc='', schedule_time_str=''):
    """TikTok海外版视频上传"""
    from uploader.tk_uploader.main import TikTokVideo

    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = TikTokVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                desc=desc or None,
                headless=False,
            )
            asyncio.run(app.main(), debug=False)
```

- [ ] **Step 4: 新增 post_video_youtube 函数**

```python
def post_video_youtube(title, files, tags, account_file,
                       enableTimer=False, videos_per_day=1, daily_times=None,
                       start_days=0, thumbnail_path=None, desc='', schedule_time_str=''):
    """YouTube视频上传"""
    from uploader.youtube_uploader.main import YouTubeVideo

    account_file = [Path(BASE_DIR / "cookiesFile" / file) for file in account_file]
    files = [Path(BASE_DIR / "videoFile" / file) for file in files]
    if thumbnail_path:
        thumbnail_path = str(Path(BASE_DIR / "videoFile" / thumbnail_path))
    publish_datetimes = _parse_schedule_time(schedule_time_str, len(files), enableTimer, videos_per_day, daily_times, start_days)

    for index, file in enumerate(files):
        for cookie in account_file:
            print(f"视频文件名：{file}")
            print(f"标题：{title}")
            print(f"描述：{desc}")
            print(f"Hashtag：{tags}")
            app = YouTubeVideo(
                title=title,
                file_path=str(file),
                tags=tags or [],
                publish_date=publish_datetimes[index] if isinstance(publish_datetimes, list) else publish_datetimes,
                account_file=str(cookie),
                desc=desc or None,
                thumbnail_path=thumbnail_path,
                headless=False,
            )
            asyncio.run(app.main(), debug=False)
```

- [ ] **Step 5: 更新 sau_backend.py import**

修改 `vendor/upstream/sau_backend.py` 第14行，添加新函数导入：

```python
from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs, post_video_bilibili, post_video_baijiahao, post_video_tiktok, post_video_youtube
```

- [ ] **Step 6: Commit**

```bash
git add vendor/upstream/myUtils/postVideo.py vendor/upstream/sau_backend.py
git commit -m "feat: add post functions for baijiahao, tiktok and youtube

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Task 3: 更新 sau_backend.py postVideo 路由

**Files:**
- Modify: `vendor/upstream/sau_backend.py` (around line 580 and 680)

- [ ] **Step 1: 读取 postVideo 路由中 type==5 的处理逻辑**

Run: `sed -n '570,600p' /home/czy/workspace/ai/social-auto-upload/vendor/upstream/sau_backend.py`
Expected: 显示 type==5 (B站) 的处理代码块

- [ ] **Step 2: 在 postVideo 函数中新增 type==6,7,8 的处理**

在 sau_backend.py 中找到 postVideo 函数，新增：
- `elif platform_type == 6: post_video_baijiahao(...)`
- `elif platform_type == 7: post_video_tiktok(...)`
- `elif platform_type == 8: post_video_youtube(...)`

格式参考现有 type==3,4,5 的处理方式。

- [ ] **Step 3: 同理更新 postVideoBatch 函数**

在 postVideoBatch 函数中添加相同的三条分支。

- [ ] **Step 4: Commit**

```bash
git add vendor/upstream/sau_backend.py
git commit -m "feat: add type 6/7/8 handling in postVideo routes

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Task 4: 更新 backend/app.py PLATFORM_MAP

**Files:**
- Modify: `backend/app.py:58`

- [ ] **Step 1: 修改 PLATFORM_MAP**

Old: `PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站"}`

New:
```python
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube"}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app.py
git commit -m "feat: add 百家号/TikTok/YouTube to PLATFORM_MAP

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Task 5: 创建前端 Logo 文件

**Files:**
- Create: `frontend/src/assets/logos/logo-baijiahao.svg`
- Create: `frontend/src/assets/logos/logo-tiktok.svg`
- Create: `frontend/src/assets/logos/logo-youtube.svg`

- [ ] **Step 1: 创建百家号 logo SVG**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none">
  <circle cx="12" cy="12" r="10" fill="#e64e3a"/>
  <text x="12" y="16" text-anchor="middle" fill="white" font-size="10" font-weight="bold">B</text>
</svg>
```

- [ ] **Step 2: 创建 TikTok logo SVG**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <path d="M19.59 6.69a4.83 4.83 0 01-3.77-4.25V2h-3.45v13.67a2.89 2.89 0 01-2.88 2.5 2.89 2.89 0 01-2.89-2.89 2.89 2.89 0 012.89-2.89c.28 0 .54.04.79.1V9.01a6.34 6.34 0 00-.79-.05 6.34 6.34 0 00-6.34 6.34 6.34 6.34 0 006.34 6.34 6.34 6.34 0 006.33-6.34V9.14a8.16 8.16 0 004.77 1.52V7.02a4.85 4.85 0 01-1-.33z"/>
</svg>
```

- [ ] **Step 3: 创建 YouTube logo SVG**

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ff0000">
  <path d="M23.498 6.186a3.016 3.016 0 00-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 00.502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 002.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 002.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z"/>
</svg>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/assets/logos/logo-baijiahao.svg frontend/src/assets/logos/logo-tiktok.svg frontend/src/assets/logos/logo-youtube.svg
git commit -m "feat: add logos for baijiahao, tiktok and youtube

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Task 6: 更新前端 platforms.js 配置

**Files:**
- Modify: `frontend/src/config/platforms.js`

- [ ] **Step 1: 添加 import 语句**

在现有 import 后添加：
```javascript
import logoBaijiahao from '@/assets/logos/logo-baijiahao.svg'
import logoTiktok from '@/assets/logos/logo-tiktok.svg'
import logoYoutube from '@/assets/logos/logo-youtube.svg'
```

- [ ] **Step 2: 在 PLATFORMS 对象中添加新平台**

在 BILIBILI 之后添加：

```javascript
BAIJIAHAO: {
    id: 6,
    key: 'baijiahao',
    name: '百家号',
    shortName: 'BJH',
    letter: 'B',
    logo: logoBaijiahao,
    color: '#e64e3a',
    bgColor: 'rgba(230, 78, 58, 0.15)',
    cssClass: 'baijiahao',
    creatorUrl: 'https://baijiahao.baidu.com/',
    settingsFields: [
      { key: 'aiContent', label: 'AI生成内容', type: 'switch' },
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
    ],
    defaultSettings: { title: '', description: '', aiContent: false, isOriginal: false },
},
TIKTOK: {
    id: 7,
    key: 'tiktok',
    name: 'TikTok',
    shortName: 'TT',
    letter: 'T',
    logo: logoTiktok,
    color: '#000000',
    bgColor: 'rgba(0, 0, 0, 0.15)',
    cssClass: 'tiktok',
    creatorUrl: 'https://www.tiktok.com/tiktokstudio/upload?lang=en',
    settingsFields: [
      { key: 'aiContent', label: 'AI生成内容', type: 'switch' },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
    ],
    defaultSettings: { title: '', description: '', aiContent: false, scheduleTime: '' },
},
YOUTUBE: {
    id: 8,
    key: 'youtube',
    name: 'YouTube',
    shortName: 'YT',
    letter: 'Y',
    logo: logoYoutube,
    color: '#ff0000',
    bgColor: 'rgba(255, 0, 0, 0.15)',
    cssClass: 'youtube',
    creatorUrl: 'https://studio.youtube.com/',
    settingsFields: [
      { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
      { key: 'aiContent', label: 'AI生成内容', type: 'switch' },
      { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
    ],
    defaultSettings: { title: '', description: '', isOriginal: false, aiContent: false, scheduleTime: '' },
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/config/platforms.js
git commit -m "feat: add baijiahao, tiktok and youtube platforms config

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Task 7: 验证集成

- [ ] **Step 1: 验证后端导入**

Run: `cd /home/czy/workspace/ai/social-auto-upload && python -c "from myUtils.postVideo import post_video_baijiahao, post_video_tiktok, post_video_youtube; print('Import OK')"`
Expected: Import OK (需在 vendor/upstream 目录下运行，或设置 PYTHONPATH)

- [ ] **Step 2: 验证前端 platforms.js 语法**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npm run build 2>&1 | head -30`
Expected: 无语法错误

- [ ] **Step 3: Git status 确认所有变更**

Run: `git status`
Expected: 显示所有新增和修改的文件

---

## 执行方式选择

**Plan complete and saved to `docs/superpowers/plans/2026-05-15-new-platforms-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?