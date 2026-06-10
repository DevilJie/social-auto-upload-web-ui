# 发布历史详情页 + 列表卡片网格 — 设计 spec

日期：2026-06-10
作者：与用户协作完成
状态：已设计，待用户审阅

> 范围仅限前端列表 UI 重构 + 新增详情页 + 后端单个 batch 查询端点 + AccountSidebar 复用化。
> 与 2026-06-08 spec（统一主-子表结构）不冲突，本 spec 是其后续的"前端展示"层。

## 1. 背景与目标

### 1.1 当前问题

| # | 问题 | 严重性 |
|---|---|---|
| A | `PublishHistory.vue` 现在的 batch 卡是垂直单列（一行一张卡），屏幕宽时大量空间浪费 | 中 |
| B | 卡的「展开明细」交互把"批次"和"明细"挤在一张卡里，越多账号越长，越难扫读 | 中 |
| C | 没有专门的详情页，深查单个账号的发布内容（标题/描述/标签/声明/封面）得逐个展开 | 高 |
| D | 视频号/小红书等平台要求未来爬取播放/点赞/收藏/评论，目前 UI 上完全无入口 | 中（前置） |
| E | `AccountSidebar` 与发布流强耦合（依赖 Pinia accountStore、含 add/remove/override），其他场景无法复用 | 中 |

### 1.2 目标

1. 列表卡改为 4 列自适应网格（≥1200px 4 列，中等 2-3 列，最窄 1 列）
2. 列表卡一次性呈现：封面、标题、渠道汇总（×N 徽章）、发布时间、状态、4 个数据占位
3. 整卡可点 → 进入新增的详情页 `/publish-history/:batchId`
4. 详情页（按 `PublishCenter` 范式，账号栏在左、主区在右）复用 `AccountSidebar` readonly 模式展示该批次的所有账号
5. 详情页主区域选中账号后展示：账号头 + 内容快照 + 数据统计占位 + 批次元信息（折叠）
6. 后端新增 `GET /api/v2/history/<batch_id>` 单批次查询端点（直接 URL 访问、刷新、分享）
7. `AccountSidebar` 重构为接受外部账号列表 + `mode: 'edit'|'readonly'`，两套场景同源

### 1.3 严格范围

> **本设计只动列表 UI、详情页、新增 1 个后端端点、AccountSidebar 复用化。其他模块（平台实现、登录、素材库、发布流、任务队列）一律不动。**

> **UI 实施阶段（写代码时）必须调用 `ui-ux-pro-max-skill` 协助设计，避免普通 AI 直出审美。**（用户 2026-06-10 明确要求）

## 2. 数据模型

### 2.1 数据库

**不建新表。** 直接复用现有：
- `publish_batches`（批次表）
- `publish_details`（明细表）

详情查询端点只读这两张表。

### 2.2 端点

| 端点 | 用途 | 响应 |
|---|---|---|
| `GET /api/v2/history?type=&status=&timeRange=&startDate=&endDate=&page=&pageSize=` | 列表（已有） | `{code, data: {items, total}}`，items 内嵌 `items[]` 明细 |
| `GET /api/v2/history/<batch_id>` | **新增**：单批次详情 | `{code, data: Batch}`，结构与列表 item 一致（含 items[]） |
| 404 时 | | `{code: 404, msg: "记录不存在或已被删除"}` |

### 2.3 列表 item 客户端派生字段

`channels_summary` 在前端由 `items[]` 聚合：

```js
function computeChannelsSummary(items) {
  // 按 platform 分组，count = 该平台明细数
  const groups = {}
  for (const it of items) {
    const key = it.platform
    if (!groups[key]) groups[key] = { platform: key, name: it.platform, count: 0, logo: getPlatformLogo(key) }
    groups[key].count++
  }
  return Object.values(groups)
}
```

不存数据库，不加后端字段。

## 3. 路由

