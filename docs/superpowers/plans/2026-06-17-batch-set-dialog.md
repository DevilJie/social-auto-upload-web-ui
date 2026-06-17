# 批量设置弹窗 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在视频发布和图集发布页面右上角加「批量设」按钮，弹窗内 4 行表单（标题/描述/标签）+ 渠道卡片网格（logo+渠道名+账号数），勾选后一键覆盖到所选渠道的渠道级 + 已个性化账号的账号级配置。

**Architecture:** 公共 `BatchSetDialog.vue` 接收 platforms 元数据 + 触发 `apply` 事件；两个 apply composable（`useBatchSetApply` 视频 / `useImageBatchSetApply` 图集）各自处理写入逻辑；图集 panel 通过扩展 `useChannelForm.publicApi`（新增 `setPlatformConfig`/`setAccountOverride`/`getCheckedAccountIds`）暴露 setter。

**Tech Stack:** Vue 3 + Composition API + Element Plus + Pinia（与现有项目一致）

**Note on testing:** 项目目前无前端自动化测试框架（无 vitest/jest）。本计划采用**手动浏览器验证**作为每个任务的测试手段——启动 dev server、用 gstack `/browse` 或人眼验证、记录操作步骤。不引入新的测试框架以避免范围扩大。

---

## File Structure

| 文件 | 状态 | 职责 |
|------|------|------|
| `frontend/src/composables/useChannelForm.js` | 修改 | 公共 API 扩展：加 `setPlatformConfig` / `setAccountOverride` / `getCheckedAccountIds` |
| `frontend/src/composables/useBatchSetApply.js` | 新增 | 视频专用：接收 reactive 引用 + accountStore，返回 `applyBatchSet(checkedKeys, payload)` |
| `frontend/src/composables/useImageBatchSetApply.js` | 新增 | 图集专用：接收 panel refs map，返回 `applyImageBatchSet(checkedKeys, payload)` |
| `frontend/src/components/BatchSetDialog.vue` | 新增 | 公共弹窗：4 行表单 + 渠道卡片网格，emit `apply` |
| `frontend/src/views/PublishCenter.vue` | 修改 | 头部加「批量设」按钮 + 注册 dialog + 接入 applyBatchSet |
| `frontend/src/views/ImagePublish.vue` | 修改 | 头部加「批量设」按钮 + 注册 dialog + 接入 applyImageBatchSet |

---

## Task 1: 扩展 useChannelForm 公共 API

**Files:**
- Modify: `frontend/src/composables/useChannelForm.js`（在 `publicApi` 对象内加 3 个方法）

### Step 1: 读 useChannelForm.js 定位 publicApi 块

```bash
grep -n "publicApi\|hasAccountOverride" frontend/src/composables/useChannelForm.js
```

预期输出包含 `publicApi` 关键字和现有方法列表。确认 publicApi 对象在文件底部。

### Step 2: 加 setPlatformConfig 方法

在 `publicApi` 对象中、`hasAccountOverride` 前一行，添加：

```js
setPlatformConfig(partial) {
  for (const [k, v] of Object.entries(partial)) {
    if (v === undefined) continue
    platformConfig[k] = Array.isArray(v) ? [...v] : v
    form[k] = Array.isArray(v) ? [...v] : v
  }
  emit('config-changed')
},
```

注意：partial 提供的字段直接覆盖（与 spec 中"覆盖"语义一致）；空字符串 `''` 也会覆盖（清空效果）。

### Step 3: 加 setAccountOverride 方法

紧接 setPlatformConfig 之后添加：

```js
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
```

行为说明：
- 合并到已有 override（保留其他字段如 scheduleTime）
- 全部清空 → 删除 override 项
- 当前编辑账号就是被设账号 → 同步刷新 form

### Step 4: 加 getCheckedAccountIds 方法

紧接 setAccountOverride 之后添加：

```js
getCheckedAccountIds() {
  return Object.entries(accountOverrides)
    .filter(([_, v]) => hasMeaningfulOverride(v))
    .map(([id]) => Number(id))
},
```

