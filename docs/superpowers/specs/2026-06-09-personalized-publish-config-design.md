# 个性化发布配置 + 发布历史明细卡片化 — 设计 spec

日期：2026-06-09
作者：与用户协作完成
状态：已设计，待用户审阅

## 1. 背景与目标

### 1.1 当前问题

| # | 问题 | 严重性 |
|---|---|---|
| A | 视频发布的"公共配置"区（视频文件 / 封面 / 批量标题描述标签）是**全局共享**：所有账号拿同一份内容发布，无法在一次批次中为不同账号配不同文案 | 高 |
| B | 图文发布同理：图片列表 + 封面是全局共享，无法在一次批次中为不同渠道发不同图片 | 高 |
| C | PublishHistory 展开明细时是一行文本（账号 · 平台 · 耗时 · 状态），看不到**该账号实际发布的内容**（标题/描述/标签/封面） | 中 |
| D | 草稿只存公共区域 + 平台级标题描述的"批量同步"状态，账号级/平台级覆写不存 → 恢复时数据丢失 | 中 |

### 1.2 目标

1. **平台级 + 账号级 两级个性化配置**（视频和图文都支持）
   - 平台级：每个平台 1 个"个性化配置"复选框。勾选后该平台下所有账号默认沿用平台级覆写。
   - 账号级：每个账号 1 个"个性化配置"复选框（仅当平台级已勾选时可独立再勾选）。勾选后该账号独立覆写。
2. **覆写区字段**：视频文件（横/竖）、封面（横/竖）、标题、描述、标签
3. **优先级**：账号覆写 > 平台覆写 > 公共区域
4. **取消勾选** → 弹窗"覆写将丢失，是否继续？"
5. **草稿**：完整保存平台/账号级覆写数据 + 勾选状态，恢复时不丢失任何字段
6. **发布**时把"按优先级合并后的完整数据"写入 `publish_details.account_configs` JSON
7. **PublishHistory 明细行**全部重设计为卡片，呈现每个账号实际发布的内容

### 1.3 不在范围

- 一键填写（OneClickFill）不感知个性化勾选状态，仍按当前实现复制第一个 detail 的 `account_configs`
- 不做跨批次的覆写继承
- 不做"覆写模板"复用
- 不改平台实现（`backend/impl/*` 一律不动）
- 不改登录/Cookie/素材库/任务中心/统计

## 2. 数据模型

### 2.1 数据库表

`publish_batches` / `publish_details` schema **不动**。`account_configs` JSON 内容扩展；草稿表的 JSON 字段也扩展。

### 2.2 `publish_details.account_configs` 合并后结构

**视频**：
```json
{
  "title": "...",
  "description": "...",
  "tags": ["..."],
  "videoLandscape": { "id": "...", "stored_path": "...", "url": "...", "name": "...", "size": ..., "type": "..." },
  "videoPortrait":  { "id": "...", ... },
  "coverLandscape": { "id": "...", "stored_path": "...", "url": "...", "name": "...", "size": ..., "type": "..." },
  "coverPortrait":  { "id": "...", ... },
  "videoFormat": "landscape" | "portrait",
  "enableTimer": 0 | 1,
  "scheduleTime": "",
  "aiContent": "...",
  "isOriginal": true | false,
  ... // 平台特有字段
}
```

**图文**：
```json
{
  "title": "...",
  "description": "...",
  "tags": ["..."],
  "images": [{ "id": "...", "stored_path": "...", "url": "...", "name": "...", "size": ..., "type": "..." }],
  "coverImage": { "id": "...", "stored_path": "...", ... },
  "enableTimer": 0 | 1,
  "scheduleTime": "",
  ... // 平台特有字段
}
```

> 关键点：写库的就是合并后的完整数据，明细卡片渲染只需读这一个字段。

### 2.3 草稿 JSON 扩展

`drafts.data` 和 `image_drafts.data` 增加 4 个键：

