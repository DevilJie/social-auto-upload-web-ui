# 图文发布渠道组件化重构

**日期:** 2026-06-01
**目标:** 将 `ImagePublish.vue`（2535 行）拆分为"父页面壳 + 渠道独立组件"架构，每个渠道封装自己的样式、布局、脚本交互、校验和发布逻辑。

---

## 1. 架构概览

### 1.1 组件树（重构后）

```
ImagePublish.vue  (父页面壳, ~400 行)
│
├── 左侧账号栏           (保留, 不动)
├── 公共配置区            (保留: 图片上传, 封面)
├── 批量同步区            (修改: 标题 + 描述 + 标签)
│
├── DouyinImagePublishPanel      (v-show, ref)
├── XiaohongshuImagePublishPanel (v-show, ref)
├── KuaishouImagePublishPanel    (v-show, ref)
│
├── 图片预览面板          (保留, 不动)
└── 对话框               (保留: 账号选择, 批量发布进度)
```

### 1.2 目录结构（重构后）

```
components/
├── douyin/
│   ├── ImagePublishPanel.vue     ← 新增：抖音图文主面板
│   ├── ActivitySelect.vue        ← 已有，不动
│   ├── HotspotSelect.vue         ← 已有，不动
│   ├── MusicSelect.vue           ← 已有，不动
│   ├── MusicDrawer.vue           ← 已有，不动
│   ├── TagSelect.vue             ← 已有，不动
│   └── MixSelect.vue             ← 已有，不动
├── xiaohongshu/
│   └── ImagePublishPanel.vue     ← 新增：小红书图文主面板
├── kuaishou/
│   └── ImagePublishPanel.vue     ← 新增：快手图文主面板
├── (其余已有组件不动)
```

### 1.3 数据归属

```
父页面拥有:                        渠道组件内部拥有:
├── images[]      图片列表          ├── platformConfig    渠道默认表单
├── coverImage    封面图片          ├── accountOverrides  账号级覆盖
├── publishAccountIds 发布账号      ├── tags[]            标签列表
├── selectedPlatform / accountId   ├── 校验规则
└── 发布进度/结果                  ├── 构建 publish payload
                                   └── 调用 imagePublishApi
```

父页面完全不关心渠道有哪些字段、怎么校验、怎么构建 payload。

---

## 2. 渠道组件统一接口

### 2.1 Props（父 → 子）

| Prop | 类型 | 必须 | 说明 |
|------|------|------|------|
| `accountId` | `Number \| null` | 是 | 当前选中账号 ID，`null`=编辑渠道默认 |
| `disabled` | `Boolean` | 否 | 发布进行中时禁用表单编辑 |

### 2.2 Emits（子 → 父）

| Event | Payload | 说明 |
|------|------|------|
| `config-changed` | 无 | 任何表单状态变更时 emit，父页面用于：dirty 标记、侧栏星标刷新、触发自动保存 |
| `publish-result` | `{ accountName, status, message }` | 单账号发布完成通知 |

### 2.3 Exposed 方法（父通过 ref 调用）

| 方法签名 | 说明 |
|------|------|
| `publish(accountId, accountName, { images, coverImage })` | 发布单个账号。内部：合并渠道/账号配置 + 公共数据 → 构建 payload → 调用 `imagePublishApi.publishImage()` → emit `publish-result` |
| `getConfigs()` → `{ platformConfig, accountOverrides }` | 获取渠道全部配置，草稿保存用 |
| `restoreConfigs(platformConfig, accountOverrides)` | 恢复草稿配置 |
| `syncTitle(title: string)` | 批量同步标题 |
| `syncDescription(desc: string)` | 批量同步描述 |
| `syncTags(tags: string[])` | 批量同步标签 |
| `validate(accountId)` → `{ valid: boolean, errors: string[] }` | 预发布校验（标题必填、声明必填、标签数量限制等） |
| `hasAccountOverride(accountId)` → `boolean` | 判断指定账号是否有自定义覆盖，侧栏星标用 |

---

## 3. ImagePublish.vue 改造（父页面）

### 3.1 删除的内容