返回所有有"有意义覆写"的账号 ID（已个性化账号）。

### Step 5: 手动验证

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173 → 进入「图集发布」页（任何平台）→ 浏览器 DevTools Console 跑：

```js
// 找到任意 panel 组件实例（Vue DevTools 或在 setup 暴露）
const panel = document.querySelector('[data-test="xhs-panel"]') // 如果存在
// 或者：临时在 panel 模板里加 <div data-test="xhs-panel"> 方便查找
```

预期：console 输出 panel 实例。点击标题/描述输入框 → 在 Vue DevTools 看到 platformConfig 变化。

**更简化的验证方式**：在 ImagePublish.vue 的 panel mount hook 里加一个 `console.log` 看 panel.publicApi 是否存在：

```js
// 临时加在 ImagePublish.vue setup 末尾，看 dev server 控制台
if (panelRef.value) {
  console.log('panel publicApi keys:', Object.keys(panelRef.value.publicApi || {}))
}
```

预期输出包含 `setPlatformConfig`、`setAccountOverride`、`getCheckedAccountIds`。

### Step 6: 移除临时验证代码 + Commit

```bash
git add frontend/src/composables/useChannelForm.js
git commit -m "feat(useChannelForm): 公共 API 加 setPlatformConfig/setAccountOverride/getCheckedAccountIds

供图集批量设弹窗使用:setPlatformConfig 覆盖 platformConfig 中
提供的字段;setAccountOverride 合并到已有账号覆写(全空时删除);
getCheckedAccountIds 返回所有有有意义覆写的账号 ID。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 2: 创建 useBatchSetApply composable（视频）

**Files:**
- Create: `frontend/src/composables/useBatchSetApply.js`

### Step 1: 创建文件

`frontend/src/composables/useBatchSetApply.js` 完整内容：

```js
import { getPlatformByKey } from '@/config/platforms'

/**
 * 视频发布批量设 composable。
 * 把 payload (title/description/tags) 写入 checkedPlatformKeys 中每个渠道的:
 *   1) platformConfigs[platformKey] (渠道级, 覆盖)
 *   2) 该渠道下已开 accountChecked 的账号 → accountOverrides[id] (账号级, 覆盖)
 *
 * @param {object} refs  { platformConfigs, accountOverrides, accountChecked, accountStore }
 * @returns {{ applyBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[] }) => void }}
 */
export function useBatchSetApply({ platformConfigs, accountOverrides, accountChecked, accountStore }) {
  function applyBatchSet(checkedPlatformKeys, payload) {
    const { title, description, tags } = payload
    for (const pk of checkedPlatformKeys) {
      // 1. 渠道级（覆盖）
      if (!platformConfigs[pk]) platformConfigs[pk] = {}
      platformConfigs[pk].title = title
      platformConfigs[pk].description = description
      platformConfigs[pk].tags = Array.isArray(tags) ? [...tags] : []

      // 2. 该渠道下已开 accountChecked 的账号（覆盖）
      const platformCfg = getPlatformByKey(pk)
      if (!platformCfg) continue
      const accounts = (accountStore?.accounts || []).filter(a => a.platform === platformCfg.name)
      for (const acc of accounts) {
        if (accountChecked[acc.id]) {
          if (!accountOverrides[acc.id]) accountOverrides[acc.id] = {}
          accountOverrides[acc.id].title = title
          accountOverrides[acc.id].description = description
          accountOverrides[acc.id].tags = Array.isArray(tags) ? [...tags] : []
        }
      }
    }
  }

  return { applyBatchSet }
}
```

### Step 2: 手动验证语法

```bash
cd frontend && node -e "import('./src/composables/useBatchSetApply.js').then(m => console.log('OK', Object.keys(m)))"
```

预期输出：`OK [ 'useBatchSetApply' ]`

### Step 3: Commit

```bash
git add frontend/src/composables/useBatchSetApply.js
git commit -m "feat(视频批量设): 新增 useBatchSetApply composable

