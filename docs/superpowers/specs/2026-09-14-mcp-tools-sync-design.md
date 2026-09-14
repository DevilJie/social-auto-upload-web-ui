# MCP 工具全量补齐 设计文档（2026-09-14）

## 背景

MCP 服务（`backend-mcp/`）于 **2026-06-04** 上线，此后后端累计 **377 个提交**，
平台从 10 个扩展到 20 个，发布链、账号体系、素材体系均有大改。
MCP 工具面停留在上线初期，存在大量缺口。本文档整理全部变动并给出补齐方案。

## 一、MCP 上线后后端变动全景

### 1. 平台扩张：10 → 20 个（registry.py）

| ID | key | 平台 | 专有发布参数（/postVideo 透传字段） |
|----|-----|------|------------------------------------|
| 11 | weibo | 微博 | videoType(原创/二创/转载)、weiboCategory 级联分类、contentStatement×2、weiboCollection |
| 12 | alipay | 支付宝 | authorStatement、reprintUrl(转载必填)、compilation 合集 |
| 13 | toutiao | 今日头条 | creationDeclaration(7 选)、enableGenerateImage、collection、extendLink/extendLinkUrl |
| 14 | zhihu | 知乎 | creationDeclaration、category 领域、thumbnailLandscape169/Portrait916 次尺寸封面 |
| 15 | csdn | CSDN | recommend |
| 16 | vivo | VIVO | vivoLocationName、vivoDistribution、vivoDeclaration、vivoPrivacy、vivoDownloadPermission |
| 17 | weixin_gzh | 微信公众号 | isOriginal、gzhClaimSource、gzhCollectionName |
| 18 | taobao_guanghe | 淘宝光合 | guangheClaim、guangheLinkType、guangheProducts/Shops |
| 19 | jingmai | 京东京麦 | jdRelatedType、jdProducts、jdNovel、jdDeclaration |
| 21 | dayu | 大鱼号 | creationDeclaration(信息来源 7 选)、dayuRepostUrl(转载必填)、category(43 选)、5 分钟粒度定时 |

> MCP `account_login` / `video_publish` 的 zod 校验仍卡死 `min(1).max(10)`，
> 11 个新平台完全无法通过 MCP 登录/发布。

### 2. 发布链变动

- **`/postVideo` 异步化**（cd19914）：入队后台执行器，立即返回 `{taskId}`；
  需轮询 `/postVideo/status/<task_id>`（queued/running/success/failed）。
  MCP `video_publish` 仍按同步接口等 600 秒。
- **批量视频发布** `/api/v2/videos/batch-publish`（8a2a146 等）：`videos[]` ×
  `publishAccountIds` 逐账号建任务，4 层配置合并（commonConfig → platformConfigs →
  platformOverrides → accountOverrides），支持 `interval_minutes` 发布链调度。
- **草稿批量发布** `/api/v2/drafts/batch-publish`（1-30 个草稿）。
- **图片草稿批量发布** `/api/image-publish/drafts/batch-publish`。
- **发布模板** `/api/v2/publish-templates`（历史成功配置一键复用）。
- **任务批量取消** `/api/v2/tasks/cancel-batch`（616e95e）。
- **B 站** `biliKeepSystemTags` 保留系统标签开关（0dfce9d）、`biliRepostSource` 转载来源。
- **视频号**：关联剧集/公众号文章/红包封面链接（channelsDrama/channelsLink*）、
  视频标注 channelsMarkTag、拍摄信息、位置、活动（多 commit）。

### 3. 账号体系变动

- `/getValidAccounts`：只返回 cookie 有效账号。
- **账号标签**：`/api/tags` GET/POST/DELETE、`/api/accounts/<id>/tags` PUT/GET、
  `/api/accounts/batch/tags` PUT。
- `/uploadCookie` / `/downloadCookie`：cookie 导入导出。
- `/syncProfile`：刷新账号昵称/头像。
- `/openCreatorCenter`：打开创作者中心。
- **账号导入**：`/platforms/import-supported`、`/importAccount`、`/importAccount/stream`（SSE）。
- `/updateUserinfo`：更新账号备注。

### 4. 素材体系变动

- **素材单查** `GET /api/materials/<id>`（MCP 现在还在 list 翻 100 条再过滤的 workaround）。
- **批量删除** `POST /api/materials/batch-delete`。
- **分块上传** `/api/uploads/`（init/chunk/merge/status/delete）。
- **视频抽帧**（frames_bp）：`/api/extract-frames`、`/api/frames-status`、`/api/frames`、
  `/api/frame-image`、`/api/frames/save-cover`（抽帧存封面）、`/api/clear-cache`、`/api/system-info`。
- **素材探测** `POST /api/materials/<id>/probe`（时长/分辨率探测）。

### 5. 辅助查询 blueprint（全部未接 MCP）

- 抖音：`/api/douyin-image/mix-list`（合集）、`activity-list`、`hotspot-search`、
  `music-search`、`search-poi`、`search-miniapp`、`search-game`、`search-mark-spu`、`search-medium`
