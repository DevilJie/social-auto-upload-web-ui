# 视频发布渠道配置统一化设计

## 背景

视频发布（PublishCenter.vue）和图文发布（ImagePublish.vue）在渠道配置方面存在较大差异：
- 图文发布：每个平台有独立的 `ImagePublishPanel.vue` 组件，使用 `useChannelForm` composable，标签为数组
- 视频发布：所有平台配置内联在 PublishCenter.vue 中，通过 `settingsFields` 动态渲染，标签为字符串

本次改造目标：让视频发布的渠道配置方式向图文发布看齐，不拆分组件，而是在 PublishCenter.vue 内部统一配置模式。

## 改动范围

### 1. 通用字段统一（所有 10 个平台）

**固定 4 个通用字段：** 标题、描述、标签、视频格式

**删除：**
- "添加话题"按钮及话题对话框（第 129-131 行、第 390-424 行）
- "参加活动"按钮（第 133-134 行）
- "添加好友"按钮（第 135-138 行）
- `commonConfig.topics` 状态及相关逻辑
- `addCustomTopic()`、`toggleRecommendedTopic()` 函数
- 推荐话题数据 `recommendedTopics`

**新增：**
- 通用标签输入组件（和图文发布一样的回车添加、去重、删除 UI）
- 每个平台的 `platformConfigs` 新增 `tags: []` 字段
- 批量同步增加标签同步支持

**注意：** B站当前在 `settingsFields` 中有自己的 `tags` 输入字段（`platforms.js` 第 162 行），改造后应从 `settingsFields` 中移除，改用通用标签输入。

### 2. 抖音渠道配置

**复用图文发布现有子组件：**
- `DouyinActivitySelect` — 官方活动（多选，最多 5 个）
- `DouyinHotspotSelect` — 关联热点
- `DouyinTagSelect` — 添加标签（POI/小程序/游戏/商品）
- `DouyinMixSelect` — 合集（账号级别）

**不需要：** `MusicSelect`（视频自带音频）

**移除字段：** `productTitle`、`productLink`、`visibility`、`allowDownload`

**新增状态：** `form.activityId`、`form.hotspotId`、`form.hotspotData`、`form.selectedTag`、`form.tagType`、`form.tagValue`、`form.mixId`、`form.mixData`

### 3. 发布逻辑改造

**前端：**
- tags 从字符串逗号分隔改为数组直接传递
- activities 单独作为数组传递
- 移除 `commonConfig.topics` 相关的 tags 拼接逻辑

**后端（`douyin/platform.py` 的 `publish_video`）：**
- 新增 `activities` 参数处理
- 在 `_fill_title_and_description` 调用前，将 activities 以 `#活动名` 形式拼入 description（和图文发布一致）
- tags 输入方式从 `keyboard.type()` 改为 `keyboard.insert_text()`（和图文发布一致）

### 4. 草稿机制

**数据结构变化：**
```js
// 之前
{
  commonConfig: { topics: [...], videoLandscape, videoPortrait, coverLandscape, coverPortrait },
  platformConfigs: { douyin: { title, description, productTitle, ... }, ... },
}

// 之后
{
  commonConfig: { videoLandscape, videoPortrait, coverLandscape, coverPortrait },
  platformConfigs: {
    douyin: { title, description, tags: [], activityId: [], hotspotId: '', selectedTag: null, mixId: '', ... },
    xiaohongshu: { title, description, tags: [], ... },
    // 每个平台都有 tags: []
  },
}
```

**兼容处理：** 恢复草稿时加迁移函数，将旧格式 `commonConfig.topics` 移到各平台 `tags` 字段。

## 不变的部分

- 左侧 `AccountSidebar`
- 右侧视频预览面板
- `CoverCard`、`CoverEditorDialog`、`MaterialSelectDialog`
- `BatchPublishDialog`
- 视频文件上传和封面管理
- 二级配置管理机制（platformConfigs + accountOverrides）
- 批量同步逻辑（扩展支持标签同步）