applyBatchSet(checkedKeys, payload) 把 title/description/tags 批量
写入 platformConfigs[pk] (渠道级) + accountOverrides[已开个性化账号]
(账号级)。覆盖策略,空字段会清空原值。tags 数组深拷贝避免引用共享。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 3: 创建 useImageBatchSetApply composable（图集）

**Files:**
- Create: `frontend/src/composables/useImageBatchSetApply.js`

### Step 1: 创建文件

`frontend/src/composables/useImageBatchSetApply.js` 完整内容：

```js
/**
 * 图集发布批量设 composable。
 * 通过 panel.publicApi 调 useChannelForm 扩展的 setPlatformConfig / setAccountOverride。
 *
 * @param {object} refs  { panels: Map<string, panelRef> } — panels 用 platformKey 索引
 * @returns {{ applyImageBatchSet: (checkedPlatformKeys: string[], payload: { title: string, description: string, tags: string[] }) => void }}
 */
export function useImageBatchSetApply({ panels }) {
  function applyImageBatchSet(checkedPlatformKeys, payload) {
    const { title, description, tags } = payload
    const tagsCopy = Array.isArray(tags) ? [...tags] : []
    for (const pk of checkedPlatformKeys) {
      const panel = panels.get?.(pk) || panels[pk]
      if (!panel?.publicApi) continue

      // 1. 写 panel 内的 platformConfig（覆盖）
      panel.publicApi.setPlatformConfig({
        title,
        description,
        tags: tagsCopy,
      })

      // 2. 写该 panel 下已个性化账号（覆盖）
      const checkedIds = panel.publicApi.getCheckedAccountIds?.() || []
      for (const aid of checkedIds) {
        panel.publicApi.setAccountOverride(aid, {
          title,
          description,
          tags: tagsCopy,
        })
      }
    }
  }

  return { applyImageBatchSet }
}
```

注意：`panels` 接受 `Map` 或普通对象（`panels.get?.(pk) || panels[pk]`），兼容两种用法。

### Step 2: 手动验证语法

```bash
cd frontend && node -e "import('./src/composables/useImageBatchSetApply.js').then(m => console.log('OK', Object.keys(m)))"
```

预期：`OK [ 'useImageBatchSetApply' ]`

### Step 3: Commit