| 删除项 | 当前行号范围 | 说明 |
|------|------|------|
| `commonConfig.topics` | 588 | 公共话题删除，下沉为渠道级 `tags` |
| `platformConfigs` reactive 对象 | 595-611 | 全部托管给渠道组件 |
| `accountOverrides` reactive 对象 | 615 | 全部托管给渠道组件 |
| `form` reactive 对象 | 618 | 删除，渠道组件各自维护 |
| `watch([selectedPlatform, selectedAccountId])` | 639-650 | 表单切换逻辑移入渠道组件 |
| `watch(form, ...)` | 653-679 | 表单同步逻辑移入渠道组件 |
| `getMergedSettings()` | 620-636 | 移入渠道组件内部 |
| `getAccountName()` | 682-685 | 改为内联 computed |
| `hasAccountOverride()` / `resetAccountOverride()` | 687-696 | 委托给渠道组件 |
| `hotspotTagInput` / `addHotspotTag()` / `removeHotspotTag()` | 699-728 | 移入 DouyinImagePublishPanel |
| `handleActivityChange()` / `handleMusicSelect()` / `handleHotspotChange()` / `handleMixChange()` / `handleTagSelect()` | 888-959 | 移入 DouyinImagePublishPanel |
| `declarationOptions` computed | 574-578 | 移入渠道组件 |
| `imagePlatformSettingsFields` computed | 581-583 | 删除，无用 |
| `topicDialogVisible` / `customTopic` / `recommendedTopics` / `addCustomTopic()` / `toggleRecommendedTopic()` | 话题相关 | 删除，`commonConfig.topics` 不存在了 |
| 话题对话框模板 | 话题 dialog | 删除 |
| 快速标签按钮模板 | 175-195 | 删除 |
| `onMusicCoverError()` | 961-963 | 移入 DouyinImagePublishPanel |
| Douyin 子组件 import 语句 | 522-526 | 移入 DouyinImagePublishPanel |
| `watch(platformConfigs, ...)` | 1319 | 删除，platformConfigs 不再存在于父页面 |
| `watch(accountOverrides, ...)` | 1320 | 删除，accountOverrides 不再存在于父页面 |
| 平台特有设置区域模板 | 163-304 | 替换为渠道组件 |
| 抖音特有配置模板 | 209-304 | 移入 DouyinImagePublishPanel |
| 小红书反检测警告 | 180-183 | 移入 XiaohongshuImagePublishPanel |

### 3.2 修改的内容

**批量同步区（模板 + 脚本）：**

当前（第 122-157 行）只有标题和描述，改造为：

```html
<div class="batch-sync-section">
  <div class="batch-sync-header" @click="batchSyncExpanded = !batchSyncExpanded">
    <span>批量设置标题、描述和标签</span>
    <el-icon><component :is="batchSyncExpanded ? ArrowDown : ArrowRight" /></el-icon>
  </div>
  <div v-show="batchSyncExpanded" class="batch-sync-body">
    <!-- 标题 -->
    <div class="form-field">
      <div class="field-head"><span>标题</span></div>
      <el-input v-model="batchTitle" placeholder="输入标题后点击同步..." maxlength="100" />
    </div>
    <!-- 描述 -->
    <div class="form-field">
      <div class="field-head"><span>描述</span></div>
      <el-input v-model="batchDescription" type="textarea" :rows="5" placeholder="输入描述后点击同步..." maxlength="2000" />
    </div>
    <!-- 标签 -->
    <div class="form-field">
      <div class="field-head"><span>标签</span></div>
      <el-input v-model="batchTagInput" placeholder="输入标签，回车添加" @keyup.enter="addBatchTag" clearable />
      <div v-if="batchTags.length" class="batch-tags-list">
        <el-tag v-for="(t, i) in batchTags" :key="i" closable @close="batchTags.splice(i, 1)" size="small">#{{ t }}</el-tag>
      </div>
    </div>
    <!-- 同步按钮 -->
    <button class="cover-action-btn primary" @click="syncBatchToAll">同步到所有平台</button>
  </div>
</div>
```

