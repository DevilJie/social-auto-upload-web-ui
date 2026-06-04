# 视频发布渠道配置统一化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让视频发布（PublishCenter.vue）的渠道配置方式向图文发布看齐——所有平台统一标题/描述/标签/视频格式，抖音复用图文子组件，发布逻辑对齐。

**Architecture:** 在 PublishCenter.vue 内部改造（不拆分组件），删除话题/活动/好友 UI，添加通用标签输入，抖音区域嵌入现有子组件。后端 douyin/platform.py 新增 activities 参数处理。

**Tech Stack:** Vue 3 + Element Plus + Pinia / Flask + Playwright

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `frontend/src/views/PublishCenter.vue` | Modify | 主改动文件：模板、逻辑、样式 |
| `frontend/src/config/platforms.js` | Modify | B站移除 tags 字段，抖音移除 productTitle/productLink/visibility/allowDownload |
| `backend/impl/douyin/platform.py` | Modify | publish_video 新增 activities 处理，tags 输入改 insert_text |

---

### Task 1: 移除话题/活动/好友 UI 及相关状态

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

- [ ] **Step 1.1: 删除模板中的"添加话题/参加活动/添加好友"按钮区域**

删除第 128-149 行（quick-tags 按钮 + topics 展示行）：

```html
<!-- 删除以下代码 (第 128-149 行) -->
<!-- Quick tag buttons -->
<div class="quick-tags">
  <button class="cover-action-btn" @click="topicDialogVisible = true">
    <span># 添加话题</span>
  </button>
  <button class="cover-action-btn">
    <span>$ 参加活动</span>
  </button>
  <button class="cover-action-btn">
    <span>@ 添加好友</span>
  </button>
</div>
<div v-if="commonConfig.topics.length" class="topics-row">
  <el-tag
    v-for="(t, i) in commonConfig.topics"
    :key="i"
    closable
    @close="commonConfig.topics.splice(i, 1)"
    size="small"
    class="cursor-pointer"
  >#{{ t }}</el-tag>
</div>
```

- [ ] **Step 1.2: 删除话题对话框模板**

删除第 389-424 行（整个 `el-dialog` 话题选择对话框）：

```html
<!-- 删除以下代码 (第 389-424 行) -->
<!-- Topic Selection Dialog -->
<el-dialog
  v-model="topicDialogVisible"
  title="添加话题"
  width="560px"
  class="topic-dialog"
>
  ...（整个对话框内容）
</el-dialog>
```

- [ ] **Step 1.3: 删除 script 中的话题相关状态和函数**

删除以下代码：

```js
// 删除 (第 718 行)
const topicDialogVisible = ref(false)

// 删除 (第 738-743 行)
const customTopic = ref('')
const recommendedTopics = [
  '游戏', '电影', '音乐', '美食', '旅行', '文化',
  '科技', '生活', '娱乐', '体育', '教育', '艺术',
  '健康', '时尚', '美妆', '摄影', '宠物', '汽车',
]

// 删除 (第 930-954 行) - 整个 Topic Methods 区块
function addCustomTopic() { ... }
function toggleRecommendedTopic(topic) { ... }
```

- [ ] **Step 1.4: 从 commonConfig 中移除 topics**

修改第 536-542 行：

```js
// 之前
const commonConfig = reactive({
  videoLandscape: null,
  videoPortrait: null,
  coverLandscape: null,
  coverPortrait: null,
  topics: [],
})

// 之后
const commonConfig = reactive({
  videoLandscape: null,
  videoPortrait: null,
  coverLandscape: null,
  coverPortrait: null,
})
```

- [ ] **Step 1.5: 从 saveDraft 中移除 topics**

修改第 975-977 行：

```js
// 之前
commonConfig: {
  topics: [...commonConfig.topics],
  videoLandscape: ...

// 之后
commonConfig: {
  videoLandscape: ...
```

- [ ] **Step 1.6: 从 restoreDraft 中移除 topics 恢复**

删除第 1024 行：

