# 图文发布功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [`) syntax for tracking.

**Goal:** 为社交媒体自动上传工具新增图文发布功能，支持上传最多 35 张图片，批量发布到抖音、快手、小红书等平台。

**Architecture:** 采用混合方案，复用视频发布的布局和通用组件，独立实现图片上传、跑马灯预览、拖拽排序等特有功能。前端使用 Vue 3 + Element Plus + Pinia，后端使用 Flask + SQLite。

**Tech Stack:** Vue 3, Element Plus, Pinia, SortableJS, browser-image-compression, Flask, SQLite, Pillow

---

## 文件结构

### 新建文件

| 文件路径 | 职责 |
|----------|------|
| `frontend/src/views/ImagePublish.vue` | 图文发布主页面 |
| `frontend/src/components/ImageUploader.vue` | 图片上传组件 |
| `frontend/src/components/ImageCarousel.vue` | 跑马灯预览组件 |
| `frontend/src/components/ImagePreviewDialog.vue` | 放大预览对话框 |
| `frontend/src/components/MaterialSelectDialog.vue` | 素材库选择对话框 |
| `frontend/src/stores/imagePublish.js` | 图文发布状态管理 |
| `frontend/src/api/imagePublish.js` | 图文发布 API 接口 |
| `backend/blueprints/image_publish_bp.py` | 图文发布后端 Blueprint |

### 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `frontend/src/router/index.js` | 添加图文发布路由，更新菜单标题 |
| `frontend/src/config/platforms.js` | 添加图文发布平台配置 |
| `backend/app.py` | 注册图文发布 Blueprint |
| `backend/init_db.py` | 添加图文发布相关表 |
| `frontend/package.json` | 添加 sortablejs、browser-image-compression 依赖 |
| `backend/requirements.txt` | 添加 Pillow 依赖 |

---

## Task 1: 菜单和路由配置

**Files:**
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/config/platforms.js`

- [ ] **Step 1: 更新路由配置**

```javascript
// frontend/src/router/index.js
import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import AccountManagement from '../views/AccountManagement.vue'
import MaterialManagement from '../views/MaterialManagement.vue'
import PublishCenter from '../views/PublishCenter.vue'
import PublishHistory from '../views/PublishHistory.vue'
import Settings from '../views/Settings.vue'
import Author from '../views/Author.vue'

const routes = [
  { path: '/', name: 'Dashboard', component: Dashboard, meta: { icon: 'HomeFilled', title: '仪表盘' } },
  { path: '/account-management', name: 'AccountManagement', component: AccountManagement, meta: { icon: 'User', title: '账号管理' } },
  { path: '/material-management', name: 'MaterialManagement', component: MaterialManagement, meta: { icon: 'Picture', title: '素材管理' } },
  { path: '/drafts', name: 'DraftBox', component: () => import('../views/DraftBox.vue'), meta: { icon: 'Document', title: '草稿箱' } },
  { path: '/publish-center', name: 'PublishCenter', component: PublishCenter, meta: { icon: 'Upload', title: '视频发布' } },
  { path: '/image-publish', name: 'ImagePublish', component: () => import('../views/ImagePublish.vue'), meta: { icon: 'Picture', title: '图文发布' } },
  { path: '/publish-history', name: 'PublishHistory', component: PublishHistory, meta: { icon: 'Clock', title: '发布历史' } },
  { path: '/changelog', name: 'Changelog', component: () => import('../views/Changelog.vue'), meta: { icon: 'Notebook', title: '更新日志' } },
  { path: '/settings', name: 'Settings', component: Settings, meta: { icon: 'Setting', title: '系统设置', isBottom: true } },
  { path: '/author', name: 'Author', component: Author, meta: { icon: 'UserFilled', title: '关于作者', isBottom: true } }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router
```

- [ ] **Step 2: 验证路由配置**

运行前端开发服务器，检查菜单显示：
```bash
cd frontend && npm run dev
```

访问 http://localhost:5173，验证：
- "发布中心"已更名为"视频发布"
- 新增"图文发布"菜单，位于视频发布后面
- 点击图文发布菜单可以正常跳转

- [ ] **Step 3: 提交代码**

```bash
git add frontend/src/router/index.js
git commit -m "feat: 添加图文发布路由，更新菜单标题"
```

---

## Task 2: 后端数据库初始化

**Files:**
- Modify: `backend/init_db.py`

- [ ] **Step 1: 添加图文发布相关表**

```python
# backend/init_db.py
# 在现有表创建语句后添加

# 图文发布任务表
cursor.execute('''
    CREATE TABLE IF NOT EXISTS image_publish_tasks (
        id TEXT PRIMARY KEY,
        image_ids TEXT NOT NULL,
        account_configs TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        scheduled_at TEXT,
        published_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
''')

# 图文发布日志表
cursor.execute('''
    CREATE TABLE IF NOT EXISTS image_publish_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL,
        account_id INTEGER NOT NULL,
        platform TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        published_at TEXT,
        created_at TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (task_id) REFERENCES image_publish_tasks(id)
    )
''')

# 图文草稿表
cursor.execute('''
    CREATE TABLE IF NOT EXISTS image_drafts (
        id TEXT PRIMARY KEY,
        image_ids TEXT NOT NULL,
        account_configs TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    )
''')
```

- [ ] **Step 2: 运行数据库初始化**

```bash
python backend/init_db.py
```

验证表已创建：
```bash
sqlite3 data/db/database.db ".tables"
```

应该看到新增的表：`image_publish_tasks`、`image_publish_logs`、`image_drafts`

- [ ] **Step 3: 提交代码**

```bash
git add backend/init_db.py
git commit -m "feat: 添加图文发布相关数据库表"
```

---

## Task 3: 后端 API Blueprint

**Files:**
- Create: `backend/blueprints/image_publish_bp.py`
- Modify: `backend/app.py`

- [ ] **Step 1: 创建图文发布 Blueprint**

```python
# backend/blueprints/image_publish_bp.py
import os
import uuid
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
import sqlite3

image_publish_bp = Blueprint('image_publish', __name__)

# 配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'image-publish')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'db', 'database.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

@image_publish_bp.route('/api/image-publish/upload', methods=['POST'])
def upload_image():
    """上传图片"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '没有文件'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '没有选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': '不支持的文件格式'}), 400
    
    # 检查文件大小
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)
    
    if file_size > MAX_FILE_SIZE:
        return jsonify({'success': False, 'error': '文件大小超过限制'}), 400
    
    # 生成唯一文件名
    file_id = str(uuid.uuid4())
    ext = file.filename.rsplit('.', 1)[1].lower()
    filename = f"{file_id}.{ext}"
    
    # 按日期创建目录
    today = datetime.now().strftime('%Y/%m/%d')
    upload_dir = os.path.join(UPLOAD_FOLDER, today)
    os.makedirs(upload_dir, exist_ok=True)
    
    # 保存原图
    filepath = os.path.join(upload_dir, filename)
    file.save(filepath)
    
    # 生成缩略图
    try:
        with Image.open(filepath) as img:
            width, height = img.size
            # 生成缩略图
            thumb_filename = f"{file_id}_thumb.{ext}"
            thumb_path = os.path.join(upload_dir, thumb_filename)
            img.thumbnail((300, 400))
            img.save(thumb_path)
    except Exception as e:
        width, height = 0, 0
        thumb_filename = filename
    
    # 返回结果
    url = f"/api/image-publish/files/{today}/{filename}"
    thumbnail = f"/api/image-publish/files/{today}/{thumb_filename}"
    
    return jsonify({
        'success': True,
        'data': {
            'id': file_id,
            'url': url,
            'thumbnail': thumbnail,
            'originalName': file.filename,
            'size': file_size,
            'width': width,
            'height': height
        }
    })

@image_publish_bp.route('/api/image-publish/files/<path:filepath>')
def serve_file(filepath):
    """提供上传的图片访问"""
    return send_from_directory(UPLOAD_FOLDER, filepath)

@image_publish_bp.route('/api/image-publish/publish', methods=['POST'])
def publish():
    """发布图文（模拟）"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    image_ids = data.get('imageIds', [])
    accounts = data.get('accounts', [])
    scheduled_at = data.get('scheduledAt')
    
    if not image_ids:
        return jsonify({'success': False, 'error': '请至少上传一张图片'}), 400
    
    if not accounts:
        return jsonify({'success': False, 'error': '请选择至少一个账号'}), 400
    
    # 生成任务 ID
    task_id = str(uuid.uuid4())
    
    # 保存到数据库
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO image_publish_tasks (id, image_ids, account_configs, status, scheduled_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            task_id,
            json.dumps(image_ids),
            json.dumps(accounts),
            'pending' if not scheduled_at else 'scheduled',
            scheduled_at
        ))
        
        # 为每个账号创建日志
        for account in accounts:
            cursor.execute('''
                INSERT INTO image_publish_logs (task_id, account_id, platform, status)
                VALUES (?, ?, ?, ?)
            ''', (task_id, account['accountId'], account['platform'], 'pending'))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
    
    return jsonify({
        'success': True,
        'data': {
            'taskId': task_id,
            'status': 'pending' if not scheduled_at else 'scheduled'
        }
    })