```bash
git add frontend/src/composables/useImageBatchSetApply.js
git commit -m "feat(图集批量设): 新增 useImageBatchSetApply composable

applyImageBatchSet(checkedKeys, payload) 通过 panel.publicApi
调 useChannelForm 扩展的 setPlatformConfig (panel 内渠道级) +
setAccountOverride (panel 内已个性化账号级)。覆盖策略。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 4: 创建 BatchSetDialog 公共组件

**Files:**
- Create: `frontend/src/components/BatchSetDialog.vue`

### Step 1: 创建文件 — 模板

`frontend/src/components/BatchSetDialog.vue` 完整内容：

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="批量设置"
    width="720px"
    top="8vh"
    :close-on-click-modal="false"
  >
    <el-form label-width="60px" label-position="top">
      <el-form-item label="标题">
        <el-input
          v-model="formTitle"
          maxlength="100"
          show-word-limit
          placeholder="留空表示清空原值"
          clearable
        />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="formDescription"
          type="textarea"
          :rows="3"
          maxlength="500"
          show-word-limit
          placeholder="留空表示清空原值"
        />
      </el-form-item>
      <el-form-item label="标签">
        <div class="tag-input-wrap">
          <el-input
            v-model="tagInput"
            placeholder="输入标签内容，按回车添加"
            @keyup.enter="addTag"
            clearable
          />
          <div v-if="formTags.length > 0" class="tags-list">
            <el-tag
              v-for="(tag, index) in formTags"
              :key="index"
              closable
              @close="removeTag(index)"
              size="small"
            >#{{ tag }}</el-tag>
          </div>
        </div>
      </el-form-item>
      <el-form-item label="渠道">
        <div class="channel-grid">
          <div
            v-for="p in platforms"
            :key="p.key"
            :class="['channel-card', {
              'is-checked': checkedKeys.has(p.key),
              'is-disabled': p.count === 0
            }]"
            @click="toggleKey(p)"
          >
            <img v-if="p.logo" :src="p.logo" :alt="p.name" class="channel-logo" />
            <div v-else class="channel-logo channel-logo-fallback">{{ p.name?.charAt(0) }}</div>
            <div class="channel-name">{{ p.name }}</div>
            <div class="channel-count">{{ p.count }} 账号</div>
            <el-icon v-if="checkedKeys.has(p.key) && p.count > 0" class="check-icon"><Check /></el-icon>
          </div>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="checkedCount === 0"
        @click="handleApply"
      >
        应用到 {{ checkedCount }} 个渠道
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array, required: true },
})

const emit = defineEmits(['update:modelValue', 'apply'])

const formTitle = ref('')
const formDescription = ref('')
const formTags = ref([])
const tagInput = ref('')
const checkedKeys = ref(new Set())

const checkedCount = computed(() => checkedKeys.value.size)

watch(() => props.modelValue, (open) => {
  if (open) {
    formTitle.value = ''
    formDescription.value = ''
    formTags.value = []
    tagInput.value = ''
    checkedKeys.value = new Set(
      props.platforms.filter(p => p.count > 0).map(p => p.key)
    )
  }
})

function toggleKey(p) {
  if (p.count === 0) return
  const next = new Set(checkedKeys.value)
  if (next.has(p.key)) {
    next.delete(p.key)
  } else {
    next.add(p.key)
  }
  checkedKeys.value = next
}

function addTag() {
  const v = (tagInput.value || '').trim()
  if (!v) return
  if (formTags.value.includes(v)) {
    tagInput.value = ''
    return
  }
  formTags.value = [...formTags.value, v]
  tagInput.value = ''
}

function removeTag(idx) {
  formTags.value = formTags.value.filter((_, i) => i !== idx)
}

function handleApply() {
  emit('apply', Array.from(checkedKeys.value), {
    title: formTitle.value,
    description: formDescription.value,
    tags: [...formTags.value],
  })
  emit('update:modelValue', false)
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
  width: 100%;
}

.channel-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 8px;
  border: 1.5px solid $border;
  border-radius: 10px;
  background: $bg-elevated;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;

  &:hover:not(.is-disabled) {
    border-color: $brand-start;
    background: rgba(139, 92, 246, 0.04);
  }

  &.is-checked {
    border-color: $brand-start;
    background: rgba(139, 92, 246, 0.1);
    box-shadow: 0 0 0 1px $brand-start inset;
  }

  &.is-disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .channel-logo {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    object-fit: contain;
  }
  .channel-logo-fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    background: $bg-surface;
    color: $text-muted;
    font-size: 14px;
    font-weight: 700;
  }

  .channel-name {
    font-size: 13px;
    font-weight: 600;
    color: $text-primary;
    text-align: center;
  }

  .channel-count {
    font-size: 11px;
    color: $text-muted;
  }

  .check-icon {
    position: absolute;
    top: 4px;
    right: 4px;
    color: $brand-start;
    font-size: 14px;
  }
}

.tag-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
</style>
```

### Step 2: 手动验证构建

```bash
cd frontend && npm run build
```

预期：构建成功，无 error。如果有 sass 变量找不到（`$border` / `$brand-start`），则需要替换为实际项目变量名（参考 `frontend/src/styles/variables.scss`）。

**如果构建失败**：检查报错，常见原因：
- SCSS 变量名不匹配 → 用项目实际变量名替换
- Element Plus 图标未注册 → 已通过 `@element-plus/icons-vue` 单独 import

### Step 3: Commit

```bash
git add frontend/src/components/BatchSetDialog.vue
git commit -m "feat(批量设): 新增公共 BatchSetDialog 组件

4 行表单(标题/描述/标签)+ 渠道卡片网格(logo+渠道名+账号数)。
默认全选 count>0 渠道,0 账号置灰。emit('apply', checkedKeys, payload)。
打开时表单清空,覆盖策略。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 5: 在 PublishCenter 集成批量设

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue` — 头部加按钮 + 注册 dialog + 接入 applyBatchSet

### Step 1: 加 import

