# 快手图文发布对接 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `KuaishouPlatform` 上实现 `publish_image()`，让快手图文（?tabType=2）发布可走与抖音图文同款流程，并补齐前端面板的「作者声明/定时发布/音乐选择」三块。

**Architecture:** 复用视频发布的 browser/ant-select/ant-picker helpers，仅新增 4 个方法到 `KuaishouPlatform`（publish_image + _upload_image_note + _set_image_cover + _set_image_music）；新建 `kuaishou_image_bp.py` 提供 `/music-search` 浏览器拦截接口；前端镜像 `douyin/MusicSelect.vue` 的搜索控件。

**Tech Stack:** Python 3 + Flask + Playwright (CloakBrowser) + Vue 3 + Element Plus

**Spec:** `docs/superpowers/specs/2026-06-03-kuaishou-image-publish-design.md`

---

## 文件结构

**新建**
- `backend/blueprints/kuaishou_image_bp.py` — 音乐搜索接口（~150 行）
- `frontend/src/api/kuaishouImage.js` — 前端 API 包装（~15 行）
- `frontend/src/components/kuaishou/MusicSelect.vue` — 音乐选择控件（~200 行）

**修改**
- `backend/impl/kuaishou/platform.py` — 加 publish_image + 3 helpers（视频流程不动）
- `backend/blueprints/image_publish_bp.py` — 调 `publish_image` 时补 3 个新字段
- `backend/app.py` — 注册新 blueprint
- `frontend/src/components/kuaishou/ImagePublishPanel.vue` — 加 3 个新控件

---

## Task 1: 创建 kuaishou_image_bp 骨架 + 注册到 app.py

**Files:**
- Create: `backend/blueprints/kuaishou_image_bp.py`
- Modify: `backend/app.py` (在 line 65 之后插入一行)

- [ ] **Step 1: 写 blueprint 骨架（含一个 `/ping` 探活端点 + `_get_cookie_path`/`_get_account_cookie_file`/`run_async` 工具）**

在 `backend/blueprints/kuaishou_image_bp.py` 写入：

```python
"""
快手图文发布相关 API 代理
使用 CloakBrowser 拦截音乐搜索接口。
"""

import asyncio
import json
import sqlite3
from pathlib import Path

from flask import Blueprint, request, jsonify

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conf import BASE_DIR
from util._logger import get_channel_logger
from impl._browser import create_browser, create_context

logger = get_channel_logger("kuaishou_image")

kuaishou_image_bp = Blueprint('kuaishou_image', __name__, url_prefix='/api/kuaishou-image')


def _get_cookie_path(cookie_file: str) -> str:
    return str(Path(BASE_DIR / "cookiesFile" / cookie_file))


def _get_account_cookie_file(account_id: str) -> str | None:
    conn = sqlite3.connect(str(Path(BASE_DIR / "db" / "database.db")))
    cursor = conn.cursor()
    if account_id:
        cursor.execute("SELECT filePath FROM user_info WHERE id = ?", (account_id,))
    else:
        cursor.execute("SELECT filePath FROM user_info WHERE type = 4 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    return row[0]


def run_async(coro):
    """在同步 Flask 上下文里跑 async 协程。"""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return asyncio.run(coro)
    except RuntimeError:
        pass
    return asyncio.run(coro)


@kuaishou_image_bp.route('/ping', methods=['GET'])
def ping():
    return jsonify({"code": 200, "msg": "kuaishou-image bp ok"})
```

- [ ] **Step 2: 在 app.py 注册 blueprint**

修改 `backend/app.py` line 65 之后（`materials_bp` 注册之后）插入：

```python
from blueprints.kuaishou_image_bp import kuaishou_image_bp  # noqa: E402
app.register_blueprint(kuaishou_image_bp)
logger.info("[Startup] kuaishou_image_bp registered OK")
```

- [ ] **Step 3: 验证可导入且 blueprint 注册成功**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "from blueprints.kuaishou_image_bp import kuaishou_image_bp; print('OK')"
```

期望输出：`OK`

- [ ] **Step 4: 验证 /ping 端点**

启动后端：

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend
python3 app.py &
sleep 3
curl -s http://localhost:5409/api/kuaishou-image/ping
```

期望：`{"code":200,"msg":"kuaishou-image bp ok"}`

然后停掉：

```bash
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
```

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/blueprints/kuaishou_image_bp.py backend/app.py
git commit -m "feat(后端): 新增 kuaishou_image_bp 骨架并注册到 app"
```

---

## Task 2: 实现 _search_music_via_browser（浏览器拦截 music-search）

**Files:**
- Modify: `backend/blueprints/kuaishou_image_bp.py`

参考 `backend/blueprints/douyin_image_bp.py` 的 `_search_music_via_browser`（line 286 起），但适配快手：导航到 `?tabType=2`，使用 `_search-input_19mmt_16` 类名 + placeholder "搜索音乐"，拦截 URL `https://cp.kuaishou.com/rest/cp/works/atlas/pc/upload/music/search`。