@image_publish_bp.route('/api/image-publish/drafts', methods=['GET'])
def get_drafts():
    """获取草稿列表"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT * FROM image_drafts ORDER BY updated_at DESC')
        drafts = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': [dict(draft) for draft in drafts]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@image_publish_bp.route('/api/image-publish/drafts', methods=['POST'])
def save_draft():
    """保存草稿"""
    data = request.get_json()
    
    if not data:
        return jsonify({'success': False, 'error': '无效的请求数据'}), 400
    
    draft_id = data.get('id') or str(uuid.uuid4())
    image_ids = data.get('imageIds', [])
    account_configs = data.get('accountConfigs', {})
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO image_drafts (id, image_ids, account_configs, updated_at)
            VALUES (?, ?, ?, datetime('now'))
        ''', (draft_id, json.dumps(image_ids), json.dumps(account_configs)))
        
        conn.commit()
        
        return jsonify({
            'success': True,
            'data': {
                'id': draft_id
            }
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()

@image_publish_bp.route('/api/image-publish/history', methods=['GET'])
def get_history():
    """获取发布历史"""
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            SELECT t.*, GROUP_CONCAT(l.platform) as platforms
            FROM image_publish_tasks t
            LEFT JOIN image_publish_logs l ON t.id = l.task_id
            GROUP BY t.id
            ORDER BY t.created_at DESC
        ''')
        history = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'data': [dict(item) for item in history]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
    finally:
        conn.close()
```

- [ ] **Step 2: 注册 Blueprint 到 Flask 应用**

```python
# backend/app.py
# 在现有 Blueprint 导入后添加
from blueprints.image_publish_bp import image_publish_bp

# 在 register_blueprint 部分添加
app.register_blueprint(image_publish_bp)
```

- [ ] **Step 3: 创建上传目录**

```bash
mkdir -p data/image-publish
```

- [ ] **Step 4: 测试上传接口**

```bash
# 测试图片上传
curl -X POST -F "file=@test.jpg" http://localhost:5409/api/image-publish/upload
```

- [ ] **Step 5: 提交代码**

```bash
git add backend/blueprints/image_publish_bp.py backend/app.py
git commit -m "feat: 添加图文发布后端 API"
```

---

## Task 4: 前端 API 接口

**Files:**
- Create: `frontend/src/api/imagePublish.js`

- [ ] **Step 1: 创建图文发布 API 接口**

```javascript
// frontend/src/api/imagePublish.js
import request from '../utils/request'

/**
 * 上传图片
 * @param {File} file - 图片文件
 * @param {Function} onProgress - 进度回调
 * @returns {Promise}
 */
export function uploadImage(file, onProgress) {
  const formData = new FormData()
  formData.append('file', file)
  
  return request({
    url: '/api/image-publish/upload',
    method: 'post',
    data: formData,
    headers: {
      'Content-Type': 'multipart/form-data'
    },
    onUploadProgress: (progressEvent) => {
      if (onProgress) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    }
  })
}

/**
 * 发布图文
 * @param {Object} data - 发布数据
 * @returns {Promise}
 */
export function publishImage(data) {
  return request({
    url: '/api/image-publish/publish',
    method: 'post',
    data
  })
}

/**
 * 获取草稿列表
 * @returns {Promise}
 */
export function getDrafts() {
  return request({
    url: '/api/image-publish/drafts',
    method: 'get'
  })
}

/**
 * 保存草稿
 * @param {Object} data - 草稿数据
 * @returns {Promise}
 */
export function saveDraft(data) {
  return request({
    url: '/api/image-publish/drafts',
    method: 'post',
    data
  })
}

/**
 * 获取发布历史
 * @returns {Promise}
 */
export function getHistory() {
  return request({
    url: '/api/image-publish/history',
    method: 'get'
  })
}
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/api/imagePublish.js
git commit -m "feat: 添加图文发布前端 API 接口"
```

---

## Task 5: 前端状态管理

**Files:**
- Create: `frontend/src/stores/imagePublish.js`

- [ ] **Step 1: 创建图文发布状态管理**

```javascript
// frontend/src/stores/imagePublish.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { uploadImage, publishImage, saveDraft } from '../api/imagePublish'

export const useImagePublishStore = defineStore('imagePublish', () => {
  // 状态
  const images = ref([])
  const selectedAccounts = ref([])
  const accountConfigs = ref({})
  const currentDraftId = ref(null)
  const publishing = ref(false)
  const batchTitle = ref('')
  const batchDescription = ref('')

  // 计算属性
  const imageCount = computed(() => images.value.length)
  const canUpload = computed(() => images.value.length < 35)
  const canPublish = computed(() => images.value.length > 0 && selectedAccounts.value.length > 0)

  // 上传图片
  async function upload(file) {
    if (!canUpload.value) {
      throw new Error('最多上传 35 张图片')
    }

    const imageInfo = {
      id: null,
      file,
      url: null,
      thumbnail: null,
      originalName: file.name,
      size: file.size,
      uploading: true,
      progress: 0,
      error: null
    }

    images.value.push(imageInfo)
    const index = images.value.length - 1

    try {
      const response = await uploadImage(file, (progress) => {
        images.value[index].progress = progress
      })

      if (response.success) {
        images.value[index] = {
          ...images.value[index],
          ...response.data,
          uploading: false
        }
      } else {
        throw new Error(response.error)
      }
    } catch (error) {
      images.value[index].uploading = false
      images.value[index].error = error.message
      throw error
    }
  }

  // 删除图片
  function removeImage(index) {
    images.value.splice(index, 1)
  }

  // 重新排序
  function reorder(fromIndex, toIndex) {
    const item = images.value.splice(fromIndex, 1)[0]
    images.value.splice(toIndex, 0, item)
  }

  // 替换图片
  async function replaceImage(index, file) {
    const oldImage = images.value[index]
    
    try {
      const response = await uploadImage(file, (progress) => {
        images.value[index].progress = progress
        images.value[index].uploading = true
      })

      if (response.success) {
        images.value[index] = {
          ...response.data,
          uploading: false,
          progress: 100,
          error: null
        }
      } else {
        throw new Error(response.error)
      }
    } catch (error) {
      images.value[index].uploading = false
      images.value[index].error = error.message
      throw error
    }
  }

  // 更新账号配置
  function updateAccountConfig(accountId, config) {
    accountConfigs.value[accountId] = {
      ...accountConfigs.value[accountId],
      ...config
    }
  }

  // 批量同步标题和描述
  function syncBatchToAll() {
    selectedAccounts.value.forEach(accountId => {
      updateAccountConfig(accountId, {
        title: batchTitle.value,
        description: batchDescription.value
      })
    })
  }

  // 保存草稿
  async function save() {
    try {
      const response = await saveDraft({
        id: currentDraftId.value,
        imageIds: images.value.map(img => img.id),
        accountConfigs: accountConfigs.value
      })

      if (response.success) {
        currentDraftId.value = response.data.id
      }

      return response
    } catch (error) {
      throw error
    }
  }

  // 发布
  async function publish(scheduledAt = null) {
    if (!canPublish.value) {
      throw new Error('请上传图片并选择账号')
    }

    publishing.value = true

    try {
      const accounts = selectedAccounts.value.map(accountId => ({
        accountId,
        platform: getPlatformByAccountId(accountId),
        title: accountConfigs.value[accountId]?.title || '',
        description: accountConfigs.value[accountId]?.description || ''
      }))

      const response = await publishImage({
        imageIds: images.value.map(img => img.id),
        accounts,
        scheduledAt
      })

      return response
    } catch (error) {
      throw error
    } finally {
      publishing.value = false
    }
  }

  // 辅助函数：根据账号 ID 获取平台
  function getPlatformByAccountId(accountId) {
    // 这里需要从 account store 获取
    // 暂时返回空字符串
    return ''
  }

  return {
    // 状态
    images,
    selectedAccounts,
    accountConfigs,
    currentDraftId,
    publishing,
    batchTitle,
    batchDescription,
    
    // 计算属性
    imageCount,
    canUpload,
    canPublish,
    
    // 方法
    upload,
    removeImage,
    reorder,
    replaceImage,
    updateAccountConfig,
    syncBatchToAll,
    save,
    publish
  }
})
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/stores/imagePublish.js
git commit -m "feat: 添加图文发布状态管理"
```

---

## Task 6: 图片上传组件

**Files:**
- Create: `frontend/src/components/ImageUploader.vue`

- [ ] **Step 1: 创建图片上传组件**

```vue
<!-- frontend/src/components/ImageUploader.vue -->
<template>
  <div class="image-uploader">
    <div class="uploader-header">
      <span class="uploader-title">图片集合</span>
      <span class="uploader-count">已上传 {{ images.length }}/35 张</span>
    </div>
    
    <div class="image-grid" ref="gridRef">
      <div
        v-for="(image, index) in images"
        :key="image.id || index"
        class="image-item"
        :class="{ 'is-uploading': image.uploading, 'is-error': image.error }"
      >
        <img
          :src="image.thumbnail || image.url"
          :alt="image.originalName"
          class="image-thumb"
        />
        
        <!-- 上传进度 -->
        <div v-if="image.uploading" class="upload-progress">
          <el-progress
            :percentage="image.progress"
            :stroke-width="4"
            :show-text="false"
          />
          <span class="progress-text">{{ image.progress }}%</span>
        </div>
        
        <!-- 错误状态 -->
        <div v-if="image.error" class="upload-error">
          <el-icon><WarningFilled /></el-icon>
          <span>{{ image.error }}</span>
          <el-button size="small" @click="retryUpload(index)">重试</el-button>
        </div>
        
        <!-- 悬停遮罩 -->
        <div class="image-overlay">
          <el-icon class="overlay-icon" @click="handleReupload(index)"><Upload /></el-icon>
          <el-icon class="overlay-icon" @click="handleSelectFromLibrary(index)"><Picture /></el-icon>
          <el-icon class="overlay-icon" @click="handleDelete(index)"><Delete /></el-icon>
        </div>
        
        <!-- 序号 -->
        <span class="image-index">{{ index + 1 }}</span>
      </div>
      
      <!-- 上传按钮 -->
      <div
        v-if="canUpload"
        class="upload-trigger"
        @click="triggerUpload"
        @dragover.prevent
        @drop.prevent="handleDrop"
      >
        <el-icon><Plus /></el-icon>
        <span>上传图片</span>
      </div>
    </div>
    
    <!-- 隐藏的文件输入 -->
    <input
      ref="fileInputRef"
      type="file"
      accept="image/jpeg,image/png,image/webp"
      multiple
      style="display: none"
      @change="handleFileSelect"
    />
    
    <!-- 素材库选择对话框 -->
    <MaterialSelectDialog
      v-model:visible="materialDialogVisible"
      @select="handleMaterialSelect"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Plus, Upload, Picture, Delete, WarningFilled } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import { useImagePublishStore } from '../stores/imagePublish'
import MaterialSelectDialog from './MaterialSelectDialog.vue'

const store = useImagePublishStore()
const { images, canUpload } = store

const gridRef = ref(null)
const fileInputRef = ref(null)
const materialDialogVisible = ref(false)
const currentReplaceIndex = ref(null)

let sortable = null

onMounted(() => {
  initSortable()
})

onUnmounted(() => {
  if (sortable) {
    sortable.destroy()
  }
})

function initSortable() {
  if (!gridRef.value) return
  
  sortable = Sortable.create(gridRef.value, {
    animation: 150,
    ghostClass: 'drag-placeholder',
    onEnd(evt) {
      store.reorder(evt.oldIndex, evt.newIndex)
    }
  })
}

function triggerUpload() {
  fileInputRef.value.click()
}

function handleFileSelect(event) {
  const files = Array.from(event.target.files)
  uploadFiles(files)
  event.target.value = ''
}

function handleDrop(event) {
  const files = Array.from(event.dataTransfer.files)
  uploadFiles(files)
}

async function uploadFiles(files) {
  for (const file of files) {
    // 验证文件格式
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      ElMessage.error('不支持的文件格式')
      continue
    }
    
    // 验证文件大小
    if (file.size > 20 * 1024 * 1024) {
      ElMessage.error('文件大小超过限制')
      continue
    }
    
    try {
      await store.upload(file)
    } catch (error) {
      ElMessage.error(error.message)
    }
  }
}

async function handleReupload(index) {
  currentReplaceIndex.value = index
  fileInputRef.value.click()
}

function handleSelectFromLibrary(index) {
  currentReplaceIndex.value = index
  materialDialogVisible.value = true
}

async function handleDelete(index) {
  try {
    await ElMessageBox.confirm('确定删除这张图片吗？', '确认删除', {
      type: 'warning'
    })
    store.removeImage(index)
  } catch {
    // 取消删除
  }
}

async function retryUpload(index) {
  const image = images.value[index]
  if (image.file) {
    await store.replaceImage(index, image.file)
  }
}

function handleMaterialSelect(material) {
  if (currentReplaceIndex.value !== null) {
    // 替换图片
    store.replaceImage(currentReplaceIndex.value, material.file)
    currentReplaceIndex.value = null
  }
}
</script>

<style scoped>
.image-uploader {
  margin-bottom: 20px;
}

.uploader-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.uploader-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.uploader-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.image-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
  max-height: calc(3 * (120px * 4/3 + 12px));
  overflow-y: auto;
  padding: 4px;
}

.image-item {
  position: relative;
  aspect-ratio: 3/4;
  border-radius: 8px;
  overflow: hidden;
  background: var(--el-fill-color-light);
}

.image-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.upload-progress {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 8px;
  background: rgba(0, 0, 0, 0.5);
}

.progress-text {
  font-size: 12px;
  color: white;
  text-align: center;
  display: block;
  margin-top: 4px;
}

.upload-error {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  font-size: 12px;
  gap: 8px;
}

.image-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  background: rgba(0, 0, 0, 0.5);
  opacity: 0;
  transition: opacity 0.2s;
}

.image-item:hover .image-overlay {
  opacity: 1;
}

.overlay-icon {
  font-size: 20px;
  color: white;
  cursor: pointer;
  padding: 8px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.3);
  transition: background 0.2s;
}

.overlay-icon:hover {
  background: rgba(0, 0, 0, 0.5);
}

.image-index {
  position: absolute;
  top: 4px;
  left: 4px;
  font-size: 12px;
  color: white;
  background: rgba(0, 0, 0, 0.5);
  padding: 2px 6px;
  border-radius: 4px;
}

.upload-trigger {
  aspect-ratio: 3/4;
  border: 2px dashed var(--el-border-color);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.upload-trigger:hover {
  border-color: var(--el-color-primary);
}

.upload-trigger .el-icon {
  font-size: 24px;
  color: var(--el-text-color-secondary);
}

.upload-trigger span {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.drag-placeholder {
  border: 2px dashed var(--el-color-primary);
  border-radius: 8px;
  background: var(--el-color-primary-light-9);
}
</style>
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/components/ImageUploader.vue
git commit -m "feat: 添加图片上传组件"
```

---

## Task 7: 跑马灯预览组件

**Files:**
- Create: `frontend/src/components/ImageCarousel.vue`

- [ ] **Step 1: 创建跑马灯预览组件**

```vue
<!-- frontend/src/components/ImageCarousel.vue -->
<template>
  <div class="image-carousel">
    <div class="carousel-header">
      <span class="carousel-title">图片预览</span>
      <span class="carousel-index">{{ currentIndex + 1 }}/{{ images.length }}</span>
    </div>
    
    <div class="carousel-body">
      <div
        class="carousel-track"
        ref="trackRef"
        @touchstart="handleTouchStart"
        @touchmove="handleTouchMove"
        @touchend="handleTouchEnd"
        @mousedown="handleMouseDown"
        @mousemove="handleMouseMove"
        @mouseup="handleMouseUp"
        @mouseleave="handleMouseUp"
      >
        <div
          v-for="(image, index) in images"
          :key="image.id || index"
          class="carousel-slide"
          :style="{ transform: `translateX(${(index - currentIndex) * 100}%)` }"
          @click="handleImageClick(index)"
        >
          <img
            :src="image.url || image.thumbnail"
            :alt="image.originalName"
            class="carousel-image"
          />
        </div>
      </div>
      
      <!-- 左右箭头 -->
      <button
        v-if="currentIndex > 0"
        class="carousel-arrow carousel-arrow-left"
        @click="prev"
      >
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <button
        v-if="currentIndex < images.length - 1"
        class="carousel-arrow carousel-arrow-right"
        @click="next"
      >
        <el-icon><ArrowRight /></el-icon>
      </button>
    </div>
    
    <!-- 底部指示器 -->
    <div class="carousel-dots">
      <span
        v-for="(image, index) in images"
        :key="index"
        class="carousel-dot"
        :class="{ active: index === currentIndex }"
        @click="goTo(index)"
      ></span>
    </div>
    
    <!-- 放大预览对话框 -->
    <ImagePreviewDialog
      v-model:visible="previewVisible"
      :images="images"
      :initial-index="currentIndex"
      @update:index="currentIndex = $event"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import ImagePreviewDialog from './ImagePreviewDialog.vue'

const props = defineProps({
  images: {
    type: Array,
    default: () => []
  }
})

const currentIndex = ref(0)
const previewVisible = ref(false)
const trackRef = ref(null)

// 触摸/鼠标状态
let startX = 0
let startY = 0
let isDragging = false
let startTime = 0

// 监听 images 变化，重置索引
watch(() => props.images.length, (newLength) => {
  if (newLength === 0) {
    currentIndex.value = 0
  } else if (currentIndex.value >= newLength) {
    currentIndex.value = newLength - 1
  }
})

function prev() {
  if (currentIndex.value > 0) {
    currentIndex.value--
  }
}

function next() {
  if (currentIndex.value < props.images.length - 1) {
    currentIndex.value++
  }
}

function goTo(index) {
  currentIndex.value = index
}

function handleImageClick(index) {
  // 如果不是拖拽，则打开预览
  if (!isDragging) {
    currentIndex.value = index
    previewVisible.value = true
  }
}

// 触摸事件
function handleTouchStart(e) {
  startX = e.touches[0].clientX
  startY = e.touches[0].clientY
  startTime = Date.now()
  isDragging = false
}

function handleTouchMove(e) {
  const currentX = e.touches[0].clientX
  const currentY = e.touches[0].clientY
  const diffX = currentX - startX
  const diffY = currentY - startY
  
  // 判断是否为水平滑动
  if (Math.abs(diffX) > Math.abs(diffY) && Math.abs(diffX) > 10) {
    isDragging = true
    e.preventDefault()
  }
}

function handleTouchEnd(e) {
  const endX = e.changedTouches[0].clientX
  const diffX = endX - startX
  const duration = Date.now() - startTime
  
  // 快速滑动或滑动距离足够
  if ((duration < 300 && Math.abs(diffX) > 30) || Math.abs(diffX) > 100) {
    if (diffX > 0) {
      prev()
    } else {
      next()
    }
  }
  
  setTimeout(() => {
    isDragging = false
  }, 10)
}

// 鼠标事件
function handleMouseDown(e) {
  startX = e.clientX
  startY = e.clientY
  startTime = Date.now()
  isDragging = false
}

function handleMouseMove(e) {
  if (e.buttons === 0) return
  
  const currentX = e.clientX
  const diffX = currentX - startX
  
  if (Math.abs(diffX) > 10) {
    isDragging = true
  }
}

function handleMouseUp(e) {
  if (!isDragging) return
  
  const endX = e.clientX
  const diffX = endX - startX
  
  if (Math.abs(diffX) > 50) {
    if (diffX > 0) {
      prev()
    } else {
      next()
    }
  }
  
  setTimeout(() => {
    isDragging = false
  }, 10)
}
</script>

<style scoped>
.image-carousel {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.carousel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.carousel-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--el-text-color-primary);
}

.carousel-index {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.carousel-body {
  position: relative;
  flex: 1;
  overflow: hidden;
}

.carousel-track {
  display: flex;
  height: 100%;
  cursor: grab;
}

.carousel-track:active {
  cursor: grabbing;
}

.carousel-slide {
  flex-shrink: 0;
  width: 100%;
  height: 100%;
  transition: transform 0.3s ease;
}

.carousel-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
  -webkit-user-drag: none;
}

.carousel-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
  z-index: 10;
}

.carousel-arrow:hover {
  background: rgba(0, 0, 0, 0.7);
}

.carousel-arrow-left {
  left: 8px;
}

.carousel-arrow-right {
  right: 8px;
}

.carousel-dots {
  display: flex;
  justify-content: center;
  gap: 8px;
  padding: 12px;
}

.carousel-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--el-border-color);
  cursor: pointer;
  transition: all 0.2s;
}

.carousel-dot.active {
  background: var(--el-color-primary);
  transform: scale(1.2);
}
</style>
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/components/ImageCarousel.vue
git commit -m "feat: 添加跑马灯预览组件"
```

---

## Task 8: 放大预览对话框

**Files:**
- Create: `frontend/src/components/ImagePreviewDialog.vue`

- [ ] **Step 1: 创建放大预览对话框**

```vue
<!-- frontend/src/components/ImagePreviewDialog.vue -->
<template>
  <el-dialog
    v-model="visible"
    :show-close="false"
    :close-on-click-modal="true"
    class="image-preview-dialog"
    @close="handleClose"
  >
    <div class="preview-container">
      <!-- 图片 -->
      <div class="preview-image-wrapper">
        <img
          :src="currentImage?.url || currentImage?.thumbnail"
          :alt="currentImage?.originalName"
          class="preview-image"
          :style="{ transform: `scale(${scale}) rotate(${rotate}deg)` }"
          @wheel.prevent="handleWheel"
        />
      </div>
      
      <!-- 工具栏 -->
      <div class="preview-toolbar">
        <el-icon class="toolbar-icon" @click="zoomOut"><ZoomOut /></el-icon>
        <span class="toolbar-text">{{ Math.round(scale * 100) }}%</span>
        <el-icon class="toolbar-icon" @click="zoomIn"><ZoomIn /></el-icon>
        <el-icon class="toolbar-icon" @click="rotateLeft"><RefreshLeft /></el-icon>
        <el-icon class="toolbar-icon" @click="rotateRight"><RefreshRight /></el-icon>
        <el-icon class="toolbar-icon" @click="toggleFullscreen"><FullScreen /></el-icon>
      </div>
      
      <!-- 左右箭头 -->
      <button
        v-if="currentIndex > 0"
        class="preview-arrow preview-arrow-left"
        @click="prev"
      >
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <button
        v-if="currentIndex < images.length - 1"
        class="preview-arrow preview-arrow-right"
        @click="next"
      >
        <el-icon><ArrowRight /></el-icon>
      </button>
      
      <!-- 序号 -->
      <div class="preview-index">
        {{ currentIndex + 1 }} / {{ images.length }}
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import {
  ZoomOut, ZoomIn, RefreshLeft, RefreshRight, FullScreen,
  ArrowLeft, ArrowRight
} from '@element-plus/icons-vue'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  },
  images: {
    type: Array,
    default: () => []
  },
  initialIndex: {
    type: Number,
    default: 0
  }
})

const emit = defineEmits(['update:visible', 'update:index'])

const currentIndex = ref(props.initialIndex)
const scale = ref(1)
const rotate = ref(0)

const currentImage = computed(() => props.images[currentIndex.value])

watch(() => props.visible, (newVal) => {
  if (newVal) {
    currentIndex.value = props.initialIndex
    scale.value = 1
    rotate.value = 0
  }
})

watch(() => props.initialIndex, (newVal) => {
  currentIndex.value = newVal
})

function handleClose() {
  emit('update:visible', false)
}

function prev() {
  if (currentIndex.value > 0) {
    currentIndex.value--
    emit('update:index', currentIndex.value)
    resetTransform()
  }
}

function next() {
  if (currentIndex.value < props.images.length - 1) {
    currentIndex.value++
    emit('update:index', currentIndex.value)
    resetTransform()
  }
}

function zoomIn() {
  if (scale.value < 3) {
    scale.value = Math.min(3, scale.value + 0.25)
  }
}

function zoomOut() {
  if (scale.value > 0.5) {
    scale.value = Math.max(0.5, scale.value - 0.25)
  }
}

function rotateLeft() {
  rotate.value -= 90
}

function rotateRight() {
  rotate.value += 90
}

function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen()
  } else {
    document.exitFullscreen()
  }
}

function handleWheel(e) {
  if (e.deltaY < 0) {
    zoomIn()
  } else {
    zoomOut()
  }
}

function resetTransform() {
  scale.value = 1
  rotate.value = 0
}
</script>

<style scoped>
.image-preview-dialog {
  :deep(.el-dialog) {
    background: transparent;
    box-shadow: none;
    max-width: 90vw;
    max-height: 90vh;
    margin: 0;
  }
  
  :deep(.el-dialog__header) {
    display: none;
  }
  
  :deep(.el-dialog__body) {
    padding: 0;
  }
}

.preview-container {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}

.preview-image-wrapper {
  max-width: 80vw;
  max-height: 80vh;
  overflow: hidden;
}

.preview-image {
  max-width: 100%;
  max-height: 80vh;
  object-fit: contain;
  transition: transform 0.2s ease;
  user-select: none;
}

.preview-toolbar {
  position: absolute;
  bottom: 20px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 16px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 8px;
}

.toolbar-icon {
  font-size: 20px;
  color: white;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background 0.2s;
}

.toolbar-icon:hover {
  background: rgba(255, 255, 255, 0.2);
}

.toolbar-text {
  font-size: 14px;
  color: white;
  min-width: 40px;
  text-align: center;
}

.preview-arrow {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.5);
  color: white;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s;
}

.preview-arrow:hover {
  background: rgba(0, 0, 0, 0.7);
}

.preview-arrow-left {
  left: 20px;
}

.preview-arrow-right {
  right: 20px;
}

.preview-index {
  position: absolute;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  padding: 4px 12px;
  background: rgba(0, 0, 0, 0.7);
  border-radius: 4px;
  color: white;
  font-size: 14px;
}
</style>
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/components/ImagePreviewDialog.vue
git commit -m "feat: 添加放大预览对话框"
```

---

## Task 9: 素材库选择对话框

**Files:**
- Create: `frontend/src/components/MaterialSelectDialog.vue`

- [ ] **Step 1: 创建素材库选择对话框**

```vue
<!-- frontend/src/components/MaterialSelectDialog.vue -->
<template>
  <el-dialog
    v-model="visible"
    title="素材库选择"
    width="680px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <div class="material-dialog">
      <!-- 搜索和筛选 -->
      <div class="material-filter">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索素材"
          clearable
          @input="handleSearch"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        
        <el-select v-model="filterType" placeholder="类型筛选" clearable>
          <el-option label="全部" value="" />
          <el-option label="图片" value="image" />
          <el-option label="视频" value="video" />
        </el-select>
      </div>
      
      <!-- 素材列表 -->
      <div class="material-list" v-loading="loading">
        <div
          v-for="material in filteredMaterials"
          :key="material.id"
          class="material-item"
          :class="{ active: selectedId === material.id }"
          @click="handleSelect(material)"
        >
          <img
            :src="material.thumbnail || material.url"
            :alt="material.name"
            class="material-thumb"
          />
          <div class="material-info">
            <span class="material-name">{{ material.name }}</span>
            <span class="material-size">{{ formatSize(material.size) }}</span>
          </div>
        </div>
        
        <div v-if="filteredMaterials.length === 0" class="material-empty">
          暂无素材
        </div>
      </div>
    </div>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="handleConfirm" :disabled="!selectedId">
          确认选择
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { getMaterials } from '../api/material'

const props = defineProps({
  visible: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:visible', 'select'])

const loading = ref(false)
const materials = ref([])
const searchKeyword = ref('')
const filterType = ref('')
const selectedId = ref(null)
const selectedMaterial = ref(null)

const filteredMaterials = computed(() => {
  let result = materials.value
  
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    result = result.filter(m => m.name.toLowerCase().includes(keyword))
  }
  
  if (filterType.value) {
    result = result.filter(m => m.type === filterType.value)
  }
  
  return result
})

onMounted(() => {
  loadMaterials()
})

async function loadMaterials() {
  loading.value = true
  try {
    const response = await getMaterials()
    if (response.success) {
      materials.value = response.data
    }
  } catch (error) {
    console.error('加载素材失败:', error)
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  // 搜索是响应式的，无需额外处理
}

function handleSelect(material) {
  selectedId.value = material.id
  selectedMaterial.value = material
}

function handleConfirm() {
  if (selectedMaterial.value) {
    emit('select', selectedMaterial.value)
    handleClose()
  }
}

function handleClose() {
  emit('update:visible', false)
  selectedId.value = null
  selectedMaterial.value = null
}

function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.material-dialog {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.material-filter {
  display: flex;
  gap: 12px;
}

.material-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
  max-height: 400px;
  overflow-y: auto;
  padding: 4px;
}

.material-item {
  border: 2px solid transparent;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}

.material-item:hover {
  border-color: var(--el-color-primary-light-5);
}

.material-item.active {
  border-color: var(--el-color-primary);
}

.material-thumb {
  width: 100%;
  height: 120px;
  object-fit: cover;
}

.material-info {
  padding: 8px;
  background: var(--el-fill-color-light);
}

.material-name {
  display: block;
  font-size: 12px;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.material-size {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}

.material-empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 40px;
  color: var(--el-text-color-secondary);
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}
</style>
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/components/MaterialSelectDialog.vue
git commit -m "feat: 添加素材库选择对话框"
```

---

## Task 10: 图文发布主页面

**Files:**
- Create: `frontend/src/views/ImagePublish.vue`

- [ ] **Step 1: 创建图文发布主页面**

```vue
<!-- frontend/src/views/ImagePublish.vue -->
<template>
  <div class="publish-center">
    <!-- ========== LEFT SIDEBAR ========== -->
    <aside class="account-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">账号管理</span>
        <span class="sidebar-count">{{ totalCount }}</span>
      </div>

      <div class="group-list">
        <div
          v-for="group in filteredAccountGroups"
          :key="group.key"
          :class="['group-wrap', { 'is-selected': selectedPlatform === group.key }]"
        >
          <!-- Group header -->
          <div
            class="group-header cursor-pointer"
            @click="toggleGroup(group.key)"
          >
            <el-icon class="expand-icon" :style="{ color: selectedPlatform === group.key ? group.color : '' }">
              <component :is="expandedGroups.has(group.key) ? ArrowDown : ArrowRight" />
            </el-icon>
            <span class="platform-badge">
              <img v-if="group.logo" :src="group.logo" :alt="group.name" class="platform-badge-img">
              <template v-else>{{ group.letter }}</template>
            </span>
            <span class="group-name">{{ group.name }}</span>
            <span class="group-count">{{ group.accounts.filter(a => publishAccountIds.has(a.id)).length }}</span>
          </div>

          <!-- Expandable account list -->
          <transition name="slide">
            <div v-show="expandedGroups.has(group.key)" class="group-accounts">
              <div
                v-for="account in group.accounts.filter(a => publishAccountIds.has(a.id))"
                :key="account.id"
                :class="['account-item cursor-pointer', {
                  active: selectedAccountId === account.id,
                  'has-override': hasAccountOverride(account.id)
                }]"
                @click="selectAccount(account, group)"
              >
                <div class="account-avatar" :style="{ borderColor: group.color }">
                  {{ account.name ? account.name.charAt(0) : '?' }}
                </div>
                <span class="account-name">{{ account.name }}</span>
                <span :class="['dot', account.status === '正常' ? 'on' : 'off']"></span>
                <el-icon v-if="hasAccountOverride(account.id)" class="override-icon" title="已自定义配置"><StarFilled /></el-icon>
                <el-icon class="account-remove" @click.stop="removePublishAccount(account.id)"><Close /></el-icon>
              </div>
              <div v-if="group.accounts.filter(a => publishAccountIds.has(a.id)).length === 0" class="no-accounts">暂无账号</div>
            </div>
          </transition>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="add-btn cursor-pointer" @click="accountDialogVisible = true">+ 添加账号</div>
      </div>
    </aside>

    <!-- ========== RIGHT MAIN AREA ========== -->
    <main class="publish-main">
      <div class="main-body">
      <!-- Left: form + content -->
      <div class="main-form-col">
      <!-- Top bar -->
      <div class="main-header">
        <div class="header-left">
          <span class="page-title">发布图文</span>
          <span
            v-if="currentPlatformConfig"
            class="platform-tag"
            :style="{ background: currentPlatformConfig.bgColor, color: currentPlatformConfig.color }"
          >
            {{ currentPlatformConfig.name }} · 个性化设置
          </span>
        </div>
        <div class="header-right">
          <button class="draft-btn" @click="saveDraft">
            <el-icon><Document /></el-icon>
            {{ currentDraftId ? '更新草稿' : '保存草稿' }}
          </button>
          <button class="publish-btn" @click="publishAll" :disabled="!canPublish || publishing">
            {{ publishing ? '发布中...' : '一键发布' }}
          </button>
        </div>
      </div>

      <!-- Scrollable content -->
      <div class="main-content">
        <!-- ===== PUBLIC CONFIG ===== -->
        <div class="config-section">
          <div class="section-bar">
            <div class="bar purple"></div>
            <span class="section-label">公共配置</span>
            <span class="hint">所有账号共享</span>
          </div>

          <!-- Image Uploader -->
          <ImageUploader />

          <!-- Batch title/description sync -->
          <div class="batch-sync-section">
            <div class="batch-sync-header" @click="batchSyncExpanded = !batchSyncExpanded">
              <span>批量设置标题和描述</span>
              <el-icon class="cursor-pointer">
                <component :is="batchSyncExpanded ? ArrowDown : ArrowRight" />
              </el-icon>
            </div>
            <div v-show="batchSyncExpanded" class="batch-sync-body">
              <div class="form-field">
                <div class="field-head">
                  <span>公共标题</span>
                </div>
                <el-input
                  v-model="batchTitle"
                  placeholder="输入标题后点击同步..."
                  maxlength="100"
                />
              </div>
              <div class="form-field">
                <div class="field-head">
                  <span>公共描述</span>
                </div>
                <el-input
                  v-model="batchDescription"
                  type="textarea"
                  :rows="5"
                  placeholder="输入描述后点击同步..."
                  maxlength="2000"
                />
              </div>
              <button class="cover-action-btn primary" @click="syncBatchToAll">
                <el-icon :size="15"><Promotion /></el-icon><span>同步到所有平台</span>
              </button>
            </div>
          </div>
        </div>

        <!-- Divider -->
        <div class="divider"></div>

        <!-- ===== PLATFORM-SPECIFIC SETTINGS ===== -->
        <div v-if="currentPlatformConfig" class="config-section">
          <div class="section-bar">
            <div class="bar" :style="{ background: currentPlatformConfig.color }"></div>
            <span class="section-label">
              {{ currentPlatformConfig.name }}
              {{ selectedAccountId ? '· ' + getAccountName(selectedAccountId) : '· 默认设置' }}
            </span>
            <span class="hint">{{ selectedAccountId ? '仅对该账号生效' : '对该分组所有未自定义的账号生效' }}</span>
          </div>

          <!-- 如果选中了账号且有自定义配置，显示"恢复默认"按钮 -->
          <div v-if="selectedAccountId && hasAccountOverride(selectedAccountId)" style="margin-bottom: 12px;">
            <el-button size="small" @click="resetAccountOverride(selectedAccountId)">恢复为渠道默认</el-button>
          </div>

          <!-- 账号级 or 渠道级标题描述 -->
          <div class="platform-title-desc">
            <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">标题</div>
              <el-input
                v-model="form.title"
                placeholder="请输入标题..."
                maxlength="100"
                show-word-limit
              />
            </div>
            <div class="setting-card" :style="{ borderColor: currentPlatformConfig.color + '26', background: currentPlatformConfig.color + '0a' }">
              <div class="setting-label" :style="{ color: currentPlatformConfig.color }">描述</div>
              <el-input
                v-model="form.description"
                type="textarea"
                :rows="5"
                placeholder="请输入描述..."
                maxlength="2000"
                show-word-limit
              />
            </div>
          </div>
        </div>

        <!-- No platform selected hint -->
        <div v-else class="no-platform-hint">
          <div class="hint-icon">
            <el-icon :size="48"><Picture /></el-icon>
          </div>
          <p>请在左侧选择一个平台分组</p>
          <p class="hint-sub">选择后可配置该平台的个性化发布设置</p>
        </div>
      </div>
      </div><!-- /main-form-col -->

      <!-- Right: Image preview panel -->
      <div class="phone-panel">
        <ImageCarousel :images="images" />
      </div>

      </div><!-- /main-body -->
    </main>

    <!-- ========== DIALOGS ========== -->

    <!-- Account Selection Dialog -->
    <el-dialog
      v-model="accountDialogVisible"
      title="选择账号"
      width="680px"
      :close-on-click-modal="false"
      class="account-select-dialog"
    >
      <div class="account-dialog-body">
        <div class="account-dialog-content">
          <!-- Left: platform list -->
          <div class="dialog-platform-list">
            <div
              :class="['dialog-platform-item', 'cursor-pointer', { active: !accountFilterPlatform }]"
              @click="accountFilterPlatform = ''"
            >全部平台</div>
            <div
              v-for="p in filteredPlatformList"
              :key="p.key"
              :class="['dialog-platform-item', 'cursor-pointer', { active: accountFilterPlatform === p.name }]"
              @click="accountFilterPlatform = p.name"
            >
              <span class="dialog-platform-badge">
                <img v-if="p.logo" :src="p.logo" :alt="p.name" class="dialog-platform-badge-img">
                <template v-else>{{ p.letter }}</template>
              </span>
              {{ p.name }}
            </div>
          </div>

          <!-- Right: account checkboxes -->
          <div class="dialog-account-list">
            <div class="dialog-select-all">
              <el-button size="small" @click="toggleSelectAll">
                {{ isAllSelected ? '取消全选' : '一键全选' }}
              </el-button>
            </div>
            <el-checkbox-group v-model="tempSelectedAccounts">
              <div
                v-for="account in filteredAccounts"
                :key="account.id"
                :class="['dialog-account-item', { disabled: account.status !== '正常' }]"
              >
                <el-checkbox :label="account.id" class="cursor-pointer">
                  <div class="dialog-account-info">
                    <div class="dialog-account-avatar">{{ account.name ? account.name.charAt(0) : '?' }}</div>
                    <span class="dialog-account-name">{{ account.name }}</span>
                    <span class="dialog-account-platform">{{ account.platform }}</span>
                    <span :class="['dialog-account-status', account.status === '正常' ? 'ok' : 'err']">
                      {{ account.status === '正常' ? '正常' : '已失效' }}
                    </span>
                  </div>
                </el-checkbox>
              </div>
            </el-checkbox-group>
            <div v-if="filteredAccounts.length === 0" class="dialog-empty">暂无可选账号</div>
          </div>
        </div>
      </div>

      <template #footer>
        <div class="dialog-footer">
          <span class="selected-count">已选择 {{ tempSelectedAccounts.length }} 个账号</span>
          <div class="dialog-footer-btns">
            <el-button @click="accountDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="confirmAccountSelection">确认添加</el-button>
          </div>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ArrowDown, ArrowRight, Document, Promotion, Picture,
  StarFilled, Close
} from '@element-plus/icons-vue'
import { useAccountStore } from '../stores/account'
import { useAppStore } from '../stores/app'
import { useImagePublishStore } from '../stores/imagePublish'
import ImageUploader from '../components/ImageUploader.vue'
import ImageCarousel from '../components/ImageCarousel.vue'

const accountStore = useAccountStore()
const appStore = useAppStore()
const imagePublishStore = useImagePublishStore()

// 平台配置（仅抖音、快手、小红书）
const imagePublishPlatforms = [
  { key: 'douyin', name: '抖音', color: '#000000', bgColor: '#0000001a' },
  { key: 'kuaishou', name: '快手', color: '#FF4906', bgColor: '#FF49061a' },
  { key: 'xiaohongshu', name: '小红书', color: '#FF2442', bgColor: '#FF24421a' }
]

// 状态
const selectedPlatform = ref(null)
const selectedAccountId = ref(null)
const expandedGroups = ref(new Set())
const accountDialogVisible = ref(false)
const accountFilterPlatform = ref('')
const tempSelectedAccounts = ref([])
const batchSyncExpanded = ref(false)
const publishing = ref(false)
const currentDraftId = ref(null)

// 表单数据
const form = ref({
  title: '',
  description: ''
})

// 从 store 获取数据
const { images, batchTitle, batchDescription, canPublish } = imagePublishStore

// 计算属性
const accountGroups = computed(() => {
  return imagePublishPlatforms.map(platform => {
    const accounts = accountStore.accounts.filter(a => a.platform === platform.name)
    return {
      ...platform,
      accounts
    }
  })
})

const filteredAccountGroups = computed(() => {
  return accountGroups.value.filter(group => group.accounts.length > 0)
})

const totalCount = computed(() => {
  return filteredAccountGroups.value.reduce((sum, group) => sum + group.accounts.length, 0)
})

const publishAccountIds = computed(() => {
  return new Set(imagePublishStore.selectedAccounts)
})

const currentPlatformConfig = computed(() => {
  if (!selectedPlatform.value) return null
  return imagePublishPlatforms.find(p => p.key === selectedPlatform.value)
})

const filteredPlatformList = computed(() => {
  return imagePublishPlatforms
})

const filteredAccounts = computed(() => {
  if (!accountFilterPlatform.value) {
    return accountStore.accounts.filter(a => imagePublishPlatforms.some(p => p.name === a.platform))
  }
  return accountStore.accounts.filter(a => a.platform === accountFilterPlatform.value)
})

const isAllSelected = computed(() => {
  return filteredAccounts.value.length > 0 &&
    filteredAccounts.value.every(a => tempSelectedAccounts.value.includes(a.id))
})

// 方法
function toggleGroup(key) {
  if (expandedGroups.value.has(key)) {
    expandedGroups.value.delete(key)
  } else {
    expandedGroups.value.add(key)
  }
}

function selectAccount(account, group) {
  selectedPlatform.value = group.key
  selectedAccountId.value = account.id
  
  // 加载账号配置
  const config = imagePublishStore.accountConfigs[account.id] || {}
  form.value = {
    title: config.title || '',
    description: config.description || ''
  }
}

function removePublishAccount(accountId) {
  imagePublishStore.selectedAccounts = imagePublishStore.selectedAccounts.filter(id => id !== accountId)
  if (selectedAccountId.value === accountId) {
    selectedAccountId.value = null
  }
}

function hasAccountOverride(accountId) {
  return !!imagePublishStore.accountConfigs[accountId]
}

function resetAccountOverride(accountId) {
  delete imagePublishStore.accountConfigs[accountId]
  form.value = { title: '', description: '' }
}

function getAccountName(accountId) {
  const account = accountStore.accounts.find(a => a.id === accountId)
  return account ? account.name : ''
}

function toggleSelectAll() {
  if (isAllSelected.value) {
    tempSelectedAccounts.value = []
  } else {
    tempSelectedAccounts.value = filteredAccounts.value
      .filter(a => a.status === '正常')
      .map(a => a.id)
  }
}

function confirmAccountSelection() {
  imagePublishStore.selectedAccounts = [...new Set([...imagePublishStore.selectedAccounts, ...tempSelectedAccounts.value])]
  accountDialogVisible.value = false
  tempSelectedAccounts.value = []
}

function syncBatchToAll() {
  imagePublishStore.syncBatchToAll()
  ElMessage.success('已同步到所有平台')
}

async function saveDraft() {
  try {
    await imagePublishStore.save()
    ElMessage.success('草稿保存成功')
  } catch (error) {
    ElMessage.error('保存失败: ' + error.message)
  }
}

async function publishAll() {
  try {
    await ElMessageBox.confirm('确定发布图文吗？', '确认发布', {
      type: 'warning'
    })
    
    publishing.value = true
    await imagePublishStore.publish()
    ElMessage.success('发布成功')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('发布失败: ' + error.message)
    }
  } finally {
    publishing.value = false
  }
}

// 监听表单变化，保存到 store
watch(form, (newForm) => {
  if (selectedAccountId.value) {
    imagePublishStore.updateAccountConfig(selectedAccountId.value, newForm)
  }
}, { deep: true })

// 初始化
onMounted(() => {
  // 默认展开第一个分组
  if (filteredAccountGroups.value.length > 0) {
    expandedGroups.value.add(filteredAccountGroups.value[0].key)
  }
})
</script>

<style scoped>
/* 复用 PublishCenter.vue 的样式 */
.publish-center {
  display: flex;
  height: calc(100vh - 60px);
  background: var(--el-bg-color);
}

.account-sidebar {
  width: 240px;
  border-right: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.sidebar-title {
  font-size: 14px;
  font-weight: 500;
}

.sidebar-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: 8px;
}

.group-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.group-wrap {
  margin-bottom: 8px;
}

.group-header {
  display: flex;
  align-items: center;
  padding: 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.group-header:hover {
  background: var(--el-fill-color-light);
}

.expand-icon {
  margin-right: 8px;
  font-size: 12px;
}

.platform-badge {
  width: 24px;
  height: 24px;
  border-radius: 4px;
  background: var(--el-fill-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  margin-right: 8px;
}

.platform-badge-img {
  width: 16px;
  height: 16px;
  object-fit: contain;
}

.group-name {
  flex: 1;
  font-size: 13px;
}

.group-count {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.group-accounts {
  padding-left: 32px;
}

.account-item {
  display: flex;
  align-items: center;
  padding: 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.account-item:hover {
  background: var(--el-fill-color-light);
}

.account-item.active {
  background: var(--el-color-primary-light-9);
}

.account-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 500;
  margin-right: 8px;
}

.account-name {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  margin-left: 8px;
}

.dot.on {
  background: var(--el-color-success);
}

.dot.off {
  background: var(--el-color-danger);
}

.override-icon {
  margin-left: 8px;
  color: var(--el-color-warning);
}

.account-remove {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  opacity: 0;
  transition: opacity 0.2s;
}

.account-item:hover .account-remove {
  opacity: 1;
}

.no-accounts {
  padding: 16px;
  text-align: center;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
}

.add-btn {
  text-align: center;
  padding: 8px;
  border-radius: 6px;
  color: var(--el-color-primary);
  font-size: 13px;
  transition: background 0.2s;
}

.add-btn:hover {
  background: var(--el-color-primary-light-9);
}

.publish-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.main-form-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.main-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-title {
  font-size: 16px;
  font-weight: 500;
}

.platform-tag {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.header-right {
  display: flex;
  gap: 12px;
}

.draft-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

.draft-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.publish-btn {
  padding: 8px 20px;
  border: none;
  border-radius: 6px;
  background: var(--el-color-primary);
  color: white;
  cursor: pointer;
  transition: opacity 0.2s;
}

.publish-btn:hover {
  opacity: 0.9;
}

.publish-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.main-content {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.config-section {
  margin-bottom: 24px;
}

.section-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.bar {
  width: 3px;
  height: 16px;
  border-radius: 2px;
}

.bar.purple {
  background: var(--el-color-primary);
}

.section-label {
  font-size: 14px;
  font-weight: 500;
}

.hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.batch-sync-section {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  overflow: hidden;
}

.batch-sync-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--el-fill-color-light);
  cursor: pointer;
}

.batch-sync-body {
  padding: 16px;
}

.form-field {
  margin-bottom: 16px;
}

.field-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.cover-action-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: white;
  cursor: pointer;
  transition: all 0.2s;
}

.cover-action-btn:hover {
  border-color: var(--el-color-primary);
  color: var(--el-color-primary);
}

.cover-action-btn.primary {
  background: var(--el-color-primary);
  border-color: var(--el-color-primary);
  color: white;
}

.cover-action-btn.primary:hover {
  opacity: 0.9;
}

.divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 24px 0;
}

.platform-title-desc {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.setting-card {
  padding: 16px;
  border: 1px solid;
  border-radius: 8px;
}

.setting-label {
  font-size: 13px;
  font-weight: 500;
  margin-bottom: 8px;
}

.no-platform-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 20px;
  color: var(--el-text-color-secondary);
}

.hint-icon {
  margin-bottom: 16px;
}

.no-platform-hint p {
  margin: 0;
  font-size: 14px;
}

.hint-sub {
  font-size: 12px;
  margin-top: 8px;
}

.phone-panel {
  width: 360px;
  border-left: 1px solid var(--el-border-color-lighter);
  display: flex;
  flex-direction: column;
  background: var(--el-fill-color-lighter);
}

/* Account dialog styles */
.account-select-dialog {
  :deep(.el-dialog__body) {
    padding: 0;
  }
}

.account-dialog-body {
  padding: 16px;
}

.account-dialog-content {
  display: flex;
  gap: 16px;
  min-height: 400px;
}

.dialog-platform-list {
  width: 150px;
  border-right: 1px solid var(--el-border-color-lighter);
  padding-right: 16px;
}

.dialog-platform-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
}

.dialog-platform-item:hover {
  background: var(--el-fill-color-light);
}

.dialog-platform-item.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
}

.dialog-platform-badge {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--el-fill-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}

.dialog-platform-badge-img {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.dialog-account-list {
  flex: 1;
  overflow-y: auto;
}

.dialog-select-all {
  margin-bottom: 12px;
}

.dialog-account-item {
  padding: 8px;
  border-radius: 6px;
  transition: background 0.2s;
}

.dialog-account-item:hover {
  background: var(--el-fill-color-light);
}

.dialog-account-item.disabled {
  opacity: 0.5;
}

.dialog-account-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dialog-account-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--el-fill-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.dialog-account-name {
  flex: 1;
  font-size: 13px;
}

.dialog-account-platform {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.dialog-account-status {
  font-size: 12px;
}

.dialog-account-status.ok {
  color: var(--el-color-success);
}

.dialog-account-status.err {
  color: var(--el-color-danger);
}

.dialog-empty {
  text-align: center;
  padding: 40px;
  color: var(--el-text-color-secondary);
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.selected-count {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.dialog-footer-btns {
  display: flex;
  gap: 12px;
}

/* Transition */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>
```

- [ ] **Step 2: 提交代码**

```bash
git add frontend/src/views/ImagePublish.vue
git commit -m "feat: 添加图文发布主页面"
```

---

## Task 11: 安装依赖

**Files:**
- Modify: `frontend/package.json`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 安装前端依赖**

```bash
cd frontend && npm install sortablejs browser-image-compression
```

- [ ] **Step 2: 安装后端依赖**

```bash
pip install Pillow
```

- [ ] **Step 3: 提交代码**

```bash
git add frontend/package.json frontend/package-lock.json backend/requirements.txt
git commit -m "feat: 添加图文发布相关依赖"
```

---

## Task 12: 功能测试

- [ ] **Step 1: 启动开发服务器**

```bash
# 启动后端
cd backend && python app.py

# 启动前端
cd frontend && npm run dev
```

- [ ] **Step 2: 测试菜单显示**

访问 http://localhost:5173，验证：
- "发布中心"已更名为"视频发布"
- 新增"图文发布"菜单，位于视频发布后面
- 点击图文发布菜单可以正常跳转

- [ ] **Step 3: 测试图片上传**

1. 点击"上传图片"按钮
2. 选择一张图片
3. 验证图片显示在网格中
4. 验证进度条显示正常
5. 验证数量计数更新

- [ ] **Step 4: 测试拖拽排序**

1. 上传多张图片
2. 拖动图片改变位置
3. 验证排序已更新

- [ ] **Step 5: 测试跑马灯预览**

1. 上传多张图片
2. 左右滑动预览
3. 点击图片打开放大预览
4. 验证序号和指示器显示正常

- [ ] **Step 6: 测试草稿保存**

1. 上传图片
2. 点击"保存草稿"
3. 验证保存成功提示

- [ ] **Step 7: 测试模拟发布**

1. 上传图片
2. 选择账号
3. 点击"一键发布"
4. 验证发布成功提示

- [ ] **Step 8: 提交最终代码**

```bash
git add -A
git commit -m "feat: 图文发布功能完成"
```

---

## 执行选项

计划已完成并保存到 `docs/superpowers/plans/2026-05-28-image-publish.md`。

两种执行方式：

**1. Subagent-Driven（推荐）** - 每个任务分发一个新子代理，任务间进行审查，快速迭代

**2. Inline Execution** - 在当前会话中执行任务，批量执行并设置检查点

选择哪种方式？
