# Draft Batch Operations Design

## Context

`DraftBox.vue` currently supports per-row "Edit" (jumps to PublishCenter or ImagePublish) and "Delete" (single draft). The publish flow always goes: click "Edit" → publish page → click "Publish". With ~30+ drafts in the box, the operator needs to publish them one-by-one, which is time-consuming.

This design adds **batch operations** to the draft box:
1. **Batch delete** — select N drafts, delete in one request.
2. **Batch publish** — select N drafts, publish each as an independent publish history (behaviorally equivalent to "click Edit → publish page → click Publish", except the user does not leave the draft box).

### Hard constraint: do not modify stable publish code paths

The publish page (`frontend/src/views/PublishCenter.vue`, ~80KB) and image-publish page (`frontend/src/views/ImagePublish.vue`, ~50KB) are **stable, multi-iteration production code** that handles per-platform declarations, 4-level merge config, draft restoration, etc. **They must not be modified** by this feature. Backend single-publish endpoints (`POST /postVideo`, `POST /api/image-publish/publish`) are also off-limits.

`platform/<platform>/platform.py` `publish_video` implementations are also off-limits. They are the leaf of the publish call tree; batch publish calls them with the same kwargs.

### Goals

- Add multi-select + batch delete + batch publish to `DraftBox.vue`.
- Make batch publish semantically equivalent to "click Edit → publish → click Publish" **per draft** (i.e., one draft → one publish history; one draft with N accounts → N publish histories).
- Reuse the existing `ext_api` task queue (`task_queue.add_task`) for async execution, status, retry, and SSE.
- Add dry-run validation so a half-edited draft does not silently fail mid-publish.

### Non-Goals

- Modify `PublishCenter.vue` or `ImagePublish.vue`.
- Modify `backend/app.py` `postVideo` / `postVideoBatch`.
- Modify `backend/blueprints/image_publish_bp.py` `publish` / `execute-publish`.
- Modify any `backend/impl/<platform>/platform.py` `publish_video` implementation.
- Add new platforms or new publish fields.
- Add platform/account overrides at batch-publish time (草稿里有什么就用什么).

---

## Data Model

No new tables. Two existing tables are involved, and **one existing table is extended**.

### `drafts` (video drafts, unchanged)

`id, type, title, cover_path, draft_data(JSON), channels_summary, video_duration, video_file_size, created_at, updated_at`. `type='video'` only — image drafts live in `image_drafts`.

### `image_drafts` (image drafts, unchanged)

`id, image_ids, account_configs(JSON), created_at, updated_at`.

`account_configs` is a **single dict** (not a list) containing the per-account config — verified by reading `image_publish_bp.publish_images:90-95` (`isinstance(config, dict)`). The dict has these top-level keys (extracted from `image_publish_bp.publish_images:99-114`):

```python
{
    "platform": str,           # 平台名 'xiaohongshu' / 'douyin' / ...
    "account_id": int,
    "account_name": str,
    "filePath": str,           # cookie 文件名（image_publish_bp 唯一存 cookie 路径的字段）
    "title": str,
    "description": str,
    "images": list,            # 图片素材对象列表 [{id, name, stored_path, url, ...}]
    "image_ids": list[str],    # images 对应的 id 列表
    "coverImage": dict,        # 封面素材对象
    "coverMaterialId": str,    # 封面素材 ID（image_publish_bp 中用，spec 上写明）
    "aiContent": str | bool,
    "isOriginal": bool,
    "creationDeclaration": str | list,
    "supplementaryDeclaration": str,  # 百家号
    "isDraft": bool,                # 视频号
    "scheduleTime": str,
    "enableTimer": int,             # 0/1
    "videosPerDay": int,
    "dailyTimes": list[str],
    "startDays": int,
    "category": str | int,
    "tags": list[str],
    "hotspot": str,
    "tag_type": str,
    "tag_value": str,
    "mini_link": str,
    "mix_id": str,
    "productLink": str,
    "productTitle": str,
    "audience": str,
    "alteredContent": bool,
    "riskWarning": str,             # 爱奇艺
    "enableCashActivity": bool,     # 爱奇艺
    # ... 其余平台特定字段
}
```