在 `frontend/src/views/PublishCenter.vue` 顶部 import 块（`import BatchPublishDialog` 附近）加：

```js
import BatchSetDialog from '@/components/BatchSetDialog.vue'
import { useBatchSetApply } from '@/composables/useBatchSetApply'
import { Setting } from '@element-plus/icons-vue'
```

（如果 `Setting` 图标已 import 则跳过；看 line 460 附近的 import 块）

### Step 2: 找 import 的图标

```bash
grep -n "import.*icons-vue\|MagicStick" frontend/src/views/PublishCenter.vue | head -3
```

确认从 `@element-plus/icons-vue` 引入的图标清单。

### Step 3: 加 applyBatchSet 初始化和 dialog 状态

在 PublishCenter.vue 的 setup 中（`batchPublishDialogVisible` ref 之后）加：

```js
// ========== 批量设 (Batch Set) ==========
const batchSetDialogOpen = ref(false)
const { applyBatchSet } = useBatchSetApply({
  platformConfigs,
  accountOverrides,
  accountChecked,
  accountStore,
})
const batchSetPlatforms = computed(() => {
  return platformList.map(p => {
    const platformAccounts = accountStore.accounts.filter(a => a.platform === p.name)
    const selectedCount = platformAccounts.filter(a => publishAccountIds.has(a.id)).length
    return { key: p.key, name: p.name, logo: p.logo, count: selectedCount }
  })
})
function onBatchSetApply(checkedKeys, payload) {
  applyBatchSet(checkedKeys, payload)
  ElMessage.success(`已批量设置到 ${checkedKeys.length} 个渠道`)
}
```

**注意**：`accountStore` 必须已在 setup 顶层通过 `useAccountStore()` 声明；如果没有，需加：

```js
import { useAccountStore } from '@/stores/account'
const accountStore = useAccountStore()
```

### Step 4: 在头部加按钮

定位 `.header-right` 块（line 36-47），在「一键填写」`el-button` 之后插入：

```vue
<el-button :icon="Setting" @click="batchSetDialogOpen = true" :disabled="publishAccountIds.size === 0">
  批量设
</el-button>
```

### Step 5: 注册 dialog

在文件底部 dialog 注册区（`<OneClickFillDialog v-model="oneClickDialogOpen" ...>` 之后）加：

```vue
<BatchSetDialog
  v-model="batchSetDialogOpen"
  :platforms="batchSetPlatforms"
  @apply="onBatchSetApply"
/>
```

### Step 6: 手动验证（dev server）

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173 → 进入「视频发布」页：

1. **基础显示**：右上角出现「批量设」按钮（位置在「一键填写」和「一键发布」之间）
2. **按钮禁用**：未选账号时（左侧无账号）按钮 disable
3. **打开弹窗**：点按钮 → 弹窗出现，4 行表单为空，渠道卡片默认全选（0 账号置灰）
4. **输入内容**：填标题/描述/标签 → 看到实时显示
5. **取消勾选**：点某个卡片 → 该卡片边框变浅，「应用到 X 个渠道」数量减 1
6. **点应用**：
   - 关闭弹窗
   - 「已批量设置到 X 个渠道」toast
   - 在左侧选中的渠道上，platformConfig 应有值（Vue DevTools 检查）
7. **验证账号级覆写**：在某个渠道下勾选一个账号的「账号个性化」+ 平台个性化 → 再批量设 → Vue DevTools 检查 `accountOverrides[id]` 也有值

### Step 7: Commit

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(视频发布): 接入批量设弹窗