| 路径 | 组件 | 说明 |
|---|---|---|
| `/publish-history` | `PublishHistory.vue` | 列表（卡片网格重构） |
| `/publish-history/:batchId` | `PublishHistoryDetail.vue` | **新增**：详情页 |

`router/index.js` 增加一条路由记录，`name: 'PublishHistoryDetail'`，无 `meta`（不进入侧边菜单），懒加载组件。

## 4. 前端组件

### 4.1 列表卡（`PublishHistory.vue` 重构）

布局：CSS Grid `grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px;`

单卡（自上而下）：

| 顺序 | 元素 | 来源 / 规则 |
|---|---|---|
| 1 | 封面 | 16:9，`batch.cover_url`；无则灰色占位（沿用） |
| 2 | 标题 | `batch.title`（`|| '无标题'`），单行省略 |
| 3 | 渠道徽章行 | 调用 `computeChannelsSummary(batch.items)`（见 2.3）→ 传入 `<ChannelSummary :channels="..." :overflow-key="batch.id" />`；溢出时 marquee（沿用 `DraftBox.vue` 动画） |
| 4 | 时间 + 状态 | `batch.created_at`（24h 内 `formatRelativeTime`；否则 `MM-DD HH:mm`）+ `statusLabel(batch.status)` 标签 |
| 5 | 4 指标占位 | 复用 `PublishStats.vue` 组件，值固定 `--` |
| 6 | 整卡可点 | `cursor: pointer`，`@click="router.push('/publish-history/' + batch.id)"` |
| 7 | 悬停态 | 边框高亮（`$brand-start` 50% 透明）+ 阴影 |

**删除：** 全部「展开明细」相关代码（`.card-main` / `.card-details` / `.detail-card` 等）。

**保留：** 过滤工具栏、3 张统计卡、分页、空状态。

### 4.2 `ChannelSummary.vue`（新增）

Props：`channels: Array<{platform, name, count, logo}>`、`overflowKey: String|Number`（用于 marquee 检测的 ref key，可选）。

模板：与 `DraftBox.vue` 行的 `channels-track` + `channels-marquee` 完全一致；溢出检测函数从 `DraftBox.vue` 提取为局部 `isOverflow` 方法。

**不** 与 `DraftBox.vue` 共用组件（避免改一处影响另一处），代码小、复制更安全。

### 4.3 `PublishStats.vue`（新增）

Props（保留为未来扩展，但当前实现不依赖）：`views`、`likes`、`favorites`、`comments`（默认 `null`）。

模板：4 列等宽，图标（`VideoPlay` / `Star` / `Collection` / `ChatLineRound`）+ 值（null 时显示 `--`）+ `el-tooltip`（"数据统计功能开发中"）。

未来实现时把 4 个 prop 接上即可，组件 API 不变。

### 4.4 详情页（`PublishHistoryDetail.vue` 新增）

整体布局：`display: flex; flex-direction: row; height: 100%;`，与 `PublishCenter` 范式一致。

**顶部导航条（`page-header`）：**
- 左：`<` 返回按钮 → `router.push('/publish-history')`
- 中：批次标题（truncate）+ 状态标签 + 创建时间
- 高 56px，边框 1px bottom

**左侧栏（`detail-sidebar`，232px 宽，`flex-shrink: 0`）：**
- `<AccountSidebar mode='readonly' :accounts="..." :account-groups="..." ...>`
- 顶部徽章标题改"批次账号 (N)"
- 平台分组自动展开所有有账号的组（mount 时 `expandedGroups = new Set(readonlyAccountGroups.map(g => g.key))`）

**主区域（`detail-main`，`flex: 1`，`overflow-y: auto`）：**
纵向 4 区块，24px 间距：

1. **账号信息头**（`account-header`，数据源：`selectedItem`）
   - 头像（取 `account.name` 首字母，沿用 `AccountSidebar` 的样式）+ 平台徽章 + 账号名 + 状态标签（`failed` 显红标）+ 「查看发布作品」链接（仅 `selectedItem.status === 'success'` 且 `selectedItem.publish_url` 非空时渲染，`target="_blank" rel="noopener noreferrer"`）
   - 失败时**不**在此处显示错误信息（统一交给内容快照的红色卡），避免双处展示
