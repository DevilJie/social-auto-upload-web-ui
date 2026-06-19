# AccountSelectDialog 三栏改造 — 设计文档

**日期：** 2026-06-19
**作者：** Claude
**状态：** 待用户审阅

---

## 1. 背景与目标

现有 `AccountSelectDialog.vue` 是发布中心（图集、视频）的"添加账号"弹窗，左右两栏：
- 左：渠道列表（单选 radio 风格）+ 标签筛选（单选 toggle 风格）混合
- 右：账号列表（el-checkbox 行式）

**问题：**
1. 渠道和标签都是单选 → 用户无法组合筛选
2. 账号用 checkbox 行式，不够直观 → 已选状态视觉弱
3. 标签可以"创建" → 但弹窗本意是"筛选账号"，创建标签是管理动作，混在一起
4. 没有"取消选择"反馈 → 误以为已取消但实际还保留

**目标：** 改造成左中右三栏，类似 BatchTagDialog 风格，但禁止创建新标签、支持多渠道 + 多标签筛选 + 已选账号高亮。

---

## 2. 设计要点

### 2.1 三栏布局

```
┌──────────────────────────────────────────────────────────────────────┐
│ ┌──────────┐ ┌─────────────────────────┐ ┌──────────────────────┐    │
│ │ 渠道筛选  │ │ 账号卡片网格             │ │ 标签筛选              │    │
│ │ ──── │ │ ──── │ │ ────           │    │
│ │ ☑ 小红书 │ │ [全选] 已选 3 / 8      │ │ 搜索: [_________]    │    │
│ │ ☑ 抖音   │ │ ┌──┐                  │ │ [全不选] 已选 2       │    │
│ │ ☐ B站    │ │ │● │ 小红书账号1     ✓ │ │ ──────────          │    │
│ │ ☑ 视频号 │ │ │  │ 小红书 [VLOG]     │ │ ☑ VLOG               │    │
│ │ ☐ 百家号 │ │ └──┘                  │ │ ☐ 美妆               │    │
│ │ ...     │ │ ┌──┐                  │ │ ☑ 美食               │    │
│ │         │ │ │● │ 抖音账号1       ✓ │ │ ...                  │    │
│ │         │ │ │  │ 抖音 [美妆]       │ │                      │    │
│ │         │ │ └──┘                  │ │                      │    │
│ └──────────┘ └─────────────────────────┘ └──────────────────────┘    │
│                                                                      │
│ [取消] [确认添加（已选 N 个账号）]                                    │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 关键改造点

| 现状 | 改造后 |
|------|--------|
| 渠道单选 radio | 渠道多选 checkbox |
| 标签单选 toggle | 标签多选 checkbox（OR 语义） |
| 渠道 + 标签混在同一栏 | 渠道独立左栏，标签独立右栏 |
| 账号用 el-checkbox 行 | 卡片网格，复用 `.batch-account-card` 样式 |
| 标签区有"新建"功能 | 标签区只筛选，**禁止新建** |
| 无"全不选"快捷 | 标签区加"全不选"按钮 |
| 选中仅靠 checkbox ✓ | 卡片右上角 ✓ 圆圈 + 高亮边框 |

### 2.3 筛选逻辑

中间账号列表 = `accounts.filter(a =>`

- ✅ 黑名单过滤（保持现有）
- ✅ `(selectedPlatformKeys.size === 0 || selectedPlatformKeys.has(a.platform))` — 空集 = 不过滤
- ✅ `(selectedTagIds.size === 0 || a.tags?.some(t => selectedTagIds.has(t.id)))` — OR 语义
- ✅ `a.status === '正常'`（保留用于"一键全选"和"已选数"统计）

### 2.4 一键全选

作用于"当前可见且有效"的账号（即同时受渠道/标签筛选影响）。与 BatchTagDialog 一致。

### 2.5 取消同步

`tempSelectedAccounts` 是单一真相源：
- 用户点击卡片 → toggle（添加/移除）
- 用户点击"一键全选"→ 加入所有可见有效账号
- 用户点击"取消全选"→ 仅从可见有效账号中移除（保留已选但被筛选过滤掉的账号）
- 用户点击"确认" → `emit('confirm', [...tempSelectedAccounts])`

**已被筛选过滤掉的已选账号仍保留** — 用户没主动取消，确认时仍带上。这是合理的（"被筛掉了但你之前选过"）。

---

## 3. Props 与事件（向后兼容）

```javascript
defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array, required: true },        // 现有，可显示渠道列表
  publishAccountIds: { type: Set, required: true },  // 现有，已选 ID
})

