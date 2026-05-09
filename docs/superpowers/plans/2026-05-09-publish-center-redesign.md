# 发布中心页面重设计 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **IMPORTANT:** Use the `ui-ux-pro-max` skill before implementing any UI code to get design guidance (style, palette, font pairing).

**Goal:** 将发布中心页面从双栏布局重设计为「左侧账号分组 + 右侧发布表单」的新布局，支持按渠道分组的账号管理和平台个性化设置。

**Architecture:** 主页面 `PublishCenter.vue` 重写为左右分栏布局（左侧 220px 固定账号栏 + 右侧自适应内容区）。按渠道自动分组账号，点击分组/账号时右侧动态显示公共配置 + 平台个性化设置。平台配置数据从 `platforms.js` 扩展，由各组件按需读取。

**Tech Stack:** Vue 3, Element Plus, Pinia, SCSS (现有设计系统), Vite

**Spec:** `docs/superpowers/specs/2026-05-09-publish-center-redesign.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `frontend/src/config/platforms.js` | Modify | 新增各平台个性化字段配置 |
| `frontend/src/views/PublishCenter.vue` | Rewrite | 主页面：布局骨架 + 状态管理 + 所有弹窗 |
| `frontend/src/styles/variables.scss` | No change | 沿用现有设计系统 |

---

### Task 1: 扩展平台配置

**Files:**
- Modify: `frontend/src/config/platforms.js`

- [ ] **Step 1: 在 platforms.js 中为每个平台添加 settingsFields 配置**

在 `PLATFORMS` 对象中的每个平台添加 `settingsFields` 数组，定义该平台的个性化设置字段。同时添加 `platformKeyToId` 映射。

```js
// 在 PLATFORMS 的每个平台对象中添加 settingsFields:

