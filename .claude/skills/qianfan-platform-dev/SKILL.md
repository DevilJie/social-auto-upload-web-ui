---
name: qianfan-platform-dev
description: 千帆同步(QianfanSync)平台对接开发规范。对接新平台、增加平台设置字段、修复发布流程、创建平台数据源接口、排查平台自动化问题时使用。涵盖:创作中心逆向侦察、cookie 管理与重新登录、表单自动化定位经验、五层参数链路、dry-run 验证、前端数据源组件模式。
---

# 千帆平台对接开发规范

本项目无官方 API，一切平台能力都来自「逆向网页端流程 + CloakBrowser 浏览器自动化」。
本规范沉淀 2026-10 实战验证的完整方法论。

## 1. 开发模式总览

核心循环：**人工流程 → 无头侦察 → 代码实现 → dry-run 验证**。

- 平台没有可用 API → 模拟真人在创作中心的操作
- 平台 UI 改版 = 回到创作中心重新侦察一遍（选择器会失效）
- 一切定位优先用「文案/placeholder/固定语义 class」，禁用 `data-v-*` 随机串和 hash class

## 2. 侦察方法论（动手写代码前必做）

### 2.1 侦察脚本模板

复用 `backend/impl/_browser.py` 统一入口（不要自己 launch）：

```python
import sys; sys.path.insert(0, str(REPO / "backend"))
from impl._browser import create_browser, create_context

browser = await create_browser(headless=True)
context = await create_context(browser, storage_state=str(cookie_path))
page = await context.new_page()
```

四通道采集，视觉+结构对照定位：
1. **截图**（`full_page=True`）—— 用眼睛看布局
2. **DOM 元素清单**（`page.evaluate` 抓 input/button/label 的 text/class/placeholder）
3. **网络监听**（`page.on("response", ...)`）—— 找页面自己调的数据 API
4. **最终 URL** —— 判断是否被重定向到登录页

### 2.2 cookie 管理

- 存放：`data/cookiesFile/<账号uuid>.json`，Playwright `storage_state` 格式
- 账号映射：SQLite `user_info` 表（`type`=平台id，`filePath`=cookie文件名，`status`：**1=有效 0=失效**，注意 status 是最后一次检查的结果，可能过期）
- 验活：`GET http://127.0.0.1:5409/checkAccount?id=<账号id>`（会更新 status）
- **cookie 失效时发起重新登录**：`GET /login?type=<平台id>&id=<任意会话id>&account_id=<账号id>`
  - 有头浏览器弹出，用户扫码；SSE 事件流 `{"status": "200", "name": 昵称}` = 成功
  - 微博/vivo 等平台登录中途不推事件（读超时是正常的，窗口开着等用户操作即可）
- 平台 id 对照见 `backend/impl/registry.py::_populate_registry()`

## 3. 数据源接口的三种形态（按优先级选型）

| 形态 | 适用条件 | 性能 | 参照 |
|---|---|---|---|
| **纯 HTTP 直连** | 接口无 wbi/签名校验，cookie+UA+Referer 即可通过 | ~100ms | `bilibili_bp.py`（seasons/topic 接口） |
| **浏览器网络拦截** | 接口带签名，但页面会自动请求 | ~15-30s | 小红书合集（list_v2 带签名） |
| **浏览器 DOM 解析** | 数据只在 UI 交互后才渲染 | ~15-60s | 微博/vivo 合集、小红书 POI |

选型前先侦察：监听页面 XHR，看数据接口要不要签名。**判断依据**：URL 无
`w_rid/wts` 参数、带 cookie 裸请求返回 `code:0` 即可直连。

### 3.1 纯 HTTP 直连标准写法

参照 `bilibili_bp.py::_bili_api_get`：
- 从 storage_state JSON 解析 bilibili 域 cookie 拼 `Cookie` 头
- 带上 `User-Agent`（Chrome 146 实测通过）+ `Referer: 创作中心页` + `Origin`
- 同步 requests，超时 10s；**响应结构做宽兼容**（字段名未知时多候选取值）

### 3.2 浏览器方案必加 TTL 缓存

前端下拉是 `empty-behavior="load-all"`：**每次展开都调接口**。浏览器方案单次
15-60s，必须加 `blueprints/_platform_cache.py` 的进程内 TTL 缓存（5 分钟），
否则用户体验极差。只缓存成功结果；key 含 account_id（和 keyword，如搜索类）。

### 3.3 已知平台签名情报（2026-10 实测）

- B站 `x2/creative/web/seasons`、`x/vupre/web/topic/type/v2`、
  `x/vupre/web/tag/recommend`：**无签名**，可直连
- 小红书合集 `collection/pc/list_v2`：**带签名**，只能浏览器内获取
- 微博合集：无独立 XHR（内嵌表单流程），DOM 解析
- 必须重登录才能侦察的平台：先走 `/login` 扫码（见 2.2）

## 4. 表单自动化定位经验（血泪坑）