新增脚本状态：
```js
const batchTags = ref([])
const batchTagInput = ref('')

function addBatchTag() {
  const tag = batchTagInput.value.trim()
  if (!tag) return
  if (batchTags.value.includes(tag)) return
  batchTags.value.push(tag)
  batchTagInput.value = ''
}

function syncBatchToAll() {
  const platforms = ['douyin', 'xiaohongshu', 'kuaishou']
  for (const key of platforms) {
    const panel = panelRefs[key]
    if (!panel) continue
    if (batchTitle.value) panel.syncTitle(batchTitle.value)
    if (batchDescription.value) panel.syncDescription(batchDescription.value)
    if (batchTags.value.length) panel.syncTags([...batchTags.value])
  }
  ElMessage.success('已同步到所有平台')
}
```

**渠道面板区（模板）：**

当前复杂的 `v-if="currentPlatformConfig"` 块，替换为：

```html
<div class="config-section" v-show="selectedPlatform">
  <div class="section-bar">
    <div class="bar" :style="{ background: currentPlatformConfig?.color }"></div>
    <span class="section-label">
      {{ currentPlatformConfig?.name }}
      {{ selectedAccountId ? '· ' + getAccountDisplayName(selectedAccountId) : '· 默认设置' }}
    </span>
    <span class="hint">{{ selectedAccountId ? '仅对该账号生效' : '对该分组所有未自定义的账号生效' }}</span>
  </div>

  <DouyinImagePublishPanel
    ref="el => panelRefs.douyin = el"
    :account-id="selectedPlatform === 'douyin' ? selectedAccountId : null"
    :disabled="publishing"
    v-show="selectedPlatform === 'douyin'"
    @config-changed="onChannelConfigChanged"
    @publish-result="onPublishResult"
  />
  <XiaohongshuImagePublishPanel
    ref="el => panelRefs.xiaohongshu = el"
    :account-id="selectedPlatform === 'xiaohongshu' ? selectedAccountId : null"
    :disabled="publishing"
    v-show="selectedPlatform === 'xiaohongshu'"
    @config-changed="onChannelConfigChanged"
    @publish-result="onPublishResult"
  />
  <KuaishouImagePublishPanel
    ref="el => panelRefs.kuaishou = el"
    :account-id="selectedPlatform === 'kuaishou' ? selectedAccountId : null"
    :disabled="publishing"
    v-show="selectedPlatform === 'kuaishou'"
    @config-changed="onChannelConfigChanged"
    @publish-result="onPublishResult"
  />
</div>
```

**`hasAccountOverride()` 改为委托：**

```js
function hasAccountOverride(accountId) {
  // 遍历所有渠道面板，检查是否有覆盖
  for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
    const panel = panelRefs[key]
    if (panel && panel.hasAccountOverride(accountId)) return true
  }
  return false
}
```

**`saveDraft()` 改造：**

删除直接引用 `platformConfigs`、`accountOverrides`、`douyinSelections`，改为：

```js
async function saveDraft() {
  try {
    // 从各渠道组件收集配置
    const allPlatformConfigs = {}
    const allAccountOverrides = {}
    for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
      const panel = panelRefs[key]
      if (panel) {
        const { platformConfig, accountOverrides } = panel.getConfigs()
        allPlatformConfigs[key] = platformConfig
        Object.assign(allAccountOverrides, accountOverrides)
      }
    }

    const draftData = {
      commonConfig: {
        images: commonConfig.images.map(img => ({ id: img.id, name: img.name, url: img.url, stored_path: img.stored_path, size: img.size, type: img.type })),
        coverImage: commonConfig.coverImage || null,
      },
      platformConfigs: allPlatformConfigs,
      accountOverrides: allAccountOverrides,
      publishAccountIds: [...publishAccountIds],
      selectedPlatform: selectedPlatform.value,
      selectedAccountId: selectedAccountId.value,
      expandedGroups: [...expandedGroups.value],
    }

    if (currentDraftId.value) {
      await imagePublishApi.saveDraft({ id: currentDraftId.value, draft_data: draftData })
      ElMessage.success('草稿已更新')
    } else {
      const resp = await imagePublishApi.saveDraft({ draft_data: draftData })
      if (resp.code === 200) {
        currentDraftId.value = resp.data.id
        ElMessage.success('草稿已保存')
      }
    }
    hasChanges.value = false
  } catch (e) {
    console.error('保存草稿失败:', e)
    ElMessage.error('草稿保存失败')
  }
}
```

**`restoreDraft()` 改造：**

