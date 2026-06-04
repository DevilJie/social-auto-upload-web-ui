# 图文发布功能设计文档

## 概述

为社交媒体自动上传工具新增图文发布功能，支持上传最多 35 张图片，批量发布到抖音、快手、小红书等平台。

## 需求背景

1. 左侧菜单"发布中心"更名为"视频发布"
2. 新增"图文发布"菜单，位于视频发布后面
3. 图文发布界面布局参考视频发布，左侧预览区改为跑马灯效果
4. 支持公共配置（图片集合）+ 渠道级/账号级个性化配置（标题、描述）
5. 本次 MVP：完成前端界面 + 模拟发布，暂不对接实际渠道

## 设计方案

### 方案选择

采用**混合方案**：复用布局和通用组件，独立实现图片特有功能。

- 复用：账号侧边栏组件、配置区域框架、样式系统
- 独立实现：图片上传、跑马灯预览、拖拽排序、素材库选择对话框

### 页面布局

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 左侧账号栏 │ 中间配置区 │ 右侧预览区 │
│ 240px │ flex:1 │ 360px │
│ │ │ │
│ 复用现有 │ 公共配置 │ 跑马灯预览 │
│ 账号侧边栏 │ + │ + │
│ (仅显示 │ 个性化配置 │ 点击放大 │
│ 抖音/快手/小红书) │ │ 预览 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 路由配置

- `/publish-center` → `PublishCenter.vue` (更名为"视频发布")
- `/image-publish` → `ImagePublish.vue` (新增"图文发布")

### 菜单顺序

1. 仪表盘
2. 账号管理
3. 素材管理
4. 草稿箱
5. **视频发布** (原"发布中心")
6. **图文发布** (新增，使用 Picture 图标)
7. 发布历史
8. 更新日志
9. 系统设置
10. 关于作者

## 前端设计

### 组件结构

**新建组件**：

| 组件 | 职责 |
|------|------|
| `frontend/src/views/ImagePublish.vue` | 主页面，组合所有子组件 |
| `frontend/src/components/ImageUploader.vue` | 图片上传、拖拽排序、悬停遮罩、进度显示 |
| `frontend/src/components/ImageCarousel.vue` | 跑马灯预览、手动滑动、序号/指示器 |
| `frontend/src/components/ImagePreviewDialog.vue` | 放大预览、缩放、全屏、左右切换 |
| `frontend/src/components/MaterialSelectDialog.vue` | 素材库选择、搜索、筛选 |

**复用组件**：

| 组件 | 说明 |
|------|------|
| `frontend/src/stores/account.js` | 账号状态管理 |
| `frontend/src/stores/app.js` | 应用配置 |
| `frontend/src/config/platforms.js` | 平台配置（需添加图文发布配置） |

### 公共配置区域

**图片上传组件** (`ImageUploader.vue`)：

- 最多上传 35 张图片
- 图片格式：JPG、PNG、WebP，单张最大 20MB
- 展示方式：3:4 小方块，平铺显示，固定 3 排，超出垂直滚动
- 拖拽排序：使用 SortableJS，支持跨行拖动，显示半透明占位符
- 悬停遮罩：显示"删除"、"重新上传"、"素材库选择" 3 个按钮
- 上传方式：支持点击上传 + 拖拽上传 + 批量选择文件
- 上传进度：显示每个文件的进度条，失败时支持重试
- 数量反馈：显示"已上传 X/35 张"，超过 35 张禁用上传按钮
- 图片裁剪：显示时裁剪（CSS `object-fit: cover`），上传时保持原图
- 图片压缩：前端压缩（使用 browser-image-compression）
- 缩略图：前端生成（使用 canvas）

**批量设置标题和描述**：

- 复用视频发布的批量同步功能
- 支持公共标题/描述批量同步到所有渠道

### 右侧预览区

**跑马灯组件** (`ImageCarousel.vue`)：

- 纯手动左右滑动（不自动轮播）
- 显示序号（如 1/35）
- 底部指示器（小圆点）
- 点击图片打开放大预览

**放大预览对话框** (`ImagePreviewDialog.vue`)：

- 支持缩放、全屏、左右切换
- 显示当前图片序号

### 渠道级/账号级个性化配置

每个渠道/账号固定配置：
- 标题（最大 100 字符）
- 描述（最大 2000 字符）

支持批量设置标题和描述，也支持单个渠道覆盖。

### 素材库选择对话框

**MaterialSelectDialog.vue**：

- 弹窗单选替换
- 显示图片预览
- 支持搜索、按类型筛选

## 后端设计

### API Blueprint

新建 `backend/blueprints/image_publish_bp.py`，注册到 Flask 应用。

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/image-publish/upload` | 上传图片 |
| POST | `/api/image-publish/publish` | 发布图文 |
| GET | `/api/image-publish/drafts` | 获取草稿列表 |
| POST | `/api/image-publish/drafts` | 保存草稿 |
| GET | `/api/image-publish/history` | 获取发布历史 |
| GET | `/api/image-publish/files/<path>` | 访问上传的图片 |

### 图片上传接口

```
POST /api/image-publish/upload
Content-Type: multipart/form-data

