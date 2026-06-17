# 批量设置弹窗 设计文档

**日期**: 2026-06-17
**分支**: `feature/20260615-1`
**作者**: Claude (brainstorming + implementation)

## 目标

在「视频发布」和「图集发布」页面的右上角各加一个「批量设」按钮。点击后弹出一个对话框（el-dialog），内含 4 行表单（标题 / 描述 / 标签）+ 渠道小卡片网格（logo + 渠道名 + 已选账号数量）。用户填入内容、勾选目标渠道（默认全选），点「应用」即可一键覆盖到所选渠道的**渠道级**配置，以及该渠道下已开启账号个性化账号的**账号级**配置。

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 弹窗输入模式 | 共享输入区 + 渠道卡片复选 | 用户指定，避免每渠道一组输入的视觉冗余 |
| 渠道卡片范围 | 所有 `platformList` 中的渠道 | 用户指定「显示所有渠道」 |
| 卡片元数据 | logo + 渠道名 + `publishAccountIds` 中该渠道的账号数量 | 直观反映「应用到几个账号」 |
| 默认选中 | 数量 > 0 的渠道默认全选 | 0 账号渠道置灰不可选 |
| 写入策略 | 覆盖（非合并） | 用户指定，空字段会清空原值 |
| 写入目标 | 渠道级 + 该渠道下已开 `accountChecked` 的账号写到账号级 | 用户指定「智能模式」 |
| 实现抽象 | 公共 dialog + 两个 apply composable（视频/图集各一） | UI 0 重复，逻辑中心化 |
| 按钮位置 | 视频/图集页面顶部右侧，在「一键填写」和「一键发布」之间 | 与现有按钮组风格一致 |
| 输入框预填 | 打开时为空 | 避免误覆盖；用户明确「批量设」是设置新值 |

## 范围

### 在范围内

1. 新组件 `BatchSetDialog.vue`（公共）
2. 新 composable `useBatchSetApply.js`（视频专用）
3. 新 composable `useImageBatchSetApply.js`（图集专用）
4. 扩展 `useChannelForm.js` 的 `publicApi`，新增 `setPlatformConfig` 和 `setAccountOverride` 方法（图集 panel 需要）
5. `PublishCenter.vue` 头部加按钮 + 引入 dialog + 接入 apply
6. `ImagePublish.vue` 头部加按钮 + 引入 dialog + 接入 apply
7. 单元测试：useBatchSetApply 覆盖逻辑
8. 单元测试：useChannelForm 新增方法
9. E2E（gstack `/qa`）验证批量设流程

### 不在范围内

- 公共区域（视频/封面/图片）的批量设
- 平台特有字段（视频格式 / 群聊 / 合集 / 声明 / 定时等）的批量设
- 跨类型互通（视频批量设不联动图集）
- 批量设历史记录 / 撤销
- 改后端 API / 数据库

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│  PublishCenter.vue / ImagePublish.vue                       │
│    顶部右侧：在「一键填写」和「一键发布」之间加「批量设」    │
│    点击 → batchSetDialogOpen = true                         │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  BatchSetDialog.vue (公共)                                  │
│    Props:                                                   │
│      modelValue (弹窗显隐)                                  │
│      platforms (Array<{key, name, logo, count}>)            │
│    内部:                                                    │
│      4 行表单 (title / description / tags)                  │
│      渠道卡片网格（默认全选 count>0 的）                    │
│      「应用到 X 个渠道」按钮                                │
│    Emits:                                                   │
│      update:modelValue, apply(checkedKeys, payload)         │
└──────────┬─────────────────────┬────────────────────────────┘
           │                     │
           ▼                     ▼
