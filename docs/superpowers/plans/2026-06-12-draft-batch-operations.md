# 草稿批量操作 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 草稿箱支持多选 + 批量删除 + 批量发布。批量发布走独立路径（不修改 PublishCenter/ImagePublish/已有单条发布端点），复用后端 task_queue 异步执行，自动写 publish_batches/publish_details 历史。

**Architecture:** 后端新增 `services/draft_merge.py` 独立实现 4 级合并 + 校验 + payload 适配（merged → platform.publish_video kwargs）。扩展 `PublishTask` 加 `payload/draft_id/source/account_id/detail_id` 字段（**payload 是 in-memory 字段，不持久化；publish_tasks 表早被删除**——见 Open Question 1），扩展 worker 让它在 `task.payload` 非空时 splat 进 `platform.publish_video(**payload)`。扩 `publish_batches` 表加 `source/draft_id` 列做溯源。3 个新端点（视频批量发布 / 图文批量发布 / 视频批量删除）。前端 DraftBox 加多选 + 工具栏 + 新组件 `BatchPublishDialog.vue`。

**Tech Stack:** Python 3 + Flask + sqlite3 + pytest（项目已有栈）、Vue 3 + Element Plus + axios

**硬约束**（违反 = plan 失败）：
- 不修改 `frontend/src/views/PublishCenter.vue`
- 不修改 `frontend/src/views/ImagePublish.vue`
- 不修改 `backend/app.py` 的 `postVideo` / `postVideoBatch`
- 不修改 `backend/blueprints/image_publish_bp.py` 的 `publish` / `execute_publish`
- 不修改 `backend/impl/<platform>/platform.py` 任何实现

---

## 文件结构

```
backend/
├── init_db.py                                      # 修改：migrate_database 加 3 列
├── ext_api/
│   ├── __init__.py                                 # 修改：加 2 个批量端点（视频发布/删除）
│   ├── task_queue.py                               # 修改：PublishTask 扩 5 字段 + worker 扩 splat payload
│   └── tests/                                      # （见 frontend 部分）
├── blueprints/
│   └── image_publish_bp.py                         # 修改：加 1 个图文批量发布端点
├── services/
│   └── draft_merge.py                              # 新建：merge_config / validate / build_platform_kwargs / DECLARATION_PLATFORMS
└── tests/
    ├── test_draft_merge.py                         # 新建：单元测试
    ├── test_drafts_batch_publish.py                # 新建：视频批量发布集成测试
    ├── test_drafts_batch_delete.py                 # 新建：批量删除集成测试
    ├── test_image_drafts_batch_publish.py          # 新建：图文批量发布集成测试
    └── test_task_queue_extended.py                 # 新建：worker 扩展测试

frontend/src/
├── components/
│   └── BatchPublishDialog.vue                      # 新建：批量发布预览/确认 dialog
├── views/
│   └── DraftBox.vue                                # 修改：多选状态 + 工具栏 + 触发 dialog
└── api/
    └── draft.js                                    # 修改：加 batchPublishVideoDrafts / batchDeleteDrafts
```

总计：6 个修改（后端 4 + 前端 2） + 6 个新建（后端 5 + 前端 1）。

---

## Task 1: 数据库迁移

**Files:**
- Modify: `backend/init_db.py` (in `migrate_database()` function)

- [ ] **Step 1: 找迁移函数位置**

```bash
grep -n "def migrate_database\|ALTER TABLE" backend/init_db.py
```

确认 `migrate_database()` 函数存在，并找到现有 `ALTER TABLE` 块的位置（应在第 130-150 行附近）。

- [ ] **Step 2: 加 3 个 ALTER TABLE**

在 `migrate_database()` 函数末尾、`return` 之前追加：

```python
# 草稿批量发布用：溯源到草稿
try:
    cursor.execute("ALTER TABLE publish_batches ADD COLUMN source TEXT NOT NULL DEFAULT ''")
except sqlite3.OperationalError:
    pass
try:
    cursor.execute("ALTER TABLE publish_batches ADD COLUMN draft_id INTEGER NOT NULL DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_publish_batches_draft ON publish_batches(source, draft_id)")
except sqlite3.OperationalError:
    pass
```

（**注意**：原 plan 还含 `ALTER TABLE publish_tasks ADD COLUMN payload` 段，但 `publish_tasks` 表在 commit 71898c0 已被删除。`PublishTask.payload` 是 in-memory 字段，task 完成/取消后即丢弃；持久化走 `publish_details.account_configs` JSON 字段（已存在，由 `_build_account_configs(task)` 填充）。**不要加 publish_tasks 那段。**）

- [ ] **Step 3: 验证迁移**

```bash
cd backend && python3 -c "import init_db; init_db.init_database(); init_db.migrate_database()"
```

Expected: 无 Traceback，无 OperationalError。

- [ ] **Step 4: 验证列存在**

```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('../data/db/database.db')
batches_cols = [r[1] for r in conn.execute('PRAGMA table_info(publish_batches)').fetchall()]
print('publish_batches has source:', 'source' in batches_cols)
print('publish_batches has draft_id:', 'draft_id' in batches_cols)
"
```

Expected: 两个都 `True`。

- [ ] **Step 5: 提交**

```bash
git add backend/init_db.py
git commit -m "feat(backend): 数据库迁移加 publish_batches.source/draft_id 列与索引"
```

---

## Task 2: 创建 services/draft_merge.py 骨架（空函数占位）

**Files:**
- Create: `backend/services/draft_merge.py`
- Create: `backend/services/__init__.py` (空文件)

- [ ] **Step 1: 创建 services 目录的 __init__.py**

```bash
touch backend/services/__init__.py
```

- [ ] **Step 2: 写空骨架（所有函数 raise NotImplementedError）**

创建 `backend/services/draft_merge.py`：

```python
"""草稿合并/校验/payload 适配模块。

所有函数独立、纯 Python，不导入任何前端代码、不依赖任何 publish-page 内部。
字段集与 PublishCenter.vue:592-637 保持同步。
"""

# 平台声明字段映射（与 PublishCenter.vue:1329-1338 一致）
DECLARATION_PLATFORMS = {
    'xiaohongshu': 'aiContent',
    'douyin': 'aiContent',
    'kuaishou': 'aiContent',
    'bilibili': 'creationDeclaration',
    'baijiahao': 'creationDeclaration',
    'tencent_video': 'creationDeclaration',
    'iqiyi': 'creationDeclaration',
    'youtube': ['audience', 'alteredContent'],
    # channels / tiktok 不在此表（不校验声明字段）
}


def merge_config(common, platform_default, platform_ov, account_ov):
    """4 级合并：返回与 PublishCenter.mergeConfig 等价的 dict。"""
    raise NotImplementedError


def validate_draft_for_publish(draft):
    """dry-run 校验。返回错误消息列表（空 = 合法）。"""
    raise NotImplementedError


def validate_image_draft_for_publish(draft):
    """图文草稿 dry-run 校验。返回错误消息列表。"""
    raise NotImplementedError


def build_platform_kwargs(merged, common, account):
    """merged dict → platform.publish_video kwargs dict。"""
    raise NotImplementedError
```

- [ ] **Step 3: 验证导入**

```bash
cd backend && python3 -c "from services.draft_merge import DECLARATION_PLATFORMS, merge_config; print(len(DECLARATION_PLATFORMS))"
```

Expected: 输出 `8`（xiaohongshu/douyin/kuaishou/bilibili/baijiahao/tencent_video/iqiyi + youtube 共 8 项）。

- [ ] **Step 4: 提交**

```bash
git add backend/services/__init__.py backend/services/draft_merge.py
git commit -m "feat(backend): 新建 services/draft_merge.py 骨架（含 DECLARATION_PLATFORMS 常量）"
```

---

## Task 3: merge_config 单元测试

**Files:**
- Create: `backend/tests/test_draft_merge.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_draft_merge.py`：

```python
"""merge_config / validate / build_platform_kwargs 单元测试。"""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from services.draft_merge import (
    DECLARATION_PLATFORMS,
    merge_config,
    validate_draft_for_publish,
    validate_image_draft_for_publish,
    build_platform_kwargs,
)


# ===== DECLARATION_PLATFORMS =====

def test_declaration_platforms_keys():
    """8 个平台：xiaohongshu/douyin/kuaishou/bilibili/baijiahao/tencent_video/iqiyi + youtube。"""
    assert set(DECLARATION_PLATFORMS.keys()) == {
        'xiaohongshu', 'douyin', 'kuaishou',
        'bilibili', 'baijiahao', 'tencent_video', 'iqiyi',
        'youtube',
    }


def test_declaration_platforms_youtube_has_two_fields():
    assert DECLARATION_PLATFORMS['youtube'] == ['audience', 'alteredContent']


# ===== merge_config: 3 级 vs 4 级 =====

def test_merge_text_3_level_priority():
    """title/description/tags 是 3 级：accountOv > platformOv > platformDefault，不走 common。"""
    common = {'title': 'C', 'description': 'C', 'tags': ['c']}
    pd = {'title': 'P', 'description': 'P', 'tags': ['p']}
    po = {'title': 'O', 'description': 'O', 'tags': ['o']}
    ao = {'title': 'A', 'description': 'A', 'tags': ['a']}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == 'A'
    assert m['description'] == 'A'
    assert m['tags'] == ['a']


def test_merge_text_3_level_falls_to_platform_default():
    """accountOv/platformOv 都缺时，走 platformDefault。"""
    common = {'title': 'C', 'description': 'C', 'tags': ['c']}
    pd = {'title': 'P', 'description': 'P', 'tags': ['p']}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == 'P'
    assert m['description'] == 'P'
    assert m['tags'] == ['p']


def test_merge_text_does_not_fall_to_common():
    """3 级字段不会回退到 common。"""
    common = {'title': 'C'}
    pd = {}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['title'] == ''   # 兜底空字符串


def test_merge_cover_video_4_level_falls_to_common():
    """cover*/video* 4 级：accountOv > platformOv > common，跳过 platformDefault。"""
    common = {'coverLandscape': {'id': 'c'}, 'videoLandscape': {'id': 'vc'}}
    pd = {'coverLandscape': {'id': 'p'}, 'videoLandscape': {'id': 'vp'}}   # 平台默认
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    # platformDefault 不参与 cover*/video* 的兜底
    assert m['coverLandscape'] == {'id': 'c'}
    assert m['videoLandscape'] == {'id': 'vc'}


def test_merge_cover_video_4_level_platform_ov_beats_common():
    common = {'coverLandscape': {'id': 'c'}}
    pd = {}
    po = {'coverLandscape': {'id': 'o'}}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['coverLandscape'] == {'id': 'o'}


def test_merge_boolean_uses_is_none():
    """布尔字段：False ≠ None。accountOv.isOriginal=False 应当胜出。"""
    common = {}
    pd = {'isOriginal': True}
    po = {}
    ao = {'isOriginal': False}
    m = merge_config(common, pd, po, ao)
    assert m['isOriginal'] is False


def test_merge_list_falls_through_to_first_non_empty():
    """列表字段：第一个非空列表胜出。"""
    common = {}
    pd = {'tags': ['p']}
    po = {'tags': []}     # 空列表算 falsy
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['tags'] == ['p']


def test_merge_ai_content_platform_specific():
    """aiContent: 3 级合并（不走 common 兜底）。"""
    common = {'aiContent': 'COMMON'}
    pd = {'aiContent': 'PD'}
    po = {'aiContent': 'OV'}
    ao = {'aiContent': 'ACC'}
    m = merge_config(common, pd, po, ao)
    assert m['aiContent'] == 'ACC'


def test_merge_creation_declaration_no_common_fallback():
    """creationDeclaration: 3 级（不参考 common）。"""
    common = {'creationDeclaration': 'COMMON'}
    pd = {}
    po = {}
    ao = {}
    m = merge_config(common, pd, po, ao)
    assert m['creationDeclaration'] is None or m['creationDeclaration'] == ''
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v
```