- [ ] **Step 1: 在 blueprint 中追加 `search_music` endpoint + `_search_music_via_browser` 实现**

在 `backend/blueprints/kuaishou_image_bp.py` 末尾追加：

```python
KUAIHOU_MUSIC_SEARCH_URL = "https://cp.kuaishou.com/rest/cp/works/atlas/pc/upload/music/search"


@kuaishou_image_bp.route('/music-search', methods=['GET'])
def search_music():
    """搜索音乐 - 通过浏览器拦截网络请求获取结果"""
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '20')

    logger.info(f"[音乐搜索] 收到请求: account_id={account_id}, keyword={keyword}, count={count}")

    if not keyword:
        return jsonify({"code": 400, "msg": "缺少keyword参数"}), 400

    try:
        cookie_file = _get_account_cookie_file(account_id)
        if not cookie_file:
            return jsonify({"code": 404, "msg": "没有可用的快手账号"}), 404

        result = run_async(_search_music_via_browser(cookie_file, keyword, count))
        if result.get("success"):
            return jsonify({"code": 200, "data": result["data"]})
        return jsonify({"code": 500, "msg": result.get("error", "请求失败")}), 500
    except Exception as e:
        logger.error(f"[音乐搜索] 异常: {e}", exc_info=True)
        return jsonify({"code": 500, "msg": str(e)}), 500


async def _search_music_via_browser(cookie_file: str, keyword: str, count: str = "20") -> dict:
    """用 CloakBrowser 打开图文发布页 → 上传测试图 → 等详情页 → 打开音乐抽屉 → 输入关键词 → 拦截 music-search API 响应。"""
    cookie_path = _get_cookie_path(cookie_file)

    # 测试图 fallback
    test_image = Path(BASE_DIR / "test_kuaishou_music_search.jpg")
    if not test_image.exists():
        try:
            from PIL import Image
            img = Image.new('RGB', (1, 1), color='red')
            img.save(str(test_image), 'JPEG')
        except ImportError:
            test_image.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00')

    browser = await create_browser(headless=True)
    try:
        context = await create_context(browser, storage_state=cookie_path)
        try:
            page = await context.new_page()

            captured = None

            async def handle_response(response):
                nonlocal captured
                if KUAIHOU_MUSIC_SEARCH_URL in response.url:
                    try:
                        data = await response.json()
                        captured = data
                    except Exception as e:
                        logger.error(f"[拦截] 解析失败: {e}")

            page.on("response", handle_response)

            # 1. 打开图文发布页
            logger.info("打开快手图文发布页...")
            await page.goto(
                "https://cp.kuaishou.com/article/publish/video?tabType=2",
                wait_until="domcontentloaded", timeout=60000,
            )
            await asyncio.sleep(2)

            # 2. 上传测试图
            logger.info("上传测试图...")
            upload_btn = page.locator("button[class^='_upload-btn']").first
            await upload_btn.wait_for(state="visible", timeout=10000)
            async with page.expect_file_chooser() as fc_info:
                await upload_btn.click()
            fc = await fc_info.value
            await fc.set_files(str(test_image))
            await asyncio.sleep(2)

            # 3. 等待详情页
            start = asyncio.get_event_loop().time()
            while (asyncio.get_event_loop().time() - start) < 60:
                if "publish/video" not in page.url:
                    break
                await asyncio.sleep(1)
            await asyncio.sleep(3)

            # 4. 点击「添加音乐」label
            logger.info("点击「添加音乐」...")
            music_label = page.get_by_text("添加音乐", exact=True).first
            await music_label.wait_for(state="visible", timeout=10000)
            await music_label.click()
            await asyncio.sleep(2)

            # 5. 等待 drawer
            drawer = page.locator('div.ant-drawer-content-wrapper:visible').first
            await drawer.wait_for(state="visible", timeout=10000)
            await asyncio.sleep(1)

            # 6. 在搜索框输入
            logger.info(f"输入关键词: {keyword}")
            search_input = drawer.locator("input._search-input_19mmt_16, input[placeholder='搜索音乐']").first
            await search_input.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(keyword)
            await asyncio.sleep(4)  # 等接口响应

            # 7. 拿到 captured
            if not captured:
                return {"success": False, "error": "未捕获到音乐搜索响应"}

            music_list = (captured.get("data") or {}).get("musicList", [])
            result = {
                "musicList": [
                    {
                        "musicId": item.get("musicId", ""),
                        "title": item.get("title", ""),
                        "author": item.get("author", ""),
                        "duration": int(item.get("duration", 0)) // 1000,
                        "cover": (item.get("cover") or [{}])[0].get("url", ""),
                    }
                    for item in music_list
                ],
                "has_more": False,
                "cursor": "0",
            }
            return {"success": True, "data": result}
        finally:
            await context.close()
    finally:
        await browser.close()
```

