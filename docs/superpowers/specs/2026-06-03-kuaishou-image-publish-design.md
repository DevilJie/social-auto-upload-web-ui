# 快手图文发布对接 — 设计稿

**日期**：2026-06-03
**作者**：Claude + 老蔡
**状态**：待用户 review

---

## 1. 目标

实现 `KuaishouPlatform.publish_image()`，对接快手创作者中心图文发布（`?tabType=2`），复用现有视频发布的基础设施（browser、cookie、CloakBrowser、ant-select/ant-picker helper）。

升级前端 `KuaishouImagePublishPanel.vue`，新增三个控件：**作者声明**、**定时发布**、**音乐选择**（完整搜索控件，与抖音 MusicSelect 形态一致）。

---

## 2. 范围

**In-scope**

- 后端：新增 `KuaishouPlatform.publish_image` 及 4 个 helper 方法
- 后端：新增 `kuaishou_image_bp.py` blueprint（含 `/music-search` 接口）
- 后端：扩展 `image_publish_bp.py` 调 `publish_image` 时的参数映射
- 前端：扩展 `KuaishouImagePublishPanel.vue`
- 前端：新增 `KuaishouMusicSelect.vue` + `frontend/src/api/kuaishouImage.js`

**Out-of-scope（明确不做）**

- 视频发布代码（`publish_video`）保持原样，不动
- 活动推荐、作者服务、添加地点、查看权限的自动化（用户未要求）
- 快手账号的"图文/视频"权限配置改动（`user_info` 表无 `image_type` 字段，沿用当前 `type=4` 即视为支持图文）
- 平台注册改动（`registry.py` 中 `(4, '.kuaishou.platform', 'KuaishouPlatform')` 已存在）

---

## 3. 关键设计决策

| 项 | 决定 | 理由 |
|---|---|---|
| 上传入口 URL | `https://cp.kuaishou.com/article/publish/video?tabType=2` | 抖音同款 + 视频页加 `tabType=2` 切换到图文 tab |
| 图片上传方式 | 一次 `file_chooser` 多选 | 视频流程已用此模式（`_upload_single`） |
| 等待重定向 | URL 离开 `publish/video` 视为进入详情页 | 与抖音图文思路一致 |
| 重定向超时 | 120s | 大量图片上传可能较慢 |
| 标题处理 | 拼到描述首行：`{title}\n\n{desc}` | 快手详情页无独立 title 字段 |
| 描述输入 | 视频流同款 `keyboard.type(desc or title)` 思路 | 与视频一致 |
| 标签 | 在描述末尾追加 ` #tag1 #tag2 ` 空格分隔 | 与视频一致 |
| 封面 | 点击「编辑封面」按钮 → 复用视频 modal 上传逻辑 | 视频/图文共享同一 ant-modal |
| 音乐选择 | 点击「添加音乐」→ 右侧 ant-drawer → 搜索 → 按 musicId 精确匹配点击「添加」 | 抖音同款 |
| 作者声明 | 复用视频 `_set_author_declaration`（ant-select） | 完全相同 |
| 定时发布 | 复用视频 `_set_schedule_time`（ant-radio + ant-picker） | 完全相同 |
| `dry_run` | 默认 True | 与抖音一致（先核对再发） |
| 跳过元素 | 活动推荐、作者服务、添加地点、查看权限 | 用户没要求；保持默认（公开/未选） |

---

## 4. 后端设计

### 4.1 `backend/impl/kuaishou/platform.py`

#### 4.1.1 `publish_image(**kwargs) -> bool`（公开方法，async）

**入口签名**（与抖音 `publish_image` 兼容）：