```json
{
  "commonConfig": { ... },                       // 现有
  "platformConfigs": { "douyin": { ... } },     // 现有（per-platform 标题描述标签等）
  "platformOverrides": {                         // 新增：渠道级覆写完整对象
    "douyin": { "title": "...", "videoLandscape": {...}, "coverLandscape": {...}, ... }
  },
  "accountOverrides": {                          // 新增：账号级覆写完整对象
    "1": { "title": "...", "videoLandscape": {...}, ... }
  },
  "platformChecked": { "douyin": true },         // 新增：渠道级勾选状态
  "accountChecked": { "1": true }                // 新增：账号级勾选状态
}
```

## 3. 前端改动

### 3.1 涉及文件

| 文件 | 改动 |
|---|---|
| `frontend/src/views/PublishCenter.vue` | 加平台/账号级复选框 + 覆写区；改造 `publishAll` / `saveDraft` / `loadDraft` |
| `frontend/src/views/ImagePublish.vue` | 同上 |
| `frontend/src/components/DouyinImagePublishPanel.vue` | 暴露 `platformOverride` / `accountOverride` props + emit |
| `frontend/src/components/XiaohongshuImagePublishPanel.vue` | 同上 |
| `frontend/src/components/KuaishouImagePublishPanel.vue` | 同上 |
| `frontend/src/views/PublishHistory.vue` | `.detail-row` → `.detail-card` 卡片化 |
| `frontend/src/api/drafts.js` | 不动（草稿 JSON 整体打包，自动透传新键） |
| `frontend/src/stores/app.js` | 可能需扩 state（保存/恢复覆写区） |

### 3.2 不动的文件

- 所有 `backend/impl/*`（平台实现）
- `frontend/src/views/TaskCenter.vue`、`Dashboard.vue`、`AccountManagement.vue`、`MaterialManagement.vue`、`Settings.vue`
- 草稿后端 schema（透传新键即可）

### 3.3 PublishCenter.vue 改动

**覆写区与现有 per-platform form 的关系**：
- 现有 `platformConfigs[platformKey].title/desc/tags` 输入保留（不动），仍为"渠道默认"文本
- 新增"渠道覆写区" / "账号覆写区" 是**新的独立编辑面板**，用于覆写视频/封面 + 文本
- 三个层级的文本字段在发布时的优先级：**账号覆写 > 渠道覆写 > 渠道默认（platformConfigs）**
- 视频/封面的优先级：**账号覆写 > 渠道覆写 > 公共区域（commonConfig）**
- UI 上：覆写区与 per-platform form 并存（不替换）。用户编辑覆写区时，per-platform form 不变；反之亦然。两边的输入都可见，但发布时按优先级合并

**新增响应式 state**：
```js
// 平台级覆写
const platformOverrides = reactive({})         // { [platformKey]: { ...同 commonConfig } }
const platformChecked = reactive({})           // { [platformKey]: boolean }

// 账号级覆写
const accountOverrides = reactive({})          // { [accountId]: { ...同 commonConfig } }
const accountChecked = reactive({})            // { [accountId]: boolean }
```

**模板：右侧主体新增"渠道级配置区"和"账号级配置区"**：
```vue
<!-- 渠道级配置区 -->
<div class="config-section platform-override-section">
  <div class="section-bar">
    <div class="bar" :style="{background: currentPlatformConfig.color}"></div>
    <el-checkbox v-model="platformChecked[selectedPlatform]"
                 @change="onPlatformCheckChange">
      {{ currentPlatformConfig.name }} 渠道使用个性化配置
    </el-checkbox>
  </div>
  <div v-show="platformChecked[selectedPlatform]" class="override-body">
    <!-- 视频文件 / 封面 / 标题 / 描述 / 标签 覆写编辑区 -->
    <CoverCard v-model="platformOverrides[selectedPlatform].coverPortrait" ... />
    <CoverCard v-model="platformOverrides[selectedPlatform].coverLandscape" ... />
    <el-input v-model="platformOverrides[selectedPlatform].title" placeholder="渠道标题" />
    <el-input v-model="platformOverrides[selectedPlatform].description" type="textarea" placeholder="渠道描述" />
    <el-input v-model="platformOverrides[selectedPlatform].tagInput" @keyup.enter="addPlatformTag" />
  </div>
</div>

<!-- 账号级配置区（仅 selectedAccountId 时显示） -->
<div v-if="selectedAccountId" class="config-section account-override-section">
  <div class="section-bar">
    <el-checkbox v-model="accountChecked[selectedAccountId]"
                 :disabled="!platformChecked[selectedPlatform]"
                 @change="onAccountCheckChange">
      {{ getAccountName(selectedAccountId) }} 账号使用个性化配置
    </el-checkbox>
  </div>
  <div v-show="accountChecked[selectedAccountId]" class="override-body">
    <!-- 视频文件 / 封面 / 标题 / 描述 / 标签 覆写编辑区 -->
    ...
  </div>
</div>
```

