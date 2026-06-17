# 微博图集发布 + 图文→图集重命名设计 Spec

**日期**: 2026-06-17
**分支**: `feature/20260615-1`
**前置 Spec**: `2026-06-15-weibo-platform-design.md`（微博账号管理已落地）、`2026-05-28-image-publish-design.md`（图集发布基线）
**作者**: Claude (brainstorming + implementation)

## 目标

1. **微博图集发布**（`WeiboPlatform.publish_image`）：在 https://weibo.com 主页创作中心直接发多图 + 正文 + 内容声明。
2. **重命名**：用户可见的"图文"全部改为"图集"（菜单 / 页面标题 / 草稿页签 / 历史筛选 / 批量对话框 / 后端日志）。

API 路径、数据库 `type='image'` 字段、imagePublishApi 方法名均**保持不变**（避免破坏现有草稿与第三方调用）。

## 范围

**做**：
- 微博图集发布（页：`https://weibo.com`；多图上传 + 正文 + 5 选项内容声明）
- 前端 `ImagePublish.vue` 加微博 panel
- 用户可见 UI 的"图文"→"图集"全量替换
- 后端日志 / 注释中的"图文"→"图集"

**不做**：
- 微博图集封面字段（首图即封面，公共区 coverImage 不传给 panel）
- 微博图集分类/频道选择（主页 DOM 无此入口）
- 微博图集定时发布（与 video 版一致 V1 不支持）
- 微博图集原创声明（主页 DOM 无"声明原创"开关）
- Playwright e2e（由用户手动验证）

## 整体架构与数据流

```
PublishCenter 前端
  └─ ImagePublish.vue
      └─ WeiboImagePublishPanel.publish()
          └─ imagePublishApi.publishImage({image_ids, account_configs, ...})
              └─ POST /api/image-publish/publish
                  └─ image_publish_bp.publish_images()
                      ├─ 平台映射: 'weibo' / '微博' → platform_id=11
                      ├─ 写 publish_batches + publish_details
                      └─ platform_obj.publish_image(**kwargs)
                          └─ WeiboPlatform.publish_image()
                              └─ 走 weibo.com 主页
                                  ├─ _upload_images(page, files)
                                  ├─ _set_description(page, desc, title, tags)  # 复用 video 版
                                  ├─ _set_content_statement(page, ai_content)   # 复用 video 版
                                  └─ _click_send(page)
                                      └─ _wait_for_image_publish_success(page)
```

## 后端设计

### `WeiboPlatform.publish_image` — 新增

文件：`backend/impl/weibo/platform.py`，紧跟 `publish_video` 之后。

```python
def publish_image(self, **kwargs) -> bool:
    """微博图集发布 — 在 weibo.com 主页创作中心直接发图+正文。"""
    asyncio.run(self._upload_all_images(**kwargs))
    return True
```

**接受的 kwargs**（与小红书 `publish_image` 一致，便于 image_publish_bp 透传）：
| 参数 | 类型 | 说明 |
|------|------|------|
| `title` | `str` | 拼到正文顶部（微博图集无独立标题） |
| `files` | `list[str]` | 图片绝对路径列表 |
| `tags` | `list[str]` | 话题，拼成 `#tag1 #tag2` |
| `account_file` | `list[str]` | cookie 文件名 |
| `desc` | `str` | 微博正文（空则回落 title） |
| `ai_content` | `str` | 内容声明（**微博版 5 选项**：无/内容为自主创作/内容为转载/内容由AI生成/内容为虚构演绎） |
| `is_original` | `bool` | 忽略（微博图集无此字段） |
| `enableTimer` / `schedule_time_str` | `bool`/`str` | 忽略（V1 不支持） |
| `dry_run` | `bool` | 接收但**不真支持**（V1 不实现 dry-run 早返回，行为与 video 版一致：`if dry_run: logger.info("dry-run skip") + return True`） |
| `cover_path` | `str` | 接收但**忽略**（微博图集无独立封面；image_publish_bp 会传 `resolve_material_path('')`，不抛错） |

### `_upload_all_images(**kwargs)` — 新增

按 `files × account_file` 笛卡尔积循环调 `_upload_one_image`，结构与 video 版 `_upload_all` 一致。

### `_upload_one_image(...)` — 新增

**入口校验**：`if len(file_path_list) > 18: raise ValueError("微博图集最多 18 张")`（微博服务端硬限制）。

