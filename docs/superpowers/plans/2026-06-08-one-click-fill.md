# 一键填写功能 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在「视频发布」和「图文发布」页面的顶部右侧各加「一键填写」按钮，点击后弹对话框展示历史成功发布记录，点选后把 per-channel/per-account 配置填入当前会话的对应渠道（保留公共区域）。

**Architecture:** 后端给 `publish_tasks` 加 `account_configs` JSON 列；`/postVideo` 路径里在 `_record_publish` 写入时存该 platform 的完整配置。前端新增 `OneClickFillDialog.vue` 共享组件，两个发布页接入。

**Tech Stack:** Python 3 + Flask + sqlite3（项目已有 `_record_publish` 模式）、Vue 3 + Element Plus（已用 axios + `@/utils/request`）、pytest

---

## 文件结构

```
backend/
├── init_db.py                                      # 修改：加迁移
├── app.py                                          # 修改：_record_publish 增 account_configs 参数 + INSERT + postVideo 调用处透传
├── blueprints/
│   └── image_publish_bp.py                         # 验证（不需改）
└── tests/
    ├── __init__.py                                 # 已存在
    └── test_publish_templates.py                   # 新建：6 个测试（迁移验证 + 新端点）

frontend/src/
├── components/
│   └── OneClickFillDialog.vue                      # 新建：共享 dialog
├── views/
│   ├── PublishCenter.vue                           # 修改：publishData 加 accountConfigs + 接入 dialog
│   └── ImagePublish.vue                            # 修改：接入 dialog
```

总计：2 个修改（后端） + 1 个新测试（后端） + 1 个新组件（前端） + 2 个修改（前端）= 4 修改 + 2 新建。

---

## Task 1: 数据库迁移（init_db.py）

**Files:**
- Modify: `backend/init_db.py:191-193` (existing ALTER TABLE block)

- [ ] **Step 1: 加 ALTER TABLE**

在 `init_db.py` 的现有 ALTER TABLE 块（`publish_tasks 添加 thumbnail_path 列` 之后）追加：

```python
# publish_tasks 添加 account_configs 列（一键填写用）
try:
    cursor.execute('ALTER TABLE publish_tasks ADD COLUMN account_configs TEXT DEFAULT "{}"')
    logger.info("已添加 publish_tasks.account_configs 列")
except sqlite3.OperationalError:
    pass  # 列已存在
```

- [ ] **Step 2: 验证迁移可执行**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -c "import init_db; init_db.init_database()"
```

Expected: 启动日志显示「已添加 publish_tasks.account_configs 列」（首次运行）或无 OperationalError（已存在）。无 Traceback。

- [ ] **Step 3: 验证列存在**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('/home/czy/workspace/ai/social-auto-upload-web-ui/data/db/database.db')
cols = [r[1] for r in conn.execute('PRAGMA table_info(publish_tasks)').fetchall()]
print('account_configs' in cols)
"
```

Expected: `True`

- [ ] **Step 4: 提交**

```bash
git add backend/init_db.py
git commit -m "feat(backend): publish_tasks 加 account_configs 列（一键填写用）"
```

---

## Task 2: 后端 `_record_publish` 接收 account_configs（TDD）

**Files:**
- Modify: `backend/app.py:634-650` (`_record_publish` definition), `app.py:702-720` (call site in postVideo)

- [ ] **Step 1: 写失败测试 — `_record_publish` 接受 account_configs 并存**

在 `backend/tests/test_record_publish_account_configs.py` 新建：

