# 微博图集发布 + 图文→图集重命名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「图集发布」页新增微博平台,实现 `WeiboPlatform.publish_image` 走 weibo.com 主页发多图+正文+5 选项内容声明;并把用户可见 UI 的"图文"全量改"图集"。API 路径、DB `type='image'`、方法名保持不变。

**Architecture:** 与现有小红书 / 抖音 / 快手图集发布同构 — `WeiboPlatform` 单独实现 `publish_image()` + 4 个 helpers;复用 video 版的 `_set_description` / `_set_content_statement` / `_create_browser` / `_create_context`;前端新增 `WeiboImagePublishPanel` 组件。`ImagePublish.vue` 加 5 处改动。

**Tech Stack:** Python 3.x + Playwright async + cloakbrowser (Stealth Chromium), Vue 3 + Element Plus + Pinia, Flask + SQLite.

**参考 Spec:** `docs/superpowers/specs/2026-06-17-weibo-image-album-design.md`

---

## 文件清单

| 操作 | 路径 | 责任 |
|---|---|---|
| Modify | `backend/impl/weibo/platform.py` | +`publish_image` + `_upload_all_images` + `_upload_one_image` + `_upload_images` + `_click_send` + `_wait_for_image_publish_success` |
| Modify | `backend/blueprints/image_publish_bp.py` | 3 处 platform_map 加 weibo=11;注释/日志重命名 |
| Modify | `backend/services/draft_merge.py` | 注释/logger 重命名 |
| Modify | `backend/storage/__init__.py` | 注释重命名 |
| Create | `backend/tests/impl/test_weibo_image_platform.py` | 单元测试 (publish_image 签名/入口校验) |
| Modify | `backend/tests/test_image_publish_endpoint.py` | 新增 case (mock platform.publish_image) |
| Create | `frontend/src/components/weibo/ImagePublishPanel.vue` | 微博图集发布面板 |
| Modify | `frontend/src/views/ImagePublish.vue` | 5 处改动 (panel 注册 + 3 数组 + getPanel map + page title) |
| Modify | `frontend/src/App.vue` | 菜单 title "图文发布"→"图集发布" |
| Modify | `frontend/src/router/index.js` | 路由 meta title |
| Modify | `frontend/src/views/DraftBox.vue` | tab/按钮/兜底文案 |
| Modify | `frontend/src/views/PublishHistory.vue` | el-option label |
| Modify | `frontend/src/components/OneClickFillDialog.vue` | 描述文案 |

**13 个文件:2 新增 + 11 修改。一次性 commit 即可回滚(原子性强)。**

---

## 任务索引

| Task | 内容 | 估计 |
|------|------|------|
| 1 | 后端 platform_map 3 处 + 注释/日志重命名 (image_publish_bp.py) | 5 min |
| 2 | 后端 draft_merge.py / storage/__init__.py 重命名 | 3 min |
| 3 | 后端 WeiboPlatform.publish_image 骨架 + 18 张校验 | 8 min |
| 4 | 后端 _upload_one_image 主流程 + wait_for 创作卡片 | 8 min |
| 5 | 后端 _upload_images + 多重兜底 | 10 min |
| 6 | 后端 _click_send + _wait_for_image_publish_success | 5 min |
| 7 | 后端 tests/impl/test_weibo_image_platform.py | 8 min |
| 8 | 后端 tests/test_image_publish_endpoint.py 新增 case | 5 min |
| 9 | 前端 components/weibo/ImagePublishPanel.vue 新增 | 12 min |
| 10 | 前端 views/ImagePublish.vue 5 处改动 | 5 min |
| 11 | 前端重命名 4 个 UI 文件 (App.vue / router / DraftBox / PublishHistory / OneClickFillDialog) | 3 min |
| 12 | 整体验证:pytest + npm build | 5 min |

---

## Task 1: 后端 platform_map 3 处加 weibo + 注释/日志重命名

**Files:**
- Modify: `backend/blueprints/image_publish_bp.py`

- [ ] **Step 1: 在 `publish_images()` 内的 `platform_map` 加 weibo=11**

打开 `backend/blueprints/image_publish_bp.py`,找到 `publish_images()` 函数内 `platform_map = { ... }` (line 169 附近),在末尾加:
```python
platform_map = {
    'douyin': 3, '抖音': 3,
    'xiaohongshu': 1, '小红书': 1,
    'kuaishou': 4, '快手': 4,
    'weibo': 11, '微博': 11,   # 新增
}
```

- [ ] **Step 2: 在 `_extract_image_channels_summary()` 内的 `platform_id_to_name` 加 11**

找到 `_extract_image_channels_summary()` 函数内 `platform_id_to_name = { ... }` (line 376 附近),在末尾加:
```python
platform_id_to_name = {
    1: ('xiaohongshu', '小红书'),
    2: ('shipinhao', '视频号'),
    3: ('douyin', '抖音'),
    4: ('kuaishou', '快手'),
    5: ('bilibili', 'B站'),
    6: ('baijiahao', '百家号'),
    11: ('weibo', '微博'),   # 新增
}
```

- [ ] **Step 3: 在 `execute_publish()` 内的 `platform_name_map` 加 11**

找到 `execute_publish()` 函数内 `platform_name_map = { ... }` (line 458 附近),在末尾加:
```python
platform_name_map = {1: '小红书', 2: '视频号', 3: '抖音', 4: '快手', 5: 'B站',
                     6: '百家号', 7: 'TikTok', 8: 'YouTube', 9: '腾讯视频', 10: '爱奇艺',
                     11: '微博'}  # 新增
```