伪代码：
```python
browser = await self.create_browser(headless=False)
try:
    context = await self.create_context(
        browser, storage_state=account_file,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) ...",
    )
    try:
        page = await context.new_page()
        # 关键: 走主页而不是 /upload/channel
        await page.goto("https://weibo.com", timeout=60000)
        await page.wait_for_load_state("domcontentloaded", timeout=30000)

        # 关键: 等创作卡片渲染,否则 cookie 失效/慢网络会假性成功
        # 发送按钮是"创作卡片就绪"的最强信号(初始 disabled 但可见)
        try:
            await page.get_by_role(
                "button", name="发送", exact=True
            ).first.wait_for(state="attached", timeout=15000)
        except Exception as e:
            raise RuntimeError(
                f"[weibo] 创作卡片未渲染(cookie 失效/未登录?): {e}"
            )
        await asyncio.sleep(2)  # 给图片工具图标、声明 trigger 等完全渲染留余量

        # 1. 上传图片
        await self._upload_images(page, file_path_list)

        # 2. 填正文 + 标签
        await self._set_description(page, desc, title, tags)  # 复用 video 版

        # 3. 内容声明 (复用 video 版 _set_content_statement)
        await self._set_content_statement(page, ai_content)

        # 4. 发送
        await self._click_send(page)

        # 5. 等成功信号
        await self._wait_for_image_publish_success(page)

        await context.storage_state(path=account_file)
    finally:
        await context.close()
finally:
    await browser.close()
```

### `_upload_images(page, files: list[str])` — 新增

策略：直接找 `input[type=file][multiple][accept^='image/']`，一次 `set_input_files(files)`。

**注意 input 隐藏状态**：用户提供的 DOM 中 input 祖父是 `style="display: none"`，只在点「图片」trigger 时显示。Playwright `set_input_files` **不要求 visible**（只要求 attached + enabled），所以**无需先点 trigger 直接 set 即可**。若 set 失败，回退到「点 trigger → expect_file_chooser」路径。

**关键 selector（按用户提供的 DOM）**：
- 触发器文本：`图片`（在 `<div class="woo-pop-wrap">` 内）
- 文件 input：`<input type="file" accept="image/*, .jpg, .jpeg, .bmp, .gif, .png, .heif, .heic, video/mp4, video/x-m4v, video/*, .mkv, .flv" multiple="">`
- 选择器：`input[type='file'][accept^='image/'][multiple]`（避开微博正文区另一个 `accept^='.jpg'` 的 input，selector 思路来自 video 版 `_set_cover` 用 `accept^='.jpg'` 严格匹配）

**多重兜底**（与 video 版 `_upload_video_file` 思路一致）：
1. 直接 `set_input_files(files)` 命中 input
2. 失败则用 `expect_file_chooser` + 点击「图片」trigger
3. 再失败则用 patch + MutationObserver（沿用 video 版的 JS patch 三个入口 `click / dispatchEvent / showPicker`）

**等待上传完成**：轮询 textarea 周围是否有"上传中"文本（视频版才有，图集页未必有；**实际实施时需现场探查**，可临时降级为"轮询 input 周围无新加的 img 预览 → 已上传"）。最多 5 分钟。

### `_click_send(page)` — 新增

微博图集发送按钮：`button > span > "发送"`（与 video 版的"发布"按钮命名不同，要单独写）。

逻辑：
1. `get_by_role("button", name="发送", exact=True).first`
2. 轮询 `disabled` 属性，最长 60s
3. `click()`

### `_wait_for_image_publish_success(page, timeout_s=60)` — 新增

微博图集发送后**无明显 toast**（与 video 版的"视频已上传成功"不同）。判定成功靠：
1. textarea 内容清空
2. 文件预览 DOM 消失（`input[type=file][accept^='image/'][multiple]` 周围已无预览元素）
3. 创作卡片回到初始态（无 disabled 按钮）

任一条件满足即视为成功。60s 内未满足抛错。

### 复用的 video 版 helper

| Helper | 用途 | 改动 |
|--------|------|------|
| `_set_description` | 填正文 + 标签 | 不改（直接复用） |
| `_set_content_statement` | 5 选项内容声明 | 不改（直接复用） |
| `_create_browser` / `_create_context` | 浏览器/上下文 | 不改 |

### `image_publish_bp.py` — 平台映射扩 3 处