defineEmits(['update:modelValue', 'confirm'])
```

**不修改 props 接口** — PublishCenter.vue 和 ImagePublish.vue 的调用方无需改动。

---

## 4. 状态

```javascript
const selectedPlatformNames = ref(new Set())  // 已选渠道（name 形式，与 a.platform 对齐）
const selectedTagIds = ref(new Set())
const tempSelectedAccounts = ref([])  // 已选账号 ID 数组
const tagKeyword = ref('')  // 标签搜索
```

**初始状态：**
- `tempSelectedAccounts` 从 `props.publishAccountIds` 拷贝（保留现有行为）
- `selectedPlatformNames`、`selectedTagIds` 都为空（让用户主动筛选）
- `tagKeyword` 为空

---

## 5. 视觉规范（复用 BatchTagDialog）

### 5.1 账号卡片（复用 + 适配）

复用 `BatchTagDialog.vue` 中的 `.batch-account-card` 样式：

- 左侧头像圆形 28x28
- 中间账号名 + 平台 tag pill
- 选中态：背景 brand-start 0.12 透明 + 边框 brand-start + 右上角 ✓
- 失效态：opacity 0.45 + cursor not-allowed

**与 BatchTagDialog 的差异：**
- 顶部加"一键全选"按钮 + 计数
- 不显示"删除"图标（这是筛选，不是管理）

### 5.2 渠道筛选（左栏）

- 复选框 + 平台 logo + 名称
- 全选/全不选：本弹窗不加（用户可逐个取消），保持简单
- 多选：勾选状态用 `:checked` + `el-checkbox`

### 5.3 标签筛选（右栏）

- 顶部搜索框
- "全不选"按钮（取消所有已选 tag）
- 标签 chip 多选
- **禁止"新建"** 按钮（删除现有 `handleCreate` 和 `.batch-tag-create` 内的 append）

### 5.4 整体宽度

将 dialog `width` 从 680px 提升到 960px（容纳三栏）。

---

## 6. 数据流图

```
┌──────────────────────────────────────────────────────────┐
│ 用户点击"添加账号"按钮（PublishCenter / ImagePublish）      │
│   ↓                                                       │
│ <AccountSelectDialog v-model :publishAccountIds />        │
│   ↓ open                                                   │
│ onOpen():                                                  │
│   - tempSelected = [...publishAccountIds]                 │
│   - selectedPlatformNames = new Set()                     │
│   - selectedTagIds = new Set()                            │
│   ↓                                                       │
│ 用户筛选（左/右栏）                                       │
│   ↓                                                       │
│ 中间账号列表 = accounts.filter(...)                        │
│   ↓                                                       │
│ 用户点击卡片 / 全选                                       │
│   ↓                                                       │
│ tempSelectedAccounts 更新                                 │
│   ↓                                                       │
│ 用户点击确认                                              │
│   ↓                                                       │
│ emit('confirm', [...tempSelectedAccounts])                │
│   ↓                                                       │
│ 父组件更新 publishAccountIds                              │
└──────────────────────────────────────────────────────────┘
```

---

## 7. 边界处理

1. **已选账号被筛选过滤掉**：保留在 tempSelectedAccounts，footer 计数包含它（用户没主动取消）。
2. **失效账号（status !== '正常'）**：
   - 仍显示但置灰
   - 不参与一键全选（与现状一致）
3. **黑名单渠道过滤**：保留现状 — 调用方传 `platforms` 时已过滤。
4. **空标签列表**：`accountStore.allTags` 为空时，右栏显示 "暂无标签"，不显示搜索框（避免无意义交互）。
5. **空账号列表**：中间显示 "暂无可选账号"。

---

## 8. 测试

### 8.1 单元（可选）

如果项目有 vitest setup，可加。但根据当前结构，多数用 Playwright。

### 8.2 Playwright e2e

- 打开 AccountSelectDialog → 三栏可见
- 勾选 2 个渠道 + 2 个标签 → 中间只显示同时命中的账号
- 全选 → 顶部计数 = 中间可见有效账号数
- 取消某个已选 → footer 计数 -1
- 确认 → emit('confirm', [...]) 父组件 publishAccountIds 同步

### 8.3 视觉对照

- 改造前后截图对比
- 与 BatchTagDialog 视觉一致性（卡片样式对齐）

---

## 9. 影响范围

**修改文件：**
- `frontend/src/components/AccountSelectDialog.vue`（主改造）

**无需修改（向后兼容）：**
- `frontend/src/views/PublishCenter.vue` — 调用方不变
- `frontend/src/views/ImagePublish.vue` — 调用方不变

**样式复用：**
- 抽取共享 SCSS 到 `frontend/src/styles/account-card.scss`（可选，避免复制粘贴）

---

## 10. 风险

| 风险 | 缓解 |
|------|------|
| 用户已习惯单选 → 多选切换 | 加 tooltip 提示多选 + OR 逻辑；保留"全部平台"复选状态（空集=不过滤） |
| 标签禁止创建 → 找不到新标签怎么办 | 用户应在 Settings/账号管理页创建标签后再来筛选 |
| 多选平台性能问题 | 账号数量不大（一般 < 100），filter 性能没问题 |
| Playwright locator 改动 | 保留 v-model / el-checkbox role，使用 placeholder/label 定位 |

---

## 11. 排期

1. 重构组件结构（三栏 + 多选状态）
2. 复用 BatchTagDialog 卡片样式（直接 import 或抽公共 SCSS）
3. 标签区去掉"新建"按钮
4. 删除已选账号过滤的逻辑（保留）
5. Playwright 验证 + 手动验证

单 phase 可完成，预计 1-2 个 commit。