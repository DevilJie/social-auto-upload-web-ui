# 素材库统一存储重构设计文档

> 日期: 2026-05-31
> 状态: 待审阅
> 范围: 废弃旧存储系统，全部重写为统一存储架构

---

## 1. 背景与问题

### 1.1 当前现状

系统存在两套完全独立的文件存储体系：

| 维度 | 视频素材系统 | 图文图片系统 |
|------|------------|------------|
| 存储目录 | `data/videoFile/` | `data/image-publish/` |
| 数据库表 | `file_records` | `image_records` |
| 主键类型 | INTEGER 自增 | TEXT UUID |
| 文件命名 | `{uuid}_{原始名}` | `{uuid}.{ext}` |
| 文件大小单位 | MB | KB |
| 上传接口 | `POST /uploadSave` | `POST /api/image-publish/upload` |
| 文件访问 | `GET /getFile?filename=xxx` | `GET /api/image-publish/files/xxx` |
| 删除接口 | `GET /deleteFile?id=数字` | `DELETE /api/image-publish/images/uuid` |
| URL 前缀 | `/getFile?filename=` | `/api/image-publish/files/` |

### 1.2 导致的 10 个具体问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | 3 个独立上传端点：`/uploadSave`(视频)、`/upload`(封面)、`/api/image-publish/upload`(图文) | 上传逻辑无法统一 |
| 2 | 2 套 URL 构建范式：旧 `getMaterialPreviewUrl` vs 新 `mat.url` 字段 | URL 解析混乱 |
| 3 | `MaterialSelectDialog.confirmSelect()` 忽略 `mat.url`，始终用旧方法 | 素材选择返回错误 URL |
| 4 | `ImageUploader` 双重 baseUrl 前缀风险 `http://localhost:5409http://...` | 图片 URL 可能错误 |
| 5 | 文件大小单位不统一：`file_records` 用 MB，`image_records` 用 KB | 前端转换逻辑混乱 |
| 6 | `CoverCard` 上传到 `/upload`，视频上传到 `/uploadSave`，封面和视频走不同代码路径 | 3 个上传端点 |
| 7 | `PublishCenter` 有自己的内联素材库 UI，不用 `MaterialSelectDialog` | 两套素材选择 UI |
| 8 | 封面图混在 `videoFile` 目录，无独立管理 | 封面生命周期绑定视频素材 |
| 9 | `/deleteFile` 只删 `file_records`，无法删 `image_records` | 素材管理页面删除图文素材失败 |
| 10 | 文件路径无 URL 编码 | 中文文件名/空格导致 URL 异常 |

### 1.3 设计目标

1. **废弃**现有 `file_records` 和 `image_records` 两张表及相关代码
2. **新建**统一 `materials` 表 + 存储抽象层
3. **支持**本地存储和 S3 兼容存储两种后端，互斥选择
4. **全部重写**前端和后端的文件上传/访问/删除逻辑，不留旧代码

---

## 2. 架构设计

### 2.1 整体架构

```
前端组件
  │
  ├─ api/materials.js (统一 API 层)
  │     ├─ upload()     → POST /api/materials/upload
  │     ├─ list()       → GET  /api/materials/list
  │     ├─ delete()     → DELETE /api/materials/<id>
  │     └─ getFileUrl() → URL 构建工具
  │
  └─ utils/storage.js (统一 URL 构建)
        └─ getFileUrl(storedPath) → {baseUrl}/api/materials/file/{storedPath}

后端
  │
  ├─ blueprints/materials_bp.py (统一路由)
  │     ├─ POST   /api/materials/upload
  │     ├─ GET    /api/materials/list
  │     ├─ DELETE /api/materials/<id>
  │     └─ GET    /api/materials/file/<path>
  │
  └─ storage/ (存储抽象层)
        ├─ base.py    StorageBackend (抽象类)
        ├─ local.py   LocalStorage   (data/materials/YYYY/MM/DD/)
        └─ s3.py      S3Storage      (bucket/materials/YYYY/MM/DD/)
```

### 2.2 存储抽象层接口

```python
# backend/storage/base.py
class StorageBackend(ABC):
    @abstractmethod
    def save(self, file_data: bytes, relative_path: str) -> str:
        """保存文件，返回实际存储路径"""

    @abstractmethod
    def get(self, relative_path: str) -> bytes:
        """读取文件内容"""

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        """获取文件访问 URL"""

    @abstractmethod
    def delete(self, relative_path: str) -> bool:
        """删除文件"""

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """文件是否存在"""
```

