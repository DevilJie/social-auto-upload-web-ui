# 批量视频发布功能设计（Batch Video Publish）

> 日期：2026-08-26
> 状态：待用户最终确认
> 目标：发布视频页从「单视频 × 多账号」升级为「多视频队列 × 各自账号集合」，后端复用持久化任务队列。

## 0. 已确认的决策（与用户逐条对齐）

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | UI 入口 | 改造现有「发布视频」页，不新建页面 |
| 2 | 核心架构 | **单视频发布状态外套一层数组**：每个数组元素 = 当前单视频发布的完整表单状态（公共配置 + 平台设置 + 平台/账号个性化 + **所选账号集合**），每个视频可配完全不同的账号和设置 |
| 3 | 执行链路 | 复用草稿批量发布的 TaskQueue（DB 持久化、任务中心可视化、SSE、页面关闭继续执行） |
| 4 | 发布间隔 | 系统设置页全局配置「任务间隔分钟数」，默认 0（连续发布）；>0 时队列串行 + 间隔等待 |
| 5 | 封面默认 | 视频添加后自动抽帧选一帧作默认封面（横竖卡同图），可换可编辑 |
| 6 | 定时发布 | 每视频用自己的 scheduleTime（结构天然支持，不做自动错开） |
| 7 | 内容覆盖 | 平台级 + 账号级标题/描述/标签覆盖天然保留（每视频内部 = 现有 override 结构） |
| 8 | 数量上限 | 不限制 |
| 9 | 草稿 | 结构升级 v2（videos 数组），旧草稿打开自动转成单元素队列 |
| 10 | 素材库多选 | 二期（MVP 用本地多文件上传添加） |

## 1. 数据模型

### 1.1 前端：视频队列状态

现有 PublishCenter 的这组"发布状态"整体变成数组元素（与现有 draft_data 结构完全同构）：

```
videos: [                          // 视频队列
  {
    // —— 与现有 draft_data 完全一致 ——
    commonConfig: { videoLandscape, videoPortrait,
                    coverLandscape, coverPortrait,
                    coverLandscape169, coverPortrait916 },
    platformConfigs:   { [platformKey]: {...} },   // 含 title/desc/tags/scheduleTime/平台特有字段
    platformOverrides: { [platformKey]: {...} },
    accountOverrides:  { [accountId]: {...} },
    platformChecked: { }, accountChecked: { },
    publishAccountIds: [ ... ],      // ★ 每视频独立的账号集合
    selectedPlatform, selectedAccountId, expandedGroups,
  },
  ...
]
currentVideoIndex: number           // 当前编辑的视频
```

**改造方式**：把 `commonConfig`、`platformConfigs`、`platformOverrides`、`accountOverrides`、`publishAccountIds` 等现有顶层响应式状态，改为「当前视频元素」的响应式代理（computed get/set 或切换时整体替换 reactive 对象）。现有 4000 行表单逻辑（4 级合并、校验、批量设置、一键填写、抽帧等）**全部无需感知多视频**，只操作"当前视频"。

### 1.2 草稿 v2（drafts 表，不建新表）

```
draft_data: {
  version: 2,
  videos: [ <现有 draft_data 结构>, ... ],
  currentIndex: 0
}
```

- 保存：整个队列存一个草稿（标题取第 1 个视频标题 + "等 N 个视频"）
- 恢复：`version` 缺失或无 `videos` → 视为旧单视频草稿，包成 `videos: [old]`，无缝兼容
- 自动保存（useAutoSave）与手动保存共用同一序列化函数

### 1.3 后端：批次与任务

- **每个视频 = 1 个 publish_batch**（batch_id 按视频生成），该视频 × 其账号集合 = N 个 publish_detail / PublishTask
- `PublishTask.source = 'batch'`（新增溯源值，区别于 ''/'draft'），任务中心/发布历史可识别"批量发布"来源
- 与草稿批量发布（source='draft'）行为一致：失败立即 FAILED 不自动重试，可在任务中心手动重试

## 2. UI 设计（PublishCenter 布局改动）

```
┌────────────────────────────────────────────────────────────────────┐
│ 发布视频 [小红书·个性化设置]        保存草稿 一键填写 批量设置 【批量发布】│ ← 顶栏不变
├────────────────────────────────────────────────────────────────────┤
│ 视频队列栏（新增，横向滚动）                                          │
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                                    │
│ │ ▶视1 │ │ 视2  │ │ 视3  │ │  ＋  │   共 3 个视频 · 已选账号合计 8 个     │
│ │缩略图│ │缩略图│ │缩略图│ │     │                                    │
│ │文件名│ │文件名│ │文件名│ │添加  │                                    │
│ └─────┘ └─────┘ └─────┘ └─────┘                                    │
├────────────────────────────────────────────────────────────────────┤
│ 左侧账号栏（不变） │ 中间表单区（不变，作用于当前视频） │ 右侧手机预览（不变）│
└────────────────────────────────────────────────────────────────────┘
```