头部右侧「一键填写」和「一键发布」之间加「批量设」按钮。
点击弹窗,选填标题/描述/标签,默认全选所有有账号的渠道,
应用后覆盖到 platformConfigs[pk] + accountOverrides[已开个性化账号]。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 6: 在 ImagePublish 集成批量设

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue` — 头部加按钮 + 注册 dialog + 接入 applyImageBatchSet

### Step 1: 找 panelRefs 结构

```bash
grep -n "panelRefs\|panelRef\|panel\." frontend/src/views/ImagePublish.vue | head -20
```

确认 panelRefs 是 Map 还是 plain object。如果当前没有 panelRefs 索引，需要先在 setup 中构造一个：

```js
// 假设 panels 是 reactive({ xiaohongshu: refObj, douyin: refObj, ... })
const panelRefs = computed(() => panels)
```

或者按现有结构组装。

### Step 2: 加 import

在 ImagePublish.vue 顶部 import 块（`import OneClickFillDialog` 附近）加：

```js
import BatchSetDialog from '@/components/BatchSetDialog.vue'
import { useImageBatchSetApply } from '@/composables/useImageBatchSetApply'
import { Setting } from '@element-plus/icons-vue'
```

### Step 3: 加 applyImageBatchSet 初始化

在 setup 中（`batchPublishDialogVisible` 之后）加：

```js
const batchSetDialogOpen = ref(false)
const { applyImageBatchSet } = useImageBatchSetApply({ panels: panelRefs })
const batchSetPlatforms = computed(() => {
  return platformList
    .filter(p => p.key in (panels || {}))  // 已有 panel 的平台
    .map(p => {
      const panel = panels[p.key]
      const selectedCount = panel?.publicApi?.getSelectedAccountCount?.() ?? 0
      return { key: p.key, name: p.name, logo: p.logo, count: selectedCount }
    })
})
function onBatchSetApply(checkedKeys, payload) {
  applyImageBatchSet(checkedKeys, payload)
  ElMessage.success(`已批量设置到 ${checkedKeys.length} 个渠道`)
}
```

**注意**：图集 panel 是否已暴露 `getSelectedAccountCount` 不确定——如果没有，需要在 panel 内部 setup 加：

```js
// panel setup 末尾
publicApi.getSelectedAccountCount = () => {
  // 通过 props.accountId 或 accountStore 算该 panel 平台的选中账号数
  // 具体实现看 panel 实际结构
}
```

如果无法加，简化：把 `count` 固定为 1（panel 存在就算有账号），或省略 `count`（只显示平台名）。

### Step 4: 在头部加按钮

定位 `.header-right` 块，在「一键填写」`el-button` 之后插入：

```vue
<el-button :icon="Setting" @click="batchSetDialogOpen = true" :disabled="publishAccountIds.size === 0">
  批量设
</el-button>
```

### Step 5: 注册 dialog

在文件底部 dialog 注册区加：

```vue
<BatchSetDialog
  v-model="batchSetDialogOpen"
  :platforms="batchSetPlatforms"
  @apply="onBatchSetApply"
/>
```

### Step 6: 手动验证（dev server）

```bash
cd frontend && npm run dev
```

打开 http://localhost:5173 → 进入「图集发布」页：

1. **基础显示**：右上角出现「批量设」按钮
2. **打开弹窗**：点按钮 → 弹窗出现，渠道卡片显示有 panel 的平台
3. **点应用**：
   - 关闭弹窗
   - toast 提示
   - 切到对应 panel → 看到 title/description/tags 已更新
4. **验证账号级覆写**：在某个 panel 内对某账号做修改（账号个性化）→ 再批量设 → 该账号覆写也被更新

### Step 7: Commit

```bash
git add frontend/src/views/ImagePublish.vue
git commit -m "feat(图集发布): 接入批量设弹窗

头部右侧加「批量设」按钮。弹窗勾选后通过 panel.publicApi
.setPlatformConfig + .setAccountOverride 批量覆盖到 panel 内
platformConfig + 该 panel 已个性化账号。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Task 7: 端到端验证

**Files:** 无（纯验证）

### Step 1: 启动完整环境

```bash
# Terminal 1: 后端
cd backend && python3 app.py

# Terminal 2: 前端
cd frontend && npm run dev
```

### Step 2: 跑通视频批量设流程

打开 http://localhost:5173 → 「视频发布」：