```js
// 删除
if (dd.commonConfig.topics) commonConfig.topics = dd.commonConfig.topics
```

- [ ] **Step 1.7: 删除 import 中不再使用的图标**

检查第 476 行 import，移除不再需要的图标（如有）。`topicDialogVisible` 相关的 `StarFilled` 等图标如果无其他用途则移除。

- [ ] **Step 1.8: 删除样式中的 quick-tags/topics-row 相关 CSS**

在 `<style>` 区块中搜索 `.quick-tags`、`.topics-row`、`.topic-dialog`、`.topic-grid`、`.topic-btn`、`.custom-topic-input`、`.recommended-topics` 相关样式并删除。

- [ ] **Step 1.9: 验证**

启动前端 dev server（`cd frontend && npm run dev`），打开视频发布页面，确认：
- "添加话题"、"参加活动"、"添加好友" 按钮已消失
- 话题对话框不再弹出
- 页面其他功能正常

- [ ] **Step 1.10: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "refactor: 移除视频发布的话题/活动/好友 UI 及相关状态"
```

---

### Task 2: 为所有平台添加通用标签输入

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

- [ ] **Step 2.1: 在模板中添加通用标签输入 UI**

在视频格式设置卡片之后（第 223 行之后）、settings-grid 之前（第 225 行之前），插入标签输入卡片：

```html
<!-- 通用标签输入 -->
<div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
  <div class="setting-label" :style="{ color: currentPlatformConfig.color }">标签</div>
  <div class="setting-hint">输入标签内容，按回车确认</div>
  <el-input
    v-model="tagInput"
    placeholder="输入标签内容，按回车添加"
    @keyup.enter="addTag"
    clearable
  />
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
```

- [ ] **Step 2.2: 在 script 中添加 tagInput ref 和 addTag/removeTag 函数**

在 `// ========== Batch sync ==========` 之前（约第 695 行前）添加：