```js
// 恢复草稿时
if (dd.platformConfigs) {
  for (const [key, val] of Object.entries(dd.platformConfigs)) {
    const panel = panelRefs[key]
    if (panel && val) {
      panel.restoreConfigs(val, dd.accountOverrides || {})
    }
  }
}
```

**`publishAll()` 改造：**

完全重写，删除所有平台特有校验逻辑，改为委托：

```js
async function publishAll() {
  // 1. 公共校验
  if (commonConfig.images.length === 0) {
    ElMessage.error('请先上传至少一张图片')
    return
  }
  if (publishAccountIds.size === 0) {
    ElMessage.error('请先添加发布账号')
    return
  }

  // 2. 渠道校验（委托给各渠道组件）
  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    const panel = panelRefs[group.key]
    if (!panel) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      const { valid, errors } = panel.validate(account.id)
      if (!valid) {
        ElMessage.error(`${account.name}(${group.name}): ${errors.join('; ')}`)
        return
      }
    }
  }

  // 3. 启动发布
  publishing.value = true
  publishProgress.value = 0
  publishResults.value = []
  isCancelled.value = false
  currentPublishingAccount.value = ''
  batchPublishDialogVisible.value = true

  const commonData = {
    images: commonConfig.images,
    coverImage: commonConfig.coverImage,
  }

  const allTasks = []
  for (const group of imageAccountGroups.value) {
    if (group.accounts.length === 0) continue
    for (const account of group.accounts) {
      if (!publishAccountIds.has(account.id)) continue
      allTasks.push({ account, groupKey: group.key })
    }
  }

  if (allTasks.length === 0) {
    ElMessage.warning('没有可发布的账号')
    publishing.value = false
    batchPublishDialogVisible.value = false
    return
  }

  // 4. 逐个调用渠道组件发布
  for (let i = 0; i < allTasks.length; i++) {
    if (isCancelled.value) {
      publishResults.value.push({ label: allTasks[i].account.name, status: 'cancelled', message: '已取消' })
      continue
    }
    const { account, groupKey } = allTasks[i]
    currentPublishingAccount.value = account.name
    publishProgress.value = Math.floor((i / allTasks.length) * 100)

    const panel = panelRefs[groupKey]
    if (panel) {
      await panel.publish(account.id, account.name, commonData)
    }
  }

  publishProgress.value = 100
  publishing.value = false
}
```

**`onPublishResult` / `onChannelConfigChanged` 回调：**

```js
function onPublishResult({ accountName, status, message }) {
  publishResults.value.push({ label: accountName, status, message })
}

function onChannelConfigChanged() {
  hasChanges.value = true
}
```

### 3.3 新增的内容

| 新增项 | 说明 |
|------|------|
| `panelRefs` 对象 | `const panelRefs = reactive({ douyin: null, xiaohongshu: null, kuaishou: null })` |
| 3 个渠道组件 import | `import DouyinImagePublishPanel from '@/components/douyin/ImagePublishPanel.vue'` 等 |
| `batchTags` / `batchTagInput` / `addBatchTag()` | 批量标签交互 |
| `onChannelConfigChanged()` | config-changed 事件处理 |
| `onPublishResult()` | publish-result 事件处理 |
| `getAccountDisplayName()` | 内联工具函数，`accountStore.accounts.find(a => a.id === accountId)?.name` |

---

## 4. DouyinImagePublishPanel 新建

**路径:** `frontend/src/components/douyin/ImagePublishPanel.vue`

### 4.1 职责

- 维护抖音渠道的 `platformConfig`（渠道默认值）和 `accountOverrides`（账号级覆盖）
- 渲染抖音图文发布专属表单
- 监听 `accountId` prop 变更，切换表单数据
- 处理所有抖音特有交互（活动、音乐、热点、标签、合集）
- 校验发布规则（活动+标签 ≤ 5，标题必填，声明必填）
- 构建发布 payload 并调用 API

### 4.2 模板结构