### 2.3 数据库 Schema

**废弃表**：`file_records`、`image_records`

**新建表**：`materials`

```sql
CREATE TABLE IF NOT EXISTS materials (
    id TEXT PRIMARY KEY,                          -- UUID
    original_filename TEXT NOT NULL,              -- 原始文件名
    stored_path TEXT NOT NULL,                    -- 相对路径: materials/2026/05/31/{uuid}.{ext}
    file_type TEXT NOT NULL,                      -- 'video' | 'image'
    mime_type TEXT,                               -- MIME 类型 (video/mp4, image/jpeg 等)
    file_size INTEGER DEFAULT 0,                  -- 字节数 (统一单位)
    storage_type TEXT NOT NULL DEFAULT 'local',   -- 'local' | 's3'
    width INTEGER DEFAULT 0,                      -- 图片宽度
    height INTEGER DEFAULT 0,                     -- 图片高度
    duration REAL DEFAULT 0,                      -- 视频时长(秒)
    upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### 2.4 存储配置

复用 `data/settings.json`，增加 `storage` 字段：

```json
{
  "proxyUrl": "",
  "storage": {
    "type": "local",
    "s3": {
      "endpoint": "",
      "access_key": "",
      "secret_key": "",
      "bucket": "",
      "region": ""
    }
  }
}
```

- `type`: `"local"` 或 `"s3"`，互斥选择
- 本地存储无需额外配置，默认 `data/materials/` 目录
- S3 配置仅在 `type` 为 `"s3"` 时生效

---

## 3. 后端改动清单（全部重写，删除旧代码）

### 3.1 新增文件

| 文件 | 说明 |
|------|------|
| `backend/storage/__init__.py` | 导出 `get_storage()` 工厂函数 |
| `backend/storage/base.py` | `StorageBackend` 抽象基类 |
| `backend/storage/local.py` | `LocalStorage` 实现 |
| `backend/storage/s3.py` | `S3Storage` 实现 |
| `backend/blueprints/materials_bp.py` | 统一素材路由 Blueprint |

### 3.2 `backend/app.py` — 删除旧路由，注册新 Blueprint

#### 删除以下路由（整段删除）：

| 路由 | 行号范围 | 说明 |
|------|---------|------|
| `/<path:filename>` | 行 109-118 | 旧静态文件服务（catch-all） |
| `_get_videofile_dir()` | 行 99-106 | videoFile 目录辅助函数 |
| `POST /upload` | 行 144-168 | 旧视频上传 |
| `GET /getFile` | 行 171-178 | 旧文件获取 |
| `POST /uploadSave` | 行 181-212 | 旧素材上传 |
| `GET /getFiles` | 行 215-256 | 旧素材列表（合并查询） |
| `GET /deleteFile` | 行 259-291 | 旧文件删除 |

同时删除全局变量 `_VIDEOFILE_DIR` 和 `_get_videofile_dir()` 函数。

#### 修改以下路由：

| 路由 | 行号 | 修改内容 |
|------|------|---------|
| `POST /postVideo` | 行 555-631 | `fileList` 中的路径改为 `materials.stored_path`；`thumbnailLandscape`/`thumbnailPortrait` 改为 `stored_path` |
| `POST /postVideoBatch` | 行 634-710 | 同上 |
| `GET /api/v2/settings` | 行 731-733 | 返回增加 `storage` 字段 |
| `PUT /api/v2/settings` | 行 736-742 | 支持 `storage` 字段读写 |

#### 新增注册：

```python
from blueprints.materials_bp import materials_bp
app.register_blueprint(materials_bp)
```

### 3.3 `backend/blueprints/image_publish_bp.py` — 删除文件操作，改用新存储

#### 删除以下代码：

| 代码 | 行号 | 说明 |
|------|------|------|
| `UPLOAD_DIR = BASE_DIR / "image-publish"` | 行 25 | 旧存储目录常量 |
| `ALLOWED_EXTENSIONS` | 行 26-27 | 旧文件格式白名单 |
| `POST /upload` 路由 | 行 43-89 | 旧图片上传（整段删除） |
| `GET /files/<filepath>` 路由 | 行 94-104 | 旧图片文件访问（整段删除） |
| `DELETE /images/<image_id>` 路由 | 行 109-134 | 旧图片删除（整段删除） |

#### 修改以下代码：

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `POST /publish` 中的文件路径查询 | 行 179-186 | 从 `materials` 表查 `stored_path`，通过 `storage.get()` 获取文件 |
| `POST /publish` 中的 `cover_path` 处理 | 行 244 | 从 `materials` 表查封面文件的 `stored_path` |
| `POST /execute-publish` 中的文件路径查询 | 行 583-590 | 同上，从 `materials` 表查 |
| `_extract_image_draft_cover()` | 行 409-431 | 封面路径改为 `stored_path` 格式，不再解析 `/api/image-publish/files/` URL |

### 3.4 `backend/routes/frames.py` — 修改视频路径解析

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `_resolve_video_path()` | 行 18-24 | 从 `materials` 表查 `stored_path`，通过 `storage.get()` 获取本地文件路径，不再硬编码 `videoFile` 目录 |

### 3.5 `backend/init_db.py` — 新增表，保留旧表但不再使用

| 操作 | 说明 |
|------|------|
| 新增 `materials` 表 | 启动时检查，不存在则自动建表 |
| 保留 `file_records` 和 `image_records` | 不删除旧表，避免数据丢失，但代码不再读写它们 |

### 3.6 `backend/conf.py` — 无需改动

`BASE_DIR` 保持不变，新存储目录 `data/materials/` 由 `LocalStorage` 内部管理。

---

## 4. 前端改动清单（全部重写，删除旧代码）

### 4.1 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/api/materials.js` | 统一素材 API 层 |
| `frontend/src/utils/storage.js` | 统一 URL 构建工具 |