- 视频号：`/api/channels/collections`、`locations`、`activities`、`drama_picker/*`
- B 站 `/api/bilibili/collections`、微博 `/api/weibo/collections`、
  公众号 `/api/weixin-gzh/collections`、小红书 `/api/xiaohongshu/collections` + `search-poi`
- 快手 `/api/kuaishou-image/music-search`
- 支付宝 `/api/alipay/compilation-search` + `music-list`、头条 `/api/toutiao/compilation-search`
- vivo `/api/vivo/search-position`

### 6. 历史与任务中心变动

- 历史详情 `GET /api/v2/history/<batch_id>`、历史删除 `DELETE /api/v2/history/<batch_id>` /
  `DELETE /api/v2/history/batch`（多条）。
- 草稿批量删除 `DELETE /api/v2/drafts/batch`。
- 孤儿任务清理、真取消（a763b81/f25020e）。

### 7. 其他

- `/api/health`、反馈 `/api/feedback/list|submit|vote`、`/api/image-proxy`。

## 二、现有 25 个 MCP 工具 vs 缺口

| 模块 | 已有工具 | 状态 |
|------|---------|------|
| accounts(4) | login/list/check/delete | login 平台上限 10 ❌；缺 valid_list/sync/open_creator/标签/cookie 导入导出/导入 |
| materials(5) | upload/list/delete/get_info/download | get_info/download 应用单查接口 ❌；缺 batch_delete/probe/抽帧 |
| drafts(5) | list/get/create/delete/update | 缺 batch_publish/batch_delete |
| publish(2) | video_publish/image_publish | 平台上限 10 ❌、缺 11 平台字段 ❌、未适配异步化 ❌；缺批量发布 |
| publish_extra(3) | history/stats/queue_status | history 平台列表过时；缺 history_detail/history_delete/publish_templates |
| tasks(5) | list/get_status/cancel/retry/stream | 缺 cancel_batch |
| settings(2) | get/update | OK |
| changelog(1) | list | OK |

## 三、方案

### A. 平台元数据后端化（自动识别新平台的核心）

后端新增 `GET /api/v2/platforms`：从 `impl.registry` 自动枚举平台（id/key/name），
附发布字段元数据（声明字段选项、联动规则、定时粒度等，数据源从前端
`frontend/src/config/platforms.js` 结构化迁入后端，前端后续改为消费同一份数据）。

- MCP `platform_list` 工具透传该端点 → **后端注册新平台，MCP 自动可见**。
- `video_publish` 等工具的平台上限校验改为运行时从该端点获取（启动时缓存 + 拉取失败回落内置表）。

### B. API 目录自省 + 通用调用（自动识别新端点的兜底）

- 后端新增 `GET /api/v2/api-catalog`：Flask `app.url_map` 自省，
  自动枚举全部路由（path/methods/docstring）→ **后端加任何新路由，MCP 立即可见**。
- MCP 新增 `api_catalog`（查目录）+ `api_call`（逃生舱：按目录直接调用后端端点）。
  安全边界：MCP 已有 token 认证；`api_call` 黑名单排除 SSE/登录/静态资源路径。

### C. 显式工具补齐（AI 友好的高质量封装）

1. **发布链**
   - `video_publish`：平台放开至全部；补 11 个新平台声明字段；适配异步化
     （默认轮询 `/postVideo/status` 到终态，`wait=false` 立即返回 taskId）。
   - `video_batch_publish`（对接 `/api/v2/videos/batch-publish`）。
   - `draft_batch_publish` / `draft_batch_delete`。
   - `publish_templates`。
2. **任务/历史**
   - `task_cancel_batch`、`history_detail`、`history_delete`。
3. **账号**
   - `account_valid_list`、`account_sync_profile`、`account_open_creator`、
     `tag_list/tag_create/tag_delete/account_tag_set`、`cookie_upload/cookie_download`。
4. **素材**
   - `material_get_info`/`material_download` 改用单查端点；
     `material_batch_delete`、`material_probe`（时长/分辨率）、抽帧
     `frame_extract/frames_list/frame_save_cover`。
5. **辅助查询（高频）**
   - `douyin_hotspot_search`、`douyin_music_search`、`douyin_mix_list`、
     `platform_collections`（B站/微博/公众号/视频号/小红书/支付宝/头条合集统一入口）。

### D. 不做的事

- 交互式 picker 类端点（taobao_guanghe picker、jd picker、channels drama_picker、
  douyin search-* 其余部分）：需要打开浏览器人机交互，不适合 MCP 封装，
  由 `api_call` 逃生舱兜底。
- 反馈类、image-proxy、静态资源：同上。
- 分块上传（MCP 侧无大文件流式需求，material_upload 已覆盖）。

## 四、测试与验收

- 每个 MCP 工具模块补 vitest（工具注册数 + 参数 schema + 后端路径断言）。
- `npm run build` + `npm test` 通过。
- 后端新增端点补 pytest（platforms/api-catalog 自省正确性）。