参数：
- file: 图片文件（JPG/PNG/WebP，最大 20MB）

响应：
{
  "success": true,
  "data": {
    "id": "uuid",
    "url": "/api/image-publish/files/2026/05/28/xxx.jpg",
    "thumbnail": "/api/image-publish/files/2026/05/28/xxx_thumb.jpg",
    "originalName": "photo.jpg",
    "size": 1024000,
    "width": 1080,
    "height": 1440
  }
}
```

### 发布接口

```
POST /api/image-publish/publish
Content-Type: application/json

参数：
{
  "imageIds": ["uuid1", "uuid2", ...],
  "accounts": [
    {
      "accountId": 1,
      "platform": "xiaohongshu",
      "title": "标题",
      "description": "描述"
    }
  ],
  "scheduledAt": "2026-05-28 18:00:00"
}

响应：
{
  "success": true,
  "data": {
    "taskId": "task-uuid",
    "status": "pending"
  }
}
```

### 图片存储

- 存储目录：`data/image-publish/`
- 按日期分组：`data/image-publish/2026/05/28/`
- 缩略图：`xxx_thumb.jpg`

### 格式验证

前后端双重验证：
- 前端：验证文件类型、大小
- 后端：二次验证，防止绕过

## 数据库设计

### 新建表

```sql
-- 图文发布任务表
CREATE TABLE image_publish_tasks (
    id TEXT PRIMARY KEY,
    image_ids TEXT NOT NULL,  -- JSON 数组，存储图片 ID
    account_configs TEXT NOT NULL,  -- JSON 数组，存储账号配置
    status TEXT DEFAULT 'pending',  -- pending/publishing/success/failed
    scheduled_at TEXT,  -- 定时发布时间
    published_at TEXT,  -- 实际发布时间
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- 图文发布日志表
CREATE TABLE image_publish_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    platform TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending/publishing/success/failed
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    published_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (task_id) REFERENCES image_publish_tasks(id)
);

-- 图文草稿表
CREATE TABLE image_drafts (
    id TEXT PRIMARY KEY,
    image_ids TEXT NOT NULL,  -- JSON 数组
    account_configs TEXT NOT NULL,  -- JSON 数组
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### 更新 init_db.py

在 `backend/init_db.py` 中添加上述表的创建语句。

## 状态管理

### 新建 Pinia Store

`frontend/src/stores/imagePublish.js`：

```javascript
// 状态
state: {
  images: [],  // 已上传的图片列表
  selectedAccounts: [],  // 选中的账号
  accountConfigs: {},  // 账号配置（标题、描述）
  currentDraftId: null,  // 当前草稿 ID
  publishing: false,  // 发布中状态
}

// Actions
actions: {
  uploadImage(file) {},  // 上传图片
  removeImage(imageId) {},  // 删除图片
  reorderImages(fromIndex, toIndex) {},  // 重新排序
  saveDraft() {},  // 保存草稿
  loadDraft(draftId) {},  // 加载草稿
  publish(scheduledAt) {},  // 发布
}
```

## 样式设计

### 复用现有样式

- 布局样式：`.publish-center`、`.account-sidebar`、`.publish-main`
- 配置区域：`.config-section`、`.section-bar`、`.setting-card`
- 按钮样式：`.cover-action-btn`、`.publish-btn`、`.draft-btn`

### 新增样式

```css
/* 图片网格布局 */
.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  max-height: calc(3 * (120px * 4/3 + 12px)); /* 固定 3 排 */
  overflow-y: auto;
}

.image-item {
  aspect-ratio: 3/4;
  object-fit: cover;
  border-radius: 8px;
  cursor: pointer;
}

/* 悬停遮罩 */
.image-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.image-item:hover .image-overlay {
  opacity: 1;
}

/* 跑马灯 */
.image-carousel {
  position: relative;
  overflow: hidden;
}

.carousel-track {
  display: flex;
  transition: transform 0.3s ease;
}

/* 拖拽占位符 */
.drag-placeholder {
  border: 2px dashed var(--el-color-primary);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}
```

## 依赖

### 前端依赖

- `sortablejs` / `vue.draggable.next` — 拖拽排序
- `browser-image-compression` — 图片压缩

### 后端依赖

- `Pillow` — 图片处理（缩略图生成）

## 测试策略

本次 MVP 测试范围：
- 前端界面功能正常
- 图片上传、删除、排序功能正常
- 草稿保存/加载功能正常
- 模拟发布功能正常

暂不测试：
- 实际渠道对接
- 实际发布流程

## 后续迭代

1. 对接抖音、快手、小红书渠道
2. 实现实际发布流程
3. 添加发布状态实时更新
4. 优化图片压缩算法
5. 添加图片编辑功能（裁剪、滤镜）