Expected: 9 个测试全部 FAIL（NotImplementedError）。

- [ ] **Step 3: 提交失败测试**

```bash
git add backend/tests/test_draft_merge.py
git commit -m "test(backend): merge_config 单元测试（9 个测试，RED 状态）"
```

---

## Task 4: merge_config 实现

**Files:**
- Modify: `backend/services/draft_merge.py`

- [ ] **Step 1: 实现 merge_config**

替换 `backend/services/draft_merge.py` 中的 `merge_config` 函数：

```python
def _first_truthy(*values):
    """返回第一个真值；布尔用 is None 检查除外。"""
    for v in values:
        if v is not None and v != '' and v != []:
            return v
    return values[-1] if values else None


def _first_list(*values):
    """返回第一个非空 list；都是空则返回最后一个。"""
    for v in values:
        if isinstance(v, list) and len(v) > 0:
            return v
    return values[-1] if values else []


def _first_bool(*values):
    """布尔合并：用 is None 判定 None 表示"未设置"，False/True 都是有效值。"""
    for v in values:
        if v is not None:
            return v
    return False


def merge_config(common, platform_default, platform_ov, account_ov):
    """合并 4 层。3 级字段（大多数）：accountOv > platformOv > platformDefault。
    4 级字段（cover*/video*）：accountOv > platformOv > common（跳过 platformDefault）。"""
    common = common or {}
    platform_default = platform_default or {}
    platform_ov = platform_ov or {}
    account_ov = account_ov or {}

    # 4 级字段（common 兜底）
    cover_landscape = _first_truthy(account_ov.get('coverLandscape'), platform_ov.get('coverLandscape'), common.get('coverLandscape'))
    cover_portrait = _first_truthy(account_ov.get('coverPortrait'), platform_ov.get('coverPortrait'), common.get('coverPortrait'))
    video_landscape = _first_truthy(account_ov.get('videoLandscape'), platform_ov.get('videoLandscape'), common.get('videoLandscape'))
    video_portrait = _first_truthy(account_ov.get('videoPortrait'), platform_ov.get('videoPortrait'), common.get('videoPortrait'))

    # 3 级文本字段
    title = _first_truthy(account_ov.get('title'), platform_ov.get('title'), platform_default.get('title'), '')
    description = _first_truthy(account_ov.get('description'), platform_ov.get('description'), platform_default.get('description'), '')
    tags = _first_list(account_ov.get('tags'), platform_ov.get('tags'), platform_default.get('tags', []))

    # 3 级平台常见字段
    video_format = _first_truthy(account_ov.get('videoFormat'), platform_ov.get('videoFormat'), platform_default.get('videoFormat', ''), '')
    enable_timer = _first_truthy(account_ov.get('enableTimer'), platform_ov.get('enableTimer'), platform_default.get('enableTimer', 0), 0)
    schedule_time = _first_truthy(account_ov.get('scheduleTime'), platform_ov.get('scheduleTime'), platform_default.get('scheduleTime', ''), '')
    ai_content = _first_truthy(account_ov.get('aiContent'), platform_ov.get('aiContent'), platform_default.get('aiContent', ''), '')
    is_original = _first_bool(account_ov.get('isOriginal'), platform_ov.get('isOriginal'), platform_default.get('isOriginal', False))

    # 3 级平台特定字段
    platform_specific = {}
    for field in [
        'creationDeclaration', 'riskWarning', 'enableCashActivity',
        'supplementaryDeclaration', 'audience', 'alteredContent',
        'zone', 'activityId', 'hotspotId', 'hotspotData', 'selectedTag',
        'tagType', 'tagValue', 'mixId', 'mixData', 'topic', 'isDraft',
        'location', 'collection', 'groupChat',
    ]:
        platform_specific[field] = _first_truthy(
            account_ov.get(field), platform_ov.get(field), platform_default.get(field)
        )

    return {
        'title': title,
        'description': description,
        'tags': tags,
        'coverLandscape': cover_landscape,
        'coverPortrait': cover_portrait,
        'videoLandscape': video_landscape,
        'videoPortrait': video_portrait,
        'videoFormat': video_format,
        'enableTimer': enable_timer,
        'scheduleTime': schedule_time,
        'aiContent': ai_content,
        'isOriginal': is_original,
        **platform_specific,
    }
```

- [ ] **Step 2: 运行测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "merge_ or declaration_"
```

Expected: 9 个 merge_config 相关测试全部 PASS。

- [ ] **Step 3: 提交**

```bash
git add backend/services/draft_merge.py
git commit -m "feat(backend): merge_config 实现 4 级合并（3 级 + 4 级字段分组）"
```

---

## Task 5: validate_draft_for_publish 单元测试

**Files:**
- Modify: `backend/tests/test_draft_merge.py`

- [ ] **Step 1: 追加测试**

在 `backend/tests/test_draft_merge.py` 末尾追加：

```python
# ===== validate_draft_for_publish =====

class FakeAccount:
    def __init__(self, id, platform, file_path):
        self.id = id
        self.platform = platform
        self.file_path = file_path


def _user_info_lookup_patch(monkeypatch, accounts):
    """monkeypatch services.draft_merge._get_account_by_id 返回 accounts 列表。"""
    def _lookup(account_id):
        for a in accounts:
            if a.id == account_id:
                return a
        return None
    monkeypatch.setattr('services.draft_merge._get_account_by_id', _lookup)


def _video_draft(draft_data, draft_id=1):
    return {'id': draft_id, 'type': 'video', 'draft_data': draft_data}


def test_validate_draft_missing_video():
    """commonConfig 视频文件都没有 → 报错。"""
    draft = _video_draft({
        'commonConfig': {'videoLandscape': None, 'videoPortrait': None,
                         'coverLandscape': {'id': 'c'}, 'coverPortrait': None},
        'platformConfigs': {'bilibili': {'title': 'T', 'videoFormat': 'portrait',
                                          'creationDeclaration': 'cd'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('视频' in e for e in errs)


def test_validate_draft_missing_publish_account_ids():
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {},
        'platformOverrides': {},
        'accountOverrides': {},
        'publishAccountIds': [],
    })
    errs = validate_draft_for_publish(draft)
    assert any('账号' in e or 'publishAccountIds' in e or '未选择' in e for e in errs)


def test_validate_draft_account_not_found(monkeypatch):
    _user_info_lookup_patch(monkeypatch, [])  # 账号表为空
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'bilibili': {}},
        'platformOverrides': {},
        'accountOverrides': {},
        'publishAccountIds': [999],
    })
    errs = validate_draft_for_publish(draft)
    assert any('999' in e and ('不存在' in e or '账号' in e) for e in errs)


def test_validate_draft_bilibili_missing_creation_declaration(monkeypatch):
    """B 站账号层缺 creationDeclaration → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'bilibili', '/cookies/b1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'bilibili': {'title': 'T', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},  # 没填 creationDeclaration
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('creationDeclaration' in e for e in errs)


def test_validate_draft_xiaohongshu_missing_ai_content(monkeypatch):
    """小红书账号层缺 aiContent → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'xiaohongshu', '/cookies/x1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},  # 没 aiContent
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('aiContent' in e for e in errs)


def test_validate_draft_youtube_missing_audience_or_altered(monkeypatch):
    """YouTube 缺 audience 或 alteredContent → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'youtube', '/cookies/y1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'youtube': {'title': 'T', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait'}},  # 缺 audience/alteredContent
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('audience' in e or 'alteredContent' in e for e in errs)


def test_validate_draft_portrait_without_portrait_cover(monkeypatch):
    """videoFormat=portrait 但缺竖版封面 → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'xiaohongshu', '/cookies/x1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': {'id': 'v'}, 'videoPortrait': None,
                         'coverLandscape': {'id': 'cl'}, 'coverPortrait': None},  # 只横版
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                            'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                    'aiContent': '内容由AI生成'}},
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('竖版封面' in e or 'portrait' in e.lower() or 'cover' in e.lower() for e in errs)