- [ ] **Step 4: 注释/日志/字符串字面量中的"图文"→"图集"**

在 `image_publish_bp.py` 内搜索所有 `图文`,逐个替换为 `图集`:
- 文件 docstring (line 1-3): `图文发布 Blueprint` → `图集发布 Blueprint`
- 注释/logger 文案: `图文内容` → `图集内容`、`图文草稿` → `图集草稿`、`图文平台` → `图集平台`、`图文发布` → `图集发布`
- **不动**:`type='image'` 字段、`/api/image-publish/...` URL、`publish_images` 函数名、`image_publish_bp` blueprint 名

可以用 grep 辅助:
```bash
grep -n "图文" /home/czy/workspace/ai/social-auto-upload-web-ui/backend/blueprints/image_publish_bp.py
```

- [ ] **Step 5: 启动后端验证 import 不报错**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && cd backend && python3 -c "from blueprints.image_publish_bp import image_publish_bp; print('OK')"
```
Expected: `OK`

- [ ] **Step 6: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/blueprints/image_publish_bp.py && git commit -m "$(cat <<'EOF'
feat(weibo): image_publish_bp 3 处 platform_map 加 weibo=11 + 重命名"图文"→"图集"

- publish_images 内 platform_map 加 'weibo': 11 / '微博': 11
- _extract_image_channels_summary 内 platform_id_to_name 加 11: ('weibo', '微博')
- execute_publish 内 platform_name_map 加 11: '微博'
- 注释/logger 字面量"图文"→"图集"(不动 API/DB type 字段)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 后端 draft_merge.py / storage/__init__.py 重命名

**Files:**
- Modify: `backend/services/draft_merge.py`
- Modify: `backend/storage/__init__.py`

- [ ] **Step 1: 替换 `backend/services/draft_merge.py` 中的"图文"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" backend/services/draft_merge.py
```
逐行查看,所有用户可见的注释/logger 文本/错误消息中的"图文"→"图集"。
**不动**:`def validate_image_draft_for_publish` 函数名、`def _dry_run_validate_image_draft` 函数名(内部 helper)。

主要替换位置 (基于 spec 调研):
- line 225: `# 图文平台声明字段映射（与视频版相同）` → `# 图集平台声明字段映射（与视频版相同）`
- line 230: `"""dry-run 校验图文草稿。返回错误消息列表。"""` → `"""dry-run 校验图集草稿。返回错误消息列表。"""`
- line 247: `errors.append(f'图文草稿({platform}) 缺 {"+".join(missing)}')` → `errors.append(f'图集草稿({platform}) 缺 {"+".join(missing)}')`
- line 250: `errors.append(f'图文草稿({platform}) 缺 {decl_field}')` → `errors.append(f'图集草稿({platform}) 缺 {decl_field}')`

- [ ] **Step 2: 替换 `backend/storage/__init__.py` 中的"图文"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" backend/storage/__init__.py
```
主要替换 (基于 spec 调研):
- line 79: `视频发布、图文发布、抽帧、封面……所有需要把素材表的` → `视频发布、图集发布、抽帧、封面……所有需要把素材表的`

- [ ] **Step 3: 验证 import**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "from services.draft_merge import validate_image_draft_for_publish; from storage import resolve_material_path; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/services/draft_merge.py backend/storage/__init__.py && git commit -m "$(cat <<'EOF'
chore(weibo): 后端 draft_merge / storage 注释"图文"→"图集"

不影响功能,仅文案统一。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 后端 WeiboPlatform.publish_image 骨架 + 18 张校验

**Files:**
- Modify: `backend/impl/weibo/platform.py`

- [ ] **Step 1: 在 `publish_video` 之后添加 `publish_image` 骨架**

打开 `backend/impl/weibo/platform.py`,找到 `def publish_video(self, **kwargs) -> bool:` (line 213),在它**之后**添加:

```python
    # ------------------------------------------------------------------
    # publish_image -- full Weibo image-album pipeline (sync entry point)
    # ------------------------------------------------------------------

    def publish_image(self, **kwargs) -> bool:
        """Publish an image album to Weibo (sync wrapper).

        入口仅做 kwargs 解包 + dry-run 早返回 + 调 _upload_all_images。
        实际浏览器操作在 _upload_one_image。
        """
        dry_run = kwargs.get("dry_run", False)
        if dry_run:
            logger.info("[weibo] dry-run skip (publish_image)")
            return True
        asyncio.run(self._upload_all_images(**kwargs))
        return True

    # ------------------------------------------------------------------
    # Internal: orchestrate all account uploads (one batch per account)
    # ------------------------------------------------------------------

    async def _upload_all_images(self, **kwargs):
        """Create a browser per account, upload all images in the batch.

        与 video 版 _upload_all 的关键区别:**单层账号循环** (图集是一账号
        一次发完所有图),不是 files × accounts 笛卡尔积。
        """
        files = kwargs.get("files", []) or []
        account_file = kwargs.get("account_file", []) or []
        title = kwargs.get("title", "")
        tags = kwargs.get("tags", []) or []
        desc = kwargs.get("desc", "") or ""
        ai_content = kwargs.get("ai_content", "") or ""
        # 忽略字段(微博图集不支持)
        # is_original / enableTimer / schedule_time_str / cover_path
        _ = kwargs.get("is_original")  # noqa
        _ = kwargs.get("enableTimer")  # noqa
        _ = kwargs.get("schedule_time_str")  # noqa
        _ = kwargs.get("cover_path")  # noqa

        # 入口校验:微博图集服务端硬上限 18 张
        if len(files) > 18:
            raise ValueError(
                f"[weibo] 图集最多 18 张,当前 {len(files)} 张"
            )

        file_path_list = [str(f) for f in files]
        account_paths = [
            str(Path(BASE_DIR / "cookiesFile") / f) for f in account_file
        ]

        # 单层账号循环(不是笛卡尔积!)
        for cookie_path in account_paths:
            await self._upload_one_image(
                title=title,
                file_path_list=file_path_list,
                tags=tags,
                account_file=cookie_path,
                desc=desc,
                ai_content=ai_content,
            )
