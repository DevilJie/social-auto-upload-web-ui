# 账号标签体系 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use compose:subagent (recommended) or compose:execute to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为账号管理系统增加标签分组功能，支持多标签、卡片内添加、筛选过滤。

**Architecture:** 后端新增 `tags` + `account_tags` 两张表（多对多），通过 Flask 路由提供 CRUD API。前端在账号卡片上展示标签并提供 popover 添加，账号列表和发布页面的选择账号对话框均支持按标签筛选。

**Tech Stack:** Python Flask + SQLite (backend), Vue 3 + Element Plus + Pinia (frontend)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/init_db.py` | 新增 tags + account_tags 表，迁移脚本 |
| Modify | `backend/app.py` | 新增标签 CRUD 和账号-标签关系路由 |
| Modify | `backend/tests/test_account_tags.py` | 新建：标签 API 测试 |
| Modify | `frontend/src/api/account.js` | 新增标签 API 方法 |
| Modify | `frontend/src/stores/account.js` | accounts 对象增加 tags 字段 |
| Modify | `frontend/src/views/AccountManagement.vue` | 标签展示 + 添加 popover + 筛选栏 |
| Modify | `frontend/src/components/AccountSelectDialog.vue` | 标签筛选 |
| Create | `frontend/src/components/TagPopover.vue` | 标签选择/创建 popover 组件 |

---

### Task 1: 数据库 — 新增 tags 和 account_tags 表

**Files:**
- Modify: `backend/init_db.py`

- [ ] **Step 1: 在 `init_database()` 中建表**

在 `init_database()` 函数的 `conn.commit()` 之前添加：

```python
    # 标签表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        color TEXT DEFAULT '#8b5cf6',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # 账号-标签关联表
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS account_tags (
        account_id INTEGER NOT NULL,
        tag_id INTEGER NOT NULL,
        PRIMARY KEY (account_id, tag_id),
        FOREIGN KEY (account_id) REFERENCES user_info(id) ON DELETE CASCADE,
        FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
    )
    """)
```

- [ ] **Step 2: 在 `migrate_database()` 中添加幂等迁移**

在 `migrate_database()` 的 `conn.commit()` 之前添加：

```python
    # 确保 tags 表存在（幂等）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            color TEXT DEFAULT '#8b5cf6',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_tags (
            account_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (account_id, tag_id),
            FOREIGN KEY (account_id) REFERENCES user_info(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)
```

- [ ] **Step 3: 验证迁移**

```bash
cd backend && python -c "from init_db import init_database, migrate_database; init_database(); migrate_database(); print('OK')"
```

Expected: `OK`

---

### Task 2: 后端 — 标签 CRUD API

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: 在 `app.py` 的路由区域（`updateUserinfo` 之后）添加标签路由**

```python
# ── Tag management ────────────────────────────────────────

@app.route('/api/tags', methods=['GET'])
def get_tags():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('SELECT * FROM tags ORDER BY name').fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/tags', methods=['POST'])
def create_tag():
    data = request.get_json()
    name = (data.get('name') or '').strip()
    color = data.get('color') or '#8b5cf6'
    if not name:
        return jsonify({"code": 400, "msg": "标签名不能为空"}), 400
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('INSERT INTO tags (name, color) VALUES (?, ?)', (name, color))
            tag_id = conn.execute('SELECT last_insert_rowid()').fetchone()[0]
            conn.commit()
        return jsonify({"code": 200, "data": {"id": tag_id, "name": name, "color": color}})
    except sqlite3.IntegrityError:
        return jsonify({"code": 409, "msg": "标签名已存在"}), 409
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/tags/<int:tag_id>', methods=['DELETE'])
def delete_tag(tag_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('DELETE FROM tags WHERE id = ?', (tag_id,))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/<int:account_id>/tags', methods=['PUT'])
def set_account_tags(account_id):
    data = request.get_json()
    tag_ids = data.get('tag_ids', [])
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.execute('DELETE FROM account_tags WHERE account_id = ?', (account_id,))
            for tid in tag_ids:
                conn.execute('INSERT OR IGNORE INTO account_tags (account_id, tag_id) VALUES (?, ?)', (account_id, tid))
            conn.commit()
        return jsonify({"code": 200})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500


@app.route('/api/accounts/<int:account_id>/tags', methods=['GET'])
def get_account_tags(account_id):
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute('''
                SELECT t.* FROM tags t
                JOIN account_tags at ON t.id = at.tag_id
                WHERE at.account_id = ?
                ORDER BY t.name
            ''', (account_id,)).fetchall()
        return jsonify({"code": 200, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"code": 500, "msg": str(e)}), 500
```

- [ ] **Step 2: 修改 `getAccounts` 和 `getValidAccounts` 返回 tags**

修改 `getAccounts` 函数：

```python
@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            # 为每个账号附加 tags
            for row in rows_list:
                tags = conn.execute('''
                    SELECT t.id, t.name, t.color FROM tags t
                    JOIN account_tags at ON t.id = at.tag_id
                    WHERE at.account_id = ?
                ''', (row[0],)).fetchall()
                row.append([dict(t) for t in tags])

        return jsonify({"code": 200, "msg": None, "data": rows_list}), 200
    except Exception as e:
        return jsonify({"code": 500, "msg": f"获取账号列表失败: {str(e)}", "data": None}), 500
```

同样修改 `getValidAccounts`，在返回前为每个 row 附加 tags（同上逻辑）。

---

### Task 3: 后端 — 标签 API 测试

**Files:**
- Create: `backend/tests/test_account_tags.py`

- [ ] **Step 1: 编写测试**

```python
import sqlite3
import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_create_and_list_tags(client):
    r = client.post('/api/tags', json={'name': '测试标签', 'color': '#ff0000'})
    assert r.status_code == 200
    tag_id = r.get_json()['data']['id']

    r = client.get('/api/tags')
    assert r.status_code == 200
    tags = r.get_json()['data']
    assert any(t['name'] == '测试标签' for t in tags)

    client.delete(f'/api/tags/{tag_id}')


def test_duplicate_tag_name(client):
    client.post('/api/tags', json={'name': '唯一标签'})
    r = client.post('/api/tags', json={'name': '唯一标签'})
    assert r.status_code == 409
    # cleanup
    tags = client.get('/api/tags').get_json()['data']
    for t in tags:
        if t['name'] == '唯一标签':
            client.delete(f'/api/tags/{t["id"]}')


def test_account_tags_crud(client):
    # 需要先有账号 — 用已有数据库中的账号或 mock
    r = client.get('/getAccounts')
    accounts = r.get_json().get('data', [])
    if not accounts:
        pytest.skip('No accounts in test DB')

    account_id = accounts[0][0]
    tag = client.post('/api/tags', json={'name': '账号标签测试'}).get_json()['data']

    r = client.put(f'/api/accounts/{account_id}/tags', json={'tag_ids': [tag['id']]})
    assert r.status_code == 200

    r = client.get(f'/api/accounts/{account_id}/tags')
    assert r.status_code == 200
    assert any(t['id'] == tag['id'] for t in r.get_json()['data'])

    # 清理
    client.put(f'/api/accounts/{account_id}/tags', json={'tag_ids': []})
    client.delete(f'/api/tags/{tag["id"]}')
```

- [ ] **Step 2: 运行测试**

```bash
cd backend && python -m pytest tests/test_account_tags.py -v
```

---

### Task 4: 前端 — API 和 Store 更新

**Files:**
- Modify: `frontend/src/api/account.js`
- Modify: `frontend/src/stores/account.js`

- [ ] **Step 1: 在 `account.js` API 中添加标签方法**

```javascript
  // ── 标签管理 ──
  getTags() {
    return http.get('/api/tags')
  },

  createTag(data) {
    return http.post('/api/tags', data)
  },

  deleteTag(id) {
    return http.delete(`/api/tags/${id}`)
  },

  setAccountTags(accountId, tagIds) {
    return http.put(`/api/accounts/${accountId}/tags`, { tag_ids: tagIds })
  },

  getAccountTags(accountId) {
    return http.get(`/api/accounts/${accountId}/tags`)
  }
```

- [ ] **Step 2: 修改 `account.js` store 的 `setAccounts` 解析 tags**

```javascript
  const setAccounts = (accountsData) => {
    accounts.value = accountsData.map(item => {
      return {
        id: item[0],
        type: item[1],
        filePath: item[2],
        name: item[3],
        status: item[4] === -1 ? '验证中' : (item[4] === 1 ? '正常' : '异常'),
        platform: platformIdToName[item[1]] || '未知',
        avatar: item[5] || '',
        tags: item[6] || []
      }
    })
  }
```

- [ ] **Step 3: 添加全局 tags 状态和加载方法**

```javascript
  const allTags = ref([])

  const loadTags = async () => {
    try {
      const res = await accountApi.getTags()
      if (res.code === 200 && res.data) {
        allTags.value = res.data
      }
    } catch (e) {
      console.error('加载标签失败:', e)
    }
  }

  // 在 return 中导出 allTags 和 loadTags
```

---

### Task 5: 前端 — TagPopover 组件

**Files:**
- Create: `frontend/src/components/TagPopover.vue`

- [ ] **Step 1: 创建 TagPopover 组件**

```vue
<template>
  <el-popover
    :visible="visible"
    placement="bottom"
    :width="240"
    trigger="click"
    @update:visible="$emit('update:visible', $event)"
  >
    <template #reference>
      <slot />
    </template>
    <div class="tag-popover">
      <div class="tag-popover-search">
        <el-input
          v-model="keyword"
          size="small"
          placeholder="搜索或创建标签..."
          clearable
          @keyup.enter="handleCreate"
        />
      </div>
      <div class="tag-popover-list">
        <div
          v-for="tag in filteredTags"
          :key="tag.id"
          class="tag-popover-item"
          @click="toggleTag(tag)"
        >
          <span class="tag-dot" :style="{ background: tag.color }"></span>
          <span class="tag-name">{{ tag.name }}</span>
          <el-icon v-if="isSelected(tag)" class="tag-check"><Check /></el-icon>
        </div>
        <div v-if="keyword && !exactMatch" class="tag-popover-create" @click="handleCreate">
          <el-icon><Plus /></el-icon>
          创建 "{{ keyword }}"
        </div>
        <div v-if="filteredTags.length === 0 && !keyword" class="tag-popover-empty">
          暂无标签
        </div>
      </div>
    </div>
  </el-popover>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Check, Plus } from '@element-plus/icons-vue'
import { accountApi } from '@/api/account'
import { useAccountStore } from '@/stores/account'

const props = defineProps({
  visible: { type: Boolean, default: false },
  accountId: { type: Number, required: true },
  selectedTags: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:visible', 'changed'])

const accountStore = useAccountStore()
const keyword = ref('')

const filteredTags = computed(() => {
  if (!keyword.value) return accountStore.allTags
  const kw = keyword.value.toLowerCase()
  return accountStore.allTags.filter(t => t.name.toLowerCase().includes(kw))
})

const exactMatch = computed(() =>
  accountStore.allTags.some(t => t.name.toLowerCase() === keyword.value.toLowerCase())
)

const selectedIds = computed(() => new Set(props.selectedTags.map(t => t.id)))

const isSelected = (tag) => selectedIds.value.has(tag.id)

async function toggleTag(tag) {
  const ids = [...selectedIds.value]
  const idx = ids.indexOf(tag.id)
  if (idx >= 0) ids.splice(idx, 1)
  else ids.push(tag.id)
  await accountApi.setAccountTags(props.accountId, ids)
  emit('changed')
}

async function handleCreate() {
  const name = keyword.value.trim()
  if (!name) return
  try {
    const res = await accountApi.createTag({ name })
    if (res.code === 200) {
      await accountStore.loadTags()
      const newTag = res.data
      const ids = [...selectedIds.value, newTag.id]
      await accountApi.setAccountTags(props.accountId, ids)
      keyword.value = ''
      emit('changed')
    }
  } catch (e) {
    console.error('创建标签失败:', e)
  }
}
</script>

<style lang="scss" scoped>
.tag-popover {
  .tag-popover-search { margin-bottom: 8px; }
  .tag-popover-list { max-height: 200px; overflow-y: auto; }
  .tag-popover-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    &:hover { background: rgba(255,255,255,0.06); }
    .tag-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
    .tag-name { flex: 1; }
    .tag-check { color: #8b5cf6; }
  }
  .tag-popover-create {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    font-size: 13px;
    color: #8b5cf6;
    cursor: pointer;
    border-radius: 6px;
    &:hover { background: rgba(139,92,246,0.1); }
  }
  .tag-popover-empty { text-align: center; padding: 12px; font-size: 13px; color: #64748b; }
}
</style>
```

---

### Task 6: 前端 — AccountManagement 卡片标签 + 筛选

**Files:**
- Modify: `frontend/src/views/AccountManagement.vue`

- [ ] **Step 1: 导入 TagPopover 并添加标签筛选状态**

在 `<script setup>` 中：

```javascript
import TagPopover from '@/components/TagPopover.vue'

const activeTagId = ref(null)
const tagPopoverVisible = ref(false)
const tagPopoverAccountId = ref(null)

onMounted(() => {
  fetchAccountsQuick()
  accountStore.loadTags()
})

const tagFilterOptions = computed(() => accountStore.allTags)

const filteredAccounts = computed(() => {
  let accounts = accountStore.accounts
  if (activeTab.value !== 'all') {
    accounts = accounts.filter(a => a.platform === activeTab.value)
  }
  if (activeTagId.value) {
    accounts = accounts.filter(a => a.tags?.some(t => t.id === activeTagId.value))
  }
  if (searchKeyword.value) {
    const keyword = searchKeyword.value.toLowerCase()
    accounts = accounts.filter(a => a.name.toLowerCase().includes(keyword))
  }
  return accounts
})

function openTagPopover(accountId) {
  tagPopoverAccountId.value = accountId
  tagPopoverVisible.value = true
}

async function onTagChanged() {
  await fetchAccountsQuick()
}
```

- [ ] **Step 2: 在模板的搜索栏下方添加标签筛选栏**

```html
    <!-- 标签筛选 -->
    <div v-if="tagFilterOptions.length > 0" class="tag-filter-bar">
      <button
        :class="['tag-filter-item', { active: !activeTagId }]"
        @click="activeTagId = null"
      >全部标签</button>
      <button
        v-for="tag in tagFilterOptions"
        :key="tag.id"
        :class="['tag-filter-item', { active: activeTagId === tag.id }]"
        @click="activeTagId = activeTagId === tag.id ? null : tag.id"
      >
        <span class="tag-dot" :style="{ background: tag.color }"></span>
        {{ tag.name }}
      </button>
    </div>
```

- [ ] **Step 3: 在卡片的 platform-row 区域添加标签展示和 + 按钮**

在 `platform-row` div 内、`status-badge` 之后添加：

```html
              <span
                v-for="tag in account.tags"
                :key="tag.id"
                class="account-tag"
                :style="{ borderColor: tag.color, color: tag.color }"
              >{{ tag.name }}</span>
              <TagPopover
                :visible="tagPopoverVisible && tagPopoverAccountId === account.id"
                :account-id="account.id"
                :selected-tags="account.tags || []
                @update:visible="tagPopoverVisible = $event"
                @changed="onTagChanged"
              >
                <button class="tag-add-btn" @click.stop="openTagPopover(account.id)">
                  <el-icon><Plus /></el-icon>
                </button>
              </TagPopover>
```

- [ ] **Step 4: 添加样式**

```scss
  .tag-filter-bar {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
    flex-wrap: wrap;

    .tag-filter-item {
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 6px 12px;
      background: $bg-surface;
      border: 1px solid $border;
      border-radius: 8px;
      font-size: 13px;
      color: $text-secondary;
      cursor: pointer;
      transition: all $transition-base;

      &:hover { background: rgba($brand-start, 0.1); }
      &.active {
        background: rgba($brand-start, 0.15);
        border-color: $brand-start;
        color: #fff;
      }

      .tag-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
      }
    }
  }

  .account-tag {
    display: inline-flex;
    align-items: center;
    padding: 1px 6px;
    border: 1px solid;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 500;
    line-height: 16px;
  }

  .tag-add-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    height: 18px;
    border: 1px dashed rgba(255,255,255,0.2);
    border-radius: 4px;
    background: transparent;
    color: $text-muted;
    cursor: pointer;
    font-size: 12px;
    transition: all $transition-base;

    &:hover {
      border-color: $brand-start;
      color: $brand-start;
      background: rgba($brand-start, 0.1);
    }
  }
```

---

### Task 7: 前端 — AccountSelectDialog 标签筛选

**Files:**
- Modify: `frontend/src/components/AccountSelectDialog.vue`

- [ ] **Step 1: 在平台列表下方添加标签筛选区域**

在 `dialog-platform-list` div 末尾添加：

```html
          <div v-if="accountStore.allTags.length > 0" class="dialog-tag-section">
            <div class="dialog-tag-title">标签筛选</div>
            <div
              :class="['dialog-platform-item', 'cursor-pointer', { active: !accountFilterTag }]"
              @click="accountFilterTag = null"
            >全部标签</div>
            <div
              v-for="tag in accountStore.allTags"
              :key="tag.id"
              :class="['dialog-platform-item', 'cursor-pointer', { active: accountFilterTag === tag.id }]"
              @click="accountFilterTag = accountFilterTag === tag.id ? null : tag.id"
            >
              <span class="tag-dot" :style="{ background: tag.color }"></span>
              {{ tag.name }}
            </div>
          </div>
```

- [ ] **Step 2: 添加标签筛选状态和过滤逻辑**

```javascript
const accountFilterTag = ref(null)

const filteredAccounts = computed(() => {
  let list = accountStore.accounts.filter(a => platformNames.value.includes(a.platform))
  if (accountFilterPlatform.value) {
    list = list.filter(a => a.platform === accountFilterPlatform.value)
  }
  if (accountFilterTag.value) {
    list = list.filter(a => a.tags?.some(t => t.id === accountFilterTag.value))
  }
  list = list.filter(a => !isPlatformDisabled(a.platform))
  return list
})
```

- [ ] **Step 3: 添加标签区域样式**

```scss
    .dialog-tag-section {
      border-top: 1px solid rgba(255, 255, 255, 0.06);
      margin-top: 8px;
      padding-top: 8px;

      .dialog-tag-title {
        padding: 8px 16px 4px;
        font-size: 11px;
        color: $text-muted;
        text-transform: uppercase;
        letter-spacing: 0.5px;
      }

      .tag-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        flex-shrink: 0;
      }
    }
```

---

### Task 8: 验证与提交

- [ ] **Step 1: 启动后端并运行测试**

```bash
cd backend && python -m pytest tests/test_account_tags.py -v
```

- [ ] **Step 2: 启动前端开发服务器**

```bash
cd frontend && npm run dev
```

- [ ] **Step 3: 手动验证**

1. 打开账号管理页面，确认标签筛选栏出现
2. 点击卡片上的 + 按钮，创建标签并关联
3. 刷新页面确认标签持久化
4. 点击标签筛选栏，确认过滤生效
5. 打开视频发布/图集发布，打开选择账号对话框，确认标签筛选可用

- [ ] **Step 4: 提交**

```bash
git add backend/init_db.py backend/app.py backend/tests/test_account_tags.py \
        frontend/src/api/account.js frontend/src/stores/account.js \
        frontend/src/components/TagPopover.vue \
        frontend/src/views/AccountManagement.vue \
        frontend/src/components/AccountSelectDialog.vue
git commit -m "feat: 账号标签体系 — 多标签、卡片添加、筛选过滤"
```
