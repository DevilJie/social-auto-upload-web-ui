# 素材库统一存储重构 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 废弃 `file_records`/`image_records` 两套存储体系，建立统一的 `materials` 表 + 存储抽象层，支持本地存储和 S3 兼容存储。

**Architecture:** 后端 `backend/storage/` 模块提供 `StorageBackend` 抽象接口，`LocalStorage` 和 `S3Storage` 两个实现。新 Blueprint `materials_bp.py` 提供统一 CRUD 路由。前端新增 `api/materials.js` + `utils/storage.js`，所有组件改用统一接口。

**Tech Stack:** Python/Flask (后端), Vue 3 + Element Plus (前端), SQLite (数据库), boto3 (S3 客户端)

**Spec:** `docs/superpowers/specs/2026-05-31-unified-storage-design.md`

---

## Phase 1: 后端基础 — 存储抽象层 + 数据库

### Task 1: 创建存储抽象层

**Files:**
- Create: `backend/storage/__init__.py`
- Create: `backend/storage/base.py`

- [ ] **Step 1: 创建 `backend/storage/base.py`**

```python
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    type: str = ""

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

    @abstractmethod
    def serve(self, relative_path: str):
        """Flask 响应：本地返回文件，S3 重定向到 presigned URL"""

    def get_local_path(self, relative_path: str) -> str | None:
        """获取本地文件绝对路径（仅 LocalStorage 有意义）"""
        return None
```

- [ ] **Step 2: 创建 `backend/storage/__init__.py`**

```python
import json
from pathlib import Path
from conf import BASE_DIR

_storage_instance = None


def get_storage():
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    settings_file = BASE_DIR / "settings.json"
    storage_type = "local"
    s3_config = {}

    if settings_file.exists():
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            storage_cfg = settings.get("storage", {})
            storage_type = storage_cfg.get("type", "local")
            s3_config = storage_cfg.get("s3", {})
        except (json.JSONDecodeError, OSError):
            pass

    if storage_type == "s3" and s3_config.get("endpoint"):
        from storage.s3 import S3Storage
        _storage_instance = S3Storage(
            endpoint=s3_config["endpoint"],
            access_key=s3_config.get("access_key", ""),
            secret_key=s3_config.get("secret_key", ""),
            bucket=s3_config.get("bucket", ""),
            region=s3_config.get("region", ""),
        )
    else:
        from storage.local import LocalStorage
        _storage_instance = LocalStorage(BASE_DIR)

    return _storage_instance


def reset_storage():
    """切换存储配置后调用，下次 get_storage() 会重新创建实例"""
    global _storage_instance
    _storage_instance = None
```

- [ ] **Step 3: 验证模块可导入**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "from storage.base import StorageBackend; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/storage/__init__.py backend/storage/base.py
git commit -m "feat: 新增存储抽象层基础类和工厂函数"
```

---

### Task 2: 实现 LocalStorage

**Files:**
- Create: `backend/storage/local.py`

- [ ] **Step 1: 创建 `backend/storage/local.py`**

```python
from flask import send_from_directory
from pathlib import Path

from storage.base import StorageBackend


class LocalStorage(StorageBackend):
    type = "local"

    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)

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
        full_path = self.base_dir / relative_path
        directory = str(full_path.parent)
        filename = full_path.name
        return send_from_directory(directory, filename)

    def get_local_path(self, relative_path: str) -> str | None:
        full_path = self.base_dir / relative_path
        if full_path.exists():
            return str(full_path)
        return None
```

- [ ] **Step 2: 验证 LocalStorage 可导入**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "from storage.local import LocalStorage; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/storage/local.py
git commit -m "feat: 实现 LocalStorage 本地存储后端"
```

---

### Task 3: 实现 S3Storage

**Files:**
- Create: `backend/storage/s3.py`

- [ ] **Step 1: 创建 `backend/storage/s3.py`**

```python
from flask import redirect

from storage.base import StorageBackend


class S3Storage(StorageBackend):
    type = "s3"

    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, region: str = ""):
        import boto3
        self.client = boto3.client(
            "s3",
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
        return resp["Body"].read()

    def get_url(self, relative_path: str) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": relative_path},
            ExpiresIn=3600,
        )

    def delete(self, relative_path: str) -> bool:
        self.client.delete_object(Bucket=self.bucket, Key=relative_path)
        return True

    def exists(self, relative_path: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=relative_path)
            return True
        except Exception:
            return False

    def serve(self, relative_path: str):
        url = self.get_url(relative_path)
        return redirect(url)
```