┌─────────────────────┐  ┌──────────────────────────┐
│ useBatchSetApply    │  │ useImageBatchSetApply    │
│ (视频)              │  │ (图集)                   │
│ 直接改              │  │ 改用 panel.publicApi     │
│ platformConfigs     │  │ .setPlatformConfig(...)  │
│ + accountOverrides  │  │ .setAccountOverride(...) │
└─────────────────────┘  └──────────────────────────┘
```

## 组件设计

### 1. `BatchSetDialog.vue`（公共，纯展示）

#### Props

```ts
defineProps({
  modelValue: { type: Boolean, required: true },   // 弹窗显隐
  platforms: {                                                  // 渠道卡片元数据
    type: Array,
    required: true,
    // 形如 [{ key, name, logo, count: 已选账号数 }]
  },
  title: { type: String, default: '批量设置' },     // 弹窗标题
})
```

#### Emits

```ts
defineEmits(['update:modelValue', 'apply'])
// apply 触发：emit('apply', checkedKeys, payload)
// payload: { title, description, tags: string[] }
```

#### 内部状态

- `formTitle` / `formDescription` / `formTags`：3 行表单 v-model
- `checkedKeys`：Set<string>，渠道卡片勾选状态
- 弹窗打开（`modelValue` 由 false→true）时：
  - 表单 3 字段清空
  - `checkedKeys` = `new Set(platforms.filter(p => p.count > 0).map(p => p.key))`

#### 模板结构

```vue
<el-dialog
  :model-value="modelValue"
  @update:model-value="emit('update:modelValue', $event)"
  :title="title"
  width="720px"
  top="8vh"
>
  <el-form label-width="60px">
    <el-form-item label="标题">
      <el-input v-model="formTitle" maxlength="100" show-word-limit />
    </el-form-item>
    <el-form-item label="描述">
      <el-input v-model="formDescription" type="textarea" :rows="3" maxlength="500" show-word-limit />
    </el-form-item>
    <el-form-item label="标签">
      <TagInput v-model="formTags" :max="10" />
    </el-form-item>
    <el-form-item label="渠道">
      <div class="channel-grid">
        <div
          v-for="p in platforms"
          :key="p.key"
          :class="['channel-card', { 'is-checked': checkedKeys.has(p.key), 'is-disabled': p.count === 0 }]"
          @click="toggleKey(p.key)"
        >
          <img v-if="p.logo" :src="p.logo" class="channel-logo" :alt="p.name" />
          <span class="channel-name">{{ p.name }}</span>
          <span class="channel-count">{{ p.count }} 账号</span>
        </div>
      </div>
    </el-form-item>
  </el-form>

  <template #footer>
    <el-button @click="emit('update:modelValue', false)">取消</el-button>
    <el-button
      type="primary"
      :disabled="checkedKeys.size === 0"
      @click="handleApply"
    >
      应用到 {{ checkedKeys.size }} 个渠道
    </el-button>
  </template>
</el-dialog>
```

#### 卡片视觉

- 默认（未选）：浅边框 + 透明背景
- 选中：品牌色边框 + 浅品牌色背景 + 右上角 ✓
- 0 账号：灰边框 + 0.4 透明度 + cursor: not-allowed
- hover（可选）：边框加深

### 2. `useBatchSetApply.js`（视频专用）

#### 签名

```js
export function useBatchSetApply({
  platformConfigs,    // reactive object, key=platformKey
  accountOverrides,   // reactive object, key=accountId
  accountChecked,     // reactive object, key=accountId
  accountStore,       // Pinia store, 用来按 platform 找账号
}) {
  return {
    applyBatchSet(checkedPlatformKeys, payload) { ... }
  }
}
```

#### 行为

```js
function applyBatchSet(checkedPlatformKeys, payload) {
  const { title, description, tags } = payload
  for (const pk of checkedPlatformKeys) {
    // 1. 写渠道级（覆盖）
    if (!platformConfigs[pk]) platformConfigs[pk] = {}
    platformConfigs[pk].title = title
    platformConfigs[pk].description = description
    platformConfigs[pk].tags = [...tags]

    // 2. 写该渠道下已开 accountChecked 的账号
    const platformCfg = getPlatformByKey(pk)
    if (!platformCfg) continue
    const accounts = accountStore.accounts.filter(a => a.platform === platformCfg.name)
    for (const acc of accounts) {
      if (accountChecked[acc.id]) {
        if (!accountOverrides[acc.id]) accountOverrides[acc.id] = {}
        accountOverrides[acc.id].title = title
        accountOverrides[acc.id].description = description
        accountOverrides[acc.id].tags = [...tags]
      }
    }
  }
}
```

#### 接入 PublishCenter

```js
import { useBatchSetApply } from '@/composables/useBatchSetApply'
import { getPlatformByKey } from '@/config/platforms'
import { useAccountStore } from '@/stores/account'