```python
"""_record_publish 接受 account_configs 参数并写入 publish_tasks.account_configs。"""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def test_record_publish_writes_account_configs():
    """_record_publish 接受 account_configs 形参并 JSON 序列化写入列。"""
    from app import _record_publish
    import sqlite3

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE publish_tasks (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            video_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT DEFAULT '',
            publish_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            thumbnail_path TEXT DEFAULT '',
            account_configs TEXT DEFAULT '{}'
        );
    """)
    conn.commit()
    conn.close()

    from conf import BASE_DIR
    with patch("app.DB_PATH", db_path):
        _record_publish(
            task_id="uuid-1",
            platform="douyin",
            account_name="测试账号",
            video_path="/tmp/v.mp4",
            title="t",
            description="d",
            tags=["a"],
            status="running",
            started_at="2026-06-08T10:00:00",
            account_configs={"douyin": {"title": "per-platform title", "tags": ["x"]}},
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_tasks WHERE id = ?", ("uuid-1",)
    ).fetchone()
    stored = json.loads(row[0])
    assert stored == {"douyin": {"title": "per-platform title", "tags": ["x"]}}
    conn.close()


def test_record_publish_default_account_configs():
    """不传 account_configs 时默认写 '{}'。"""
    from app import _record_publish
    import sqlite3

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE publish_tasks (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            video_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT DEFAULT '',
            publish_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            thumbnail_path TEXT DEFAULT '',
            account_configs TEXT DEFAULT '{}'
        );
    """)
    conn.commit()
    conn.close()

    with patch("app.DB_PATH", db_path):
        _record_publish(
            task_id="uuid-2",
            platform="douyin",
            account_name="x",
            video_path="/v",
            title="t",
            description="",
            tags=[],
            status="running",
            started_at="2026-06-08T10:00:00",
        )

    conn = sqlite3.connect(str(db_path))
    row = conn.execute(
        "SELECT account_configs FROM publish_tasks WHERE id = ?", ("uuid-2",)
    ).fetchone()
    assert row[0] == "{}"
    conn.close()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/test_record_publish_account_configs.py -v
```

Expected: 2 个 `FAILED`（TypeError: missing keyword argument 'account_configs'）

- [ ] **Step 3: 修改 `_record_publish` 函数**

在 `backend/app.py` line 634，把：

```python
def _record_publish(task_id, platform, account_name, video_path, title, description, tags, status, started_at, finished_at=None, error_message=""):
```

改为：

```python
def _record_publish(task_id, platform, account_name, video_path, title, description, tags, status, started_at, finished_at=None, error_message="", account_configs=None):
```

把 INSERT 改成（line 638-647）：

```python
            conn.execute(
                """INSERT INTO publish_tasks
                   (id, platform, account_name, video_path, title, description,
                    tags, status, retry_count, max_retries, error_message,
                    publish_url, created_at, started_at, finished_at,
                    thumbnail_path, account_configs)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 3, ?, '', ?, ?, ?, ?, ?)""",
                (task_id, platform, account_name, video_path, title, description,
                 json.dumps(tags, ensure_ascii=False), status, error_message,
                 started_at, started_at, finished_at, '',
                 json.dumps(account_configs or {}, ensure_ascii=False))
            )
```

注：保留了 `thumbnail_path` 列插入（值为空字符串 `''`，因为 `_record_publish` 当前不存 thumbnail；thumbnail 由后续 UPDATE 单独写）。如果你 review 时认为这样不规范，可改为 NULL。

- [ ] **Step 4: 运行测试，确认通过**

```bash
python3 -m pytest tests/test_record_publish_account_configs.py -v
```

Expected: 2 个 `PASSED`

- [ ] **Step 5: 修改 `postVideo` 调用处**

定位 `backend/app.py:702-720` 的 `_record_publish(...)` 调用。在 `tags=data.get('tags', []),` 之后追加一行：

```python
            account_configs={data.get('type'): {**{k: v for k, v in data.items() if k not in ('fileList', 'accountList', 'type', 'title', 'description', 'tags', 'thumbnail', 'thumbnailLandscape', 'thumbnailPortrait')}, 'title': data.get('title'), 'description': data.get('description'), 'tags': data.get('tags')}},
```