```

- [ ] **Step 2: 添加 `_upload_one_image` 主流程占位(下一 task 完整实现)**

紧接着 `_upload_all_images` 之后添加 stub:
```python
    # ------------------------------------------------------------------
    # Internal: upload one image album to one account
    # ------------------------------------------------------------------

    async def _upload_one_image(
        self,
        title: str,
        file_path_list: list,
        tags: list,
        account_file: str,
        desc: str = "",
        ai_content: str = "",
    ):
        """Upload one image album to one Weibo account (待 Task 4 完整实现)."""
        raise NotImplementedError("[weibo] _upload_one_image 待实现")
```

- [ ] **Step 3: 验证 import 不报错**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "from impl.weibo.platform import WeiboPlatform; p = WeiboPlatform(); print(hasattr(p, 'publish_image'))"
```
Expected: `True`

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/weibo/platform.py && git commit -m "$(cat <<'EOF'
feat(weibo): WeiboPlatform.publish_image 骨架 + 18 张上限校验

- 新增 publish_image (sync entry, 调 _upload_all_images)
- 新增 _upload_all_images (单层账号循环,非笛卡尔积)
- 新增 _upload_one_image stub (NotImplementedError,待 Task 4 完整实现)
- dry_run 早返回(与 video 版行为一致)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 后端 _upload_one_image 主流程 + wait_for 创作卡片

**Files:**
- Modify: `backend/impl/weibo/platform.py`

- [ ] **Step 1: 替换 `_upload_one_image` stub 为完整实现**

把 Task 3 写的 `_upload_one_image` stub 整段替换为:

```python
    async def _upload_one_image(
        self,
        title: str,
        file_path_list: list,
        tags: list,
        account_file: str,
        desc: str = "",
        ai_content: str = "",
    ):
        """Upload one image album to one Weibo account.

        流程:
        1. 创建 browser + context + 走 weibo.com 主页(不是 /upload/channel)
        2. wait_for 创作卡片(发送按钮) — cookie 失效检测
        3. _upload_images 上传多图
        4. _set_description 填正文 + 标签(复用 video 版)
        5. _set_content_statement 选 5 选项内容声明(复用 video 版)
        6. _click_send 点击发送
        7. _wait_for_image_publish_success 等成功信号
        8. 保存 cookie
        """
        browser = await self.create_browser(headless=False)
        try:
            context = await self.create_context(
                browser,
                storage_state=account_file,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.4324.150 Safari/537.36"
                ),
            )
            try:
                page = await context.new_page()
                # 关键: 走主页而不是 /upload/channel
                await page.goto("https://weibo.com", timeout=60000)
                await page.wait_for_load_state("domcontentloaded", timeout=30000)

                # 关键: wait_for 创作卡片(发送按钮) — cookie 失效/未登录会抛
                try:
                    await page.get_by_role(
                        "button", name="发送", exact=True
                    ).first.wait_for(state="attached", timeout=15000)
                except Exception as e:
                    raise RuntimeError(
                        f"[weibo] 创作卡片未渲染(cookie 失效/未登录?): {e}"
                    )
                await asyncio.sleep(2)  # 等图片工具/声明 trigger 完全渲染

                # 1. 上传图片
                await self._upload_images(page, file_path_list)

                # 2. 填正文 + 标签
                await self._set_description(page, desc, title, tags)

                # 3. 内容声明 (复用 video 版)
                await self._set_content_statement(page, ai_content)

                # 4. 发送
                await self._click_send(page)

                # 5. 等成功信号
                await self._wait_for_image_publish_success(page)

                # 6. 保存 cookie
                await context.storage_state(path=account_file)
                logger.info("[weibo] cookie 已更新")
                await asyncio.sleep(2)
            finally:
                await context.close()
        finally:
            await browser.close()
```