```python
async def publish_image(self, **kwargs) -> bool:
    # 解析 kwargs
    title = kwargs.get("title", "")
    files = kwargs.get("files", [])             # 绝对路径列表
    tags = kwargs.get("tags", []) or []
    account_file = kwargs.get("account_file", [])  # cookie 文件名列表
    desc = kwargs.get("desc", "")
    cover_path = kwargs.get("cover_path", "")
    enable_timer = kwargs.get("enableTimer", False)
    schedule_time_str = kwargs.get("schedule_time_str", "")
    author_declaration = kwargs.get("author_declaration", "")
    music_id = kwargs.get("music_id", "")
    music_title = kwargs.get("music_title", "")
    activities = kwargs.get("activities", []) or []
    dry_run = kwargs.get("dry_run", True)

    # 解析路径
    account_paths = [str(Path(BASE_DIR / "cookiesFile" / f)) for f in account_file]
    file_paths = [str(f) for f in files]

    # activities 拼到描述末尾
    if activities:
        activity_tags = " ".join([f"#{act}" for act in activities])
        desc = f"{desc} {activity_tags}".strip()

    for cookie_path in account_paths:
        await self._upload_image_note(
            title=title, file_paths=file_paths, tags=tags,
            account_file=cookie_path, desc=desc, cover_path=cover_path,
            author_declaration=author_declaration,
            music_id=music_id, music_title=music_title,
            enable_timer=enable_timer, schedule_time_str=schedule_time_str,
            dry_run=dry_run,
        )
    return True
```

#### 4.1.2 `_upload_image_note(...)`（async，单账号完整流程）

```python
async def _upload_image_note(
    self, *, title, file_paths, tags, account_file, desc="", cover_path="",
    author_declaration="", music_id="", music_title="",
    enable_timer=False, schedule_time_str="", dry_run=True,
):
    browser = await self.create_browser(headless=False)
    try:
        context = await self.create_context(browser, storage_state=account_file)
        try:
            page = await context.new_page()

            # 1. 打开图文 tab
            await page.goto(
                "https://cp.kuaishou.com/article/publish/video?tabType=2",
                wait_until="domcontentloaded", timeout=60000,
            )
            await page.wait_for_url(
                "**/article/publish/video?tabType=2**", timeout=60000,
            )
            await asyncio.sleep(2)

            # 2. 上传图片（多选 file chooser）
            upload_btn = page.locator("button[class^='_upload-btn']")
            await upload_btn.wait_for(state="visible", timeout=10000)
            async with page.expect_file_chooser() as fc_info:
                await upload_btn.click()
            file_chooser = await fc_info.value
            await file_chooser.set_files(file_paths)
            await asyncio.sleep(2)

            # 3. 等待重定向到详情页
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

            # 4. 关闭新手引导 / 弹层
            await self._close_guide_overlay(page)

            # 5. 填写描述（标题拼首行 + 描述正文 + 标签）
            full_desc = f"{title}\n\n{desc}" if title else desc
            logger.info("Filling description")
            desc_editor = page.locator("#work-description-edit").first
            await desc_editor.wait_for(state="visible", timeout=15000)
            await desc_editor.click()
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(full_desc[:500])
            for tag in (tags or [])[:3]:
                await page.keyboard.type(f" #{tag}")
                await page.keyboard.press("Space")
            await asyncio.sleep(0.3)

            # 6. 设置封面
            if cover_path and Path(cover_path).is_file():
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
                # 10. 点击发布
                publish_btn = page.get_by_text("发布", exact=True)
                await publish_btn.first.click()
                # 等跳转到 manage 页
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

        finally:
            await context.close()
    finally:
        await browser.close()
```

#### 4.1.3 `_set_image_cover(page, cover_path)`（static async）