const accountStore = useAccountStore()
const { applyBatchSet } = useBatchSetApply({
  platformConfigs, accountOverrides, accountChecked, accountStore,
})

const batchSetDialogOpen = ref(false)
const batchSetPlatforms = computed(() => {
  return platformList.map(p => {
    const platformAccounts = accountStore.accounts.filter(a => a.platform === p.name)
    const selectedCount = platformAccounts.filter(a => publishAccountIds.has(a.id)).length
    return { key: p.key, name: p.name, logo: p.logo, count: selectedCount }
  })
})

function onBatchSetApply(checkedKeys, payload) {
  applyBatchSet(checkedKeys, payload)
  batchSetDialogOpen.value = false
  ElMessage.success(`已批量设置到 ${checkedKeys.length} 个渠道`)
}
```

#### 模板

在 `.header-right` 内、`<el-button @click="oneClickDialogOpen = true">一键填写</el-button>` 之后加：

```vue
<el-button :icon="Setting" @click="batchSetDialogOpen = true" :disabled="publishAccountIds.size === 0">
  批量设
</el-button>
```

并在文件底部 import dialog + 注册：

```vue
<BatchSetDialog
  v-model="batchSetDialogOpen"
  :platforms="batchSetPlatforms"
  @apply="onBatchSetApply"
/>
```

### 3. `useImageBatchSetApply.js`（图集专用）

#### 签名

```js
export function useImageBatchSetApply({ panels }) {
  // panels: Map<platformKey, panelRef>  来自 ImagePublish 的 panel refs
  return {
    applyImageBatchSet(checkedPlatformKeys, payload) { ... }
  }
}
```

#### 行为

```js
function applyImageBatchSet(checkedPlatformKeys, payload) {
  const { title, description, tags } = payload
  for (const pk of checkedPlatformKeys) {
    const panel = panels.get(pk)
    if (!panel?.publicApi) continue

    // 1. 写 panel 内的 platformConfig（覆盖）
    panel.publicApi.setPlatformConfig({ title, description, tags })

    // 2. 写该 panel 下已开 accountChecked 的账号
    const accountIds = panel.publicApi.getCheckedAccountIds?.() || []
    for (const aid of accountIds) {
      panel.publicApi.setAccountOverride(aid, { title, description, tags })
    }
  }
}
```

#### 接入 ImagePublish

`ImagePublish.vue` 已有 `panelRefs` map（按 platformKey 存 panel 组件 ref）。新增：

```js
import { useImageBatchSetApply } from '@/composables/useImageBatchSetApply'

const { applyImageBatchSet } = useImageBatchSetApply({ panels: panelRefs })

const batchSetDialogOpen = ref(false)
const batchSetPlatforms = computed(() => {
  return platformList
    .filter(p => p.key in panelRefs.value)  // 已经有 panel 的平台
    .map(p => {
      const panel = panelRefs.value[p.key]
      const selectedCount = panel?.publicApi?.getSelectedAccountCount?.() ?? 0
      return { key: p.key, name: p.name, logo: p.logo, count: selectedCount }
    })
})