（这是把 per-platform 的所有相关字段打包成 `{platform_key: config_dict}` 存到 `account_configs` 列。）

- [ ] **Step 6: 验证整个 app 还能导入**

```bash
python3 -c "from app import app; print('ok')"
```

Expected: `ok`

- [ ] **Step 7: 提交**

```bash
git add backend/app.py backend/tests/test_record_publish_account_configs.py
git commit -m "feat(backend): _record_publish 接受 account_configs 并写入 publish_tasks"
```

---

## Task 3: 新端点 `GET /api/v2/publish-templates`（TDD）

**Files:**
- Modify: `backend/ext_api/__init__.py`（在文件末尾追加新路由）
- Test: `backend/tests/test_publish_templates.py`（新建）

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_publish_templates.py` 新建：

```python
"""GET /api/v2/publish-templates 端点测试。"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _make_db():
    """创建一个临时 SQLite + 完整 publish_tasks + image_publish_tasks schema，返回 db_path。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_path = Path(tmp.name)
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE publish_tasks (
            id TEXT PRIMARY KEY,
            platform TEXT NOT NULL,
            account_name TEXT NOT NULL,
            video_path TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            status TEXT DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            max_retries INTEGER DEFAULT 3,
            error_message TEXT DEFAULT '',
            publish_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            thumbnail_path TEXT DEFAULT '',
            account_configs TEXT DEFAULT '{}'
        );
        CREATE TABLE image_publish_tasks (
            id TEXT PRIMARY KEY,
            image_ids TEXT NOT NULL,
            account_configs TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            scheduled_at TEXT,
            published_at TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def _insert_video(conn, id_, status, account_configs, created_at='2026-06-08T10:00:00', title='t', thumbnail_path='thumb.png'):
    conn.execute(
        "INSERT INTO publish_tasks (id, platform, account_name, video_path, title, status, account_configs, thumbnail_path, created_at) VALUES (?, 'douyin', 'x', '/v', ?, ?, ?, ?, ?)",
        (id_, title, status, json.dumps(account_configs, ensure_ascii=False), thumbnail_path, created_at)
    )


def test_video_templates_filters_success_and_nonempty():
    """只返回 status=success 且 account_configs 非空的记录。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    _insert_video(conn, "1", "success", {"douyin": {"title": "ok"}}, "2026-06-08T10:00:00", "task 1")
    _insert_video(conn, "2", "success", {}, "2026-06-08T09:00:00", "task 2")
    _insert_video(conn, "3", "failed", {"douyin": {"title": "bad"}}, "2026-06-08T08:00:00", "task 3")
    _insert_video(conn, "4", "success", {"douyin": {"title": "ok2"}}, "2026-06-08T07:00:00", "task 4")
    conn.commit()
    conn.close()

    import ext_api.__init__ as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video"):
            resp = get_publish_templates()
            data = resp.get_json()
            ids = [r['id'] for r in data['data']['list']]
            assert ids == ["1", "4"]
            assert data['data']['total'] == 2


def test_video_templates_returns_expected_fields():
    """响应字段含 type, title, description, thumbnail_path, channels, account_configs, created_at。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    _insert_video(
        conn, "1", "success", {"douyin": {"title": "ok"}, "xiaohongshu": {"title": "xhs"}},
        "2026-06-08T10:00:00", "My Title", "thumb.png"
    )
    conn.commit()
    conn.close()

    import ext_api.__init__ as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video"):
            resp = get_publish_templates()
            data = resp.get_json()
            item = data['data']['list'][0]
            assert item['type'] == 'video'
            assert item['title'] == 'My Title'
            assert item['thumbnail_path'] == 'thumb.png'
            assert item['account_configs'] == {"douyin": {"title": "ok"}, "xiaohongshu": {"title": "xhs"}}
            platforms = [c['platform'] for c in item['channels']]
            assert set(platforms) == {'douyin', 'xiaohongshu'}


def test_image_templates_returns_image_with_first_image_id():
    """图文返回 first_image_id 和 account_configs 数组。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "INSERT INTO image_publish_tasks (id, image_ids, account_configs, status, created_at) VALUES (?, ?, ?, 'success', '2026-06-08T10:00:00')",
        (
            "img-1",
            json.dumps(["img-uuid-1", "img-uuid-2"]),
            json.dumps([
                {"account_id": 2, "platform": "douyin", "title": "img title", "description": "d"},
                {"account_id": 3, "platform": "xiaohongshu", "title": "xhs", "description": "d2"},
            ], ensure_ascii=False),
        )
    )
    conn.commit()
    conn.close()

    import ext_api.__init__ as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=image"):
            resp = get_publish_templates()
            data = resp.get_json()
            item = data['data']['list'][0]
            assert item['type'] == 'image'
            assert item['first_image_id'] == 'img-uuid-1'
            assert item['title'] == 'img title'
            assert isinstance(item['account_configs'], list)
            assert len(item['account_configs']) == 2
            assert item['account_configs'][0]['account_id'] == 2


def test_publish_templates_invalid_type_returns_400():
    """type 参数不是 video/image 返 400。"""
    from ext_api import get_publish_templates

    import ext_api.__init__ as ext
    with ext.app.test_request_context("/api/v2/publish-templates?type=foo"):
        resp = get_publish_templates()
        assert resp[1] == 400
        assert 'type' in resp[0].get_json()['msg']


def test_publish_templates_pagination():
    """page / page_size 生效。"""
    from ext_api import get_publish_templates

    db_path = _make_db()
    conn = sqlite3.connect(str(db_path))
    for i in range(25):
        _insert_video(
            conn, f"id{i}", "success", {"douyin": {"i": i}},
            f"2026-06-08T1{i % 10}:00:00" if i < 10 else f"2026-06-08T0{i // 10}:00:00", f"task {i}"
        )
    conn.commit()
    conn.close()

    import ext_api.__init__ as ext
    with patch.object(ext, "_db_conn", lambda: sqlite3.connect(str(db_path))):
        with ext.app.test_request_context("/api/v2/publish-templates?type=video&page=2&page_size=10"):
            resp = get_publish_templates()
            data = resp.get_json()
            assert data['data']['total'] == 25
            assert len(data['data']['list']) == 10
```

- [ ] **Step 2: 运行测试，确认全部失败**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/test_publish_templates.py -v
```

Expected: 5 个 `FAILED` with `ImportError: cannot import name 'get_publish_templates' from 'ext_api'`

- [ ] **Step 3: 在 ext_api/__init__.py 末尾添加新路由**

在 `backend/ext_api/__init__.py` 文件末尾追加：

```python
@ext_api.route('/publish-templates', methods=['GET'])
def get_publish_templates():
    """一键填写：从历史成功发布里取可复用的 per-channel 配置。
    Query: type=video|image, page=1, page_size=20
    """
    import json as _json
    type_ = request.args.get('type', '').strip()
    if type_ not in ('video', 'image'):
        return jsonify({"code": 400, "msg": "type 必须是 video 或 image"}), 400

    try:
        page = int(request.args.get('page', 1))
        page_size = min(int(request.args.get('page_size', 20)), 100)
    except ValueError:
        return jsonify({"code": 400, "msg": "page / page_size 必须是整数"}), 400

    offset = (page - 1) * page_size
    conn = _db_conn()

    if type_ == 'video':
        rows = conn.execute(
            """SELECT id, title, description, thumbnail_path, account_configs, created_at
               FROM publish_tasks
               WHERE status = 'success' AND account_configs IS NOT NULL AND account_configs != '{}'
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, offset)
        ).fetchall()
        total = conn.execute(
            """SELECT COUNT(*) FROM publish_tasks
               WHERE status = 'success' AND account_configs IS NOT NULL AND account_configs != '{}'"""
        ).fetchone()[0]
        conn.close()

        items = []
        for r in rows:
            configs = _json.loads(r['account_configs'] or '{}')
            channels = [{'platform': k} for k in configs.keys()]
            items.append({
                "id": r['id'],
                "type": "video",
                "title": r['title'] or '',
                "description": r['description'] or '',
                "thumbnail_path": r['thumbnail_path'] or '',
                "first_image_id": None,
                "channels": channels,
                "account_configs": configs,
                "created_at": r['created_at'],
            })
    else:  # image
        rows = conn.execute(
            """SELECT id, account_configs, image_ids, created_at
               FROM image_publish_tasks
               WHERE status = 'success' AND account_configs IS NOT NULL
               ORDER BY created_at DESC
               LIMIT ? OFFSET ?""",
            (page_size, offset)
        ).fetchall()
        total = conn.execute(
            """SELECT COUNT(*) FROM image_publish_tasks
               WHERE status = 'success' AND account_configs IS NOT NULL"""
        ).fetchone()[0]
        conn.close()

        items = []
        for r in rows:
            configs = _json.loads(r['account_configs'] or '[]')
            image_ids = _json.loads(r['image_ids'] or '[]')
            first_image_id = image_ids[0] if image_ids else None
            channels = [
                {'platform': c.get('platform', ''), 'account_id': c.get('account_id')}
                for c in configs
            ]
            items.append({
                "id": r['id'],
                "type": "image",
                "title": (configs[0].get('title') if configs else '') or '',
                "description": (configs[0].get('description') if configs else '') or '',
                "thumbnail_path": None,
                "first_image_id": first_image_id,
                "channels": channels,
                "account_configs": configs,
                "created_at": r['created_at'],
            })

    return jsonify({
        "code": 200,
        "data": {
            "list": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    })
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
python3 -m pytest tests/test_publish_templates.py -v
```

Expected: 5 个 `PASSED`

- [ ] **Step 5: 提交**

```bash
git add backend/ext_api/__init__.py backend/tests/test_publish_templates.py
git commit -m "feat(backend): 新增 GET /api/v2/publish-templates 一键填写模板接口"
```

---

## Task 4: 验证 image_publish 成功时 account_configs 已写入

**Files:**
- Inspect: `backend/blueprints/image_publish_bp.py:35-100`

- [ ] **Step 1: 跑现有 image_publish 流程看 DB**

如果项目里有可用的图片素材 + 账号，跑一次图文发布成功（或者 mock 调用），然后查 DB 验证 `image_publish_tasks.account_configs` 有值。

或者：直接读代码确认 INSERT 已写 `account_configs`（在 `backend/blueprints/image_publish_bp.py:61-63`）。**预期：已写。** 跳过这步即可，无需改动。

- [ ] **Step 2: 提交（如有改动）**

```bash
git status
# 如果没改动：跳过
# 如果改了：
# git add ... && git commit -m "fix(backend): ..."
```

---

## Task 5: 前端 OneClickFillDialog.vue 组件

**Files:**
- Create: `frontend/src/components/OneClickFillDialog.vue` (新文件)

- [ ] **Step 1: 创建文件**

文件分 3 段：`<template>`、`<script setup>`、`<style scoped>`。

创建 `frontend/src/components/OneClickFillDialog.vue`：

```vue
<template>
  <el-dialog
    :model-value="modelValue"
    @update:model-value="emit('update:modelValue', $event)"
    title="从历史发布一键填写"
    width="80%"
    top="5vh"
  >
    <div v-loading="loading" class="grid">
      <el-empty
        v-if="!loading && list.length === 0"
        :description="`还没有可用的历史记录，去 ${type === 'video' ? '视频发布' : '图文发布'} 试试？`"
      />
      <div v-for="record in list" :key="record.id" class="card" @click="handlePick(record)">
        <div class="card-cover">
          <img v-if="record.coverSrc" :src="record.coverSrc" alt="封面" />
          <div v-else class="cover-placeholder">
            <el-icon :size="32"><Picture /></el-icon>
          </div>
        </div>
        <div class="card-body">
          <div class="card-title">{{ record.title || '无标题' }}</div>
          <div class="card-desc">{{ (record.description || '').slice(0, 60) }}</div>
          <div class="card-channels">
            <span v-for="ch in record.channels" :key="(ch.platform || '') + '-' + (ch.account_id || '')" class="channel-tag">
              {{ ch.platform || '未知平台' }}
            </span>
          </div>
          <div class="card-time">{{ formatRelativeTime(record.created_at) }}</div>
        </div>
      </div>
    </div>

    <el-pagination
      v-if="total > 0"
      v-model:current-page="page"
      v-model:page-size="pageSize"
      :total="total"
      :page-sizes="[10, 20, 50]"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="load"
      @size-change="load"
    />
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { http } from '@/utils/request'
import { Picture } from '@element-plus/icons-vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  type: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue', 'pick'])

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

function formatRelativeTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = (now - d) / 1000
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString('zh-CN')
}

function buildVideoCoverUrl(thumbPath) {
  if (!thumbPath) return ''
  const cleanPath = thumbPath.replace(/^uploads\//, '')
  return `${window.location.protocol}//${window.location.hostname}:5409/uploads/${cleanPath}`
}

async function load() {
  loading.value = true
  try {
    const res = await http.get('/api/v2/publish-templates', {
      params: { type: props.type, page: page.value, page_size: pageSize.value }
    })
    const items = res.data?.list || []
    for (const item of items) {
      if (item.type === 'video' && item.thumbnail_path) {
        item.coverSrc = buildVideoCoverUrl(item.thumbnail_path)
      } else if (item.type === 'image' && item.first_image_id) {
        try {
          const m = await http.get('/api/materials/list', {
            params: { id: item.first_image_id, page: 1, page_size: 1 }
          })
          const mat = m.data?.list?.[0]
          if (mat) {
            const stored = mat.stored_path || ''
            item.coverSrc = stored
              ? `${window.location.protocol}//${window.location.hostname}:5409/${stored.replace(/^\/+/, '')}`
              : mat.url || ''
          } else {
            item.coverSrc = ''
          }
        } catch (_) {
          item.coverSrc = ''
        }
      } else {
        item.coverSrc = ''
      }
    }
    list.value = items
    total.value = res.data?.total || 0
  } catch (e) {
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(() => props.modelValue, (open) => {
  if (open) {
    page.value = 1
    load()
  }
})

function handlePick(record) {
  emit('pick', record)
  emit('update:modelValue', false)
}
</script>

<style lang="scss" scoped>
@use '@/styles/variables.scss' as *;

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  min-height: 200px;
}

.card {
  border: 1px solid $border;
  border-radius: 12px;
  background: $bg-elevated;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.2s;
  &:hover {
    border-color: $brand-start;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
  }
}

.card-cover {
  position: relative;
  width: 100%;
  padding-top: 56.25%;
  background: $bg-surface;
  img {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .cover-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: $text-muted;
  }
}

.card-body { padding: 12px; }

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: $text-primary;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 12px;
  color: $text-muted;
  margin: 4px 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}

.card-channels {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  .channel-tag {
    font-size: 11px;
    padding: 2px 6px;
    background: $bg-surface;
    border-radius: 4px;
    color: $text-secondary;
  }
}

.card-time {
  font-size: 11px;
  color: $text-muted;
  margin-top: 8px;
}
</style>
```

- [ ] **Step 2: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -5
```

Expected: build 成功，无错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/components/OneClickFillDialog.vue
git commit -m "feat(frontend): 新增 OneClickFillDialog 共享组件"
```

---

## Task 6: PublishCenter.vue 接入「一键填写」+ 发请求时带 accountConfigs

**Files:**
- Modify: `frontend/src/views/PublishCenter.vue`（2 处改动：publishData 加 accountConfigs + 加按钮和 dialog）

- [ ] **Step 1: publishData 加 accountConfigs 字段**

定位 `frontend/src/views/PublishCenter.vue` line ~1390 附近，`publishData` 构造的最后几行（`alteredContent: platformSettings.alteredContent || false,` 之后），追加：

```js
        accountConfigs: { [group.id]: platformSettings },
      }