### 4.2 新增文件详细设计

#### `frontend/src/api/materials.js`

```javascript
import http from '@/utils/request'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export const materialsApi = {
  /** 上传文件 */
  upload(formData, onProgress) {
    return http.upload('/api/materials/upload', formData, onProgress)
  },

  /** 获取素材列表，type: 'all' | 'video' | 'image' */
  list(type = 'all') {
    return http.get('/api/materials/list', { type })
  },

  /** 删除素材 */
  delete(id) {
    return http.delete(`/api/materials/${id}`)
  },
}
```

#### `frontend/src/utils/storage.js`

```javascript
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

/**
 * 统一文件 URL 构建
 * @param {string} storedPath - 相对路径，如 "materials/2026/05/31/uuid.jpg"
 */
export function getFileUrl(storedPath) {
  if (!storedPath) return ''
  if (storedPath.startsWith('http')) return storedPath // 已经是完整 URL（S3 presigned）
  return `${BASE_URL}/api/materials/file/${storedPath}`
}
```

### 4.3 删除文件

| 文件 | 说明 |
|------|------|
| `frontend/src/api/material.js` | 旧素材 API，全部删除 |

### 4.4 `frontend/src/api/imagePublish.js` — 修改上传函数

| 函数 | 行号 | 修改内容 |
|------|------|---------|
| `uploadImage()` | 行 6-15 | 改为调用 `materialsApi.upload()`，返回统一格式数据 |
| `publishImage()` | 行 18-20 | 不变 |
| `getDrafts()` | 行 23-25 | 不变 |
| `saveDraft()` | 行 28-30 | 不变 |
| `deleteDraft()` | 行 33-35 | 不变 |
| `getHistory()` | 行 38-40 | 不变 |

### 4.5 `frontend/src/views/PublishCenter.vue` — 核心改动

#### 删除以下代码：

| 代码 | 行号 | 说明 |
|------|------|------|
| `import * as materialApi from '@/api/material'` | ~行 680 | 旧 API 导入 |
| `materialApi.getMaterialPreviewUrl()` 的所有调用 | 行 1079, 1165, 1183 | 旧 URL 构建 |
| `materialApi.getAllMaterials()` 调用 | 行 1138 | 旧素材列表 |

#### 修改以下代码：