- [ ] **Step 2: 验证 import 不报错**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "from blueprints.kuaishou_image_bp import _search_music_via_browser, search_music; print('OK')"
```

期望：`OK`

- [ ] **Step 3: 启动后端，触发 /music-search 端点（用真实快手账号）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend
python3 app.py &
sleep 3
# 把快手账号 id 替换成你的真实 id
curl -s "http://localhost:5409/api/kuaishou-image/music-search?account_id=1&keyword=测试"
```

期望：返回 200 + `data.musicList` 数组（如 cookie 失效会返回 500/404，这是正常的）

停掉：

```bash
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
```

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/blueprints/kuaishou_image_bp.py
git commit -m "feat(后端): 快手音乐搜索接口 + 浏览器拦截"
```

---

## Task 3: KuaishouPlatform 加 publish_image 入口

**Files:**
- Modify: `backend/impl/kuaishou/platform.py` (在 `publish_video` 之前追加)

- [ ] **Step 1: 写 publish_image 入口（仅参数解析 + 账号循环；具体流程 _upload_image_note 留 TODO）**

在 `backend/impl/kuaishou/platform.py` 的 `_publish_video_async` 之前，**`publish_video` 之前**插入：

```python
    # ------------------------------------------------------------------
    # Publish image — image note upload pipeline
    # ------------------------------------------------------------------

    async def publish_image(self, **kwargs) -> bool:
        """Publish an image note to Kuaishou via CloakBrowser.

        Accepted keyword arguments:

        - ``title`` (*str*) -- note title (will be prepended to description)
        - ``files`` (*list[str]*) -- image absolute file paths
        - ``tags`` (*list[str]*) -- hashtags
        - ``account_file`` (*list[str]*) -- cookie file names
        - ``desc`` (*str*, optional) -- description
        - ``cover_path`` (*str*, optional) -- cover image absolute path
        - ``author_declaration`` (*str*, optional) -- 作者声明 option text
        - ``music_id`` (*str*, optional) -- 音乐 ID
        - ``music_title`` (*str*, optional) -- 音乐标题（用于搜索匹配）
        - ``enableTimer`` (*bool*, optional)
        - ``schedule_time_str`` (*str*, optional)
        - ``activities`` (*list[str]*, optional) -- official activities
        - ``dry_run`` (*bool*, optional) -- skip publish click (default True)
        """
        title = kwargs.get("title", "")
        files = kwargs.get("files", []) or []
        tags = kwargs.get("tags", []) or []
        account_file = kwargs.get("account_file", []) or []
        desc = kwargs.get("desc", "")
        cover_path = kwargs.get("cover_path", "")
        author_declaration = kwargs.get("author_declaration", "")
        music_id = kwargs.get("music_id", "")
        music_title = kwargs.get("music_title", "")
        enable_timer = kwargs.get("enableTimer", False)
        schedule_time_str = kwargs.get("schedule_time_str", "")
        activities = kwargs.get("activities", []) or []
        dry_run = kwargs.get("dry_run", True)

        account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
        file_paths = [str(f) for f in files]

        if cover_path and not Path(cover_path).is_file():
            logger.warning("Cover file not found: %s", cover_path)
            cover_path = ""

        if activities:
            activity_tags = " ".join([f"#{act}" for act in activities])
            desc = f"{desc} {activity_tags}".strip()

        for cookie_path in account_paths:
            await self._upload_image_note(
                title=title,
                file_paths=file_paths,
                tags=tags,
                account_file=cookie_path,
                desc=desc,
                cover_path=cover_path,
                author_declaration=author_declaration,
                music_id=music_id,
                music_title=music_title,
                enable_timer=enable_timer,
                schedule_time_str=schedule_time_str,
                dry_run=dry_run,
            )
        return True

    async def _upload_image_note(
        self, *, title, file_paths, tags, account_file, desc="", cover_path="",
        author_declaration="", music_id="", music_title="",
        enable_timer=False, schedule_time_str="", dry_run=True,
    ):
        """Upload image note to one Kuaishou account. Implemented in Task 4+."""
        raise NotImplementedError("_upload_image_note: pending Task 4+")
```

- [ ] **Step 2: 验证 import 成功 + 方法存在**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "
from impl.kuaishou.platform import KuaishouPlatform
p = KuaishouPlatform()
assert hasattr(p, 'publish_image'), 'publish_image missing'
assert hasattr(p, '_upload_image_note'), '_upload_image_note missing'
print('OK')
"
```