- [ ] **Step 2: 验证 S3Storage 可导入（boto3 懒加载，无需实际连接）**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "from storage.s3 import S3Storage; print('OK')"`
Expected: `OK`（如果 boto3 未安装，先 `pip install boto3`）

- [ ] **Step 3: Commit**

```bash
git add backend/storage/s3.py
git commit -m "feat: 实现 S3Storage S3 兼容存储后端"
```

---

### Task 4: 数据库新增 materials 表

**Files:**
- Modify: `backend/init_db.py`

- [ ] **Step 1: 在 `init_db.py` 的 `init_database()` 函数中追加 `materials` 表创建语句**

在 `init_db.py` 中找到创建 `image_records` 表的 SQL（约行 141-151），在其后追加：

```python
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS materials (
            id TEXT PRIMARY KEY,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER DEFAULT 0,
            storage_type TEXT NOT NULL DEFAULT 'local',
            width INTEGER DEFAULT 0,
            height INTEGER DEFAULT 0,
            duration REAL DEFAULT 0,
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
```

- [ ] **Step 2: 运行 init_db.py 确认建表成功**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui && python3 backend/init_db.py`
Expected: 无报错

- [ ] **Step 3: 验证表已创建**

Run: `sqlite3 data/db/database.db ".schema materials"`
Expected: 显示 materials 表的 CREATE TABLE 语句

- [ ] **Step 4: Commit**

```bash
git add backend/init_db.py
git commit -m "feat: 数据库新增 materials 统一素材表"
```

---

## Phase 2: 后端路由 — 统一素材 Blueprint

### Task 5: 创建 materials_bp.py 统一素材路由

**Files:**
- Create: `backend/blueprints/materials_bp.py`

- [ ] **Step 1: 创建 `backend/blueprints/materials_bp.py`**

```python
import os
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, request, jsonify

from conf import BASE_DIR

materials_bp = Blueprint("materials", __name__, url_prefix="/api/materials")

DB_PATH = BASE_DIR / "db" / "database.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _guess_file_type(mime_type):
    if mime_type and mime_type.startswith("video/"):
        return "video"
    return "image"


@materials_bp.route("/upload", methods=["POST"])
def upload():
    """统一文件上传"""
    from storage import get_storage

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"code": 400, "msg": "未找到文件"})

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1].lower()
    now = datetime.now()
    relative_path = f"materials/{now.strftime('%Y/%m/%d')}/{file_id}{ext}"

    storage = get_storage()
    file_data = file.read()
    storage.save(file_data, relative_path)

    mime_type = file.content_type or "application/octet-stream"
    file_type = _guess_file_type(mime_type)
    file_size = len(file_data)

    conn = _get_db()
    conn.execute(
        """INSERT INTO materials
           (id, original_filename, stored_path, file_type, mime_type, file_size, storage_type)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (file_id, file.filename, relative_path, file_type, mime_type, file_size, storage.type),
    )
    conn.commit()
    conn.close()

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
        },
    })


@materials_bp.route("/list", methods=["GET"])
def list_files():
    """获取素材列表"""
    from storage import get_storage

    file_type = request.args.get("type", "all")
    conn = _get_db()
    if file_type in ("video", "image"):
        rows = conn.execute(
            "SELECT * FROM materials WHERE file_type = ? ORDER BY upload_time DESC",
            (file_type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM materials ORDER BY upload_time DESC"
        ).fetchall()

    storage = get_storage()
    result = []
    for row in rows:
        item = dict(row)
        item["url"] = storage.get_url(item["stored_path"])
        result.append(item)
    conn.close()
    return jsonify({"code": 200, "data": result})


@materials_bp.route("/<material_id>", methods=["DELETE"])
def delete(material_id):
    """删除素材"""
    from storage import get_storage

    conn = _get_db()
    row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"code": 404, "msg": "素材不存在"})

    storage = get_storage()
    storage.delete(row["stored_path"])

    conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
    conn.commit()
    conn.close()
    return jsonify({"code": 200, "msg": "删除成功"})


@materials_bp.route("/file/<path:relative_path>")
def serve_file(relative_path):
    """文件访问"""
    from storage import get_storage

    storage = get_storage()
    return storage.serve(relative_path)
```

- [ ] **Step 2: 在 `app.py` 中注册 Blueprint**

在 `backend/app.py` 中找到其他 Blueprint 的注册位置（搜索 `register_blueprint`），在其附近添加：

```python
from blueprints.materials_bp import materials_bp
app.register_blueprint(materials_bp)
```

- [ ] **Step 3: 启动后端，验证新接口可用**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 app.py &`（后台启动）
然后: `curl -s http://localhost:5409/api/materials/list | python3 -m json.tool`
Expected: `{"code": 200, "data": []}`

- [ ] **Step 4: 验证上传接口**

```bash
echo "test" > /tmp/test.txt
curl -s -F "file=@/tmp/test.txt" http://localhost:5409/api/materials/upload | python3 -m json.tool
```
Expected: 返回 `{"code": 200, "msg": "上传成功", "data": {...}}`

- [ ] **Step 5: 停止后端，Commit**

```bash
kill %1
git add backend/blueprints/materials_bp.py backend/app.py
git commit -m "feat: 新增统一素材路由 Blueprint 并注册"
```

---

## Phase 3: 后端清理 — 删除旧路由，适配发布逻辑

### Task 6: 删除 app.py 中的旧文件路由

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: 删除 `_get_videofile_dir()` 函数和 `_VIDEOFILE_DIR` 变量**

删除 `app.py` 中行 99-106 的 `_get_videofile_dir()` 函数和 `_VIDEOFILE_DIR` 全局变量。

- [ ] **Step 2: 删除 `serve_videofile` 路由（`/<path:filename>` catch-all）**

删除 `app.py` 中行 109-118 的 `@app.route('/<path:filename>')` 路由。

- [ ] **Step 3: 删除 `upload_file` 路由（`POST /upload`）**

删除 `app.py` 中行 144-168 的 `upload_file` 函数。

- [ ] **Step 4: 删除 `get_file` 路由（`GET /getFile`）**

删除 `app.py` 中行 171-178 的 `get_file` 函数。

- [ ] **Step 5: 删除 `upload_save` 路由（`POST /uploadSave`）**

删除 `app.py` 中行 181-212 的 `upload_save` 函数。

- [ ] **Step 6: 删除 `get_all_files` 路由（`GET /getFiles`）**

删除 `app.py` 中行 215-256 的 `get_all_files` 函数。

- [ ] **Step 7: 删除 `delete_file` 路由（`GET /deleteFile`）**

删除 `app.py` 中行 259-291 的 `delete_file` 函数。

- [ ] **Step 8: 删除不再需要的 `uuid` import（如果仅被旧路由使用）**

检查 `import uuid` 是否还有其他引用（如 `postVideo` 中可能用到）。如果仅在已删除的路由中使用，删除该 import。

- [ ] **Step 9: Commit**

```bash
git add backend/app.py
git commit -m "refactor: 删除 app.py 中的旧文件上传/获取/删除路由"
```

---

### Task 7: 修改 app.py 中的 postVideo/postVideoBatch 适配新存储

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: 修改 `postVideo` 路由中的文件路径处理**

在 `postVideo` 函数（行 555-631）中，找到 `data.get('fileList', [])` 和 `thumbnailLandscape`/`thumbnailPortrait` 相关代码。将文件路径从旧格式（`videoFile` 目录下的文件名）改为通过 `materials` 表查 `stored_path`，然后用 `storage.get_local_path()` 获取本地绝对路径：

在 `postVideo` 函数开头添加辅助逻辑：

```python
from storage import get_storage

def _resolve_material_path(path_or_stored_path):
    """从 stored_path 获取本地文件绝对路径"""
    storage = get_storage()
    local = storage.get_local_path(path_or_stored_path)
    if local:
        return local
    # 兼容：如果不是 stored_path 格式，尝试作为旧路径直接返回
    return path_or_stored_path
```

在 `postVideo` 中构建 `publish_data` 的地方：
- `fileList` 中每个路径调用 `_resolve_material_path()` 转换
- `thumbnailLandscape` / `thumbnailPortrait` 同样调用 `_resolve_material_path()` 转换

- [ ] **Step 2: 同样修改 `postVideoBatch`（行 634-710）**

与 Step 1 相同的路径转换逻辑。

- [ ] **Step 3: 验证启动不报错**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "from app import app; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "refactor: postVideo/postVideoBatch 适配新的存储路径格式"
```

---

### Task 8: 删除 image_publish_bp.py 中的旧文件路由，适配新存储

**Files:**
- Modify: `backend/blueprints/image_publish_bp.py`

- [ ] **Step 1: 删除旧常量**

删除 `UPLOAD_DIR = BASE_DIR / "image-publish"` 和 `ALLOWED_EXTENSIONS` 常量。

- [ ] **Step 2: 删除 `upload_image` 路由（`POST /upload`）**

删除行 43-89 的 `upload_image` 函数。

- [ ] **Step 3: 删除 `serve_image` 路由（`GET /files/<filepath>`）**

删除行 94-104 的 `serve_image` 函数。

- [ ] **Step 4: 删除 `delete_image` 路由（`DELETE /images/<image_id>`）**

删除行 109-134 的 `delete_image` 函数。

- [ ] **Step 5: 修改 `publish_images` 中的文件路径查询**

在行 179-186 处，将：
```python
row = conn.execute("SELECT stored_filename FROM image_records WHERE id = ?", (img_id,)).fetchone()
image_files.append(row['stored_filename'])
```
改为：
```python
row = conn.execute("SELECT stored_path FROM materials WHERE id = ?", (img_id,)).fetchone()
if row:
    from storage import get_storage
    storage = get_storage()
    local_path = storage.get_local_path(row['stored_path'])
    image_files.append(local_path or row['stored_path'])
```

- [ ] **Step 6: 修改 `_extract_image_draft_cover` 函数**

将函数改为直接返回 `stored_path`，不再解析旧 URL 格式：

```python
def _extract_image_draft_cover(draft_data):
    """从图文草稿数据中提取封面路径"""
    common_config = draft_data.get('commonConfig', {})

    cover = common_config.get('coverImage')
    if cover and isinstance(cover, dict):
        stored_path = cover.get('stored_path', '')
        if stored_path:
            return stored_path
        # 兼容旧草稿：从 path 字段提取
        path = cover.get('path', '')
        if path:
            return path

    images = common_config.get('images', [])
    if images:
        img = images[0]
        if isinstance(img, dict):
            return img.get('stored_path', '') or img.get('path', '')
    return ''
```

- [ ] **Step 7: 修改 `execute_publish` 中的文件路径查询（行 583-590）**

同 Step 5，从 `materials` 表查 `stored_path`。

- [ ] **Step 8: Commit**

```bash
git add backend/blueprints/image_publish_bp.py
git commit -m "refactor: 删除图文发布旧文件路由，适配新存储"
```

---

### Task 9: 修改 frames.py 中的视频路径解析

**Files:**
- Modify: `backend/routes/frames.py`

- [ ] **Step 1: 重写 `_resolve_video_path` 函数**

将行 17-23 的：
```python
def _resolve_video_path(video_path):
    full_path = os.path.join(str(BASE_DIR), 'videoFile', video_path)
    if os.path.isfile(full_path):
        return full_path
    if os.path.isfile(video_path):
        return video_path
    return None
```

改为：
```python
def _resolve_video_path(video_path):
    from storage import get_storage
    storage = get_storage()
    # 优先作为 stored_path 查找
    local = storage.get_local_path(video_path)
    if local:
        return local
    # 兼容：直接尝试文件路径
    if os.path.isfile(video_path):
        return video_path
    return None
```

- [ ] **Step 2: Commit**

```bash
git add backend/routes/frames.py
git commit -m "refactor: 抽帧路由适配新的存储路径格式"
```

---

### Task 10: 修改 settings 路由支持 storage 配置

**Files:**
- Modify: `backend/app.py`（settings 路由区域，行 713-742）

- [ ] **Step 1: 在 `PUT /api/v2/settings` 路由中添加 storage 配置变更时重置存储实例**

在 `api_update_settings` 函数（行 736-742）中，写完 settings 后检查 storage 配置是否变更：

```python
@app.route('/api/v2/settings', methods=['PUT'])
def api_update_settings():
    data = request.get_json(force=True)
    old_settings = _read_settings()
    new_settings = {**old_settings, **data}
    _write_settings(new_settings)

    # 如果存储配置变更，重置存储实例
    if data.get('storage'):
        from storage import reset_storage
        reset_storage()

    return jsonify({"code": 200, "msg": "设置已更新"})
```

- [ ] **Step 2: 新增 S3 连接测试路由**

在 `materials_bp.py` 末尾添加：

```python
@materials_bp.route("/test-s3", methods=["POST"])
def test_s3_connection():
    """测试 S3 连接"""
    data = request.get_json(force=True)
    try:
        import boto3
        client = boto3.client(
            "s3",
            endpoint_url=data.get("endpoint", ""),
            aws_access_key_id=data.get("access_key", ""),
            aws_secret_access_key=data.get("secret_key", ""),
            region_name=data.get("region", ""),
        )
        client.head_bucket(Bucket=data.get("bucket", ""))
        return jsonify({"code": 200, "msg": "连接成功"})
    except Exception as e:
        return jsonify({"code": 400, "msg": f"连接失败: {str(e)}"})
```

- [ ] **Step 3: Commit**

```bash
git add backend/app.py backend/blueprints/materials_bp.py
git commit -m "feat: settings 路由支持存储配置，新增 S3 连接测试接口"
```

---

## Phase 4: 前端基础 — API 层 + 工具函数

### Task 11: 创建前端统一 API 和 URL 工具

**Files:**
- Create: `frontend/src/api/materials.js`
- Create: `frontend/src/utils/storage.js`
- Delete: `frontend/src/api/material.js`

- [ ] **Step 1: 创建 `frontend/src/utils/storage.js`**

```javascript
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5409'

/**
 * 统一文件 URL 构建
 * @param {string} storedPath - 相对路径，如 "materials/2026/05/31/uuid.jpg"
 */
export function getFileUrl(storedPath) {
  if (!storedPath) return ''
  if (storedPath.startsWith('http')) return storedPath
  return `${BASE_URL}/api/materials/file/${storedPath}`
}
```

- [ ] **Step 2: 创建 `frontend/src/api/materials.js`**

```javascript
import http from '@/utils/request'

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

- [ ] **Step 3: 删除 `frontend/src/api/material.js`**

删除整个文件。

- [ ] **Step 4: Commit**

```bash
git add frontend/src/utils/storage.js frontend/src/api/materials.js
git rm frontend/src/api/material.js
git commit -m "feat: 新增前端统一素材 API 和 URL 工具，删除旧 material.js"
```

---

### Task 12: 修改前端 Store 清理无效代码

**Files:**
- Modify: `frontend/src/stores/app.js`

- [ ] **Step 1: 删除 `addMaterial` action**

删除 `app.js` 中行 101-104 的 `addMaterial` 函数，并从 `return` 语句中移除。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/stores/app.js
git commit -m "refactor: 删除 store 中未使用的 addMaterial action"
```

---

## Phase 5: 前端组件重写

### Task 13: 重写 PublishCenter.vue — 上传和素材选择

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`

这是最大的改动。逐项修改：

- [ ] **Step 1: 替换 import**

将所有 `materialApi` 相关 import 替换为：
```javascript
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
```
删除旧的 `import * as materialApi from '@/api/material'` 或 `import { materialApi } from '@/api/material'`。

- [ ] **Step 2: 修改 `el-upload` 改用自定义上传方法**

行 547-564 的 `<el-upload>` 组件：
- 删除 `:action="\`${apiBaseUrl}/uploadSave\`"` 属性
- 删除 `:headers="authHeaders"` 属性
- 添加 `:http-request="handleVideoUpload"` 属性
- 保留 `:on-success` 和 `:on-error`（需要配合 http-request 调整）

或者更简单的方式：将 `el-upload` 改为 `:auto-upload="false"`，在文件选择后手动调用 `materialsApi.upload()`。

- [ ] **Step 3: 重写 `handleVideoUploadSuccess`（行 1073-1121）**

```javascript
async function handleVideoUpload(options) {
  const file = options.file
  const formData = new FormData()
  formData.append('file', file)
  try {
    const resp = await materialsApi.upload(formData)
    if (resp.code === 200) {
      const d = resp.data
      const videoData = {
        name: d.original_filename,
        url: getFileUrl(d.stored_path),
        stored_path: d.stored_path,
        size: d.file_size,
        type: d.mime_type,
      }
      if (videoUploadTarget.value === 'portrait') {
        commonConfig.videoPortrait = videoData
      } else {
        commonConfig.videoLandscape = videoData
      }
      videoUploadDialogVisible.value = false
      ElMessage.success('视频上传成功')
      // 自动填充标题
      if (appStore.autoFillTitle) {
        const title = file.name.replace(/\.[^.]+$/, '')
        for (const key of Object.keys(platformConfigs)) {
          platformConfigs[key].title = title
        }
        for (const group of accountGroups.value) {
          for (const account of group.accounts) {
            if (accountOverrides[account.id]?.title) {
              accountOverrides[account.id].title = title
            }
          }
        }
        if (selectedPlatform.value) {
          const accountId = selectedAccountId.value
          if (accountId && accountOverrides[accountId]?.title) {
            form.title = accountOverrides[accountId].title
          } else if (platformConfigs[selectedPlatform.value]) {
            form.title = platformConfigs[selectedPlatform.value].title
          }
        }
      }
      triggerFrameExtraction(videoData, videoUploadTarget.value)
    } else {
      ElMessage.error(resp.msg || '上传失败')
    }
  } catch (error) {
    ElMessage.error('视频上传失败')
  }
}
```

同时删除旧的 `handleVideoUploadSuccess` 函数。

- [ ] **Step 4: 修改 `selectFromLibrary`（行 1129-1152）**

将 `materialApi.getAllMaterials()` 替换为 `materialsApi.list()`：
```javascript
const response = await materialsApi.list()
```

- [ ] **Step 5: 重写 `confirmMaterialSelect`（行 1154-1218）**

封面分支：
```javascript
const coverData = {
  name: material.original_filename,
  url: getFileUrl(material.stored_path),
  stored_path: material.stored_path,
  size: material.file_size,
  type: material.mime_type,
}
```

视频分支：
```javascript
const videoData = {
  name: material.original_filename,
  url: getFileUrl(material.stored_path),
  stored_path: material.stored_path,
  size: material.file_size,
  type: material.mime_type,
}
```

- [ ] **Step 6: 修改 `filteredMaterials` computed**

行 970-976：改用 `material.file_type` 过滤：
```javascript
const filteredMaterials = computed(() => {
  const list = materials.value
  if (materialLibraryMode.value === 'cover') {
    return list.filter(m => m.file_type === 'image')
  }
  return list.filter(m => m.file_type === 'video')
})
```

- [ ] **Step 7: 修改 `publishAll` 中的文件路径（行 1638, 1641-1642）**

```javascript
fileList: [selectedVideo.stored_path],
// ...
thumbnailLandscape: commonConfig.coverLandscape ? commonConfig.coverLandscape.stored_path : '',
thumbnailPortrait: commonConfig.coverPortrait ? commonConfig.coverPortrait.stored_path : '',
```

- [ ] **Step 8: 修改 `saveDraft`（行 1292-1330）**

将序列化中的 `path` 改为 `stored_path`：
```javascript
videoLandscape: commonConfig.videoLandscape
  ? { name, stored_path: commonConfig.videoLandscape.stored_path, url, size, type }
  : null,
```

- [ ] **Step 9: 修改 `restoreDraft`（行 1332-1407）**

恢复时用 `getFileUrl()` 重新生成 `url`：
```javascript
if (dd.commonConfig.videoLandscape) {
  const v = dd.commonConfig.videoLandscape
  if (v.stored_path) v.url = getFileUrl(v.stored_path)
  commonConfig.videoLandscape = v
}
```

- [ ] **Step 10: 删除 `apiBaseUrl` 和 `authHeaders`（如果不再被其他地方使用）**

检查这两个变量是否还有其他引用。如果仅被 `el-upload` 使用，可以删除。

- [ ] **Step 11: 验证前端编译通过**

Run: `cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run build 2>&1 | tail -5`
Expected: 无报错

- [ ] **Step 12: Commit**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "refactor: 重写视频发布界面上传、素材选择、URL 构建、发布逻辑"
```

---

### Task 14: 重写 CoverCard.vue

**Files:**
- Modify: `frontend/src/components/CoverCard.vue`

- [ ] **Step 1: 替换 import 并重写 `onFileSelected`**

```javascript
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'

async function onFileSelected(e) {
  const file = e.target.files?.[0]
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const resp = await materialsApi.upload(formData)
    if (resp.code === 200) {
      const d = resp.data
      emit('update:modelValue', {
        name: d.original_filename,
        url: getFileUrl(d.stored_path),
        stored_path: d.stored_path,
        size: d.file_size,
        type: d.mime_type,
      })
      ElMessage.success('封面上传成功')
    } else {
      ElMessage.error(resp.msg || '上传失败')
    }
  } catch {
    ElMessage.error('上传失败')
  }
  e.target.value = ''
}
```

- [ ] **Step 2: 删除旧的 `import { http } from '@/utils/request'` 和 `import { materialApi } from '@/api/material'`**

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/CoverCard.vue
git commit -m "refactor: 重写 CoverCard 封面上传使用统一存储"
```