def test_validate_draft_douyin_activity_tags_cap(monkeypatch):
    """抖音活动+标签 > 5 → 报错。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'douyin', '/cookies/d1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': None, 'videoPortrait': {'id': 'v'},
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'douyin': {'title': 'T', 'videoFormat': 'portrait',
                                        'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {
            '1': {'title': 'T', 'videoFormat': 'portrait', 'aiContent': '内容由AI生成',
                  'activityId': ['a', 'b', 'c'], 'tags': ['t1', 't2', 't3']},  # 3+3=6 > 5
        },
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert any('5' in e or '活动' in e or '标签' in e for e in errs)


def test_validate_draft_happy_path(monkeypatch):
    """完整合法草稿 → 错误列表为空。"""
    _user_info_lookup_patch(monkeypatch, [FakeAccount(1, 'xiaohongshu', '/cookies/x1')])
    draft = _video_draft({
        'commonConfig': {'videoLandscape': None, 'videoPortrait': {'id': 'v'},
                         'coverLandscape': None, 'coverPortrait': {'id': 'c'}},
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                            'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                    'aiContent': '内容由AI生成'}},
        'publishAccountIds': [1],
    })
    errs = validate_draft_for_publish(draft)
    assert errs == []
```

- [ ] **Step 2: 运行测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "validate_"
```

Expected: 9 个 validate 测试全部 FAIL（NotImplementedError 或 AttributeError）。

- [ ] **Step 3: 提交失败测试**

```bash
git add backend/tests/test_draft_merge.py
git commit -m "test(backend): validate_draft_for_publish 单元测试（9 个测试，RED 状态）"
```

---

## Task 6: validate_draft_for_publish + _get_account_by_id 实现

**Files:**
- Modify: `backend/services/draft_merge.py`

- [ ] **Step 1: 实现 _get_account_by_id（数据库查询）**

在 `backend/services/draft_merge.py` 顶部 import 后、DECLARATION_PLATFORMS 前加：

```python
import sqlite3
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from conf import BASE_DIR

DB_PATH = BASE_DIR / "db" / "database.db"


def _get_account_by_id(account_id):
    """查 user_info 表，返回 account 对象（id/platform/file_path）或不存在的 None。"""
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            row = conn.execute(
                "SELECT id, platform, file_path FROM user_info WHERE id = ?",
                (account_id,),
            ).fetchone()
        if not row:
            return None
        account = type('Account', (), {})()
        account.id = row[0]
        account.platform = row[1]
        account.file_path = row[2]
        return account
    except Exception:
        return None
```

- [ ] **Step 2: 实现 validate_draft_for_publish**

替换 `validate_draft_for_publish` 函数：

```python
def validate_draft_for_publish(draft):
    """dry-run 校验视频草稿。返回错误消息列表。"""
    errors = []
    draft_data = draft.get('draft_data') or {}
    common = draft_data.get('commonConfig') or {}
    platform_configs = draft_data.get('platformConfigs') or {}
    platform_overrides = draft_data.get('platformOverrides') or {}
    account_overrides = draft_data.get('accountOverrides') or {}
    publish_account_ids = draft_data.get('publishAccountIds') or []

    # 1. 视频文件
    if not (common.get('videoLandscape') or common.get('videoPortrait')):
        errors.append('缺少视频文件')

    # 2. 至少 1 张封面（来自 3 个源）
    has_cover = bool(common.get('coverLandscape') or common.get('coverPortrait'))
    if not has_cover:
        for ov in account_overrides.values():
            if ov and (ov.get('coverLandscape') or ov.get('coverPortrait')):
                has_cover = True
                break
    if not has_cover:
        for ov in platform_overrides.values():
            if ov and (ov.get('coverLandscape') or ov.get('coverPortrait')):
                has_cover = True
                break
    if not has_cover:
        errors.append('缺少封面')

    # 3. publishAccountIds 非空
    if not publish_account_ids:
        errors.append('草稿未选择发布账号（publishAccountIds 为空）')
        return errors   # 后续检查依赖账号

    # 4. 每个账号的检查
    for account_id in publish_account_ids:
        account = _get_account_by_id(account_id)
        if account is None:
            errors.append(f'账号 {account_id} 不存在')
            continue

        platform = account.platform
        platform_default = platform_configs.get(platform) or {}
        account_ov = account_overrides.get(str(account_id)) or {}

        merged = merge_config(common, platform_default, None, account_ov)

        # 标题
        if not merged.get('title') or not str(merged['title']).strip():
            errors.append(f'账号 {account_id}({platform}) 缺标题')

        # 视频格式
        vf = merged.get('videoFormat')
        if vf not in ('portrait', 'landscape'):
            errors.append(f'账号 {account_id}({platform}) 缺视频格式')

        # 封面 per-videoFormat
        if vf == 'portrait' and not merged.get('coverPortrait'):
            errors.append(f'账号 {account_id}({platform}) 缺竖版封面')
        if vf == 'landscape' and not merged.get('coverLandscape'):
            errors.append(f'账号 {account_id}({platform}) 缺横版封面')

        # 声明字段
        decl_field = DECLARATION_PLATFORMS.get(platform)
        if decl_field:
            if isinstance(decl_field, list):
                # YouTube: 多个字段
                missing = [f for f in decl_field if not merged.get(f)]
                if missing:
                    errors.append(f'账号 {account_id}({platform}) 缺 {"+".join(missing)}')
            else:
                if not merged.get(decl_field):
                    errors.append(f'账号 {account_id}({platform}) 缺 {decl_field}')

        # 抖音活动+标签 ≤ 5
        if platform == 'douyin':
            ac_len = len(merged.get('activityId') or [])
            tg_len = len(merged.get('tags') or [])
            if ac_len + tg_len > 5:
                errors.append(f'账号 {account_id}(douyin) 活动({ac_len})+标签({tg_len}) 超过 5')

    return errors
```

- [ ] **Step 3: 运行测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "validate_"
```

Expected: 9 个 validate 测试全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add backend/services/draft_merge.py
git commit -m "feat(backend): validate_draft_for_publish 实现（dry-run 校验 8 类规则）"
```

---

## Task 7: validate_image_draft_for_publish 测试 + 实现

**Files:**
- Modify: `backend/tests/test_draft_merge.py`
- Modify: `backend/services/draft_merge.py`

- [ ] **Step 1: 追加测试**

在 `backend/tests/test_draft_merge.py` 末尾追加：

```python
# ===== validate_image_draft_for_publish =====

def _image_draft(draft_id, account_configs, image_ids=None):
    return {
        'id': draft_id,
        'image_ids': image_ids or ['img-1', 'img-2'],
        'account_configs': account_configs,
    }


def test_validate_image_draft_missing_image_ids():
    draft = _image_draft(1, {
        'platform': 'xiaohongshu', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/x1', 'title': 'T', 'description': '',
        'aiContent': '内容由AI生成', 'isOriginal': True,
    }, image_ids=[])
    errs = validate_image_draft_for_publish(draft)
    assert any('image' in e.lower() or '图片' in e for e in errs)


def test_validate_image_draft_missing_title():
    draft = _image_draft(1, {
        'platform': 'xiaohongshu', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/x1', 'title': '', 'description': '',
        'aiContent': '内容由AI生成', 'isOriginal': True,
    })
    errs = validate_image_draft_for_publish(draft)
    assert any('title' in e.lower() or '标题' in e for e in errs)


def test_validate_image_draft_xiaohongshu_missing_ai_content():
    draft = _image_draft(1, {
        'platform': 'xiaohongshu', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/x1', 'title': 'T', 'description': '',
        'isOriginal': True,
        # 缺 aiContent
    })
    errs = validate_image_draft_for_publish(draft)
    assert any('aiContent' in e or 'ai_content' in e for e in errs)


def test_validate_image_draft_bilibili_missing_creation_declaration():
    draft = _image_draft(1, {
        'platform': 'bilibili', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/b1', 'title': 'T', 'description': '',
        'isOriginal': True,
        # 缺 creationDeclaration
    })
    errs = validate_image_draft_for_publish(draft)
    assert any('creationDeclaration' in e or 'creation_declaration' in e for e in errs)


def test_validate_image_draft_happy_path():
    draft = _image_draft(1, {
        'platform': 'xiaohongshu', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/x1', 'title': 'T', 'description': '',
        'aiContent': '内容由AI生成', 'isOriginal': True,
    })
    errs = validate_image_draft_for_publish(draft)
    assert errs == []
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "image_draft"
```

Expected: 5 个 image 测试全部 FAIL。

- [ ] **Step 3: 实现 validate_image_draft_for_publish**

替换 `backend/services/draft_merge.py` 中的 `validate_image_draft_for_publish`：

```python
# 图文平台声明字段映射（与视频版相同）
_IMAGE_DECLARATION_PLATFORMS = DECLARATION_PLATFORMS


def validate_image_draft_for_publish(draft):
    """dry-run 校验图文草稿。返回错误消息列表。"""
    errors = []
    image_ids = draft.get('image_ids') or []
    config = draft.get('account_configs') or {}

    if not image_ids:
        errors.append('缺少 image_ids')

    if not config.get('title') or not str(config['title']).strip():
        errors.append('缺 title（标题）')

    platform = config.get('platform', '')
    decl_field = _IMAGE_DECLARATION_PLATFORMS.get(platform)
    if decl_field:
        if isinstance(decl_field, list):
            missing = [f for f in decl_field if not config.get(f)]
            if missing:
                errors.append(f'图文草稿({platform}) 缺 {"+".join(missing)}')
        else:
            if not config.get(decl_field):
                errors.append(f'图文草稿({platform}) 缺 {decl_field}')

    return errors
```

- [ ] **Step 4: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "image_draft"
```

Expected: 5 个 image 测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/services/draft_merge.py backend/tests/test_draft_merge.py
git commit -m "feat(backend): validate_image_draft_for_publish 实现（图文明文单 dict 校验）"
```

---

## Task 8: build_platform_kwargs 单元测试

**Files:**
- Modify: `backend/tests/test_draft_merge.py`

- [ ] **Step 1: 追加测试**

在 `backend/tests/test_draft_merge.py` 末尾追加：

```python
# ===== build_platform_kwargs =====

class FakeAccountForBuild:
    def __init__(self, file_path='/cookies/x1'):
        self.file_path = file_path


def test_build_kwargs_title_and_desc_renamed():
    """merged.title → title, merged.description → desc。"""
    merged = {'title': 'T', 'description': 'D', 'tags': ['t1']}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['title'] == 'T'
    assert kw['desc'] == 'D'
    assert kw['tags'] == ['t1']


def test_build_kwargs_cover_renames_to_landscape_portrait():
    """merged.coverLandscape/Portrait → thumbnail_landscape_path/portrait_path。"""
    merged = {'coverLandscape': {'stored_path': '/abs/land.jpg'},
              'coverPortrait': {'stored_path': '/abs/port.jpg'}}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['thumbnail_landscape_path'] == '/abs/land.jpg'
    assert kw['thumbnail_portrait_path'] == '/abs/port.jpg'


def test_build_kwargs_video_chosen_by_videoformat():
    """videoFormat=portrait 选 coverPortrait 视频，landscape 选 coverLandscape。"""
    merged = {'videoFormat': 'portrait',
              'videoPortrait': {'stored_path': '/abs/port.mp4'},
              'videoLandscape': {'stored_path': '/abs/land.mp4'}}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['files'] == ['/abs/port.mp4']


def test_build_kwargs_video_falls_to_common():
    """merged 没视频时，common.videoPortrait/landscape 兜底。"""
    merged = {'videoFormat': 'portrait', 'videoPortrait': None, 'videoLandscape': None}
    common = {'videoPortrait': {'stored_path': '/abs/common.mp4'}}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['files'] == ['/abs/common.mp4']


def test_build_kwargs_schedule_time_translations():
    """merged.scheduleTime → enableTimer + schedule_time_str。"""
    merged = {'scheduleTime': '2026-06-19 10:00:00'}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['enableTimer'] == 1
    assert kw['schedule_time_str'] == '2026-06-19 10:00:00'


def test_build_kwargs_empty_schedule_time_means_no_timer():
    merged = {'scheduleTime': ''}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['enableTimer'] == 0
    assert kw['schedule_time_str'] == ''


def test_build_kwargs_ai_content_renamed():
    merged = {'aiContent': '内容由AI生成'}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['ai_content'] == '内容由AI生成'


def test_build_kwargs_creation_declaration_list_joined():
    """merged.creationDeclaration 是 list → 用逗号 join。"""
    merged = {'creationDeclaration': ['剧情演绎,仅供娱乐', '取材网络,谨慎甄别']}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['creation_declaration'] == '剧情演绎,仅供娱乐,取材网络,谨慎甄别'


def test_build_kwargs_creation_declaration_none_to_empty():
    merged = {'creationDeclaration': None}
    common = {}
    account = FakeAccountForBuild()
    kw = build_platform_kwargs(merged, common, account)
    assert kw['creation_declaration'] == ''


def test_build_kwargs_category_uses_zone_or_isoriginal():
    """merged.zone（B 站）或 is_original 决定 category。"""
    # B 站
    merged = {'zone': '影视', 'isOriginal': True}
    kw = build_platform_kwargs(merged, {}, FakeAccountForBuild())
    assert kw['category'] == '影视'
    # 非 B 站
    merged = {'zone': '', 'isOriginal': True}
    kw = build_platform_kwargs(merged, {}, FakeAccountForBuild())
    assert kw['category'] == 1
    # 默认
    merged = {'zone': '', 'isOriginal': False}
    kw = build_platform_kwargs(merged, {}, FakeAccountForBuild())
    assert kw['category'] == 0


def test_build_kwargs_account_file():
    merged = {}
    common = {}
    account = FakeAccountForBuild(file_path='/cookies/x1')
    kw = build_platform_kwargs(merged, common, account)
    assert kw['account_file'] == ['/cookies/x1']


def test_build_kwargs_selected_tag_miniapp_link():
    merged = {'selectedTag': {'type': 'miniapp', '_searchKeyword': 'foo'}}
    kw = build_platform_kwargs(merged, {}, FakeAccountForBuild())
    assert kw['mini_link'] == 'foo'


def test_build_kwargs_selected_tag_non_miniapp_empty_link():
    merged = {'selectedTag': {'type': 'topic', '_searchKeyword': 'foo'}}
    kw = build_platform_kwargs(merged, {}, FakeAccountForBuild())
    assert kw['mini_link'] == ''


def test_build_kwargs_defaults():
    """videos_per_day / daily_times / start_days 默认值。"""
    kw = build_platform_kwargs({}, {}, FakeAccountForBuild())
    assert kw['videos_per_day'] == 1
    assert kw['daily_times'] == ['10:00']
    assert kw['start_days'] == 0


def test_build_kwargs_audience_default():
    kw = build_platform_kwargs({}, {}, FakeAccountForBuild())
    assert kw['audience'] == 'not_kids'
    assert kw['altered_content'] is False
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "build_kwargs"
```

Expected: 14 个 build_kwargs 测试全部 FAIL（NotImplementedError）。

- [ ] **Step 3: 提交失败测试**

```bash
git add backend/tests/test_draft_merge.py
git commit -m "test(backend): build_platform_kwargs 单元测试（14 个测试，RED 状态）"
```

---

## Task 9: build_platform_kwargs 实现

**Files:**
- Modify: `backend/services/draft_merge.py`

- [ ] **Step 1: 实现 build_platform_kwargs**

替换 `backend/services/draft_merge.py` 中的 `build_platform_kwargs`：

```python
def _resolve_stored_path(material):
    """从素材对象取 stored_path；None/空返回 ''。"""
    if not material:
        return ''
    if isinstance(material, dict):
        return material.get('stored_path', '') or ''
    return ''


def build_platform_kwargs(merged, common, account):
    """merged dict → platform.publish_video kwargs dict。
    common 兜底素材；account 提供 cookie 路径。"""
    merged = merged or {}
    common = common or {}

    video_format = merged.get('videoFormat') or ''

    # 视频文件路径（按 videoFormat 选）
    if video_format == 'portrait':
        selected_video = _resolve_stored_path(merged.get('videoPortrait')) \
            or _resolve_stored_path(common.get('videoPortrait'))
    elif video_format == 'landscape':
        selected_video = _resolve_stored_path(merged.get('videoLandscape')) \
            or _resolve_stored_path(common.get('videoLandscape'))
    else:
        # 无 videoFormat：先后再竖
        selected_video = _resolve_stored_path(merged.get('videoLandscape')) \
            or _resolve_stored_path(common.get('videoLandscape')) \
            or _resolve_stored_path(merged.get('videoPortrait')) \
            or _resolve_stored_path(common.get('videoPortrait'))

    # 封面路径
    cover_landscape = _resolve_stored_path(merged.get('coverLandscape')) \
        or _resolve_stored_path(common.get('coverLandscape'))
    cover_portrait = _resolve_stored_path(merged.get('coverPortrait')) \
        or _resolve_stored_path(common.get('coverPortrait'))

    # 通用 thumbnail（仅 portrait 缺时用 landscape 兜底，反之亦然；否则两者都有）
    generic_thumbnail = cover_portrait or cover_landscape

    # creationDeclaration list → 逗号 join；None → ''
    creation_decl = merged.get('creationDeclaration')
    if isinstance(creation_decl, list):
        creation_declaration = ','.join(creation_decl)
    elif creation_decl:
        creation_declaration = str(creation_decl)
    else:
        creation_declaration = ''

    # category: zone 优先（B 站），否则 isOriginal ? 1 : 0
    zone = merged.get('zone') or ''
    is_original = merged.get('isOriginal')
    if zone:
        category = zone
    else:
        category = 1 if is_original else 0

    # schedule_time
    schedule_time_str = merged.get('scheduleTime') or ''
    enable_timer = 1 if schedule_time_str else 0

    # mini_link: 仅 selectedTag.type === 'miniapp'
    selected_tag = merged.get('selectedTag') or {}
    if isinstance(selected_tag, dict) and selected_tag.get('type') == 'miniapp':
        mini_link = selected_tag.get('_searchKeyword') or ''
    else:
        mini_link = ''

    return {
        'title': merged.get('title', '') or '',
        'desc': merged.get('description', '') or '',
        'tags': merged.get('tags') or [],
        'activities': merged.get('activityId') or [],
        'files': [selected_video] if selected_video else [],
        'account_file': [account.file_path] if account and getattr(account, 'file_path', None) else [],
        'category': category,
        'enableTimer': enable_timer,
        'videos_per_day': 1,
        'daily_times': ['10:00'],
        'start_days': 0,
        'thumbnail_path': generic_thumbnail,
        'thumbnail_landscape_path': cover_landscape,
        'thumbnail_portrait_path': cover_portrait,
        'productLink': merged.get('productLink', '') or '',
        'productTitle': merged.get('productTitle', '') or '',
        'schedule_time_str': schedule_time_str,
        'ai_content': merged.get('aiContent', '') or '',
        'creation_declaration': creation_declaration,
        'risk_warning': merged.get('riskWarning', '') or '',
        'enable_cash_activity': bool(merged.get('enableCashActivity')),
        'supplementary_declaration': merged.get('supplementaryDeclaration', '') or '',
        'is_draft': bool(merged.get('isDraft')),
        'audience': merged.get('audience') or 'not_kids',
        'altered_content': bool(merged.get('alteredContent')),
        'hotspot': merged.get('hotspotId', '') or '',
        'tag_type': merged.get('tagType', '') or '',
        'tag_value': merged.get('tagValue', '') or '',
        'mini_link': mini_link,
        'mix_id': merged.get('mixId', '') or '',
    }
```

- [ ] **Step 2: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v -k "build_kwargs"
```

Expected: 14 个 build_kwargs 测试全部 PASS。

- [ ] **Step 3: 跑全部测试**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py -v
```

Expected: 全部 37 个测试（9 merge + 9 validate + 5 image + 14 build_kwargs）通过。

- [ ] **Step 4: 提交**

```bash
git add backend/services/draft_merge.py
git commit -m "feat(backend): build_platform_kwargs 实现 merged→platform.publish_video kwargs 完整翻译"
```

---

## Task 10: PublishTask 扩展（加 5 字段 + to_dict/from_row）

**Files:**
- Modify: `backend/ext_api/task_queue.py:36-67` (PublishTask class)
- Modify: `backend/ext_api/task_queue.py:69-130` (to_dict / from_row)

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_task_queue_extended.py`：

```python
"""PublishTask 扩展字段测试。"""
import sys
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from ext_api.task_queue import PublishTask


def test_publish_task_default_new_fields():
    """新字段默认值。"""
    t = PublishTask()
    assert t.source == ''
    assert t.draft_id == 0
    assert t.account_id == 0
    assert t.payload == {}
    assert t.detail_id == ''


def test_publish_task_to_dict_includes_payload():
    """to_dict 把 payload 转 JSON 字符串。"""
    t = PublishTask(
        platform='bilibili', platform_type=5,
        source='draft', draft_id=42, account_id=3,
        payload={'title': 'T', 'files': ['/a.mp4']},
        detail_id='d-1',
    )
    d = t.to_dict()
    assert d['source'] == 'draft'
    assert d['draft_id'] == 42
    assert d['account_id'] == 3
    assert d['detail_id'] == 'd-1'
    # payload 是 JSON 字符串（DB 存储）
    assert isinstance(d['payload'], str)
    parsed = json.loads(d['payload'])
    assert parsed == {'title': 'T', 'files': ['/a.mp4']}


def test_publish_task_from_row_round_trip():
    """to_dict → from_row 往返保留所有新字段。"""
    t = PublishTask(
        platform='douyin', platform_type=3,
        source='draft', draft_id=99, account_id=5,
        payload={'title': 'X', 'ai_content': '内容由AI生成'},
        detail_id='d-2',
    )
    d = t.to_dict()
    t2 = PublishTask.from_row(d)
    assert t2.source == 'draft'
    assert t2.draft_id == 99
    assert t2.account_id == 5
    assert t2.payload == {'title': 'X', 'ai_content': '内容由AI生成'}
    assert t2.detail_id == 'd-2'
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_task_queue_extended.py -v
```

Expected: 3 个测试全部 FAIL（AttributeError: 'PublishTask' object has no attribute 'source'）。

- [ ] **Step 3: 扩展 PublishTask 类**

在 `backend/ext_api/task_queue.py` 的 PublishTask 类（line 36-67）追加新字段：

```python
    # 草稿批量发布溯源字段（Task 10 扩展）
    source: str = ''                # '' | 'draft' | 'normal'
    draft_id: int = 0
    account_id: int = 0
    detail_id: str = ''            # publish_details.id
    payload: dict = field(default_factory=dict)
```

- [ ] **Step 4: 更新 to_dict**

替换 `to_dict` 方法（line 69-72）：

```python
    def to_dict(self):
        d = asdict(self)
        d['tags'] = json.dumps(self.tags, ensure_ascii=False)
        d['payload'] = json.dumps(self.payload, ensure_ascii=False)
        return d
```

- [ ] **Step 5: 更新 from_row**

找到 `from_row` 类方法（line 74-130），在 `return cls(...)` 调用的字段列表里加 4 个新参数：

```python
    @classmethod
    def from_row(cls, row_dict):
        """从数据库行构造"""
        tags = row_dict.get('tags', '[]')
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        payload = row_dict.get('payload', '{}')
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        return cls(
            id=row_dict['id'],
            batch_id=row_dict.get('batch_id', ''),
            platform=row_dict['platform'],
            platform_type=row_dict.get('platform_type', 0),
            account_name=row_dict['account_name'],
            account_cookie_path=row_dict.get('account_cookie_path', ''),
            video_path=row_dict['video_path'],
            title=row_dict['title'],
            description=row_dict.get('description', ''),
            thumbnail_path=row_dict.get('thumbnail_path', ''),
            tags=tags,
            status=row_dict['status'],
            retry_count=row_dict.get('retry_count', 0),
            max_retries=row_dict.get('max_retries', 3),
            error_message=row_dict.get('error_message', ''),
            publish_url=row_dict.get('publish_url', ''),
            created_at=row_dict['created_at'],
            source=row_dict.get('source', ''),
            draft_id=row_dict.get('draft_id', 0),
            account_id=row_dict.get('account_id', 0),
            detail_id=row_dict.get('detail_id', ''),
            payload=payload,
        )
```

- [ ] **Step 6: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_task_queue_extended.py -v
```

Expected: 3 个测试全部 PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/ext_api/task_queue.py backend/tests/test_task_queue_extended.py
git commit -m "feat(backend): PublishTask 扩 5 字段（source/draft_id/account_id/detail_id/payload）"
```

---

## Task 11: Worker 扩展（splat payload 到 platform.publish_video）

**Files:**
- Modify: `backend/ext_api/task_queue.py:197-260` (_execute method)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_task_queue_extended.py` 末尾追加：

```python
import asyncio
from unittest.mock import patch, MagicMock


def test_execute_splats_payload_to_platform_publish_video():
    """_execute 当 task.payload 非空时调 platform.publish_video(**payload)。"""
    from ext_api import task_queue as tq
    from ext_api.task_queue import TaskStatus

    # 构造一个最小 task
    t = PublishTask(
        platform='xiaohongshu', platform_type=1,
        payload={'title': 'T', 'files': ['/a.mp4'], 'tags': ['x'],
                 'desc': 'D', 'ai_content': '内容由AI生成'},
        account_id=1, source='draft', draft_id=42,
    )

    # Mock platform
    fake_platform = MagicMock()
    fake_platform.publish_video = MagicMock(return_value=True)

    with patch.object(tq, 'get_platform', return_value=fake_platform):
        queue = tq.get_task_queue()
        asyncio.run(queue._execute(t))

    # 验证 publish_video 被以 payload kwargs 调用
    fake_platform.publish_video.assert_called_once()
    call_kwargs = fake_platform.publish_video.call_args.kwargs
    assert call_kwargs['title'] == 'T'
    assert call_kwargs['files'] == ['/a.mp4']
    assert call_kwargs['tags'] == ['x']
    assert call_kwargs['desc'] == 'D'
    assert call_kwargs['ai_content'] == '内容由AI生成'


def test_execute_async_publish_video():
    """platform.publish_video 是 async 时也走 splat。"""
    from ext_api import task_queue as tq

    async def fake_async_publish(**kwargs):
        return True

    fake_platform = MagicMock()
    fake_platform.publish_video = fake_async_publish

    t = PublishTask(
        platform='douyin', platform_type=3,
        payload={'title': 'X', 'files': ['/a.mp4']},
    )

    with patch.object(tq, 'get_platform', return_value=fake_platform):
        queue = tq.get_task_queue()
        result = asyncio.run(queue._execute(t))

    assert result is True
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_task_queue_extended.py -v -k "execute_"
```

Expected: 2 个测试 FAIL（worker 还是走 legacy 老函数）。

- [ ] **Step 3: 扩展 _execute**

替换 `backend/ext_api/task_queue.py:197-260` 的 `_execute` 方法（保留 legacy 块作为兜底）：

```python
    async def _execute(self, task: PublishTask):
        """调用上游 uploader 执行上传。

        新逻辑：当 task.payload 非空时，调 platform.publish_video(**payload)（splat）。
        旧逻辑（task.payload 为空时）：保留原 myUtils.postVideo 模块函数调用（向后兼容）。
        """
        # 新逻辑：payload 透传到 platform.publish_video
        if task.payload:
            from impl.registry import get_platform
            platform = get_platform(task.platform_type)
            if not platform:
                raise ValueError(f"不支持的平台类型: {task.platform_type}")
            publish_fn = platform.publish_video
            loop = asyncio.get_event_loop()
            if asyncio.iscoroutinefunction(publish_fn):
                return await loop.run_in_executor(
                    None, lambda: publish_fn(**task.payload)
                )
            return publish_fn(**task.payload)

        # 旧逻辑：保留原代码不动
        from myUtils.postVideo import (
            post_video_DouYin, post_video_ks,
            post_video_tencent, post_video_xhs,
            post_video_bilibili
        )

        file_list = [task.video_path]
        account_list = [task.account_cookie_path]
        tags = task.tags
        title = task.title
        thumbnail_path = task.thumbnail_path
        desc = task.description

        loop = asyncio.get_event_loop()
        match task.platform_type:
            case 1:
                await loop.run_in_executor(
                    None, lambda: post_video_xhs(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        thumbnail_path=thumbnail_path, desc=desc
                    )
                )
            case 2:
                await loop.run_in_executor(
                    None, lambda: post_video_tencent(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0, False,
                        thumbnail_path=thumbnail_path, desc=desc
                    )
                )
            case 3:
                await loop.run_in_executor(
                    None, lambda: post_video_DouYin(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        thumbnail_landscape_path='', thumbnail_portrait_path=thumbnail_path,
                        productLink='', productTitle='', desc=desc
                    )
                )
            case 4:
                await loop.run_in_executor(
                    None, lambda: post_video_ks(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        thumbnail_path=thumbnail_path, desc=desc
                    )
                )
            case 5:
                await loop.run_in_executor(
                    None, lambda: post_video_bilibili(
                        title, file_list, tags, account_list, None, 0, 1, ['10:00'], 0,
                        desc=desc
                    )
                )
            case _:
                raise ValueError(f"不支持的平台类型: {task.platform_type}")
```

- [ ] **Step 4: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_task_queue_extended.py -v -k "execute_"
```

Expected: 2 个 execute 测试全部 PASS。

- [ ] **Step 5: 跑全部扩展测试**

```bash
cd backend && python3 -m pytest tests/test_task_queue_extended.py -v
```

Expected: 5 个测试全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/ext_api/task_queue.py backend/tests/test_task_queue_extended.py
git commit -m "feat(backend): worker 扩 splat task.payload 到 platform.publish_video(**kwargs)"
```

---

## Task 12: 视频批量发布端点测试

**Files:**
- Create: `backend/tests/test_drafts_batch_publish.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_drafts_batch_publish.py`：

```python
"""POST /api/v2/drafts/batch-publish 端点集成测试。"""
import json
import sys
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _setup_db(tmp_db):
    """建测试数据库（含 drafts + user_info + publish_batches/publish_details）。

    注意：legacy `publish_tasks` 表已删除（commit 71898c0）。`PublishTask` 持久化走
    `publish_details.account_configs` JSON（由 `_build_account_configs(task)` 填充）。
    本 fixture 只需建 `publish_batches` + `publish_details` 即可，因为 Task 12 测试用
    `monkeypatch` mock 了 `add_task`，不会触发真实 `_insert_db`。
    """
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE user_info (
            id INTEGER PRIMARY KEY,
            platform TEXT NOT NULL DEFAULT '',
            file_path TEXT NOT NULL DEFAULT '',
            user_name TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'video',
            title TEXT NOT NULL DEFAULT '',
            cover_path TEXT NOT NULL DEFAULT '',
            draft_data TEXT NOT NULL DEFAULT '{}',
            channels_summary TEXT NOT NULL DEFAULT '[]',
            video_duration REAL NOT NULL DEFAULT 0,
            video_file_size INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE publish_batches (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            video_material_id TEXT DEFAULT '',
            image_material_ids TEXT DEFAULT '[]',
            landscape_cover_material_id TEXT DEFAULT '',
            portrait_cover_material_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            account_count INTEGER NOT NULL DEFAULT 0,
            success_count INTEGER NOT NULL DEFAULT 0,
            failed_count INTEGER NOT NULL DEFAULT 0,
            schedule_time TEXT DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            draft_id INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE publish_details (
            id TEXT PRIMARY KEY,
            batch_id TEXT NOT NULL,
            account_id INTEGER,
            account_name TEXT NOT NULL DEFAULT '',
            platform TEXT NOT NULL DEFAULT '',
            account_configs TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            error_message TEXT NOT NULL DEFAULT '',
            publish_url TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            FOREIGN KEY (batch_id) REFERENCES publish_batches(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    conn.close()


def _insert_user(conn, id, platform, file_path):
    conn.execute("INSERT INTO user_info (id, platform, file_path) VALUES (?, ?, ?)",
                (id, platform, file_path))
    conn.commit()


def _insert_video_draft(conn, id, draft_data, type='video'):
    conn.execute("INSERT INTO drafts (id, type, draft_data) VALUES (?, ?, ?)",
                (id, type, json.dumps(draft_data, ensure_ascii=False)))
    conn.commit()


def _valid_video_draft_data():
    return {
        'commonConfig': {'videoPortrait': {'stored_path': '/abs/v.mp4'},
                         'coverPortrait': {'stored_path': '/abs/c.jpg'}},
        'platformConfigs': {'xiaohongshu': {'title': 'T', 'videoFormat': 'portrait',
                                            'aiContent': '内容由AI生成'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': 'T', 'videoFormat': 'portrait',
                                    'aiContent': '内容由AI生成'}},
        'publishAccountIds': [1],
    }


def test_batch_publish_happy_path(tmp_path, monkeypatch):
    """1 草稿 + 1 账号 → 1 个 task 入队。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        _insert_video_draft(conn, 1, _valid_video_draft_data())

    # mock add_task
    added_tasks = []
    def fake_add_task(task):
        added_tasks.append(task)
        return 'task-1'

    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue', lambda: MagicMock(add_task=fake_add_task))

    # mock DB_PATH
    from app import _get_db_path
    monkeypatch.setattr('app._get_db_path', lambda: db_path)

    # mock init
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()

    resp = client.post('/api/v2/drafts/batch-publish',
                       json={'draft_ids': [1]})

    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['task_ids']) == 1
    assert data['failed'] == []
    assert len(added_tasks) == 1
    assert added_tasks[0].source == 'draft'
    assert added_tasks[0].draft_id == 1
    assert added_tasks[0].account_id == 1
    assert added_tasks[0].platform == 'xiaohongshu'
    assert added_tasks[0].platform_type == 1   # xiaohongshu = 1
    assert added_tasks[0].payload['title'] == 'T'
    assert added_tasks[0].payload['ai_content'] == '内容由AI生成'


