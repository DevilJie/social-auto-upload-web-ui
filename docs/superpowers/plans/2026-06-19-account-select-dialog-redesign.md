# AccountSelectDialog 三栏改造 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `AccountSelectDialog.vue` 从左右两栏（单选渠道/标签混合 + el-checkbox 行）改造成左中右三栏（多选渠道 + 卡片网格 + 多选标签 OR 筛选），复用 BatchTagDialog 视觉风格，禁止创建新标签。

**Architecture:**
- 单一组件改造，props/emits 接口不变（PublishCenter.vue、ImagePublish.vue 调用方零修改）
- 状态从 `accountFilterPlatform: string` + `accountFilterTag: number` 改为 `selectedPlatformNames: Set<string>` + `selectedTagIds: Set<number>`（OR 语义）
- 卡片样式直接复用 BatchTagDialog 的 .batch-account-card（统一视觉）

**Tech Stack:** Vue 3 + Element Plus + SCSS

---

## File Structure

### 修改文件
- `frontend/src/components/AccountSelectDialog.vue` — 主改造（状态、模板、样式）

### 不变（向后兼容）
- `frontend/src/views/PublishCenter.vue` — 调用方不变
- `frontend/src/views/ImagePublish.vue` — 调用方不变

---

## Task 1: AccountSelectDialog 三栏改造

**Files:**
- Modify: `frontend/src/components/AccountSelectDialog.vue`（全文重写）

- [ ] **Step 1: 改造 `<template>` 为三栏结构**

完整替换 `<template>` 部分（约 line 1-93）为：

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    title="选择账号"
    width="960px"
    :close-on-click-modal="false"
    class="account-select-dialog"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="account-dialog-body">
      <!-- 左:渠道筛选 -->
      <div class="account-section platform-section">
        <div class="account-section-header">
          <span class="account-section-title">渠道筛选</span>
          <span class="account-section-count">已选 {{ selectedPlatformNames.size }}</span>
        </div>
        <div class="platform-list">
          <label
            v-for="p in platforms"
            :key="p.key"
            :class="['platform-item', 'cursor-pointer', { active: selectedPlatformNames.has(p.name) }]"
          >
            <el-checkbox
              :model-value="selectedPlatformNames.has(p.name)"
              @change="togglePlatform(p.name)"
            />
            <span class="platform-badge">
              <img v-if="p.logo" :src="p.logo" :alt="p.name" class="platform-badge-img">
              <template v-else>{{ p.letter }}</template>
            </span>
            <span class="platform-name">{{ p.name }}</span>
          </label>
          <div v-if="platforms.length === 0" class="empty-hint">暂无可选渠道</div>
        </div>
      </div>

      <!-- 中:账号卡片 -->
      <div class="account-section accounts-section">
        <div class="account-section-header">
          <span class="account-section-title">账号</span>
          <span class="account-section-count">已选 {{ tempSelectedAccounts.length }} / {{ accounts.length }}</span>
          <el-button size="small" link type="primary" class="ml-auto" @click="toggleSelectAll">
            {{ isAllSelected ? '取消全选' : '一键全选' }}
          </el-button>
        </div>
        <div class="account-grid">
          <div
            v-for="account in filteredAccounts"
            :key="account.id"
            :class="['account-card', { selected: tempSelectedAccounts.includes(account.id), disabled: account.status !== '正常' }]"
            @click="account.status === '正常' && toggleAccount(account.id)"
          >
            <div class="account-avatar">
              <img v-if="account.avatar" :src="proxyAvatar(account.avatar)" :alt="account.name">
              <img v-else :src="getDefaultAvatar(account.name)" :alt="account.name">
            </div>
            <div class="account-info">
              <div class="account-name" :title="account.name">{{ account.name }}</div>
              <div class="account-meta">
                <span class="account-platform">{{ account.platform }}</span>
                <span
                  v-for="tag in account.tags || []"
                  :key="tag.id"
                  class="account-tag-pill"
                  :style="{ borderColor: tag.color, color: tag.color }"
                >{{ tag.name }}</span>
              </div>
            </div>
            <div v-if="tempSelectedAccounts.includes(account.id)" class="account-check">
              <el-icon><Check /></el-icon>
            </div>
          </div>
          <div v-if="filteredAccounts.length === 0" class="empty-hint">暂无可选账号</div>
        </div>
      </div>

      <!-- 右:标签筛选 -->
      <div class="account-section tag-section">
        <div class="account-section-header">
          <span class="account-section-title">标签筛选</span>
          <span class="account-section-count">已选 {{ selectedTagIds.size }}</span>
          <el-button
            size="small"
            link
            type="primary"
            class="ml-auto"
            :disabled="selectedTagIds.size === 0"
            @click="clearAllTags"
          >全不选</el-button>
        </div>

        <div v-if="accountStore.allTags.length > 0" class="tag-search">
          <el-input
            v-model="tagKeyword"
            size="default"
            placeholder="搜索标签..."
            clearable
          />
        </div>

        <div class="tag-list">
          <div
            v-for="tag in filteredTags"
            :key="tag.id"
            :class="['tag-chip', { selected: selectedTagIds.has(tag.id) }]"
            :style="selectedTagIds.has(tag.id)
              ? { background: tag.color, borderColor: tag.color, color: '#fff' }
              : { borderColor: tag.color, color: tag.color }"
            @click="toggleTag(tag.id)"
          >
            <el-icon v-if="selectedTagIds.has(tag.id)" class="tag-check"><Check /></el-icon>
            <span>{{ tag.name }}</span>
          </div>
          <div v-if="accountStore.allTags.length === 0" class="empty-hint">暂无标签</div>
          <div v-else-if="filteredTags.length === 0" class="empty-hint">没有匹配的标签</div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <span class="selected-count">已选择 {{ tempSelectedAccounts.length }} 个账号</span>
        <div class="dialog-footer-btns">
          <el-button @click="$emit('update:modelValue', false)">取消</el-button>
          <el-button type="primary" @click="confirmSelection">确认添加</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>