```

完整 publishData 末尾形如：

```js
        audience: platformSettings.audience || 'not_kids',
        alteredContent: platformSettings.alteredContent || false,
        accountConfigs: { [group.id]: platformSettings },
      }
```

- [ ] **Step 2: 引入组件和 icon**

在 `<script setup>` 顶部 import 区域追加：

```js
import { MagicStick } from '@element-plus/icons-vue'
import OneClickFillDialog from '@/components/OneClickFillDialog.vue'
import { ElMessage } from 'element-plus'
```

（如果 `ElMessage` 已引入则不重复加）

- [ ] **Step 3: 加响应式状态**

找一个 `ref` 声明区域追加：

```js
const oneClickDialogOpen = ref(false)
```

- [ ] **Step 4: 加 handler**

```js
function handleOneClickFill(record) {
  const histConfigs = record.account_configs || {}
  let filled = 0
  for (const key of Object.keys(platformConfigs)) {
    if (histConfigs[key] && typeof histConfigs[key] === 'object') {
      platformConfigs[key] = {
        ...platformConfigs[key],
        ...histConfigs[key],
      }
      filled++
    }
  }
  if (filled > 0) {
    ElMessage.success(`已从历史填充 ${filled} 个平台配置`)
  } else {
    ElMessage.warning('当前会话没有与历史记录匹配的平台')
  }
}
```

- [ ] **Step 5: 模板顶部加按钮 + 末尾挂 dialog**

定位「发布」按钮（`type="primary" @click="...">发布` 之类），**在它前面**加：

```vue
<el-button :icon="MagicStick" @click="oneClickDialogOpen = true">
  一键填写
