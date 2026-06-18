# 微博平台接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把微博作为第 11 个平台接入到现有 Registry，实现账号登录 / 检查 / 同步 / 打开创作中心 4 个方法，不动 `BasePlatform`、不动路由、不动数据库 schema。

**Architecture:** 复用现有 `BasePlatform` + Registry 模式 + `save_login_result` 统一收尾。差异集中在 (1) login 流程的 `framenavigated` 监听（双事件 enter/exit 解决 popup 误判），(2) 专用 `scrape_weibo_profile`（微博 DOM 用 CSS-in-JS hash class，通用 scraper 失效）。

**Tech Stack:** Python 3.x、Playwright async API、cloakbrowser（Stealth Chromium）、SQLite、Vue 3 + Element Plus（前端）

**参考 Spec:** `docs/superpowers/specs/2026-06-15-weibo-platform-design.md`

---

## 文件清单

| 操作 | 路径 | 责任 |
|---|---|---|
| Create | `backend/impl/weibo/__init__.py` | 空包标记 |
| Create | `backend/impl/weibo/platform.py` | `WeiboPlatform` 类，4 个方法 |
| Modify | `backend/impl/_utils.py` | +`scrape_weibo_profile()`；+`PLATFORM_SYNC_URLS[11]`；+`PLATFORM_SCRAPE_FNS[11]` |
| Modify | `backend/impl/registry.py` | +`(11, ".weibo.platform", "WeiboPlatform")` |
| Modify | `backend/app.py:175-179` | +`PLATFORM_MAP[11] = "微博"`；+`PLATFORM_ID_TO_KEY[11] = "weibo"` |
| Create | `frontend/src/assets/logos/weibo.png` | 微博 logo（占位 PNG，1x1 红色 #E6162D 像素） |
| Modify | `frontend/src/config/platforms.js` | +`PLATFORMS.WEIBO` 条目 |
| Create | `backend/tests/impl/__init__.py` | 空包标记 |
| Create | `backend/tests/impl/test_weibo_platform.py` | 单元测试（注册完整性 + scraper 纯函数 + 抽象方法） |

---

## Task 1: 写 `scrape_weibo_profile` 失败用例测试

**Files:**
- Create: `backend/tests/impl/__init__.py`
- Create: `backend/tests/impl/test_weibo_scraper.py`

- [ ] **Step 1: 创建 `backend/tests/impl/__init__.py`**

```python
"""Tests for individual platform implementations."""
```

- [ ] **Step 2: 创建 `backend/tests/impl/test_weibo_scraper.py`**

```python
"""Unit tests for `scrape_weibo_profile` in backend.impl._utils."""
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl._utils import scrape_weibo_profile  # noqa: E402


def _make_page(evaluate_result=None, evaluate_raises=False):
    """构造一个最小 mock page，scrape_weibo_profile 只需用到 wait_for_load_state / sleep / evaluate。"""
    page = MagicMock()
    page.wait_for_load_state = AsyncMock()
    if evaluate_raises:
        page.evaluate = AsyncMock(side_effect=RuntimeError("boom"))
    else:
        page.evaluate = AsyncMock(return_value=evaluate_result or {})
    return page


def test_scraper_returns_empty_on_evaluate_exception():
    """evaluate 抛异常时返回空字符串。"""
    import asyncio
    page = _make_page(evaluate_raises=True)
    name, avatar = asyncio.run(scrape_weibo_profile(page))
    assert name == ""
    assert avatar == ""


def test_scraper_extracts_sinaimg_avatar():
    """evaluate 返回含 sinaimg.cn 的 img 信息时，avatar 被正确抓出。"""
    import asyncio
    page = _make_page(evaluate_result={
        "name": "",
        "avatar": "https://tvax2.sinaimg.cn/crop.0.0.512.512.180/abc123.jpg",
        "debug": [],
    })
    name, avatar = asyncio.run(scrape_weibo_profile(page))
    assert avatar == "https://tvax2.sinaimg.cn/crop.0.0.512.512.180/abc123.jpg"
```