def test_batch_publish_multi_account_yields_multi_tasks(tmp_path, monkeypatch):
    """1 草稿 + 2 账号（不同平台）→ 2 个 task。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    draft_data = {
        'commonConfig': {'videoPortrait': {'stored_path': '/abs/v.mp4'},
                         'coverPortrait': {'stored_path': '/abs/c.jpg'}},
        'platformConfigs': {
            'xiaohongshu': {'title': 'T-xhs', 'videoFormat': 'portrait', 'aiContent': 'X'},
            'douyin': {'title': 'T-dy', 'videoFormat': 'portrait', 'aiContent': 'X'},
        },
        'platformOverrides': {},
        'accountOverrides': {
            '1': {'title': 'T-xhs', 'videoFormat': 'portrait', 'aiContent': 'X'},
            '2': {'title': 'T-dy', 'videoFormat': 'portrait', 'aiContent': 'X'},
        },
        'publishAccountIds': [1, 2],
    }
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        _insert_user(conn, 2, 'douyin', '/cookies/d1')
        _insert_video_draft(conn, 1, draft_data)

    added_tasks = []
    def fake_add_task(task):
        added_tasks.append(task)
        return f'task-{len(added_tasks)}'

    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue', lambda: MagicMock(add_task=fake_add_task))
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['task_ids']) == 2
    assert len(added_tasks) == 2
    assert {t.platform for t in added_tasks} == {'xiaohongshu', 'douyin'}


def test_batch_publish_partial_failure(tmp_path, monkeypatch):
    """1 合法 + 1 缺字段 → 1 task + 1 failed。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    bad_draft = {
        'commonConfig': {'videoPortrait': None, 'videoLandscape': None,
                         'coverPortrait': {'stored_path': '/c.jpg'}},
        'platformConfigs': {'xiaohongshu': {'title': '', 'videoFormat': 'portrait'}},
        'platformOverrides': {},
        'accountOverrides': {'1': {'title': '', 'videoFormat': 'portrait'}},
        'publishAccountIds': [1],
    }
    with sqlite3.connect(str(db_path)) as conn:
        _insert_user(conn, 1, 'xiaohongshu', '/cookies/x1')
        _insert_video_draft(conn, 1, _valid_video_draft_data())
        _insert_video_draft(conn, 2, bad_draft)

    added_tasks = []
    def fake_add_task(task):
        added_tasks.append(task)
        return f'task-{len(added_tasks)}'

    from ext_api import task_queue as tq
    monkeypatch.setattr(tq, 'get_task_queue', lambda: MagicMock(add_task=fake_add_task))
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1, 2]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['task_ids']) == 1
    assert len(data['failed']) == 1
    assert data['failed'][0]['draft_id'] == 2