The image batch endpoint reads each draft's `account_configs` (single dict) and constructs a `publish_images` call with `image_ids` and the same `account_configs` — **no 4-level merge needed** (image flow is simpler, configs are already per-account).

### `draft_data` JSON shape (video drafts)

Verified by querying the live DB (`drafts.id=15` on 2026-06-11):

```json
{
  "commonConfig":      { "videoLandscape", "videoPortrait", "coverLandscape", "coverPortrait" },
  "platformConfigs":   { "<platform>": { title, description, tags, aiContent, isOriginal, ... } },
  "platformOverrides": { "<platform>": { coverLandscape, coverPortrait, videoLandscape, videoPortrait } },
  "accountOverrides":  { "<accountId>": { title, description, tags, aiContent, isOriginal, ... } },
  "platformChecked":   { "<platform>": bool },
  "accountChecked":    { "<accountId>": bool },
  "publishAccountIds": [int],
  "selectedPlatform":  string | null,
  "selectedAccountId": int | null,
  "expandedGroups":    [string],
  "videoModeTab":      "portrait" | "landscape"
}
```

`platformConfigs` is the **platformDefault** layer; `platformOverrides` is the platform-overrides layer; `accountOverrides` is the per-account overrides layer; `commonConfig` is the common fallback.

`platformChecked` and `accountChecked` are UI state and **do not participate in the publish loop** (confirmed by reading `PublishCenter.vue:1298-1451`); the loop iterates over `publishAccountIds` and looks up `accountGroups` (grouped by `user_info.platform`).

### `publish_batches` (extended)

Add 2 columns via `migrate_database()` in `init_db.py`:

```sql
ALTER TABLE publish_batches ADD COLUMN source TEXT NOT NULL DEFAULT '';
ALTER TABLE publish_batches ADD COLUMN draft_id INTEGER NOT NULL DEFAULT 0;
```

`source='draft'` for batch-published drafts; empty for normal postVideo flow. `draft_id` is the originating `drafts.id` (image drafts use `image_drafts.id`; the type discriminates). Indexed: `CREATE INDEX idx_publish_batches_draft ON publish_batches(source, draft_id)`.

The Task Center's "filter by source" UI and the draft box's "view tasks for this draft" link rely on these columns.

> **Important — no `publish_tasks` table exists.** The legacy `publish_tasks` / `publish_logs` / `image_publish_tasks` / `image_publish_logs` tables were dropped in commit `71898c0` ("refactor(db): 合并发布历史为 publish_batches + publish_details 两表"). `PublishTask` is an in-memory dataclass; its persistent state goes to `publish_details.account_configs` (a JSON column already populated by `task_queue._insert_db` via `_build_account_configs(task)`). **`PublishTask.payload` is in-memory only** — used to splat into `platform.publish_video(**payload)` at execution time, then discarded. It does NOT need a DB column.

---

## Backend API

Three new endpoints. **No modification** to any existing publish endpoint.

### 1. `POST /api/v2/drafts/batch-publish` (video)

**Request**
```json
{ "draft_ids": [15, 16, 18] }   // 1-30
```

**Response 200**
```json
{
  "task_ids": ["uuid-...", "uuid-..."],
  "failed": [
    { "draft_id": 18, "reason": "缺少视频文件" },
    { "draft_id": 16, "reason": "账号 5(bilibili) 缺 creationDeclaration" }
  ]
}
```

**Error responses**
- `400 draft_ids 数量必须 1-30`
- `400 wrong_type_ids: [3]` — if any draft has `type != 'video'`
- `404 missing_ids: [99, 100]` — if any draft_id not found

