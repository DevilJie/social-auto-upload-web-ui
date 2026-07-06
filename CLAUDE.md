# CLAUDE.md

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.


## 5.Learn to Use Context7 MCP

**Avoid overly complex implementations and outdated tech stacks.**

If your implementation solution is overly complicated, stop development immediately. Then use the Context7 MCP service to check the latest technical documentation and implement it in a more elegant way.

## 6. Playwright 自动化输入技巧（contenteditable 富文本）

向 contenteditable 富文本输入标签、话题等需要触发 React onChange/onComposition 的内容时，**逐字符输入**比剪贴板粘贴可靠很多。

### 推荐：`locator.press_sequentially(text, delay=N)`

```python
editor = page.locator('.EditorArea [contenteditable="true"]')
await editor.press_sequentially(" #新疆", delay=150)  # 自动 focus，逐字符
await asyncio.sleep(2)  # 等待 React 监听完成
await page.keyboard.press(" ")  # 激活联想（如话题标签）
```

**优点**：
- **自动 focus 到该元素**，不用先 `editor.click()`
- **正确触发 React 合成事件**（compositionstart / input / change），比 `keyboard.type` 更可靠
- `delay` 控制每个字符间隔（ms），150ms 既人眼可辨又不太慢

### 不推荐：`page.keyboard.type(text, delay=N)`

- 不会自动 focus，需要先 click
- 在 React 富文本上可能丢 onChange 事件
- 官方推荐改用 `press_sequentially`

### 激活"#"话题标签的标准流程

知乎/微博等内容平台的 `#xxx` 话题标签需要空格触发联想。完整流程：

```python
for tag in parsed_tags:
    text = f" #{tag}"
    await editor.press_sequentially(text, delay=150)  # 1. 逐字符输入 #xxx
    await asyncio.sleep(2)                            # 2. 等 React 监听完成
    await page.keyboard.press(" ")                    # 3. 单独按空格激活话题
    await asyncio.sleep(0.5)                          # 4. 等激活动画
```

**常见误区**：
- ❌ 用 `clipboard.writeText` + `Control+V` 粘贴整段：React 监听经常丢字符
- ❌ 把空格和 `#xxx` 一起粘贴：无法触发联想
- ❌ 按完空格立刻进行下一步：标签芯片还没渲染

### 模拟键盘输入 `#`（话题前缀）—— CDP 直发

`#` 在 US 键盘布局上是 `Shift + Digit3`,**Playwright 的 keyboard 抽象在 Shift 修饰下会丢字符** —— `keyboard.press("Shift+3")` 与 `keyboard.down("Shift") + down("3") + up("3") + up("Shift")` 实测都会让快手等平台识别成数字 `3` 而不是 `#`,导致话题样式不触发、`#` 后字符无法被识别为话题内容。

**Playwright `keyboard.*` 各 API 实测行为**：

| API | 插入字符 | event.key | shiftKey | React onKeyDown | React onChange |
|---|---|---|---|---|---|
| `keyboard.press("Shift+3")` | `#`(理论) / `3`(实测) | `#` / `3` | true | ✓ | ✓ |
| `keyboard.press("3")` | `3` | `3` | false | ✓ | ✓ |
| `keyboard.press("#")` | — | — | — | **抛 `Unknown key: "#"`** | — |
| `keyboard.type("#")` | `#`(走 insertText) | 无 keydown | — | ✗ | ✓ |
| `keyboard.insert_text("#")` | `#` | 无 keydown | — | ✗ | ✓ |

**唯一可靠方案：CDP `Input.dispatchKeyEvent` 直发**,绕过 Playwright keyboard 抽象,显式告诉 Chromium "这次按键的 text 是 # 且带 Shift 修饰"：

```python
# 1. 获取 CDP session(同一 page/context 复用)
cdp = await page.context.new_cdp_session(page)

# 2. 显式发送带 text='#' 的 keyDown + keyUp
#    modifiers 位掩码: 1=Alt 2=Ctrl 4=Meta 8=Shift
await cdp.send("Input.dispatchKeyEvent", {
    "type": "keyDown",
    "key": "#",
    "code": "Digit3",
    "text": "#",
    "modifiers": 8,                # 8 = Shift
    "windowsVirtualKeyCode": 51,   # VK_3
})
await cdp.send("Input.dispatchKeyEvent", {
    "type": "keyUp",
    "key": "#",
    "code": "Digit3",
    "modifiers": 8,
    "windowsVirtualKeyCode": 51,
})

# 3. 等 500ms 让 React onKeyDown/onChange 完成 setState,激活"# 触发话题"识别状态
await asyncio.sleep(0.5)

# 4. 再用 press_sequentially 逐字输入标签内容
await element.press_sequentially(tag, delay=150)
```