期望：`OK`

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/impl/kuaishou/platform.py
git commit -m "feat(后端): KuaishouPlatform.publish_image 入口（流程占位）"
```

---

## Task 4: 实现 _upload_image_note 框架（goto/上传/重定向/描述填写）

**Files:**
- Modify: `backend/impl/kuaishou/platform.py`（替换 `_upload_image_note` 占位实现）

- [ ] **Step 1: 实现 _upload_image_note 前半段（goto → 上传 → 等重定向 → 填描述+标签）**

把 Task 3 占位的 `raise NotImplementedError(...)` 替换为：

```python
    async def _upload_image_note(
        self, *, title, file_paths, tags, account_file, desc="", cover_path="",
        author_declaration="", music_id="", music_title="",
        enable_timer=False, schedule_time_str="", dry_run=True,
    ):
        """Upload image note to one Kuaishou account."""
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(browser, storage_state=account_file)
            try:
                page = await context.new_page()

                # 1. 打开图文 tab
                logger.info("Navigating to Kuaishou image upload page")
                await page.goto(
                    "https://cp.kuaishou.com/article/publish/video?tabType=2",
                    wait_until="domcontentloaded", timeout=60000,
                )
                await page.wait_for_url(
                    "**/article/publish/video?tabType=2**", timeout=60000,
                )
                await asyncio.sleep(2)

                # 2. 上传图片（file chooser 多选）
                logger.info("Uploading %d images", len(file_paths))
                upload_btn = page.locator("button[class^='_upload-btn']")
                await upload_btn.wait_for(state="visible", timeout=10000)
                async with page.expect_file_chooser() as fc_info:
                    await upload_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(file_paths)
                await asyncio.sleep(2)

                # 3. 等详情页
                logger.info("Waiting for redirect to detail page...")
                start = asyncio.get_event_loop().time()
                while (asyncio.get_event_loop().time() - start) < 120:
                    if "publish/video" not in page.url:
                        logger.info("Redirected to: %s", page.url)
                        break
                    await asyncio.sleep(1)
                else:
                    logger.warning("Redirect timeout")
                await asyncio.sleep(3)

                # 4. 关闭引导弹层
                await self._close_guide_overlay(page)

                # 5. 填描述（标题拼首行 + 描述 + 标签）
                full_desc = f"{title}\n\n{desc}" if title else desc
                logger.info("Filling description: %s", full_desc[:50])
                desc_editor = page.locator("#work-description-edit").first
                await desc_editor.wait_for(state="visible", timeout=15000)
                await desc_editor.click()
                await page.keyboard.press("Control+KeyA")
                await page.keyboard.press("Delete")
                await page.keyboard.type(full_desc[:500])
                for tag in (tags or [])[:3]:
                    await page.keyboard.type(f" #{tag}")
                    await page.keyboard.press("Space")
                await asyncio.sleep(0.5)

                logger.info("Description filled. cover_path=%s, music_id=%s", cover_path, music_id)
            finally:
                await context.close()
        finally:
            await browser.close()
```

- [ ] **Step 2: 验证语法 + 导入**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "
import ast
src = open('backend/impl/kuaishou/platform.py').read()
ast.parse(src)
print('syntax OK')
from impl.kuaishou.platform import KuaishouPlatform
p = KuaishouPlatform()
print('import OK')
"
```

期望：
```
syntax OK
import OK
```

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/impl/kuaishou/platform.py
git commit -m "feat(后端): _upload_image_note 框架（上传/重定向/描述）"
```

---

## Task 5: 实现 _set_image_cover

**Files:**
- Modify: `backend/impl/kuaishou/platform.py`（在 `_set_thumbnail` 后面新增）

- [ ] **Step 1: 追加 _set_image_cover 静态方法**

在 `backend/impl/kuaishou/platform.py` 的 `_set_thumbnail` 静态方法后追加：

```python
    # ------------------------------------------------------------------
    # Helper: set image cover (image note)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_cover(page, cover_path: str):
        """点击「编辑封面」按钮 → 上传封面图 → 确认。"""
        logger.info("[kuaishou] setting image cover: %s", cover_path)
        try:
            edit_btn = page.get_by_text("编辑封面", exact=True)
            await edit_btn.wait_for(state="visible", timeout=10000)
            await edit_btn.click()
            await asyncio.sleep(2)

            modal = page.locator('div[role="document"].ant-modal:visible')
            await modal.wait_for(state="visible", timeout=30000)
            await asyncio.sleep(1)

            upload_tab = modal.locator("div[class*='header-title-item']").nth(1)
            await upload_tab.wait_for(state="visible", timeout=10000)
            await upload_tab.click()
            await asyncio.sleep(1)

            file_input = modal.locator("input[type='file']")
            await file_input.wait_for(state="attached", timeout=30000)
            await file_input.set_input_files(cover_path)
            await asyncio.sleep(3)

            confirm_btn = modal.locator("button:has-text('确认')").first
            await confirm_btn.wait_for(state="visible", timeout=10000)
            await confirm_btn.click()
            await asyncio.sleep(2)

            try:
                await modal.wait_for(state="hidden", timeout=30000)
            except Exception:
                pass
            logger.info("[kuaishou] image cover set successfully")
        except Exception as exc:
            logger.info(f"[kuaishou] image cover failed (non-fatal): {exc}")
```

- [ ] **Step 2: 验证 import**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "
from impl.kuaishou.platform import KuaishouPlatform
assert hasattr(KuaishouPlatform, '_set_image_cover')
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/impl/kuaishou/platform.py
git commit -m "feat(后端): _set_image_cover 静态方法（图文封面）"
```