**交互逻辑**：
```js
// 平台级勾选变化
function onPlatformCheckChange(checked) {
  if (!checked && hasPlatformOverrideContent(selectedPlatform)) {
    ElMessageBox.confirm(
      '取消个性化配置后，本渠道的覆写将丢失，恢复使用公共默认，是否继续？',
      '确认取消',
      { confirmButtonText: '继续', cancelButtonText: '取消', type: 'warning' }
    ).then(() => {
      delete platformOverrides[selectedPlatform.value]
    }).catch(() => {
      // 用户取消 → 恢复勾选
      platformChecked[selectedPlatform.value] = true
    })
  } else if (checked) {
    // 勾选 → 自动复制公共区域当前值作为初始值
    platformOverrides[selectedPlatform.value] = {
      title: '', description: '', tagInput: '', tags: [],
      coverPortrait: null, coverLandscape: null,
      videoLandscape: null, videoPortrait: null,
    }
  }
}

// 账号级勾选变化（结构同上；账号级取消时弹同样弹窗）
function onAccountCheckChange(checked) { ... }
```

**`publishAll` 改造**：
```js
function resolveAccountConfig(platformKey, accountId) {
  // 文本字段优先级：账号覆写 > 渠道覆写 > 渠道默认 (platformConfigs[platformKey])
  // 视频/封面优先级：账号覆写 > 渠道覆写 > 公共区域 (commonConfig)
  // 平台特有字段优先级：账号覆写 > 渠道覆写 > 渠道默认 > 公共默认
  const accountOv = (accountChecked[accountId] && accountOverrides[accountId]) || null
  const platformOv = (platformChecked[platformKey] && platformOverrides[platformKey]) || null
  const platformDefault = platformConfigs[platformKey] || null
  return mergeConfig(commonConfig, platformDefault, platformOv, accountOv)
}

async function publishAll() {
  const batchId = crypto.randomUUID()
  for (const account of selectedAccounts) {
    const merged = resolveAccountConfig(account.platform, account.id)
    await postVideo({
      ...merged,
      accountId: account.id,
      batchId,
      // 其他平台路由字段
    })
  }
}

function mergeConfig(common, platformDefault, platformOv, accountOv) {
  // 4 级优先级：accountOv > platformOv > platformDefault > common
  // 文本字段（title/desc/tags）不走 common 兜底（commonConfig 没存这些文本），
  // 走 platformDefault (platformConfigs) 兜底。
  return {
    title: accountOv?.title ?? platformOv?.title ?? platformDefault?.title ?? '',
    description: accountOv?.description ?? platformOv?.description ?? platformDefault?.description ?? '',
    tags: accountOv?.tags ?? platformOv?.tags ?? platformDefault?.tags ?? [],
    // 视频/封面走 commonConfig 兜底
    coverLandscape: accountOv?.coverLandscape ?? platformOv?.coverLandscape ?? common.coverLandscape,
    coverPortrait:  accountOv?.coverPortrait  ?? platformOv?.coverPortrait  ?? common.coverPortrait,
    videoLandscape: accountOv?.videoLandscape ?? platformOv?.videoLandscape ?? common.videoLandscape,
    videoPortrait:  accountOv?.videoPortrait  ?? platformOv?.videoPortrait  ?? common.videoPortrait,
    // 平台特有字段（视频格式 / 定时 / AI 声明 等）：
    // 文本/枚举走 platformDefault 兜底（per-platform form 一定有值），
    // 不走 common 兜底（commonConfig 不存这些）
    videoFormat: accountOv?.videoFormat ?? platformOv?.videoFormat ?? platformDefault?.videoFormat ?? 'portrait',
    enableTimer: accountOv?.enableTimer ?? platformOv?.enableTimer ?? platformDefault?.enableTimer ?? 0,
    scheduleTime: accountOv?.scheduleTime ?? platformOv?.scheduleTime ?? platformDefault?.scheduleTime ?? '',
    aiContent: accountOv?.aiContent ?? platformOv?.aiContent ?? platformDefault?.aiContent ?? '',
    isOriginal: accountOv?.isOriginal ?? platformOv?.isOriginal ?? platformDefault?.isOriginal ?? false,
    // ... 其他 platformConfigs 字段按相同优先级模式展开
  }
}
```