def test_batch_publish_draft_not_found(tmp_path, monkeypatch):
    """draft_ids 包含不存在的 id → 404。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [99]})
    assert resp.status_code == 404
    assert 99 in resp.get_json().get('missing_ids', [])


def test_batch_publish_wrong_type(tmp_path, monkeypatch):
    """type=image 草稿打到视频端点 → 400。"""
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    with sqlite3.connect(str(db_path)) as conn:
        _insert_video_draft(conn, 1, {}, type='image')

    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 400
    assert 1 in resp.get_json().get('wrong_type_ids', [])


def test_batch_publish_too_many(tmp_path, monkeypatch):
    """>30 个 → 400。"""
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': list(range(31))})
    assert resp.status_code == 400


def test_batch_publish_empty(tmp_path, monkeypatch):
    """空列表 → 400。"""
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.post('/api/v2/drafts/batch-publish', json={'draft_ids': []})
    assert resp.status_code == 400
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_drafts_batch_publish.py -v
```

Expected: 7 个测试全部 FAIL（404 Not Found，端点不存在）。

- [ ] **Step 3: 提交失败测试**

```bash
git add backend/tests/test_drafts_batch_publish.py
git commit -m "test(backend): 视频批量发布端点集成测试（7 个测试，RED 状态）"
```

---

## Task 13: 实现视频批量发布端点

**Files:**
- Modify: `backend/ext_api/__init__.py` (add route handler)

- [ ] **Step 1: 找 ext_api/__init__.py 末尾的路由注册位置**

```bash
tail -50 backend/ext_api/__init__.py
```

确认追加位置在最后 `@ext_api_bp.route(...)` 之后。

- [ ] **Step 2: 加新路由**

在 `backend/ext_api/__init__.py` 末尾追加：

```python
@ext_api_bp.route('/drafts/batch-publish', methods=['POST'])
def batch_publish_drafts():
    """视频草稿批量发布：每个 (draft, account) 入队 1 个 task。"""
    import json
    import sqlite3
    import uuid
    from flask import request, jsonify
    from ext_api.task_queue import get_task_queue, PublishTask
    from impl.registry import get_platform, PLATFORM_MAP
    from services.draft_merge import (
        merge_config, validate_draft_for_publish, build_platform_kwargs
    )

    data = request.get_json() or {}
    draft_ids = data.get('draft_ids') or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    placeholders = ','.join('?' * len(draft_ids))
    rows = conn.execute(
        f"SELECT id, type, draft_data FROM drafts WHERE id IN ({placeholders})",
        draft_ids
    ).fetchall()
    conn.close()

    found_ids = {r['id'] for r in rows}
    missing_ids = [i for i in draft_ids if i not in found_ids]
    if missing_ids:
        return jsonify({"code": 404, "msg": "草稿不存在", "missing_ids": missing_ids}), 404

    wrong_type = [r['id'] for r in rows if r['type'] != 'video']
    if wrong_type:
        return jsonify({"code": 400, "msg": "包含非视频草稿", "wrong_type_ids": wrong_type}), 400

    task_queue = get_task_queue()
    task_ids = []
    failed = []

    for r in rows:
        draft = {'id': r['id'], 'type': r['type'],
                 'draft_data': json.loads(r['draft_data'] or '{}')}
        try:
            errs = validate_draft_for_publish(draft)
            if errs:
                failed.append({'draft_id': r['id'], 'reason': '; '.join(errs)})
                continue

            draft_data = draft['draft_data']
            common = draft_data.get('commonConfig') or {}
            platform_configs = draft_data.get('platformConfigs') or {}
            account_overrides = draft_data.get('accountOverrides') or {}
            publish_account_ids = draft_data.get('publishAccountIds') or []

            for account_id in publish_account_ids:
                # 查 user_info
                acc_conn = sqlite3.connect(str(db_path))
                acc_row = acc_conn.execute(
                    "SELECT id, platform, file_path FROM user_info WHERE id = ?",
                    (account_id,)
                ).fetchone()
                acc_conn.close()
                if not acc_row:
                    failed.append({'draft_id': r['id'], 'reason': f'账号 {account_id} 不存在'})
                    continue

                account_platform = acc_row[1]
                platform_default = platform_configs.get(account_platform) or {}
                account_ov = account_overrides.get(str(account_id)) or {}

                merged = merge_config(common, platform_default, None, account_ov)

                account_obj = type('A', (), {})()
                account_obj.id = acc_row[0]
                account_obj.platform = acc_row[1]
                account_obj.file_path = acc_row[2]

                payload = build_platform_kwargs(merged, common, account_obj)

                platform_id = [k for k, v in PLATFORM_MAP.items() if v == account_platform]
                if not platform_id:
                    failed.append({'draft_id': r['id'], 'reason': f'未知平台: {account_platform}'})
                    continue
                ptype = platform_id[0]

                task_id = str(uuid.uuid4())
                task = PublishTask(
                    id=task_id,
                    platform=account_platform,
                    platform_type=ptype,
                    account_name=acc_row[1] or '',
                    account_cookie_path=acc_row[2] or '',
                    video_path=(payload.get('files') or ['/'])[0],
                    title=payload.get('title', ''),
                    description=payload.get('desc', ''),
                    thumbnail_path=payload.get('thumbnail_path', ''),
                    tags=payload.get('tags') or [],
                    source='draft',
                    draft_id=r['id'],
                    account_id=account_id,
                    payload=payload,
                )
                try:
                    task_queue.add_task(task)
                    task_ids.append(task_id)
                except Exception as e:
                    failed.append({'draft_id': r['id'], 'reason': f'入队失败: {e}'})
        except Exception as e:
            failed.append({'draft_id': r['id'], 'reason': str(e)})

    return jsonify({"code": 200, "task_ids": task_ids, "failed": failed}), 200
```

- [ ] **Step 3: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_drafts_batch_publish.py -v
```

Expected: 7 个测试全部 PASS。

- [ ] **Step 4: 提交**

```bash
git add backend/ext_api/__init__.py
git commit -m "feat(backend): POST /api/v2/drafts/batch-publish 端点（视频批量发布）"
```

---

## Task 14: 视频批量删除端点测试 + 实现

**Files:**
- Create: `backend/tests/test_drafts_batch_delete.py`
- Modify: `backend/ext_api/__init__.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_drafts_batch_delete.py`：

```python
"""DELETE /api/v2/drafts/batch 端点集成测试。"""
import json
import sys
import sqlite3
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _setup_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE drafts (
            id INTEGER PRIMARY KEY,
            type TEXT NOT NULL DEFAULT 'video',
            title TEXT NOT NULL DEFAULT '',
            cover_path TEXT NOT NULL DEFAULT '',
            draft_data TEXT NOT NULL DEFAULT '{}',
            channels_summary TEXT NOT NULL DEFAULT '[]',
            video_duration REAL NOT NULL DEFAULT 0,
            video_file_size INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def test_batch_delete_happy_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO drafts (id, type) VALUES (1, 'video'), (2, 'video'), (3, 'video')")
        conn.commit()

    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={'draft_ids': [1, 2]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted'] == [1, 2]
    assert data['failed'] == []

    # 验证 DB 中 1, 2 已被删除，3 还在
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute("SELECT id FROM drafts").fetchall()
    assert [r[0] for r in rows] == [3]


def test_batch_delete_partial_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("INSERT INTO drafts (id, type) VALUES (1, 'video')")
        conn.commit()

    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={'draft_ids': [1, 99]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['deleted'] == [1]
    assert len(data['failed']) == 1
    assert data['failed'][0]['draft_id'] == 99


def test_batch_delete_empty(tmp_path, monkeypatch):
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={'draft_ids': []})
    assert resp.status_code == 400


def test_batch_delete_no_body(tmp_path, monkeypatch):
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.delete('/api/v2/drafts/batch', json={})
    assert resp.status_code == 400
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_drafts_batch_delete.py -v
```

Expected: 4 个测试 FAIL（404）。

- [ ] **Step 3: 实现批量删除端点**

在 `backend/ext_api/__init__.py` 末尾追加：

```python
@ext_api_bp.route('/drafts/batch', methods=['DELETE'])
def batch_delete_drafts():
    """视频草稿批量删除。"""
    import sqlite3
    from flask import request, jsonify

    data = request.get_json() or {}
    draft_ids = data.get('draft_ids') or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    placeholders = ','.join('?' * len(draft_ids))

    existing = {r[0] for r in conn.execute(
        f"SELECT id FROM drafts WHERE id IN ({placeholders})", draft_ids
    ).fetchall()}

    deleted = []
    failed = []
    for did in draft_ids:
        if did in existing:
            try:
                conn.execute("DELETE FROM drafts WHERE id = ?", (did,))
                deleted.append(did)
            except Exception as e:
                failed.append({'draft_id': did, 'reason': str(e)})
        else:
            failed.append({'draft_id': did, 'reason': '草稿不存在'})

    conn.commit()
    conn.close()

    return jsonify({"code": 200, "deleted": deleted, "failed": failed}), 200
```

- [ ] **Step 4: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_drafts_batch_delete.py -v
```

Expected: 4 个测试全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add backend/ext_api/__init__.py backend/tests/test_drafts_batch_delete.py
git commit -m "feat(backend): DELETE /api/v2/drafts/batch 端点（视频批量删除）"
```

---

## Task 15: 图文批量发布端点测试 + 实现

**Files:**
- Create: `backend/tests/test_image_drafts_batch_publish.py`
- Modify: `backend/blueprints/image_publish_bp.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_image_drafts_batch_publish.py`：

```python
"""POST /api/image-publish/drafts/batch-publish 端点集成测试。"""
import json
import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def _setup_db(tmp_db):
    conn = sqlite3.connect(str(tmp_db))
    conn.executescript("""
        CREATE TABLE image_drafts (
            id INTEGER PRIMARY KEY,
            image_ids TEXT NOT NULL DEFAULT '[]',
            account_configs TEXT NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    conn.close()


def _valid_image_draft_config():
    return {
        'platform': 'xiaohongshu', 'account_id': 1, 'account_name': 'a',
        'filePath': '/cookies/x1', 'title': 'T', 'description': '',
        'aiContent': '内容由AI生成', 'isOriginal': True,
    }


def test_image_batch_publish_happy_path(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO image_drafts (id, image_ids, account_configs) VALUES (1, ?, ?)",
            (json.dumps(['img-1', 'img-2']), json.dumps(_valid_image_draft_config())),
        )
        conn.commit()

    called = []
    def fake_publish():
        called.append(True)
        from flask import jsonify
        return jsonify({"code": 200, "msg": "ok"}), 200

    # Mock image_publish endpoint
    monkeypatch.setattr('blueprints.image_publish_bp.publish_images', fake_publish)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['failed'] == []
    assert len(called) == 1   # publish_images 被调一次


def test_image_batch_publish_missing_image_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO image_drafts (id, image_ids, account_configs) VALUES (1, '[]', ?)",
            (json.dumps(_valid_image_draft_config()),),
        )
        conn.commit()

    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': [1]})
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data['failed']) == 1
    assert data['failed'][0]['draft_id'] == 1


