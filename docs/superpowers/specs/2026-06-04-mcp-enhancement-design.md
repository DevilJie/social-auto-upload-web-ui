# backend-mcp 增强 设计文档

## 概述

基于 `MCP-REQUIREMENTS.md`（2026-06-04 用户实测产出）的需求，扩展 `backend-mcp` 服务的能力面。**严格不动 backend 和 frontend 任何代码**——只通过 MCP 这一层穿针引线，把后端 `/api/v2/` 等已有能力包装成对 AI 友好的工具，补齐发布链 + 任务跟踪 + 错误友好化。

## 设计原则

1. **MCP 零侵入**——不改后端、不改前端。复用现有 Flask 端点。
2. **客户端是 AI**——AI 没有持久化文件系统，工具返回的"路径"概念要让位给"素材 ID"和"公开 URL"。
3. **后端能力优先**——发现后端已经实现的能力（任务管理、统计、历史、下载），直接穿 Zod schema 暴露，不重复造轮子。
4. **错误信息友好化**——所有工具返回统一格式的错误码 + 建议 + 可重试标志。

## 范围

### 在范围内（本设计要做）

| 类别 | 工具 | 调用的后端端点 |
|------|------|---------------|
| 素材 | `material_get_info` | `GET /api/materials/list`（按 id 过滤） |
| 素材 | `material_download` | `GET /api/materials/list`（返回 URL） |
| 草稿 | `draft_update` | `PUT /api/v2/drafts/<id>` |
| 任务 | `task_list` | `GET /api/v2/tasks` |
| 任务 | `task_get_status` | `GET /api/v2/tasks/<id>` |
| 任务 | `task_cancel` | `POST /api/v2/tasks/<id>/cancel` |
| 任务 | `task_retry` | `POST /api/v2/tasks/<id>/retry` |
| 任务 | `task_stream` | `GET /api/v2/tasks/stream`（SSE） |
| 发布 | `publish_history` | `GET /api/v2/history` |
| 发布 | `publish_stats` | `GET /api/v2/stats` |
| 发布 | `queue_status` | `GET /api/v2/queue/status` |
| 系统 | `changelog_list` | `GET /api/v2/changelog` |
| 发布 | `video_publish` 接受 `material_id` | MCP 层预处理：id → 查 list 拿 stored_path → 调 `/postVideo` |
| 通用 | 错误响应标准化 | `src/errors.ts` 新增翻译层 |

### 不在范围内（需要后端改造）

| 能力 | 原因 |
|------|------|
| `auto_thumbnail` 自动抽帧 | 后端无 ffmpeg 端点 |
| `material_get_info` 含 width/height/duration | materials 表没存 |
| `video_publish` 后端原生支持 material_id | `/postVideo` 只接 fileList，MCP 在外层包 |
| `video_publish_multi` 多平台并行 | 需后端改架构 |
| `material_download` 实际下载二进制 | AI 客户端无本地 FS，需求弱；只返回 URL 即可 |

## 错误响应格式

**当前（透传 Flask）：**
```json
{ "code": 400, "msg": "缺少必填字段: type", "data": null }
```

**统一后：**
```json
{
  "code": 4001,
  "error": "MISSING_REQUIRED_FIELD",
  "message": "缺少必填字段: type",
  "suggestion": "请在调用时提供 type 参数（1-10 平台 ID）",
  "retryable": false,
  "details": { "field": "type" }
}
```

**字段含义：**
- `code`：MCP 层统一业务码（4xxx = 客户端错误，5xxx = 服务端错误，6xxx = 网络错误）
- `error`：机器可读错误标识（UPPER_SNAKE_CASE）
- `message`：人类可读消息（中文，来自 Flask 的 msg）
- `suggestion`：下一步操作建议（固定文案）
- `retryable`：AI 客户端是否应该自动重试
- `details`：可选上下文（如缺失字段名）

**错误码表：**