2. **内容快照**（`content-snapshot`，数据源：`selectedItem`）
   - 成功时：左封面（16:9，160px 宽） + 右文字（标题/描述 2 行省略/标签 el-tag/作品声明/定时发布时间/发布耗时）
   - 失败时：整块降级为"发布失败"红色卡片，主体显示 `selectedItem.error_message`，无封面、无内容字段
3. **数据统计**（`data-stats`）
   - `<PublishStats />`，值 `--`
4. **批次元信息**（`batch-meta`，数据源：`batch` 本身，`<el-collapse>` 折叠，默认收）
   - 批次 ID（完整 UUID + 复制按钮）、批次 `schedule_time`（无则"未设置"）、`started_at`（无则"—"）、`finished_at`（无则"—"）、`account_count`（与侧边栏实际账号数对比，识别已删除账号）

**选中默认行为：** 详情页 mount 时若 `selectedAccountId` 为空：
1. 找 `batch.items` 中**第一个 `account_id` 存在且能在 `accountStore.accounts` 里找到**的 item
2. 用该 item 的 `account_id` 作为 `selectedAccountId`
3. 若所有 item 的 `account_id` 都找不到（账号全被删除 / store 未加载完）→ 走空状态分支

**数据派生：**
- `batchAccounts = computed(() => accountStore.accounts.filter(a => batch.value?.items.some(it => it.account_id === a.id)))` — 只含仍存在的账号
- `readonlyAccountGroups = computed(() => platformList.map(p => ({ key: p.key, name: p.name, logo: p.logo, color: p.color, letter: p.letter, accounts: batchAccounts.value.filter(a => a.platform === p.name) })).filter(g => g.accounts.length > 0))` — 空分组不渲染
- `expandedGroups = computed(() => new Set(readonlyAccountGroups.value.map(g => g.key)))` — mount 时默认全部展开
- `selectedItem = computed(() => batch.value?.items.find(it => it.account_id === selectedAccountId.value))`

**账号已删除的可见性：**
- 侧边栏**不**显示已删除账号（按 `batchAccounts` 过滤掉）
- 详情页 `account_count` 字段（批次元信息）= `items.length`（含已删除），与侧边栏展示的账号数会不一致 — 用户可由此识别"有账号已删除"

**空状态：**
- 后端 404 → 跳回 `PublishHistory` + toast "记录不存在或已被删除"
- `batch.items` 为空 / `batchAccounts` 为空 → 主区域"该批次暂无账号数据"

### 4.5 `AccountSidebar.vue` 重构

新增 props：

| prop | 类型 | 默认 | 说明 |
|---|---|---|---|
| `mode` | `'edit' \| 'readonly'` | `'edit'` | 控制编辑流相关元素 |

**不**新增 `accounts` prop — 组件渲染仍由 `accountGroups` 驱动（已有），readonly 场景下父组件直接把过滤后的子集构造成 `accountGroups` 传入即可。这样改动最小、不引入未使用 prop。

**模板分支：**

| 元素 | `mode='edit'` | `mode='readonly'` |
|---|---|---|
| `sidebar-footer`（`+ 添加账号`） | 渲染 | **隐藏** |
| `account-remove` 关闭按钮 | 渲染 | **隐藏** |
| `has-override` 角标 | 渲染 | **隐藏** |
| `group-accounts` 过滤（`publishAccountIds`） | 过滤 | 不过滤 |
| `group-count` 徽章 | 显示 `publishAccountIds` 中数量 | 显示该组账号总数 |

**事件约束：** readonly 模式下不会 emit `remove-account` / `open-account-dialog`（相应按钮不渲染）。

**调用方：**