**Behavior**
1. Fetch all drafts (`SELECT * FROM drafts WHERE id IN (...) AND type='video'`).
2. For each draft, run `validate_draft_for_publish(draft)` (dry-run). Failures go into `failed`.
3. For each valid draft, iterate over `draft.draft_data.publishAccountIds`. For each `account_id`:
   - Look up `account.file_path` and `account.platform_id` from `user_info` (joined to platform registry).
   - Run `merge_config(common, platformDefault, platformOv, accountOv)` with all four layers pulled from `draft.draft_data`.
   - Run `build_platform_kwargs(merged, common, account) -> dict` (see Payload Adapter below).
   - Construct `PublishTask(platform=<str>, platform_type=<int>, account_name=<str>, account_cookie_path=<file_path>, payload=<kwargs>, source='draft', draft_id=<draft.id>, ...)` and call `task_queue.add_task(task)`.
   - Append the new task id to `task_ids`.
4. If `add_task` raises, append `{draft_id, reason: "入队失败: <msg>"}` to `failed` and continue.
5. Return.

### 2. `POST /api/image-publish/drafts/batch-publish` (image)

**Request**
```json
{ "draft_ids": [3, 4] }   // 1-30
```

**Response**: same shape as video.

**Error responses**: same as video, but for `image_drafts`.

**Behavior**
1. Fetch all drafts (`SELECT * FROM image_drafts WHERE id IN (...)`).
2. For each draft, run `validate_image_draft_for_publish(draft)`. Failures go into `failed`.
3. For each valid draft:
   - Read `draft.account_configs` (single dict, per-account).
   - For each entry in `draft.image_ids` (or once with the full list), call `image_publish_bp.publish_images`-equivalent (image batch loops over the existing per-row endpoint OR calls a new batch path).
   - **Decision**: to keep image batch simple and reuse the existing endpoint, **call `POST /api/image-publish/publish` N times** internally (one call per image-id-set, or one call with all image_ids). The endpoint already writes `publish_batches` + `publish_details` rows.
   - Append the resulting task / detail ids to `task_ids`.

> The exact internal flow (one call per image vs one call total) is an implementation detail; the spec only requires that the draft ends up as one row in `publish_batches` and one row in `publish_details` per (draft, account). This mirrors the current image flow's "one POST = one detail" behavior.

### 3. `DELETE /api/v2/drafts/batch` (video batch delete)

**Request**
```json
{ "draft_ids": [15, 16, 18] }
```

**Response 200**
```json
{ "deleted": [15, 16], "failed": [{ "draft_id": 18, "reason": "..." }] }
```

Image drafts reuse the existing `DELETE /api/image-publish/drafts/<id>` per-row endpoint; the frontend loops. Image delete has no side effects worth a custom batch endpoint.

---

## 4-Level Merge Logic (backend, new function)

`merge_config(common, platform_default, platform_ov, account_ov)` lives in `backend/services/draft_merge.py` (new file). It returns a dict with **the same 30+ fields** as `PublishCenter.vue:592-637`. The field list and priority order must be kept in sync with the publish page; this is documented in the module docstring with a reference to the publish page line range.

### Field groups and merge priority

The publish page uses **two distinct priority chains**. The batch endpoint must mirror them exactly:

**3-level merge** (most fields): `accountOv > platformOv > platformDefault`. **No `common` fallback.**
- `title`, `description`, `tags`
- `videoFormat`, `enableTimer`, `scheduleTime`, `aiContent`, `isOriginal`
- `creationDeclaration`, `riskWarning`, `enableCashActivity`, `supplementaryDeclaration`
- `audience`, `alteredContent`
- `zone`, `activityId`, `hotspotId`, `hotspotData`, `selectedTag`, `tagType`, `tagValue`
- `mixId`, `mixData`, `topic`, `isDraft`, `location`, `collection`, `groupChat`

