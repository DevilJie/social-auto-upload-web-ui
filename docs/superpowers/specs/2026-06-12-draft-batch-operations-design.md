# Draft Batch Operations Design

## Context

`DraftBox.vue` currently supports per-row "Edit" (jumps to PublishCenter or ImagePublish) and "Delete" (single draft). The publish flow always goes: click "Edit" → publish page → click "Publish". With ~30+ drafts in the box, the operator needs to publish them one-by-one, which is time-consuming.

This design adds **batch operations** to the draft box:
1. **Batch delete** — select N drafts, delete in one request.
2. **Batch publish** — select N drafts, publish each as an independent publish history (behaviorally equivalent to "click Edit → publish page → click Publish", except the user does not leave the draft box).

### Hard constraint: do not modify stable publish code paths

The publish page (`frontend/src/views/PublishCenter.vue`, ~80KB) and image-publish page (`frontend/src/views/ImagePublish.vue`, ~50KB) are **stable, multi-iteration production code** that handles per-platform declarations, 4-level merge config, draft restoration, etc. **They must not be modified** by this feature. Backend single-publish endpoints (`POST /postVideo`, `POST /api/image-publish/publish`) and their helpers are also off-limits.

The batch path is **independent**: it reads `draft_data` directly, performs the same 4-level merge in a new backend function, and feeds the merged payload into the existing task queue without touching the publish endpoints.

### Goals

- Add multi-select + batch delete + batch publish to `DraftBox.vue`.
- Make batch publish semantically equivalent to "click Edit → publish → click Publish" **per draft** (i.e., one draft → one publish history; one draft with N accounts → N publish histories).
- Reuse the existing `ext_api` task queue (`task_queue.add_task`) for async execution, status, retry, and SSE.
- Add dry-run validation so a half-edited draft does not silently fail mid-publish.

### Non-Goals

- Modify `PublishCenter.vue` or `ImagePublish.vue`.
- Modify `backend/app.py` `postVideo` / `postVideoBatch` or `backend/blueprints/image_publish_bp.py` `publish` / `execute-publish`.
- Modify any `backend/impl/<platform>/platform.py` `publish_video` implementation.
- Add new platforms or new publish fields.
- Add platform/account overrides at batch-publish time (草稿里有什么就用什么).

---

## Data Model

No new tables. Two existing tables are involved.

### `drafts` (video drafts, unchanged)

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER PK | |
| `type` | TEXT DEFAULT 'video' | `'video'` only — image drafts live in `image_drafts` |
| `title` | TEXT | First non-empty platform title |
| `cover_path` | TEXT | Card thumbnail path |
| `draft_data` | TEXT | Full state JSON (see below) |
| `channels_summary` | TEXT | `[{platform, count}, ...]` |
| `video_duration` | REAL | Seconds |
| `video_file_size` | INTEGER | Bytes |
| `created_at` / `updated_at` | DATETIME | |

### `image_drafts` (image drafts, unchanged)

`id, image_ids, account_configs, created_at, updated_at`. Two separate tables because image and video flows have always been managed independently.

### `draft_data` JSON shape (video drafts)

Verified by querying the live DB (`drafts.id=15` on 2026-06-11):

```json
{
  "commonConfig":   { "videoLandscape", "videoPortrait", "coverLandscape", "coverPortrait" },
  "platformConfigs": { "<platform>": { title, description, tags, aiContent, isOriginal, ... } },
  "platformOverrides": { "<platform>": { coverLandscape, coverPortrait, videoLandscape, videoPortrait } },
  "accountOverrides":   { "<accountId>": { title, description, tags, aiContent, isOriginal, ... } },
  "platformChecked":   { "<platform>": bool },
  "accountChecked":    { "<accountId>": bool },
  "publishAccountIds": [int],
  "selectedPlatform":  string | null,
  "selectedAccountId": int | null,
  "expandedGroups":    [string],
  "videoModeTab":      "portrait" | "landscape"
}
```