`PublishCenter.vue`：
```vue
<AccountSidebar
  :mode="'edit'"
  :account-groups="accountGroups"
  :total-count="totalCount"
  :selected-platform="selectedPlatform"
  :selected-account-id="selectedAccountId"
  :expanded-groups="expandedGroups"
  :publish-account-ids="publishAccountIds"
  :has-account-override="hasAccountOverride"
  @toggle-group="toggleGroup"
  @select-account="selectAccount"
  @remove-account="removePublishAccount"
  @open-account-dialog="accountDialogVisible = true"
/>
```

`PublishHistoryDetail.vue`：
```vue
<AccountSidebar
  :mode="'readonly'"
  :account-groups="readonlyAccountGroups"
  :total-count="batchAccounts.length"
  :selected-platform="null"
  :selected-account-id="selectedAccountId"
  :expanded-groups="expandedGroups"
  :publish-account-ids="readonlyPublishAccountIds"
  :has-account-override="() => false"
  @toggle-group="toggleGroup"
  @select-account="selectAccount"
/>
```

`readonlyPublishAccountIds` 是详情页内 `const readonlyPublishAccountIds = new Set()`（空 Set，与 `accountGroups.accounts` 一一对应 → 不过滤）— 显式传空 Set 而不是 `new Set()` 在模板里每次渲染新建（避免不必要的依赖追踪）。

## 5. API 层

`frontend/src/api/v2.js`：

```js
export const historyApi = {
  getHistory(params) { /* 已有 */ },
  getBatch(batchId) {
    return http.get(`/api/v2/history/${batchId}`)
  },
}
```

## 6. 后端实现

### 6.1 端点位置

`backend/ext_api/__init__.py`，紧跟现有 `@ext_api.route('/history', methods=['GET'])` 之后。

### 6.2 路由

```python
@ext_api.route('/history/<batch_id>', methods=['GET'])
def get_history_batch(batch_id):
    """获取单个发布批次详情（包含所有明细）"""
    ...
```

### 6.3 行为

- 从 `publish_batches` 查 1 行
- 找不到 → 返回 `HTTP 404` + body `{"code": 404, "msg": "记录不存在或已被删除"}`（与现有 ext_api 错误格式一致：HTTP 状态码表达错误，body 也带 `code` 字段供前端 `res.code === 200` 检查）
- 找到 → 从 `publish_details WHERE batch_id = ?` 查所有明细
- 明细行 `account_configs` JSON 反序列化、`duration` 计算（沿用列表端点逻辑）
- 返回结构与列表 item 一致：`{id, type, title, ..., cover_url, account_count, success_count, failed_count, status, ..., items: [...]}`，外层包 `{"code": 200, "data": <batch>}`，HTTP 状态 200
- 复用 `_resolve_cover_url` / `_resolve_cover_from_path` / `compute_personalized` 等现有 helper
- 共用 `_to_beijing_time` 时间转换

### 6.4 性能

- 单批次 + 通常 < 20 明细，单查询足够
- 不分页（详情页全量加载）
- 不加新索引

## 7. 错误处理 & 边界

| 场景 | 表现 | 触发 |
|---|---|---|
| `/api/v2/history/<id>` 404 | 跳回列表 + toast | 后端返回 404 |
| `/api/v2/history/<id>` 5xx | 主区域顶部红条 + 重试按钮 | 网络/服务错误 |
| `batch.items` 为空 | 主区域"该批次暂无账号数据" | 数据异常 |
| `batchAccounts` 全空（账号全被删） | 主区域"该批次暂无账号数据" + 提示去「账号管理」 | 默认选中失败 |
| 单个 item 失败 | 内容快照降级为"发布失败"红色卡（仅错误信息），账号头只显失败状态标签 | `item.status === 'failed'` |
| 账号已被删除 | 侧边栏**不显示**该账号；`batch-meta` 的 `account_count` 与侧边栏实际数对比即可识别 | `account_id` 在 store 查不到 |
| `accountStore` 还没加载 | `onMounted` 串行：先 `setAccounts()` 再 `fetchDetail()` | 时序 |
| `expandedGroups` 默认 | mount 时填满所有有账号的平台 | 一次展开所有 |

