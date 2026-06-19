# 渠道黑名单 + 登录弹窗 UI 重设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在系统设置新增渠道黑名单功能 + 重设计账号管理的登录弹窗为平台 Logo 卡片网格点选式

**Architecture:** 后端零改动,黑名单数据复用 `settings` 表新增 `disabledPlatforms` key(JSON 字符串数组)。前端扩展 Pinia `stores/app.js`(Composition API),通过 `isPlatformDisabled(key)` getter 让各消费方响应式过滤。登录弹窗抽出为独立 `LoginDialog.vue`,内部用 `reactive({})` 维护卡片状态 + `Map` 维护多 SSE 连接,支持多平台并发登录。

**Tech Stack:** Vue 3 + Pinia + Element Plus + Vite / Playwright(浏览器手动 + gstack `/qa` E2E)/ 项目无单测基础设施,每个任务通过浏览器手动验证 + 截图(或 gstack `/qa` 走 Playwright)

**Spec:** `docs/superpowers/specs/2026-06-18-channel-blacklist-and-login-ui-design.md`(必读)

---

## 关键技术约束(每个任务都需遵守)

1. **`account.platform` 是中文名**(如「小红书」),不是 key。所有按 account 过滤黑名单的地方必须 `const key = platformNameToKey[a.platform]; key && !appStore.isPlatformDisabled(key)`。
2. **平台对象数组**(`platformList` / `IMAGE_PLATFORMS` / `props.platforms`)本身有 `.key` 字段,可直接 `p.key`。
3. **JSON 序列化**:PUT 时直接传 JS 数组(后端自动 `json.dumps`);GET 时后端只对 `storage` 自动反序列化,`disabledPlatforms` 拿到的是字符串,前端必须 `JSON.parse`。
4. **Pinia 用 Composition API**(setup 函数),不是 Options API。
5. **`account.platform` 字段在 store 里**:参考 `frontend/src/stores/account.js:19` `platform: platformIdToName[item[1]] || '未知'`。
6. **平台映射工具**:`frontend/src/config/platforms.js` 导出 `PLATFORMS`、`platformList`、`platformNameToKey`、`platformNameToId`、`platformIdToName` 等。
7. **commit message 全部用中文**(项目规则)。
8. **后端零改动** — 任何任务都不修改 `backend/`。

---

## 文件结构

### 新增

- `frontend/src/components/PlatformBlacklistDialog.vue` — 添加黑名单渠道的弹窗(4 列 Logo 网格 + 已添加灰显)
- `frontend/src/components/LoginDialog.vue` — 重新设计的登录弹窗(`add` / `relogin` 两种模式,支持多卡片并发)

### 修改

- `frontend/src/stores/app.js` — 扩展 `disabledPlatforms` ref + `isPlatformDisabled` + `addDisabledPlatforms` / `removeDisabledPlatform` actions
- `frontend/src/views/Settings.vue` — 新增「渠道黑名单」card(内嵌小卡片网格 + ✕ 移除 + 挂载 PlatformBlacklistDialog)
- `frontend/src/views/AccountManagement.vue` — 卡片加「已拉黑」tag + 禁用「登录」「同步」「创作中心」按钮 + 替换内嵌 dialog 为 `<LoginDialog>` + 删除遗留 SSE 代码
- `frontend/src/components/AccountSidebar.vue` — 过滤黑名单平台分组
- `frontend/src/components/AccountSelectDialog.vue` — 过滤黑名单平台筛选条 + 账号列表(账号来自 `useAccountStore`)
- `frontend/src/views/PublishCenter.vue` — 「渠道个性化」过滤黑名单 + 进入页时清理 `publishAccountIds`
- `frontend/src/views/ImagePublish.vue` — 同上(基于 `IMAGE_PLATFORMS`)

---

## Phase 1:基础设施(Store + 黑名单 card UI)

### Task 1:扩展 Pinia store — 新增 `disabledPlatforms` state + `isPlatformDisabled`

**Files:**
- Modify: `frontend/src/stores/app.js`(全文件)

**目的:** 建立 store 层 API,后续任务都依赖它。

- [ ] **Step 1: 阅读 `frontend/src/stores/app.js` 当前内容**

Run: `cat frontend/src/stores/app.js`(或用 Read 工具)
确认:文件用 `defineStore('app', () => { ... })` Composition API 风格,已有 `autoFillTitle`、`autoSaveDraft`、`materials` 等 ref。

- [ ] **Step 2: 在 `frontend/src/stores/app.js` 中 import 区追加**

```js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { settingsApi } from '@/api/v2'
```

(若 `settingsApi` 已 import 可跳过;`computed` 用于后续 platformList,本任务暂可不加)

- [ ] **Step 3: 在 setup 函数体内(`return` 之前)追加黑名单 state + getter + actions**

```js
// ========== 渠道黑名单 ==========
// 平台 key 数组,如 ['xiaohongshu', 'youtube']
const disabledPlatforms = ref([])

// 判断某平台 key 是否被拉黑
const isPlatformDisabled = (key) => disabledPlatforms.value.includes(key)

// 批量添加(单次 PUT)
const addDisabledPlatforms = async (keys) => {
  const newKeys = keys.filter(k => !disabledPlatforms.value.includes(k))
  if (newKeys.length === 0) return
  const snapshot = [...disabledPlatforms.value]
  disabledPlatforms.value = [...disabledPlatforms.value, ...newKeys]
  try {
    await settingsApi.updateSettings({
      disabledPlatforms: disabledPlatforms.value
    })
  } catch (e) {
    disabledPlatforms.value = snapshot  // 回滚
    throw e
  }
}

// 移除单个
const removeDisabledPlatform = async (key) => {
  const snapshot = [...disabledPlatforms.value]
  disabledPlatforms.value = disabledPlatforms.value.filter(k => k !== key)
  try {
    await settingsApi.updateSettings({
      disabledPlatforms: disabledPlatforms.value
    })
  } catch (e) {
    disabledPlatforms.value = snapshot
    throw e
  }
}
```

- [ ] **Step 4: 在 `return { ... }` 中导出新成员**

在 return 对象里追加(保持字母序或就近分组):

```js
return {
  // ... 现有 return 内容保持不变 ...
  disabledPlatforms,
  isPlatformDisabled,
  addDisabledPlatforms,
  removeDisabledPlatform,
}
```

- [ ] **Step 5: 启动 dev server 验证语法**

```bash
cd frontend && npm run dev
```

Expected: Vite 启动无报错(若 `settingsApi` import 报错,确认 `frontend/src/api/v2.js` 中有 `settingsApi` 命名导出)。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/app.js
git commit -m "feat(store): 扩展 app store 新增渠道黑名单 state 与 actions"
```

---

### Task 2:`fetchSettings` 中解析 `disabledPlatforms`(JSON.parse)

**Files:**
- Modify: `frontend/src/views/Settings.vue`(定位 `fetchSettings` 函数,约在 line 411-427)

**目的:** 启动时从后端加载黑名单到 store。Settings.vue 已有 `fetchSettings` 调 `settingsApi.getSettings()`,在拿到 data 后写一份到 store。

**先确认:**
- 用 Read 工具读 `frontend/src/views/Settings.vue:411-460` 的 `fetchSettings` / `handleSave` 实现
- 确认 `fetchSettings` 中是否已 import 并使用 `useAppStore`

- [ ] **Step 1: 在 `Settings.vue` 的 `<script setup>` 顶部 import useAppStore**

```js
import { useAppStore } from '@/stores/app'
const appStore = useAppStore()
```

(若已存在则跳过)

- [ ] **Step 2: 在 `fetchSettings` 拿到 data 后,把 `disabledPlatforms` 解析到 store**

定位 `fetchSettings` 函数,在 `data` 已经被处理(默认值、类型转换等)之后,追加:

```js
// 把 disabledPlatforms(JSON 字符串数组)同步到 app store
if (data.disabledPlatforms) {
  try {
    const parsed = typeof data.disabledPlatforms === 'string'
      ? JSON.parse(data.disabledPlatforms)
      : data.disabledPlatforms
    appStore.disabledPlatforms = Array.isArray(parsed) ? parsed : []
  } catch (e) {
    console.warn('解析 disabledPlatforms 失败:', e)
    appStore.disabledPlatforms = []
  }
} else {
  appStore.disabledPlatforms = []
}
```

(具体变量名根据现有 `fetchSettings` 实现调整,如 `settings` 而非 `data`)

- [ ] **Step 3: 启动 dev server + 后端**

```bash
# 终端 1: 启后端
cd backend && python3 app.py