```

- [ ] **Step 2: 改造 `<script setup>` 状态和逻辑**

完整替换 `<script setup>` 部分（约 line 95-176）为：

```javascript
<script setup>
import { ref, computed, watch } from 'vue'
import { Check } from '@element-plus/icons-vue'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { accountApi } from '@/api/account'
import { getDefaultAvatar, proxyAvatar } from '@/utils/avatar'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  platforms: { type: Array, required: true },
  publishAccountIds: { type: Set, required: true },
})

const emit = defineEmits(['update:modelValue', 'confirm'])

const accountStore = useAccountStore()
const appStore = useAppStore()

const selectedPlatformNames = ref(new Set())
const selectedTagIds = ref(new Set())
const tempSelectedAccounts = ref([])
const tagKeyword = ref('')

const isPlatformKeyDisabled = (key) => appStore.isPlatformDisabled(key)

const filteredAccounts = computed(() => {
  let list = accountStore.accounts
  // 黑名单过滤
  list = list.filter(a => !isPlatformKeyDisabled(platformKeyOf(a)))
  // 渠道筛选（空集 = 不过滤）
  if (selectedPlatformNames.value.size > 0) {
    list = list.filter(a => selectedPlatformNames.value.has(a.platform))
  }
  // 标签筛选（OR 语义）
  if (selectedTagIds.value.size > 0) {
    list = list.filter(a => a.tags?.some(t => selectedTagIds.value.has(t.id)))
  }
  return list
})

const validFilteredAccounts = computed(() =>
  filteredAccounts.value.filter(a => a.status === '正常')
)

const filteredTags = computed(() => {
  const all = accountStore.allTags
  if (!tagKeyword.value.trim()) return all
  const kw = tagKeyword.value.trim().toLowerCase()
  return all.filter(t => t.name.toLowerCase().includes(kw))
})

const isAllSelected = computed(() => {
  const ids = validFilteredAccounts.value.map(a => a.id)
  if (ids.length === 0) return false
  return ids.every(id => tempSelectedAccounts.value.includes(id))
})

function platformKeyOf(account) {
  // a.platform 是 name（如 "小红书"）；查找对应 key（用于黑名单检查）
  const entry = props.platforms.find(p => p.name === account.platform)
  return entry?.key || ''
}

function togglePlatform(name) {
  const next = new Set(selectedPlatformNames.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  selectedPlatformNames.value = next
}

function toggleAccount(id) {
  if (tempSelectedAccounts.value.includes(id)) {
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(x => x !== id)
  } else {
    tempSelectedAccounts.value = [...tempSelectedAccounts.value, id]
  }
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    const visibleIds = new Set(validFilteredAccounts.value.map(a => a.id))
    tempSelectedAccounts.value = tempSelectedAccounts.value.filter(id => !visibleIds.has(id))
  } else {
    const visibleIds = validFilteredAccounts.value.map(a => a.id)
    const merged = new Set([...tempSelectedAccounts.value, ...visibleIds])
    tempSelectedAccounts.value = [...merged]
  }
}

function toggleTag(tagId) {
  const next = new Set(selectedTagIds.value)
  if (next.has(tagId)) next.delete(tagId)
  else next.add(tagId)
  selectedTagIds.value = next
}

function clearAllTags() {
  selectedTagIds.value = new Set()
}

function confirmSelection() {
  emit('confirm', [...tempSelectedAccounts.value])
  emit('update:modelValue', false)
}