- [ ] **Step 3: 运行测试，预期 FAIL（`scrape_weibo_profile` 还不存在）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/impl/test_weibo_scraper.py -v
```

Expected:
```
ImportError: cannot import name 'scrape_weibo_profile' from 'impl._utils'
```
或 `ModuleNotFoundError: No module named 'impl._utils'` —— 两种失败形式都说明函数未存在，符合预期。

- [ ] **Step 4: 提交（红）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/tests/impl/__init__.py backend/tests/impl/test_weibo_scraper.py && git commit -m "test(weibo): 新增 scrape_weibo_profile 失败用例"
```

---

## Task 2: 实现 `scrape_weibo_profile` 让 Task 1 的测试通过

**Files:**
- Modify: `backend/impl/_utils.py` —— 在 `scrape_youtube_profile` 之后追加 `scrape_weibo_profile`

- [ ] **Step 1: 在 `backend/impl/_utils.py` 文件末尾追加 `scrape_weibo_profile`**

追加位置：在 `async def scrape_youtube_profile(page):` 函数定义结束之后、文件末尾的 `PLATFORM_SCRAPE_FNS` 字典之前。

```python
async def scrape_weibo_profile(page):
    """Weibo-specific scraper.

    微博创作中心 DOM 使用 CSS-in-JS hash class（如 ``_wrap_1l406_3``），
    通用 JS 注入的 class 选择器会全部失效。本函数依赖两个稳定锚点：
    头像 CDN 域名（sinaimg.cn 系列）+ 头像 img 父容器内的 leaf 文本。

    抓取顺序：
    1. 头像：遍历 <img>，匹配 sinaimg.cn / tvax*.sinaimg.cn 域名，过滤 icon/logo
    2. 昵称：找到头像 <img> 后向上 5 层父容器内查找 leaf span/div 文本，
       用 isValidName 过滤（来自 _SCRAPE_JS 中的同款逻辑）

    失败兜底：返回 ("", "")，由 save_login_result 兜底用户名。

    Returns:
        tuple[str, str]: (user_name, avatar_url)
    """
    # 复用 _SCRAPE_JS 中已写好的 isValidName，避免重新实现
    # 但 isValidName 在 _SCRAPE_JS 内部 closure 里，外部不可见
    # 这里直接重写一份相同语义的过滤函数
    exclude_keywords = (
        "登录", "注册", "密码", "手机", "首页", "上传", "数据", "管理",
        "发布", "创作", "视频", "直播", "消息", "设置", "帮助", "退出",
        "更多", "搜索", "扫码", "关注", "粉丝", "获赞", "作品", "动态",
        "喜欢", "收藏", "共创", "中心", "工具", "服务", "收益", "任务",
        "课程", "通知", "评论", "互动", "权限", "认证", "申请", "开通",
        "绑定", "电商", "带货", "网址", "链接", "复制", "分享", "下载",
        "打开", "全部", "菜单", "内容", "素材", "流量", "分析", "商品",
        "订单", "结算", "功能", "主页", "个人", "专栏", "活动", "热门",
        "推荐", "播放量", "点赞数", "评论数", "转发数", "浏览量", "阅读量",
        "新增", "昨日", "请选择", "请输入", "未知", "微博用户",
    )

    def _is_valid_name(text: str) -> bool:
        if not text or len(text) < 2 or len(text) > 30:
            return False
        for kw in exclude_keywords:
            if kw in text:
                return False
        return True

    name = ""
    avatar = ""

    try:
        await page.wait_for_load_state("domcontentloaded", timeout=5000)
        await asyncio.sleep(2)

        result = await page.evaluate(
            """() => {
                const imgs = [...document.querySelectorAll('img')];
                const cdnHosts = [
                    'sinaimg.cn', 'tvax2.sinaimg.cn', 'tvax1.sinaimg.cn',
                    'wx1.sinaimg.cn', 'wx2.sinaimg.cn', 'wx3.sinaimg.cn',
                    'wx4.sinaimg.cn',
                ];
                const filtered = imgs.filter(img => {
                    const src = img.src || '';
                    const lower = src.toLowerCase();
                    if (!src.startsWith('http')) return false;
                    if (lower.includes('icon') || lower.includes('logo')) return false;
                    if (lower.includes('qrcode') || lower.includes('placeholder')) return false;
                    if (lower.includes('default') || lower.includes('blank')) return false;
                    return cdnHosts.some(h => src.includes(h));
                });
                const avatar = filtered.length ? filtered[0].src : '';

                // 昵称：在第一个头像 img 的父容器树上找 leaf 文本
                let name = '';
                if (filtered.length) {
                    let container = filtered[0].parentElement;
                    for (let i = 0; i < 5 && container; i++) {
                        const leaves = container.querySelectorAll('span, div, p, a');
                        for (const leaf of leaves) {
                            if (leaf.childElementCount > 0) continue;
                            const text = (leaf.textContent || '').trim();
                            if (text && text.length >= 2 && text.length <= 30) {
                                name = text;
                                break;
                            }
                        }
                        if (name) break;
                        container = container.parentElement;
                    }
                }

                return { name, avatar };
            }"""
        )
        avatar = (result.get("avatar") or "").strip()
        candidate = (result.get("name") or "").strip()
        if _is_valid_name(candidate):
            name = candidate
        logger.info(f"[weibo] profile scraped - name={name!r} avatar={avatar[:50] if avatar else 'None'}")
    except Exception as e:
        logger.info(f"[weibo] profile scrape error: {e}")

    return name, avatar
```