function onBatchSetApply(checkedKeys, payload) {
  applyImageBatchSet(checkedKeys, payload)
  batchSetDialogOpen.value = false
  ElMessage.success(`已批量设置到 ${checkedKeys.length} 个渠道`)
}
```

模板同视频：在「一键填写」后插入「批量设」按钮 + 注册 dialog。

### 4. `useChannelForm.js` 扩展

图集 panel 内部用 `useChannelForm`。需要扩展 publicApi：

#### 新增方法

```js
publicApi: {
  // 已有：publish, getConfigs, restoreConfigs, syncTitle, syncDescription, syncTags, validate, hasAccountOverride

  // 新增：
  setPlatformConfig(partial) {
    // partial = { title?, description?, tags? }（只覆盖提供的字段，覆盖策略与 apply 一致）
    for (const [k, v] of Object.entries(partial)) {
      if (v === undefined) continue
      platformConfig[k] = Array.isArray(v) ? [...v] : v
      form[k] = Array.isArray(v) ? [...v] : v
    }
    emit('config-changed')
  },

  setAccountOverride(accountId, partial) {
    const existing = accountOverrides[accountId] || {}
    const next = { ...existing }
    for (const [k, v] of Object.entries(partial)) {
      if (v === undefined) continue
      next[k] = Array.isArray(v) ? [...v] : v
    }
    if (Object.values(next).some(hasValues)) {
      accountOverrides[accountId] = next
    } else {
      delete accountOverrides[accountId]
    }
    if (accountId === props.accountId) {
      applyToForm(getMergedConfig(accountId))
    }
    emit('config-changed')
  },

  getCheckedAccountIds() {
    return Object.entries(accountOverrides)
      .filter(([_, v]) => hasMeaningfulOverride(v))
      .map(([id]) => Number(id))
  },
}
```

**注意**：图集 panel 内部目前没有 `accountChecked`（图集没有"平台个性化"勾选，每个平台就是单独一个 panel）。但 panel 内的 `accountOverrides` 已经表达了"哪些账号有覆写"，所以 `getCheckedAccountIds` 用 `hasMeaningfulOverride` 判断已开个性化的账号。

## 数据流

### 视频

1. 用户点「批量设」→ `batchSetDialogOpen = true`
2. BatchSetDialog 监听 `modelValue` 变化 → 重置表单为空 + checkedKeys = count>0 的 key 集合
3. 用户填表 + 勾选/取消渠道卡片 → 内部 v-model
4. 点「应用到 X 个渠道」→ emit('apply', checkedKeys, { title, description, tags })
5. PublishCenter 的 `onBatchSetApply` 调 `applyBatchSet(checkedKeys, payload)`
6. `applyBatchSet` 改 `platformConfigs[pk]` 和 `accountOverrides[id]`（reactive）
7. PublishCenter 现有的 `watch(form)` / 4 级合并自动触发 → UI 刷新
8. 弹窗关闭 + ElMessage 成功提示

### 图集

1. 用户点「批量设」→ `batchSetDialogOpen = true`
2. BatchSetDialog 同上重置
3. 步骤 4 同上
4. ImagePublish 的 `onBatchSetApply` 调 `applyImageBatchSet(checkedKeys, payload)`
5. `applyImageBatchSet` 遍历 panelRefs：
   - `panel.publicApi.setPlatformConfig({ title, description, tags })` → 改 panel 内部 platformConfig
   - `panel.publicApi.getCheckedAccountIds()` → 拿已个性化账号
   - 对每个已个性化账号调 `panel.publicApi.setAccountOverride(id, ...)`
6. panel 内部 `emit('config-changed')` → ImagePublish 已有的 config-changed 监听触发 → UI 刷新
7. 弹窗关闭 + ElMessage 成功提示

## 错误处理 / 边界

| 场景 | 行为 |
|------|------|
| 没有可选渠道（全部 0 账号） | 「应用」按钮 disable，鼠标 hover 提示「请先添加账号」 |
| `publishAccountIds.size === 0` | 视频/图集页面「批量设」按钮 disable（与「一键填写」一致） |
| 标签数量 > 10 | 沿用 TagInput 既有 max 限制 |
| 描述超长 | maxlength=500 沿用视频/图集现有 textarea 限制 |
| 标题超长 | maxlength=100 沿用视频/图集现有 input 限制 |
| 用户输入全空白 | 「应用」按钮 enable（允许"清空"操作） |
| 弹窗打开时输入框为空 | 不预填（用户明确：批量设是"设置新值"） |
| 标签输入是字符串数组 | 复用 `TagInput` 组件的 v-model 协议（若已存在）或 el-tag + el-input 简单实现 |

## 测试

### 单元测试

1. **useBatchSetApply.test.js**
   - mock `platformConfigs`、`accountOverrides`、`accountChecked`、`accountStore`
   - 测 1：勾选 1 个渠道 → 写 platformConfigs[pk] 三字段
   - 测 2：勾选 1 个渠道，该渠道下有 2 个账号，其中 1 个 accountChecked=true → 写渠道 + 1 个账号
   - 测 3：勾选 3 个渠道 → 循环覆盖
   - 测 4：tags 数组被深拷贝（apply 后改原 payload.tags 不影响写入值）
   - 测 5：空 payload { title:'', description:'', tags:[] } → 三个字段都清空（覆盖语义）

2. **useImageBatchSetApply.test.js**
   - mock panelRefs（每个 panel 暴露 publicApi）
   - 测 1：勾选 1 个 panel → 调 setPlatformConfig 一次 + setAccountOverride N 次（N=已个性化账号数）
   - 测 2：panel 不存在 / publicApi 缺失 → 跳过不报错

3. **useChannelForm 扩展测试**
   - 测 setPlatformConfig：partial 提供的字段被覆盖；未提供的字段保持不变
   - 测 setAccountOverride：新 override 合并到已有 override；空 override 被删除
   - 测 getCheckedAccountIds：返回所有 hasMeaningfulOverride 的 accountId

### E2E（gstack `/qa`）

场景 1 — 视频批量设：
1. 启动后端 + 前端
2. 登录账号（至少 2 个平台 × 2 个账号 = 4 账号）
3. 进入视频发布页 → 点「批量设」
4. 填标题 / 描述 / 标签
5. 默认全选 → 点「应用」
6. 检查：左侧每个渠道标题/描述/标签都更新了
7. 切到有账号个性化的账号 → 标题/描述/标签也跟着更新
8. 取消所有勾选 → 「应用」按钮 disable

场景 2 — 图集批量设：
1. 同上但进入图集发布页
2. 验证 panel 内的 title/description/tags 都被更新

## 依赖

- 现有 `TagInput` 组件（若不存在则新增 `<TagInput>` 简单实现：el-tag + el-input，与项目风格一致）
- Element Plus `el-dialog` / `el-form` / `el-form-item` / `el-input` / `el-button`
- 现有 `platformList` / `getPlatformByKey` / `useAccountStore`
- 图集 panel 已暴露 `publicApi`（来自 `useChannelForm`），需扩展

## 风险

| 风险 | 缓解 |
|------|------|
| 覆盖策略导致误清空 | 弹窗打开时输入框为空 + 「应用」按钮文案明确「应用到 X 个渠道」+ 成功提示 |
| 图集 panel 没暴露 setPlatformConfig | 已规划扩展 useChannelForm 公共 API |
| 标签组件不一致 | 先用 el-tag + el-input 简单实现，后续统一 TagInput |
| 视频 watch(form) 触发与 apply 时机冲突 | apply 是同步写 reactive，与 watch 协同，无竞态 |
| 卡片数量计算性能 | computed 缓存，依赖 accountStore.accounts 和 publishAccountIds，规模小（< 50）无影响 |

## 后续

- 若用户反馈需要「平台特有字段」批量设（如视频格式、群聊、合集、声明），可在此弹窗扩展 tab
- 若需要「撤销批量设」，可在 useBatchSetApply 内部保存 snapshot + 提供 restore