**数据 placeholder 约定：**
- `PublishStats.vue` 内部值硬编码 `--`，未来接 `stats: {views, likes, favorites, comments}` 时把 4 个 prop 接上即可

## 8. 测试

### 8.1 后端

`backend/tests/test_history_detail_endpoint.py`（新增）：

| 用例 | 断言 |
|---|---|
| 存在 batch + 多个 items | 200；返回 batch 字段正确；items 长度正确；item 含 `account_configs`（已反序列化） |
| 不存在 batch | 404；msg 含"不存在" |
| 存在 batch 但 items 为空 | 200；items = `[]` |
| 账号已删除但 detail 仍在 | 200；item.account_name 仍保留历史值 |
| duration 计算 | item.duration 存在时返回秒数；缺 started/finished 时为 null |

### 8.2 前端组件

> 项目当前**未配置前端单元测试框架**（无 vitest / jest）。本 spec 不强行引入新依赖；组件正确性靠手工端到端（8.3）+ `AccountSidebar` 重构的 `PublishCenter` 回归覆盖。

如果后续要为前端加单元测试，建议放置：`frontend/src/components/__tests__/`，并使用 vitest。覆盖组件：

| 组件 | 用例 |
|---|---|
| `ChannelSummary.spec.js` | 渲染 N 个徽章；总宽度溢出时加 `channels-marquee` class |
| `PublishStats.spec.js` | 渲染 4 指标；值为 null 时显示 `--`；tooltip 文案正确 |
| `AccountSidebar.readonly.spec.js` | `mode='readonly'` 时 footer/remove/override 元素不在 DOM；所有账号可见；`select-account` 事件正常 emit |

### 8.3 端到端（手工）

1. 发布一次成功 + 失败混合批次 → 列表 4 列卡、卡上数据占位正常、点击进详情
2. 详情页侧边栏账号齐全、点不同账号切换主区内容
3. 直接 URL 访问详情刷新不丢
4. `PublishCenter` 侧边栏行为完全不变（回归）

## 9. 实施拆解（任务粒度）

按 [superpowers:writing-plans] 进一步细化到 2-5 分钟/任务。
本 spec 阶段只列大块：

1. 后端：新增 `GET /api/v2/history/<batch_id>` + 单元测试
2. 前端：`ChannelSummary.vue` + 单测
3. 前端：`PublishStats.vue` + 单测
4. 前端：重构 `AccountSidebar.vue`（加 props + mode 分支）+ 回归
5. 前端：调整 `PublishCenter.vue` 调用方（不改行为）
6. 前端：新增 `PublishHistoryDetail.vue`（页面 + 路由 + 4 个区块）
7. 前端：重构 `PublishHistory.vue` 列表为卡片网格（删展开视图、接 ChannelSummary/PublishStats）
8. 手工 e2e + UI 视觉走查

**UI 实施阶段强制调用 `ui-ux-pro-max-skill`**（写卡片网格样式、详情页布局、数据占位组件时）。

## 10. 风险与回退

| 风险 | 缓解 |
|---|---|
| `AccountSidebar` 重构影响 `PublishCenter` | 步骤 5 单独跑 PublishCenter 发布流程回归 |
| 卡片网格 CSS 在某些分辨率下错位 | 用 `auto-fill, minmax(280px, 1fr)` 自然断点，无 media query |
| 详情页直接刷新时 `accountStore` 还没好 | onMounted 串行：先 `setAccounts` 再 `fetchDetail` |
| 数据占位组件 props 未来变 | 组件 API 留好，prop 默认 null，未来传值即可 |

## 11. 后续工作（不做，仅记录）

- 真正的发布数据爬取（播放/点赞/收藏/评论）后端 + 前端接通
- 详情页支持按时间倒序的"批次"列表（如果想看某个视频的所有发布批次聚合）
- 列表卡支持"再次发布"快捷入口（用历史批次填充 PublishCenter）