### 2.1 视频队列栏（新组件 `VideoQueueBar.vue`）

- 每个视频一张卡片：**封面缩略图**（无封面时视频首帧/占位图）+ **文件名**（超长省略）+ 状态角标（校验通过 ✓ / 校验失败 ✗ 红 / 未配置 ⚠）+ hover 删除按钮 ×
- 点击卡片切换当前编辑视频（整个表单、账号勾选、平台选中态随之切换）
- 末尾「＋ 添加视频」卡片：打开**多选**上传弹窗（MaterialUploader multiple=true，已支持）
- 队列只有 1 个视频时仍显示（与现状视觉差异最小，多一个"＋"卡片）
- 拖拽排序（el-upload 之外的轻量实现，或二期；MVP 提供「左移/右移」右键菜单或按钮）

### 2.2 添加视频的行为

每个上传的文件 → 新队列元素：
1. **深拷贝当前视频的完整配置**（含账号选择、平台设置、个性化、定时）——"配好一个，后续一键复制"的核心体验
2. 视频文件写入新元素 `commonConfig.videoLandscape`（沿用现状：方向由素材表 orientation 自动判定）
3. `autoFillTitle` 开启时标题自动填文件名（去扩展名），沿用现有逻辑
4. **自动抽帧**：调现有 `frameApi.extractFrames` → 取推荐帧 → 同时设为该视频的 `coverLandscape` 与 `coverPortrait`（横竖同图，用户可换）
5. 新元素成为当前编辑视频

> 右侧手机面板的「本地上传」按钮保持现状语义：**替换当前视频的文件**（单个）；队列栏「＋」才是**新增**（多个）。

### 2.3 批量发布流程（替换现有"一键发布"按钮行为）

1. 点击「批量发布」→ 对队列**每个视频**跑现有 collect-all 校验（视频/封面/标题/声明/平台字数与时长限制，逐视频汇总）
2. `accountCheckMode === 'pre-publish'` 时，对所选视频的**账号并集**跑一次 PrePublishCheckDialog（cookie 预检）
3. 弹出**批量发布确认弹窗**（新组件，交互模式复用 BatchDraftPublishDialog）：
   - 表格：每行一个视频（缩略图、标题、目标账号数、校验结果）
   - 校验失败行禁选并展示原因；默认勾选全部通过项
   - 底部：已选 X 个视频 · 预计产生 Y 个发布任务（Σ 每视频账号数）
4. 确认 → 一次性 POST 全部勾选视频 → 成功后：
   - 弹窗切换为「已提交」态：成功提交 N 个视频 / M 个任务，失败列表（如有）
   - **已提交的视频从队列移除**；校验未通过未勾选的留在队列继续修
   - 提供跳转按钮「去任务中心查看进度」
5. 进度/结果统一看任务中心（SSE 实时）与发布历史（每视频一个批次卡片）

**删除**：旧 `publishAll()` 前端逐账号循环 + `/postVideo` 轮询、`BatchPublishDialog.vue` 进度弹窗（整条前端轮询链路被任务队列取代；`/postVideo` 接口本身保留，无其他调用方也不动它）。

### 2.4 系统设置页（Settings.vue）

新增分组「批量发布」：
- 「任务间隔（分钟）」数字输入，默认 0，说明文案："发布队列中相邻两个任务的等待时间，0 为连续发布；大于 0 时队列自动切换为串行执行，可降低风控风险"
- 存 `settings` 表 key `batch_task_interval_minutes`（走现有 /api/v2/settings）

## 3. 后端设计

### 3.1 新接口：`POST /api/v2/videos/batch-publish`（ext_api 蓝图）

```
Body:   { "videos": [ <draft_data 结构>, ... ] }     // 数量不限
Resp:   { "code": 200,
          "data": { "task_ids": [...],
                    "failed": [ {"video": 0, "reason": "..."} ],   // 按队列下标
                    "batch_ids": [...] } }                          // 每视频一个
```

处理流程（**逐行对照复用 `drafts/batch-publish` 的实现**）：