**`saveDraft` / `loadDraft` 改造**：
```js
function saveDraft() {
  return {
    commonConfig: cloneDeep(commonConfig),
    platformConfigs: cloneDeep(platformConfigs),
    platformOverrides: cloneDeep(platformOverrides),
    accountOverrides: cloneDeep(accountOverrides),
    platformChecked: { ...platformChecked },
    accountChecked: { ...accountChecked },
    // 其他现有字段
  }
}

function loadDraft(d) {
  // ... 现有恢复逻辑
  if (d.platformOverrides) Object.assign(platformOverrides, d.platformOverrides)
  if (d.accountOverrides)  Object.assign(accountOverrides,  d.accountOverrides)
  if (d.platformChecked)   Object.assign(platformChecked,   d.platformChecked)
  if (d.accountChecked)    Object.assign(accountChecked,    d.accountChecked)
}
```

### 3.4 ImagePublish.vue 改动

完全平行于 PublishCenter，差异：
- 公共区域只有 `images` / `coverImage`（无视频文件）
- 平台特有字段（aiContent/isOriginal/产品链接等）由 panel 内部维护

**覆写区与 panel 的关系**：
- 渠道级覆写区 / 账号级覆写区是**新的独立编辑面板**（与视频覆写区同结构），不复用 panel 组件
- panel 组件本身（`DouyinImagePublishPanel` 等）保持原样，仅承担"渠道默认"的角色
- 复选框在覆写区 section 的 header，复选区在 section 内部
- 父组件 ImagePublish.vue 自己管理覆写区 state（不通过 panel 透传）

**改造点**：
- 新增 `platformOverrides` / `accountOverrides` / `platformChecked` / `accountChecked` 四个 reactive 对象（同 PublishCenter 模式）
- 渠道级覆写区在"渠道默认 panel 上方"渲染，账号级覆写区在"渠道默认 panel 下方 + selectedAccountId 时"渲染
- 草稿保存/恢复同视频

### 3.5 PublishHistory.vue 明细卡片化

**当前实现**：`PublishHistory.vue:137-156` 的 `.detail-row` 是横向 flex 文本行

**改造后**：
```vue
<div v-if="expandedBatchId === batch.id" class="card-details">
  <div v-for="d in batch.items" :key="d.id" class="detail-card"
       :class="`status-${d.status}`">
    <div class="detail-cover">
      <img v-if="getCoverUrl(d)" :src="getCoverUrl(d)" :alt="d.platform" />
      <div v-else class="cover-placeholder"><el-icon :size="24"><Picture /></el-icon></div>
    </div>
    <div class="detail-body">
      <div class="detail-head">
        <span class="detail-platform">{{ d.platform }} · {{ d.account_name }}</span>
        <span class="status-tag" :class="`status-${d.status}`">
          {{ statusLabel(d.status) }} · {{ formatDuration(d.duration) }}
        </span>
        <el-tag v-if="d.personalized" type="warning" size="small" effect="plain">个性化</el-tag>
      </div>
      <div v-if="d.status === 'failed' && d.error_message" class="detail-error">
        错误：{{ d.error_message }}
      </div>
      <template v-else>
        <div class="detail-title">{{ getCfgField(d, 'title') || batch.title || '无标题' }}</div>
        <div class="detail-desc">{{ getCfgField(d, 'description') || batch.description || '无描述' }}</div>
        <div v-if="getCfgField(d, 'tags')?.length" class="detail-tags">
          <el-tag v-for="t in getCfgField(d, 'tags')" :key="t" size="small" effect="plain">#{{ t }}</el-tag>
        </div>
      </template>
      <div class="detail-foot">
        <a v-if="d.publish_url" :href="d.publish_url" target="_blank" rel="noopener noreferrer" @click.stop>[查看发布作品]</a>
      </div>
    </div>
  </div>
</div>
```