**Key insight**: `draft_data` stores the **unmerged 4-layer state** + `publishAccountIds`. The actual publish payload is obtained by applying `mergeConfig(common, platformDefault, platformOv, accountOv)` for each `(platform, account_id)` pair. This is the exact same logic `PublishCenter.vue:592-637` performs on the publish page.

`platformChecked` and `accountChecked` are UI state and **do not participate in the publish loop** (confirmed by reading `PublishCenter.vue:1298-1451`); the loop iterates over `publishAccountIds` and looks up `accountGroups` (grouped by `user_info.platform`).

### `image_drafts` `account_configs` JSON shape (image drafts)

Stored as a list of `account_configs` entries; each entry already contains per-account merged fields (image-publish flow is simpler than video and does not use 4-level merge). See `image_publish_bp.saveDraft` for exact schema.

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
2. For each draft, run `validate_draft_for_publish(draft)` (dry-run, see below). Failures go into `failed`.
3. For each valid draft, iterate over `draft.draft_data.publishAccountIds`. For each `account_id`:
   - Look up `user_info.platform` for that account.
   - Run `merge_config(common, platformDefault, platformOv, accountOv)` with all four layers pulled from `draft.draft_data`.
   - Call `task_queue.add_task(type='video', platform=<account.platform>, account_id=<account_id>, payload=<merged>, source='draft', draft_id=<draft.id>)`.
   - Append the new task id to `task_ids`.
4. If `add_task` raises, append `{draft_id, reason: "入队失败: <msg>"}` to `failed` and continue with the next draft.
5. Return.

### 2. `POST /api/image-publish/drafts/batch-publish` (image)

Same shape. The image flow is simpler: `image_drafts` already stores per-account merged `account_configs`, so no 4-level merge is needed — payload construction reads the stored `account_configs` entry directly. Validation: each `account_configs` entry must have a non-empty `image_ids` list, a non-empty `title`, and platform-required declaration fields.

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

Field groups:
- **Text**: `title`, `description`, `tags`
- **Media** (common falls back): `coverLandscape`, `coverPortrait`, `videoLandscape`, `videoPortrait`
- **Platform-common**: `videoFormat`, `enableTimer`, `scheduleTime`, `aiContent`, `isOriginal`
- **Platform-specific**: `creationDeclaration`, `riskWarning`, `enableCashActivity`, `supplementaryDeclaration`, `audience`, `alteredContent`, `zone`, `activityId`, `hotspotId`, `hotspotData`, `selectedTag`, `tagType`, `tagValue`, `mixId`, `mixData`, `topic`, `isDraft`, `location`, `collection`, `groupChat`

Priority for every field: `accountOv > platformOv > platformDefault > common`. Boolean fields use `is None` checks (False is a valid override). List fields fall through to the first non-empty list.

**Critical rule**: this function is **standalone** — it does not import or call any publish-page code, it does not import Vue components, and it does not import the frontend in any form. It is a pure-Python dict builder.

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
   - `channels`, `tiktok` → no declaration required (they use a bool switch for AI content but it is not a publish blocker; leave as "publishable")
7. Douyin special: `activityId.length + tags.length <= 5`.

Errors are returned as `[{draft_id, reason: "..."}]` to the frontend. **A draft with errors does not block other drafts.**

---

## Task Queue Integration

`task_queue.add_task` already exists in `backend/ext_api/task_queue.py:254`. Each call enqueues a single publish job that the worker picks up and dispatches to `platform.publish_video(**payload)`. The payload structure matches what the publish page constructs, so workers can run unmodified.

Each `add_task` call passes metadata:
```python
task = task_queue.add_task(
    type='video',
    platform=<account.platform>,   # e.g. 'bilibili'
    account_id=<account_id>,
    payload=<merged_payload>,
    metadata={
        'source': 'draft',
        'draft_id': draft.id,
    },
)
```