# 终端 2: 启前端
cd frontend && npm run dev
```

- [ ] **Step 4: 浏览器手动验证**

打开 http://localhost:5173 → 进入「系统设置」页面 → F12 打开 Console → 执行:

```js
// Pinia 在 window 上不一定暴露,改用 Vue devtools
// 或者临时在 Settings.vue 加 console.log 看是否拿到
```

更简单:在 `fetchSettings` 末尾临时加 `console.log('disabledPlatforms:', appStore.disabledPlatforms)`,刷新页面看 console 输出。

Expected: console 输出 `disabledPlatforms: []`(首次使用)或之前保存的数组。

验证后**移除临时 log**。

- [ ] **Step 5: 手动 PUT 测试(可选)**

在 Console 执行(假设 `settingsApi` 可访问,或通过浏览器 devtools):

```js
fetch('/api/v2/settings', {
  method: 'PUT',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ disabledPlatforms: ['xiaohongshu'] })
}).then(r => r.json()).then(console.log)
```

刷新页面 → console.log 应输出 `['xiaohongshu']`。

清理测试数据:再次 PUT `disabledPlatforms: []`。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat(settings): fetchSettings 中解析 disabledPlatforms 同步到 store"
```

---

### Task 3:Settings.vue 新增「渠道黑名单」card 静态布局(空态)

**Files:**
- Modify: `frontend/src/views/Settings.vue`(template 区,加在合适位置,如「发布设置」card 之后)

**目的:** 先把 card 容器、标题、空态、按钮位置搭好,后续任务再接 ✕ 移除和弹窗。

- [ ] **Step 1: 在 `<script setup>` 区追加 import 和计算属性**

```js
import { Plus, Close, Warning } from '@element-plus/icons-vue'
import { PLATFORMS } from '@/config/platforms'

// 已拉黑渠道的平台对象数组(filter(Boolean) 容错)
const disabledPlatformObjects = computed(() =>
  appStore.disabledPlatforms
    .map(k => PLATFORMS[k])
    .filter(Boolean)
)

const blacklistDialogVisible = ref(false)

const openBlacklistDialog = () => { blacklistDialogVisible.value = true }
```

(`computed` / `ref` 若已 import 跳过)

- [ ] **Step 2: 在 template 中追加 card HTML**

找一个合适位置(建议在「发布设置」card 之后),插入:

```html
<div class="settings-card">
  <div class="card-header">
    <h3>渠道黑名单</h3>
    <el-button type="primary" @click="openBlacklistDialog">
      <el-icon><Plus /></el-icon> 添加渠道
    </el-button>
  </div>
  <p class="card-desc">
    被加入黑名单的渠道,将无法在视频发布、图集发布、账号登录场景下被选择
  </p>

  <!-- 已拉黑渠道的小卡片网格 -->
  <div v-if="disabledPlatformObjects.length" class="blacklist-grid">
    <div
      v-for="p in disabledPlatformObjects"
      :key="p.key"
      class="blacklist-chip"
      :class="`platform-${p.cssClass}`"
    >
      <img v-if="p.logo" :src="p.logo" :alt="p.name" class="chip-logo" />
      <span class="chip-name">{{ p.name }}</span>
      <button class="chip-remove" type="button">
        <el-icon><Close /></el-icon>
      </button>
    </div>
  </div>

  <!-- 空态 -->
  <div v-else class="blacklist-empty">
    <el-icon class="empty-icon"><Warning /></el-icon>
    <span>暂无黑名单渠道,点击右上角「添加渠道」开始</span>
  </div>
</div>
```

注意:`@click="removeFromBlacklist(p.key)"` 在 Task 4 接入,本任务先空着。

- [ ] **Step 3: 在 `<style scoped>` 中追加样式**

```css
.blacklist-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.blacklist-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-light);
  position: relative;
  transition: all 0.2s;
}

.blacklist-chip:hover {
  border-color: var(--el-color-primary);
}

.chip-logo {
  width: 18px;
  height: 18px;
  border-radius: 4px;
}

.chip-name {
  font-size: 13px;
}

.chip-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: 0;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.4);
  color: white;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.2s;
  padding: 0;
  margin-left: 2px;
}

.blacklist-chip:hover .chip-remove {
  opacity: 1;
}

.chip-remove:hover {
  background: var(--el-color-danger);
}

.blacklist-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin-top: 12px;
  padding: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 8px;
}

.empty-icon {
  font-size: 18px;
}
```

- [ ] **Step 4: 浏览器验证**

刷新 http://localhost:5173 → 系统设置页 → 应看到「渠道黑名单」card,显示空态文案。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat(settings): 新增渠道黑名单 card 静态布局"
```

---

### Task 4:Settings.vue 接入 ✕ 移除交互

**Files:**
- Modify: `frontend/src/views/Settings.vue`(template + script)

- [ ] **Step 1: 在 `<script setup>` 中追加 `removeFromBlacklist` 函数**

```js
import { ElMessage } from 'element-plus'

const removeFromBlacklist = async (key) => {
  try {
    await appStore.removeDisabledPlatform(key)
    ElMessage.success('已从黑名单移除')
  } catch (e) {
    console.error('移除黑名单失败:', e)
    ElMessage.error('移除失败,请重试')
  }
}
```

(`ElMessage` 若已 import 跳过)

- [ ] **Step 2: 在 template 的 `<button class="chip-remove">` 上绑定 click**

把 Task 3 中的:

```html
<button class="chip-remove" type="button">
```

改为:

```html
<button class="chip-remove" type="button" @click="removeFromBlacklist(p.key)">
```

- [ ] **Step 3: 浏览器验证**

- 打开 Console,执行:
  ```js
  fetch('/api/v2/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ disabledPlatforms: ['xiaohongshu', 'douyin'] })
  })
  ```
- 刷新页面 → 看到「小红书」「抖音」两个 chip
- 鼠标 hover chip → ✕ 按钮出现 → 点击 → chip 消失 + Toast「已从黑名单移除」
- 再次刷新 → 只剩一个 chip(确认已持久化)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat(settings): 渠道黑名单 chip 接入 ✕ 移除交互"
```

---

### Task 5:新建 `PlatformBlacklistDialog.vue` 弹窗

**Files:**
- Create: `frontend/src/components/PlatformBlacklistDialog.vue`

- [ ] **Step 1: 创建文件 `frontend/src/components/PlatformBlacklistDialog.vue`**