**4-level merge** (4 fields): `accountOv > platformOv > common` (skip `platformDefault`). **`common` is the fallback.**
- `coverLandscape`, `coverPortrait`, `videoLandscape`, `videoPortrait`

Boolean fields use `is None` checks (False is a valid override). List fields fall through to the first non-empty list. String fields use truthy checks.

**Critical rule**: this function is **standalone** — it does not import or call any publish-page code, it does not import Vue components, and it does not import the frontend in any form. It is a pure-Python dict builder.

The TDD test must include a case for each field proving which priority chain it uses, e.g., `merge_config(common={'title': 'X'}, platform_default={'title': 'Y'}, platform_ov={'title': 'Z'}, account_ov={'title': 'W'})` for both chain types.

---

## Validation (dry-run, backend)

`validate_draft_for_publish(draft) -> list[str]` lives in `backend/services/draft_merge.py` next to the merge function. Returns a list of error messages; empty list means valid.

Per draft, before iterating accounts:
1. `commonConfig.videoLandscape or commonConfig.videoPortrait` must be set.
2. At least one of: `commonConfig.coverLandscape/Portrait`, any `accountOverrides[*].coverLandscape/Portrait`, any `platformOverrides[*].coverLandscape/Portrait` must be set.
3. `publishAccountIds` must be non-empty.

For each `account_id` in `publishAccountIds`:
1. Look up `user_info.platform`. If account does not exist → error: `"账号 {id} 不存在"`.
2. Run `merge_config(...)` to get the merged payload.
3. `merged.title` must be a non-empty string.
4. `merged.videoFormat` must be in `{'portrait', 'landscape'}`.
5. Cover check based on `videoFormat`:
   - `'portrait'` requires `merged.coverPortrait` to be set.
   - `'landscape'` requires `merged.coverLandscape` to be set.
6. **Platform-specific declaration fields** (using `DECLARATION_PLATFORMS` table, mirroring `PublishCenter.vue:1329-1338`):
   - `xiaohongshu`, `douyin`, `kuaishou` → `aiContent`
   - `bilibili`, `baijiahao`, `tencent_video`, `iqiyi` → `creationDeclaration`
   - `youtube` → `audience` AND `alteredContent` (both required)
   - `channels`, `tiktok` → no declaration required (publishable without these)
7. Douyin special: `activityId.length + tags.length <= 5`.

Errors are returned as `[{draft_id, reason: "..."}]` to the frontend. **A draft with errors does not block other drafts.**

---

## Payload Adapter (merged → platform.publish_video kwargs)

The output of `merge_config(...)` uses **Vue-style camelCase** field names (`coverLandscape`, `creationDeclaration`, `aiContent`...). The `platform.publish_video(**kwargs)` methods accept **Python-style snake_case** field names with different renames (`thumbnail_landscape_path`, `creation_declaration`, `ai_content`...). The publish endpoint `app.py:466-556` does this translation today.

`build_platform_kwargs(merged, common, account) -> dict` lives in `backend/services/draft_merge.py` and produces the kwargs dict that `platform.publish_video(**kwargs)` expects. The transformation is **deliberately separate from `merge_config`** so the two can evolve independently.

### Field renames (full list)