```html
<template>
  <div class="douyin-image-publish-panel">
    <!-- 恢复默认按钮 -->
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <!-- ① 标题 -->
    <div class="setting-card">
      <div class="setting-label">标题</div>
      <el-input v-model="form.title" placeholder="请输入标题..." maxlength="100" show-word-limit />
    </div>

    <!-- ② 描述 -->
    <div class="setting-card">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="2000" show-word-limit />
    </div>

    <!-- ③ 标签（热点标签交互模式） -->
    <div class="setting-card">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认（官方活动 + 标签最多 5 个）</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag
          v-for="(tag, index) in form.tags"
          :key="index"
          closable
          @close="removeTag(index)"
          size="small"
          :disable-transitions="false"
        >#{{ tag }}</el-tag>
      </div>
    </div>

    <!-- ④ 官方活动 -->
    <div class="setting-card">
      <div class="setting-label">官方活动</div>
      <DouyinActivitySelect v-model="form.activityId" @change="handleActivityChange" />
    </div>

    <!-- ⑤ 选择音乐 -->
    <div class="setting-card">
      <div class="setting-label">选择音乐</div>
      <DouyinMusicSelect :account-id="accountId" v-model="form.selectedMusic" :data="form.selectedMusicData" @change="handleMusicSelect" />
    </div>

    <!-- ⑥ 关联热点 -->
    <div class="setting-card">
      <div class="setting-label">关联热点</div>
      <DouyinHotspotSelect v-model="form.hotspotId" :data="form.hotspotData" @change="handleHotspotChange" />
    </div>

    <!-- ⑦ 自主声明 -->
    <div class="setting-card">
      <div class="setting-label">自主声明</div>
      <el-select v-model="form.aiContent" placeholder="请选择自主声明" clearable>
        <el-option v-for="opt in declarationOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>

    <!-- ⑧ 添加标签（地点/小程序/游戏/标记） -->
    <div class="setting-card">
      <div class="setting-label">添加标签</div>
      <DouyinTagSelect :account-id="accountId" v-model="form.selectedTag" @change="handleTagSelect" />
    </div>

    <!-- ⑨ 添加合集（仅账号级） -->
    <div v-if="accountId" class="setting-card">
      <div class="setting-label">添加合集</div>
      <DouyinMixSelect :account-id="accountId" v-model="form.mixId" :data="form.mixData" @change="handleMixChange" />
    </div>
  </div>
</template>
```

### 4.3 脚本关键逻辑