watch(() => props.modelValue, async (visible) => {
  if (visible) {
    tempSelectedAccounts.value = [...props.publishAccountIds]
    selectedPlatformNames.value = new Set()
    selectedTagIds.value = new Set()
    tagKeyword.value = ''
    if (accountStore.accounts.length === 0) {
      try {
        const res = await accountApi.getAccounts()
        if (res.code === 200 && res.data) {
          accountStore.setAccounts(res.data)
        }
      } catch (e) {
        console.error('加载账号失败:', e)
      }
    }
  }
})
</script>
```

- [ ] **Step 3: 改造 `<style>` 三栏布局 + 卡片样式**

完整替换 `<style lang="scss" scoped>` 部分（约 line 178-367）为：

```scss
<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.account-select-dialog {
  :deep(.el-dialog__body) {
    padding: 16px 20px;
  }

  .account-dialog-body {
    display: flex;
    gap: 12px;
    height: 520px;
  }

  .account-section {
    display: flex;
    flex-direction: column;
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid $border;
    border-radius: $radius-card;
    overflow: hidden;
  }

  .platform-section {
    flex: 1;
    min-width: 180px;
  }

  .accounts-section {
    flex: 2.2;
  }

  .tag-section {
    flex: 1;
    min-width: 220px;
  }

  .account-section-header {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid $border-light;
    background: rgba(255, 255, 255, 0.02);
    flex-shrink: 0;

    .account-section-title {
      font-size: 13px;
      font-weight: 600;
      color: $text-primary;
    }

    .account-section-count {
      font-size: 12px;
      color: $brand-start;
      font-weight: 500;
      padding: 2px 8px;
      background: rgba($brand-start, 0.12);
      border-radius: 10px;
    }

    .ml-auto {
      margin-left: auto;
      font-size: 12px;
    }
  }

  // ── 左:渠道列表 ──
  .platform-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .platform-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 10px;
    border-radius: 6px;
    cursor: pointer;
    transition: all $transition-fast;
    border-left: 3px solid transparent;

    &:hover { background: rgba(255, 255, 255, 0.04); }

    &.active {
      background: rgba($brand-start, 0.08);
      border-left-color: $brand-start;
    }

    .platform-badge {
      width: 24px;
      height: 24px;
      border-radius: 5px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: #fff;
      font-size: 11px;
      font-weight: 700;
      flex-shrink: 0;
      background: rgba(139, 92, 246, 0.12);

      .platform-badge-img { width: 20px; height: 20px; object-fit: contain; }
    }

    .platform-name {
      font-size: 13px;
      color: $text-primary;
    }

    :deep(.el-checkbox) {
      margin-right: 0;
    }
  }

  // ── 中:账号卡片网格（复用 BatchTagDialog 风格）──
  .account-grid {
    flex: 1;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
    gap: 8px;
    padding: 12px;
    overflow-y: auto;
    align-content: start;
  }

  .account-card {
    position: relative;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: $bg-surface;
    border: 1px solid $border;
    border-radius: $radius-sm;
    cursor: pointer;
    transition: all $transition-fast;

    &:hover:not(.disabled) {
      background: rgba($brand-start, 0.06);
      border-color: $border-active;
    }

    &.selected {
      background: rgba($brand-start, 0.12);
      border-color: $brand-start;
      box-shadow: 0 0 0 1px rgba($brand-start, 0.25);

      .account-name { color: #fff; font-weight: 600; }
    }

    &.disabled {
      opacity: 0.45;
      cursor: not-allowed;
    }

    .account-avatar {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: rgba($brand-start, 0.12);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      overflow: hidden;
      color: #c4b5fd;
      font-size: 12px;
      font-weight: 700;

      img { width: 100%; height: 100%; object-fit: cover; }
    }

    .account-info {
      flex: 1;
      min-width: 0;
    }

    .account-name {
      font-size: 12px;
      font-weight: 500;
      color: $text-primary;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      transition: color $transition-fast;
    }

    .account-meta {
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 3px;
      flex-wrap: wrap;
    }

    .account-platform {
      font-size: 10px;
      color: $text-muted;
    }

    .account-tag-pill {
      display: inline-flex;
      align-items: center;
      padding: 0 5px;
      border: 1px solid;
      border-radius: 3px;
      font-size: 9px;
      font-weight: 500;
      line-height: 14px;
    }

    .account-check {
      position: absolute;
      top: 4px;
      right: 4px;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: $brand-start;
      color: #fff;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 10px;
    }
  }

  // ── 右:标签区 ──
  .tag-search {
    padding: 12px 12px 4px;
    flex-shrink: 0;

    :deep(.el-input__wrapper) {
      background: $bg-surface;
      box-shadow: none;
      border-radius: $radius-sm;
      padding: 2px 12px;
    }
  }

  .tag-list {
    flex: 1;
    padding: 8px 12px 12px;
    overflow-y: auto;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-content: start;
  }

  .tag-chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    border: 1px solid;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all $transition-fast;
    background: transparent;
    user-select: none;

    &:hover {
      transform: translateY(-1px);
      box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }

    &.selected {
      font-weight: 600;
    }

    .tag-check { font-size: 12px; }
  }

  .empty-hint {
    width: 100%;
    text-align: center;
    padding: 24px 0;
    color: $text-muted;
    font-size: 13px;
  }

  // ── Footer ──
  .dialog-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;

    .selected-count { font-size: 13px; color: $text-muted; }
    .dialog-footer-btns { display: flex; gap: 8px; }
  }
}