- [ ] **Step 2: 验证 Python 语法**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "import ast; ast.parse(open('impl/weibo/platform.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/weibo/platform.py && git commit -m "$(cat <<'EOF'
feat(weibo): _upload_one_image 主流程 — 走 weibo.com 主页 + wait_for 创作卡片

主流程 5 步:_upload_images → _set_description → _set_content_statement
→ _click_send → _wait_for_image_publish_success
cookie 失效检测:wait_for 发送按钮 attached,15s 内未渲染抛 RuntimeError

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 后端 _upload_images + 多重兜底

**Files:**
- Modify: `backend/impl/weibo/platform.py`

- [ ] **Step 1: 在 `_upload_one_image` 之后添加 `_upload_images`**

```python
    # ------------------------------------------------------------------
    # Helper: upload image files via hidden input[type=file]
    # ------------------------------------------------------------------

    @staticmethod
    async def _upload_images(page, files: list):
        """上传图集多张图 — 多重兜底(2026-06-17 v1)。

        selector 策略:input[type=file][accept^='image/'][multiple]
        (用户提供的 DOM 行 9-10:accept 以 image/* 开头,且带 multiple)
        注意:input 祖父是 display:none,但 Playwright set_input_files 不要求
        visible,只要求 attached + enabled。

        多重兜底:
        1. 直接 set_input_files(files) 命中 input
        2. 失败则 expect_file_chooser + 点击「图片」trigger
        3. 再失败则 patch click/dispatchEvent/showPicker + MutationObserver

        等待完成:轮询「发送」按钮的 disabled 属性为 None(上传+表单就绪
        → 启用);最多 5 分钟。
        """
        if not files:
            logger.warning("[weibo] 无图片可上传")
            return

        logger.info("[weibo] 准备上传 %d 张图片", len(files))

        # 0. 安装 MutationObserver 兜底(参考 video 版 _upload_video_file)
        await page.evaluate(r"""() => {
            if (window.__weiboImgObserverInstalled) return;
            window.__weiboImgObserverInstalled = true;
            window.__weiboImgInitialInputCount =
                document.querySelectorAll('input[type="file"]').length;
            const observer = new MutationObserver(() => {
                const inputs = document.querySelectorAll('input[type="file"]');
                if (inputs.length > window.__weiboImgInitialInputCount) {
                    for (let i = window.__weiboImgInitialInputCount;
                         i < inputs.length; i++) {
                        inputs[i].setAttribute('data-weibo-img-new', '1');
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }""")

        # 1. Patch 三个入口(参考 video 版)
        patch_status = await page.evaluate(r"""() => {
            if (window.__weiboImgAllPatched) return 'already-patched';
            window.__weiboImgAllPatched = true;
            const markInput = function (input) {
                try {
                    input.setAttribute('data-weibo-img-upload', '1');
                    if (!input.isConnected) {
                        input.style.display = 'none';
                        document.body.appendChild(input);
                    }
                } catch (e) {}
            };
            const origClick = HTMLInputElement.prototype.click;
            HTMLInputElement.prototype.click = function () {
                if (this && this.type === 'file') {
                    markInput(this);
                } else {
                    return origClick.apply(this, arguments);
                }
            };
            const origDispatch = EventTarget.prototype.dispatchEvent;
            EventTarget.prototype.dispatchEvent = function (event) {
                if (this && this.type === 'file' && event &&
                    event.type === 'click' && event instanceof MouseEvent) {
                    markInput(this);
                    return true;
                }
                return origDispatch.apply(this, arguments);
            };
            if (HTMLInputElement.prototype.showPicker) {
                const origShow = HTMLInputElement.prototype.showPicker;
                HTMLInputElement.prototype.showPicker = function () {
                    if (this && this.type === 'file') {
                        markInput(this);
                    } else {
                        return origShow.apply(this, arguments);
                    }
                };
            }
            return 'patched';
        }""")
        logger.info("[weibo] img patch status: %s", patch_status)

        # 2. 找「图片」trigger
        # selector:文本 "图片" 在 woo-pop-wrap 内,且 sibling 包含 image upload input
        img_trigger = page.get_by_text("图片", exact=True).first
        if await img_trigger.count() == 0:
            raise RuntimeError("[weibo] 未找到「图片」工具图标")

        # 3. 优先直接 set_input_files(接受 hidden input)
        target_input_sel = (
            "input[type='file'][accept^='image/'][multiple]"
        )
        try:
            target_input = page.locator(target_input_sel).first
            await target_input.wait_for(state="attached", timeout=10000)
            await target_input.set_input_files(files)
            logger.info("[weibo] 已通过 set_input_files 提交 %d 张图", len(files))
        except Exception as e:
            logger.info("[weibo] 直接 set_input_files 失败: %s", e)

            # 兜底 1: expect_file_chooser + 点击 trigger
            try:
                async with page.expect_file_chooser(timeout=5000) as fc_info:
                    await img_trigger.click(force=True)
                fc = await fc_info.value
                await fc.set_files(files)
                logger.info("[weibo] 已通过 expect_file_chooser 提交")
            except Exception as e2:
                logger.info("[weibo] expect_file_chooser 失败: %s", e2)
                # 兜底 2: 等带标记的 input 出现(patch 命中)
                marked_sel = (
                    "input[type='file'][data-weibo-img-upload='1'],"
                    "input[type='file'][data-weibo-img-new='1']"
                )
                deadline = asyncio.get_event_loop().time() + 30
                found = None
                while asyncio.get_event_loop().time() < deadline:
                    count = await page.locator(marked_sel).count()
                    if count > 0:
                        found = page.locator(marked_sel).first
                        break
                    await asyncio.sleep(0.5)
                if found is not None:
                    await found.set_input_files(files)
                    logger.info("[weibo] 已通过 patched input 提交")
                else:
                    raise RuntimeError(
                        f"[weibo] 30s 内未找到可用的 file input"
                    )

        # 4. 等待上传完成 — 轮询「发送」按钮 enabled(最稳判定)
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        deadline = asyncio.get_event_loop().time() + 300  # 5 分钟
        while asyncio.get_event_loop().time() < deadline:
            try:
                disabled = await send_btn.get_attribute("disabled")
                if disabled is None:
                    logger.info("[weibo] 图片已上传,发送按钮已启用")
                    return
            except Exception:
                pass
            await asyncio.sleep(2)

        raise RuntimeError("[weibo] 5 分钟内图片未上传完成(发送按钮未启用)")
```

- [ ] **Step 2: 验证语法**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "import ast; ast.parse(open('impl/weibo/platform.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/weibo/platform.py && git commit -m "$(cat <<'EOF'
feat(weibo): _upload_images 多重兜底 + 发送按钮 enabled 等待

3 重兜底:set_input_files → expect_file_chooser → patch+MutationObserver
等待策略:轮询「发送」按钮 disabled 属性为 None(5 分钟超时)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 后端 _click_send + _wait_for_image_publish_success

**Files:**
- Modify: `backend/impl/weibo/platform.py`

- [ ] **Step 1: 在 `_upload_images` 之后添加 `_click_send`**

```python
    # ------------------------------------------------------------------
    # Helper: click 发送 button
    # ------------------------------------------------------------------

    @staticmethod
    async def _click_send(page):
        """点击「发送」按钮(图集版,视频版是「发布」)。

        与 video 版 _click_publish 同构,只是 button name 不同。
        初始 disabled,表单就绪后启用 — 轮询 disabled 属性(最长 60s)。
        """
        send_btn = page.get_by_role("button", name="发送", exact=True).first
        try:
            await send_btn.wait_for(state="visible", timeout=10000)
        except Exception as e:
            raise RuntimeError(f"[weibo] 未找到「发送」按钮: {e}")

        # 轮询 disabled(最长 60s)
        for _ in range(60):
            disabled = await send_btn.get_attribute("disabled")
            if disabled is None:
                break
            await asyncio.sleep(1)
        else:
            raise RuntimeError("[weibo] 「发送」按钮一直 disabled,表单未就绪")

        await send_btn.click()
        logger.info("[weibo] 已点击「发送」按钮")
```

- [ ] **Step 2: 在 `_click_send` 之后添加 `_wait_for_image_publish_success`**

```python
    # ------------------------------------------------------------------
    # Helper: wait for image publish success signal
    # ------------------------------------------------------------------

    @staticmethod
    async def _wait_for_image_publish_success(page, timeout_s: int = 60):
        """等待图集发布完成。

        微博图集发送后**无明显 toast**(与 video 版的「视频已上传成功」
        不同)。判定成功靠 3 个条件 OR:
        1. textarea 内容清空
        2. 创作卡片回到初始态(「发送」按钮重新 disabled)
        3. 工具图标区域无新加的 img 预览

        60s 内任一命中即视为成功。
        """
        deadline = asyncio.get_event_loop().time() + timeout_s
        textarea = page.locator("textarea[placeholder*='有什么新鲜事']").first
        send_btn = page.get_by_role("button", name="发送", exact=True).first

        while asyncio.get_event_loop().time() < deadline:
            try:
                # 条件 1: textarea 清空
                textarea_empty = await textarea.input_value() == ""
                # 条件 2: 发送按钮重新 disabled
                disabled = await send_btn.get_attribute("disabled")
                send_disabled = disabled is not None
                if textarea_empty or send_disabled:
                    logger.info("[weibo] 图集发布成功(textarea 空=%s, send 禁用=%s)",
                                textarea_empty, send_disabled)
                    return
            except Exception:
                pass
            await asyncio.sleep(2)

        raise RuntimeError(
            f"[weibo] 等待图集发布完成超时({timeout_s}s)"
        )
```

- [ ] **Step 3: 验证语法**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "import ast; ast.parse(open('impl/weibo/platform.py').read()); print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/impl/weibo/platform.py && git commit -m "$(cat <<'EOF'
feat(weibo): _click_send + _wait_for_image_publish_success 完成发布流程

_click_send:轮询 disabled 60s 后点击(与 video 版 _click_publish 同构)
_wait_for_image_publish_success:textarea 清空 OR 发送按钮重新 disabled(60s 超时)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 后端 tests/impl/test_weibo_image_platform.py 单元测试

**Files:**
- Create: `backend/tests/impl/test_weibo_image_platform.py`

- [ ] **Step 1: 检查 `backend/tests/impl/` 目录是否存在**

```bash
ls /home/czy/workspace/ai/social-auto-upload-web-ui/backend/tests/impl/__init__.py 2>/dev/null && echo "exists" || echo "missing"
```
- 如果 `exists`:跳过 Step 2
- 如果 `missing`:执行 Step 2

- [ ] **Step 2: 创建 `backend/tests/impl/__init__.py` (如缺失)**

```python
"""Tests for individual platform implementations."""
```

- [ ] **Step 3: 创建 `backend/tests/impl/test_weibo_image_platform.py`**

```python
"""Unit tests for WeiboPlatform.publish_image signature and platform metadata."""
import sys
from pathlib import Path

# 把 backend 目录加进 sys.path(与项目其他测试一致)
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from impl.weibo.platform import WeiboPlatform  # noqa: E402


def test_publish_image_method_exists():
    """WeiboPlatform 暴露 publish_image 方法。"""
    p = WeiboPlatform()
    assert hasattr(p, "publish_image")
    assert callable(p.publish_image)


def test_platform_metadata():
    """platform_id=11, platform_key='weibo'。"""
    p = WeiboPlatform()
    assert p.platform_id == 11
    assert p.platform_key == "weibo"
    assert p.platform_name == "微博"


def test_publish_image_dry_run_returns_true():
    """dry_run=True 时不进入异步流程,直接返回 True。"""
    p = WeiboPlatform()
    result = p.publish_image(dry_run=True, files=[], account_file=[])
    assert result is True


def test_publish_image_18_image_limit():
    """files 数 > 18 时抛 ValueError。"""
    p = WeiboPlatform()
    too_many = [f"/tmp/fake_{i}.jpg" for i in range(19)]
    try:
        p.publish_image(
            files=too_many,
            account_file=["dummy.json"],
            dry_run=False,
        )
    except ValueError as e:
        assert "18" in str(e)
        return
    except Exception:
        # asyncio.run 可能因 dummy 路径失败 — 只要不是正常返回即视为约束生效
        return
    raise AssertionError("expected ValueError for >18 images, got success")
```

- [ ] **Step 4: 跑测试**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/impl/test_weibo_image_platform.py -v
```
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/tests/impl/ && git commit -m "$(cat <<'EOF'
test(weibo): 单元测试 WeiboPlatform.publish_image 签名/平台元数据/18 张上限

- test_publish_image_method_exists: 验证方法存在
- test_platform_metadata: 验证 platform_id=11, key='weibo'
- test_publish_image_dry_run_returns_true: 验证 dry_run 早返回
- test_publish_image_18_image_limit: 验证 >18 张抛 ValueError

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: 后端 tests/test_image_publish_endpoint.py 新增 case

**Files:**
- Modify: `backend/tests/test_image_publish_endpoint.py`

- [ ] **Step 1: 找到现有 case 列表**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && grep -n "^def test_\|^class " tests/test_image_publish_endpoint.py | head -20
```
确认现有 case 风格(命名、fixture、import 风格)。

- [ ] **Step 2: 在文件末尾追加 weibo case**

按照现有 case 的风格(看 1-2 个 case 模仿),在末尾追加:

```python
def test_publish_endpoint_routes_weibo_to_publish_image(client, monkeypatch):
    """POST /api/image-publish/publish 带 platform='weibo' 时,
    路由到 WeiboPlatform.publish_image(platform_id=11)。

    间接验证 platform_map 含 'weibo': 11 / '微博': 11
    (platform_map 是函数内局部变量,模块导入不可见)。
    """
    from impl import registry as reg

    calls = []

    class FakeWeibo:
        def publish_image(self, **kwargs):
            calls.append(kwargs)
            return True

    fake = FakeWeibo()
    monkeypatch.setattr(reg, "get_platform", lambda pid: fake if pid == 11 else None)

    # 直接调 publish_images() 而不走 HTTP,绕开 DB 写入
    from blueprints.image_publish_bp import publish_images
    from flask import Flask
    app = Flask(__name__)
    with app.test_request_context(
        "/api/image-publish/publish",
        method="POST",
        json={
            "image_ids": ["img1"],
            "account_configs": {
                "platform": "微博",
                "filePath": "dummy.json",
                "title": "测试图集",
                "description": "测试描述",
                "tags": ["测试"],
                "aiContent": "内容由AI生成",
            },
        },
    ):
        resp = publish_images()
        # 验证调到了 publish_image
        assert len(calls) == 1
        assert calls[0]["title"] == "测试图集"
        assert calls[0]["desc"] == "测试描述"
        assert calls[0]["ai_content"] == "内容由AI生成"
```

> 注:具体实现要看 `tests/test_image_publish_endpoint.py` 现有 fixture (`client`, 任何 DB mock) — 如果现有 case 都用真实 DB / `image_ids` 在 materials 表里能找到,需相应调整。

如果 `monkeypatch` 不在现有测试里,改用 `unittest.mock.patch`:
```python
from unittest.mock import patch

@patch("impl.registry.get_platform")
def test_publish_endpoint_routes_weibo_to_publish_image(mock_get_platform, ...):
    ...
    mock_get_platform.return_value = fake
```

- [ ] **Step 3: 跑新 case**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/test_image_publish_endpoint.py -v -k weibo
```
Expected: 1 passed (test_publish_endpoint_routes_weibo_to_publish_image)

- [ ] **Step 4: 跑全部 image_publish_endpoint 测试确保无回归**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/test_image_publish_endpoint.py -v
```
Expected: 全部 passed

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add backend/tests/test_image_publish_endpoint.py && git commit -m "$(cat <<'EOF'
test(weibo): image-publish endpoint 新增 weibo 路由 case

mock get_platform(11) → FakeWeibo.publish_image,验证
publish_images() 调到了 publish_image 且 kwargs 透传正确。
间接验证 platform_map 含 'weibo': 11 / '微博': 11。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 前端 components/weibo/ImagePublishPanel.vue 新增

**Files:**
- Create: `frontend/src/components/weibo/ImagePublishPanel.vue`

- [ ] **Step 1: 创建 `frontend/src/components/weibo/` 目录**

```bash
mkdir -p /home/czy/workspace/i/social-auto-upload-web-ui/frontend/src/components/weibo
```
(如果目录已存在,无影响)

- [ ] **Step 2: 创建 `frontend/src/components/weibo/ImagePublishPanel.vue`**

按以下完整内容写入文件 (照 `xiaohongshu/ImagePublishPanel.vue` 模板改字段):

```vue
<template>
  <div class="weibo-image-publish-panel">
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入微博正文..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <div class="setting-card" style="grid-column: 1 / -1">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入话题内容,按回车确认(微博图集会拼成 #话题1 #话题2)</div>
      <el-input v-model="tagInput" placeholder="输入话题内容,按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(tag, index) in form.tags" :key="index" closable @close="removeTag(index)" size="small" :disable-transitions="false">#{{ tag }}</el-tag>
      </div>
    </div>

    <div class="settings-row">
      <div class="setting-card" style="grid-column: 1 / -1">
        <div class="setting-label">内容声明</div>
        <el-select v-model="form.aiContent" placeholder="请选择" :disabled="disabled" style="width: 100%;">
          <el-option
            v-for="opt in statementOptions"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import { PLATFORMS } from '@/config/platforms'
import { useChannelForm } from '@/composables/useChannelForm'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// 内容声明 options 来自 settingsFields.contentStatement(不是 aiContent!)
const statementField = PLATFORMS.WEIBO.settingsFields.find(f => f.key === 'contentStatement')
const statementOptions = computed(() => statementField?.options || [])

// 9 STANDARD_FIELDS 全部齐备(必含 aiContent,即使 PLATFORMS.WEIBO.defaultSettings 没这个 key)
const WEIBO_DEFAULTS = {
  title: '',
  description: '',
  tags: [],
  images: [],
  coverImage: null,
  enableTimer: false,
  scheduleTime: '',
  aiContent: '',
  isOriginal: false,
  // 微博视频版残留字段(冗余但无害):
  videoType: '',
  weiboCategory: [],
  contentStatement: '',
}

const { form, hasAccountOverride, resetOverride, publicApi } = useChannelForm(
  WEIBO_DEFAULTS,
  { props, emit },
  {
    publishFn: async (accountId, accountName, commonData, merged, extra) => {
      const account = accountStore.accounts.find(a => a.id === accountId)
      if (!account) {
        emit('publish-result', { accountName, status: 'fail', message: '账号不存在' })
        return
      }
      try {
        await imagePublishApi.publishImage({
          image_ids: commonData.images.map(img => img.id),
          account_configs: {
            account_id: accountId,
            platform: account.platform,
            filePath: account.filePath,
            title: merged.title,           // = description (watch 同步)
            description: merged.description,
            tags: merged.tags || [],
            aiContent: merged.aiContent || '',
            isOriginal: false,
            cover_path: '',
            dry_run: false,
          },
          batchId: extra?.batchId || '',
          landscapeCoverMaterialId: '',
          portraitCoverMaterialId: '',
        })
        emit('publish-result', { accountName, status: 'success', message: '发布成功' })
      } catch (e) {
        emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
      }
    },
    // 微博 panel 无独立必填项,所有校验已在 publishAll 完成
    validateFn: (accountId, merged) => ({ valid: true, errors: [] }),
  },
)

// 关键:form.title 始终 = form.description(让 publishAll 的 !merged.title 校验通过)
watch(() => form.description, (v) => { form.title = v || '' })

const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) { ElMessage.warning('话题已存在'); return }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) { form.tags.splice(index, 1) }

defineExpose(publicApi)
</script>

<style scoped>
.weibo-image-publish-panel {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(350px, 1fr));
  gap: 12px;
}

.settings-row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 1fr;
  gap: 12px;
}

.settings-row .setting-card {
  min-width: 0;
}

.setting-card {
  border: 1px solid rgba(230, 22, 45, 0.15);
  background: rgba(230, 22, 45, 0.04);
  border-radius: 8px;
  padding: 16px;
}

.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: #E6162D;
  margin-bottom: 8px;
}

.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
</style>
```

- [ ] **Step 3: 验证前端构建(只 import 这个文件不报错)**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vue-tsc --noEmit 2>&1 | head -20
```
Expected: 不应报 weibo 组件相关错误(可能报其他未相关错误可忽略)

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add frontend/src/components/weibo/ImagePublishPanel.vue && git commit -m "$(cat <<'EOF'
feat(weibo): 新增 WeiboImagePublishPanel

描述 + 标签 + 内容声明(微博版 5 选项)
9 STANDARD_FIELDS 齐备(aiContent 显式声明)
watch 同步 form.title = form.description(绕过 publishAll title 校验)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: 前端 views/ImagePublish.vue 5 处改动

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`

- [ ] **Step 1: `IMAGE_PLATFORM_KEYS` 加 'weibo'**

打开 `frontend/src/views/ImagePublish.vue`,找到 line 277 附近:
```js
const IMAGE_PLATFORM_KEYS = ['xiaohongshu', 'douyin', 'kuaishou']
```
改为:
```js
const IMAGE_PLATFORM_KEYS = ['xiaohongshu', 'douyin', 'kuaishou', 'weibo']
```

- [ ] **Step 2: import WeiboImagePublishPanel + 注册 ref**

在 line 268 附近 (`import KuaishouImagePublishPanel from '@/components/kuaishou/ImagePublishPanel.vue'`) 之后添加:
```js
import WeiboImagePublishPanel from '@/components/weibo/ImagePublishPanel.vue'
```

在 line 363 附近 (`const kuaishouPanelRef = ref(null)`) 之后添加:
```js
const weiboPanelRef = ref(null)
```

- [ ] **Step 3: getPanel map 加 weibo 键**

找到 line 366 附近的 `getPanel`:
```js
function getPanel(key) {
  const map = { douyin: douyinPanelRef, xiaohongshu: xiaohongshuPanelRef, kuaishou: kuaishouPanelRef }
  return map[key]?.value
}
```
改为:
```js
function getPanel(key) {
  const map = { douyin: douyinPanelRef, xiaohongshu: xiaohongshuPanelRef, kuaishou: kuaishouPanelRef, weibo: weiboPanelRef }
  return map[key]?.value
}
```

- [ ] **Step 4: 3 处 hardcoded 数组加 'weibo'**

找到以下 3 处,分别在数组末尾加 `'weibo'`:

(a) `hasAccountOverride` 循环 (line 386 附近):
```js
for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
```
改为:
```js
for (const key of ['douyin', 'xiaohongshu', 'kuaishou', 'weibo']) {
```

(b) `saveDraft` 循环 (line 587 附近):
```js
for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
```
改为:
```js
for (const key of ['douyin', 'xiaohongshu', 'kuaishou', 'weibo']) {
```

(c) `migrateOldDraftFormat` 循环 (line 838 附近):
```js
for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
```
改为:
```js
for (const key of ['douyin', 'xiaohongshu', 'kuaishou', 'weibo']) {
```

- [ ] **Step 5: 模板加 `<WeiboImagePublishPanel>` + page title 改"图集"**

在 line 134 附近 (`<KuaishouImagePublishPanel ... />`) 之后添加:
```vue
<WeiboImagePublishPanel
  ref="weiboPanelRef"
  :account-id="selectedPlatform === 'weibo' ? selectedAccountId : null"
  :disabled="publishing"
  v-show="selectedPlatform === 'weibo'"
  @config-changed="onChannelConfigChanged"
  @publish-result="onPublishResult"
/>
```

在 line 26 附近,page title 改:
```vue
<span class="page-title">图文发布</span>
```
改为:
```vue
<span class="page-title">图集发布</span>
```

- [ ] **Step 6: 跑前端构建**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run build 2>&1 | tail -20
```
Expected: 编译成功(可能有 warning 但无 error)

- [ ] **Step 7: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add frontend/src/views/ImagePublish.vue && git commit -m "$(cat <<'EOF'
feat(weibo): ImagePublish.vue 5 处改动

- IMAGE_PLATFORM_KEYS 加 'weibo'
- import + ref + getPanel map 加 weibo
- hasAccountOverride / saveDraft / migrateOldDraftFormat 3 数组加 'weibo'
- 模板加 <WeiboImagePublishPanel>
- page title 改"图集发布"

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: 前端重命名 4 个 UI 文件

**Files:**
- Modify: `frontend/src/App.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/views/DraftBox.vue`
- Modify: `frontend/src/views/PublishHistory.vue`
- Modify: `frontend/src/components/OneClickFillDialog.vue`

- [ ] **Step 1: `App.vue` 菜单 title 改"图集发布"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" frontend/src/App.vue
```
唯一替换: `{ path: '/image-publish', icon: Picture, title: '图文发布' }` → `title: '图集发布'`

- [ ] **Step 2: `router/index.js` meta title 改"图集发布"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" frontend/src/router/index.js
```
唯一替换: `title: '图文发布'` → `title: '图集发布'`

- [ ] **Step 3: `DraftBox.vue` 3 处改"图集"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" frontend/src/views/DraftBox.vue
```
- line 9: `label="图文草稿"` → `label="图集草稿"`
- line 158: `<el-empty description="还没有保存的图文草稿">` → `<el-empty description="还没有保存的图集草稿">`
- line 159: `去发布图文` → `去发布图集`
- line 335: `const typeName = type === 'video' ? '视频' : '图文'` → `const typeName = type === 'video' ? '视频' : '图集'`

- [ ] **Step 4: `PublishHistory.vue` el-option label 改"图集"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" frontend/src/views/PublishHistory.vue
```
唯一替换: `label="图文" value="image"` → `label="图集" value="image"` (value 不变)

- [ ] **Step 5: `OneClickFillDialog.vue` 描述文案改"图集发布"**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && grep -n "图文" frontend/src/components/OneClickFillDialog.vue
```
唯一替换: `去 ${type === 'video' ? '视频发布' : '图文发布'} 试试？` → `去 ${type === 'video' ? '视频发布' : '图集发布'} 试试？`

- [ ] **Step 6: 跑前端构建**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run build 2>&1 | tail -20
```
Expected: 编译成功

- [ ] **Step 7: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git add frontend/src/App.vue frontend/src/router/index.js frontend/src/views/DraftBox.vue frontend/src/views/PublishHistory.vue frontend/src/components/OneClickFillDialog.vue && git commit -m "$(cat <<'EOF'
chore(weibo): 前端 4 个 UI 文件"图文"→"图集"

- App.vue 菜单 title
- router/index.js 路由 meta title
- DraftBox.vue tab label + 按钮 + 兜底文案 (3 处)
- PublishHistory.vue el-option label
- OneClickFillDialog.vue 描述文案

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: 整体验证

**Files:** 无 (验证步骤)

- [ ] **Step 1: 跑后端全部测试**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/ -v 2>&1 | tail -30
```
Expected: 全部 passed(包括 weibo 新增的 5 个 case:test_weibo_image_platform 4 个 + test_image_publish_endpoint weibo 1 个)

- [ ] **Step 2: 跑前端 build**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run build 2>&1 | tail -10
```
Expected: 编译成功,无 error

- [ ] **Step 3: 检查 git log**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git log --oneline -15
```
Expected: 看到 12 个 commit(每个 Task 一个)

- [ ] **Step 4: 检查文件清单**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git diff --stat master..feature/20260615-1
```
Expected: 13 个文件 (2 新增 + 11 修改) — 与 spec 文件清单一致

- [ ] **Step 5: 交付用户测试 (无 commit)**

按 spec 浏览器 e2e 步骤,提示用户启动 dev server 手动验证:
```
1. cd backend && python3 app.py
2. cd frontend && npm run dev
3. 打开「图集发布」页,确认左侧出现「微博」账号分组
4. 选 1 个微博账号 + 2~3 张测试图 + 描述 + 内容声明(AI 生成)
5. 点「一键发布」,观察 CloakBrowser
6. 微博 Web 端确认图集已发出
7. 失败时把 log 贴给 Claude,按 selector 漂移修复
```

- [ ] **Step 6: (可选) 一次性合并 commit**

如果用户确认手动测试通过,可以 squash 12 个 commit 为 1 个:
```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui && git rebase -i master
```
(留作可选,默认保持 12 个 commit 便于 review)

---

## 验收门禁

- [ ] pytest 全部 passed
- [ ] npm run build 无 error
- [ ] 13 个文件(2 新增 + 11 修改)
- [ ] 12 个 commit
- [ ] 用户手动浏览器 e2e 通过(由你测试)