```js
<script setup>
import { ref, reactive, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useAccountStore } from '@/stores/account'
import { imagePublishApi } from '@/api/imagePublish'
import DouyinActivitySelect from './ActivitySelect.vue'
import DouyinMusicSelect from './MusicSelect.vue'
import DouyinHotspotSelect from './HotspotSelect.vue'
import DouyinTagSelect from './TagSelect.vue'
import DouyinMixSelect from './MixSelect.vue'
import { PLATFORMS } from '@/config/platforms'

const props = defineProps({
  accountId: { type: [Number, Object], default: null },
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['config-changed', 'publish-result'])

const accountStore = useAccountStore()

// ===== 内部数据 =====
const channelDefaults = { ...PLATFORMS.DOUYIN.defaultSettings, tags: [] }
const platformConfig = reactive({ ...channelDefaults })
const accountOverrides = reactive({})
const form = reactive({ ...platformConfig })

// ===== 标签输入 =====
const tagInput = ref('')

function addTag() { ... }
function removeTag(index) { ... }

// ===== 监听 accountId 切换表单 =====
watch(() => props.accountId, (newId) => {
  if (!newId) {
    // 切换到渠道默认
    Object.assign(form, platformConfig)
  } else {
    const override = accountOverrides[newId]
    if (override && Object.keys(override).length > 0) {
      Object.assign(form, { ...platformConfig, ...override })
    } else {
      Object.assign(form, platformConfig)
    }
  }
}, { immediate: true })

// ===== 表单变更同步 =====
watch(form, (newVal) => {
  if (!props.accountId) {
    // 渠道级：直接写入 platformConfig
    Object.assign(platformConfig, newVal)
  } else {
    // 账号级：计算与渠道默认的差异
    const diff = {}
    for (const key of Object.keys(newVal)) {
      if (JSON.stringify(newVal[key]) !== JSON.stringify(platformConfig[key])) {
        diff[key] = newVal[key]
      }
    }
    if (Object.keys(diff).length > 0) {
      accountOverrides[props.accountId] = { ...diff }
    } else {
      delete accountOverrides[props.accountId]
    }
  }
  emit('config-changed')
}, { deep: true })

// ===== 交互处理 =====
function handleActivityChange(activity) { ... }
function handleMusicSelect(music) { ... }
function handleHotspotChange(hotspot) { ... }
function handleTagSelect(tag) { ... }
function handleMixChange(mix) { ... }

// ===== 暴露方法 =====
defineExpose({
  async publish(accountId, accountName, commonData) {
    // 1. 合并配置
    const override = accountOverrides[accountId] || {}
    const merged = { ...platformConfig, ...override }
    // 2. 构建 payload
    const account = accountStore.accounts.find(a => a.id === accountId)
    const imageIds = commonData.images.map(img => img.id)
    // 3. 调用 API
    try {
      await imagePublishApi.publishImage({
        image_ids: imageIds,
        account_configs: [{
          account_id: accountId,
          platform: account.platform,
          filePath: account.filePath,
          title: merged.title,
          description: merged.description || '',
          tags: merged.tags || [],
          aiContent: merged.aiContent || '',
          mix_id: merged.mixId || '',
          music_name: merged.selectedMusic || '',
          hotspot: merged.hotspotId || '',
          tag_type: /* ... tag type mapping */,
          tag_value: /* ... tag value */,
          mini_link: /* ... */,
          activities: merged.activityId || [],
          cover_path: commonData.coverImage?.stored_path || '',
          dry_run: false,
        }],
      })
      emit('publish-result', { accountName, status: 'success', message: '发布成功' })
    } catch (e) {
      emit('publish-result', { accountName, status: 'fail', message: e.message || '发布失败' })
    }
  },

  getConfigs() {
    return {
      platformConfig: JSON.parse(JSON.stringify(platformConfig)),
      accountOverrides: JSON.parse(JSON.stringify(accountOverrides)),
    }
  },

  restoreConfigs(config, overrides) {
    Object.assign(platformConfig, config)
    Object.keys(accountOverrides).forEach(k => delete accountOverrides[k])
    Object.assign(accountOverrides, overrides)
    // 刷新当前表单
    if (props.accountId) {
      const override = accountOverrides[props.accountId]
      Object.assign(form, override ? { ...platformConfig, ...override } : { ...platformConfig })
    } else {
      Object.assign(form, platformConfig)
    }
  },

  syncTitle(title) {
    if (!props.accountId) {
      platformConfig.title = title
      form.title = title
    }
    emit('config-changed')
  },

  syncDescription(desc) {
    if (!props.accountId) {
      platformConfig.description = desc
      form.description = desc
    }
    emit('config-changed')
  },

  syncTags(tags) {
    if (!props.accountId) {
      platformConfig.tags = [...tags]
      form.tags = [...tags]
    }
    emit('config-changed')
  },

  validate(accountId) {
    const errors = []
    const override = accountOverrides[accountId] || {}
    const merged = { ...platformConfig, ...override }
    if (!merged.title || !merged.title.trim()) errors.push('标题不能为空')
    if (!merged.aiContent) errors.push('请选择自主声明')
    const activityCount = merged.activityId?.length || 0
    const tagCount = merged.tags?.length || 0
    if (activityCount + tagCount > 5) errors.push('官方活动 + 标签最多 5 个')
    return { valid: errors.length === 0, errors }
  },

  hasAccountOverride(accountId) {
    const override = accountOverrides[accountId]
    if (!override) return false
    return Object.values(override).some(v => v !== undefined && v !== '' && v !== false && !(Array.isArray(v) && v.length === 0))
  },
})
</script>
```

### 4.4 标签交互细节

标签采用当前热点标签的交互模式（从 `ImagePublish.vue` 原 `addHotspotTag` / `removeHotspotTag` 迁移而来）：

```js
const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
  const activityCount = form.activityId?.length || 0
  const tagCount = form.tags?.length || 0
  if (activityCount + tagCount >= 5) {
    ElMessage.warning('官方活动 + 标签最多 5 个')
    return
  }
  if (!form.tags) form.tags = []
  if (form.tags.includes(tag)) {
    ElMessage.warning('标签已存在')
    return
  }
  form.tags.push(tag)
  tagInput.value = ''
}

function removeTag(index) {
  form.tags.splice(index, 1)
}
```

---

## 5. XiaohongshuImagePublishPanel 新建

**路径:** `frontend/src/components/xiaohongshu/ImagePublishPanel.vue`

### 5.1 模板结构