- [ ] **Step 2: 运行 Task 1 的测试，预期 PASS**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/impl/test_weibo_scraper.py -v
```

Expected:
```
test_scraper_returns_empty_on_evaluate_exception PASSED
test_scraper_extracts_sinaimg_avatar PASSED
```

- [ ] **Step 3: 提交（绿）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/_utils.py && git commit -m "feat(weibo): 实现 scrape_weibo_profile 专用抓取器"
```

---

## Task 3: 在 `_utils.py` 的两个注册表里加微博条目

**Files:**
- Modify: `backend/impl/_utils.py:549-576` —— `PLATFORM_SYNC_URLS` 与 `PLATFORM_SCRAPE_FNS` 各加一行

- [ ] **Step 1: 在 `PLATFORM_SYNC_URLS` 字典追加第 11 项**

定位到 `PLATFORM_SYNC_URLS = { ... 10: "https://creator.iqiyi.com/", }`，在最后一行尾 `,` 之后追加：

```python
    11: "https://weibo.com/set/index",
```

完整结构：
```python
PLATFORM_SYNC_URLS = {
    1: "https://creator.xiaohongshu.com/",
    2: "https://channels.weixin.qq.com/platform/post/create",
    3: "https://creator.douyin.com/",
    4: "https://cp.kuaishou.com/article/publish/video",
    5: "https://account.bilibili.com/account/home",
    6: "https://baijiahao.baidu.com/builder/rc/home",
    7: "https://www.tiktok.com/",
    8: "https://studio.youtube.com",
    9: "https://mp.v.qq.com/",
    10: "https://creator.iqiyi.com/",
    11: "https://weibo.com/set/index",
}
```

- [ ] **Step 2: 在 `PLATFORM_SCRAPE_FNS` 字典追加第 11 项**

```python
    11: scrape_weibo_profile,     # Weibo
```

完整结构：
```python
PLATFORM_SCRAPE_FNS = {
    1: scrape_user_profile,         # Xiaohongshu
    2: scrape_tencent_profile,      # WeChat Channels
    3: scrape_user_profile,         # Douyin
    4: scrape_user_profile,         # Kuaishou
    5: scrape_bilibili_profile,     # Bilibili
    6: scrape_baijiahao_profile,    # Baijiahao
    7: scrape_user_profile,         # TikTok
    8: scrape_youtube_profile,      # YouTube
    11: scrape_weibo_profile,       # Weibo
}
```

- [ ] **Step 3: 运行所有后端测试，预期无回归**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/ -v 2>&1 | tail -30
```

Expected: 全部测试 PASS（之前的 19 个 + 刚才加的 2 个）。如有失败，回滚本 task 改的 dict，再排查。

- [ ] **Step 4: 提交**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/_utils.py && git commit -m "feat(weibo): 在 PLATFORM_SYNC_URLS / PLATFORM_SCRAPE_FNS 注册 id=11"
```