</el-button>
```

定位 `</template>` 之前，**最后一个元素之后**追加：

```vue
    <OneClickFillDialog
      v-model="oneClickDialogOpen"
      type="video"
      :current-platforms="Object.keys(platformConfigs)"
      @pick="handleOneClickFill"
    />
```

- [ ] **Step 6: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -5
```

Expected: 成功

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/PublishCenter.vue
git commit -m "feat(frontend): 视频发布页接入一键填写 + 发请求带 accountConfigs"
```

---

## Task 7: ImagePublish.vue 接入「一键填写」

**Files:**
- Modify: `frontend/src/views/ImagePublish.vue`

- [ ] **Step 1: 引入组件和 icon**

在 `<script setup>` 顶部 import 区域追加：

```js
import { MagicStick } from '@element-plus/icons-vue'
import OneClickFillDialog from '@/components/OneClickFillDialog.vue'
import { ElMessage } from 'element-plus'
```

- [ ] **Step 2: 加响应式状态**

```js
const oneClickDialogOpen = ref(false)
```

- [ ] **Step 3: 加 handler**

```js
function handleOneClickFill(record) {
  const histConfigs = record.account_configs || []
  const histMap = new Map(histConfigs.map(c => [c.account_id, c]))
  let filled = 0
  for (let i = 0; i < accountConfigs.length; i++) {
    const cur = accountConfigs[i]
    const hist = histMap.get(cur.account_id)
    if (hist && typeof hist === 'object') {
      accountConfigs[i] = {
        ...cur,
        title: hist.title ?? cur.title,
        description: hist.description ?? cur.description,
        tags: hist.tags ?? cur.tags,
      }
      filled++
    }
  }
  if (filled > 0) {
    ElMessage.success(`已从历史填充 ${filled} 个账号配置`)
  } else {
    ElMessage.warning('当前账号与历史记录没有交集')
  }
}
```

注：`accountConfigs` 的实际字段名要看现有代码。如需复制更多字段，扩展 `accountConfigs[i] = { ...cur, ...覆盖字段 }`。实施时 grep `accountConfigs` 看看现有结构，必要时覆盖 `location / aiContent / isOriginal` 等。

- [ ] **Step 4: 模板顶部加按钮 + 末尾挂 dialog**

定位「发布」按钮，**在它前面**加：

```vue
<el-button :icon="MagicStick" @click="oneClickDialogOpen = true" :disabled="accountConfigs.length === 0">
  一键填写