`source='draft'` and `draft_id` flow into `publish_batches` / `publish_details` so the existing Task Center can filter "tasks from drafts" and link back to the originating draft.

---

## Payload Adapter (merged → postVideo schema)

The output of `merge_config(...)` is **not** the final `postVideo` payload. The publish page performs a second transformation (`PublishCenter.vue:1498-1552`) to turn the merged fields into the schema `postVideo` expects. The batch endpoint must replicate this transformation, **without** importing the publish page.

The transform lives in `backend/services/draft_merge.py` as `build_postVideo_payload(merged, common, account, platform_id) -> dict`.

Key field renames (the rest pass through unchanged):

| Merged (post `merge_config`) | `postVideo` payload |
|---|---|
| `merged.title` | `title` |
| `merged.description` | `description` |
| `merged.tags` | `tags` |
| `merged.activityId` | `activities` |
| `merged.videoPortrait` *or* `merged.videoLandscape` (chosen by `videoFormat`, falling back to `common`) → `material.stored_path` | `fileList: [stored_path]` |
| `merged.coverLandscape` (or `common.coverLandscape`) → `stored_path` | `thumbnailLandscape` |
| `merged.coverPortrait` (or `common.coverPortrait`) → `stored_path` | `thumbnailPortrait` |
| `merged.scheduleTime` | `enableTimer: 1 if scheduleTime else 0`, `scheduleTime` |
| `merged.zone` (B 站) or `merged.isOriginal ? 1 : 0` | `category` |
| `merged.creationDeclaration` (str *or* list of str) | `creationDeclaration: list.join(',')` *or* str |
| `merged.audience` (default `'not_kids'`) | `audience` |
| `merged.alteredContent` (default `false`) | `alteredContent` |
| `merged.hotspotId` | `hotspot` |
| `merged.tagType` / `merged.tagValue` | `tag_type` / `tag_value` |
| `merged.mixId` | `mix_id` |
| `merged.selectedTag` (object, when `type === 'miniapp'`) | `mini_link: selectedTag._searchKeyword` |
| `merged.isDraft` (channels) | `isDraft` |
| `merged.supplementaryDeclaration` (baijiahao) | `supplementaryDeclaration` |
| `merged.riskWarning` (iqiyi) | `riskWarning` |
| `merged.enableCashActivity` (iqiyi) | `enableCashActivity` |
| `platform_id` (1-10, looked up via `user_info.platform`) | `type` |
| `account.filePath` (cookie path) | `accountList: [filePath]` |
| `account.id` | `accountId` |
| `common.videoLandscape.id` *or* `common.videoPortrait.id` | `videoMaterialId` |
| `common.coverLandscape.id` | `landscapeCoverMaterialId` |
| `common.coverPortrait.id` | `portraitCoverMaterialId` |
| (newly generated `crypto.randomUUID()`) | `batchId` |
| Defaults: `videosPerDay: 1`, `dailyTimes: ['10:00']`, `startDays: 0` | (pass through) |

The `batchId` is **per draft**, not per (draft, account). All accounts of a given draft share one `batchId`, mirroring the publish page (`PublishCenter.vue:1441`).

Material objects carry the fields the worker needs to copy the file from the materials store to the platform's upload path. The publish page sends **only the `stored_path` strings** to `postVideo`; the full material objects are sent via `coverLandscape` / `coverPortrait` keys (line 1542+) for `account_configs` persistence. The batch endpoint must do the same: pass `stored_path` strings in `fileList` / `thumbnail*`, and pass the full material objects in `coverLandscape` / `coverPortrait` / `videoLandscape` / `videoPortrait` for downstream persistence.