---

## Task 4: 写 `WeiboPlatform` 类属性 + 抽象方法测试

**Files:**
- Create: `backend/tests/impl/test_weibo_platform.py`

- [ ] **Step 1: 创建 `backend/tests/impl/test_weibo_platform.py`**

```python
"""Unit tests for `WeiboPlatform` class registration and contracts."""
import sys
from pathlib import Path

# 把 backend 目录加进 sys.path（与项目其他测试一致）
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.registry import is_supported, get_platform  # noqa: E402
from app import PLATFORM_MAP, PLATFORM_ID_TO_KEY  # noqa: E402


def test_weibo_platform_class_attributes():
    """WeiboPlatform 的 platform_id/key/name 必须与 spec 一致。"""
    from impl.weibo.platform import WeiboPlatform
    p = WeiboPlatform()
    assert p.platform_id == 11
    assert p.platform_key == "weibo"
    assert p.platform_name == "微博"


def test_weibo_registered_in_registry():
    """Registry 必须能用 id=11 拿到 WeiboPlatform。"""
    assert is_supported(11) is True
    platform = get_platform(11)
    assert platform is not None
    assert platform.__class__.__name__ == "WeiboPlatform"


def test_weibo_platform_mappings_in_app():
    """app.py 的 PLATFORM_MAP / PLATFORM_ID_TO_KEY 必须包含 11。"""
    assert PLATFORM_MAP[11] == "微博"
    assert PLATFORM_ID_TO_KEY[11] == "weibo"


def test_weibo_publish_video_not_implemented():
    """本轮范围外，publish_video 应继承基类抛 NotImplementedError。"""
    from impl.weibo.platform import WeiboPlatform
    p = WeiboPlatform()
    try:
        p.publish_video()
        raised = False
    except NotImplementedError:
        raised = True
    assert raised, "publish_video should raise NotImplementedError in this round"
```

- [ ] **Step 2: 运行测试，预期 FAIL（`WeiboPlatform` 还没创建）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/impl/test_weibo_platform.py -v
```

Expected:
```
ModuleNotFoundError: No module named 'impl.weibo.platform'
```

- [ ] **Step 3: 提交（红）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/tests/impl/test_weibo_platform.py && git commit -m "test(weibo): 新增 WeiboPlatform 注册/契约测试"
```

---

## Task 5: 创建 `WeiboPlatform` 骨架让 Task 4 测试通过

**Files:**
- Create: `backend/impl/weibo/__init__.py`
- Create: `backend/impl/weibo/platform.py`

- [ ] **Step 1: 创建 `backend/impl/weibo/__init__.py`**

```python
"""Weibo platform package."""
```

- [ ] **Step 2: 创建 `backend/impl/weibo/platform.py`（骨架 + login 占位）**

