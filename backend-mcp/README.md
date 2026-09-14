# Social Auto Upload MCP Service

社交媒体自动上传工具的MCP服务，允许AI客户端通过MCP协议调用系统功能。

## 功能

共 **61 个工具**，覆盖后端全量能力（与网页发布同链路）：

### 平台与自描述（3）
- `platform_list` — 全部平台清单 + 各平台发布配置元数据（声明字段选项/联动规则/定时约束）。**发布前必查**
- `api_catalog` — 枚举后端全部 HTTP API（自动发现新端点）
- `api_call` — 通用 API 调用逃生舱（专用工具未覆盖的新能力直接调用；SSE/浏览器交互端点被禁用）

### 账号管理（13）
- `account_login` / `account_list` / `account_valid_list` / `account_check` / `account_delete`
- `account_sync_profile`（同步昵称头像）/ `account_open_creator_center` / `cookie_download`
- 标签：`tag_list` / `tag_create` / `tag_delete` / `account_tags_set` / `account_tags_batch_add`

### 素材管理（7）
- `material_upload` / `material_list` / `material_get_info`（单查）/ `material_download` / `material_delete` / `material_batch_delete` / `material_probe`（探测时长）

### 视频抽帧（4）
- `frame_extract` / `frames_status` / `frames_list` / `frame_save_cover`（帧 → 4 比例封面）

### 草稿箱（7）
- `draft_list` / `draft_get` / `draft_create` / `draft_delete` / `draft_update` / `draft_batch_publish` / `draft_batch_delete`

### 发布（3）
- `video_publish` — **与网页发布页完全同链路**（`/api/v2/videos/batch-publish`）：多账号一次性发布，
  平台声明字段以 `platform_list` 元数据为准，默认等待发布任务终态（`wait=false` 立即返回 task_ids）
- `video_batch_publish` — 批量发布多个视频（支持 `interval_minutes` 发布间隔链）
- `image_publish` — 图文发布（cookie 路径自动解析）

### 发布辅助查询（9）
- 抖音：`douyin_hotspot_search` / `douyin_music_search` / `douyin_mix_list` / `douyin_activity_list`
- 快手：`kuaishou_music_search`
- 合集：`platform_collections`（B站/微博/公众号/视频号/小红书）
- `alipay_compilation_search` / `toutiao_compilation_search` / `vivo_search_position`

### 任务/历史/设置/日志（13）
- `task_list` / `task_get_status` / `task_cancel` / `task_cancel_batch` / `task_retry` / `task_stream`
- `publish_history` / `history_detail` / `history_delete` / `publish_templates`（一键复用历史配置）
- `publish_stats` / `queue_status`
- `settings_get` / `settings_update` / `changelog_list`

## 自动识别新功能

- 后端 `registry` 注册新平台 → `platform_list` 自动可见（`impl/platform_meta.py` 补充字段元数据）
- 后端新增任何 HTTP 路由 → `api_catalog` 自动可见，`api_call` 可直接调用
- 新能力在被封装为专用工具前，AI 不会失明

## 安装

```bash
npm install
```

## 配置

复制 `.env.example` 为 `.env`，根据需要修改配置：

```env
BACKEND_URL=http://localhost:5409
MCP_PORT=5410
TRANSPORT_MODE=both
DB_PATH=../data/db/database.db
```

## 启动

```bash
# 开发模式
npm run dev

# 生产模式
npm run build
npm start
```

## 使用

### Claude Desktop 配置

在 Claude Desktop 的配置文件中添加：

```json
{
  "mcpServers": {
    "social-auto-upload": {
      "command": "node",
      "args": ["/path/to/backend-mcp/dist/index.js"],
      "env": {
        "TRANSPORT_MODE": "stdio"
      }
    }
  }
}
```

### SSE 模式连接

```bash
# 启动SSE服务
TRANSPORT_MODE=sse npm start

# 连接到 http://localhost:5410/sse
```

## API Token

在系统设置界面配置 MCP API Token，用于认证MCP客户端连接。