This adapter function gets its own TDD test: every row in the table above is at least one test case.

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
| `backend/tests/test_draft_merge.py` (new) | `merge_config` | Each of the 30+ fields with all 4 priority permutations; booleans (False ≠ None); lists (empty vs missing); common fallback when all 3 higher layers lack a field. |
| `backend/tests/test_draft_merge.py` | `validate_draft_for_publish` | Missing video / cover / title / videoFormat / declaration; wrong videoFormat; portrait without portrait cover; YouTube missing either `audience` or `alteredContent`; Douyin activity+tags > 5. |
| `backend/tests/test_draft_merge.py` | `build_postVideo_payload` | One test case per row in the Payload Adapter table; `videoFormat=portrait` picks portrait video, `landscape` picks landscape, missing falls back to common; `creationDeclaration` as list joins with comma; `batchId` is unique per call but stable within a draft. |
| `backend/tests/test_draft_merge.py` | `DECLARATION_PLATFORMS` constant | Mirrors publish-page table: every platform key maps to the correct field(s). |

### Integration (backend, Flask test client)

| Endpoint | Cases |
|---|---|
| `POST /api/v2/drafts/batch-publish` | happy path (1 draft, 1 account → 1 task); multi-account → multi-task; partial failure (1 of 3 drafts invalid, others succeed); draft not found → 404; wrong type → 400; > 30 → 400; empty → 400; `add_task` raises → in `failed`. |
| `POST /api/image-publish/drafts/batch-publish` | happy path + missing image_ids / title / declaration. |
| `DELETE /api/v2/drafts/batch` | happy path; partial failure (1 not found); empty → 400. |

Mocks: `task_queue.add_task` is patched to return deterministic ids; `user_info` lookup is patched with a fixture table.

### Manual / e2e (gstack /qa + Playwright)

| Flow | Steps |
|---|---|
| Batch publish happy path | Save a draft via PublishCenter; switch to DraftBox; select; click Batch Publish; confirm; expect toast + tasks visible in Task Center. |
| Batch publish partial failure | Save 2 drafts, delete the video file for one; batch publish; expect 1 success + 1 failure in dialog. |
| Batch delete | Select 3 drafts; click Batch Delete; confirm; expect rows removed; expect API DELETE request with all 3 ids. |

### Out of test scope

- `PublishCenter.vue` / `ImagePublish.vue` (not modified)
- `postVideo` / `image_publish.publish` (not modified)
- `platform.publish_video` per-platform implementations (already covered by their own tests)

---

## Files

### Create

- `backend/services/draft_merge.py` — `merge_config`, `validate_draft_for_publish`, `DECLARATION_PLATFORMS`
- `backend/tests/test_draft_merge.py` — unit + integration tests
- `frontend/src/components/BatchPublishDialog.vue` — confirmation/preview dialog

### Modify

- `backend/ext_api/__init__.py` — add `POST /api/v2/drafts/batch-publish` and `DELETE /api/v2/drafts/batch` route handlers
- `backend/blueprints/image_publish_bp.py` — add `POST /api/image-publish/drafts/batch-publish` route handler
- `frontend/src/views/DraftBox.vue` — add multi-select state, toolbar, dialog trigger
- `frontend/src/api/draft.js` — add `batchPublishVideoDrafts`, `batchDeleteDrafts`

### Not modified (the hard constraint)

- `frontend/src/views/PublishCenter.vue`
- `frontend/src/views/ImagePublish.vue`
- `backend/app.py` (`postVideo`, `postVideoBatch`)
- `backend/blueprints/image_publish_bp.py` (`publish`, `execute-publish`)
- Any `backend/impl/<platform>/platform.py`

---

## Open Questions

1. **Douyin activity+tag cap of 5** — currently checked only when `selectedPlatform.value === 'douyin'` in the publish page (line 1410). In batch publish, a single draft can target multiple Douyin accounts, so the cap must hold per-account, not per-draft. Trivial adjustment; flagged for the implementation plan.
2. **Image-draft `account_configs` shape** — the spec assumes image drafts already store per-account merged fields. Need to confirm by reading `image_publish_bp.saveDraft` to verify the exact schema (the image flow is simpler and may store the full payload including `fileList` / `thumbnail`). The implementation plan must read this file before writing the image-batch handler.