| Merged (post `merge_config`) | `platform.publish_video` kwarg |
|---|---|
| `merged.title` | `title` |
| `merged.description` | `desc` |
| `merged.tags` | `tags` |
| `merged.activityId` | `activities` |
| `merged.videoPortrait` (or `common.videoPortrait`; chosen by `videoFormat`) → `material.stored_path` | `files=[stored_path]` |
| `merged.coverLandscape` (or `common.coverLandscape`) → `stored_path` | `thumbnail_landscape_path` |
| `merged.coverPortrait` (or `common.coverPortrait`) → `stored_path` | `thumbnail_portrait_path` |
| `common.coverLandscape` (or merged; only if portrait cover missing) → `stored_path` | `thumbnail_path` (generic fallback) |
| `merged.scheduleTime` | `schedule_time_str` |
| `merged.aiContent` | `ai_content` |
| `merged.creationDeclaration` (str *or* list of str; `None` → `''`) | `creation_declaration` (list joined with `','`) |
| `merged.isOriginal` (bool) | not passed — handled per-platform by `category` |
| `merged.audience` (default `'not_kids'`) | `audience` |
| `merged.alteredContent` (default `False`) | `altered_content` |
| `merged.hotspotId` | `hotspot` |
| `merged.tagType` / `merged.tagValue` | `tag_type` / `tag_value` |
| `merged.mixId` | `mix_id` |
| `merged.selectedTag` (object, when `type === 'miniapp'`) | `mini_link: selectedTag._searchKeyword or ''` |
| `merged.isDraft` (channels) | `is_draft` |
| `merged.supplementaryDeclaration` (baijiahao) | `supplementary_declaration` |
| `merged.riskWarning` (iqiyi) | `risk_warning` |
| `merged.enableCashActivity` (iqiyi) | `enable_cash_activity` |
| `merged.zone` (B 站) or `merged.isOriginal ? 1 : 0` | `category` |
| `account.file_path` (cookie file basename) | `account_file=[file_path]` |
| `merged.scheduleTime` truthy | `enableTimer=1` else `enableTimer=0` |
| `merged.tags.length > 0` only if drafts has them | not duplicated |
| Defaults: `videos_per_day=1`, `daily_times=['10:00']`, `start_days=0` | (pass through as kwargs) |

The `fileList` (PublishCenter-side) becomes a **single-element** `files=[stored_path]` list (matching the signature in `xiaohongshu/platform.py:206-242` and the call in `app.py:492-523`).

`isOriginal` is **not** a top-level publish_video kwarg in most platforms; it flows through `category` (line above). If a platform implementation needs raw `is_original`, the adapter can add it; currently the publish page (line 1515) and `app.py:490-523` do not pass it.

This adapter function gets its own TDD test: every row in the table above is at least one test case.

---

## Task Queue Integration (extended)

`task_queue` (`backend/ext_api/task_queue.py`) currently has a worker that calls the **legacy module-level** uploaders (`myUtils.postVideo.post_video_DouYin` etc.) with hardcoded positional args, and does **not** read `PublishTask.ai_content` / `is_original` / `creation_declaration` / `schedule_time` / `video_landscape` / `video_portrait` / `cover_landscape` / `cover_portrait`. This means today's queue path loses the 4-level-merged config — only the basic title/file/desc/tags/cover flow works.

Batch publish needs the **full** merged config to reach `platform.publish_video`, so the worker is extended.

### Extension 1: extend `PublishTask` dataclass

`backend/ext_api/task_queue.py:36-67` — add fields:

```python
@dataclass
class PublishTask:
    # ... existing fields ...

    # Batch-publish / draft-source fields (NEW)
    source: str = ''               # '' | 'draft' | 'normal'
    draft_id: int = 0              # 0 for non-draft tasks
    account_id: int = 0            # the user_info.id of the target account
    payload: dict = field(default_factory=dict)
    # `payload` holds the kwargs to splat into platform.publish_video(**payload).
    # For batch-publish-from-draft, payload is the output of build_platform_kwargs().
    # For pre-existing flow, payload is empty and the existing positional path still works.
```

`to_dict()` and `from_row()` need updates to JSON-encode / -decode `payload`. **`PublishTask.payload` is in-memory only** (see the `publish_batches` extension note above) — no DB column is added.

### Extension 2: extend the worker

`backend/ext_api/task_queue.py:197-260` — replace the `match task.platform_type` body with:

