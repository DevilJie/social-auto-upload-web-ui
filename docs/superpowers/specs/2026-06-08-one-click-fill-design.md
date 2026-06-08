# 一键填写 设计文档

## 概述

在「视频发布」和「图文发布」页面的顶部右侧各加一个「一键填写」按钮。点击后弹出一个对话框（el-dialog），内部以**卡片形式**展示历史发布成功的记录（卡片样式参考 `DraftBox.vue`），每张卡片含封面、标题、描述、渠道 logo、发布时间。用户点选其中一条记录后，把该记录里**所有渠道/账号级别的 per-platform 配置**（不含公共区域——视频/封面/公共标题描述）填入当前会话的对应渠道。

数据源：发布历史（成功记录 + `account_configs` 非空），按时间倒排，分页。

## 关键决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 数据源 | 发布历史（成功 + `account_configs` 非空） | 用户指定 |
| 卡片过滤条件 | status='success' AND account_configs 非空 | 用户指定 |
| 排序 | created_at DESC | 用户指定 |
| 跨平台行为 | 只填交集（history 有 + 当前已勾的） | 用户选推荐 |
| 按钮位置 | 视频/图文页面顶部右侧（发布按钮旁） | 用户选推荐 |
| 视频数据存储 | `publish_tasks` 加 `account_configs` JSON 列 | 当前表只存 title/desc/tags，缺 per-platform 字段 |
| 图文数据存储 | 已有 `account_configs` 列 | 复用现有 |
| dialog 实现 | 共享组件 `OneClickFillDialog.vue` | DRY、以后扩展容易 |

## 范围

### 在范围内

1. 数据库迁移：`publish_tasks` 加 `account_configs TEXT DEFAULT '{}'`
2. 视频发布成功时把 per-platform config 写入 `account_configs`
3. 图文发布成功时（如果当前没存的话）写入 `account_configs`
4. 新后端端点 `GET /api/v2/publish-templates?type=video|image`
5. 新前端组件 `OneClickFillDialog.vue`
6. `PublishCenter.vue` 顶部加按钮 + 处理 pick 逻辑
7. `ImagePublish.vue` 顶部加按钮 + 处理 pick 逻辑
8. 后端 pytest

### 不在范围内

- 历史搜索、标签、收藏
- 跨类型互通（视频历史不出现在图文选择区）
- 「最近使用」快速选择
- 「删除某条历史」入口
- 改 DraftBox / PublishHistory 视图
- 改后端现有的 list 接口（image_publish_bp 的 /history）

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│  PublishCenter.vue / ImagePublish.vue                       │
│    顶部右侧：新增「一键填写」按钮（el-button + MagicStick）  │
│    点击 → 打开 OneClickFillDialog                            │
└────────────────────┬────────────────────────────────────────┘
                     │ open(type='video'|'image', currentPlatforms)
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  OneClickFillDialog.vue (新组件)                             │
│    el-dialog → 卡片网格（参考 DraftBox 样式）                │
│    分页器 + 每张卡片：封面/标题/描述/渠道/时间              │
│    点击卡片 → emit('pick', record)                          │
└────────────────────┬────────────────────────────────────────┘
                     │ GET /api/v2/publish-templates?type=
                     ▼
┌─────────────────────────────────────────────────────────────┐
│  后端 (新 blueprint 或 ext_api 追加)                         │
│    SELECT ... WHERE status='success' AND account_configs ... │
│    ORDER BY created_at DESC                                  │
└─────────────────────────────────────────────────────────────┘
```

## 后端设计

### `backend/init_db.py` 迁移

```python
# publish_tasks 添加 account_configs 列
try:
    cursor.execute('ALTER TABLE publish_tasks ADD COLUMN account_configs TEXT DEFAULT "{}"')
    logger.info("已添加 publish_tasks.account_configs 列")
except sqlite3.OperationalError:
    pass  # 列已存在