```python
@staticmethod
async def _set_image_cover(page, cover_path: str):
    """点击「编辑封面」按钮 → 上传封面 → 确认。"""
    try:
        edit_btn = page.get_by_text("编辑封面", exact=True)
        await edit_btn.wait_for(state="visible", timeout=10000)
        await edit_btn.click()
        await asyncio.sleep(2)

        # 等待 modal
        modal = page.locator('div[role="document"].ant-modal:visible')
        await modal.wait_for(state="visible", timeout=30000)
        await asyncio.sleep(1)

        # 切到「上传封面」tab（第 2 个 header-title-item）
        upload_tab = modal.locator("div[class*='header-title-item']").nth(1)
        await upload_tab.wait_for(state="visible", timeout=10000)
        await upload_tab.click()
        await asyncio.sleep(1)

        # 找 file input
        file_input = modal.locator("input[type='file']")
        await file_input.wait_for(state="attached", timeout=30000)
        await file_input.set_input_files(cover_path)
        await asyncio.sleep(3)

        # 点击确认
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

#### 4.1.4 `_set_image_music(page, music_id, music_title)`（static async）

```python
@staticmethod
async def _set_image_music(page, music_id: str, music_title: str = ""):
    """点击「添加音乐」→ 搜索 → 按 musicId 匹配 → 点「添加」。"""
    try:
        music_label = page.get_by_text("添加音乐", exact=True)
        await music_label.wait_for(state="visible", timeout=10000)
        await music_label.click()
        await asyncio.sleep(2)

        drawer = page.locator('div.ant-drawer-content-wrapper:visible')
        await drawer.wait_for(state="visible", timeout=10000)
        await asyncio.sleep(1)

        # 搜索
        search_input = drawer.locator("input._search-input_19mmt_16, input[placeholder='搜索音乐']").first
        await search_input.click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.press("Delete")
        await page.keyboard.type(music_title)
        await asyncio.sleep(3)

        # 找匹配 musicId 的卡片，点「添加」按钮
        cards = drawer.locator("div._item_19mmt_90")
        count = await cards.count()
        target_card = None
        for i in range(count):
            card = cards.nth(i)
            # musicId 不在 DOM 上，所以用 title 匹配
            title_el = card.locator("div._info-title_19mmt_139")
            t = (await title_el.text_content() or "").strip()
            if t == music_title:
                target_card = card
                break
        if target_card is None and count > 0:
            # fallback: 取第一个
            target_card = cards.first
            logger.warning(f"[kuaishou] music title not exact match, using first")
        if target_card:
            add_btn = target_card.locator("button:has-text('添加'), div._button_3a3lq_1:has-text('添加')").first
            await add_btn.click()
            await asyncio.sleep(2)
            logger.info(f"[kuaishou] music added: {music_title}")
        else:
            logger.warning(f"[kuaishou] no music card found for: {music_title}")

        # 关闭 drawer
        close_btn = page.locator("div.ant-drawer-close").first
        if await close_btn.count():
            await close_btn.click(force=True)
    except Exception as exc:
        logger.info(f"[kuaishou] image music failed (non-fatal): {exc}")
```

### 4.2 `backend/blueprints/kuaishou_image_bp.py`（新建）

Mirror `douyin_image_bp.py` 的结构。包含：

- `_get_cookie_path(cookie_file)`
- `_get_account_cookie_file(account_id)`
- `_search_music_via_browser(cookie_file, keyword, count)`：用 CloakBrowser 拦截 music-search API

**Endpoint**：

```python
@kuaishou_image_bp.route('/music-search', methods=['GET'])
def search_music():
    account_id = request.args.get('account_id')
    keyword = request.args.get('keyword', '')
    count = request.args.get('count', '20')
    # ... 调用 _search_music_via_browser
    return jsonify({"code": 200, "data": {"musicList": [...], "has_more": False, "cursor": "0"}})
```

**`_search_music_via_browser` 实现思路**：
1. 用 test 图片（已存在的 `BASE_DIR/test_music_search.jpg`，或动态创建）打开 headless 浏览器
2. 访问 `https://cp.kuaishou.com/article/publish/video?tabType=2`
3. 等到详情页出现
4. 点击「添加音乐」label
5. 等 drawer 出现
6. 在 `input._search-input_19mmt_16` 输入 keyword
7. 拦截 `https://cp.kuaishou.com/rest/cp/works/atlas/pc/upload/music/search` 的响应
8. 返回 musicList（保留 `musicId`, `title`, `author`, `duration`, `cover[0].url`）

**响应字段映射**（后端 → 前端）：
```json
{
  "musicId": item["musicId"],
  "title": item["title"],
  "author": item.get("author", ""),
  "duration": item.get("duration", 0),  // 毫秒 → 前端转秒
  "cover": item.get("cover", [{}])[0].get("url", "")
}
```

### 4.3 `backend/blueprints/image_publish_bp.py`