| 代码位置 | 行号 | 当前实现 | 新实现 |
|----------|------|---------|--------|
| `el-upload` action | 行 551 | `` `${apiBaseUrl}/uploadSave` `` | 改用 `:http-request` 自定义上传方法，调用 `materialsApi.upload()` |
| `apiBaseUrl` | 行 680 | 用于拼接上传 URL | 删除，改用统一 API |
| `handleVideoUploadSuccess()` | 行 1073-1121 | 从 `response.data.filepath` 提取文件名，用 `getMaterialPreviewUrl` 构建 URL | 从新接口返回的 `stored_path` 用 `getFileUrl()` 构建 URL；`path` 改为 `stored_path` |
| `confirmMaterialSelect()` 封面分支 | 行 1159-1176 | `material.file_path.split('/').pop()` + `getMaterialPreviewUrl()` | 使用 `getFileUrl(material.stored_path)` |
| `confirmMaterialSelect()` 视频分支 | 行 1177-1215 | 同上 | 同上 |
| `selectFromLibrary()` | 行 1129-1152 | `materialApi.getAllMaterials()` | `materialsApi.list()` |
| `publishAll()` fileList | 行 1644 | `selectedVideo.path` | `selectedVideo.stored_path` |
| `publishAll()` 封面路径 | 行 1647-1648 | `coverLandscape.path` / `coverPortrait.path` | `coverLandscape.stored_path` / `coverPortrait.stored_path` |
| `saveDraft()` | 行 1292-1330 | 序列化 `{ name, path, url, size, type }` | 改为 `{ name, stored_path, url, size, type }` |
| `restoreDraft()` | 行 1332-1407 | 直接赋值 | 用 `getFileUrl(stored_path)` 重新生成 `url` 字段 |

#### `commonConfig` 数据结构变更：

```javascript
// 旧结构
{ name, url, path, size, type }

// 新结构
{ name, url, stored_path, size, type, mime_type }
// url: 由 getFileUrl(stored_path) 生成，用于前端预览
// stored_path: 后端相对路径，用于发布和草稿
// mime_type: 精确的 MIME 类型
```

### 4.6 `frontend/src/components/CoverCard.vue` — 重写上传逻辑

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `import * as materialApi from '@/api/material'` | ~行顶部 | 删除，改为 `import { materialsApi } from '@/api/materials'` |
| `onFileSelected()` | 行 64-91 | 整个函数重写：调用 `materialsApi.upload()` 构建新 FormData，用 `getFileUrl(resp.data.stored_path)` 替代 `getMaterialPreviewUrl`，返回数据使用新结构 `{ name, url, stored_path, size, type }` |

### 4.7 `frontend/src/components/CoverEditorDialog.vue` — 重写封面上传保存

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| 封面保存上传逻辑 | 行 407-413 | 同 CoverCard，用 `materialsApi.upload()` + `getFileUrl()` |

### 4.8 `frontend/src/components/ImageUploader.vue` — 重写上传逻辑

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `import imagePublishApi` | ~行顶部 | 改为 `import { materialsApi } from '@/api/materials'` |
| `uploadFile()` | 行 183-243 | 整个函数重写：用 `materialsApi.upload()` 替代 `imagePublishApi.uploadImage()`，用 `getFileUrl()` 构建 URL，消除双重 baseUrl 前缀 bug |
| `reUpload()` | 行 251-264 | 同上 |
| `onDrop()` | 行 295-315 | 调用新的 `uploadFile()` |
| 图片数据结构 | 行 225-234 | `{ id, name, url, stored_path, size, type, uploading, progress }` |

### 4.9 `frontend/src/components/ImageCoverUpload.vue` — 重写封面上传

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `onFileSelected()` | 行 74-113 | 用 `materialsApi.upload()` 替代 `imagePublishApi.uploadImage()`，用 `getFileUrl()` 构建 URL |

### 4.10 `frontend/src/views/ImagePublish.vue` — 修改素材库和发布逻辑

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `onMaterialSelected()` | 行 844-883 | 适配新素材数据结构，使用 `stored_path` 和 `getFileUrl()` |
| `publishAll()` 中 imageIds | 行 1191 | `img.id` 改为 `img.stored_path`（或保留 id 查 materials 表） |
| `publishAll()` 中 cover_path | 行 1227 | `commonConfig.coverImage?.stored_path` |
| `loadDraft()` 图片 URL 恢复 | 行 1344-1354 | 用 `getFileUrl(img.stored_path)` 替代硬编码拼接 |
| `saveDraft()` | 行 1013-1055 | 序列化使用 `stored_path` |