**辅助函数**：
```js
function getCfgField(d, field) {
  return d.account_configs?.[field]
}

function getCoverUrl(d) {
  // account_configs.coverLandscape / coverPortrait 是 dict 对象（含 url 字段）
  const cfg = d.account_configs || {}
  return cfg.coverLandscape?.url || cfg.coverPortrait?.url || d.cover_url || ''
}
```

**`personalized` 字段**：后端 `/api/v2/history` 端点派生计算（详见 §4.3）。**数据库不存**。

## 4. 后端改动

### 4.1 `backend/ext_api/task_queue.py`

`_insert_db` 中 `cfg` dict 扩展，**不动 INSERT 语句的字段**（`account_configs` 始终是 JSON 字符串）：

```python
cfg = {
    'title': task.title,
    'description': task.description,
    'tags': task.tags,
    'thumbnail_path': task.thumbnail_path,
    'videoLandscape': task.video_landscape,           # 新增（前端 mergeConfig 已传）
    'videoPortrait':  task.video_portrait,            # 新增
    'coverLandscape': task.cover_landscape,            # 新增
    'coverPortrait':  task.cover_portrait,             # 新增
    'videoFormat': task.video_format,                 # 新增
    'enableTimer': task.enable_timer,                 # 新增
    'scheduleTime': task.schedule_time,               # 新增
    'aiContent': task.ai_content,                     # 新增
    'isOriginal': task.is_original,                   # 新增
    'platform_type': task.platform_type,
    # ... 其他 platformConfigs 字段（per-platform form 全部纳入）
}
```

**重要**：当前 `cfg` 只存 `title/desc/tags/thumbnail_path/platform_type`，导致历史卡片信息不全。**这次改造把所有 per-platform form 字段都纳入 `account_configs` JSON**，使得历史卡片可以完整还原该账号当时实际发布的内容。

`PublishTask` dataclass 加可选字段（默认值 None）：
- `video_landscape: dict | None = None`
- `video_portrait: dict | None = None`
- `cover_landscape: dict | None = None`
- `cover_portrait: dict | None = None`
- `video_format: str | None = None`
- `enable_timer: int | None = None`
- `schedule_time: str | None = None`
- `ai_content: str | None = None`
- `is_original: bool | None = None`

后端在 `/postVideo` 路由把前端传来的对应字段写入 `task.video_landscape` 等。`/postVideo` 路由接受新字段，存入 `task` 对象。

### 4.2 `backend/blueprints/image_publish_bp.py`

`/api/image-publish/publish` 接受 `account_configs` 中扩字段：
- `images` 列表
- `coverImage` 对象
- （覆盖原 `image_ids` / cover 字段）

写入 `publish_details.account_configs` JSON 时把这些字段也存进去。

### 4.3 `backend/ext_api/__init__.py` `/api/v2/history`

请求响应**已**返回 `account_configs` JSON 解析后的对象，**无需改字段**。

**新增派生字段** `items[].personalized: bool`：在 `/api/v2/history` 中对每个 detail 计算。**数据库不存**，仅在响应中计算。

**具体比较规则**（按字段类型区分）：