```html
<template>
  <div class="xiaohongshu-image-publish-panel">
    <!-- 小红书反检测警告 -->
    <div class="xhs-warning">
      <el-icon><WarningFilled /></el-icon>
      <span>由于小红书反检测机制比较恶心，如果出现被警告的情况！请立即停止使用小红书渠道！</span>
    </div>

    <!-- 恢复默认按钮 -->
    <div v-if="accountId && hasAccountOverride(accountId)" style="margin-bottom: 12px;">
      <el-button size="small" @click="resetOverride">恢复为渠道默认</el-button>
    </div>

    <!-- ① 标题 -->
    <div class="setting-card">
      <div class="setting-label">标题</div>
      <el-input v-model="form.title" placeholder="请输入标题..." maxlength="100" show-word-limit :disabled="disabled" />
    </div>

    <!-- ② 描述 -->
    <div class="setting-card">
      <div class="setting-label">描述</div>
      <el-input v-model="form.description" type="textarea" :rows="5" placeholder="请输入描述..." maxlength="2000" show-word-limit :disabled="disabled" />
    </div>

    <!-- ③ 标签 -->
    <div class="setting-card">
      <div class="setting-label">标签</div>
      <div class="setting-hint">输入标签内容，按回车确认（标签数量限制待定）</div>
      <el-input v-model="tagInput" placeholder="输入标签内容，按回车添加" @keyup.enter="addTag" clearable :disabled="disabled" />
      <div v-if="form.tags && form.tags.length > 0" class="tags-list">
        <el-tag v-for="(t, i) in form.tags" :key="i" closable @close="removeTag(i)" size="small">#{{ t }}</el-tag>
      </div>
    </div>
  </div>
</template>
```

### 5.2 脚本

与 DouyinImagePublishPanel 相同的框架结构，接口方法实现完整，但 `validate()` 的校验规则按小红书规则设置（当前仅校验标题必填和声明必填）。

---

## 6. KuaishouImagePublishPanel 新建

**路径:** `frontend/src/components/kuaishou/ImagePublishPanel.vue`

与 XiaohongshuImagePublishPanel 同理，框架相同，校验规则按快手规则设置。

---

## 7. 草稿兼容性

旧草稿与新草稿格式存在差异，恢复时必须处理以下兼容迁移：

### 7.1 `commonConfig.topics` → 各渠道 `tags`

```js
if (dd.commonConfig?.topics && Array.isArray(dd.commonConfig.topics)) {
  // 旧草稿：将 commonConfig.topics 迁移到各渠道的 tags
  for (const key of ['douyin', 'xiaohongshu', 'kuaishou']) {
    if (dd.platformConfigs?.[key]) {
      dd.platformConfigs[key].tags = [...dd.commonConfig.topics]
    }
  }
  delete dd.commonConfig.topics
}
```

### 7.2 `douyinSelections` → `platformConfigs.douyin` + `accountOverrides`

旧草稿将抖音选中的音乐/热点/合集/标签等数据作为独立的 `douyinSelections` 存储。新草稿中，这些数据是 `platformConfigs.douyin` 和 `accountOverrides` 的一部分。兼容逻辑：

```js
if (dd.douyinSelections) {
  const sel = dd.douyinSelections
  const douyinCfg = dd.platformConfigs?.douyin || {}
  // 迁移选中数据到平台配置
  if (sel.selectedMusic !== undefined) douyinCfg.selectedMusic = sel.selectedMusic
  if (sel.selectedMusicData !== undefined) douyinCfg.selectedMusicData = sel.selectedMusicData
  if (sel.hotspotId !== undefined) douyinCfg.hotspotId = sel.hotspotId
  if (sel.hotspotData !== undefined) douyinCfg.hotspotData = sel.hotspotData
  if (sel.mixId !== undefined) douyinCfg.mixId = sel.mixId
  if (sel.mixData !== undefined) douyinCfg.mixData = sel.mixData
  if (sel.selectedTag !== undefined) douyinCfg.selectedTag = sel.selectedTag
  if (sel.tagType !== undefined) douyinCfg.tagType = sel.tagType
  if (sel.tagValue !== undefined) douyinCfg.tagValue = sel.tagValue
  // coverImage 已在 commonConfig 中，不再重复迁移
  if (!dd.platformConfigs) dd.platformConfigs = {}
  dd.platformConfigs.douyin = douyinCfg
  delete dd.douyinSelections
}
```