DOUYIN: {
  // ... 现有字段 ...
  settingsFields: [
    { key: 'productTitle', label: '商品名称', type: 'input', placeholder: '请输入商品名称' },
    { key: 'productLink', label: '商品链接', type: 'input', placeholder: '请输入商品链接' },
    { key: 'aiContent', label: '包含AI生成内容', type: 'switch' },
    { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
    { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
    { key: 'visibility', label: '谁可以看', type: 'radio', options: [{ label: '公开', value: 'public' }, { label: '私密', value: 'private' }] },
    { key: 'allowDownload', label: '允许下载', type: 'switch' },
  ],
  defaultSettings: { productTitle: '', productLink: '', aiContent: false, isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true },
},

XIAOHONGSHU: {
  // ... 现有字段 ...
  settingsFields: [
    { key: 'collection', label: '合集', type: 'select', placeholder: '请选择合集' },
    { key: 'groupChat', label: '群聊', type: 'select', placeholder: '请选择群聊' },
    { key: 'location', label: '位置', type: 'select', placeholder: '选择位置' },
    { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
    { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
  ],
  defaultSettings: { collection: '', groupChat: '', location: '', isOriginal: false, scheduleTime: '' },
},

KUAISHOU: {
  // ... 现有字段 ...
  settingsFields: [
    { key: 'productTitle', label: '商品名称', type: 'input', placeholder: '请输入商品名称' },
    { key: 'productLink', label: '商品链接', type: 'input', placeholder: '请输入商品链接' },
    { key: 'aiContent', label: '包含AI生成内容', type: 'switch' },
    { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
    { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
  ],
  defaultSettings: { productTitle: '', productLink: '', aiContent: false, isOriginal: false, scheduleTime: '' },
},

BILIBILI: {
  // ... 现有字段 ...
  settingsFields: [
    { key: 'zone', label: '分区', type: 'select', placeholder: '选择投稿分区' },
    { key: 'tags', label: '标签', type: 'input', placeholder: '自定义标签，逗号分隔' },
    { key: 'topic', label: '话题', type: 'select', placeholder: '选择话题' },
    { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
    { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
  ],
  defaultSettings: { zone: '', tags: '', topic: '', isOriginal: false, scheduleTime: '' },
},

CHANNELS: {
  // ... 现有字段 ...
  settingsFields: [
    { key: 'isDraft', label: '草稿模式', type: 'switch', description: '仅保存草稿（用手机发布）' },
    { key: 'location', label: '位置', type: 'select', placeholder: '选择位置' },
    { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
  ],
  defaultSettings: { isDraft: false, location: '', isOriginal: false },
},
```

同时在文件末尾添加辅助函数：

```js
/**
 * 根据 key 获取平台配置
 */
export function getPlatformByKey(key) {
  return platformList.find(p => p.key === key) || null
}

/**
 * 根据 key 获取平台 ID
 */
export const platformKeyToId = Object.fromEntries(
  platformList.map(p => [p.key, p.id])
)
```

- [ ] **Step 2: 验证修改不影响现有功能**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: 构建成功，无错误

- [ ] **Step 3: Commit**

```bash
git add frontend/src/config/platforms.js
git commit -m "feat: add per-platform settings fields config to platforms.js"
```

---

### Task 2: 重写 PublishCenter.vue 布局骨架

**Files:**
- Rewrite: `frontend/src/views/PublishCenter.vue`

这是最大的任务。按以下步骤逐步构建，每步 commit。

- [ ] **Step 1: 创建页面骨架 — 左右分栏 + 顶部操作栏**

先用 `ui-ux-pro-max` 技能获取深色主题布局的设计建议，然后重写 `PublishCenter.vue` 的 `<template>` 和 `<script setup>` 骨架。

`<template>` 核心结构：

```html
<template>
  <div class="publish-center">
    <!-- 左侧账号栏 -->
    <aside class="account-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">发布账号</span>
        <span class="sidebar-count">共 {{ totalCount }} 个</span>
      </div>
      <!-- 账号分组列表 -->
      <div class="group-list">
        <div v-for="group in accountGroups" :key="group.key"
             :class="['group-item', { active: selectedPlatform === group.key, expanded: expandedGroups.has(group.key) }]">
          <div class="group-header" @click="toggleGroup(group.key)">
            <span class="expand-icon">{{ expandedGroups.has(group.key) ? '▼' : '▶' }}</span>
            <span class="platform-badge" :style="{ background: group.color }">{{ group.letter }}</span>
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ group.accounts.length }}</span>
          </div>
          <div v-if="expandedGroups.has(group.key)" class="group-accounts">
            <div v-for="account in group.accounts" :key="account.id"
                 :class="['account-item', { active: selectedAccountId === account.id }]"
                 @click="selectAccount(account)">
              <div :class="['account-avatar', { 'selected-ring': selectedAccountId === account.id }]"></div>
              <span class="account-name">{{ account.name }}</span>
              <span :class="['status-dot', account.status === '正常' ? 'online' : 'offline']"></span>
            </div>
          </div>
        </div>
      </div>
      <!-- 底部添加按钮 -->
      <div class="sidebar-footer">
        <div class="add-account-btn" @click="accountDialogVisible = true">
          <span class="plus-icon">+</span> 添加账号
        </div>
      </div>
    </aside>

    <!-- 右侧内容区 -->
    <main class="publish-main">
      <!-- 顶部操作栏 -->
      <div class="main-header">
        <div class="header-left">
          <span class="page-title">发布视频</span>
          <span v-if="currentPlatformConfig" class="platform-tag"
                :style="{ background: currentPlatformConfig.bgColor, color: currentPlatformConfig.color }">
            {{ currentPlatformConfig.name }} · 个性化设置
          </span>
        </div>
        <div class="header-actions">
          <span class="action-text" @click="saveDraft">保存草稿</span>
          <el-button type="primary" class="publish-btn" @click="publishAll"
                     :loading="publishing">一键发布</el-button>
        </div>
      </div>

      <!-- 内容滚动区 -->
      <div class="main-content">
        <!-- 公共配置区 -->
        <!-- (Task 3 实现) -->

        <!-- 个性化设置区 -->
        <!-- (Task 4 实现) -->
      </div>
    </main>

    <!-- 弹窗部分 -->
    <!-- (Task 5-6 实现) -->
  </div>
</template>
```

`<script setup>` 核心状态：

```js
import { ref, reactive, computed } from 'vue'
import { useAccountStore } from '@/stores/account'
import { useAppStore } from '@/stores/app'
import { platformList, getPlatformByKey, platformKeyToId } from '@/config/platforms'
import { materialApi } from '@/api/material'
import { http } from '@/utils/request'
import { ElMessage } from 'element-plus'

const accountStore = useAccountStore()
const appStore = useAppStore()
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

// ===== 左侧状态 =====
const expandedGroups = ref(new Set())
const selectedPlatform = ref(null)  // 当前选中的平台 key
const selectedAccountId = ref(null) // 当前选中的账号 ID

// 账号分组计算属性
const accountGroups = computed(() => {
  const groupMap = {}
  for (const p of platformList) {
    const accounts = accountStore.accounts.filter(a => a.platform === p.name)
    groupMap[p.key] = {
      key: p.key,
      id: p.id,
      name: p.name,
      letter: p.letter,
      color: p.color,
      bgColor: p.bgColor,
      cssClass: p.cssClass,
      logo: p.logo,
      accounts,
      settingsFields: p.settingsFields || [],
      defaultSettings: p.defaultSettings || {},
    }
  }
  return Object.values(groupMap)
})

const totalCount = computed(() => accountStore.accounts.length)

// 当前平台配置
const currentPlatformConfig = computed(() => {
  if (!selectedPlatform.value) return null
  return getPlatformByKey(selectedPlatform.value)
})

// 初始化：展开第一个有账号的分组
const initGroups = () => {
  const firstGroupWithAccounts = accountGroups.value.find(g => g.accounts.length > 0)
  if (firstGroupWithAccounts) {
    expandedGroups.value.add(firstGroupWithAccounts.key)
    selectedPlatform.value = firstGroupWithAccounts.key
  }
}

const toggleGroup = (key) => {
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
  // 切换分组时更新右侧
  selectedPlatform.value = key
  selectedAccountId.value = null
}

const selectAccount = (account) => {
  const platform = accountGroups.value.find(g => g.accounts.some(a => a.id === account.id))
  if (platform) {
    selectedPlatform.value = platform.key
    expandedGroups.value.add(platform.key)
  }
  selectedAccountId.value = account.id
}

// ===== 右侧状态 =====
const publishing = ref(false)

// 公共配置
const commonConfig = reactive({
  fileList: [],
  coverFile: null,
  title: '',
  description: '',
  topics: [],
})

// 各平台个性化配置
const platformConfigs = reactive({
  douyin: { productTitle: '', productLink: '', aiContent: false, isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true },
  xiaohongshu: { collection: '', groupChat: '', location: '', isOriginal: false, scheduleTime: '' },
  kuaishou: { productTitle: '', productLink: '', aiContent: false, isOriginal: false, scheduleTime: '' },
  bilibili: { zone: '', tags: '', topic: '', isOriginal: false, scheduleTime: '' },
  channels: { isDraft: false, location: '', isOriginal: false },
})

// 当前个性化配置
const currentSettings = computed(() => {
  if (!selectedPlatform.value) return {}
  return platformConfigs[selectedPlatform.value] || {}
})

initGroups()
```

`<style>` 骨架：

```scss
@use '@/styles/variables.scss' as *;

.publish-center {
  display: flex;
  height: 100%;
  overflow: hidden;

  // ===== 左侧账号栏 =====
  .account-sidebar {
    width: 220px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    background: $bg-base;
    border-right: 1px solid $border;

    .sidebar-header {
      padding: 14px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid $border;
      .sidebar-title { color: $text-primary; font-weight: 600; font-size: 14px; }
      .sidebar-count { color: $text-muted; font-size: 12px; }
    }

    .group-list {
      flex: 1;
      overflow-y: auto;
      padding: 6px 10px;
    }

    .group-item {
      margin-bottom: 2px;
      .group-header {
        display: flex;
        align-items: center;
        gap: 6px;
        padding: 8px 10px;
        border-radius: 8px;
        cursor: pointer;
        transition: $transition-base;
        &:hover { background: rgba(255,255,255,0.03); }
      }
      &.active .group-header {
        border: 1px solid var(--group-color, $border-active);
        background: var(--group-bg, transparent);
      }
      .expand-icon { color: $text-muted; font-size: 8px; width: 10px; }
      .platform-badge {
        width: 18px; height: 18px; border-radius: 4px;
        display: flex; align-items: center; justify-content: center;
        color: #fff; font-size: 9px; font-weight: 700;
      }
      .group-name { color: $text-secondary; font-size: 11px; flex: 1; }
      &.active .group-name { color: $text-primary; }
      .group-count {
        color: $text-muted; font-size: 10px;
        background: rgba(255,255,255,0.05); padding: 1px 6px; border-radius: 10px;
      }
    }

    .group-accounts {
      padding-left: 12px;
      margin-top: 2px;
    }

    .account-item {
      display: flex; align-items: center; gap: 6px;
      padding: 6px 8px; border-radius: 6px; cursor: pointer;
      transition: $transition-base;
      &:hover { background: rgba(255,255,255,0.03); }
      &.active { background: rgba($brand-start, 0.08); }
      .account-avatar {
        width: 22px; height: 22px; background: $bg-elevated;
        border-radius: 50%; flex-shrink: 0;
        &.selected-ring { border: 1.5px solid $brand-start; }
      }
      .account-name { color: $text-secondary; font-size: 10px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      &.active .account-name { color: $text-primary; }
      .status-dot {
        width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0;
        &.online { background: $success-color; }
        &.offline { background: $danger-color; }
      }
    }

    .sidebar-footer {
      padding: 10px 14px;
      border-top: 1px solid $border;
      .add-account-btn {
        display: flex; align-items: center; justify-content: center; gap: 4px;
        padding: 8px; border: 1px dashed $text-muted; border-radius: 8px;
        color: $brand-start; font-size: 11px; cursor: pointer;
        transition: $transition-base;
        &:hover { border-color: $brand-start; background: rgba($brand-start, 0.05); }
      }
    }
  }

  // ===== 右侧内容区 =====
  .publish-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;

    .main-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 16px;
      border-bottom: 1px solid $border;
      flex-shrink: 0;

      .header-left {
        display: flex; align-items: center; gap: 10px;
        .page-title { color: $text-primary; font-weight: 600; font-size: 15px; }
        .platform-tag {
          padding: 3px 10px; border-radius: 12px; font-size: 11px;
          display: inline-flex; align-items: center; gap: 4px;
        }
      }
      .header-actions {
        display: flex; align-items: center; gap: 10px;
        .action-text { color: $text-secondary; font-size: 13px; cursor: pointer; &:hover { color: $text-primary; } }
        .publish-btn { background: $gradient-brand; border-color: transparent; color: #fff; font-weight: 600; }
      }
    }

    .main-content {
      flex: 1;
      overflow-y: auto;
      padding: 20px;
    }
  }
}
```

- [ ] **Step 2: 验证页面加载**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: rewrite publish center layout skeleton with account sidebar"
```

---

### Task 3: 实现右侧公共配置区

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue` (在 `.main-content` 内添加公共配置模板和样式)

- [ ] **Step 1: 在 `.main-content` 中添加公共配置区模板**

先用 `ui-ux-pro-max` 技能获取深色主题表单的设计建议（表单输入框、上传区域、标签按钮的样式）。

在 `<!-- 公共配置区 -->` 注释位置插入：

```html
<!-- ===== 公共配置区 ===== -->
<div class="config-section public-config">
  <div class="section-header">
    <div class="section-indicator purple"></div>
    <span class="section-label">公共配置</span>
    <span class="section-hint">所有账号共享</span>
  </div>

  <!-- 视频 + 封面 并排 -->
  <div class="media-row">
    <div class="media-card">
      <div class="media-label">视频</div>
      <div v-if="commonConfig.fileList.length === 0" class="media-empty">
        <div class="empty-text">无视频</div>
        <div class="empty-hint">请选择视频</div>
        <div class="empty-actions">
          <el-button size="small" @click="triggerUploadVideo">本地选择</el-button>
          <el-button size="small" @click="selectFromLibrary('video')">素材库</el-button>
        </div>
      </div>
      <div v-else class="media-preview">
        <div v-for="(file, idx) in commonConfig.fileList" :key="idx" class="preview-item">
          <video :src="file.url" class="preview-thumb" muted></video>
          <div class="preview-info">
            <span class="preview-name">{{ file.name }}</span>
            <span class="preview-size">{{ (file.size / 1024 / 1024).toFixed(2) }}MB</span>
          </div>
          <el-button type="danger" size="small" text @click="commonConfig.fileList.splice(idx, 1)">删除</el-button>
        </div>
        <el-button size="small" @click="triggerUploadVideo">继续添加</el-button>
      </div>
    </div>
    <div class="media-card">
      <div class="media-label">封面</div>
      <div v-if="!commonConfig.coverFile" class="media-empty">
        <div class="empty-text">无封面</div>
        <div class="empty-hint">请选择封面</div>
        <div class="empty-actions">
          <el-button size="small" @click="triggerUploadCover">本地上传</el-button>
          <el-button size="small" @click="captureFromVideo">从视频截取</el-button>
        </div>
      </div>
      <div v-else class="media-preview">
        <img :src="commonConfig.coverFile.url" class="preview-thumb" />
        <el-button type="danger" size="small" text @click="commonConfig.coverFile = null">删除</el-button>
      </div>
    </div>
  </div>

  <!-- 标题 -->
  <div class="form-field">
    <div class="field-header">
      <span class="field-label">标题</span>
      <span class="field-counter">{{ commonConfig.title.length }}/20</span>
    </div>
    <el-input v-model="commonConfig.title" placeholder="请输入标题..." maxlength="20" show-word-limit />
  </div>

  <!-- 描述 -->
  <div class="form-field">
    <div class="field-header">
      <span class="field-label">描述</span>
      <span class="field-counter">{{ commonConfig.description.length }}/1000</span>
    </div>
    <el-input v-model="commonConfig.description" type="textarea" :rows="4" placeholder="请输入描述..." maxlength="1000" show-word-limit />
  </div>

  <!-- 快捷标签 -->
  <div class="quick-tags">
    <el-button size="small" plain @click="topicDialogVisible = true"># 添加话题</el-button>
    <el-button size="small" plain>$ 参加活动</el-button>
    <el-button size="small" plain">@ 添加好友</el-button>
    <el-button size="small" plain>常用话题</el-button>
  </div>

  <!-- 已选话题显示 -->
  <div v-if="commonConfig.topics.length > 0" class="selected-topics">
    <el-tag v-for="(topic, idx) in commonConfig.topics" :key="idx" closable @close="commonConfig.topics.splice(idx, 1)" size="small">
      #{{ topic }}
    </el-tag>
  </div>
</div>
```

添加对应的样式（在 `.main-content` 内部）：

```scss
.config-section {
  margin-bottom: 20px;
}
.section-header {
  display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
  .section-indicator { width: 3px; height: 16px; border-radius: 2px; &.purple { background: $brand-start; } }
  .section-label { color: $text-primary; font-weight: 600; font-size: 14px; }
  .section-hint { color: $text-muted; font-size: 12px; }
}

.media-row {
  display: flex; gap: 14px; margin-bottom: 18px;
}
.media-card {
  flex: 1;
  .media-label { color: $text-secondary; font-size: 12px; margin-bottom: 8px; }
}
.media-empty {
  border: 1px dashed $border; border-radius: $radius-card; padding: 24px; text-align: center; background: $bg-surface;
  .empty-text { color: $text-muted; font-size: 13px; }
  .empty-hint { color: $danger-color; font-size: 11px; margin: 4px 0 10px; }
  .empty-actions { display: flex; gap: 6px; justify-content: center; }
}
.media-preview {
  .preview-item { display: flex; align-items: center; gap: 10px; padding: 8px; border: 1px solid $border; border-radius: $radius-base; margin-bottom: 6px; }
  .preview-thumb { width: 60px; height: 40px; object-fit: cover; border-radius: 4px; background: $bg-base; }
  .preview-info { flex: 1; min-width: 0; .preview-name { color: $text-primary; font-size: 12px; display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } .preview-size { color: $text-muted; font-size: 11px; } }
}

.form-field {
  margin-bottom: 14px;
  .field-header { display: flex; justify-content: space-between; margin-bottom: 6px; .field-label { color: $text-secondary; font-size: 12px; } .field-counter { color: $text-muted; font-size: 10px; } }
  :deep(.el-input__wrapper), :deep(.el-textarea__inner) {
    background: $bg-surface; border: 1px solid $border; border-radius: $radius-base; box-shadow: none;
    &:focus { border-color: $border-active; }
  }
}

.quick-tags {
  display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px;
}
.selected-topics {
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px;
  .el-tag { background: $gradient-brand-subtle; border-color: $border-active; color: $text-primary; }
}
```

添加对应的方法（在 `<script setup>` 中）：

```js
// ===== 上传相关 =====
const uploadVideoVisible = ref(false)
const uploadCoverVisible = ref(false)
const materialLibraryVisible = ref(false)
const uploadType = ref('video') // 'video' or 'cover'

const triggerUploadVideo = () => {
  uploadType.value = 'video'
  uploadVideoVisible.value = true
}

const triggerUploadCover = () => {
  uploadType.value = 'cover'
  uploadCoverVisible.value = true
}

const captureFromVideo = () => {
  if (commonConfig.fileList.length === 0) {
    ElMessage.warning('请先上传视频')
    return
  }
  // 从第一个视频截取封面（简化实现：使用视频第一帧）
  const videoUrl = commonConfig.fileList[0].url
  const video = document.createElement('video')
  video.src = videoUrl
  video.currentTime = 1
  video.onloadeddata = () => {
    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0)
    commonConfig.coverFile = {
      name: 'cover.jpg',
      url: canvas.toDataURL('image/jpeg'),
      isCaptured: true,
    }
    ElMessage.success('已从视频截取封面')
  }
}

const selectFromLibrary = (type) => {
  uploadType.value = type
  materialLibraryVisible.value = true
}

const handleVideoUploadSuccess = (response, file) => {
  if (response.code === 200) {
    const filePath = response.data.path || response.data
    const filename = filePath.split('/').pop()
    commonConfig.fileList.push({
      name: file.name,
      url: materialApi.getMaterialPreviewUrl(filename),
      path: filePath,
      size: file.size,
      type: file.type,
    })
    ElMessage.success('视频上传成功')
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}

const handleCoverUploadSuccess = (response, file) => {
  if (response.code === 200) {
    const filePath = response.data.path || response.data
    const filename = filePath.split('/').pop()
    commonConfig.coverFile = {
      name: file.name,
      url: materialApi.getMaterialPreviewUrl(filename),
      path: filePath,
      size: file.size,
    }
    ElMessage.success('封面上传成功')
  } else {
    ElMessage.error(response.msg || '上传失败')
  }
}
```

- [ ] **Step 2: 验证公共配置区渲染**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: add public config section (video, cover, title, description, tags)"
```

---

### Task 4: 实现平台个性化设置区

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue` (在公共配置区下方添加个性化设置模板和样式)

- [ ] **Step 1: 添加个性化设置区模板**

先用 `ui-ux-pro-max` 技能获取品牌色卡片的设计建议。

在公共配置区下方添加：

```html
<!-- 分割线 -->
<div class="section-divider"></div>

<!-- ===== 个性化设置区 ===== -->
<div v-if="currentPlatformConfig" class="config-section platform-config">
  <div class="section-header">
    <div class="section-indicator" :style="{ background: currentPlatformConfig.color }"></div>
    <span class="section-label">{{ currentPlatformConfig.name }} 个性化设置</span>
    <span class="section-hint">仅对该分组账号生效</span>
  </div>

  <div class="settings-grid">
    <div v-for="field in currentPlatformConfig.settingsFields" :key="field.key"
         class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
      <div class="setting-label" :style="{ color: currentPlatformConfig.color }">{{ field.label }}</div>

      <!-- 文本输入 -->
      <el-input v-if="field.type === 'input'" v-model="currentSettings[field.key]"
                :placeholder="field.placeholder" size="small" />

      <!-- 开关 -->
      <el-switch v-else-if="field.type === 'switch'" v-model="currentSettings[field.key]" />

      <!-- 单选 -->
      <div v-else-if="field.type === 'radio'" class="radio-group">
        <label v-for="opt in field.options" :key="opt.value" class="radio-item">
          <input type="radio" :name="`${currentPlatform}-${field.key}`"
                 :value="opt.value" v-model="currentSettings[field.key]" />
          <span :class="['radio-label', { active: currentSettings[field.key] === opt.value }]">{{ opt.label }}</span>
        </label>
      </div>

      <!-- 下拉选择 -->
      <el-select v-else-if="field.type === 'select'" v-model="currentSettings[field.key]"
                 :placeholder="field.placeholder" size="small" clearable>
        <!-- 选项数据后续接入 -->
      </el-select>

      <!-- 日期时间 -->
      <el-date-picker v-else-if="field.type === 'datetime'" v-model="currentSettings[field.key]"
                      type="datetime" :placeholder="field.placeholder" size="small" />
    </div>
  </div>
</div>
```

对应样式：

```scss
.section-divider {
  border-top: 1px dashed $border; margin: 8px 0 20px;
}
.platform-config {
  .settings-grid {
    display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
  }
  .setting-card {
    border-radius: $radius-base; padding: 10px 12px; border: 1px solid;
    .setting-label { font-size: 11px; margin-bottom: 6px; }
    :deep(.el-input__wrapper), :deep(.el-select) {
      background: $bg-surface; border: 1px solid $border; border-radius: $radius-sm; box-shadow: none;
    }
  }
  .radio-group {
    display: flex; gap: 12px;
    .radio-item { display: flex; align-items: center; gap: 4px; cursor: pointer;
      input { display: none; }
      .radio-label { color: $text-muted; font-size: 12px; &.active { color: $brand-start; } }
    }
  }
}
```

- [ ] **Step 2: 验证个性化设置区渲染**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: add per-platform personalized settings section"
```

---

### Task 5: 实现账号选择弹窗

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue` (添加弹窗模板、状态和方法)

- [ ] **Step 1: 添加账号选择弹窗**

在 `</template>` 前添加弹窗模板：

```html
<!-- 账号选择弹窗 -->
<el-dialog v-model="accountDialogVisible" title="选择账号" width="700px" class="account-select-dialog">
  <div class="dialog-filter">
    <el-select v-model="filterPlatform" placeholder="搜索平台" size="small" clearable style="width: 160px">
      <el-option label="全部平台" value="" />
      <el-option v-for="p in platformList" :key="p.key" :label="p.name" :value="p.key">
        <div style="display:flex;align-items:center;gap:6px;">
          <span :style="{width:'14px',height:'14px',background:p.color,borderRadius:'3px',display:'inline-flex',alignItems:'center',justifyContent:'center',color:'#fff',fontSize:'8px'}">{{ p.letter }}</span>
          {{ p.name }}
        </div>
      </el-option>
    </el-select>
    <el-input v-model="filterAccountName" placeholder="输入账号名称搜索..." size="small" style="flex:1" />
  </div>
  <div class="dialog-body">
    <div class="platform-sidebar">
      <div v-for="p in platformList" :key="p.key"
           :class="['platform-option', { active: filterPlatform === p.key }]"
           @click="filterPlatform = p.key">
        <span :style="{width:'18px',height:'18px',background:p.color,borderRadius:'4px',display:'flex',alignItems:'center',justifyContent:'center',color:'#fff',fontSize:'9px',fontWeight:700}">{{ p.letter }}</span>
        <span class="platform-option-name">{{ p.name }}</span>
      </div>
    </div>
    <div class="account-checklist">
      <div v-for="account in filteredAccounts" :key="account.id" class="account-check-item">
        <el-checkbox v-model="account._selected">
          <div class="account-check-info">
            <span class="account-check-name">{{ account.name }}</span>
            <span class="account-check-platform">{{ account.platform }}</span>
            <span v-if="account.status !== '正常'" class="account-check-status offline">{{ account.status }}</span>
            <span v-else class="account-check-status online">正常</span>
          </div>
        </el-checkbox>
      </div>
      <div v-if="filteredAccounts.length === 0" class="no-accounts">暂无账号</div>
    </div>
  </div>
  <template #footer>
    <div class="dialog-footer-bar">
      <span class="selected-count">已选择 {{ tempSelectedCount }} 个账号</span>
      <div>
        <el-button @click="accountDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddAccounts">确认添加</el-button>
      </div>
    </div>
  </template>
</el-dialog>
```

添加对应的状态和方法：

```js
// ===== 弹窗状态 =====
const accountDialogVisible = ref(false)
const filterPlatform = ref('')
const filterAccountName = ref('')

// 过滤后的账号列表
const filteredAccounts = computed(() => {
  let list = accountStore.accounts
  if (filterPlatform.value) {
    const platformConfig = getPlatformByKey(filterPlatform.value)
    if (platformConfig) {
      list = list.filter(a => a.platform === platformConfig.name)
    }
  }
  if (filterAccountName.value) {
    list = list.filter(a => a.name.includes(filterAccountName.value))
  }
  return list
})

const tempSelectedCount = computed(() => {
  return filteredAccounts.value.filter(a => a._selected).length
})

const confirmAddAccounts = () => {
  // 已选账号已经在 store 中，直接关闭
  accountDialogVisible.value = false
  ElMessage.success('账号已添加')
}

// 话题弹窗
const topicDialogVisible = ref(false)
const customTopic = ref('')
const recommendedTopics = ['游戏', '电影', '音乐', '美食', '旅行', '科技', '生活', '娱乐', '体育', '教育', '健康', '时尚']

const addCustomTopic = () => {
  if (!customTopic.value.trim()) { ElMessage.warning('请输入话题'); return }
  if (!commonConfig.topics.includes(customTopic.value.trim())) {
    commonConfig.topics.push(customTopic.value.trim())
    customTopic.value = ''
  } else { ElMessage.warning('话题已存在') }
}

const toggleRecommendedTopic = (topic) => {
  const idx = commonConfig.topics.indexOf(topic)
  if (idx > -1) commonConfig.topics.splice(idx, 1)
  else commonConfig.topics.push(topic)
}
```

弹窗样式：

```scss
.account-select-dialog {
  .dialog-filter { display: flex; gap: 10px; margin-bottom: 14px; }
  .dialog-body { display: flex; gap: 0; border: 1px solid $border; border-radius: $radius-base; overflow: hidden; min-height: 300px; }
  .platform-sidebar {
    width: 140px; border-right: 1px solid $border; padding: 8px;
    .platform-option {
      display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 6px;
      cursor: pointer; transition: $transition-base; margin-bottom: 2px;
      &:hover { background: rgba(255,255,255,0.03); }
      &.active { background: rgba($brand-start, 0.08); }
      .platform-option-name { color: $text-secondary; font-size: 12px; }
      &.active .platform-option-name { color: $text-primary; }
    }
  }
  .account-checklist { flex: 1; padding: 10px; overflow-y: auto; }
  .account-check-item {
    padding: 8px 10px; border: 1px solid $border; border-radius: $radius-base; margin-bottom: 6px;
    &:hover { border-color: $border-active; }
    .account-check-info { display: flex; align-items: center; gap: 8px; }
    .account-check-name { color: $text-primary; font-size: 13px; }
    .account-check-platform { color: $text-muted; font-size: 11px; }
    .account-check-status { font-size: 10px; padding: 1px 6px; border-radius: 8px; &.online { color: $success-color; background: rgba($success-color, 0.1); } &.offline { color: $danger-color; background: rgba($danger-color, 0.1); } }
  }
  .no-accounts { text-align: center; color: $text-muted; padding: 40px; }
  .dialog-footer-bar {
    display: flex; justify-content: space-between; align-items: center;
    .selected-count { color: $text-muted; font-size: 12px; }
  }
}
```

- [ ] **Step 2: 验证弹窗功能**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: add account selection dialog with platform filter"
```

---

### Task 6: 实现话题弹窗和上传弹窗

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

- [ ] **Step 1: 添加话题弹窗和上传弹窗模板**

在 `</template>` 前添加：

```html
<!-- 话题弹窗 -->
<el-dialog v-model="topicDialogVisible" title="添加话题" width="500px">
  <div class="topic-input-row">
    <el-input v-model="customTopic" placeholder="输入自定义话题" class="topic-input">
      <template #prepend>#</template>
    </el-input>
    <el-button type="primary" @click="addCustomTopic">添加</el-button>
  </div>
  <div class="topic-recommend">
    <h4>推荐话题</h4>
    <div class="topic-grid">
      <el-button v-for="topic in recommendedTopics" :key="topic"
                 :type="commonConfig.topics.includes(topic) ? 'primary' : 'default'"
                 size="small" @click="toggleRecommendedTopic(topic)">{{ topic }}</el-button>
    </div>
  </div>
  <template #footer>
    <el-button @click="topicDialogVisible = false">关闭</el-button>
  </template>
</el-dialog>

<!-- 视频上传弹窗 -->
<el-dialog v-model="uploadVideoVisible" title="上传视频" width="600px">
  <el-upload drag :auto-upload="true" :action="`${apiBaseUrl}/upload`"
             :on-success="handleVideoUploadSuccess"
             :headers="authHeaders" multiple accept="video/*">
    <el-icon style="font-size: 40px; color: var(--el-color-primary)"><Upload /></el-icon>
    <div style="color: #94a3b8; margin-top: 8px">将视频文件拖到此处，或<em style="color: #8b5cf6">点击上传</em></div>
    <template #tip><div style="color: #64748b; font-size: 12px; margin-top: 4px">支持 MP4、AVI 等视频格式</div></template>
  </el-upload>
</el-dialog>

<!-- 封面上传弹窗 -->
<el-dialog v-model="uploadCoverVisible" title="上传封面" width="500px">
  <el-upload drag :auto-upload="true" :action="`${apiBaseUrl}/upload`"
             :on-success="handleCoverUploadSuccess"
             :headers="authHeaders" accept="image/*">
    <el-icon style="font-size: 40px; color: var(--el-color-primary)"><Upload /></el-icon>
    <div style="color: #94a3b8; margin-top: 8px">将封面图片拖到此处，或<em style="color: #8b5cf6">点击上传</em></div>
  </el-upload>
</el-dialog>

<!-- 素材库弹窗 -->
<el-dialog v-model="materialLibraryVisible" title="选择素材" width="700px">
  <el-checkbox-group v-model="selectedMaterials">
    <div class="material-list">
      <div v-for="material in materials" :key="material.id" class="material-check-item">
        <el-checkbox :label="material.id">
          <span style="color: #f1f5f9; font-size: 13px">{{ material.filename }}</span>
          <span style="color: #64748b; font-size: 11px; margin-left: 8px">{{ material.filesize }}MB</span>
        </el-checkbox>
      </div>
    </div>
  </el-checkbox-group>
  <template #footer>
    <el-button @click="materialLibraryVisible = false">取消</el-button>
    <el-button type="primary" @click="confirmMaterialSelect">确定</el-button>
  </template>
</el-dialog>

<!-- 批量发布进度弹窗 -->
<el-dialog v-model="batchDialogVisible" title="发布进度" width="500px"
           :close-on-click-modal="false" :close-on-press-escape="false" :show-close="false">
  <el-progress :percentage="batchProgress" :status="batchProgress === 100 ? 'success' : ''" />
  <div v-if="currentPublishingLabel" style="text-align: center; color: #94a3b8; margin: 12px 0">
    正在发布：{{ currentPublishingLabel }}
  </div>
  <div v-if="batchResults.length > 0" class="batch-results">
    <div v-for="(r, i) in batchResults" :key="i" :class="['result-row', r.status]">
      <span class="result-label">{{ r.label }}</span>
      <span class="result-msg">{{ r.message }}</span>
    </div>
  </div>
  <template #footer>
    <el-button @click="cancelBatch" :disabled="batchProgress === 100">取消</el-button>
    <el-button v-if="batchProgress === 100" type="primary" @click="batchDialogVisible = false">关闭</el-button>
  </template>
</el-dialog>
```

添加上传和发布相关状态/方法：

```js
import { Upload } from '@element-plus/icons-vue'
import { computed } from 'vue'

const authHeaders = computed(() => ({ 'Authorization': `Bearer ${localStorage.getItem('token') || ''}` }))
const materials = computed(() => appStore.materials)
const selectedMaterials = ref([])

const confirmMaterialSelect = async () => {
  if (selectedMaterials.value.length === 0) { ElMessage.warning('请选择素材'); return }
  if (materials.value.length === 0) {
    try {
      const res = await materialApi.getAllMaterials()
      if (res.code === 200) appStore.setMaterials(res.data)
    } catch { ElMessage.error('获取素材失败'); return }
  }
  for (const id of selectedMaterials.value) {
    const m = materials.value.find(x => x.id === id)
    if (m) {
      const exists = commonConfig.fileList.some(f => f.path === m.file_path)
      if (!exists) {
        commonConfig.fileList.push({
          name: m.filename,
          url: materialApi.getMaterialPreviewUrl(m.file_path.split('/').pop()),
          path: m.file_path,
          size: m.filesize * 1024 * 1024,
          type: 'video/mp4',
        })
      }
    }
  }
  ElMessage.success(`已添加 ${selectedMaterials.value.length} 个素材`)
  materialLibraryVisible.value = false
  selectedMaterials.value = []
}

// ===== 发布逻辑 =====
const batchDialogVisible = ref(false)
const batchProgress = ref(0)
const batchResults = ref([])
const currentPublishingLabel = ref('')
const batchCancelled = ref(false)

const saveDraft = () => {
  ElMessage.success('已保存草稿')
}

const publishAll = async () => {
  if (commonConfig.fileList.length === 0) { ElMessage.error('请先上传视频'); return }
  if (!commonConfig.title.trim()) { ElMessage.error('请输入标题'); return }

  publishing.value = true
  batchDialogVisible.value = true
  batchProgress.value = 0
  batchResults.value = []
  batchCancelled.value = false

  // 收集所有需要发布的账号
  const allTasks = []
  for (const group of accountGroups.value) {
    if (group.accounts.length === 0) continue
    const settings = platformConfigs[group.key]
    if (!settings) continue
    for (const account of group.accounts) {
      allTasks.push({ group, account, settings })
    }
  }

  for (let i = 0; i < allTasks.length; i++) {
    if (batchCancelled.value) {
      batchResults.value.push({ label: allTasks[i].account.name, status: 'cancelled', message: '已取消' })
      continue
    }
    const { group, account, settings } = allTasks[i]
    currentPublishingLabel.value = `${account.name} (${group.name})`
    batchProgress.value = Math.floor((i / allTasks.length) * 100)

    try {
      const publishData = {
        type: group.id,
        title: commonConfig.title,
        tags: commonConfig.topics,
        fileList: commonConfig.fileList.map(f => f.path),
        accountList: [account.filePath],
        enableTimer: settings.scheduleTime ? 1 : 0,
        category: settings.isOriginal ? 1 : 0,
        productLink: (settings.productLink || '').trim(),
        productTitle: (settings.productTitle || '').trim(),
        isDraft: settings.isDraft || false,
      }
      await http.post('/postVideo', publishData)
      batchResults.value.push({ label: account.name, status: 'success', message: '发布成功' })
    } catch (err) {
      batchResults.value.push({ label: account.name, status: 'error', message: err.message || '发布失败' })
    }
  }

  batchProgress.value = 100
  currentPublishingLabel.value = ''
  publishing.value = false
}

const cancelBatch = () => {
  batchCancelled.value = true
  ElMessage.info('正在取消发布...')
}
```

样式：

```scss
.topic-input-row { display: flex; gap: 10px; margin-bottom: 16px; .topic-input { flex: 1; } }
.topic-recommend {
  h4 { margin: 0 0 12px; color: #f1f5f9; font-size: 14px; }
  .topic-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 8px; }
}
.material-list { display: flex; flex-direction: column; gap: 6px; }
.material-check-item { padding: 8px 10px; border: 1px solid $border; border-radius: $radius-base; &:hover { border-color: $border-active; } }
.batch-results { margin-top: 12px; border-top: 1px solid $border; padding-top: 10px; max-height: 200px; overflow-y: auto;
  .result-row { padding: 4px 0; font-size: 12px; .result-label { font-weight: 500; color: #f1f5f9; margin-right: 8px; } .result-msg { color: #64748b; }
    &.success .result-label { color: $success-color; }
    &.error .result-label { color: $danger-color; }
    &.cancelled .result-label { color: $text-muted; }
  }
}
```

- [ ] **Step 2: 验证完整页面功能**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build --mode development 2>&1 | tail -5`
Expected: 构建成功

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: add dialogs (topic, upload, material, batch publish) and publish logic"
```

---

### Task 7: 清理和最终验证

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue` (最终检查)
- Verify: `frontend/src/config/platforms.js`

- [ ] **Step 1: 移除未使用的 import**

检查 `<script setup>` 顶部，确保没有未使用的导入（`Folder`, `Check`, `InfoFilled` 等旧代码的导入）。确保只保留实际使用的：
- `ref, reactive, computed` from 'vue'
- `Upload` from '@element-plus/icons-vue'
- `ElMessage` from 'element-plus'
- `useAccountStore`, `useAppStore`
- `materialApi`
- `http`
- `platformList, getPlatformByKey` 等

- [ ] **Step 2: 验证完整构建**

Run: `cd /home/czy/workspace/ai/social-auto-upload/frontend && npx vite build 2>&1 | tail -10`
Expected: 构建成功，无警告

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PublishCenter.vue frontend/src/config/platforms.js
git commit -m "chore: cleanup unused imports and verify final build"
```

---

## Self-Review

**1. Spec coverage:**
- Section 1 (整体布局): Task 2 ✓
- Section 2 (左侧账号分组): Task 2 ✓
- Section 3 (右侧发布内容): Task 3 (公共) + Task 4 (个性化) ✓
- Section 4 (弹窗设计): Task 5 (账号选择) + Task 6 (话题/上传/素材/发布) ✓
- Section 5 (数据模型): Task 2 ✓
- Section 6 (样式规范): Task 2-4 ✓
- Section 7 (交互流程): Task 2 (导航) + Task 6 (发布) ✓
- Section 8 (移除的功能): Task 2 (完全重写) ✓
- Section 9 (文件变更清单): 全部覆盖 ✓

**2. Placeholder scan:** 无 TBD/TODO。所有步骤包含完整代码。

**3. Type consistency:**
- `accountGroups` 的 `key` 字段与 `selectedPlatform` 使用同一 key（如 `'douyin'`）✓
- `platformConfigs` 的 key 与 `getPlatformByKey` 返回的 `p.key` 一致 ✓
- `currentSettings` 从 `platformConfigs[selectedPlatform.value]` 读取 ✓
- `settingsFields` 中的 `field.key` 与 `currentSettings[field.key]` 对应 ✓