| 字段 | `account_configs` 侧 | `publish_batches` 侧 | 比较方式 |
|---|---|---|---|
| 视频 | `cfg.videoLandscape?.id` (字符串) | `b.video_material_id` (字符串) | 字符串 `!=` |
| 视频 | `cfg.videoPortrait?.id` | `b.video_material_id` | 字符串 `!=` |
| 横版封面 | `cfg.coverLandscape?.id` | `b.landscape_cover_material_id` | 字符串 `!=` |
| 竖版封面 | `cfg.coverPortrait?.id` | `b.portrait_cover_material_id` | 字符串 `!=` |
| 标题 | `cfg.title` (字符串) | `b.title` (字符串) | 字符串 `!=` |
| 描述 | `cfg.description` (字符串) | `b.description` (字符串) | 字符串 `!=` |
| 图文图片 | `cfg.images?.map(i => i.id).join(',')` | `b.image_material_ids` JSON 数组 join | 字符串 `!=` |
| 图文封面 | `cfg.coverImage?.id` | `b.image_material_ids[0]` | 字符串 `!=`（兜底） |
| 标签 | `cfg.tags` (数组) | **无对应字段** | **跳过**（`publish_batches` 不存 tags，无法对比） |
| 平台特有字段 (aiContent/isOriginal/...) | `cfg.*` | 无 | 跳过（不存公共值） |

**任一非跳过字段不一致 → `personalized = true`**。

实现位置：`backend/ext_api/__init__.py` 的 `/api/v2/history` handler，在 for-loop 处理 `batches` 时给每个 `items[i]` 注入 `personalized` 字段。建议把比较逻辑抽成独立函数 `_compute_personalized(account_configs, batch_row)` 便于单测。

### 4.4 草稿后端（`backend/app.py` 的 draft 路由）

`POST /api/drafts/save` 和 `GET /api/drafts/{id}` 接受/返回的 JSON 整体打包，新增键 `platformOverrides` / `accountOverrides` / `platformChecked` / `accountChecked` 透传即可。

**前置验证（实施步骤第一步必做）**：
- 实施前先看 `backend/app.py` 的 draft 路由源码，确认：
  1. 入参是否做了 schema 校验（如有，新增键会被静默丢弃 → 需要放开白名单或去掉校验）
  2. 出参是否做了字段过滤（如有，新增键不会返回给前端 → 需要放开）
  3. 数据库列（如 `data TEXT`）是否够大（草稿 JSON 现在变大 2-3 倍，需要确保不是 VARCHAR(255) 之类）
- 验证方式：写一个最小测试脚本 `scripts/verify_draft_passthrough.py`，POST 一个带新键的草稿，再 GET 回来，对比 JSON 一致

**后端代码只在验证发现问题时才动**。

### 4.5 不动的后端文件

- `backend/init_db.py`（表结构不变）
- `backend/app.py` 主体（除 `/postVideo` 新字段透传外）
- `backend/impl/*` 平台实现
- `backend/_browser.py` / `_utils.py` / `conf.py` / `storage.py` / `registry.py`
- `backend/ext_api/task_queue.py` 的 `_update_db` / `_notify_status`（逻辑不变）

## 5. UI：发布历史明细卡片

### 5.1 卡片布局

```
┌───────────────────────────────────────────────────────────────┐
│  ┌─────────┐                                                  │
│  │         │  抖音 · 账号A              ✓ 成功 · 2分10秒  [个性化]│
│  │  封面   │  ────────────────────────────────────────         │
│  │ 缩略图  │  标题：夏日穿搭分享第三期                          │
│  │         │  描述：今天分享三套穿搭...                        │
│  └─────────┘  标签：[#穿搭] [#夏日] [#时尚]                    │
│   16:9                                                   [链接]│
└───────────────────────────────────────────────────────────────┘
```

- 左：16:9 封面缩略图（per-account `coverLandscape` → `coverPortrait` → 批次封面 → 占位）
- 右上：平台 · 账号 + 状态徽标 + 耗时 + 个性化角标（如有）
- 右中：标题（单行截断，长文可点击展开）
- 右中：描述（2 行截断，长文可点击展开）
- 右中：标签（chip 列表）
- 右下：发布链接 `publish_url`（预留字段，发布成功后回填）
- 失败态：标题改为错误信息，封面置灰

### 5.2 样式

参考 `PublishHistory.vue` 现有 `.batch-card` / `.card-cover` / `.card-body` 风格，缩放为子卡片（高度 96px 左右，flex 横向布局，gap 12px）。