| MCP code | error | 触发条件 | suggestion | retryable |
|----------|-------|---------|-----------|-----------|
| 4001 | MISSING_REQUIRED_FIELD | 缺少必填参数 | 检查参数 schema | false |
| 4002 | INVALID_PLATFORM_TYPE | type 不在 1-10 | 使用 1-10 的平台 ID | false |
| 4003 | MATERIAL_NOT_FOUND | material_id 不存在 | 调 material_list 查可用 ID | false |
| 4004 | ACCOUNT_NOT_FOUND | account_id 不存在 | 调 account_list 查可用 ID | false |
| 4005 | DRAFT_NOT_FOUND | 草稿 ID 不存在 | 调 draft_list 查可用 ID | false |
| 4006 | TASK_NOT_FOUND | 任务 ID 不存在 | 调 task_list 查可用 ID | false |
| 4011 | AUTH_FAILED | Cookie 失效或未登录 | 调 account_login 重新登录 | true |
| 4041 | ENDPOINT_NOT_FOUND | Flask 返回 404 | 检查后端版本 | false |
| 4081 | LOGIN_TIMEOUT | login 5 分钟内未完成 | 重试或检查浏览器 | true |
| 5001 | INTERNAL_ERROR | Flask 500 | 查看 logs；如持续请联系管理员 | false |
| 6001 | NETWORK_ERROR | 无法连接 Flask | 检查后端是否在 5409 端口运行 | true |
| 6002 | STREAM_CLOSED | SSE 流意外断开 | 重试调用 | true |

## video_publish material_id 包装方案

**MCP 层做 id → path 转换，不改后端：**

```typescript
// accounts.ts 风格的伪代码
async (params) => {
  let { material_id, fileList, ...rest } = params;

  // 互斥校验
  if (!material_id && !fileList?.length) {
    return error(MISSING_REQUIRED_FIELD, 'material_id 或 fileList 至少二选一');
  }

  // material_id → fileList
  if (material_id) {
    const list = await client.get('/api/materials/list', { page: '1', page_size: '100' });
    const mat = list.data.items.find(m => m.id === material_id);
    if (!mat) return error(MATERIAL_NOT_FOUND, `素材 ${material_id} 不存在`);
    fileList = [mat.stored_path];  // 后端只认 stored_path
  }

  const response = await client.post('/postVideo', { ...rest, fileList });
  return success(response);
}
```

**AI 客户端使用：**
```python
# 之前（需要客户端知道本地路径）
video_publish(type=2, title="...", fileList=["/path/to/video.mp4"], ...)

# 之后（用素材 ID，更符合 AI 心智）
video_publish(type=2, title="...", material_id="cb0c96b9-...", ...)
```

## 目录变化

```
backend-mcp/src/
  errors.ts                       (新增) 错误码 + 翻译函数
  tools/
    materials.ts                  (改) 加 material_get_info / material_download
    drafts.ts                     (改) 加 draft_update
    tasks.ts                      (新增) task_list / get_status / cancel / retry / stream
    publish_extra.ts              (新增) publish_history / publish_stats / queue_status
    publish.ts                    (改) video_publish 接受 material_id
    changelog.ts                  (新增) changelog_list
  server.ts                       (改) 注册新模块

backend-mcp/tests/
  errors.test.ts                  (新增)
  tools/materials.test.ts         (改) 数量从 3 改 5
  tools/drafts.test.ts            (改) 数量从 4 改 5
  tools/tasks.test.ts             (新增) 5 个工具
  tools/publish_extra.test.ts     (新增) 3 个工具
  tools/changelog.test.ts         (新增)
  tools/publish.test.ts           (改) video_publish 新增 material_id 路径测试
```

## 兼容性

- **旧工具不变**——`account_list` / `material_list` / `video_publish(fileList=...)` 等都保留原行为。
- **新参数可选**——`video_publish` 的 `material_id` 是可选参数，传 `fileList` 的旧用法仍能用。
- **错误格式升级**——返回结构新增 `error` / `suggestion` / `retryable` 字段，旧字段 `code` / `msg` 保留。AI 客户端旧解析逻辑不破。

## 验证策略

- **单元测试**（vitest，mock client）——验证工具注册、参数 schema、错误码映射
- **手动 e2e**（用户在 Claude CLI 测）——验证 task_stream SSE 实时推送、material_id 实际能调通
- **构建 + 测试 + 重启 Claude CLI**——每次提交后必须做

## 不在范围

- 任何 backend (Flask) 修改
- 任何 frontend (Vue) 修改
- SSE 多 transport 并存的 bug（用 `TRANSPORT_MODE=stdio` 绕开；架构升级留待将来）
- `SSEServerTransport` 迁移到 `StreamableHTTPServerTransport`（SDK deprecated 提示）