```js
// ========== Tag Input ==========
const tagInput = ref('')

function addTag() {
  const tag = tagInput.value.trim()
  if (!tag) return
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

- [ ] **Step 2.3: 在所有平台的 platformConfigs 中添加 tags: []**

修改第 558-569 行，每个平台配置添加 `tags: []`：

```js
const platformConfigs = reactive({
  douyin: { title: '', description: '', tags: [], productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true, videoFormat: '' },
  xiaohongshu: { title: '', description: '', tags: [], collection: '', groupChat: '', location: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  kuaishou: { title: '', description: '', tags: [], productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  bilibili: { title: '', description: '', tags: [], zone: '', topic: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
  channels: { title: '', description: '', tags: [], isDraft: false, location: '', aiContent: false, isOriginal: false, videoFormat: '' },
  baijiahao: { title: '', description: '', tags: [], aiContent: false, isOriginal: false, videoFormat: '' },
  tiktok: { title: '', description: '', tags: [], aiContent: false, isOriginal: false, scheduleTime: '', videoFormat: '' },
  youtube: { title: '', description: '', tags: [], audience: 'not_kids', alteredContent: false, scheduleTime: '', videoFormat: '' },
  iqiyi: { title: '', description: '', tags: [], creationDeclaration: '', riskWarning: '', enableCashActivity: false, scheduleTime: '', videoFormat: '' },
  tencent_video: { title: '', description: '', tags: [], creationDeclaration: [], scheduleTime: '', videoFormat: '' },
})
```

注意：bilibili 的 `tags: ''`（字符串）改为 `tags: []`（数组），并移除原有的 `tags` 字段定义。

- [ ] **Step 2.4: 在批量同步中添加标签同步**

修改 `syncBatchToAll()` 函数（第 699-705 行），添加标签同步支持：

```js
function syncBatchToAll() {
  for (const key of Object.keys(platformConfigs)) {
    if (batchTitle.value) platformConfigs[key].title = batchTitle.value
    if (batchDescription.value) platformConfigs[key].description = batchDescription.value
    if (batchTags.value.length > 0) platformConfigs[key].tags = [...batchTags.value]
  }
  ElMessage.success('已同步到所有平台')
}
```

- [ ] **Step 2.5: 添加批量标签输入 UI 和状态**

在批量同步区域的描述输入之后（第 121 行之后）、同步按钮之前（第 122 行之前），添加标签批量输入：

```html
<div class="form-field">
  <div class="field-head">
    <span>公共标签</span>
  </div>
  <el-input
    v-model="batchTagInput"
    placeholder="输入标签内容，按回车添加"
    @keyup.enter="addBatchTag"
    clearable
  />
  <div v-if="batchTags.length > 0" style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 6px;">
    <el-tag
      v-for="(t, i) in batchTags"
      :key="i"
      closable
      @close="batchTags.splice(i, 1)"
      size="small"
    >#{{ t }}</el-tag>
  </div>
</div>
```

在 script 中添加（batchTitle/batchDescription 附近）：

```js
const batchTagInput = ref('')
const batchTags = ref([])

function addBatchTag() {
  const tag = batchTagInput.value.trim()
  if (!tag) return
  if (batchTags.value.includes(tag)) {
    ElMessage.warning('标签已存在')
    return
  }
  batchTags.value.push(tag)
  batchTagInput.value = ''
}
```

- [ ] **Step 2.6: 添加标签输入相关样式**

在 `<style>` 区块中添加：

```scss
.setting-hint {
  font-size: 12px;
  color: #909399;
  margin-bottom: 8px;
  line-height: 1.5;
}

.tags-list {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
```

- [ ] **Step 2.7: 验证**

打开视频发布页面：
- 选择任意平台，确认标签输入卡片出现
- 输入标签按回车，确认标签 tag 出现
- 点击 tag 的关闭按钮，确认标签被删除
- 输入重复标签，确认提示"标签已存在"
- 展开批量设置，确认标签批量输入可用
- 点击"同步到所有平台"，切换到其他平台确认标签已同步

- [ ] **Step 2.8: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: 视频发布所有平台添加通用标签输入"
```

---

### Task 3: 抖音渠道配置改造

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`
- Modify: `frontend/src/config/platforms.js`

- [ ] **Step 3.1: 导入抖音子组件**

在 PublishCenter.vue 的 import 区域（第 490 行之后）添加：

```js
import DouyinActivitySelect from '@/components/douyin/ActivitySelect.vue'
import DouyinHotspotSelect from '@/components/douyin/HotspotSelect.vue'
import DouyinTagSelect from '@/components/douyin/TagSelect.vue'
import DouyinMixSelect from '@/components/douyin/MixSelect.vue'
```

- [ ] **Step 3.2: 修改抖音 platformConfigs 默认值**

修改第 559 行的 douyin 配置：

```js
// 之前
douyin: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true, videoFormat: '' },

// 之后
douyin: { title: '', description: '', tags: [], aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '', activityId: [], hotspotId: '', hotspotData: null, selectedTag: null, tagType: '', tagValue: '', mixId: '', mixData: null },
```

- [ ] **Step 3.3: 更新 platforms.js 中抖音的 settingsFields 和 defaultSettings**

修改 `frontend/src/config/platforms.js` 第 78-95 行：

```js
// 之前 (第 78-95 行)
settingsFields: [
  { key: 'productTitle', label: '商品名称', type: 'input', placeholder: '请输入商品名称' },
  { key: 'productLink', label: '商品链接', type: 'input', placeholder: '请输入商品链接' },
  { key: 'aiContent', label: '自主声明', type: 'select', ... },
  { key: 'isOriginal', label: '原创声明', type: 'radio', ... },
  { key: 'scheduleTime', label: '定时发布', type: 'datetime', ... },
  { key: 'visibility', label: '谁可以看', type: 'radio', ... },
  { key: 'allowDownload', label: '允许下载', type: 'switch' },
  { key: 'videoFormat', label: '视频格式', type: 'radio', ... },
],
defaultSettings: { title: '', description: '', productTitle: '', productLink: '', aiContent: '', isOriginal: false, scheduleTime: '', visibility: 'public', allowDownload: true, videoFormat: '' },

// 之后
settingsFields: [
  { key: 'aiContent', label: '自主声明', type: 'select', placeholder: '请选择自主声明', options: [
    { label: '内容由AI生成', value: '内容由AI生成' },
    { label: '内容为个人观点或见解', value: '内容为个人观点或见解' },
    { label: '内容为转载信息', value: '内容为转载信息' },
    { label: '内容含营销推广信息', value: '内容含营销推广信息' },
    { label: '虚构演绎，仅供娱乐', value: '虚构演绎，仅供娱乐' },
    { label: '无需添加自主声明', value: '无需添加自主声明' },
  ] },
  { key: 'isOriginal', label: '原创声明', type: 'radio', options: [{ label: '原创', value: true }, { label: '非原创', value: false }] },
  { key: 'scheduleTime', label: '定时发布', type: 'datetime', placeholder: '选择时间' },
],
defaultSettings: { title: '', description: '', tags: [], aiContent: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
```

注意：移除了 `productTitle`、`productLink`、`visibility`、`allowDownload`、`videoFormat`（videoFormat 已在通用字段中处理）。

- [ ] **Step 3.4: 在模板的抖音区域添加子组件**

在 settings-grid（第 225 行）之前、视频格式卡片之后（第 223 行之后），添加抖音专属区域：

```html
<!-- 抖音专属配置 -->
<template v-if="selectedPlatform === 'douyin'">
  <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
    <div class="setting-label" :style="{ color: currentPlatformConfig.color }">官方活动</div>
    <DouyinActivitySelect v-model="form.activityId" @change="handleDouyinActivityChange" />
  </div>

  <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
    <div class="setting-label" :style="{ color: currentPlatformConfig.color }">关联热点</div>
    <DouyinHotspotSelect v-model="form.hotspotId" :data="form.hotspotData" @change="handleDouyinHotspotChange" />
  </div>

  <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
    <div class="setting-label" :style="{ color: currentPlatformConfig.color }">添加标签</div>
    <DouyinTagSelect :account-id="selectedAccountId" v-model="form.selectedTag" @change="handleDouyinTagSelect" />
  </div>

  <div v-if="selectedAccountId" class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
    <div class="setting-label" :style="{ color: currentPlatformConfig.color }">添加合集</div>
    <DouyinMixSelect :account-id="selectedAccountId" v-model="form.mixId" :data="form.mixData" @change="handleDouyinMixChange" />
  </div>
</template>
```

- [ ] **Step 3.5: 添加抖音子组件的事件处理函数**

在 script 中（Topic Methods 位置替换为 Douyin Methods）添加：

```js
// ========== Douyin-specific Methods ==========
function handleDouyinActivityChange(activity) {
  if (activity?.challenge?.length > 0) {
    for (const topic of activity.challenge) {
      if (form.tags && !form.tags.includes(topic)) {
        if ((form.activityId?.length || 0) + (form.tags?.length || 0) >= 5) break
        form.tags.push(topic)
      }
    }
  }
}

function handleDouyinHotspotChange(hotspot) {
  if (hotspot) {
    form.hotspotId = hotspot.word
    form.hotspotData = hotspot
  } else {
    form.hotspotId = ''
    form.hotspotData = null
  }
}

function handleDouyinTagSelect(tag) {
  if (tag) {
    form.selectedTag = tag
    const m = { poi: 'location', miniapp: 'miniapp', game: 'gamepad', mark: 'mark' }
    form.tagType = m[tag.type] || ''
    form.tagValue = tag.name || tag.id || ''
    ElMessage.success(`标签已选择: ${tag.name}`)
  } else {
    form.selectedTag = null
    form.tagType = ''
    form.tagValue = ''
  }
}

function handleDouyinMixChange(mix) {
  if (mix) {
    form.mixId = mix.mix_name
    form.mixData = mix
  } else {
    form.mixId = ''
    form.mixData = null
  }
}
```

- [ ] **Step 3.6: 验证**

打开视频发布页面，选择抖音平台：
- 确认"官方活动"、"关联热点"、"添加标签"卡片出现
- 确认选择账号后"合集"卡片出现
- 确认各子组件交互正常（搜索、选择、清除）
- 确认其他平台不受影响

- [ ] **Step 3.7: 提交**

```bash
git add frontend/src/views/PublishCenter.vue frontend/src/config/platforms.js
git commit -m "feat: 抖音视频发布复用图文子组件（活动/热点/标签/合集）"
```

---

### Task 4: 发布逻辑改造

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

- [ ] **Step 4.1: 修改 publishAll 中的 tags 组装逻辑**

修改第 1257-1259 行：

```js
// 之前
const customTags = (platformSettings.tags || '').split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
const allTags = [...commonConfig.topics, ...customTags]

// 之后
const tags = platformSettings.tags || []
```

- [ ] **Step 4.2: 修改 publishData 构建，添加 activities 和 douyin 特有字段**

修改第 1261-1288 行的 publishData 构建：

```js
const publishData = {
  type: group.id,
  title: platformSettings.title,
  description: platformSettings.description || '',
  tags: tags,
  activities: platformSettings.activityId || [],
  fileList: [selectedVideo.stored_path],
  videoFormat: videoFormat,
  accountList: [account.filePath],
  thumbnailLandscape: commonConfig.coverLandscape ? commonConfig.coverLandscape.stored_path : '',
  thumbnailPortrait: commonConfig.coverPortrait ? commonConfig.coverPortrait.stored_path : '',
  enableTimer: platformSettings.scheduleTime ? 1 : 0,
  scheduleTime: platformSettings.scheduleTime || '',
  videosPerDay: 1,
  dailyTimes: ['10:00'],
  startDays: 0,
  category: platformSettings.zone || (platformSettings.isOriginal ? 1 : 0),
  // 抖音特有字段
  hotspot: platformSettings.hotspotId || '',
  tag_type: platformSettings.tagType || '',
  tag_value: platformSettings.tagValue || '',
  mini_link: platformSettings.selectedTag?.type === 'miniapp' ? (platformSettings.selectedTag._searchKeyword || '') : '',
  mix_id: platformSettings.mixId || '',
  // 通用字段
  isDraft: platformSettings.isDraft || false,
  aiContent: platformSettings.aiContent || '',
  creationDeclaration: Array.isArray(platformSettings.creationDeclaration)
    ? platformSettings.creationDeclaration.join(',')
    : platformSettings.creationDeclaration || '',
  riskWarning: platformSettings.riskWarning || '',
  enableCashActivity: platformSettings.enableCashActivity || false,
  audience: platformSettings.audience || 'not_kids',
  alteredContent: platformSettings.alteredContent || false,
}
```

注意：移除了 `productLink` 和 `productTitle`，新增了 `activities`、`hotspot`、`tag_type`、`tag_value`、`mini_link`、`mix_id`。

- [ ] **Step 4.3: 验证**

确认发布逻辑代码无语法错误，标签从数组直接传递，activities 单独传递。

- [ ] **Step 4.4: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "refactor: 视频发布逻辑改为 activities+tags 数组传递"
```

---

### Task 5: 后端改造 — douyin publish_video 支持 activities

**Files:**
- Modify: `backend/impl/douyin/platform.py`

- [ ] **Step 5.1: 在 publish_video 中添加 activities 参数解析**

修改第 223 行之后，添加：

```python
# 之前 (第 223 行)
tags = kwargs.get("tags", []) or []

# 之后
tags = kwargs.get("tags", []) or []
activities = kwargs.get("activities", []) or []
```

- [ ] **Step 5.2: 在 _upload_one_video 调用中传递 activities**

修改第 265-278 行的 `_upload_one_video` 调用：

```python
# 之前
await self._upload_one_video(
    title=title,
    file_path=file_path,
    tags=tags,
    ...
)

# 之后
await self._upload_one_video(
    title=title,
    file_path=file_path,
    tags=tags,
    activities=activities,
    ...
)
```

- [ ] **Step 5.3: 在 _upload_one_video 签名中添加 activities 参数**

修改第 285-289 行：

```python
# 之前
async def _upload_one_video(
    self,
    title: str,
    file_path: str,
    tags: list,
    ...

# 之后
async def _upload_one_video(
    self,
    title: str,
    file_path: str,
    tags: list,
    activities: list | None = None,
    ...
```

- [ ] **Step 5.4: 在 _upload_one_video 中拼接 activities 到 description**

在第 342-344 行的 `_fill_title_and_description` 调用之前，添加 activities 处理（和图文发布一致）：

```python
# 之前 (第 342-344 行)
await self._fill_title_and_description(
    page, title, desc or title, tags
)

# 之后
# Append activities as hashtags to description (与图文发布一致)
if activities:
    activity_tags = " ".join([f"#{act}" for act in activities])
    desc = f"{desc or title} {activity_tags}".strip()

await self._fill_title_and_description(
    page, title, desc or title, tags
)
```

- [ ] **Step 5.5: 修改 _fill_title_and_description 中 tags 输入方式**

修改第 452-454 行：

```python
# 之前
for tag in tags or []:
    await page.keyboard.type(" #" + tag)
    await page.keyboard.press("Space")

# 之后（与图文发布一致）
for tag in tags or []:
    await page.keyboard.insert_text(" #" + tag)
    await page.keyboard.press("Space")
```

- [ ] **Step 5.6: 更新 publish_video docstring**

修改第 199-220 行的 docstring，添加 activities 参数说明：

```python
async def publish_video(self, **kwargs) -> bool:
    """Publish a video to Douyin via CloakBrowser.

    Accepted keyword arguments:

    - ``title`` (*str*) -- video title
    - ``files`` (*list[str]*) -- video absolute file paths
    - ``tags`` (*list[str]*) -- hashtags
    - ``activities`` (*list[str]*, optional) -- official activities (appended as #tags to description)
    - ``account_file`` (*list[str]*) -- cookie file names
    ...
    """
```

- [ ] **Step 5.7: 验证**

启动后端（`cd backend && python3 app.py`），确认无导入错误或语法错误。

- [ ] **Step 5.8: 提交**

```bash
git add backend/impl/douyin/platform.py
git commit -m "feat: 抖音视频发布支持 activities 参数，tags 输入改用 insert_text"
```

---

### Task 6: 草稿兼容 — 旧格式迁移

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

- [ ] **Step 6.1: 在 restoreDraft 中添加旧格式迁移逻辑**

在 `restoreDraft` 函数中，`dd.platformConfigs` 恢复之后（第 1053 行之后），添加迁移逻辑：

```js
// 兼容旧草稿格式：将 commonConfig.topics 迁移到各平台的 tags
if (dd.commonConfig?.topics && dd.commonConfig.topics.length > 0) {
  for (const key of Object.keys(platformConfigs)) {
    if (!platformConfigs[key].tags || platformConfigs[key].tags.length === 0) {
      platformConfigs[key].tags = [...dd.commonConfig.topics]
    }
  }
}

// 兼容旧草稿格式：bilibili 的 tags 从字符串转数组
if (dd.platformConfigs?.bilibili && typeof dd.platformConfigs.bilibili.tags === 'string') {
  const str = dd.platformConfigs.bilibili.tags
  platformConfigs.bilibili.tags = str.split(/[,，\s]+/).map(t => t.replace(/^#/, '').trim()).filter(Boolean)
}

// 兼容旧草稿格式：为缺少 tags 的平台补充空数组
for (const key of Object.keys(platformConfigs)) {
  if (!Array.isArray(platformConfigs[key].tags)) {
    platformConfigs[key].tags = []
  }
}

// 兼容旧草稿格式：为抖音补充新增字段
if (dd.platformConfigs?.douyin) {
  const dy = platformConfigs.douyin
  if (!Array.isArray(dy.activityId)) dy.activityId = []
  if (!dy.hotspotId && dy.hotspotId !== '') dy.hotspotId = ''
  if (!dy.hotspotData && dy.hotspotData !== null) dy.hotspotData = null
  if (!dy.selectedTag && dy.selectedTag !== null) dy.selectedTag = null
  if (!dy.tagType && dy.tagType !== '') dy.tagType = ''
  if (!dy.tagValue && dy.tagValue !== '') dy.tagValue = ''
  if (!dy.mixId && dy.mixId !== '') dy.mixId = ''
  if (!dy.mixData && dy.mixData !== null) dy.mixData = null
}
```

- [ ] **Step 6.2: 验证**

- 创建一个旧格式的视频发布草稿（先用改动前的代码保存一个）
- 切换到新代码，从草稿箱恢复该草稿
- 确认 topics 正确迁移到各平台的 tags
- 确认 bilibili 的 tags 从字符串正确转为数组
- 确认抖音新增字段有默认值

- [ ] **Step 6.3: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat: 视频发布草稿兼容旧格式迁移（topics→tags、字符串→数组）"
```

---

### Task 7: B站移除 settingsFields 中的 tags 字段

**Files:**
- Modify: `frontend/src/config/platforms.js`

- [ ] **Step 7.1: 从 B站 settingsFields 中移除 tags**

修改 `frontend/src/config/platforms.js` 第 162 行：

```js
// 删除这一行
{ key: 'tags', label: '标签', type: 'input', placeholder: '如：#标签1 #标签2 或 逗号分隔' },
```

同时从 B站 defaultSettings 中移除 tags（第 176 行）：

```js
// 之前
defaultSettings: { title: '', description: '', zone: '', tags: '', topic: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },

// 之后
defaultSettings: { title: '', description: '', zone: '', topic: '', creationDeclaration: '', isOriginal: false, scheduleTime: '', videoFormat: '' },
```

- [ ] **Step 7.2: 验证**

选择 B站平台，确认：
- settingsFields 中不再有独立的"标签"输入
- 通用标签输入卡片正常工作

- [ ] **Step 7.3: 提交**

```bash
git add frontend/src/config/platforms.js
git commit -m "refactor: B站移除 settingsFields 中的 tags 字段，改用通用标签输入"
```

---

### Task 8: 端到端验证

- [ ] **Step 8.1: 启动前后端**

```bash
# 终端 1
cd backend && python3 app.py

# 终端 2
cd frontend && npm run dev
```

- [ ] **Step 8.2: 验证通用功能**

打开视频发布页面：
- [ ] 所有平台都有标题、描述、标签、视频格式 4 个通用字段
- [ ] 标签输入支持回车添加、去重、删除
- [ ] 批量设置支持标题、描述、标签同步
- [ ] "添加话题"、"参加活动"、"添加好友" 按钮已消失

- [ ] **Step 8.3: 验证抖音专属功能**

选择抖音平台：
- [ ] 官方活动子组件正常（搜索、多选、最多 5 个）
- [ ] 关联热点子组件正常
- [ ] 添加标签子组件正常（POI/小程序/游戏/商品）
- [ ] 选择账号后合集子组件出现
- [ ] settingsFields 中不再有 productTitle/productLink/visibility/allowDownload

- [ ] **Step 8.4: 验证草稿机制**

- [ ] 保存草稿，确认数据结构中无 topics，各平台有 tags 数组
- [ ] 恢复草稿，确认 tags 正确还原
- [ ] 恢复旧格式草稿，确认 topics 正确迁移到 tags

- [ ] **Step 8.5: 验证其他平台**

逐一检查各平台（小红书、快手、B站、视频号、百家号、TikTok、YouTube、腾讯视频、爱奇艺）：
- [ ] settingsFields 渲染正常
- [ ] 标签输入正常
- [ ] 无多余字段

- [ ] **Step 8.6: 最终提交**

```bash
git add -A
git commit -m "feat: 视频发布渠道配置统一化完成"
```