### 4.11 `frontend/src/views/MaterialManagement.vue` — 重写整个页面

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `import * as materialApi from '@/api/material'` | ~行顶部 | 删除，改为 `import { materialsApi } from '@/api/materials'` |
| `fetchMaterials()` | 行 232-249 | 调用 `materialsApi.list()` |
| `submitUpload()` | 行 321-388 | 调用 `materialsApi.upload()` |
| `handleDelete()` | 行 407-435 | 调用 `materialsApi.delete(id)` |
| `getPreviewUrl()` | 行 438-451 | 整个函数替换为 `getFileUrl(material.stored_path)` |
| `downloadFile()` | 行 454-457 | 用 `getFileUrl()` + window.open |
| `isVideoFile()` / `isImageFile()` | 行 460-468 | 改用 `material.file_type` 字段判断 |
| 素材数据结构引用 | 多处 | `material.filename` → `material.original_filename`，`material.filesize` → `material.file_size`（字节） |

### 4.12 `frontend/src/components/MaterialSelectDialog.vue` — 重写

| 代码 | 行号 | 修改内容 |
|------|------|---------|
| `import * as materialApi from '@/api/material'` | ~行顶部 | 删除，改为 `import { materialsApi } from '@/api/materials'` |
| `loadMaterials()` | 行 168-183 | 调用 `materialsApi.list(filterType)` |
| `getMaterialUrl()` | 行 134-147 | 整个函数替换为 `getFileUrl(mat.stored_path)`，消除双重 URL 模式 |
| `confirmSelect()` | 行 185-207 | 返回统一数据结构 `{ id, name, url, stored_path, size, type }`，不再使用 `getMaterialPreviewUrl` |
| `isImage()` / `isVideo()` | 行 105-116 | 改用 `mat.file_type` 字段 |

### 4.13 `frontend/src/views/Settings.vue` — 新增存储配置区域

在"网络代理"和"发布设置"之间新增"文件存储"卡片：

- 存储类型 Radio 切换：本地存储 / S3 兼容存储
- 选择 S3 时展开配置表单：Endpoint、Access Key、Secret Key、Bucket、Region
- "测试连接"按钮
- 切换存储类型时弹出确认提示

### 4.14 `frontend/src/stores/app.js` — 清理无效代码

| 代码 | 说明 |
|------|------|
| `addMaterial()` action | 删除（从未被调用） |
| `materials` state | 保留，数据结构适配新字段 |

---

## 5. 后端新 Blueprint 详细设计

### `backend/blueprints/materials_bp.py`

```python
from flask import Blueprint, request, jsonify, send_file
from storage import get_storage
from conf import BASE_DIR
import sqlite3, uuid, os
from datetime import datetime

materials_bp = Blueprint('materials', __name__, url_prefix='/api/materials')

DB_PATH = BASE_DIR / "db" / "database.db"

def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def _guess_file_type(mime_type):
    """根据 MIME 类型判断文件类型"""
    if mime_type and mime_type.startswith('video/'):
        return 'video'
    return 'image'

@materials_bp.route('/upload', methods=['POST'])
def upload():
    """统一文件上传"""
    file = request.files.get('file')
    if not file:
        return jsonify({"code": 400, "msg": "未找到文件"})

    # 生成存储路径
    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    now = datetime.now()
    relative_path = f"materials/{now.strftime('%Y/%m/%d')}/{file_id}{ext}"

    # 通过存储后端保存
    storage = get_storage()
    file_data = file.read()
    storage.save(file_data, relative_path)

    # 获取文件信息
    mime_type = file.content_type or 'application/octet-stream'
    file_type = _guess_file_type(mime_type)
    file_size = len(file_data)

    # 写入数据库
    conn = _get_db()
    conn.execute(
        """INSERT INTO materials
           (id, original_filename, stored_path, file_type, mime_type, file_size, storage_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (file_id, file.filename, relative_path, file_type, mime_type, file_size, storage.type)
    )
    conn.commit()
    conn.close()

    # 构建访问 URL
    url = storage.get_url(relative_path)

    return jsonify({
        "code": 200,
        "msg": "上传成功",
        "data": {
            "id": file_id,
            "original_filename": file.filename,
            "stored_path": relative_path,
            "file_type": file_type,
            "mime_type": mime_type,
            "file_size": file_size,
            "url": url,
        }
    })

@materials_bp.route('/list', methods=['GET'])
def list_files():
    """获取素材列表"""
    file_type = request.args.get('type', 'all')
    conn = _get_db()
    if file_type == 'all':
        rows = conn.execute(
            "SELECT * FROM materials ORDER BY upload_time DESC"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM materials WHERE file_type = ? ORDER BY upload_time DESC",
            (file_type,)
        ).fetchall()

    storage = get_storage()
    result = []
    for row in rows:
        item = dict(row)
        item['url'] = storage.get_url(item['stored_path'])
        result.append(item)
    conn.close()
    return jsonify({"code": 200, "data": result})

@materials_bp.route('/<material_id>', methods=['DELETE'])
def delete(material_id):
    """删除素材"""
    conn = _get_db()
    row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"code": 404, "msg": "素材不存在"})

    # 删除文件
    storage = get_storage()
    storage.delete(row['stored_path'])

    # 删除记录
    conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return jsonify({"code": 200, "msg": "删除成功"})

@materials_bp.route('/file/<path:relative_path>')
def serve_file(relative_path):
    """文件访问"""
    storage = get_storage()
    # 本地存储: send_file
    # S3 存储: 重定向到 presigned URL
    return storage.serve(relative_path)
```