完整内容:

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    title="添加黑名单渠道"
    width="680px"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onOpen"
  >
    <div class="blacklist-dialog-body">
      <p class="dialog-hint">选择要加入黑名单的渠道(已加入的不可重复选择)</p>
      <div class="platform-grid">
        <div
          v-for="p in platformList"
          :key="p.key"
          :class="[
            'platform-card',
            `platform-${p.cssClass}`,
            {
              'is-disabled': isAlreadyDisabled(p.key),
              'is-selected': isSelected(p.key)
            }
          ]"
          @click="toggleSelect(p.key)"
        >
          <div class="platform-logo-wrap">
            <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-logo" />
            <span v-else class="platform-letter">{{ p.letter }}</span>
          </div>
          <div class="platform-name">{{ p.name }}</div>
          <div v-if="isAlreadyDisabled(p.key)" class="platform-badge added">已添加</div>
          <div v-else-if="isSelected(p.key)" class="platform-badge selected">✓</div>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:modelValue', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="selectedKeys.length === 0"
        @click="onConfirm"
      >
        确认添加{{ selectedKeys.length > 0 ? `(${selectedKeys.length})` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import { platformList } from '@/config/platforms'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  disabledKeys: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const selectedKeys = ref([])

const isAlreadyDisabled = (key) => props.disabledKeys.includes(key)
const isSelected = (key) => selectedKeys.value.includes(key)

const toggleSelect = (key) => {
  if (isAlreadyDisabled(key)) return
  if (isSelected(key)) {
    selectedKeys.value = selectedKeys.value.filter(k => k !== key)
  } else {
    selectedKeys.value = [...selectedKeys.value, key]
  }
}

const onOpen = () => {
  // 每次打开重置选择
  selectedKeys.value = []
}

const onConfirm = () => {
  emit('confirm', [...selectedKeys.value])
  selectedKeys.value = []
  emit('update:modelValue', false)
}
</script>

<style scoped>
.blacklist-dialog-body {
  padding: 0 4px;
}

.dialog-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 16px 0;
}

.platform-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.platform-card {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px 8px;
  border: 2px solid var(--el-border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-bg-color);
}

.platform-card:hover:not(.is-disabled) {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
}

.platform-card.is-selected {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}

.platform-card.is-disabled {
  opacity: 0.45;
  cursor: not-allowed;
  background: var(--el-fill-color-light);
}

.platform-logo-wrap {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}

.platform-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}

.platform-letter {
  font-size: 20px;
  font-weight: bold;
}

.platform-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
}

.platform-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 8px;
  color: white;
}

.platform-badge.added {
  background: var(--el-text-color-disabled);
}

.platform-badge.selected {
  background: var(--el-color-primary);
}