```python
# publish_images() 里的 platform_map 加 weibo
platform_map = {
    'douyin': 3, '抖音': 3,
    'xiaohongshu': 1, '小红书': 1,
    'kuaishou': 4, '快手': 4,
    'weibo': 11, '微博': 11,   # 新增
}

# _extract_image_channels_summary.platform_id_to_name 加 11
platform_id_to_name = {
    1: ('xiaohongshu', '小红书'),
    2: ('shipinhao', '视频号'),
    3: ('douyin', '抖音'),
    4: ('kuaishou', '快手'),
    5: ('bilibili', 'B站'),
    6: ('baijiahao', '百家号'),
    11: ('weibo', '微博'),   # 新增
}

# execute_publish() 里的 platform_name_map 加 11
platform_name_map = {1: '小红书', ..., 10: '爱奇艺', 11: '微博'}  # 新增
```

### 后端重命名（用户可见 + 日志）

文件 `backend/blueprints/image_publish_bp.py`、`backend/services/draft_merge.py`、`backend/storage/__init__.py` 中：
- 注释 / `logger.info` / `logger.error` 文案里的"图文"→"图集"
- 不动：URL `/api/image-publish/...`、函数名 `publish_images`、DB `type='image'` 字段

### 数据库

- `drafts.type='image'` / `publish_batches.type='image'` **保持原值**（API 兼容）
- `materials` 表无 schema 变更
- 无新表

## 前端设计

### `frontend/src/components/weibo/ImagePublishPanel.vue` — 新增

照 `xiaohongshu/ImagePublishPanel.vue` 模板（`useChannelForm` composable 复用），但**字段精简**：

| 字段 | 显示 | panel `form` 字段值 |
|------|------|---------------------|
| 描述（textarea） | ✓ | `form.description` |
| 标签（输入+tag 列表） | ✓ | `form.tags` |
| 内容声明（select） | ✓ | `form.aiContent`（用 `PLATFORMS.WEIBO.settingsFields` 里 `contentStatement` 的 options） |
| 标题 | ✗ | **不显示；`form.title` 始终等于 `form.description`（watch 同步）**，让 publishAll 的 `!merged.title` 校验通过 |
| 原创声明 | ✗ | `form.isOriginal` 固定 false |
| 定时发布 | ✗ | `form.enableTimer` 固定 false，`form.scheduleTime` 固定空 |

**关键：`form.title` 隐藏但必须随 `form.description` 实时同步**。原因：前端 `ImagePublish.vue::publishAll()` 强制校验所有平台账号的 `merged.title` 非空，微博无独立标题会直接卡死发布。watch 写法：
```js
watch(() => form.description, (v) => { form.title = v || '' })
```

`publishFn` 调 `imagePublishApi.publishImage`，payload 形态：
```js
{
  image_ids: commonData.images.map(img => img.id),
  account_configs: {
    account_id, platform: '微博', filePath: account.filePath,
    title: merged.title,            // 并入 desc (微博图集无独立标题)
    description: merged.description,
    tags: merged.tags,
    aiContent: merged.aiContent,    // 微博版 5 选项
    isOriginal: false,              // 微博图集无此字段
    cover_path: '',                 // 微博图集无独立封面
    dry_run: false,
  },
  batchId,
  landscapeCoverMaterialId: '',
  portraitCoverMaterialId: '',
}
```

`validateFn` 校验：标题非空（虽然不显示但 4 级合并要求）、其他必填项。

### `frontend/src/views/ImagePublish.vue` — 5 处改动

1. `IMAGE_PLATFORM_KEYS` 加 `'weibo'`
2. `import WeiboImagePublishPanel` + `const weiboPanelRef = ref(null)`
3. `getPanel` map 加 `weibo: weiboPanelRef` 键
4. `hasAccountOverride` 循环 / `saveDraft` 循环 / `migrateOldDraftFormat` 循环 — 3 处 hardcoded 平台数组加 `'weibo'`
5. 模板加 `<WeiboImagePublishPanel v-show="selectedPlatform === 'weibo'" ...>`

页面 title：`图文发布` → `图集发布`

### 前端重命名（用户可见 UI 全部）