### 7.3 `accountOverrides` 中的 `coverImage` 清理

旧草稿可能把封面图片误存到 `accountOverrides` 中，恢复时清理：

```js
if (dd.accountOverrides) {
  for (const override of Object.values(dd.accountOverrides)) {
    delete override.coverImage
  }
}
```

### 7.4 `loadDraft()` 完整改造

```js
async function loadDraft(draftId) {
  try {
    const resp = await draftApi.getDraft(draftId)
    if (resp.code !== 200) return
    const draft = resp.data
    const dd = draft.draft_data
    if (!dd) { ElMessage.error('草稿数据为空'); return }

    currentDraftId.value = draft.id

    // 恢复公共配置
    if (dd.commonConfig) {
      if (dd.commonConfig.images) {
        commonConfig.images = dd.commonConfig.images.map((img, i) => ({
          id: img.id, name: img.name || `图片 ${i + 1}`,
          url: img.stored_path ? getFileUrl(img.stored_path) : (img.url || ''),
          stored_path: img.stored_path || '', size: img.size || 0,
          type: img.type || 'image/jpeg', uploading: false, progress: 100,
        }))
      }
      if (dd.commonConfig.coverImage) {
        const ci = dd.commonConfig.coverImage
        commonConfig.coverImage = { ...ci, url: ci.stored_path ? getFileUrl(ci.stored_path) : (ci.url || '') }
      }
    }

    // 兼容迁移（7.1 ~ 7.3）
    migrateOldDraftFormat(dd)

    // 恢复各渠道配置
    if (dd.platformConfigs) {
      for (const [key, val] of Object.entries(dd.platformConfigs)) {
        const panel = panelRefs[key]
        if (panel && val) {
          panel.restoreConfigs(val, dd.accountOverrides || {})
        }
      }
    }

    // 恢复发布账号
    if (dd.publishAccountIds) {
      publishAccountIds.clear()
      dd.publishAccountIds.forEach(id => publishAccountIds.add(id))
    }

    // 恢复 UI 状态
    if (dd.expandedGroups) expandedGroups.value = new Set(dd.expandedGroups)
    if (dd.selectedPlatform) selectedPlatform.value = dd.selectedPlatform
    if (dd.selectedAccountId) {
      selectedAccountId.value = dd.selectedAccountId
    } else if (dd.publishAccountIds?.length > 0) {
      selectedAccountId.value = dd.publishAccountIds[0]
    }

    ElMessage.success('草稿已加载')
  } catch (e) {
    console.error('加载草稿失败:', e)
    ElMessage.error('加载草稿失败')
  }
}
```

---

## 8. 改造清单汇总

| 序号 | 文件 | 操作 | 说明 |
|------|------|------|------|
| 1 | `views/ImagePublish.vue` | **大幅修改** | 删除平台特有逻辑，改为壳 + ref 调度 |
| 2 | `components/douyin/ImagePublishPanel.vue` | **新建** | 抖音图文主面板 |
| 3 | `components/xiaohongshu/ImagePublishPanel.vue` | **新建** | 小红书图文主面板 |
| 4 | `components/kuaishou/ImagePublishPanel.vue` | **新建** | 快手图文主面板 |
| 5 | `components/douyin/ActivitySelect.vue` | **不动** | — |
| 6 | `components/douyin/HotspotSelect.vue` | **不动** | — |
| 7 | `components/douyin/MusicSelect.vue` | **不动** | — |
| 8 | `components/douyin/MusicDrawer.vue` | **不动** | — |
| 9 | `components/douyin/TagSelect.vue` | **不动** | — |
| 10 | `components/douyin/MixSelect.vue` | **不动** | — |
| 11 | `config/platforms.js` | **不动** | 无需改动 |

---

## 9. 不变的部分

以下内容完全不变：

- 左侧账号栏（模板 + 逻辑）
- 图片上传区（ImageUploader + ImageCarousel）
- 封面设置区（ImageCoverUpload）
- 图片预览面板（Phone mockup）
- 账号选择对话框
- 批量发布进度对话框
- 素材库对话框
- `api/imagePublish.js`、`api/draft.js`
- 所有后端代码