.cursor-pointer { cursor: pointer; }
</style>
```

- [ ] **Step 4: Vite build 验证**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && bunx vite build 2>&1 | tail -10
```

Expected: `✓ built in <N>s` 无错

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add frontend/src/components/AccountSelectDialog.vue
git commit -m "refactor(account-select): 三栏改造 + 多选渠道/标签 + 卡片样式"
```

## Context

This is **Task 1 of 1**. Plan at `/home/czy/workspace/ai/social-auto-upload-web-ui/docs/superpowers/plans/2026-06-19-account-select-dialog-redesign.md`. Spec at `docs/superpowers/specs/2026-06-19-account-select-dialog-redesign-design.md`.

The改造涉及一个 367 行的 Vue 组件的全文替换。建议 implementer 一次性完成整个文件替换而非增量修改 — 模板/script/style 三部分都和现有版本差异显著，分步增量会产生大量中间态导致 review 困难。

调用方不变（PublishCenter.vue、ImagePublish.vue），props/emits 接口保持向后兼容。

## Important Constraints

- **`@/utils/avatar` 已存在** — 提供 `getDefaultAvatar` 和 `proxyAvatar`，与 BatchTagDialog 一致
- **`@element-plus/icons-vue` 已可用** — 导入 `Check` 图标
- **`accountStore.setAccounts` 已存在** — 用现有方法写入
- **`isPlatformKeyDisabled` 来自 appStore** — 保留现有黑名单过滤逻辑
- **SCSS variables** 来自 `@/styles/variables.scss` — `$border`, `$text-primary`, `$brand-start` 等
- **`platforms` props** 已经在调用方过滤黑名单，但 `accountStore.accounts` 可能含黑名单平台账号，需在 `filteredAccounts` 内再做一次防御

## Before You Begin

如果 `getDefaultAvatar` / `proxyAvatar` 在 `@/utils/avatar` 找不到，read 该文件确认函数签名。如果 `accountStore.setAccounts` 方法名不匹配，read `@/stores/account.js` 确认。

## Self-Review

- 三栏布局：左 flex:1 / 中 flex:2.2 / 右 flex:1 ✓
- 多选渠道：`selectedPlatformNames: Set<string>` ✓
- 多选标签：`selectedTagIds: Set<number>` OR 语义 ✓
- 卡片复用 BatchTagDialog 风格（avatar + info + ✓）✓
- 标签区无"新建"按钮 ✓
- 标签区有"全不选"按钮（`clearAllTags`）✓
- 一键全选作用于可见且有效的账号 ✓
- 取消已选卡片 → `tempSelectedAccounts` 立即更新 ✓
- 确认后 emit `confirm` + close ✓
- props/emits 接口不变 ✓
- vite build 通过 ✓

## Report

- Status: DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- Files changed
- vite build 输出
- Self-review findings

---

## Self-Review（已完成）

**Spec coverage:**
- 三栏布局 ✓ Step 1
- 多选渠道 ✓ Step 2 (`selectedPlatformNames`)
- 多选标签 OR ✓ Step 2 (`selectedTagIds`, `some()`)
- 卡片样式复用 BatchTagDialog ✓ Step 1 + Step 3
- 标签禁创建 ✓ Step 1（删除"新建"按钮 UI 和 handleCreate）
- 标签"全不选" ✓ Step 2 (`clearAllTags`)
- 一键全选 ✓ Step 2 (`toggleSelectAll`)
- 已选账号高亮 ✓ Step 3 (.selected 样式)
- 取消同步 ✓ Step 2 (`toggleAccount`)

**No placeholder:** ✓ 每个 step 有完整代码

**Type consistency:**
- `selectedPlatformNames: Set<string>` 一致
- `selectedTagIds: Set<number>` 一致
- `tempSelectedAccounts: Array<number>` 一致
- `togglePlatform(name: string)` 一致
- `toggleTag(tagId: number)` 一致
- `toggleAccount(id: number)` 一致

**已知限制：**
- Task 1 没拆分子任务（因为涉及同一文件三部分 — 模板/script/style — 高度耦合，拆分会增加 review 复杂度）
- 不含 Playwright e2e（项目无 Playwright 配置）

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-19-account-select-dialog-redesign.md`。

执行选择：**Subagent-Driven**（用户已要求"采用 sub-agent 开始实现"）。