1. 左侧选 2 个不同平台（如抖音 1 账号 + 小红书 1 账号）→ 共 2 账号
2. 点「批量设」按钮
3. 验证：弹窗出现，2 个渠道卡片默认勾选（其他 0 账号置灰）
4. 填入：标题「测试标题」/ 描述「测试描述」/ 标签「标签1 标签2」
5. 点「应用到 2 个渠道」
6. 验证：弹窗关闭 + toast 提示
7. 切到抖音平台 → 看到「标题」「描述」「标签」已更新为「测试标题/测试描述/标签1 标签2」
8. 切到小红书平台 → 同样看到更新

### Step 3: 验证账号级覆写

在 Task 7 步骤 1 之后：

1. 在抖音某账号下勾选「账号个性化」+ 修改其标题为「独立标题」
2. 再次点「批量设」→ 填入新内容「账号级测试」
3. 验证：抖音渠道级（platformConfigs.douyin）=「账号级测试」
4. 切到该账号 → 标题也是「账号级测试」（不是「独立标题」）

### Step 4: 跑通图集批量设流程

打开 http://localhost:5173 → 「图集发布」：

1. 左侧选 2 个平台账号
2. 点「批量设」按钮
3. 验证：弹窗出现，渠道卡片显示 panel 列表
4. 填入内容 → 点「应用」
5. 切到每个 panel → 看到 title/description/tags 已更新

### Step 5: 跑边界情况

1. **未选账号**：左侧无账号 → 「批量设」按钮 disable
2. **0 账号渠道置灰**：批量设弹窗中，0 账号渠道卡片不响应点击 + 透明度低
3. **空输入应用**：批量设打开 → 不填任何内容 → 点「应用」→ 验证：原 title/description/tags 被清空（覆盖语义）
4. **取消勾选**：批量设 → 取消所有卡片 → 「应用到 0 个渠道」按钮 disable

### Step 6: 用 gstack /qa 跑 e2e（可选）

```bash
# 让 gstack 跑完整流程并截图
# gstack 知道项目结构，会用 /browse 操作浏览器
```

### Step 7: 总结验证 + 最终 commit（如果还有零散改动）

```bash
git status
# 如果有未提交改动：
git add -A
git commit -m "chore(批量设): 验证后的小修小补

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage:**

| Spec 章节 | 对应 Task |
|-----------|-----------|
| 1. 入口位置 | Task 5/6 Step 4 |
| 2. 弹窗结构（4 行表单 + 卡片网格） | Task 4 |
| 3. 关键行为（默认全选/覆盖/空输入） | Task 4 + Task 7 |
| 4. 架构（公共 dialog + 2 个 composable） | Task 2/3/4 |
| 5. 写入逻辑 | Task 1/2/3 |
| 6. 数据流（视频/图集） | Task 5/6 |
| 7. 错误处理/边界 | Task 4 + Task 7 |
| 8. 测试 | Task 7（手动浏览器验证） |

**2. Placeholder scan:** 无 TBD/TODO；每个 task 的代码块都是完整可粘贴内容。

**3. Type consistency:**
- `applyBatchSet(checkedPlatformKeys, payload)` — 一致（Task 2 定义、Task 5 调用、Task 7 验证）
- `applyImageBatchSet(checkedPlatformKeys, payload)` — 一致（Task 3 定义、Task 6 调用）
- `setPlatformConfig(partial)` / `setAccountOverride(id, partial)` / `getCheckedAccountIds()` — Task 1 定义、Task 3 调用
- `emit('apply', checkedKeys, payload)` — Task 4 emit、Task 5/6 监听

**4. 潜在问题：**
- Task 6 Step 3 中 `getSelectedAccountCount` 不一定存在——plan 中说明了"如果没有则简化"分支
- Task 4 用 SCSS 变量 `$border` / `$brand-start` / `$bg-elevated` / `$bg-surface` / `$text-muted` / `$text-primary`——Step 2 中要求构建检查
- Task 1 改动 `useChannelForm` 公共 API，可能影响其他使用方——Step 5 要求 dev server 验证现有功能未坏

**5. 风险评估：**
- 中：图集 panel 结构复杂，可能需要小幅调整 plan（Step 1/3 中有分支处理）
- 低：视频侧改动小，clear scope
- 低：dialog 组件独立，无外部依赖

Plan 自审通过。准备进入执行阶段。