```python
"""Weibo platform implementation — CloakBrowser."""

import asyncio
import os
import threading
from pathlib import Path
from queue import Queue

from conf import BASE_DIR

from .._utils import save_login_result, scrape_weibo_profile
from ..base_platform import BasePlatform
from util._logger import get_channel_logger

logger = get_channel_logger("weibo")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_WEIBO_CREATOR_URL = "https://weibo.com/set/index"
_WEIBO_LOGIN_HOST = "passport.weibo.com"
_WEIBO_LOGIN_PATH = "/sso/signin"


# ======================================================================
# WeiboPlatform
# ======================================================================

class WeiboPlatform(BasePlatform):
    platform_id = 11
    platform_key = "weibo"
    platform_name = "微博"

    # ------------------------------------------------------------------
    # login()
    # ------------------------------------------------------------------

    async def login(self, id: str, status_queue: Queue, account_id=None) -> None:
        """Perform Weibo login by navigating to creator centre and waiting for the
        user to complete the SSO popup.

        Flow:
        1. Open ``weibo.com/set/index``. If unauthenticated, the server redirects
           to ``passport.weibo.com/sso/signin``.
        2. Watch ``main_frame``'s ``framenavigated`` event with two flags:
           ``enter_login`` and ``exit_login``. ``exit_login`` fires when the URL
           leaves passport.weibo.com back to weibo.com/xxx.
        3. Delegate to ``save_login_result`` to scrape profile, save cookie, write DB.
        4. The browser is left open on failure (login_mode=True) so the user can
           see what went wrong.
        """
        enter_login = asyncio.Event()
        exit_login = asyncio.Event()

        async def _on_nav(frame):
            if frame != page.main_frame:
                return
            url = frame.url
            is_login_page = _WEIBO_LOGIN_HOST in url and _WEIBO_LOGIN_PATH in url
            if is_login_page:
                enter_login.set()
            elif enter_login.is_set():
                exit_login.set()

        browser = await self.create_browser(login_mode=True)
        success = False
        try:
            context = await self.create_context(browser)
            try:
                page = await context.new_page()
                page.on(
                    "framenavigated",
                    lambda f: asyncio.create_task(_on_nav(f)),
                )
                await page.goto(_WEIBO_CREATOR_URL)

                # Wait for the user to complete login
                await exit_login.wait()
                logger.info("[weibo] login completion detected")

                await save_login_result(
                    context, page,
                    platform_id=self.platform_id,
                    platform_name=self.platform_name,
                    status_queue=status_queue,
                    scrape_fn=scrape_weibo_profile,
                    account_id=account_id,
                )
                success = True
            finally:
                await context.close()
        finally:
            if success:
                await browser.close()

    # ------------------------------------------------------------------
    # check_cookie()
    # ------------------------------------------------------------------

    async def check_cookie(self, cookie_file: str) -> bool:
        """Return True if the saved cookie file is still valid."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        if not os.path.exists(cookie_path):
            return False

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(_WEIBO_CREATOR_URL, timeout=30000)
                await page.wait_for_load_state("domcontentloaded", timeout=10000)
                await asyncio.sleep(2)

                if _WEIBO_LOGIN_HOST in page.url:
                    logger.info("[weibo] cookie expired, needs re-login")
                    return False

                logger.info("[weibo] cookie valid")
                return True
            except Exception as exc:
                logger.info(f"[weibo] cookie check error: {exc}")
                return False
            finally:
                await context.close()
        finally:
            await browser.close()

    # ------------------------------------------------------------------
    # open_creator_center()
    # ------------------------------------------------------------------

    async def open_creator_center(self, cookie_file: str) -> None:
        """Open the Weibo creator centre in a visible browser window."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        from .._browser import create_browser_sync, create_context_sync

        def _launch():
            browser = create_browser_sync(headless=False)
            try:
                context = create_context_sync(browser, storage_state=cookie_path)
                page = context.new_page()
                page.goto(url)
                try:
                    page.wait_for_event("close", timeout=0)
                except Exception:
                    pass
            finally:
                try:
                    browser.close()
                except Exception:
                    pass

        thread = threading.Thread(target=_launch, daemon=True)
        thread.start()

    # ------------------------------------------------------------------
    # sync_profile()
    # ------------------------------------------------------------------

    async def sync_profile(self, cookie_file: str) -> tuple:
        """Sync profile info (name, avatar) from Weibo creator centre."""
        cookie_path = str(Path(BASE_DIR / "cookiesFile" / cookie_file))
        url = _WEIBO_CREATOR_URL

        browser = await self.create_browser(headless=True)
        try:
            context = await self.create_context(browser, storage_state=cookie_path)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                return await scrape_weibo_profile(page)
            except Exception as e:
                logger.info(f"[weibo] sync profile failed: {e}")
                return "", ""
            finally:
                await context.close()
        finally:
            await browser.close()
```

- [ ] **Step 3: 在 `registry.py` 注册 id=11**

打开 `backend/impl/registry.py`，把 `_populate_registry()` 的 `imports` 列表从：

```python
        (10, ".iqiyi.platform", "IqiyiPlatform"),
```

改为：

```python
        (10, ".iqiyi.platform", "IqiyiPlatform"),
        (11, ".weibo.platform", "WeiboPlatform"),
```

注意原文件 `imports` 列表中每个元组独占一行（已确认）。