@media (max-width: 640px) {
  .platform-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
```

- [ ] **Step 2: 在 `Settings.vue` 中挂载该弹窗**

在 `Settings.vue` `<script setup>` 中:

```js
import PlatformBlacklistDialog from '@/components/PlatformBlacklistDialog.vue'

const onBlacklistConfirm = async (newKeys) => {
  try {
    await appStore.addDisabledPlatforms(newKeys)
    ElMessage.success(`已添加 ${newKeys.length} 个渠道到黑名单`)
  } catch (e) {
    console.error('添加黑名单失败:', e)
    ElMessage.error('添加失败,请重试')
  }
}
```

在 template 中(可放在最后一个 `.settings-card` 之后,或某个合适位置):

```html
<PlatformBlacklistDialog
  v-model="blacklistDialogVisible"
  :disabled-keys="appStore.disabledPlatforms"
  @confirm="onBlacklistConfirm"
/>
```

(`blacklistDialogVisible` 在 Task 3 已定义)

- [ ] **Step 3: 浏览器验证完整流程**

- 系统设置页 → 点「+ 添加渠道」按钮 → 弹窗打开
- 看到 10 个平台卡片网格
- 点击「小红书」「抖音」→ 出现 ✓ 标记,按钮文案变成「确认添加(2)」
- 点击「确认添加(2)」→ 弹窗关闭 → 主页 card 出现「小红书」「抖音」chip
- 再次点「+ 添加渠道」→ 小红书/抖音显示为「已添加」灰显
- 鼠标 hover chip → ✕ → 点击 → 移除

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PlatformBlacklistDialog.vue frontend/src/views/Settings.vue
git commit -m "feat(blacklist): 新增 PlatformBlacklistDialog 弹窗并接入 Settings 页"
```

---

## Phase 2:黑名单生效到各消费方

### Task 6:AccountSidebar 过滤黑名单平台分组

**Files:**
- Modify: `frontend/src/components/AccountSidebar.vue`

**先调研:**
- 用 Read 工具读 `frontend/src/components/AccountSidebar.vue` 全文
- 找到「按平台分组」的 computed / 渲染逻辑,确认变量名(可能叫 `groupedAccounts` 或 `accountsByPlatform`)

- [ ] **Step 1: 在 `<script setup>` 顶部 import**

```js
import { useAppStore } from '@/stores/app'
import { platformNameToKey } from '@/config/platforms'

const appStore = useAppStore()
```

- [ ] **Step 2: 修改分组 computed,过滤黑名单平台**

找到现有的分组计算逻辑(假设是 `groupedAccounts`),改为:

```js
const groupedAccounts = computed(() => {
  // 原有分组逻辑的结果(假设叫 rawGroups)
  return rawGroups.value.filter(group => {
    const key = platformNameToKey[group.platform]  // group.platform 是中文名
    return key && !appStore.isPlatformDisabled(key)
  })
})
```

**变量名适配:** 如果原变量不叫 `groupedAccounts` 或 `rawGroups`,按实际名替换。核心是:在原分组结果上加 `.filter(group => { const k = platformNameToKey[group.platform]; return k && !appStore.isPlatformDisabled(k) })`。

如果分组用 `account.platform` 作为 group key 且 group 对象没有 `.platform` 字段,而是直接以平台名为 key 的 Map/Object,改成:

```js
const visibleGroupedAccounts = computed(() => {
  const result = {}
  for (const [platformName, accounts] of Object.entries(rawGroups.value)) {
    const key = platformNameToKey[platformName]
    if (key && !appStore.isPlatformDisabled(key)) {
      result[platformName] = accounts
    }
  }
  return result
})
```

- [ ] **Step 3: 浏览器验证**

- 系统设置 → 添加「小红书」到黑名单
- 进入视频发布页 → 左侧账号栏**不应**出现「小红书」分组(即使有小红书账号)
- 系统设置 → 移除「小红书」→ 视频发布页恢复显示

(若 left sidebar 显示空白,检查 `rawGroups` 是否成功响应式)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/AccountSidebar.vue
git commit -m "feat(account-sidebar): 过滤渠道黑名单中的平台分组"
```

---

### Task 7:AccountSelectDialog 过滤黑名单(平台筛选条 + 账号列表)

**Files:**
- Modify: `frontend/src/components/AccountSelectDialog.vue`(已知:line 1-80 模板,从 `useAccountStore` 拿账号)

**先调研:**
- 用 Read 工具读 `frontend/src/components/AccountSelectDialog.vue` 全文,确认:
  - `platforms` prop 用法(平台筛选条 line 12-29 用 `v-for="p in platforms"`)
  - 账号列表渲染用的变量名(从代码看是 `filteredAccounts`,line 39)
  - `toggleSelectAll` 实现(line 33)

- [ ] **Step 1: 在 `<script setup>` 中 import**

```js
import { useAppStore } from '@/stores/app'
import { platformNameToKey } from '@/config/platforms'

const appStore = useAppStore()
```

- [ ] **Step 2: 新增「平台是否被拉黑」helper**

```js
const isPlatformDisabled = (platformName) => {
  const key = platformNameToKey[platformName]
  return key && appStore.isPlatformDisabled(key)
}

const isPlatformKeyDisabled = (key) => appStore.isPlatformDisabled(key)
```

- [ ] **Step 3: template 中平台筛选条过滤**

把原 `<div v-for="p in platforms"`(line 17-28)改为:

```html
<template v-for="p in platforms" :key="p.key">
  <div
    v-if="!isPlatformKeyDisabled(p.key)"
    :class="['dialog-platform-item', 'cursor-pointer', { active: accountFilterPlatform === p.name }]"
    @click="accountFilterPlatform = p.name"
  >
    <span class="dialog-platform-badge">
      <img v-if="p.logo" :src="p.logo" :alt="p.name" class="dialog-platform-badge-img">
      <template v-else>{{ p.letter }}</template>
    </span>
    {{ p.name }}
  </div>
</template>
```

(原 `<div v-for>` 直接换成 `<template v-for>` + 内部 `v-if`,避免 fragment 警告)

- [ ] **Step 4: 修改 `filteredAccounts` computed**

找到 `filteredAccounts`(根据 Read 结果),追加黑名单过滤:

```js
const filteredAccounts = computed(() => {
  return accountStore.accounts.filter(a => {
    // 原有过滤逻辑(平台筛选 / 搜索关键字 等)
    // ...
    
    // 追加: 黑名单过滤
    if (isPlatformDisabled(a.platform)) return false
    
    return true
  })
})
```

具体写法以现有 `filteredAccounts` 为基础叠加,**保留原有所有过滤条件**,只在最后 return 前加 `if (isPlatformDisabled(a.platform)) return false`。

- [ ] **Step 5: 修改「一键全选」`toggleSelectAll`**

找到 `toggleSelectAll`(line 33 的 `@click`),改为只针对 `filteredAccounts`(即过滤后的列表)操作:

```js
const toggleSelectAll = () => {
  const allIds = filteredAccounts.value.map(a => a.id)
  const allSelected = allIds.every(id => tempSelectedAccounts.value.includes(id))
  if (allSelected) {
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(
      id => !allIds.includes(id)
    )
  } else {
    tempSelectedAccounts.value = [...new Set([...tempSelectedAccounts.value, ...allIds])]
  }
}
```

(若现有实现已基于 filteredAccounts,仅确认 isAllSelected 计算正确即可)

- [ ] **Step 6: 浏览器验证**

- 系统设置 → 添加「小红书」「抖音」到黑名单
- 进入视频发布页 → 点「+ 添加账号」打开 AccountSelectDialog
- 平台筛选条**不应**出现「小红书」「抖音」
- 「一键全选」不应包含小红书/抖音账号(即使在 accountStore 中存在)
- 系统设置 → 移除黑名单 → 重开弹窗,小红书/抖音恢复

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/AccountSelectDialog.vue
git commit -m "feat(account-select-dialog): 过滤黑名单平台筛选条与账号列表"
```

---

### Task 8:PublishCenter 渠道个性化过滤 + publishAccountIds 清理

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`(2446 行)

**先调研:**
- Read 文件,定位:
  - 「渠道个性化」checkbox 区域(约 line 61-74 附近,带 `platformChecked` / `accountChecked`)
  - `publishAccountIds` 定义和初始化
  - `onMounted` / `onActivated`(若已存在)

- [ ] **Step 1: 在 `<script setup>` 顶部 import**

```js
import { useAppStore } from '@/stores/app'
import { useAccountStore } from '@/stores/account'
import { platformNameToKey, platformList } from '@/config/platforms'

const appStore = useAppStore()
const accountStore = useAccountStore()
```

- [ ] **Step 2: 进入页面时清理 publishAccountIds**

找到 `onMounted`(若无,新增):

```js
onMounted(() => {
  // 清理 publishAccountIds 中属于黑名单平台的账号
  const filtered = new Set()
  for (const id of publishAccountIds.value) {
    const acc = accountStore.accounts.find(a => a.id === id)
    if (!acc) continue
    const key = platformNameToKey[acc.platform]
    if (key && !appStore.isPlatformDisabled(key)) {
      filtered.add(id)
    }
  }
  publishAccountIds.value = filtered
})
```

(`onMounted` 已 import 跳过)

- [ ] **Step 3: 「渠道个性化」checkbox 区过滤黑名单平台**

定位 line 61 附近 `v-for` 或 `v-if` 渲染「渠道个性化」checkbox 的部分。原本可能直接遍历 `platformList`,改为:

```js
// 在 <script setup> 中新增计算属性
const visiblePlatformsForCustomize = computed(() =>
  platformList.filter(p => !appStore.isPlatformDisabled(p.key))
)
```

把 template 中渠道个性化区域的 `v-for="p in platformList"` 改为 `v-for="p in visiblePlatformsForCustomize"`。

(具体变量名以实际代码为准)

- [ ] **Step 4: 浏览器验证**

- 系统设置 → 添加「小红书」到黑名单
- 进入视频发布页
- 左侧账号栏 + 「+ 添加账号」弹窗 + 「渠道个性化」区域**都不应**出现小红书
- 即使之前选中过小红书账号,进入页面后被自动清理

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(publish-center): 渠道个性化过滤黑名单并清理已选 publishAccountIds"
```

---

### Task 9:ImagePublish 同上(基于 IMAGE_PLATFORMS)

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`(1674 行)

**先调研:**
- Read 文件,确认 `IMAGE_PLATFORMS` 定义位置(约 line 298 `IMAGE_PLATFORMS = platformList.filter(...)`)
- 找到「渠道个性化」对应区域 + `publishAccountIds`

- [ ] **Step 1: 在 `<script setup>` 顶部 import**

```js
import { useAppStore } from '@/stores/app'
import { useAccountStore } from '@/stores/account'
import { platformNameToKey } from '@/config/platforms'

const appStore = useAppStore()
const accountStore = useAccountStore()
```

- [ ] **Step 2: onMounted 清理 publishAccountIds**

```js
onMounted(() => {
  const filtered = new Set()
  for (const id of publishAccountIds.value) {
    const acc = accountStore.accounts.find(a => a.id === id)
    if (!acc) continue
    const key = platformNameToKey[acc.platform]
    if (key && !appStore.isPlatformDisabled(key)) {
      filtered.add(id)
    }
  }
  publishAccountIds.value = filtered
})
```

- [ ] **Step 3: 「渠道个性化」过滤**

```js
const visibleImagePlatformsForCustomize = computed(() =>
  IMAGE_PLATFORMS.filter(p => !appStore.isPlatformDisabled(p.key))
)
```

template 中相应位置 `v-for="p in IMAGE_PLATFORMS"` 改为 `v-for="p in visibleImagePlatformsForCustomize"`。

- [ ] **Step 4: 浏览器验证**

- 系统设置 → 添加「腾讯视频」到黑名单(图集不支持腾讯视频,但用小红书测试更准)
- 添加「小红书」到黑名单
- 进入图集发布页
- 各处都不出现小红书

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ImagePublish.vue
git commit -m "feat(image-publish): 渠道个性化过滤黑名单并清理 publishAccountIds"
```

---

### Task 10:AccountManagement 加「已拉黑」tag + 禁用按钮

**Files:**
- Modify: `frontend/src/views/AccountManagement.vue`(1109 行)

**先调研:**
- Read 文件,定位卡片渲染区(line 53-110 附近,有 `account-card` class 和 `handleReLogin` / `handleSyncProfile` / `handleOpenCreatorCenter` / `handleDelete`)

- [ ] **Step 1: 在 `<script setup>` 顶部 import + 加 helper**

```js
import { useAppStore } from '@/stores/app'
import { platformNameToKey } from '@/config/platforms'

const appStore = useAppStore()

const isAccountDisabled = (account) => {
  const key = platformNameToKey[account.platform]
  return !!(key && appStore.isPlatformDisabled(key))
}
```

- [ ] **Step 2: template 中卡片右上角加 tag**

定位 line 53 附近的 `<div class="account-card">`,在合适位置(如 platform-name 旁边)加:

```html
<el-tag
  v-if="isAccountDisabled(account)"
  type="info"
  size="small"
  effect="plain"
  class="disabled-tag"
>
  已拉黑
</el-tag>
```

- [ ] **Step 3: template 中禁用「登录」「同步」「创作中心」按钮**

定位 line 79(`handleReLogin`)、line 90(`handleSyncProfile`)、line 97(`handleOpenCreatorCenter`)的三个 `<button>`,加 `:disabled`:

```html
<!-- 登录按钮(line 79 附近) -->
<button
  v-if="account.status === '异常'"
  class="action-btn login"
  :disabled="isAccountDisabled(account)"
  @click="handleReLogin(account)"
>
  {{ isAccountDisabled(account) ? '已拉黑' : '登录' }}
</button>

<!-- 同步按钮(line 90 附近) -->
<button
  class="action-btn sync"
  :disabled="isAccountDisabled(account) || account.status === '异常' || syncingIds.has(account.id)"
  @click="handleSyncProfile(account)"
>
  同步
</button>

<!-- 创作中心按钮(line 97 附近) -->
<button
  class="action-btn creator"
  :disabled="isAccountDisabled(account) || account.status === '异常'"
  @click="handleOpenCreatorCenter(account)"
>
  创作中心
</button>
```

**「删除」按钮**(line 101)**保持不变**(允许用户清理已拉黑平台的账号)。

- [ ] **Step 4: 用 `<el-tooltip>` 包裹禁用态按钮(可选)**

若希望 hover 禁用按钮时显示「该渠道已被加入黑名单,请先在系统设置中移除」,可以包一层 `<el-tooltip>`(但要注意 disabled button 不触发 mouseenter,需在父级 wrap)。

简化做法:加一个 CSS class 表示禁用态,加 `:title` 属性(原生 tooltip):

```html
<button
  ...
  :disabled="isAccountDisabled(account) || ..."
  :title="isAccountDisabled(account) ? '该渠道已被加入黑名单,请先在系统设置中移除' : ''"
  :class="['action-btn sync', { 'is-blacklisted': isAccountDisabled(account) }]"
>
```

- [ ] **Step 5: 样式(可选)**

在 `<style>` 中追加:

```css
.action-btn.is-blacklisted {
  opacity: 0.5;
  cursor: not-allowed;
}

.disabled-tag {
  margin-left: 8px;
}
```

- [ ] **Step 6: 浏览器验证**

- 系统设置 → 添加「小红书」到黑名单
- 进入账号管理页 → 已有小红书账号依然显示
- 卡片右上角显示「已拉黑」tag
- 「登录」「同步」「创作中心」按钮置灰不可点
- 「删除」按钮可点

- 系统设置 → 移除黑名单 → 账号管理页按钮恢复

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/AccountManagement.vue
git commit -m "feat(account-mgmt): 卡片显示「已拉黑」tag 并禁用登录/同步/创作中心按钮"
```

---

## Phase 3:登录弹窗重设计

### Task 11:新建 LoginDialog.vue 框架 + add 模式静态布局

**Files:**
- Create: `frontend/src/components/LoginDialog.vue`

- [ ] **Step 1: 创建文件,写入框架代码**

完整内容:

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    :width="mode === 'relogin' ? '420px' : '680px'"
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
    @open="onDialogOpen"
    @close="handleClose"
  >
    <!-- add 模式: 平台卡片网格 -->
    <div v-if="mode === 'add'" class="login-dialog-body">
      <p class="dialog-hint">选择要登录的平台,点击卡片即开始登录</p>
      <div v-if="cardList.length === 0" class="empty-state">
        所有渠道都已加入黑名单,请先在系统设置中移除后再来登录
      </div>
      <div v-else class="platform-grid">
        <div
          v-for="p in cardList"
          :key="p.key"
          :class="[
            'platform-card',
            `platform-${p.cssClass}`,
            `is-${p.status}`
          ]"
          @click="onCardClick(p)"
        >
          <!-- idle 状态 -->
          <template v-if="p.status === 'idle'">
            <div class="platform-logo-wrap">
              <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-logo" />
              <span v-else class="platform-letter">{{ p.letter }}</span>
            </div>
            <div class="platform-name">{{ p.name }}</div>
          </template>

          <!-- logging 状态 -->
          <template v-else-if="p.status === 'logging'">
            <el-icon class="loading-icon is-loading"><Loading /></el-icon>
            <div class="platform-name">{{ p.name }}</div>
            <div class="status-text">登录中...</div>
            <button class="cancel-btn" type="button" @click.stop="cancelLogin(p.key)">取消</button>
          </template>

          <!-- success 状态 -->
          <template v-else-if="p.status === 'success'">
            <el-icon class="success-icon"><Select /></el-icon>
            <div class="platform-name">{{ p.name }}</div>
            <div class="status-text">登录成功</div>
          </template>

          <!-- fail 状态 -->
          <template v-else-if="p.status === 'fail'">
            <el-icon class="fail-icon"><CloseBold /></el-icon>
            <div class="platform-name">{{ p.name }}</div>
            <div class="status-text fail-text">{{ p.errMsg || '登录失败' }}</div>
            <button class="retry-btn" type="button" @click.stop="retryLogin(p.key)">重试</button>
          </template>
        </div>
      </div>
    </div>

    <!-- relogin 模式: 单卡片 -->
    <div v-else class="login-dialog-body relogin-body">
      <div v-if="reloginPlatform" class="relogin-card" :class="`platform-${reloginPlatform.cssClass}`">
        <div class="platform-logo-wrap">
          <img v-if="reloginPlatform.logo" :src="reloginPlatform.logo" :alt="reloginPlatform.name" class="platform-logo" />
          <span v-else class="platform-letter">{{ reloginPlatform.letter }}</span>
        </div>
        <div class="platform-name">{{ reloginPlatform.name }}</div>
        <template v-if="reloginStatus === 'logging'">
          <el-icon class="loading-icon is-loading"><Loading /></el-icon>
          <div class="status-text">登录中...</div>
        </template>
        <template v-else-if="reloginStatus === 'success'">
          <el-icon class="success-icon"><Select /></el-icon>
          <div class="status-text">登录成功</div>
        </template>
        <template v-else-if="reloginStatus === 'fail'">
          <el-icon class="fail-icon"><CloseBold /></el-icon>
          <div class="status-text fail-text">{{ reloginErrMsg || '登录失败' }}</div>
          <button class="retry-btn" type="button" @click="startRelogin">重试</button>
        </template>
        <p class="relogin-hint">正在打开浏览器,请在弹出的浏览器窗口中完成登录</p>
      </div>
      <div v-else class="empty-state">账号信息异常</div>
    </div>

    <template #footer>
      <el-button v-if="mode === 'relogin' && reloginStatus === 'logging'"
                 @click="cancelRelogin">取消登录</el-button>
      <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading, Select, CloseBold } from '@element-plus/icons-vue'
import { useAppStore } from '@/stores/app'
import { platformList, PLATFORMS, platformNameToKey } from '@/config/platforms'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  mode: { type: String, default: 'add' },  // 'add' | 'relogin'
  account: { type: Object, default: null }
})

const emit = defineEmits(['update:modelValue', 'success', 'fail'])

const appStore = useAppStore()

// add 模式: 多卡片状态
const cardStates = reactive({})  // key -> { status, errMsg }
const eventSources = new Map()   // key -> EventSource(非响应式)

// relogin 模式: 单卡片状态
const reloginStatus = ref('idle')
const reloginErrMsg = ref('')
const reloginPlatform = computed(() => {
  if (props.mode !== 'relogin' || !props.account) return null
  const key = platformNameToKey[props.account.platform]
  return key ? PLATFORMS[key] : null
})
const reloginKey = computed(() => reloginPlatform.value?.key)

const dialogTitle = computed(() => {
  if (props.mode === 'relogin' && reloginPlatform.value) {
    return `重新登录:${reloginPlatform.value.name}`
  }
  return '添加账号'
})

// 卡片列表(响应式:平台状态变化时自动更新)
const cardList = computed(() =>
  platformList
    .filter(p => !appStore.isPlatformDisabled(p.key))
    .map(p => ({
      ...p,
      status: cardStates[p.key]?.status || 'idle',
      errMsg: cardStates[p.key]?.errMsg || ''
    }))
)

function setCardStatus(key, status, errMsg = '') {
  cardStates[key] = { status, errMsg }
}

function onDialogOpen() {
  if (props.mode === 'add') {
    initCardStates()
  } else if (props.mode === 'relogin') {
    startRelogin()
  }
}

function initCardStates() {
  // 清掉旧状态
  for (const k of Object.keys(cardStates)) delete cardStates[k]
}

function handleClose() {
  // 清理所有 SSE 连接
  for (const key of eventSources.keys()) closeSSE(key)
  emit('update:modelValue', false)
}

// ===== SSE 逻辑在 Task 12 实现 =====
function startLogin(platformKey, accountId = null) {
  // 占位,Task 12 实现
}

function closeSSE(platformKey) {
  const es = eventSources.get(platformKey)
  if (es) {
    es.close()
    eventSources.delete(platformKey)
  }
}

function onCardClick(p) {
  if (p.status === 'idle' || p.status === 'fail') {
    startLogin(p.key)
  }
}

function cancelLogin(platformKey) {
  closeSSE(platformKey)
  setCardStatus(platformKey, 'idle')
  ElMessage.info('已取消登录')
}

function retryLogin(platformKey) {
  closeSSE(platformKey)
  startLogin(platformKey)
}

function startRelogin() {
  if (!reloginKey.value || !props.account) return
  reloginStatus.value = 'logging'
  reloginErrMsg.value = ''
  // Task 12 中实现 startLogin(reloginKey.value, props.account.id) + 监听 status 更新 reloginStatus
}

function cancelRelogin() {
  if (reloginKey.value) closeSSE(reloginKey.value)
  reloginStatus.value = 'idle'
  ElMessage.info('已取消登录')
}
</script>

<style scoped>
.login-dialog-body {
  padding: 0 4px;
}

.dialog-hint {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  margin: 0 0 16px 0;
}

.platform-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.platform-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 16px 8px;
  min-height: 130px;
  border: 2px solid var(--el-border-color);
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  background: var(--el-bg-color);
  position: relative;
}

.platform-card.is-idle:hover {
  border-color: var(--el-color-primary);
  transform: translateY(-2px);
}

.platform-card.is-logging {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  cursor: progress;
}

.platform-card.is-success {
  border-color: var(--el-color-success);
  background: var(--el-color-success-light-9);
  cursor: default;
}

.platform-card.is-fail {
  border-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.platform-logo-wrap {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}

.platform-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
}

.platform-letter {
  font-size: 20px;
  font-weight: bold;
}

.platform-name {
  font-size: 13px;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.status-text {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.fail-text {
  color: var(--el-color-danger);
  max-width: 100%;
  word-break: break-all;
  text-align: center;
  padding: 0 4px;
}

.loading-icon {
  font-size: 28px;
  color: var(--el-color-primary);
  margin-bottom: 6px;
}

.success-icon {
  font-size: 28px;
  color: var(--el-color-success);
  margin-bottom: 6px;
}

.fail-icon {
  font-size: 28px;
  color: var(--el-color-danger);
  margin-bottom: 6px;
}

.cancel-btn,
.retry-btn {
  margin-top: 6px;
  padding: 2px 10px;
  border: 1px solid currentColor;
  background: transparent;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
}

.cancel-btn {
  color: var(--el-text-color-secondary);
}

.retry-btn {
  color: var(--el-color-danger);
}

.empty-state {
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 40px 20px;
}

/* relogin 模式 */
.relogin-body {
  display: flex;
  justify-content: center;
}

.relogin-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 32px 24px;
  border: 2px solid var(--el-border-color);
  border-radius: 12px;
  min-width: 280px;
}

.relogin-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  text-align: center;
}

@media (max-width: 640px) {
  .platform-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}
</style>
```

- [ ] **Step 2: 浏览器验证静态布局**

不要先接入 AccountManagement(下一个 task 再做)。临时在某个页面(如 AccountManagement 顶部)加测试代码:

```html
<el-button @click="testDialogVisible = true">测试 LoginDialog</el-button>
<LoginDialog v-model="testDialogVisible" mode="add" />
```

刷新 → 点测试按钮 → 看到 10 个平台卡片(idle 态),hover 高亮。点卡片暂时无反应(Task 12 接入 SSE)。

切换 relogin 模式测试:

```html
<LoginDialog v-model="testDialogVisible" mode="relogin" :account="{ platform: '小红书' }" />
```

看到单一卡片 + 「登录中...」spinner(reloginStatus 被立即设为 logging,但 SSE 未启动,会一直 loading)。

**测试完移除测试代码。**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/LoginDialog.vue
git commit -m "feat(login-dialog): 新建 LoginDialog 组件框架与静态布局"
```

---

### Task 12:LoginDialog 接入 SSE 逻辑

**Files:**
- Modify: `frontend/src/components/LoginDialog.vue`

- [ ] **Step 1: 替换 `startLogin` 占位实现**

```js
function startLogin(platformKey, accountId = null) {
  const platform = PLATFORMS[platformKey]
  if (!platform) return

  const type = platform.id  // 1-10
  const tempId = crypto.randomUUID()
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'
  let url = `${baseUrl}/login?type=${type}&id=${encodeURIComponent(tempId)}`
  if (accountId) {
    url += `&account_id=${encodeURIComponent(accountId)}`
  }

  setCardStatus(platformKey, 'logging')
  // 若是 relogin 模式,由 startRelogin 单独处理 reloginStatus
  if (props.mode === 'relogin' && reloginKey.value === platformKey) {
    reloginStatus.value = 'logging'
  }

  const es = new EventSource(url)
  eventSources.set(platformKey, es)

  es.onmessage = (event) => {
    let result
    try {
      result = JSON.parse(event.data)
    } catch (e) {
      // 非 JSON,忽略(本场景不应出现二维码)
      return
    }

    if (result.status === '200') {
      setCardStatus(platformKey, 'success')
      closeSSE(platformKey)
      if (props.mode === 'relogin' && reloginKey.value === platformKey) {
        reloginStatus.value = 'success'
      }
      emit('success', { platform: platformKey, accountId: accountId || undefined })
      ElMessage.success(`${platform.name} 登录成功`)
      // relogin 模式: 1.5s 后自动关闭弹窗
      if (props.mode === 'relogin') {
        setTimeout(() => {
          emit('update:modelValue', false)
        }, 1500)
      }
      return
    }

    if (result.status === '500' || result.status === '0' || result.status === 'error') {
      const errMsg = result.msg || result.error || '登录失败'
      setCardStatus(platformKey, 'fail', errMsg)
      closeSSE(platformKey)
      if (props.mode === 'relogin' && reloginKey.value === platformKey) {
        reloginStatus.value = 'fail'
        reloginErrMsg.value = errMsg
      }
      emit('fail', { platform: platformKey, errMsg })
      return
    }

    // status === '1' 或其他: 等待中,保持 logging
  }

  es.onerror = () => {
    // 成功后 closeSSE 也会触发 onerror,需检查状态防误判
    if (cardStates[platformKey]?.status === 'success') return
    if (props.mode === 'relogin' && reloginStatus.value === 'success') return

    const errMsg = '连接断开,请检查后端服务'
    setCardStatus(platformKey, 'fail', errMsg)
    closeSSE(platformKey)
    if (props.mode === 'relogin' && reloginKey.value === platformKey) {
      reloginStatus.value = 'fail'
      reloginErrMsg.value = errMsg
    }
    emit('fail', { platform: platformKey, errMsg })
  }
}
```

- [ ] **Step 2: 完善 `startRelogin` 调用 `startLogin`**

```js
function startRelogin() {
  if (!reloginKey.value || !props.account) return
  closeSSE(reloginKey.value)  // 清旧连接
  startLogin(reloginKey.value, props.account.id)
}
```

- [ ] **Step 3: 完善 `cancelRelogin`**

```js
function cancelRelogin() {
  if (reloginKey.value) closeSSE(reloginKey.value)
  reloginStatus.value = 'idle'
  ElMessage.info('已取消登录')
}
```

- [ ] **Step 4: 浏览器手动验证(关键!需要真实后端 + 浏览器)**

启动后端 + 前端,**临时**在某个页面挂测试代码:

```html
<el-button @click="testDialogVisible = true">测试 LoginDialog</el-button>
<LoginDialog v-model="testDialogVisible" mode="add" @success="p => console.log('success', p)" />
```

刷新 → 点测试按钮 → 点「B站」卡片 →
- 卡片切到 logging 状态(spinner + 「登录中...」)
- 后端启动 Playwright 浏览器窗口弹出
- 在浏览器中登录 B 站
- 登录成功 → 卡片切到 success(✓ + 绿色描边)+ Toast「B站 登录成功」
- Console 输出 `success { platform: 'bilibili' }`

测试失败场景:
- 点「小红书」卡片 → 在 Playwright 浏览器中关闭登录窗口 / 等待超时
- 卡片切到 fail(✕ + 错误文案 + 「重试」按钮)

测试取消:
- 点「抖音」卡片 → 在 logging 状态下点卡片底部「取消」
- 卡片回到 idle + Toast「已取消登录」

**测试完移除测试代码。**

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/LoginDialog.vue
git commit -m "feat(login-dialog): 接入 SSE 登录逻辑(add/relogin 双模式)"
```

---

### Task 13:AccountManagement 替换内嵌 dialog 为 `<LoginDialog>` + 删除遗留 SSE 代码

**Files:**
- Modify: `frontend/src/views/AccountManagement.vue`(主要删 line 124-186 dialog、line 514-608 SSE 代码、相关 state)

**先调研:**
- Read `frontend/src/views/AccountManagement.vue`,定位:
  - 现有 `<el-dialog>` (line 124-186) 的 template 块
  - 单例 `eventSource`(line 514)
  - `connectSSE`(line 520-608)
  - `closeSSEConnection`(line 516-518)
  - `qrCodeData`、`loginStatus`、`sseConnecting` 等 ref
  - `handleAddAccount` / `handleReLogin` 函数
  - `submitAccountForm` 函数(line 610)
  - `dialogType` / `dialogVisible` 状态
  - `fetchAccountsQuick`(成功后调用)

- [ ] **Step 1: 在 `<script setup>` 顶部 import LoginDialog**

```js
import LoginDialog from '@/components/LoginDialog.vue'
```

- [ ] **Step 2: 加 LoginDialog 弹窗控制 state**

```js
const loginDialogVisible = ref(false)
const loginMode = ref('add')  // 'add' | 'relogin'
const reloginAccount = ref(null)
```

- [ ] **Step 3: 改写 `handleAddAccount` 和 `handleReLogin`**

原 `handleAddAccount`(可能是打开原 dialog + 选平台)简化为:

```js
const handleAddAccount = () => {
  loginMode.value = 'add'
  reloginAccount.value = null
  loginDialogVisible.value = true
}
```

原 `handleReLogin(account)`:

```js
const handleReLogin = (account) => {
  if (isAccountDisabled(account)) return  // 黑名单禁用
  loginMode.value = 'relogin'
  reloginAccount.value = account
  loginDialogVisible.value = true
}
```

(`isAccountDisabled` 在 Task 10 已定义)

- [ ] **Step 4: 加 `onLoginSuccess` / `onLoginFail` 回调**

```js
const onLoginSuccess = ({ platform, accountId }) => {
  // 沿用现有机制:刷新账号列表(后端 sync_profile 已写库)
  fetchAccountsQuick()
}

const onLoginFail = ({ platform, errMsg }) => {
  console.warn(`登录失败 [${platform}]:`, errMsg)
}
```

- [ ] **Step 5: 在 template 中替换原 `<el-dialog>`**

定位原 dialog(line 124-186),整段替换为:

```html
<LoginDialog
  v-model="loginDialogVisible"
  :mode="loginMode"
  :account="reloginAccount"
  @success="onLoginSuccess"
  @fail="onLoginFail"
/>
```

删除原 dialog 内的:
- 平台 select
- 账号名 input(用户决定不再填账号名)
- 「登录中...」/「登录成功」/「添加失败」三态文本展示
- 二维码展示区(如果有)

- [ ] **Step 6: 删除遗留 SSE 代码**

删除:
- 单例 `let eventSource = null`(line 514)
- `closeSSEConnection` 函数(line 516-518)
- `connectSSE` 函数(line 520-608)
- `qrCodeData` ref(若有,在 line 524 附近)
- `loginStatus` ref(若有)
- `sseConnecting` ref(若有)
- `submitAccountForm` 中调用 `connectSSE` 的分支(line 610-628 中的 dialogType === 'add' 分支)

`submitAccountForm` 改造后只保留 `dialogType === 'edit'` 的更新逻辑(如果还有编辑账号名功能的话),或者整个删除(如果不再需要)。

- [ ] **Step 7: 检查其他引用**

用 grep 确认所有 `qrCodeData`、`loginStatus`、`sseConnecting`、`connectSSE`、`closeSSEConnection` 引用都已清理:

```bash
grep -n "qrCodeData\|loginStatus\|sseConnecting\|connectSSE\|closeSSEConnection" frontend/src/views/AccountManagement.vue
```

Expected: 无输出(或仅注释中残留,可一并清掉)。

- [ ] **Step 8: 浏览器完整流程验证**

**新增账号流程:**
- 进入账号管理页 → 点顶部「添加账号」按钮
- 弹窗打开 → 显示 10 个平台卡片(若黑名单有渠道则不显示)
- 点「B站」卡片 → 切到 logging + 后端弹出 Playwright 浏览器
- 在浏览器中登录 B 站 → 卡片切到 success + Toast
- 点弹窗「关闭」→ 弹窗关闭
- 账号列表自动刷新出现 B 站账号(带真实 nickname)

**重新登录流程:**
- 找一个状态为「异常」的账号(或手动改 DB 把某账号 status 改成「异常」)
- 点该卡片的「登录」按钮
- 弹窗显示「重新登录:B站」+ 立即进入 logging
- 后端弹出浏览器 → 重新登录 → 卡片显示 ✓ → 1.5s 后弹窗关闭
- 账号状态变正常

**失败重试:**
- 点卡片 → 关闭后端浏览器 / 等待超时
- 卡片显示 fail + 「重试」按钮
- 点「重试」→ 重新进入 logging

**取消:**
- 点卡片进入 logging → 点卡片底部「取消」
- 卡片回到 idle + Toast

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/AccountManagement.vue
git commit -m "refactor(account-mgmt): 替换内嵌登录 dialog 为 LoginDialog 组件并清理遗留 SSE 代码"
```

---

## Phase 4:E2E 验证(gstack /qa + Playwright)

### Task 14:E2E — 黑名单完整流程

**目的:** 用 Playwright 真浏览器跑一遍黑名单的添加/生效/移除闭环。

- [ ] **Step 1: 启动后端 + 前端**

```bash
cd backend && python3 app.py &
cd frontend && npm run dev &
```

- [ ] **Step 2: 用 gstack /qa 或直接 Playwright 跑流程**

如果用 gstack:

```
/qa 测试渠道黑名单:
1. 进入「系统设置」页面
2. 点「+ 添加渠道」按钮,弹窗出现
3. 勾选「小红书」「抖音」,点「确认添加(2)」
4. 验证:card 区域出现「小红书」「抖音」两个 chip
5. 进入「视频发布」页面
6. 验证:左侧账号栏无小红书/抖音分组
7. 点「+ 添加账号」,验证:弹窗平台筛选条无小红书/抖音,账号列表无小红书/抖音账号
8. 进入「账号管理」页面,点「添加账号」
9. 验证:LoginDialog 弹窗中无小红书、抖音卡片
10. 回到「系统设置」,点小红书 chip 的 ✕
11. 进入「视频发布」,验证:小红书恢复显示
12. 进入「账号管理」添加账号,验证:小红书卡片恢复
```

- [ ] **Step 3: 修复发现的问题(若有)**

记录 Playwright 报告的问题,逐一修复。

- [ ] **Step 4: 截图归档**

把成功跑通的截图保存(可选)。

- [ ] **Step 5: Commit**(若有修复)

```bash
git add ...
git commit -m "fix(blacklist): 修复 E2E 验证发现的问题"
```

---

### Task 15:E2E — 登录弹窗完整流程

**目的:** 验证登录弹窗的 add / relogin / 失败重试 / 取消等场景。

- [ ] **Step 1: 启动后端 + 前端**

(同 Task 14)

- [ ] **Step 2: 用 Playwright 跑流程**

```
/qa 测试登录弹窗:
【add 模式 - 成功】
1. 进入账号管理页
2. 点「添加账号」,弹窗显示 10 个平台卡片
3. 点「B站」卡片,卡片切到 logging(spinner + 登录中...)
4. 后端弹出 Playwright 浏览器
5. 在浏览器中完成 B 站登录
6. 验证:卡片切到 success(✓ + 绿色描边),Toast「B站 登录成功」
7. 关闭弹窗
8. 验证:账号列表出现 B 站账号,带真实 nickname

【add 模式 - 多并发】
9. 重新打开弹窗,同时点「抖音」「快手」
10. 验证:两个卡片都进入 logging 状态
11. 在两个浏览器窗口分别登录
12. 验证:两个卡片都切到 success

【add 模式 - 失败重试】
13. 点「小红书」卡片,在浏览器中关闭登录窗口
14. 验证:卡片切到 fail,显示「重试」按钮
15. 点「重试」,卡片重新进入 logging

【add 模式 - 取消】
16. 点「百家号」卡片,在 logging 状态下点卡片底部「取消」
17. 验证:卡片回到 idle + Toast「已取消登录」

【relogin 模式】
18. 找一个状态为「异常」的账号(或手动改 DB)
19. 点该卡片「登录」按钮
20. 验证:弹窗显示「重新登录:{平台}」+ 立即进入 logging
21. 后端弹出浏览器,完成登录
22. 验证:卡片显示 ✓ → 1.5s 后弹窗自动关闭
23. 验证:账号状态变正常

【黑名单 + 登录共存】
24. 系统设置中把小红书加入黑名单
25. 账号管理中,小红书卡片显示「已拉黑」tag,「登录」「同步」「创作中心」禁用
26. 点「添加账号」,弹窗中无小红书卡片
27. 移除黑名单后,卡片恢复
```

- [ ] **Step 3: 修复发现的问题(若有)**

- [ ] **Step 4: Commit**(若有修复)

```bash
git add ...
git commit -m "fix(login-dialog): 修复 E2E 验证发现的问题"
```

---

## Self-Review

### Spec coverage check

| Spec 章节 | 对应 Task |
|----------|----------|
| 关键决策 - 数据存储 settings | Task 1, 2 |
| 关键决策 - JSON 序列化 | Task 2(GET 时 JSON.parse) |
| 关键决策 - 批量 PUT | Task 1(addDisabledPlatforms 单次 PUT), Task 5 |
| 关键决策 - account.platform 中文名转换 | Task 6, 7, 8, 9, 10(各消费方) |
| 关键决策 - 卡片保持 success 不淡出 | Task 11(模板逻辑) |
| 关键决策 - 不自动关闭弹窗 | Task 11(add 模式无自动关闭, relogin 模式 1.5s 后关闭) |
| 关键决策 - SSE Map 多并发 | Task 11(eventSources Map), Task 12(startLogin) |
| Settings card 小卡片网格 + ✕ | Task 3, 4 |
| PlatformBlacklistDialog | Task 5 |
| AccountSidebar 过滤 | Task 6 |
| AccountSelectDialog 过滤 | Task 7 |
| PublishCenter / ImagePublish 过滤 | Task 8, 9 |
| AccountManagement 「已拉黑」tag + 禁用按钮 | Task 10 |
| LoginDialog add 模式 | Task 11, 12 |
| LoginDialog relogin 模式 | Task 11(静态), Task 12(逻辑) |
| AccountManagement 替换 + 清理 | Task 13 |
| E2E 黑名单流 | Task 14 |
| E2E 登录弹窗 | Task 15 |

无遗漏。

### Placeholder scan

- ✅ 无 "TBD" / "TODO" / "implement later"
- ✅ 每个代码 step 都有完整代码
- ✅ 每个 commit step 都有具体 message
- ✅ 无"类似 Task N"引用,代码都重复展示

### Type consistency

- `appStore.isPlatformDisabled(key)` — Task 1 定义,Task 6/7/8/9/10/11 一致使用
- `appStore.addDisabledPlatforms(keys[])` — Task 1 定义,Task 5 使用
- `appStore.removeDisabledPlatform(key)` — Task 1 定义,Task 4 使用
- `isAccountDisabled(account)` — Task 10 定义,Task 13 使用
- `LoginDialog` props (`mode`, `account`) — Task 11 定义,Task 13 使用
- `LoginDialog` emits (`success`, `fail`) — Task 11 定义,Task 13 使用
- `cardStates[key] = { status, errMsg }` — Task 11 定义,Task 12 使用
- `platformNameToKey` 在所有按 account 过滤处一致使用

一致。

---

## 总结

15 个 task,4 个 phase,每个 phase 结束都有独立可验收的成果:

- **Phase 1 结束** (Task 1-5): 黑名单可以在 Settings 页添加/移除,持久化到后端
- **Phase 2 结束** (Task 6-10): 黑名单在发布页/账号管理页生效,可手动验证
- **Phase 3 结束** (Task 11-13): 新登录弹窗可使用,旧 SSE 代码清理
- **Phase 4 结束** (Task 14-15): E2E 验证完整流程

预计工作量:**1-2 个工作日**(熟练 Vue 工程师)。

每个 task 都有:
- 精确文件路径
- 完整代码片段
- 浏览器手动验证步骤
- 中文 commit message

执行模式可选 subagent-driven(推荐,每 task 一个 subagent + 两阶段 review)或 inline executing-plans(本会话内执行)。