---

## Task 6: 实现 _set_image_music

**Files:**
- Modify: `backend/impl/kuaishou/platform.py`

- [ ] **Step 1: 追加 _set_image_music 静态方法**

在 `_set_image_cover` 之后追加：

```python
    # ------------------------------------------------------------------
    # Helper: set image music (image note)
    # ------------------------------------------------------------------

    @staticmethod
    async def _set_image_music(page, music_id: str, music_title: str = ""):
        """点击「添加音乐」→ 抽屉内搜索 → 按 musicId/music_title 匹配 → 点「添加」。"""
        logger.info("[kuaishou] setting image music: id=%s, title=%s", music_id, music_title)
        try:
            music_label = page.get_by_text("添加音乐", exact=True)
            await music_label.wait_for(state="visible", timeout=10000)
            await music_label.click()
            await asyncio.sleep(2)

            drawer = page.locator('div.ant-drawer-content-wrapper:visible').first
            await drawer.wait_for(state="visible", timeout=10000)
            await asyncio.sleep(1)

            search_input = drawer.locator(
                "input._search-input_19mmt_16, input[placeholder='搜索音乐']"
            ).first
            await search_input.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(music_title or music_id)
            await asyncio.sleep(3)

            cards = drawer.locator("div._item_19mmt_90")
            count = await cards.count()
            target_card = None
            for i in range(count):
                card = cards.nth(i)
                title_el = card.locator("div._info-title_19mmt_139")
                if not await title_el.count():
                    continue
                t = (await title_el.text_content() or "").strip()
                if music_title and t == music_title:
                    target_card = card
                    break
            if target_card is None and count > 0:
                target_card = cards.first
                logger.warning("[kuaishou] music title not exact match, using first card")

            if target_card:
                add_btn = target_card.locator(
                    "div._button_3a3lq_1:has-text('添加'), button:has-text('添加')"
                ).first
                await add_btn.click(force=True)
                await asyncio.sleep(2)
                logger.info("[kuaishou] music added")
            else:
                logger.warning("[kuaishou] no music card found")

            close_btn = page.locator("div.ant-drawer-close").first
            if await close_btn.count():
                await close_btn.click(force=True)
        except Exception as exc:
            logger.info(f"[kuaishou] image music failed (non-fatal): {exc}")
```

- [ ] **Step 2: 验证 import**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "
from impl.kuaishou.platform import KuaishouPlatform
assert hasattr(KuaishouPlatform, '_set_image_music')
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/impl/kuaishou/platform.py
git commit -m "feat(后端): _set_image_music 静态方法（图文音乐）"
```

---

## Task 7: 集成 cover/music/declaration/schedule/publish 到 _upload_image_note

**Files:**
- Modify: `backend/impl/kuaishou/platform.py`（在 Task 4 的 `_upload_image_note` 内追加步骤 6-10）

- [ ] **Step 1: 在 _upload_image_note 末尾追加 cover/music/declaration/schedule/publish 调用**

在 `logger.info("Description filled. cover_path=%s, music_id=%s", cover_path, music_id)` 这一行**之后**插入（注意缩进保持 16 空格）：

```python
                # 6. 设置封面
                if cover_path:
                    await self._set_image_cover(page, cover_path)

                # 7. 设置音乐
                if music_id:
                    await self._set_image_music(page, music_id, music_title)

                # 8. 作者声明
                if author_declaration:
                    await self._set_author_declaration(page, author_declaration)

                # 9. 定时发布
                if enable_timer and schedule_time_str:
                    publish_date = parse_schedule_time(
                        schedule_time_str, 1, enable_timer, 1, None, 0
                    )[0]
                    if publish_date != 0:
                        await self._set_schedule_time(page, publish_date)

                logger.info("Form filling completed. dry_run=%s", dry_run)

                if not dry_run:
                    publish_btn = page.get_by_text("发布", exact=True)
                    await publish_btn.first.click()
                    await page.wait_for_url(
                        "**/article/manage/video?status=2&from=publish**",
                        timeout=60000,
                    )
                    logger.info("Published successfully")
                    await context.storage_state(path=account_file)
                else:
                    logger.info("========================================")
                    logger.info("点击发布！发布成功！（dry_run）")
                    logger.info("========================================")