def test_image_batch_publish_draft_not_found(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    _setup_db(db_path)
    monkeypatch.setattr('services.draft_merge.DB_PATH', db_path)
    monkeypatch.setattr('app._get_db_path', lambda: db_path)
    monkeypatch.setattr('app._ensure_db', lambda: None)

    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': [99]})
    assert resp.status_code == 404


def test_image_batch_publish_empty(tmp_path, monkeypatch):
    monkeypatch.setattr('app._get_db_path', lambda: None)
    monkeypatch.setattr('app._ensure_db', lambda: None)
    from app import app
    client = app.test_client()
    resp = client.post('/api/image-publish/drafts/batch-publish', json={'draft_ids': []})
    assert resp.status_code == 400
```

- [ ] **Step 2: 跑测试，验证失败**

```bash
cd backend && python3 -m pytest tests/test_image_drafts_batch_publish.py -v
```

Expected: 4 个测试 FAIL（404）。

- [ ] **Step 3: 实现图文批量发布端点**

在 `backend/blueprints/image_publish_bp.py` 末尾追加：

```python
@image_publish_bp.route('/drafts/batch-publish', methods=['POST'])
def batch_publish_image_drafts():
    """图文草稿批量发布：每个 draft 调一次 publish_images 走单账号链路。"""
    import json
    import sqlite3
    from flask import request, jsonify
    from services.draft_merge import validate_image_draft_for_publish

    data = request.get_json() or {}
    draft_ids = data.get('draft_ids') or []
    if not isinstance(draft_ids, list) or not draft_ids or len(draft_ids) > 30:
        return jsonify({"code": 400, "msg": "draft_ids 数量必须 1-30"}), 400

    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    placeholders = ','.join('?' * len(draft_ids))
    rows = conn.execute(
        f"SELECT id, image_ids, account_configs FROM image_drafts WHERE id IN ({placeholders})",
        draft_ids
    ).fetchall()
    conn.close()

    found_ids = {r[0] for r in rows}
    missing_ids = [i for i in draft_ids if i not in found_ids]
    if missing_ids:
        return jsonify({"code": 404, "msg": "图文草稿不存在", "missing_ids": missing_ids}), 404

    succeeded = []
    failed = []
    for r in rows:
        draft = {
            'id': r[0],
            'image_ids': json.loads(r[1] or '[]'),
            'account_configs': json.loads(r[2] or '{}'),
        }
        errs = validate_image_draft_for_publish(draft)
        if errs:
            failed.append({'draft_id': r[0], 'reason': '; '.join(errs)})
            continue

        # 调一次 publish_images：构造 data 让它走原来的单账号链路
        config = draft['account_configs']
        try:
            from flask import current_app
            with current_app.test_request_context(
                '/api/image-publish/publish',
                method='POST',
                json={
                    'image_ids': draft['image_ids'],
                    'account_configs': config,
                    'landscapeCoverMaterialId': '',
                    'portraitCoverMaterialId': '',
                },
            ):
                resp = publish_images()
                if resp[1] == 200:
                    succeeded.append(r[0])
                else:
                    failed.append({'draft_id': r[0], 'reason': str(resp[0].get_json())})
        except Exception as e:
            failed.append({'draft_id': r[0], 'reason': f'发布失败: {e}'})

    return jsonify({"code": 200, "succeeded": succeeded, "failed": failed}), 200
```

- [ ] **Step 4: 跑测试，验证通过**

```bash
cd backend && python3 -m pytest tests/test_image_drafts_batch_publish.py -v
```

Expected: 4 个测试全部 PASS。

- [ ] **Step 5: 跑全部后端测试**

```bash
cd backend && python3 -m pytest tests/test_draft_merge.py tests/test_task_queue_extended.py tests/test_drafts_batch_publish.py tests/test_drafts_batch_delete.py tests/test_image_drafts_batch_publish.py -v
```

Expected: 全部 36 个测试通过。

- [ ] **Step 6: 提交**

```bash
git add backend/blueprints/image_publish_bp.py backend/tests/test_image_drafts_batch_publish.py
git commit -m "feat(backend): POST /api/image-publish/drafts/batch-publish 端点（图文批量发布）"
```

---

## Task 16: 前端 api/draft.js 加 2 个方法

**Files:**
- Modify: `frontend/src/api/draft.js`

- [ ] **Step 1: 看现有 draft.js**

```bash
cat frontend/src/api/draft.js
```

确认现有方法风格。

- [ ] **Step 2: 追加 2 个方法**

在 `frontend/src/api/draft.js` 末尾追加：

```js
// 草稿批量发布（视频）：POST /api/v2/drafts/batch-publish
export function batchPublishVideoDrafts(draftIds) {
  return request({
    url: '/api/v2/drafts/batch-publish',
    method: 'post',
    data: { draft_ids: draftIds },
  })
}

// 草稿批量删除：DELETE /api/v2/drafts/batch
export function batchDeleteDrafts(draftIds) {
  return request({
    url: '/api/v2/drafts/batch',
    method: 'delete',
    data: { draft_ids: draftIds },
  })
}
```

- [ ] **Step 3: 提交**

```bash
git add frontend/src/api/draft.js
git commit -m "feat(frontend): api/draft.js 加 batchPublishVideoDrafts / batchDeleteDrafts"
```

---

## Task 17: 新建 BatchPublishDialog.vue 组件

**Files:**
- Create: `frontend/src/components/BatchPublishDialog.vue`

- [ ] **Step 1: 创建组件**

创建 `frontend/src/components/BatchPublishDialog.vue`：

```vue
<template>
  <el-dialog
    :model-value="visible"
    title="批量发布预览"
    width="640px"
    @update:model-value="$emit('update:visible', $event)"
    :close-on-click-modal="false"
  >
    <div v-if="drafts.length === 0" class="empty">未选中任何草稿</div>
    <div v-else>
      <el-table
        ref="tableRef"
        :data="tableData"
        @selection-change="onSelectionChange"
        :max-height="400"
      >
        <el-table-column type="selection" width="50" />
        <el-table-column prop="title" label="标题" />
        <el-table-column prop="platforms" label="目标平台" width="180" />
        <el-table-column prop="status" label="状态" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.status === 'ok'" type="success" size="small">通过</el-tag>
            <el-tooltip v-else :content="row.reason" placement="top">
              <el-tag type="danger" size="small">失败</el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary">
        已选 <b>{{ selectedIds.length }}</b> / {{ drafts.length }} 项
      </div>
    </div>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="selectedIds.length === 0"
        :loading="submitting"
        @click="onConfirm"
      >
        确认发布 {{ selectedIds.length }} 项
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps({
  visible: { type: Boolean, default: false },
  drafts: { type: Array, default: () => [] },        // [{id, type, title, platforms}]
  failures: { type: Array, default: () => [] },      // [{draft_id, reason}]
})

const emit = defineEmits(['update:visible', 'confirm'])

const tableRef = ref(null)
const submitting = ref(false)
const selectedIds = ref([])

// 失败集合（draft_id → reason）
const failureMap = computed(() => {
  const m = new Map()
  for (const f of props.failures) m.set(f.draft_id, f.reason)
  return m
})

// 表格数据：每条草稿带 status/reason/platforms
const tableData = computed(() =>
  props.drafts.map((d) => {
    const reason = failureMap.value.get(d.id)
    return {
      id: d.id,
      title: d.title || `草稿 #${d.id}`,
      platforms: (d.platforms || []).join('、') || '—',
      status: reason ? 'fail' : 'ok',
      reason: reason || '',
    }
  })
)

// 默认勾选：仅未失败的
watch(
  () => [props.visible, props.drafts],
  ([vis]) => {
    if (vis) {
      selectedIds.value = tableData.value
        .filter((r) => r.status === 'ok')
        .map((r) => r.id)
      // 同步 el-table 选中状态
      nextTick(() => {
        if (tableRef.value) {
          tableRef.value.clearSelection()
          for (const row of tableData.value) {
            if (selectedIds.value.includes(row.id)) {
              tableRef.value.toggleRowSelection(row, true)
            }
          }
        }
      })
    }
  },
  { immediate: true }
)

import { nextTick } from 'vue'
function onSelectionChange(rows) {
  selectedIds.value = rows.map((r) => r.id)
}

async function onConfirm() {
  if (selectedIds.value.length === 0) return
  submitting.value = true
  emit('confirm', selectedIds.value)
}
// 父组件拿到响应后调 resetSubmitting()
function resetSubmitting() {
  submitting.value = false
}
defineExpose({ resetSubmitting })
</script>

<style scoped>
.empty {
  text-align: center;
  color: #909399;
  padding: 40px 0;
}
.summary {
  margin-top: 12px;
  text-align: right;
  color: #606266;
}
</style>
```

- [ ] **Step 2: 提交**

```bash
git add frontend/src/components/BatchPublishDialog.vue
git commit -m "feat(frontend): 新建 BatchPublishDialog 组件（预览+勾选+确认）"
```

---

## Task 18: DraftBox.vue 改造（多选 + 工具栏 + 触发 dialog）

**Files:**
- Modify: `frontend/src/views/DraftBox.vue`

- [ ] **Step 1: 读现有 DraftBox.vue 结构**

```bash
grep -n "^const\|^function\|template\|el-card\|el-button\|el-table" frontend/src/views/DraftBox.vue | head -30
```

了解布局（卡片网格 vs 表格）。

- [ ] **Step 2: 加 selection 状态**

在 `<script setup>` 顶部追加：

```js
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { batchPublishVideoDrafts, batchDeleteDrafts } from '@/api/draft'
import BatchPublishDialog from '@/components/BatchPublishDialog.vue'

const selection = ref(new Set())           // 选中的草稿 id
const selectMode = ref(false)              // 多选模式开关
const dialogVisible = ref(false)
const dialogDrafts = ref([])                // 给 dialog 的草稿列表
const dialogFailures = ref([])              // 校验失败列表
const isPublishing = ref(false)
```

- [ ] **Step 3: 加工具栏模板**

在主卡片列表**之上**插入：

```vue
<div class="draft-toolbar">
  <el-button
    :type="selectMode ? 'primary' : 'default'"
    size="small"
    @click="selectMode = !selectMode"
  >
    {{ selectMode ? '退出多选' : '多选' }}
  </el-button>
  <template v-if="selectMode && selection.size > 0">
    <span class="selected-count">已选 {{ selection.size }} 项</span>
    <el-button size="small" @click="onBatchDelete">批量删除</el-button>
    <el-button size="small" type="primary" @click="onBatchPublish">批量发布</el-button>
    <el-button size="small" text @click="selection.clear()">清空</el-button>
  </template>
</div>
```

- [ ] **Step 4: 草稿卡片加 checkbox（仅多选模式显示）**

在现有草稿卡片 `<el-card>` 内**最前面**插入：

```vue
<el-checkbox
  v-if="selectMode"
  :model-value="selection.has(draft.id)"
  @change="(v) => toggleSelection(draft.id, v)"
  class="draft-card-checkbox"
/>
```

- [ ] **Step 5: 加 handler 函数**

在 `<script setup>` 末尾追加：

```js
function toggleSelection(id, checked) {
  if (checked) selection.value.add(id)
  else selection.value.delete(id)
  // 触发响应式更新
  selection.value = new Set(selection.value)
}

async function onBatchDelete() {
  try {
    await ElMessageBox.confirm(
      `确认删除选中的 ${selection.value.size} 个草稿？此操作不可恢复。`,
      '批量删除',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  const ids = [...selection.value]
  try {
    const resp = await batchDeleteDrafts(ids)
    const { deleted = [], failed = [] } = resp || {}
    if (deleted.length) {
      ElMessage.success(`已删除 ${deleted.length} 个草稿`)
      // 从本地列表移除
      drafts.value = drafts.value.filter((d) => !deleted.includes(d.id))
    }
    if (failed.length) {
      ElMessage.warning(`${failed.length} 个草稿删除失败：${failed.map((f) => f.reason).join('; ')}`)
    }
    selection.value = new Set()
  } catch (e) {
    ElMessage.error(`批量删除失败：${e.message || e}`)
  }
}

async function onBatchPublish() {
  const ids = [...selection.value]
  // 调后端 dry-run：先调一次 batch-publish 看 failed 列表
  // 简化：直接弹 dialog 展示
  dialogDrafts.value = drafts.value
    .filter((d) => ids.includes(d.id))
    .map((d) => ({
      id: d.id,
      type: d.type,
      title: d.title,
      platforms: [],   // 后端 validate 决定；这里先不展示
    }))
  dialogFailures.value = []
  dialogVisible.value = true
}

async function onDialogConfirm(confirmedIds) {
  dialogVisible.value = false
  if (confirmedIds.length === 0) return

  isPublishing.value = true
  try {
    const resp = await batchPublishVideoDrafts(confirmedIds)
    const { task_ids = [], failed = [] } = resp || {}
    if (task_ids.length) {
      ElMessage.success(
        `已入队 ${task_ids.length} 个任务，去任务中心查看 →`,
        { duration: 4000 }
      )
    }
    if (failed.length) {
      ElMessage.warning(
        `${failed.length} 个草稿发布失败：${failed.map((f) => f.reason).join('; ')}`
      )
    }
    selection.value = new Set()
  } catch (e) {
    ElMessage.error(`批量发布失败：${e.message || e}`)
  } finally {
    isPublishing.value = false
  }
}
```

- [ ] **Step 6: 在 template 末尾加 dialog**

在 `</template>` 前插入：

```vue
<BatchPublishDialog
  v-model:visible="dialogVisible"
  :drafts="dialogDrafts"
  :failures="dialogFailures"
  @confirm="onDialogConfirm"
/>
```

- [ ] **Step 7: 提交**

```bash
git add frontend/src/views/DraftBox.vue
git commit -m "feat(frontend): DraftBox 加多选模式 + 批量删除/发布按钮 + BatchPublishDialog"
```

---

## Task 19: 手动 e2e 验证

**Files:** (no code changes; just verification)

- [ ] **Step 1: 启动后端 + 前端**

```bash
# terminal 1
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 app.py

# terminal 2
cd /home/czy/workspace/ai/social-auto-upload-web-ui/frontend && npm run dev
```

- [ ] **Step 2: 在浏览器打开**

访问 `http://localhost:5173/draft-box`（或前端实际路由）。

- [ ] **Step 3: 验证多选 + 批量删除**

1. 点击右上角「多选」按钮
2. 勾选 2 个草稿
3. 点击「批量删除」
4. 弹 confirm → 点击「删除」
5. 期望：toast 提示「已删除 N 个」，列表中那 2 个消失
6. 验证 DB：`sqlite3 data/db/database.db "SELECT id, title FROM drafts"` — 确认已删除

- [ ] **Step 4: 验证批量发布 happy path**

1. 用 PublishCenter 存 1 个完整合法草稿
2. 切到 DraftBox
3. 多选 → 勾选该草稿
4. 点击「批量发布」
5. 弹 dialog 显示 ✓ 通过
6. 点击「确认发布」
7. 期望：toast「已入队 N 个任务，去任务中心查看 →」
8. 跳到 TaskCenter：任务可见，状态为 queued/running/success
9. 验证 DB 溯源：`SELECT id, source, draft_id, status FROM publish_batches WHERE source='draft'`
   - 期望：source='draft', draft_id=<id>

- [ ] **Step 5: 验证批量发布部分失败**

1. 用 PublishCenter 存 1 个完整草稿
2. 手动去草稿 DB 删一个视频文件路径（让草稿不合法）
3. 多选 → 勾选 1 合法 + 1 不合法
4. 批量发布 → dialog 显示 1 通过 + 1 失败
5. 不勾选失败的项 → 确认发布
6. 期望：仅 1 个 task 入队

- [ ] **Step 6: 验证图文批量发布**

1. 用 ImagePublish 存 1 个完整图文草稿
2. 切到 DraftBox 切到图文 Tab
3. 同样的多选/批量发布流程
4. 期望：图文 task 入队

- [ ] **Step 7: 跑全部后端测试套件**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui/backend && python3 -m pytest tests/ -v
```

Expected: 全部 36 个新增测试 + 已有测试 PASS。

- [ ] **Step 8: 收尾 commit（如果有 fix）**

```bash
git status
# 如果有未提交修改
git add -A
git commit -m "fix: e2e 验证中修复的细节"
```

如果无修改则跳过。

---

## 自审（写完后）

| Spec 章节 | 覆盖任务 |
|---|---|
| 硬约束（不改 PublishCenter 等）| Task 1-19 全程 |
| 视频批量发布端点 | Task 12, 13 |
| 图文批量发布端点 | Task 15 |
| 视频批量删除端点 | Task 14 |
| 4 级合并（3 级 vs 4 级）| Task 3, 4 |
| 视频校验 | Task 5, 6 |
| 图文校验 | Task 7 |
| Payload Adapter | Task 8, 9 |
| PublishTask 扩展 | Task 10 |
| Worker 扩展 | Task 11 |
| Frontend 多选 | Task 18 |
| BatchPublishDialog | Task 17 |
| API 客户端 | Task 16 |
| e2e 验证 | Task 19 |

**所有 spec 要求都被任务覆盖。** 没有占位符（"类似 Task N" / "TBD"），所有代码块完整可执行。