在 `publish_images()` 和 `execute_publish()` 调 `platform.publish_image(...)` 处补齐：

```python
author_declaration=config.get('aiContent', ''),  # 前端用 aiContent 字段
music_id=config.get('music_id', ''),
music_title=config.get('music_title', ''),
```

`platform_map` 已经包含 `kuaishou: 4`，**不需要改**。

---

## 5. 前端设计

### 5.1 `frontend/src/components/kuaishou/ImagePublishPanel.vue`

**改动**：
- 保留：标题、描述、标签
- 新增：作者声明（`el-select`，options 从 `PLATFORMS.KUAISHOU.settingsFields.find(f => f.key === 'aiContent').options` 取）
- 新增：定时发布（`el-date-picker` `type="datetime"`，v-model 到 `form.scheduleTime`）
- 新增：音乐选择（`KuaishouMusicSelect`）
- `publishFn` 把新字段透传给后端
- `validateFn` 把 `merged.aiContent` 当作必填（与现状一致），把 `merged.scheduleTime` 当可选

### 5.2 `frontend/src/components/kuaishou/MusicSelect.vue`（新建）

Mirror `frontend/src/components/douyin/MusicSelect.vue`，但：
- props 增加 `accountId`
- 搜索 API 调用 `kuaishouImageApi.searchMusic`
- 列表项用 `musicId` 作 :key，label 展示 `title - author`
- 不需要分页（接口返回最多 50 条已够用，`has_more: false` 时不滚动加载）

### 5.3 `frontend/src/api/kuaishouImage.js`（新建）

```js
import http from './http'

export const kuaishouImageApi = {
  searchMusic(accountId, keyword, cursor = 0, count = 20) {
    return http.get(`/api/kuaishou-image/music-search?account_id=${accountId}&keyword=${encodeURIComponent(keyword)}&cursor=${cursor}&count=${count}`)
  },
}
```

---

## 6. 数据契约

### 6.1 前端 → 后端（`/api/image-publish/publish`）

新增字段（`account_configs[0]` 内）：
- `aiContent`: string（映射到 `author_declaration`）
- `music_id`: string
- `music_title`: string

### 6.2 前端 → 后端（`/api/kuaishou-image/music-search`）

```
GET /api/kuaishou-image/music-search?account_id={id}&keyword={kw}&count=20
```

返回：
```json
{
  "code": 200,
  "data": {
    "musicList": [
      {
        "musicId": "29061582568$4",
        "title": "比比拉布（剪辑版）",
        "author": "",
        "duration": 122,
        "cover": "https://..."
      }
    ],
    "has_more": false,
    "cursor": "0"
  }
}
```

---

## 7. 错误处理 / 边界

| 场景 | 行为 |
|---|---|
| 音乐搜索 API 失败 | 前端 toast 错误；publish 仍可继续（音乐为可选） |
| 封面不存在 / 上传失败 | log warning，publish 继续 |
| 音乐标题在 drawer 中找不到 | 兜底选第一个；log warning |
| 任意 `_set_*` 异常 | try/except 吞掉并 log，不阻塞主流程 |
| 重定向超时（120s） | log warning，继续尝试填表（可能后续操作失败但能定位问题） |
| 音乐 search 关键词为空 | 后端返回 400（与抖音一致） |
| 账号 cookie 失效 | publish 整体失败（由 browser 自身的导航失败暴露） |

---

## 8. 实施顺序（粗略）

1. 后端：`publish_image` + helpers（不依赖音乐 search）
2. 后端：`kuaishou_image_bp.music-search`
3. 后端：扩展 `image_publish_bp` 参数映射
4. 前端：`kuaishouImage.js` API
5. 前端：`KuaishouMusicSelect.vue`
6. 前端：扩展 `KuaishouImagePublishPanel.vue`
7. 真机 e2e：登录 → dry run 一次 → 真实发布一次

---

## 9. 不做

- 不写后端单元测试（项目内已有发到真实平台的 e2e 习惯）
- 不改视频发布任何代码
- 不做活动推荐、作者服务、添加地点、查看权限自动化
- 不重构现有 `_upload_single` / `_set_thumbnail`