```

- [ ] **Step 2: 验证语法 + 导入**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "
import ast
src = open('backend/impl/kuaishou/platform.py').read()
ast.parse(src)
print('syntax OK')
from impl.kuaishou.platform import KuaishouPlatform
print('import OK')
"
```

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/impl/kuaishou/platform.py
git commit -m "feat(后端): _upload_image_note 集成封面/音乐/声明/定时/发布"
```

---

## Task 8: 扩展 image_publish_bp 参数映射

**Files:**
- Modify: `backend/blueprints/image_publish_bp.py`（在 `publish_images()` 和 `execute_publish()` 两处调 `publish_image` 时补 3 个字段）

- [ ] **Step 1: 修改 publish_images() 中的 publish_image 调用**

`publish_images()` 里 `publish_fn = platform.publish_image` 下面有 `if asyncio.iscoroutinefunction(publish_fn):` 和 `else:` 两个分支，**每个分支都要改**。在每个分支的 `activities=config.get('activities', []),` **这一行之后**插入：

```python
                author_declaration=config.get('aiContent', ''),
                music_id=config.get('music_id', ''),
                music_title=config.get('music_title', ''),
```

注意缩进：第一分支 16 空格，第二分支（同步 else）也是 16 空格。

- [ ] **Step 2: 修改 execute_publish() 中的 publish_image 调用**

`execute_publish()` 同样有两处（asyncio 分支 + 同步 else 分支），结构与 Step 1 相同。在每个分支的 `activities=data.get('activities', []),` 之后插入：

```python
            author_declaration=data.get('author_declaration', ''),
            music_id=data.get('music_id', ''),
            music_title=data.get('music_title', ''),
```

注意这里用 `data.get(...)` 而不是 `config.get(...)`，因为 `execute_publish` 的入参是 `data`（request body）而不是 `config`。

- [ ] **Step 3: 验证语法 + 导入**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
python3 -c "
import ast
src = open('backend/blueprints/image_publish_bp.py').read()
ast.parse(src)
print('syntax OK')
from blueprints.image_publish_bp import image_publish_bp
print('import OK')
"
```

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend/blueprints/image_publish_bp.py
git commit -m "feat(后端): image_publish_bp 透传 author_declaration/music_id/music_title"
```

---

## Task 9: 前端 kuaishouImage.js API

**Files:**
- Create: `frontend/src/api/kuaishouImage.js`

- [ ] **Step 1: 写 API 模块**

创建 `frontend/src/api/kuaishouImage.js`：

```js
import { http } from '@/utils/request'