---

## 6. 后端存储实现详细设计

### `backend/storage/local.py`

```python
class LocalStorage(StorageBackend):
    type = 'local'

    def __init__(self, base_dir):
        self.base_dir = base_dir  # BASE_DIR

    def save(self, file_data: bytes, relative_path: str) -> str:
        full_path = self.base_dir / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_bytes(file_data)
        return relative_path

    def get(self, relative_path: str) -> bytes:
        full_path = self.base_dir / relative_path
        return full_path.read_bytes()

    def get_url(self, relative_path: str) -> str:
        return f"/api/materials/file/{relative_path}"

    def delete(self, relative_path: str) -> bool:
        full_path = self.base_dir / relative_path
        if full_path.exists():
            full_path.unlink()
            return True
        return False

    def exists(self, relative_path: str) -> bool:
        return (self.base_dir / relative_path).exists()

    def serve(self, relative_path: str):
        from flask import send_from_directory
        import os
        full_path = self.base_dir / relative_path
        directory = str(full_path.parent)
        filename = full_path.name
        return send_from_directory(directory, filename)
```

### `backend/storage/s3.py`

```python
class S3Storage(StorageBackend):
    type = 's3'

    def __init__(self, endpoint, access_key, secret_key, bucket, region=''):
        self.client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self.bucket = bucket

    def save(self, file_data: bytes, relative_path: str) -> str:
        self.client.put_object(
            Bucket=self.bucket,
            Key=relative_path,
            Body=file_data,
        )
        return relative_path

    def get(self, relative_path: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=relative_path)
        return resp['Body'].read()

    def get_url(self, relative_path: str) -> str:
        # 生成预签名 URL，有效期 1 小时
        return self.client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.bucket, 'Key': relative_path},
            ExpiresIn=3600,
        )

    def delete(self, relative_path: str) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=relative_path)
        return True

    def exists(self, relative_path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=relative_path)
            return True
        except:
            return False

    def serve(self, relative_path: str):
        from flask import redirect
        url = self.get_url(relative_path)
        return redirect(url)
```

---

## 7. 平台实现层适配

发布时，平台实现（`backend/impl/*/platform.py`）需要通过文件路径访问本地文件。需要修改这些文件路径的获取方式：

### 7.1 视频发布（`/postVideo`、`/postVideoBatch`）

**当前**: 前端传 `fileList: ["uuid_video.mp4"]`，后端平台实现拼接 `BASE_DIR / "videoFile" / filename`

**新方案**: 前端传 `fileList: ["materials/2026/05/31/uuid.mp4"]`，后端通过 `storage.get(stored_path)` 获取文件，或 `LocalStorage` 直接返回本地路径供 Playwright 使用

### 7.2 图文发布（`/api/image-publish/publish`）

**当前**: 后端从 `image_records` 查 `stored_filename`，拼接 `BASE_DIR / "image-publish" / stored_filename`

**新方案**: 从 `materials` 表查 `stored_path`，通过 `storage.get()` 获取文件

### 7.3 封面路径

**当前**: 前端传封面路径如 `uuid_cover.jpg`，后端拼接 `videoFile` 目录