---

### Task 15: 重写 CoverEditorDialog.vue

**Files:**
- Modify: `frontend/src/components/CoverEditorDialog.vue`

- [ ] **Step 1: 找到封面上传逻辑（约行 407-413）并重写**

替换 `http.post('/upload', ...)` 为 `materialsApi.upload()`，使用 `getFileUrl()` 构建 URL，数据结构改为 `{ name, url, stored_path, size, type }`。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/CoverEditorDialog.vue
git commit -m "refactor: 重写封面编辑器上传使用统一存储"
```

---

### Task 16: 重写 ImageUploader.vue

**Files:**
- Modify: `frontend/src/components/ImageUploader.vue`

- [ ] **Step 1: 替换 import**

将 `import { imagePublishApi } from '@/api/imagePublish'` 替换为：
```javascript
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
```
如果组件内还用了 `imagePublishApi` 的其他方法（如 publishImage），保留相关 import。

- [ ] **Step 2: 重写 `uploadFile` 函数（行 183-243）**

```javascript
async function uploadFile(file) {
  // 验证文件类型和大小
  const validTypes = ['image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/bmp']
  if (!validTypes.includes(file.type)) {
    ElMessage.warning('不支持的图片格式')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    ElMessage.warning('图片大小不能超过 10MB')
    return
  }

  // 创建占位符
  const placeholder = {
    id: `temp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: file.name,
    url: URL.createObjectURL(file),
    stored_path: '',
    size: file.size,
    type: file.type,
    uploading: true,
    progress: 0,
  }
  images.value.push(placeholder)
  const index = images.value.length - 1

  try {
    const formData = new FormData()
    formData.append('file', file)
    const resp = await materialsApi.upload(formData, (percent) => {
      images.value[index].progress = percent
    })
    if (resp.code === 200) {
      const d = resp.data
      images.value[index] = {
        id: d.id,
        name: d.original_filename,
        url: getFileUrl(d.stored_path),
        stored_path: d.stored_path,
        size: d.file_size,
        type: d.mime_type,
        uploading: false,
        progress: 100,
      }
    }
  } catch {
    images.value.splice(index, 1)
    ElMessage.error('图片上传失败')
  }
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ImageUploader.vue
git commit -m "refactor: 重写 ImageUploader 使用统一存储，修复双重 URL bug"
```

---

### Task 17: 重写 ImageCoverUpload.vue

**Files:**
- Modify: `frontend/src/components/ImageCoverUpload.vue`

- [ ] **Step 1: 替换 import 并重写 `onFileSelected`（行 74-113）**

与 CoverCard.vue 相同模式：用 `materialsApi.upload()` + `getFileUrl()`，数据结构用 `stored_path`。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/ImageCoverUpload.vue
git commit -m "refactor: 重写 ImageCoverUpload 使用统一存储"
```

---

### Task 18: 重写 MaterialSelectDialog.vue

**Files:**
- Modify: `frontend/src/components/MaterialSelectDialog.vue`

- [ ] **Step 1: 替换 import**

删除 `import * as materialApi from '@/api/material'`，改为：
```javascript
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
```

- [ ] **Step 2: 重写 `loadMaterials`（行 168-183）**

```javascript
async function loadMaterials() {
  loading.value = true
  try {
    const resp = await materialsApi.list(props.filterType)
    if (resp.code === 200) {
      materials.value = resp.data || []
    }
  } catch (e) {
    console.error('加载素材失败:', e)
  }
  loading.value = false
}
```

- [ ] **Step 3: 简化 `getMaterialUrl`（行 134-147）**

```javascript
function getMaterialUrl(mat) {
  return getFileUrl(mat.stored_path)
}
```

- [ ] **Step 4: 重写 `confirmSelect`（行 185-207）**

```javascript
function confirmSelect() {
  if (!selectedId.value) return
  const material = materials.value.find(m => m.id === selectedId.value)
  if (!material) return
  emit('select', {
    id: material.id,
    name: material.original_filename,
    url: getFileUrl(material.stored_path),
    stored_path: material.stored_path,
    size: material.file_size,
    type: material.mime_type,
  })
  dialogVisible.value = false
}
```

- [ ] **Step 5: 重写类型判断（行 105-116）**

```javascript
const isImage = (mat) => mat.file_type === 'image'
const isVideo = (mat) => mat.file_type === 'video'
```

- [ ] **Step 6: 修改模板中的字段引用**

将 `mat.filename` 替换为 `mat.original_filename`，`mat.filesize` 替换为格式化后的 `mat.file_size`。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/MaterialSelectDialog.vue
git commit -m "refactor: 重写素材选择对话框使用统一存储"
```

---

### Task 19: 重写 MaterialManagement.vue

**Files:**
- Modify: `frontend/src/views/MaterialManagement.vue`

- [ ] **Step 1: 替换 import**

```javascript
import { materialsApi } from '@/api/materials'
import { getFileUrl } from '@/utils/storage'
```

- [ ] **Step 2: 重写 `fetchMaterials`（行 232-249）**

```javascript
async function fetchMaterials() {
  loading.value = true
  try {
    const response = await materialsApi.list()
    if (response.code === 200) {
      appStore.setMaterials(response.data)
    }
  } catch (error) {
    ElMessage.error('获取素材列表失败')
  }
  loading.value = false
}
```

- [ ] **Step 3: 重写 `submitUpload`（行 321-388）**

核心改动：将 `materialApi.uploadMaterial` 改为 `materialsApi.upload`。

- [ ] **Step 4: 重写 `handleDelete`（行 407-435）**

```javascript
async function handleDelete(material) {
  try {
    await ElMessageBox.confirm('确定要删除该素材吗？', '提示', { type: 'warning' })
    const resp = await materialsApi.delete(material.id)
    if (resp.code === 200) {
      appStore.removeMaterial(material.id)
      ElMessage.success('删除成功')
    }
  } catch {}
}
```

- [ ] **Step 5: 替换 `getPreviewUrl`（行 438-451）**

```javascript
function getPreviewUrl(material) {
  return getFileUrl(material.stored_path)
}
```

- [ ] **Step 6: 替换 `downloadFile`（行 454-457）**

```javascript
function downloadFile(material) {
  window.open(getFileUrl(material.stored_path), '_blank')
}
```

- [ ] **Step 7: 修改模板中的字段引用**

- `material.filename` → `material.original_filename`
- `material.filesize` → 需要从字节格式化显示（`formatSize(material.file_size)`）
- `material.upload_time` → 保持不变
- `isVideoFile(material)` → `material.file_type === 'video'`
- `isImageFile(material)` → `material.file_type === 'image'`

- [ ] **Step 8: 删除 `isVideoFile` / `isImageFile` 函数和旧的扩展名判断**

- [ ] **Step 9: Commit**

```bash
git add frontend/src/views/MaterialManagement.vue
git commit -m "refactor: 重写素材管理页面使用统一存储"
```

---

### Task 20: 修改 ImagePublish.vue

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`

- [ ] **Step 1: 添加 import**

```javascript
import { getFileUrl } from '@/utils/storage'
```

- [ ] **Step 2: 修改 `onMaterialSelected`（行 844-883）**

构造 imageData 时使用新字段：
```javascript
const imageData = {
  id: material.id,
  name: material.name,
  url: material.url,
  stored_path: material.stored_path,
  size: material.size,
  type: material.type,
  uploading: false,
  progress: 100,
}
```

- [ ] **Step 3: 修改 `publishAll` 中的 cover_path（行 1227）**

```javascript
cover_path: commonConfig.coverImage?.stored_path || ''
```

- [ ] **Step 4: 修改 `saveDraft` 和 `loadDraft`**

草稿序列化/反序列化时使用 `stored_path` 字段。`loadDraft` 恢复时用 `getFileUrl(img.stored_path)` 重新生成 URL。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ImagePublish.vue
git commit -m "refactor: 修改图文发布页面适配新存储格式"
```

---

### Task 21: 修改 imagePublish.js API 层

**Files:**
- Modify: `frontend/src/api/imagePublish.js`

- [ ] **Step 1: 修改 `uploadImage` 函数（行 6-15）**

改为使用 `materialsApi.upload()`：

```javascript
import { materialsApi } from '@/api/materials'

export const imagePublishApi = {
  uploadImage(file, onProgress) {
    const formData = new FormData()
    formData.append('file', file)
    return materialsApi.upload(formData, (progressEvent) => {
      if (onProgress && progressEvent.total) {
        const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        onProgress(percent)
      }
    })
  },
  // 其他方法不变
  publishImage(data) { return http.post('/api/image-publish/publish', data) },
  getDrafts() { return http.get('/api/image-publish/drafts') },
  saveDraft(data) { return http.post('/api/image-publish/drafts', data) },
  deleteDraft(id) { return http.delete(`/api/image-publish/drafts/${id}`) },
  getHistory() { return http.get('/api/image-publish/history') },
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/imagePublish.js
git commit -m "refactor: imagePublish API 上传改用统一素材接口"
```

---

### Task 22: Settings.vue 新增存储配置

**Files:**
- Modify: `frontend/src/views/Settings.vue`

- [ ] **Step 1: 在 settings reactive 对象中添加 storage 字段**

```javascript
const settings = reactive({
  proxyUrl: '',
  autoFillTitle: true,
  autoSaveDraft: true,
  autoSaveInterval: 10,
  portraitRatio: '9:16',
  landscapeRatio: '16:9',
  storage: {
    type: 'local',
    s3: { endpoint: '', access_key: '', secret_key: '', bucket: '', region: '' },
  },
})
```

- [ ] **Step 2: 在 `fetchSettings` 中加载 storage 配置**

从后端返回的 settings 中读取 `storage` 字段。

- [ ] **Step 3: 在 `handleSave` 中包含 storage 配置**

保存时传入 `storage` 字段。

- [ ] **Step 4: 在模板中"网络代理"和"发布设置"之间添加"文件存储"卡片**

使用 Element Plus 的 `el-card`、`el-radio-group`、`el-form` 组件：
- 存储类型 Radio 切换
- S3 配置表单（条件渲染）
- "测试连接"按钮
- 切换确认提示

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Settings.vue
git commit -m "feat: 设置页面新增文件存储配置区域"
```

---

## Phase 6: 集成验证

### Task 23: 全栈集成验证

- [ ] **Step 1: 启动后端验证**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 app.py &
```

验证以下接口：
- `curl http://localhost:5409/api/materials/list` → `{"code": 200, "data": []}`
- 上传测试文件 → 返回含 `stored_path` 的成功响应
- 列表查询 → 能看到刚上传的文件
- 文件访问 → `curl http://localhost:5409/api/materials/file/{stored_path}` 返回文件内容
- 删除 → 返回成功

- [ ] **Step 2: 启动前端验证**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run dev
```

手动验证：
1. 素材管理页面：上传视频/图片 → 显示 → 预览 → 删除
2. 视频发布：上传视频 → 上传封面 → 从素材库选择
3. 图文发布：上传图片 → 从素材库选择图片/封面

- [ ] **Step 3: 修复编译或运行时错误**

根据验证结果修复问题，每修一处提交一次。

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "fix: 集成验证修复"
```

---

## 改动文件汇总

| 操作 | 文件 | Task |
|------|------|------|
| Create | `backend/storage/__init__.py` | 1 |
| Create | `backend/storage/base.py` | 1 |
| Create | `backend/storage/local.py` | 2 |
| Create | `backend/storage/s3.py` | 3 |
| Create | `backend/blueprints/materials_bp.py` | 5 |
| Create | `frontend/src/api/materials.js` | 11 |
| Create | `frontend/src/utils/storage.js` | 11 |
| Delete | `frontend/src/api/material.js` | 11 |
| Modify | `backend/init_db.py` | 4 |
| Modify | `backend/app.py` | 6, 7, 10 |
| Modify | `backend/blueprints/image_publish_bp.py` | 8 |
| Modify | `backend/routes/frames.py` | 9 |
| Modify | `frontend/src/stores/app.js` | 12 |
| Modify | `frontend/src/views/PublishCenter.vue` | 13 |
| Modify | `frontend/src/components/CoverCard.vue` | 14 |
| Modify | `frontend/src/components/CoverEditorDialog.vue` | 15 |
| Modify | `frontend/src/components/ImageUploader.vue` | 16 |
| Modify | `frontend/src/components/ImageCoverUpload.vue` | 17 |
| Modify | `frontend/src/components/MaterialSelectDialog.vue` | 18 |
| Modify | `frontend/src/views/MaterialManagement.vue` | 19 |
| Modify | `frontend/src/views/ImagePublish.vue` | 20 |
| Modify | `frontend/src/api/imagePublish.js` | 21 |
| Modify | `frontend/src/views/Settings.vue` | 22 |