```python
async def _execute(self, task: PublishTask):
    from impl.registry import get_platform

    if task.payload:
        # Batch-publish path: payload carries the full kwargs.
        # Splat them into platform.publish_video(**payload).
        platform = get_platform(task.platform_type)
        if not platform:
            raise ValueError(f"不支持的平台类型: {task.platform_type}")
        publish_fn = platform.publish_video
        loop = asyncio.get_event_loop()
        if asyncio.iscoroutinefunction(publish_fn):
            return await loop.run_in_executor(None, lambda: publish_fn(**task.payload))
        return publish_fn(**task.payload)

    # Legacy path (untouched): title/file_list/tags/desc/thumbnail_path
    # ... existing match-case block unchanged ...
```

The legacy block stays as-is for any existing callers (e.g., the manual postVideo flow that may also use the queue). It is a strict no-op for batch-publish.

### Extension 3: history source / draft_id

`app.py:_record_publish` (line 652-680) reads from `data` only. To capture `source` and `draft_id` for batch-published tasks, the new batch endpoint inserts the `publish_batches` row **directly** (bypassing the `POST /postVideo` flow), with `source='draft'` and `draft_id=<id>`. `publish_details` is then written by the existing `_record_publish` helper.

This means the batch endpoint writes the `publish_batches` row **before** adding the task to the queue; the worker (after Extension 2) writes `publish_details` via `_record_publish` with the data the task carries.

Actually, the simpler approach: the batch endpoint inserts `publish_batches` with `source='draft'`, `draft_id=<id>`, and **also** inserts a `publish_details` row for each (account) with `status='pending'`. The worker updates the `publish_details` row to `running` / `success` / `failed` when it runs, mirroring `_update_publish_result`. The new `_record_publish` is not used for batch (it lives in `app.py` and does not know about `source`/`draft_id`).

To keep the worker change minimal, the batch endpoint stores `batch_id` and `detail_id` in `task.batch_id` and a new `task.detail_id` field, and the worker updates the matching `publish_details` row by `detail_id`. This adds one more `PublishTask` field.

### Why not just call `POST /postVideo` in a loop?

The simpler alternative is to have the batch endpoint issue `N` HTTP calls (or function calls) to `POST /postVideo` internally. `POST /postVideo` already writes `publish_batches` / `publish_details` correctly (via `_before_publish` and `_record_publish`), and already handles the full 4-level-merged payload via `platform.publish_video(**kwargs)`.

**This approach is rejected** because it gives up the task queue's async execution, status, retry, and SSE — which is the main reason for the batch endpoint in the first place. But the spec keeps it as a **fallback** if the worker extension proves too risky during implementation: in that case the batch endpoint just calls `platform.publish_video(**kwargs)` synchronously in a loop, mirroring `postVideo` body (line 466-556), and the existing `_before_publish` history recording happens automatically because the route is `/postVideo` internally. (See Open Question 1.)

---

## Frontend

### A. `DraftBox.vue` — multi-select + toolbar

- Add a `selection` reactive `Set<number>` and a checkbox column on each row.
- Top toolbar (above the table): "全选 / 反选 / 已选 N 项" + buttons "批量删除" and "批量发布".
- Toolbar is hidden when `selection.size === 0`; otherwise floats at the top with a clear "清空选择" link.
- Existing per-row Edit / Delete buttons remain unchanged.

**File**: `frontend/src/views/DraftBox.vue` (modify, ~150 lines added)
**Constraint**: this file IS the main battleground for this feature; modifications here are expected. The "do not modify" rule applies to `PublishCenter.vue` and `ImagePublish.vue` only.

### B. `BatchPublishDialog.vue` — new component

Path: `frontend/src/components/BatchPublishDialog.vue`.

Props: `visible: Boolean`, `drafts: Array<{id, type, title}>`, `failures: Array<{draft_id, reason}>`.
Emits: `update:visible`, `confirm` (with final `draft_ids` list after user un-ticks failures).