**新方案**: 前端传 `stored_path`，后端通过存储抽象层获取文件

### 7.4 抽帧（`/api/extract-frames`）

**当前**: `_resolve_video_path()` 先尝试 `BASE_DIR / "videoFile" / video_path`

**新方案**: 从 `materials` 表查 `stored_path`，本地存储直接用 `BASE_DIR / stored_path`

---

## 8. 改动汇总清单

### 8.1 新增文件（7 个）

| 文件 | 说明 |
|------|------|
| `backend/storage/__init__.py` | 存储模块导出 |
| `backend/storage/base.py` | 抽象基类 |
| `backend/storage/local.py` | 本地存储实现 |
| `backend/storage/s3.py` | S3 存储实现 |
| `backend/blueprints/materials_bp.py` | 统一素材路由 |
| `frontend/src/api/materials.js` | 统一前端素材 API |
| `frontend/src/utils/storage.js` | 统一 URL 构建工具 |

### 8.2 删除文件（1 个）

| 文件 | 说明 |
|------|------|
| `frontend/src/api/material.js` | 旧素材 API，全部功能由 `materials.js` 替代 |

### 8.3 后端修改文件（5 个）

| 文件 | 删除内容 | 修改内容 |
|------|---------|---------|
| `backend/app.py` | 删除 7 个旧路由 + `_VIDEOFILE_DIR` 相关代码（行 99-291） | 注册 `materials_bp`；修改 `/postVideo`、`/postVideoBatch` 的文件路径处理 |
| `backend/blueprints/image_publish_bp.py` | 删除 `UPLOAD_DIR`、`ALLOWED_EXTENSIONS`、3 个文件操作路由（行 25-134） | 修改 `/publish`、`/execute-publish` 中的文件查询逻辑；修改 `_extract_image_draft_cover()` |
| `backend/routes/frames.py` | — | 修改 `_resolve_video_path()` 从 `materials` 表查文件 |
| `backend/init_db.py` | — | 新增 `materials` 表创建语句 |
| `backend/conf.py` | — | 无改动 |

### 8.4 前端修改文件（11 个）

| 文件 | 改动范围 |
|------|---------|
| `frontend/src/views/PublishCenter.vue` | 重写视频上传、素材选择、URL 构建、发布数据组装、草稿序列化 |
| `frontend/src/components/CoverCard.vue` | 重写封面上传函数 |
| `frontend/src/components/CoverEditorDialog.vue` | 重写封面保存上传 |
| `frontend/src/components/ImageUploader.vue` | 重写图片上传函数，修复双重 URL bug |
| `frontend/src/components/ImageCoverUpload.vue` | 重写封面上传 |
| `frontend/src/components/MaterialSelectDialog.vue` | 重写素材加载、URL 构建、选择确认 |
| `frontend/src/views/MaterialManagement.vue` | 重写素材 CRUD 全部函数 |
| `frontend/src/views/ImagePublish.vue` | 修改素材库选择回调、发布数据组装、草稿恢复 |
| `frontend/src/views/Settings.vue` | 新增存储配置区域 |
| `frontend/src/stores/app.js` | 删除 `addMaterial`，适配新数据结构 |
| `frontend/src/api/imagePublish.js` | 修改 `uploadImage` 调用新 API |

---

## 9. 依赖新增

| 依赖 | 用途 | 安装 |
|------|------|------|
| `boto3` | S3 兼容存储客户端 | `pip install boto3` |

---

## 10. 测试计划

1. **本地存储测试**: 上传视频/图片 → 列表显示 → 预览 → 删除 → 确认文件和记录都删除
2. **视频发布测试**: 上传视频 → 选封面 → 发布到平台 → 确认文件正确传递
3. **图文发布测试**: 上传多图 → 选封面 → 发布到平台 → 确认图片正确传递
4. **素材库选择测试**: 从素材库选择视频/图片 → 确认 URL 可用 → 确认发布数据正确
5. **S3 存储测试**: 配置 MinIO → 上传 → 列表 → 预览（presigned URL） → 删除
6. **设置切换测试**: 本地 ↔ S3 切换 → 确认新上传走新后端
7. **草稿测试**: 保存草稿 → 恢复草稿 → 确认文件 URL 正确
8. **抽帧测试**: 上传视频 → 提取帧 → 确认帧图片正常显示