// 快手图文发布相关 API
export const kuaishouImageApi = {
  // 搜索音乐
  searchMusic(accountId, keyword, cursor = 0, count = 20) {
    return http.get(`/api/kuaishou-image/music-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&cursor=${cursor}&count=${count}`)
  },
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/api/kuaishouImage.js
git commit -m "feat(前端): 新增 kuaishouImage API 模块（音乐搜索）"
```

---

## Task 10: 前端 KuaishouMusicSelect.vue 组件

**Files:**
- Create: `frontend/src/components/kuaishou/MusicSelect.vue`

镜像 `frontend/src/components/douyin/MusicSelect.vue`（~240 行），但：
- API 调用换成 `kuaishouImageApi.searchMusic`
- 不要分页逻辑（count 传 50，不滚动加载）

- [ ] **Step 1: 写组件**

创建 `frontend/src/components/kuaishou/MusicSelect.vue`：

```vue
<template>
  <div class="music-select">
    <el-select
      v-model="selectedMusicId"
      placeholder="搜索音乐"
      clearable
      filterable
      no-data-text=" "
      @change="handleChange"
      style="width: 100%"
    >
      <template #header>
        <div class="search-input-wrapper">
          <el-input
            v-model="searchKeyword"
            placeholder="输入关键词后按回车搜索"
            clearable
            @keyup.enter="handleSearch"
            @clear="handleClear"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>
        <div v-if="loading" class="loading-indicator">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>加载中...</span>
        </div>
      </template>
      <el-option
        v-for="music in musicList"
        :key="music.musicId"
        :label="`${music.title} - ${music.author || '未知作者'}`"
        :value="music.musicId"
      >
        <div class="music-option">
          <img
            v-if="music.cover"
            :src="music.cover"
            :alt="music.title"
            class="music-cover"
            @error="onImageError"
          />
          <div class="music-info">
            <div class="music-title">{{ music.title }}</div>
            <div class="music-meta">
              <span class="music-author">{{ music.author || '未知作者' }}</span>
              <span class="music-duration">{{ formatDuration(music.duration) }}</span>
            </div>
          </div>
        </div>
      </el-option>
    </el-select>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { Search, Loading } from '@element-plus/icons-vue'
import { kuaishouImageApi } from '@/api/kuaishouImage'

const props = defineProps({
  accountId: { type: [String, Number], default: '' },
  modelValue: { type: String, default: '' },
  data: { type: Object, default: null },
})

const emit = defineEmits(['update:modelValue', 'change'])

const loading = ref(false)
const musicList = ref([])
const selectedMusicId = ref(props.modelValue || '')
const searchKeyword = ref('')

watch(() => props.modelValue, (val) => {
  selectedMusicId.value = val || ''
  if (val && !musicList.value.find(m => m.musicId === val)) {
    if (props.data && props.data.musicId === val) {
      musicList.value.unshift(props.data)
    } else {
      musicList.value.unshift({ musicId: val, title: val, author: '', duration: 0, cover: '' })
    }
  }
}, { immediate: true })

async function handleSearch() {
  const keyword = searchKeyword.value?.trim()
  if (!keyword) { musicList.value = []; return }
  loading.value = true
  try {
    const resp = await kuaishouImageApi.searchMusic(props.accountId || '', keyword, 0, 50)
    if (resp.code === 200) {
      musicList.value = resp.data?.musicList || []
    }
  } catch (e) {
    console.error('搜索音乐失败:', e)
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchKeyword.value = ''
  musicList.value = []
}

function handleChange(val) {
  if (val) {
    const music = musicList.value.find(m => m.musicId === val)
    emit('update:modelValue', val)
    emit('change', { ...music, _searchKeyword: searchKeyword.value })
  } else {
    emit('update:modelValue', null)
    emit('change', null)
  }
}

function formatDuration(seconds) {
  if (!seconds) return '00:00'
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
}

function onImageError(e) {
  e.target.style.display = 'none'
}
</script>

<style scoped lang="scss">
.music-select { width: 100%; }
.search-input-wrapper { padding: 8px 12px; }
.loading-indicator {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 8px 12px; color: #94A3B8; font-size: 13px;
  .is-loading { animation: rotating 1s linear infinite; }
  @keyframes rotating { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
}
.music-option { display: flex; align-items: center; gap: 12px; padding: 8px 0; }
.music-cover { width: 40px; height: 40px; border-radius: 4px; object-fit: cover; flex-shrink: 0; }
.music-info { flex: 1; min-width: 0; }
.music-title { font-size: 14px; color: #F8FAFC; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.music-meta { display: flex; gap: 12px; margin-top: 4px; font-size: 12px; color: #94A3B8; }
</style>
```

- [ ] **Step 2: 验证 import 不报错**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend
node -e "
const fs = require('fs');
const src = fs.readFileSync('src/components/kuaishou/MusicSelect.vue', 'utf-8');
if (src.length < 100) throw new Error('file too small');
console.log('OK');
"
```

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/components/kuaishou/MusicSelect.vue
git commit -m "feat(前端): 新增 KuaishouMusicSelect 组件（搜索控件）"
```

---

## Task 11: 扩展 KuaishouImagePublishPanel.vue

**Files:**
- Modify: `frontend/src/components/kuaishou/ImagePublishPanel.vue`

- [ ] **Step 1: 在 template 中加 3 个 setting-card（作者声明/定时发布/音乐）**

在现有 `setting-card` "标签" 之后插入：

```vue
    <div class="setting-card">
      <div class="setting-label">作者声明</div>
      <el-select v-model="form.aiContent" placeholder="请选择作者声明" clearable style="width: 100%" :disabled="disabled">
        <el-option v-for="opt in declarationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <div class="setting-card">
      <div class="setting-label">定时发布</div>
      <el-date-picker
        v-model="form.scheduleTime"
        type="datetime"
        placeholder="选择日期时间"
        format="YYYY-MM-DD HH:mm:ss"
        value-format="YYYY-MM-DD HH:mm:ss"
        style="width: 100%"
        :disabled="disabled"
      />
    </div>

    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <KuaishouMusicSelect :account-id="accountId" v-model="form.selectedMusicId" :data="form.selectedMusicData" @change="handleMusicChange" />
    </div>
```

- [ ] **Step 2: 在 script setup 中 import 必要依赖 + 写 handlers**

修改 `<script setup>`：

1. import 顶部加：
```js
import { ref, computed } from 'vue'
import KuaishouMusicSelect from './MusicSelect.vue'
```

2. 在 `const KS_DEFAULTS = ...` 之后、`const { form, ... } = useChannelForm(...)` 之前，加：

```js
const declarationOptions = computed(() => {
  const field = PLATFORMS.KUAISHOU.settingsFields.find(f => f.key === 'aiContent')
  return field?.options || []
})

function handleMusicChange(music) {
  if (music) {
    form.selectedMusicId = music.musicId
    form.selectedMusicData = music
    form.musicTitle = music.title
  } else {
    form.selectedMusicId = ''
    form.selectedMusicData = null
    form.musicTitle = ''
  }
}
```

3. 在 `publishFn` 的 `account_configs: [{` 块内、最后一个字段之后加：

```js
            music_id: merged.selectedMusicId || '',
            music_title: merged.musicTitle || '',
```

- [ ] **Step 3: 验证 Vue 模板能 import（npm 不一定装了，可以用 grep 查语法问题）**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend
# 找 import 的对应文件存在
test -f src/components/kuaishou/MusicSelect.vue && echo "MusicSelect.vue exists"
# 检查模板里引用的 KuaishouMusicSelect 是否在 script 中 import
grep -q "import KuaishouMusicSelect" src/components/kuaishou/ImagePublishPanel.vue && echo "import OK"
# 检查文件行数增加（从 126 涨到 ~180+）
wc -l src/components/kuaishou/ImagePublishPanel.vue
```

- [ ] **Step 4: 启动前端 dev server，跑 `npm run build` 检查 Vue 编译**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend
npm run build 2>&1 | tail -20
```

期望：无 Vue 编译错误，build 成功。

如果失败，修复直到成功。

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/components/kuaishou/ImagePublishPanel.vue
git commit -m "feat(前端): KuaishouImagePublishPanel 加作者声明/定时/音乐"
```

---

## Task 12: E2E 启动后端 + 前端，登录态校验

**Files:** N/A（纯运行验证）

- [ ] **Step 1: 启动后端 dev server**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend
# 先 kill 残留
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
python3 app.py &
sleep 4
curl -s http://localhost:5409/api/kuaishou-image/ping
```

期望：`{"code":200,"msg":"kuaishou-image bp ok"}`

- [ ] **Step 2: 启动前端 dev server**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend
# 先 kill 残留
lsof -i :5173 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
npm run dev &
sleep 8
curl -sI http://localhost:5173/ | head -1
```

期望：`HTTP/1.1 200 OK`

- [ ] **Step 3: 触发一次 music-search（用真实快手账号）**

```bash
# 把 1 替换成你的真实快手账号 id
curl -s "http://localhost:5409/api/kuaishou-image/music-search?account_id=1&keyword=测试&count=10" | head -c 500
```

期望：返回 JSON，code=200，musicList 数组可能为空（如果快手接口对该关键词没返回）；如果 cookie 失效会返回 500/404，**这是正常的**，先把请求链路跑通即可。

- [ ] **Step 4: 保留后端+前端运行（不要 kill）以供 Task 13/14 使用**

⚠️ 不要停掉后端和前端。直接进入 Task 13。

---

## Task 13: E2E dry_run 验证

**Files:** N/A

- [ ] **Step 1: 在前端页面上加 1 张图，选中快手账号，标题/描述/标签必填，作者声明必填，**不勾定时**，不选音乐，**dry_run=True（默认）**

通过浏览器（手动或 gstack）访问 `http://localhost:5173/`，进入"图文发布"：
1. 选 1 张图片
2. 平台勾选"快手"
3. 标题、描述、标签填好
4. 作者声明选一项
5. 点击"发布"（前端默认 dry_run=True）

期望：后端日志显示：
- "Uploading 1 images"
- "Redirected to: ..."
- "Form filling completed. dry_run=True"
- "点击发布！发布成功！（dry_run）"

- [ ] **Step 2: 同样步骤，但加一个封面（用 commonData 选封面图）+ 选音乐**

期望：后端日志显示：
- "setting image cover: /path/to/cover.jpg"
- "image cover set successfully" (或 failed 警告)
- "setting image music: id=..., title=..."
- "music added" 或兜底

- [ ] **Step 3: 同样步骤，但勾选定时发布（选一个未来时间）**

期望：后端日志显示 "Published successfully" 之前的定时发布步骤无报错。

⚠️ 不勾定时但选了未来时间也可能被快手前端要求，**保持 dry_run=True 即可，不会真发。**

---

## Task 14: E2E 真实发布（dry_run=False）

**Files:** N/A

⚠️ **这一步会真实发布到快手账号，只跑 1 次，发布 1 张测试图 + 1 个简短描述**

- [ ] **Step 1: 在前端，把"发布"按钮调用改成 dry_run=False（临时改前端）**

在 `frontend/src/components/kuaishou/ImagePublishPanel.vue` 的 `publishFn` 中，把 `dry_run: false,` 那一行的注释/条件去掉（或者临时改为 `true`），并把 `dry_run: true` 改为 `dry_run: false`：

```js
            dry_run: false,  // 临时改 false
```

⚠️ **只对快手账号测试，不要影响抖音/小红书的 dry_run**（这次改的只是 Kuaishou 面板，不影响其他平台）。

- [ ] **Step 2: 重新跑一次发布流程（同 Task 13 Step 1）**

期望：浏览器跳转到 `https://cp.kuaishou.com/article/manage/video?status=2&from=publish...`，后端日志显示：
- "Published successfully"
- "Cookie state updated"

- [ ] **Step 3: 恢复 dry_run=True**

把 `dry_run: false,` 改回 `dry_run: true,`（commit 一次也行，但建议改回后不再发 commit —— 避免引入无意义改动；或单独 commit `revert: dry_run default true`）。

- [ ] **Step 4: 收尾：停掉后端 + 前端**

```bash
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
lsof -i :5173 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
```

---

## 验收清单

- [ ] 后端 `KuaishouPlatform.publish_image` 实现并通过 dry_run 验证
- [ ] 后端 `/api/kuaishou-image/music-search` 可用
- [ ] 前端 `KuaishouImagePublishPanel` 含 5 个控件（标题/描述/标签/作者声明/定时/音乐）
- [ ] `image_publish_bp` 透传 3 个新字段
- [ ] e2e dry_run + e2e 真实发布各一次成功
- [ ] 视频发布流程未受影响