Layout:
- Header: "批量发布预览"
- Body: a list of rows, one per draft, each row showing: title, target platforms (from `publishAccountIds` → `user_info.platform`), ✓ or ✗ with reason.
- Failed rows are un-checked by default; user can un-tick more.
- "确认发布 N 项" button (disabled when N=0).
- On confirm: emit `confirm` with `draft_ids`, then call the batch endpoint.
- After response: show toast "已入队 N 个任务，去查看 →" (link to `/tasks`), and a section listing the failed items with a "重试" button.

**No reuse** of `PublishCenter.vue` or `ImagePublish.vue` internals. The dialog contains its own minimal payload preview (just for display; the actual API call is fire-and-forget to the backend batch endpoint).

### C. `api/draft.js` — add 2 methods

```js
export function batchPublishVideoDrafts(draftIds) { ... }   // POST /api/v2/drafts/batch-publish
export function batchDeleteDrafts(draftIds) { ... }         // DELETE /api/v2/drafts/batch
```

For image drafts, the frontend loops over `imagePublishApi.deleteDraft(id)` (existing method).

### D. Style/UX

Use `ui-ux-pro-max-skill` for the dialog and toolbar styling. The draft box currently uses a card grid; multi-select needs a "select mode" toggle so the card grid can stay clean in default view.

---

## Error Handling

| Scenario | Status | Where handled | User-facing message |
|---|---|---|---|
| `draft_ids` empty or > 30 | 400 | backend | toast "请选择 1-30 个草稿" |
| Draft not found | 404 | backend | toast + close dialog |
| Wrong type (video endpoint gets image) | 400 | backend | toast + close dialog |
| Draft missing video/cover/title/declaration | 200 (in `failed`) | backend | shown in dialog; user un-ticks and confirms the rest |
| Account in `publishAccountIds` does not exist | 200 (in `failed`) | backend | shown in dialog |
| `add_task` queue error | 200 (in `failed`) | backend | shown in dialog with "重试" button |
| Network error / timeout | n/a | frontend | toast "网络错误，请稍后再试" |
| Backend 5xx | n/a | frontend | toast "服务异常，请稍后再试" |

**Never block the entire batch on a single failure.** The dialog always shows the full result of `failed` and lets the user re-submit the un-failed subset.

---

## Testing (TDD)

For every new function, write a FAILING test first, then make it GREEN, then REFACTOR.

### Unit (backend)

| File | Function | Cases |
|---|---|---|
| `backend/tests/test_draft_merge.py` (new) | `merge_config` | Each of the 30+ fields, **with a 3-level vs 4-level chain assertion per field**; booleans (False ≠ None); lists (empty vs missing); common fallback for `cover*` / `video*` only; platformDefault fallback for everything else. |
| `backend/tests/test_draft_merge.py` | `validate_draft_for_publish` | Missing video / cover / title / videoFormat / declaration; wrong videoFormat; portrait without portrait cover; YouTube missing either `audience` or `alteredContent`; Douyin activity+tags > 5. |
| `backend/tests/test_draft_merge.py` | `validate_image_draft_for_publish` | Missing `image_ids` / `title` / declaration fields in `account_configs`. |
| `backend/tests/test_draft_merge.py` | `build_platform_kwargs` | One test case per row in the Payload Adapter table; `videoFormat=portrait` picks portrait video, `landscape` picks landscape, missing falls back to common; `creationDeclaration` as list joins with comma; `None` becomes `''`. |
| `backend/tests/test_draft_merge.py` | `DECLARATION_PLATFORMS` constant | Mirrors publish-page table: every platform key maps to the correct field(s). |

### Integration (backend, Flask test client)

| Endpoint | Cases |
|---|---|
| `POST /api/v2/drafts/batch-publish` | happy path (1 draft, 1 account → 1 task); multi-account → multi-task; partial failure (1 of 3 drafts invalid, others succeed); draft not found → 404; wrong type → 400; > 30 → 400; empty → 400; `add_task` raises → in `failed`. |
| `POST /api/image-publish/drafts/batch-publish` | happy path + missing image_ids / title / declaration. |
| `DELETE /api/v2/drafts/batch` | happy path; partial failure (1 not found); empty → 400. |