```
for video_index, vd in enumerate(videos):
    build draft = { type:'video', draft_data: vd }
    errs = validate_draft_for_publish(draft)          # 复用 draft_merge
    if errs → failed.append(video_index, errs); continue

    for account_id in vd.publishAccountIds:
        查 user_info → merge_config(common, platformDefault, platformOv, accountOv)   # 复用
        追加校验: validate_video_for_platform / validate_title_for_platform
                  / validate_desc_for_platform       # 与 /postVideo 同源，按平台逐账号校验
        payload = build_platform_kwargs(merged, common, account)                     # 复用
        resolve 视频绝对路径（失败 → failed 记录，不开浏览器）
        task = PublishTask(batch_id=uuid4(),          # ★ 每视频独立 batch
                           platform=中文名, platform_type=..., source='batch',
                           max_retries=0, payload=payload, ...)
        task_queue.add_task(task)
```

与草稿批量发布的唯一差异：配置来自请求体而非 drafts 表、source='batch'、无 30 条上限、batch_id 按视频生成。

### 3.2 TaskQueue 间隔支持（`ext_api/task_queue.py`）

- worker 完成一个任务后读设置 `batch_task_interval_minutes`（读 settings 表，缓存 30s）：
  - `> 0`：全局串行锁（interval 模式下只允许 1 个 worker 取任务）+ 任务结束后 `sleep` 指定分钟数，等待期间队列状态 pending 数照常展示
  - `= 0`：维持现状（2 并发连续执行），与草稿批量发布现状一致
- 间隔作用于**整个任务队列**（批量视频发布与草稿批量发布共用队列，风控收益共享）

### 3.3 不改动的部分

- `publish_executor`（/postVideo 链路）原样保留
- 各平台 impl（registry / BasePlatform）零改动
- publish_batches / publish_details 表结构零改动（source 列已存在）
- 发布历史 UI：每视频一个批次卡片，自然按现有逻辑展示

## 4. 涉及文件清单

| 层 | 文件 | 改动 |
|----|------|------|
| 前端 | `views/PublishCenter.vue` | 状态数组化（核心重构）+ 队列栏接入 + 批量发布流程替换 |
| 前端 | `components/VideoQueueBar.vue` | **新建**：视频队列卡片条 |
| 前端 | `components/VideoBatchConfirmDialog.vue` | **新建**：发布确认弹窗（逐视频校验+勾选） |
| 前端 | `components/BatchPublishDialog.vue` | **删除**（前端轮询进度弹窗，被任务中心取代） |
| 前端 | `api/draft.js`（或新 `api/batchPublish.js`） | 加 `batchPublishVideos(videos)` |
| 前端 | `views/Settings.vue` | 加「任务间隔」配置项 |
| 后端 | `ext_api/__init__.py` | 加 `/videos/batch-publish` 路由 |
| 后端 | `ext_api/task_queue.py` | worker 间隔支持（串行锁 + sleep） |
| 后端 | `services/draft_merge.py` | 无结构改动（如需补 batch 校验辅助则小改） |

## 5. 边界与风险

1. **PublishCenter 重构风险（最大项）**：状态代理化必须保证 4 级合并、批量设置、一键填写、抽帧、草稿恢复等现有功能不回归 —— 每步用现有功能清单逐项手工验证 + 现有测试跑通
2. **任务量**：不限视频数 × 每视频账号数 = 任务数可能很大；确认弹窗明确展示"预计 Y 个任务"，用户可见可控
3. **间隔等待期间关后端**：间隔只是 sleep，任务已在 DB（queued/pending），重启后需人工在任务中心重试（与草稿批量发布现状一致，不新增处理）
4. **旧草稿兼容**：v1→v2 只在读取时包装，不迁移写回；保存后自然升级为 v2
5. **素材库批量添加**：MVP 不做（MaterialSelectDialog 仍单选替换当前视频文件），二期加多选模式

## 6. 实施顺序（每步可验证）

1. 后端 `/videos/batch-publish` 路由 + TaskQueue 间隔 → curl 构造 2 视频 × 2 账号请求，验证任务中心出现 4 个任务、批次按视频聚合、间隔生效
2. PublishCenter 状态数组化（先不动 UI，单视频行为回归验证）
3. VideoQueueBar + 添加视频（深拷贝 + 自动标题 + 自动封面）
4. 批量确认弹窗 + 批量发布按钮替换 + 删除旧轮询链路
5. 草稿 v2 保存/恢复/自动保存
6. Settings 间隔项
7. 全功能回归清单逐项过（单视频路径 = 队列 1 项时的所有现有功能）