```

### `backend/app.py`（postVideo 流程）

在 `/postVideo` 路由的"发布成功"分支里，把前端传来的该 platform 的 per-platform config 写入：

```python
# 大致在判断 r['status'] == 'success' 后
conn.execute(
    "UPDATE publish_tasks SET account_configs = ? WHERE id = ?",
    (json.dumps(platform_config_for_this_channel, ensure_ascii=False),
     task_id)
)
```

注：`platform_config_for_this_channel` 是发布时前端传来的 `platformConfigs[platform]` 完整 dict。

### `backend/app.py`（postVideoBatch 流程）

每条 channel 独立 UPDATE 自己的 `account_configs`（每条 task 一行，存对应 platform 的 config）。

### `backend/blueprints/image_publish_bp.py`

发布成功后 UPDATE `image_publish_tasks.account_configs` 为最终值。当前流程里 INSERT 时已存，但失败重试后可能更新；需检查并确保成功后写最终值。

### 新端点

```python
@ext_api.route('/publish-templates', methods=['GET'])
def get_publish_templates():
    type_ = request.args.get('type', '').strip()  # 'video' or 'image'
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

        items = []
        for r in rows:
            configs = json.loads(r['account_configs'] or '{}')
            # channels: 视频是 dict (key=platform), 用 keys 列表
            channels = [{'platform': k} for k in configs.keys()]
            items.append({
                "id": r['id'],
                "type": "video",
                "title": r['title'] or "",
                "description": r['description'] or "",
                "thumbnail_path": r['thumbnail_path'] or "",  # 相对路径，前端拼
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

        items = []
        for r in rows:
            configs = json.loads(r['account_configs'] or '[]')
            image_ids = json.loads(r['image_ids'] or '[]')
            first_image_id = image_ids[0] if image_ids else None
            # channels: 图文是 list, 每个含 account_id / platform
            channels = [
                {'platform': c.get('platform', ''), 'account_id': c.get('account_id')}
                for c in configs
            ]
            items.append({
                "id": r['id'],
                "type": "image",
                "title": (configs[0].get('title') if configs else '') or '',
                "description": (configs[0].get('description') if configs else '') or '',
                "first_image_id": first_image_id,  # 前端用 materials API 拿 URL
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

**响应字段约定**：
- 视频：返回 `thumbnail_path`（相对路径），前端拼 base_url
- 图文：返回 `first_image_id`，前端调 `materials` API 拿 URL
- `channels` 统一为 `[{'platform': str, 'account_id'?: number}]` 对象数组
- `account_configs`：
  - 视频：dict，`{platform_key: per_platform_config}`
  - 图文：list，`[per_account_config]`

## 前端设计

### `frontend/src/components/OneClickFillDialog.vue`（新文件）

**Props**：
- `modelValue: boolean`（v-model）
- `type: 'video' | 'image'`
- `currentPlatforms: string[]` —— 当前会话已选的平台/账号，用于匹配交集（视频用 platform key，图文用 account_id）

**Emits**：
- `update:modelValue`
- `pick(record)` —— record 包含 `account_configs` 完整结构

**Script**：
```js
import { ref, watch, computed } from 'vue'
import { http } from '@/utils/request'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'

const props = defineProps(['modelValue', 'type', 'currentPlatforms'])
const emit = defineEmits(['update:modelValue', 'pick'])

const loading = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

async function load() {
  loading.value = true
  try {
    const res = await http.get('/api/v2/publish-templates', {
      params: { type: props.type, page: page.value, page_size: pageSize.value }
    })
    const items = res.data?.list || []
    // 给每条记录补上 coverSrc：视频用 thumbnail_path 拼；图文查 materials API
    for (const item of items) {
      if (item.type === 'video' && item.thumbnail_path) {
        item.coverSrc = `${window.location.protocol}//${window.location.hostname}:5409/uploads/${item.thumbnail_path.replace(/^uploads\//, '')}`
      } else if (item.type === 'image' && item.first_image_id) {
        // 调用 materials API 拿 URL（项目已有 http.get('/api/materials/list', {params:{id}})）
        try {
          const m = await http.get('/api/materials/list', { params: { id: item.first_image_id, page: 1, page_size: 1 } })
          const mat = m.data?.list?.[0]
          item.coverSrc = mat?.url || mat?.stored_path ? `${window.location.protocol}//${window.location.hostname}:5409/${mat.stored_path}` : ''
        } catch (_) { item.coverSrc = '' }
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
```

**Template**：
```vue
<el-dialog
  :model-value="modelValue"
  @update:model-value="emit('update:modelValue', $event)"
  :title="type === 'video' ? '从历史发布一键填写' : '从历史发布一键填写'"
  width="80%"
  top="5vh"
>
  <div v-loading="loading" class="grid">
    <el-empty v-if="!loading && list.length === 0"
              :description="`还没有可用的历史记录，去 ${type === 'video' ? '视频发布' : '图文发布'} 试试？`" />
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
          <span v-for="ch in (Array.isArray(record.channels) ? record.channels : [])" :key="ch" class="channel-tag">
            {{ typeof ch === 'string' ? ch : ch.platform || ch.account_name }}
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
```

**Style**（参考 DraftBox `.draft-card`）：
```scss
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
  }
}
.card-cover {
  position: relative;
  width: 100%;
  padding-top: 56.25%;  /* 16:9 */
  background: $bg-surface;
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .cover-placeholder {
    position: absolute; inset: 0;
    display: flex; align-items: center; justify-content: center;
    color: $text-muted;
  }
}
.card-body { padding: 12px; }
.card-title {
  font-size: 14px; font-weight: 600;
  color: $text-primary;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.card-desc {
  font-size: 12px; color: $text-muted;
  margin: 4px 0 8px;
  overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
  -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.card-channels {
  display: flex; flex-wrap: wrap; gap: 4px;
  .channel-tag {
    font-size: 11px; padding: 2px 6px;
    background: $bg-surface; border-radius: 4px;
    color: $text-secondary;
  }
}
.card-time {
  font-size: 11px; color: $text-muted; margin-top: 8px;
}
```

### `frontend/src/views/PublishCenter.vue` 改动

1. import `OneClickFillDialog`
2. 加响应式 `oneClickDialogOpen = ref(false)`
3. 在「发布」按钮旁加按钮：
   ```vue
   <el-button :icon="MagicStick" @click="oneClickDialogOpen = true">一键填写</el-button>
   ```
4. 加方法：
   ```js
   function handleOneClickFill(record) {
     const histConfigs = record.account_configs || {}
     let filled = 0
     for (const key of Object.keys(platformConfigs)) {
       if (histConfigs[key]) {
         // 只填交集
         platformConfigs[key] = { ...platformConfigs[key], ...histConfigs[key] }
         filled++
       }
     }
     ElMessage.success(`已从历史填充 ${filled} 个平台配置`)
   }
   ```
5. 模板末尾加 `<OneClickFillDialog v-model="oneClickDialogOpen" type="video" :current-platforms="Object.keys(platformConfigs)" @pick="handleOneClickFill" />`

### `frontend/src/views/ImagePublish.vue` 改动

类似：
1. 加 `oneClickDialogOpen` ref
2. 加按钮
3. 加方法（按 account_id 求交集）：
   ```js
   function handleOneClickFill(record) {
     const histConfigs = record.account_configs || []
     const histMap = new Map(histConfigs.map(c => [c.account_id, c]))
     let filled = 0
     for (let i = 0; i < accountConfigs.length; i++) {
       const cur = accountConfigs[i]
       const hist = histMap.get(cur.account_id)
       if (hist) {
         accountConfigs[i] = {
           ...cur,
           title: hist.title ?? cur.title,
           description: hist.description ?? cur.description,
           tags: hist.tags ?? cur.tags,
           // 其他 per-account 字段同理
         }
         filled++
       }
     }
     ElMessage.success(`已从历史填充 ${filled} 个账号配置`)
   }
   ```

## 数据流

**打开 dialog**：
```
User click 「一键填写」 (video page)
  → PublishCenter.vue: oneClickDialogOpen = true
  → OneClickFillDialog: watch modelValue → load()
  → GET /api/v2/publish-templates?type=video&page=1
  → SQL: WHERE status='success' AND account_configs != '{}' ORDER BY created_at DESC
  → 返回 list, total
  → 渲染卡片网格
```

**选中记录**：
```
User click 卡片
  → OneClickFillDialog.handlePick(record)
  → emit 'pick', record
  → PublishCenter.vue.handleOneClickFill(record)
  → 遍历 platformConfigs: 跟 record.account_configs 求 key 交集
  → 命中的覆盖 platformConfigs[key] = {...cur, ...hist}
  → toast: 「已从历史填充 N 个平台配置」
  → emit 'update:modelValue', false → 关闭 dialog
```

## 测试

### 后端 pytest（`backend/tests/test_publish_templates.py`，新文件）

1. `test_video_templates_filters_success_and_nonempty`：
   - INSERT 5 行：3 个 success + 2 个 failed，account_configs 各种状态
   - GET `/publish-templates?type=video`
   - 断言只返回 success 且 account_configs 非空
2. `test_video_templates_ordering_desc`：
   - INSERT 3 行不同时间
   - 断言按 created_at DESC
3. `test_video_templates_pagination`：
   - INSERT 25 行
   - page=2&page_size=10 → 返回 10 条
4. `test_image_templates_filters_success`：
   - 类似视频
5. `test_invalid_type_returns_400`：
   - `?type=foo` → 400
6. `test_publish_tasks_migration_column_exists`：
   - PRAGMA table_info(publish_tasks) 应包含 account_configs
7. `test_postvideo_writes_account_configs`：
   - mock 上游发布成功
   - 断言 publish_tasks.account_configs 被 UPDATE

### 前端

不写组件测试。手动 e2e 验证：
- 视频页点「一键填写」→ 弹 dialog 显示成功历史
- 选一条 → toast 显示填充数 → 平台配置被覆盖
- 视频/封面/公共标题描述不变（公共区域保护）
- 图文页同样流程
- 翻页正常

## 实施顺序

1. 后端迁移（init_db.py + ALTER TABLE）
2. 后端写入逻辑（postVideo / postVideoBatch / image publish 成功时）
3. 后端端点（`/api/v2/publish-templates`）
4. 后端测试
5. 前端 dialog 组件（OneClickFillDialog.vue）
6. PublishCenter.vue 接入
7. ImagePublish.vue 接入
8. 手动 e2e

## 风险与权衡

| 风险 | 缓解 |
|------|------|
| `publish_tasks` 加列导致老数据无 `account_configs` | 列表查询时 `account_configs != '{}'` 过滤掉 |
| 视频一条历史只对应一个 platform（按 task_id 一行） | SELECT 的 `account_configs` 实际是 dict 而不是 list（与图文的 list 不同）—— 接口响应里 `channels` 字段统一用 list 表示 |
| 用户选了一条历史，但当前会话平台完全不重叠 | toast 提示「0 个平台配置」 |
| `account_configs` 字段在批量发布时未及时更新 | 在 `/postVideo` 成功路径里同步 UPDATE；批量时逐条 UPDATE |