**为什么 CDP 能 work、Playwright keyboard 不能**：
- Playwright keyboard 抽象在内部 `usKeyboardLayout` 查 Digit3 时,把 `shifted` 字段替换 text 后应输出 `#`,但实测在 CloakBrowser / Chromium 派生环境下 key 字段没替换为 shifted 字符
- CDP `Input.dispatchKeyEvent` 直接接收开发者传入的 `key`/`text`,由 Chromium 原样派发 DOM 事件,JS 端读到的 `event.key='#'`、`event.shiftKey=true`,与真人按键完全一致

**适用场景**：
- 快手、小红书、抖音、B 站、视频号等内容平台的"输入 # 后联想话题"功能
- 任何要求 JS 端读到 `event.key='#'` + `event.shiftKey=true` 的 React onKeyDown 处理器(输入法候选框、@ 弹框、自动补全)

**参考实现**：`backend/impl/kuaishou/platform.py` 的 `_input_tags` 方法(line ~772),已落地完整逻辑(CDP # → 500ms 等待 → press_sequentially 逐字 → 选中 _active_ 高亮项 → 空格兜底)。



---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


## 项目概述

社交媒体自动上传桌面工具，支持 10 个平台：小红书、视频号、抖音、快手、百家号、B站、TikTok、YouTube、腾讯视频、爱奇艺。通过 Tauri 2 打包为 Windows 桌面应用，内嵌 Python 后端和 Vue 前端。

## 架构

**三层结构：** Tauri 桌面壳 → Vue 前端 → Flask API → 平台自动化（Playwright + CloakBrowser）

### 后端 (`backend/`)

- **框架：** Flask，生产环境用 Waitress 托管，端口 5409
- **入口：** `backend/app.py` — 包含大部分路由（文件上传、账号 CRUD、SSE 登录、发布调度），注册两个 Blueprint：`ext_api`（任务队列）和 `frames_bp`（抽帧管理）
- **数据库：** SQLite `data/db/database.db`，schema 在 `backend/init_db.py` 定义，表包括 `user_info`、`file_records`、`publish_tasks`、`publish_logs`、`settings`、`drafts`
- **配置：** `backend/conf.py` — `BASE_DIR` 指向 `data/`（打包模式通过 `SAU_DATA_DIR` 环境变量覆盖），Chrome 路径自动检测
- **日志：** `backend/util/_logger.py` — `get_channel_logger()` 工厂函数

### 平台实现（Registry 模式）

`backend/impl/registry.py` 维护 platform_id → class 的映射，通过延迟导入注册。每个平台在 `backend/impl/<平台名>/platform.py` 中实现，继承 `BasePlatform`（`backend/impl/base_platform.py`）。

**抽象方法：** `login`、`check_cookie`、`open_creator_center`、`sync_profile`、`publish_video`

**平台 ID：** 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺, 11=微博

浏览器自动化通过 `backend/impl/_browser.py` 的 CloakBrowser（隐匿 Chromium）实现。

### 前端 (`frontend/`)

- **框架：** Vue 3 + Vite + Element Plus + Pinia + Vue Router
- **端口：** 5173（dev）
- **主视图：** `PublishCenter.vue`（核心发布界面）、`AccountManagement.vue`、`Dashboard.vue`、`Settings.vue`
- **状态管理：** `frontend/src/stores/`（app.js、account.js、user.js）
- **API 层：** `frontend/src/api/` — 按模块拆分（accounts、drafts、frames、materials、users）

### Tauri 桌面应用 (`src-tauri/`)

- Tauri 2 + Rust，`src-tauri/tauri.conf.json` 配置打包资源（Python 后端、前端 dist、CloakBrowser 二进制）
- `src-tauri/src/lib.rs` — WebView2 检测、数据目录管理、资源同步
- 目标平台：Windows NSIS 安装包

## 常用命令

### 启动前检查

端口被占用时先 kill：
```bash
lsof -i :5409 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
lsof -i :5173 | grep -v "^COMMAND" | awk '{print $2}' | xargs -r kill -9
```

### 后端

```bash
cd backend && python3 app.py          # 启动开发服务器 (端口 5409)
pip install -r backend/requirements.txt  # 安装 Python 依赖
python backend/init_db.py              # 初始化/迁移数据库
```

### 前端

```bash
cd frontend && npm run dev             # 启动开发服务器 (端口 5173)
cd frontend && npm run build           # 构建生产版本
```

### Tauri 桌面应用

```bash
cd src-tauri && cargo tauri dev        # 开发模式
cd src-tauri && cargo tauri build      # 构建桌面安装包
```

## 开发注意事项

- 后端 `app.py` 是单文件路由（~900 行），新增路由优先考虑放到 Blueprint 中
- 平台实现使用 Registry 模式，新增平台需在 `registry.py` 的 `_populate_registry()` 中注册
- 前端 `PublishCenter.vue` 是最复杂的组件（86KB），修改需谨慎
- 数据目录 `data/` 包含运行时数据（数据库、cookies、视频、日志），不要提交到 git
- 所有 git commit message 必须使用中文