- [ ] **Step 4: 运行 Task 4 的测试，预期 PASS**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/impl/test_weibo_platform.py -v
```

Expected:
```
test_weibo_platform_class_attributes PASSED
test_weibo_registered_in_registry PASSED
test_weibo_platform_mappings_in_app FAILED  # ← 预期，本 task 还没改 app.py
test_weibo_publish_video_not_implemented PASSED
```

如果 4 个全 PASS，Task 6 仍然要做（确保 PLATFORM_MAP / PLATFORM_ID_TO_KEY 一并补上），但表明骨架完整。

- [ ] **Step 5: 提交（绿）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/weibo/ backend/impl/registry.py && git commit -m "feat(weibo): 新增 WeiboPlatform 骨架并注册到 registry (id=11)"
```

---

## Task 6: 在 `app.py` 加 `PLATFORM_MAP[11]` 与 `PLATFORM_ID_TO_KEY[11]`

**Files:**
- Modify: `backend/app.py:175-179`

- [ ] **Step 1: 修改 `PLATFORM_MAP`**

打开 `backend/app.py`，定位到 `PLATFORM_MAP = {1: "小红书", ..., 10: "爱奇艺"}`，在 `10: "爱奇艺"` 之后追加 `11: "微博"`：

```python
PLATFORM_MAP = {1: "小红书", 2: "视频号", 3: "抖音", 4: "快手", 5: "B站", 6: "百家号", 7: "TikTok", 8: "YouTube", 9: "腾讯视频", 10: "爱奇艺", 11: "微博"}
```

- [ ] **Step 2: 修改 `PLATFORM_ID_TO_KEY`**

在 `PLATFORM_ID_TO_KEY` 字典的 `10: 'iqiyi',` 之后追加 `11: 'weibo',`：

```python
PLATFORM_ID_TO_KEY = {
    1: 'xiaohongshu', 2: 'channels', 3: 'douyin', 4: 'kuaishou', 5: 'bilibili',
    6: 'baijiahao', 7: 'tiktok', 8: 'youtube', 9: 'tencent_video', 10: 'iqiyi',
    11: 'weibo',
}
```

- [ ] **Step 3: 重跑 Task 4 全部 4 个测试，预期全 PASS**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/impl/test_weibo_platform.py -v
```

Expected:
```
test_weibo_platform_class_attributes PASSED
test_weibo_registered_in_registry PASSED
test_weibo_platform_mappings_in_app PASSED
test_weibo_publish_video_not_implemented PASSED
```

- [ ] **Step 4: 跑全部后端测试，确认无回归**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/ 2>&1 | tail -20
```

Expected: 全 PASS；若有失败，对照原 task 的 commit 排查。

- [ ] **Step 5: 提交**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/app.py && git commit -m "feat(weibo): 在 app.py 的 PLATFORM_MAP / PLATFORM_ID_TO_KEY 加 id=11"
```

---

## Task 7: 前端 `platforms.js` 加 `WEIBO` 条目 + 占位 logo

**Files:**
- Create: `frontend/src/assets/logos/weibo.png`
- Modify: `frontend/src/config/platforms.js:1-19`（imports） + 末尾（PLATFORMS 字典）

- [ ] **Step 1: 创建占位 logo 文件**

由于 logo PNG 二进制不便用 Edit 工具写入，用 Python 一行生成（项目已装 Python 与 Pillow 可能不在依赖中，改用 `printf` 写最小 PNG）：

```bash
# 生成 1x1 像素微博红 #E6162D 的最小合法 PNG（67 字节）
python3 -c "
import struct, zlib, base64
sig = b'\x89PNG\r\n\x1a\n'
ihdr = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
ihdr_chunk = b'IHDR' + ihdr
ihdr_full = struct.pack('>I', len(ihdr)) + ihdr_chunk + struct.pack('>I', zlib.crc32(ihdr_chunk))
# RGB(230, 22, 45) = 微博红 #E6162D
row = b'\x00' + b'\xE6\x16\x2D'
idat_data = zlib.compress(row)
idat_chunk = b'IDAT' + idat_data
idat_full = struct.pack('>I', len(idat_data)) + idat_chunk + struct.pack('>I', zlib.crc32(idat_chunk))
iend_chunk = b'IEND'
iend_full = struct.pack('>I', 0) + iend_chunk + struct.pack('>I', zlib.crc32(iend_chunk))
with open('/home/czy/workspace/ai/social-auto-upload-web-ui/frontend/src/assets/logos/weibo.png', 'wb') as f:
    f.write(sig + ihdr_full + idat_full + iend_full)