</el-button>
```

定位 `</template>` 之前，**最后一个元素之后**追加：

```vue
    <OneClickFillDialog
      v-model="oneClickDialogOpen"
      type="image"
      :current-platforms="accountConfigs.map(a => a.account_id)"
      @pick="handleOneClickFill"
    />
```

- [ ] **Step 5: 验证 build 通过**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npx vite build --mode development 2>&1 | tail -5
```

Expected: 成功

- [ ] **Step 6: 提交**

```bash
git add frontend/src/views/ImagePublish.vue
git commit -m "feat(frontend): 图文发布页接入一键填写"
```

---

## Task 8: 手动 e2e 验证

**Files:** 无（仅验证）

- [ ] **Step 1: 启动后端**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 app.py
```

Expected: 启动无错，5409 端口监听

- [ ] **Step 2: 启动前端**

新终端：

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run dev
```

- [ ] **Step 3: 验证 e2e 清单**

打开 `http://localhost:5173`：

**视频发布**：
- [ ] 在「视频发布」页上传视频 + 选 1-2 个平台 + 填标题描述 + 发布成功
- [ ] 重复一次，再选 1-2 个平台（其中至少 1 个跟上次不同） + 发布成功
- [ ] 进「视频发布」页，点「一键填写」
- [ ] dialog 弹出，显示历史卡片（含封面、标题、渠道 logo、发布时间）
- [ ] 翻页（如有多条）
- [ ] 选一条历史
- [ ] toast 提示「已从历史填充 N 个平台配置」
- [ ] 平台卡片里的 title/description/tags/aiContent 等被覆盖
- [ ] **公共区域**（视频、封面、公共标题描述、tags）**未变**
- [ ] 用 curl 查 DB：`sqlite3 data/db/database.db "SELECT id, account_configs FROM publish_tasks WHERE status='success' ORDER BY created_at DESC LIMIT 5"` —— 应能看到非空 JSON

**图文发布**：
- [ ] 在「图文发布」页上传图片 + 选 1-2 个账号 + 填描述 + 发布成功
- [ ] 重复一次
- [ ] 进「图文发布」页，点「一键填写」
- [ ] dialog 弹出
- [ ] 选一条历史
- [ ] toast 提示「已从历史填充 N 个账号配置」
- [ ] 每个账号的 title/description/tags 被覆盖
- [ ] **图片/封面**（公共区域）**未变**
- [ ] 没选账号时按钮 disabled

- [ ] **Step 4: 最终 commit（如有零散改动）**

```bash
git status
```

如有未提交改动：

```bash
git add -A && git commit -m "chore: 一键填写 e2e 验证后的微调"
```

否则跳过。

---

## 完成标准

✅ 后端 pytest 全部通过（Task 2：2 个 + Task 3：5 个 = 7 个新测试）
✅ 前端 vite build 成功
✅ 浏览器 e2e 清单全部通过
✅ 所有改动已 commit（中文 message）
✅ Spec `docs/superpowers/specs/2026-06-08-one-click-fill-design.md` 和 Plan `docs/superpowers/plans/2026-06-08-one-click-fill.md` 都已落盘