### 4.1 定位策略
- 优先文案：`page.get_by_text("文案", exact=True)`；标题是长串时（如「更多设置
  （含声明与权益…）」）exact 会失配，必须**子串匹配 + 可见性过滤**
- 组件库语义 class 可信：B站 `bcc-checkbox`/`bcc-radio`/`season-item-title`、
  小红书 `item-label` 是固定 class，非随机串
- **`has-text()` 会匹配所有祖先容器**——用 `div:has-text("x")` 后逐个
  `inner_text` 判断会卡死流程。改用 `get_by_text(exact=True)` 精确匹配
- el-select 新版触发器是 `.el-select__wrapper`（Element Plus 2.9）

### 4.2 交互模式
- **弹层/弹窗用完必须关闭**（点确认按钮或 Escape），否则遮罩拦截后续所有
  点击（`subtree intercepts pointer events` → 30s 超时崩流程）
- contenteditable 富文本：`click()` + `clear_and_type(page, text, delay=10)`；
  B站简介/粉丝动态都有 `data-placeholder` 可定位
- checkbox 先 `is_checked()` 再决定是否勾选；radio 点 label 文本
- `#` 话题前缀必须 CDP `Input.dispatchKeyEvent` 直发（Playwright keyboard 丢字符），
  参照 `impl/kuaishou/platform.py::_input_tags`

### 4.3 Python 层陷阱
- **`@staticmethod` 里没有 self**：抽方法时把 `self.helper()` 改成
  `ClassName.helper()`，否则 NameError 且常被 `except: continue` 吞掉，
  表现为"跳过"甚至重复执行
- 轮询等待给每个动作设**短超时**（scroll/click 5s），外层 `asyncio.wait_for`
  总超时 30s——防单点卡死拖垮整个发布流程
- 失败一律 `logger.warning` + 跳过（可选项不阻塞发布），必填项才抛异常

## 5. 新增平台设置字段的五层链路

一个平台参数从 UI 到自动化要动 5 处（以 B站 `bili_xxx` 为例）：

```
1. frontend/src/views/PublishCenter.vue   表单控件 + form 默认值 + 4 级合并
2. backend/app.py                          postVideo/postVideoBatch data.get 透传
3. backend/services/draft_merge.py         合并白名单 + snake_case 映射
4. backend/impl/platform_meta.py           fields 控件定义 + 默认值（MCP 自描述用）
5. backend/impl/<平台>/platform.py         kwargs 接收 → 自动化方法
```

- 命名惯例：前端 camelCase（`biliCollectionName`）→ 后端 snake_case（`bili_collection_name`）
- 平台专属参数带平台前缀，避免跨平台冲突（如 `xhs_collection_id` vs `collection_id`）
- `publish_video(self, **kwargs)` 各平台只取自己需要的 key，多余 kwargs 无害
- 前端数据源下拉组件：`RemoteSearchSelect`（props: fetcher/fieldMap/searchMode/
  emptyBehavior，参照 B站合集/话题用法）；数据源 API 放 `blueprints/<平台>_bp.py`

## 6. dry-run 验证流程（提交前必做）

1. `impl/bilibili/platform.py` 顶部 `_PUBLISH_DRY_RUN = True`（脚本里 monkey-patch）
2. 后台脚本调 `platform.publish_video(...)` 传真实参数 + 测试视频
   （`data/materials/` 下有 0.28MB 小视频；未提交的稿件 B站自动作废，不会发布）
3. **验证证据 = `data/logs/bilibili_before_submit.png`**（提交前自动全页截图）
   + bilibili 日志里的「发布调试」参数汇总
4. 验证脚本用**日志驱动退出**（轮询日志出现 DRY_RUN 标志），不要傻等固定时长
5. stderr 不要吞（`2>$null` 会丢异常栈），重定向到文件排查

## 7. UI 规范

- 下拉数据源统一用 `RemoteSearchSelect`；原生 el-select 用于静态选项
  （分区/声明），样式已在 `styles/index.scss` 与 setting-card 统一边距：
  触发器 `padding:6px 14px; min-height:40px`，弹层选项 `padding:8px 14px` + 项间 2px
- 组件改样式时用 `:deep()`，弹层是 teleport 到 body 的需非 scoped 全局块
- 截图/侦察产物放 `data/screenshots/`（运行时数据，不提交 git）

## 8. 对接新平台检查清单

- [ ] 侦察：创作中心 URL、发布流程、表单全字段（截图 + DOM 清单 + API 抓包）
- [ ] `impl/<平台>/platform.py` 实现 BasePlatform 五方法（login/check_cookie/
      open_creator_center/sync_profile/publish_video）
- [ ] `registry.py` 注册平台 id
- [ ] `platform_meta.py` 声明 fields + 默认值
- [ ] 前端平台卡片 + 数据源下拉（如需）
- [ ] dry-run 验证 + before_submit 截图核对
- [ ] 数据源接口选型（纯 HTTP > 拦截 > DOM）+ TTL 缓存