print('OK')
"
```

Expected: 输出 `OK`，文件存在。若后续用户能提供真 logo，覆盖即可。

- [ ] **Step 2: 在 `platforms.js` 顶部 import 区追加 logo import**

打开 `frontend/src/config/platforms.js`，在 `import logoIqiyi from '@/assets/logos/aiqiyi.png'` 之后追加：

```js
import logoWeibo from '@/assets/logos/weibo.png'
```

- [ ] **Step 3: 在 `PLATFORMS` 字典中 `IQIYI` 之后追加 `WEIBO` 条目**

打开 `frontend/src/config/platforms.js`，定位到 IQIYI 块的末尾（line 300-303），即：

```js
    defaultSettings: { title: '', description: '', creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '' },
  },
}

// 派生数据
```

把这 4 行用以下内容整体替换（`WEIBO` 块插入在 IQIYI 之后、关闭 `}` 之前）：

```js
    defaultSettings: { title: '', description: '', creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '' },
  },
  WEIBO: {
    id: 11,
    key: 'weibo',
    name: '微博',
    shortName: 'WB',
    letter: 'W',
    logo: logoWeibo,
    color: '#E6162D',
    bgColor: 'rgba(230, 22, 45, 0.15)',
    cssClass: 'weibo',
    creatorUrl: 'https://weibo.com/set/index',
    settingsFields: [
      // 微博账号管理阶段，发布相关字段留空（publish_video 未实现）
    ],
    defaultSettings: { title: '', description: '' },
  },
}

// 派生数据
```

注意 JS 缩进：与上方 `IQIYI: {` 平级使用 2 空格缩进（条目 key、closing `},` 都是 2 空格）。

- [ ] **Step 4: 验证前端构建无语法错误**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build 2>&1 | tail -20
```

Expected: build 成功，无 error。如有 `Failed to resolve import` 表示 logo 路径错。

- [ ] **Step 5: 提交**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add frontend/src/config/platforms.js frontend/src/assets/logos/weibo.png && git commit -m "feat(frontend): 在 platforms.js 加 WEIBO 条目与占位 logo"
```

---

## Task 8: 端到端冒烟（手动 / 浏览器外）

这一步**不需要写代码**，而是 reviewer 跑一次「快速人工检查表」：

- [ ] **Step 1: 跑后端服务，curl 一下账号列表确认平台元数据没坏**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 app.py &
sleep 3
curl -s http://127.0.0.1:5409/getAccounts | python3 -m json.tool | head -20
kill %1
```

Expected: 返回 `code: 200` 与账号列表（应不含 type=11 账号——这是预期；元数据完整性以 Task 6 测试为准）。

- [ ] **Step 2: 启动前端 dev 服务，确认微博入口显示在账号管理页**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run dev &
sleep 5
# 浏览器打开 http://localhost:5173，登录后进「账号管理」页
# 验证微博 logo 红色 "W" 出现在平台列表中
kill %1
```

Expected: 微博出现在账号管理页面平台列表中，可点击（点了之后会真正打开浏览器去微博——这步仅确认元数据，没真账号不用登录）。

- [ ] **Step 3: 最终汇总 commit（如有遗留）**

如果 Step 1-2 期间发现需要小修（比如 cssClass 不在样式表里），按需修一次。预期无修。

---

## 自检摘要

- ✅ 任务粒度：每个 Step 是单动作（2-5 分钟）
- ✅ TDD：Task 1 → 2、Task 4 → 5 都是先红后绿
- ✅ DRY：scraper 写在 `_utils.py` 与 bilibili/tencent 同行；platform.py 与 xiaohongshu 同构
- ✅ YAGNI：不写 publish_video，不写前端发布面板，不写 E2E 浏览器测试
- ✅ 频繁提交：每个 Task 1 个 commit
- ✅ 无占位符：所有代码块完整可执行