Mocks: `task_queue.add_task` is patched to return deterministic ids and to capture the `PublishTask` for inspection; `user_info` lookup is patched with a fixture table.

### Worker integration

A separate test (`backend/tests/test_task_queue_extended.py`) verifies the worker Extension 2: feed it a `PublishTask` with `payload={'title': '...', 'files': [...], 'ai_content': '...', 'creation_declaration': '...', ...}` and assert `platform.publish_video` was called with the same kwargs.

### Manual / e2e (gstack /qa + Playwright)

| Flow | Steps |
|---|---|
| Batch publish happy path | Save a draft via PublishCenter; switch to DraftBox; select; click Batch Publish; confirm; expect toast + tasks visible in Task Center; click the task and verify `source='draft'`, `draft_id=<id>` in the publish_batches row. |
| Batch publish partial failure | Save 2 drafts, delete the video file for one; batch publish; expect 1 success + 1 failure in dialog. |
| Batch delete | Select 3 drafts; click Batch Delete; confirm; expect rows removed; expect API DELETE request with all 3 ids. |

### Out of test scope

- `PublishCenter.vue` / `ImagePublish.vue` (not modified)
- `postVideo` / `image_publish.publish` (not modified)
- `platform.publish_video` per-platform implementations (already covered by their own tests)

---

## Files

### Create

- `backend/services/draft_merge.py` — `merge_config`, `validate_draft_for_publish`, `validate_image_draft_for_publish`, `build_platform_kwargs`, `DECLARATION_PLATFORMS`
- `backend/tests/test_draft_merge.py` — unit + integration tests
- `frontend/src/components/BatchPublishDialog.vue` — confirmation/preview dialog

### Modify

- `backend/ext_api/__init__.py` — add `POST /api/v2/drafts/batch-publish` and `DELETE /api/v2/drafts/batch` route handlers
- `backend/blueprints/image_publish_bp.py` — add `POST /api/image-publish/drafts/batch-publish` route handler
- `backend/ext_api/task_queue.py` — add `PublishTask.source` / `draft_id` / `account_id` / `payload` / `detail_id` fields; extend `_execute` to splat `payload` into `platform.publish_video(**payload)` when present
- `backend/init_db.py` — extend `migrate_database()` to add `publish_batches.source` / `draft_id` columns (with index). **No `publish_tasks` table changes** — that table was dropped in commit `71898c0`; `PublishTask.payload` is in-memory only.
- `frontend/src/views/DraftBox.vue` — add multi-select state, toolbar, dialog trigger
- `frontend/src/api/draft.js` — add `batchPublishVideoDrafts`, `batchDeleteDrafts`

### Not modified (the hard constraint)

- `frontend/src/views/PublishCenter.vue`
- `frontend/src/views/ImagePublish.vue`
- `backend/app.py` (`postVideo`, `postVideoBatch`)
- `backend/blueprints/image_publish_bp.py` (`publish`, `execute_publish`)
- Any `backend/impl/<platform>/platform.py`

---

## Open Questions

1. **Worker Extension 2 risk** — replacing the worker's `match task.platform_type` body changes the queue's behavior for any existing queue users. Mitigation: keep the legacy block as a strict fallthrough when `task.payload` is empty (covered above). Implementation plan should verify no existing caller passes a non-empty `payload` today.
2. **History write strategy for batch** — the spec proposes the batch endpoint inserts `publish_batches` + `publish_details` directly, and the worker updates `publish_details` status. An alternative is for the batch endpoint to call `_record_publish` after the task runs, but that would require knowing the task id at insert time. The proposed strategy keeps history records visible in the Task Center even before the worker picks up the task.
3. **Image batch endpoint's exact internal flow** — the spec leaves the image batch endpoint's internal implementation flexible (call `POST /api/image-publish/publish` N times, or batch internally). The implementation plan should pick one and document it.