### 5.3 收起/展开交互

保持现状：点击批次卡片展开/收起明细区。明细区内每张卡不可点击（仅 [链接] 可点击）。

## 6. 测试计划

### 6.1 后端单测

新增 `backend/tests/test_personalized_config.py`：

1. `test_postvideo_persists_video_landscape_override` — 视频发布时 `task.video_landscape` 写入 `account_configs` JSON
2. `test_postvideo_persists_cover_override` — 视频封面覆写写入
3. `test_image_publish_persists_images_override` — 图文发布图片覆写写入
4. `test_drafts_round_trip_preserves_platform_overrides` — 草稿保存 + 恢复后 `platformOverrides` / `accountOverrides` / `platformChecked` / `accountChecked` 完整
5. `test_history_response_includes_account_configs` — `/api/v2/history` 返回的 `items[].account_configs` 包含新字段

### 6.2 前端 e2e（gstack `/qa` + Playwright）

1. 视频页：勾选平台级 → 改视频文件 → 取消勾选 → 弹确认 → 确认后值清空
2. 视频页：勾选平台级 + 账号级 → 三个层级值互不干扰
3. 图文页：同上
4. 历史页：展开批次 → 每条明细以卡片呈现，显示对应账号实际发布的标题/描述
5. 草稿：保存后关闭页面 → 重新打开 → 平台/账号级覆写数据完整恢复

### 6.3 手工冒烟

- 公共区域 1 套内容，3 账号全用公共 → 历史卡片 3 张都显示相同内容
- 公共区域 1 套内容，3 账号各自覆写 → 历史卡片 3 张内容各异
- 草稿保存 → 关闭 → 重开 → 覆写数据完整

## 7. 风险

| 风险 | 缓解 |
|---|---|
| 公共 + 平台 + 账号三层状态，UI 复杂度高 | 账号级复选框在平台级未勾选时禁用；UI 折叠/展开明示层级 |
| 取消勾选时用户误操作导致数据丢失 | 必须弹确认弹窗，确认后清除 |
| 草稿 JSON 变大（多 2 级覆写） | 草稿表是 JSON 列，无字段长度限制 |
| `account_configs` JSON 字段内容变动，老数据缺新字段 | 渲染时按缺省处理（`?? ''` / `?? []`） |
| 一键填写场景下 platformChecked/accountChecked 状态丢失 | 一键填写不复制个性化勾选状态，行为合理（用户可手动再勾） |
| `task_queue.py` 的 `PublishTask` dataclass 加字段，影响其他调用方 | 新增字段默认 None，向后兼容 |

## 8. 实施步骤（高层）

0. **前置验证**：写 `scripts/verify_draft_passthrough.py`，跑通草稿后端透传新键（按 §4.4）。不通过则改后端
1. `backend/ext_api/task_queue.py`：`PublishTask` 加可选字段，`_insert_db` cfg dict 扩展（含 per-platform form 全字段）
2. `backend/app.py` `/postVideo`：把新字段从 request body 透传到 `task`
3. `backend/blueprints/image_publish_bp.py` `/api/image-publish/publish`：扩 `account_configs` 字段透传
4. `backend/ext_api/__init__.py` `/api/v2/history`：抽 `_compute_personalized()` 函数 + 在 items 里注入 `personalized` 字段
5. `backend/tests/test_personalized_config.py`：新增测试（含 personalized 计算的边界用例）
6. `frontend/src/views/PublishCenter.vue`：state + 模板 + publishAll + saveDraft/loadDraft 改造
7. `frontend/src/views/ImagePublish.vue`：同上
8. `frontend/src/views/PublishHistory.vue`：`.detail-row` → `.detail-card` 卡片化
9. 跑后端单测 + 前端 e2e + 手工冒烟

## 9. 不在范围

- 一键填写感知个性化
- 跨批次覆写继承
- 覆写模板复用
- 平台实现（`backend/impl/*`）
- 登录 / Cookie / 素材库 / 任务中心 / 统计
- 桌面打包（Tauri）
- `mcp__social-auto-upload__*` MCP 工具