| 文件 | 改动 |
|------|------|
| `frontend/src/App.vue` | 菜单项 title `图文发布` → `图集发布` |
| `frontend/src/router/index.js` | 路由 meta title `图文发布` → `图集发布` |
| `frontend/src/views/ImagePublish.vue` | page-title `图文发布` → `图集发布` |
| `frontend/src/views/DraftBox.vue` | tab pane `图文草稿` → `图集草稿`、`去发布图文` 按钮 → `去发布图集`、`typeName` 兜底 |
| `frontend/src/views/PublishHistory.vue` | el-option `图文` → `图集` |
| `frontend/src/components/OneClickFillDialog.vue` | 描述 `图文发布` → `图集发布` |

**不动**：
- `imagePublishApi` 方法名
- `/api/image-publish/...` URL
- 组件文件名（`ImagePublish.vue` / `imagePublish.js` / `image_publish_bp.py` 等保留 image 后缀，因 type='image'）

## 草稿兼容性

旧草稿 `platformConfigs` 不含 `weibo` key → `loadDraft` 时 `Object.entries(dd.platformConfigs)` 自然不遍历缺失 key，skip 即可（`if (panel && val)` 守卫只是顺便防 `val` 为空），**无破坏**。

新草稿首次保存会写入 `platformConfigs.weibo = { title:'', description:'', tags:[], aiContent:'', ... }`。

## 测试 / 验证

### 单元测试

1. `backend/tests/impl/test_weibo_image_platform.py` — 新增
   - `WeiboPlatform.publish_image` 存在、签名含 `title/files/account_file/desc/ai_content`
   - `platform_id == 11`、`platform_key == "weibo"`（video 测试已覆盖，仅复用）

2. `backend/tests/test_image_publish_endpoint.py` — 新增 case
   - POST `/api/image-publish/publish` 带 `platform: 'weibo'` / `'微博'`
   - mock `platform_obj.publish_image`，验证被调用且 kwargs 含 `title/files/tags/desc/ai_content`
   - 验证 `platform_map` 含 `'weibo': 11, '微博': 11`

### 前端构建验证

`cd frontend && npm run build` — 不报错即过。

### 浏览器 e2e — 用户手动测试

按用户要求跳过 Playwright 自动化，由用户手动验证：

1. 启动 dev server（`cd backend && python3 app.py` + `cd frontend && npm run dev`）
2. 登录一个微博账号
3. 打开「图集发布」页，确认左侧出现「微博」账号分组
4. 选 1 个微博账号 + 2~3 张测试图 + 描述 + 内容声明（AI 生成）
5. 点「一键发布」，观察 CloakBrowser
6. 微博 Web 端确认图集已发出
7. 失败时把 log 贴给 Claude，按 selector 漂移修复

## 风险与回滚

- **风险**：微博图集 DOM 的 hash class 会漂移（CloakBrowser 渲染），且图集发送无明显 toast 成功信号。
  - **对策**：所有 selector 用 `text=` / `role=button[name=]` / `placeholder=` / `accept^=` 等不依赖 class 的方式。`_wait_for_image_publish_success` 多条件 OR 判定。
- **风险**：前端 `IMAGE_PLATFORM_KEYS` 加 `'weibo'` 后，若微博账号未登录，账号分组会显示空列表但仍可点击 — 行为与现有其他平台一致。
- **回滚**：13 个文件（11 改 + 2 新增）一次性 commit，git revert 即可，原子性强。

## 改动文件清单（13 个）

### 新增（2）
1. `backend/tests/impl/test_weibo_image_platform.py`
2. `frontend/src/components/weibo/ImagePublishPanel.vue`

### 修改（11）
3. `backend/impl/weibo/platform.py` — 加 `publish_image` + 4 个 helpers
4. `backend/blueprints/image_publish_bp.py` — 3 处 platform_map 加 weibo + 注释/日志重命名
5. `backend/services/draft_merge.py` — 注释/logger 重命名
6. `backend/storage/__init__.py` — 注释重命名
7. `backend/tests/test_image_publish_endpoint.py` — 新增 case
8. `frontend/src/views/ImagePublish.vue` — 加 weibo panel + 3 处 hardcoded 数组 + getPanel map 加 weibo 键 + page title
9. `frontend/src/App.vue` — 菜单 title
10. `frontend/src/router/index.js` — 路由 meta title
11. `frontend/src/views/DraftBox.vue` — tab/按钮/兜底文案
12. `frontend/src/views/PublishHistory.vue` — el-option
13. `frontend/src/components/OneClickFillDialog.vue` — 描述文案
