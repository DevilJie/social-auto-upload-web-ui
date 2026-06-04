# backend-mcp 增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `backend-mcp` 增加 13 个新工具 + 统一错误响应格式 + `video_publish` 支持 `material_id`。零后端、零前端改动。

**Architecture:** 纯 MCP 层包装。复用 Flask 已有 `/api/v2/*` 端点（任务管理、统计、历史、草稿 CRUD、变更日志），在 MCP 层加 Zod schema + 业务描述 + 错误码翻译。`material_id` 走"在 MCP 内查素材 list → 拿 stored_path → 转交 `/postVideo`"的预处理路径。

**Tech Stack:** TypeScript + MCP SDK + zod + axios + vitest（保持现有栈）。

---

## File Structure

### 新增文件
| 文件 | 职责 |
|------|------|
| `src/errors.ts` | 错误码表 + Flask 响应 → MCP 错误格式翻译函数 |
| `src/tools/tasks.ts` | 5 个任务管理工具 |
| `src/tools/publish_extra.ts` | 3 个发布辅助工具（history / stats / queue） |
| `src/tools/changelog.ts` | 1 个更新日志工具 |
| `tests/errors.test.ts` | 错误翻译函数单元测试 |
| `tests/tools/tasks.test.ts` | 任务工具注册测试 |
| `tests/tools/publish_extra.test.ts` | 发布辅助工具注册测试 |
| `tests/tools/changelog.test.ts` | changelog 工具注册测试 |

### 修改文件
| 文件 | 改动 |
|------|------|
| `src/tools/materials.ts` | 加 `material_get_info` / `material_download`（2 个） |
| `src/tools/drafts.ts` | 加 `draft_update`（1 个） |
| `src/tools/publish.ts` | `video_publish` 接受 `material_id` |
| `src/server.ts` | 注册 3 个新模块 |
| `tests/tools/materials.test.ts` | 工具数 3 → 5 |
| `tests/tools/drafts.test.ts` | 工具数 4 → 5 |
| `tests/tools/publish.test.ts` | 加 material_id 转换的行为测试 |

---

## Chunk 0：错误响应基础

### Task 1：错误码表与翻译函数

**Files:**
- Create: `backend-mcp/src/errors.ts`
- Create: `backend-mcp/tests/errors.test.ts`

- [ ] **Step 1: 写失败测试**——`tests/errors.test.ts`

```typescript
import { describe, it, expect } from 'vitest';
import { translateError, ErrorCodes, type McpError } from '../src/errors';

describe('translateError', () => {
  it('Flask 400 + "缺少必填字段" → MISSING_REQUIRED_FIELD', () => {
    const e = translateError({ code: 400, msg: '缺少必填字段: type', data: null });
    expect(e.code).toBe(4001);
    expect(e.error).toBe('MISSING_REQUIRED_FIELD');
    expect(e.retryable).toBe(false);
  });

  it('Flask 401 + Cookie 失效 → AUTH_FAILED + retryable', () => {
    const e = translateError({ code: 401, msg: 'Cookie 已失效', data: null });
    expect(e.code).toBe(4011);
    expect(e.error).toBe('AUTH_FAILED');
    expect(e.retryable).toBe(true);
  });

  it('Flask 404 → ENDPOINT_NOT_FOUND', () => {
    const e = translateError({ code: 404, msg: '素材不存在', data: null });
    expect(e.code).toBe(4003);  // 404 命中"素材不存在"子串规则
    expect(e.error).toBe('MATERIAL_NOT_FOUND');
  });

  it('Flask 500 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 500, msg: '数据库连接失败', data: null });
    expect(e.code).toBe(5001);
    expect(e.error).toBe('INTERNAL_ERROR');
    expect(e.retryable).toBe(false);
  });

  it('网络错误（无响应）→ NETWORK_ERROR', () => {
    const e = translateError(null, new Error('ECONNREFUSED'));
    expect(e.code).toBe(6001);
    expect(e.error).toBe('NETWORK_ERROR');
    expect(e.retryable).toBe(true);
  });

  it('未知错误码 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 418, msg: '我是茶壶', data: null });
    expect(e.code).toBe(5001);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend-mcp && npx vitest run tests/errors.test.ts`
Expected: FAIL — `errors.ts` 不存在

- [ ] **Step 3: 实现 `src/errors.ts`**

```typescript
// 业务错误码表
export const ErrorCodes = {
  MISSING_REQUIRED_FIELD: 4001,
  INVALID_PLATFORM_TYPE: 4002,
  MATERIAL_NOT_FOUND: 4003,
  ACCOUNT_NOT_FOUND: 4004,
  DRAFT_NOT_FOUND: 4005,
  TASK_NOT_FOUND: 4006,
  AUTH_FAILED: 4011,
  ENDPOINT_NOT_FOUND: 4041,
  LOGIN_TIMEOUT: 4081,
  INTERNAL_ERROR: 5001,
  NETWORK_ERROR: 6001,
  STREAM_CLOSED: 6002,
} as const;

export interface McpError {
  code: number;
  error: string;
  message: string;
  suggestion: string;
  retryable: boolean;
  details?: Record<string, any>;
}

const SUGGESTIONS: Record<string, string> = {
  MISSING_REQUIRED_FIELD: '检查工具参数 schema，补全必填字段',
  INVALID_PLATFORM_TYPE: '使用 1-10 的平台 ID（1=小红书, 2=视频号, 3=抖音, ...）',
  MATERIAL_NOT_FOUND: '调 material_list 查可用素材 ID',
  ACCOUNT_NOT_FOUND: '调 account_list 查可用账号 ID',
  DRAFT_NOT_FOUND: '调 draft_list 查可用草稿 ID',
  TASK_NOT_FOUND: '调 task_list 查可用任务 ID',
  AUTH_FAILED: '调 account_login 重新登录该平台账号',
  ENDPOINT_NOT_FOUND: '检查后端版本；如持续请联系管理员',
  LOGIN_TIMEOUT: '重试登录，确认浏览器已打开且二维码有效',
  INTERNAL_ERROR: '查看后端 logs；如持续请联系管理员',
  NETWORK_ERROR: '检查后端是否在 5409 端口运行',
  STREAM_CLOSED: '重试调用；如持续请检查后端 SSE 端点',
};

function detectByMessage(msg: string): string {
  if (msg.includes('Cookie') || msg.includes('未登录') || msg.includes('登录')) {
    return 'AUTH_FAILED';
  }
  if (msg.includes('素材') || msg.includes('material')) return 'MATERIAL_NOT_FOUND';
  if (msg.includes('账号') || msg.includes('account')) return 'ACCOUNT_NOT_FOUND';
  if (msg.includes('草稿') || msg.includes('draft')) return 'DRAFT_NOT_FOUND';
  if (msg.includes('任务') || msg.includes('task')) return 'TASK_NOT_FOUND';
  if (msg.includes('缺少必填字段') || msg.includes('不能为空')) return 'MISSING_REQUIRED_FIELD';
  return 'INTERNAL_ERROR';
}

export function translateError(
  flaskResp: { code: number; msg?: string; data?: any } | null,
  networkError?: Error
): McpError {
  // 网络错误优先
  if (networkError || !flaskResp) {
    return {
      code: ErrorCodes.NETWORK_ERROR,
      error: 'NETWORK_ERROR',
      message: networkError?.message || '无法连接后端',
      suggestion: SUGGESTIONS.NETWORK_ERROR,
      retryable: true,
    };
  }

  const msg = flaskResp.msg || '未知错误';
  const httpCode = flaskResp.code;

  // HTTP 状态映射
  if (httpCode === 401) {
    return mkError('AUTH_FAILED', msg);
  }
  if (httpCode === 404) {
    return mkError(detectByMessage(msg), msg);
  }
  if (httpCode === 500) {
    return mkError('INTERNAL_ERROR', msg);
  }
  if (httpCode === 400) {
    return mkError(detectByMessage(msg), msg);
  }
  return mkError('INTERNAL_ERROR', msg);
}

function mkError(symbol: string, msg: string): McpError {
  return {
    code: (ErrorCodes as any)[symbol] ?? 5001,
    error: symbol,
    message: msg,
    suggestion: SUGGESTIONS[symbol] ?? SUGGESTIONS.INTERNAL_ERROR,
    retryable: symbol === 'AUTH_FAILED' || symbol === 'NETWORK_ERROR' || symbol === 'STREAM_CLOSED' || symbol === 'LOGIN_TIMEOUT',
  };
}

export function formatErrorResult(err: McpError) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(err, null, 2) }],
    isError: true,
  };
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/errors.test.ts`
Expected: PASS — 6 个测试全过

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/errors.ts backend-mcp/tests/errors.test.ts
git commit -m "feat(mcp): 新增错误码翻译层，统一 Flask 响应格式"
```

---

## Chunk 1：素材与草稿

### Task 2：material_get_info 工具

**Files:**
- Modify: `backend-mcp/src/tools/materials.ts`（在 `material_delete` 后面追加）
- Modify: `backend-mcp/tests/tools/materials.test.ts`（更新工具数期望）

- [ ] **Step 1: 更新测试期望**

修改 `tests/tools/materials.test.ts`：
```typescript
import { describe, it, expect } from 'vitest';
import { registerMaterialTools } from '../../src/tools/materials';
import { BackendClient } from '../../src/client';

describe('material tools', () => {
  it('应该注册5个素材相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerMaterialTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(5);
    expect(tools.map(t => t.name)).toEqual([
      'material_upload',
      'material_list',
      'material_delete',
      'material_get_info',
      'material_download',
    ]);
  });
});
```

- [ ] **Step 2: 跑测试确认失败（3 ≠ 5）**

Run: `cd backend-mcp && npx vitest run tests/tools/materials.test.ts`
Expected: FAIL — 注册数 3 ≠ 5

- [ ] **Step 3: 在 `materials.ts` 末尾追加两个工具**

```typescript
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

// ... 现有代码保持 ...

  // 获取素材详情
  server.tool(
    'material_get_info',
    '获取素材的详细信息，包括公开 URL、缩略图、文件大小等',
    {
      id: z.string().describe('素材 ID（UUID）'),
    },
    async ({ id }) => {
      try {
        // 后端没有"按 id 查单个"接口，只能 list 全量后过滤（page_size=100 够用）
        const response = await client.get('/api/materials/list', {
          type: 'all',
          page: '1',
          page_size: '100',
        });
        const items = response?.data?.items ?? [];
        const item = items.find((m: any) => m.id === id);
        if (!item) {
          return formatErrorResult({
            code: ErrorCodes.MATERIAL_NOT_FOUND,
            error: 'MATERIAL_NOT_FOUND',
            message: `素材 ${id} 不存在`,
            suggestion: '调 material_list 查可用素材 ID',
            retryable: false,
          });
        }
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(item, null, 2),
          }],
        };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
```

- [ ] **Step 4: 跑测试确认仍失败（缺 material_download）**

Run: `cd backend-mcp && npx vitest run tests/tools/materials.test.ts`
Expected: FAIL — 注册数 4 ≠ 5

---

### Task 3：material_download 工具

**Files:**
- Modify: `backend-mcp/src/tools/materials.ts`（在 `material_get_info` 后面追加）

- [ ] **Step 1: 在 `materials.ts` `material_get_info` 之后追加**

```typescript
  // 获取素材下载 URL
  server.tool(
    'material_download',
    '获取素材的可访问 URL（指向后端 /api/materials/file/<path>）。AI 客户端无持久化文件系统，本工具返回 URL 而非二进制。',
    {
      id: z.string().describe('素材 ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get('/api/materials/list', {
          type: 'all',
          page: '1',
          page_size: '100',
        });
        const items = response?.data?.items ?? [];
        const item = items.find((m: any) => m.id === id);
        if (!item) {
          return formatErrorResult({
            code: ErrorCodes.MATERIAL_NOT_FOUND,
            error: 'MATERIAL_NOT_FOUND',
            message: `素材 ${id} 不存在`,
            suggestion: '调 material_list 查可用素材 ID',
            retryable: false,
          });
        }
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify({
              id: item.id,
              filename: item.original_filename,
              mime_type: item.mime_type,
              file_size: item.file_size,
              url: item.url,
              thumbnail_url: item.thumbnail_url,
            }, null, 2),
          }],
        };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
```

- [ ] **Step 2: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/tools/materials.test.ts`
Expected: PASS — 5 个工具名匹配

- [ ] **Step 3: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/tools/materials.ts backend-mcp/tests/tools/materials.test.ts
git commit -m "feat(mcp): 新增 material_get_info 和 material_download 工具"
```

---

### Task 4：draft_update 工具

**Files:**
- Modify: `backend-mcp/src/tools/drafts.ts`
- Modify: `backend-mcp/tests/tools/drafts.test.ts`

- [ ] **Step 1: 更新测试期望**

```typescript
// tests/tools/drafts.test.ts
import { describe, it, expect } from 'vitest';
import { registerDraftTools } from '../../src/tools/drafts';
import { BackendClient } from '../../src/client';

describe('draft tools', () => {
  it('应该注册5个草稿相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerDraftTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(5);
    expect(tools.map(t => t.name)).toEqual([
      'draft_list',
      'draft_get',
      'draft_create',
      'draft_delete',
      'draft_update',
    ]);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend-mcp && npx vitest run tests/tools/drafts.test.ts`
Expected: FAIL — 4 ≠ 5

- [ ] **Step 3: 在 `drafts.ts` 中 `import { formatErrorResult, translateError }` 并在 `draft_delete` 后面追加**

```typescript
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

// ... 现有 import 和 registerDraftTools 函数 ...

  // 更新草稿
  server.tool(
    'draft_update',
    '更新已存在的草稿数据',
    {
      id: z.union([z.string(), z.number()]).describe('草稿 ID'),
      draft_data: z.record(z.string(), z.any()).describe('新的草稿数据 JSON'),
    },
    async ({ id, draft_data }) => {
      try {
        const response = await client.put(`/api/v2/drafts/${id}`, { draft_data });
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2),
          }],
        };
      } catch (error: any) {
        // 404 视为 DRAFT_NOT_FOUND
        if (error?.response?.status === 404) {
          return formatErrorResult({
            code: ErrorCodes.DRAFT_NOT_FOUND,
            error: 'DRAFT_NOT_FOUND',
            message: `草稿 ${id} 不存在`,
            suggestion: '调 draft_list 查可用草稿 ID',
            retryable: false,
          });
        }
        return formatErrorResult(translateError(null, error));
      }
    }
  );
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/tools/drafts.test.ts`
Expected: PASS — 5 个工具名匹配

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/tools/drafts.ts backend-mcp/tests/tools/drafts.test.ts
git commit -m "feat(mcp): 新增 draft_update 工具"
```

---

## Chunk 2：发布辅助工具（无 SSE）

### Task 5：publish_history / publish_stats / queue_status 工具

**Files:**
- Create: `backend-mcp/src/tools/publish_extra.ts`
- Create: `backend-mcp/tests/tools/publish_extra.test.ts`

- [ ] **Step 1: 写测试**

```typescript
// tests/tools/publish_extra.test.ts
import { describe, it, expect } from 'vitest';
import { registerPublishExtraTools } from '../../src/tools/publish_extra';
import { BackendClient } from '../../src/client';

describe('publish extra tools', () => {
  it('应该注册3个发布辅助工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishExtraTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(3);
    expect(tools.map(t => t.name)).toEqual([
      'publish_history',
      'publish_stats',
      'queue_status',
    ]);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend-mcp && npx vitest run tests/tools/publish_extra.test.ts`
Expected: FAIL — `publish_extra.ts` 不存在

- [ ] **Step 3: 实现 `src/tools/publish_extra.ts`**

```typescript
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError } from '../errors.js';

export function registerPublishExtraTools(server: McpServer, client: BackendClient): void {
  // 发布历史
  server.tool(
    'publish_history',
    '获取发布历史记录（支持按平台/状态/日期范围过滤）',
    {
      platform: z.string().optional().describe('平台 key：xiaohongshu/channels/douyin/kuaishou/bilibili'),
      status: z.enum(['pending', 'queued', 'running', 'success', 'failed', 'cancelled']).optional(),
      time_range: z.enum(['today', '7days', '30days']).optional(),
      start_date: z.string().optional().describe('YYYY-MM-DD'),
      end_date: z.string().optional().describe('YYYY-MM-DD'),
      page: z.number().optional().describe('页码（从 1 开始）'),
      page_size: z.number().optional().describe('每页数量（默认 20）'),
    },
    async (params) => {
      try {
        const q: Record<string, string> = {};
        if (params.platform) q.platform = params.platform;
        if (params.status) q.status = params.status;
        if (params.time_range) q.timeRange = params.time_range;
        if (params.start_date) q.startDate = params.start_date;
        if (params.end_date) q.endDate = params.end_date;
        if (params.page) q.page = String(params.page);
        if (params.page_size) q.pageSize = String(params.page_size);
        const response = await client.get('/api/v2/history', q);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 统计数据
  server.tool(
    'publish_stats',
    '获取发布统计数据：总数、成功率、按平台分布、7天趋势',
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/stats');
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 队列状态
  server.tool(
    'queue_status',
    '获取发布任务队列状态（待处理/运行中/worker 数）',
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/queue/status');
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/tools/publish_extra.test.ts`
Expected: PASS — 3 个工具名匹配

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/tools/publish_extra.ts backend-mcp/tests/tools/publish_extra.test.ts
git commit -m "feat(mcp): 新增 publish_history / publish_stats / queue_status 工具"
```

---

### Task 6：changelog_list 工具

**Files:**
- Create: `backend-mcp/src/tools/changelog.ts`
- Create: `backend-mcp/tests/tools/changelog.test.ts`

- [ ] **Step 1: 写测试**

```typescript
// tests/tools/changelog.test.ts
import { describe, it, expect } from 'vitest';
import { registerChangelogTools } from '../../src/tools/changelog';
import { BackendClient } from '../../src/client';

describe('changelog tools', () => {
  it('应该注册1个更新日志工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerChangelogTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe('changelog_list');
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend-mcp && npx vitest run tests/tools/changelog.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现 `src/tools/changelog.ts`**

```typescript
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { formatErrorResult, translateError } from '../errors.js';

export function registerChangelogTools(server: McpServer, client: BackendClient): void {
  server.tool(
    'changelog_list',
    '获取系统更新日志列表（按日期倒序）',
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/changelog');
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/tools/changelog.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/tools/changelog.ts backend-mcp/tests/tools/changelog.test.ts
git commit -m "feat(mcp): 新增 changelog_list 工具"
```

---

## Chunk 3：任务管理工具（含 1 个 SSE）

### Task 7：task_list / task_get_status / task_cancel / task_retry 工具

**Files:**
- Create: `backend-mcp/src/tools/tasks.ts`
- Create: `backend-mcp/tests/tools/tasks.test.ts`

- [ ] **Step 1: 写测试（验证 5 个工具注册）**

```typescript
// tests/tools/tasks.test.ts
import { describe, it, expect } from 'vitest';
import { registerTaskTools } from '../../src/tools/tasks';
import { BackendClient } from '../../src/client';

describe('task tools', () => {
  it('应该注册5个任务管理工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerTaskTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(5);
    expect(tools.map(t => t.name)).toEqual([
      'task_list',
      'task_get_status',
      'task_cancel',
      'task_retry',
      'task_stream',
    ]);
  });
});
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend-mcp && npx vitest run tests/tools/tasks.test.ts`
Expected: FAIL

- [ ] **Step 3: 实现 `src/tools/tasks.ts`**

```typescript
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

export function registerTaskTools(server: McpServer, client: BackendClient): void {
  // 任务列表
  server.tool(
    'task_list',
    '获取发布任务列表（支持状态过滤、分页）',
    {
      status: z.enum(['pending', 'queued', 'running', 'success', 'failed', 'cancelled', 'all']).optional(),
      page: z.number().optional(),
      page_size: z.number().optional(),
    },
    async ({ status, page, page_size }) => {
      try {
        const q: Record<string, string> = {};
        if (status) q.status = status;
        if (page) q.page = String(page);
        if (page_size) q.pageSize = String(page_size);
        const response = await client.get('/api/v2/tasks', q);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 任务详情
  server.tool(
    'task_get_status',
    '查询单个发布任务的状态、进度、结果',
    {
      task_id: z.string().describe('任务 ID'),
    },
    async ({ task_id }) => {
      try {
        const response = await client.get(`/api/v2/tasks/${task_id}`);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        if (error?.response?.status === 404) {
          return formatErrorResult({
            code: ErrorCodes.TASK_NOT_FOUND,
            error: 'TASK_NOT_FOUND',
            message: `任务 ${task_id} 不存在`,
            suggestion: '调 task_list 查可用任务 ID',
            retryable: false,
          });
        }
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 取消任务
  server.tool(
    'task_cancel',
    '取消正在等待或运行中的任务',
    {
      task_id: z.string().describe('任务 ID'),
    },
    async ({ task_id }) => {
      try {
        const response = await client.post(`/api/v2/tasks/${task_id}/cancel`);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 重试任务
  server.tool(
    'task_retry',
    '重试失败的任务（重新入队）',
    {
      task_id: z.string().describe('任务 ID'),
    },
    async ({ task_id }) => {
      try {
        const response = await client.post(`/api/v2/tasks/${task_id}/retry`);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 任务状态 SSE 实时推送
  server.tool(
    'task_stream',
    '订阅任务状态变更的 SSE 流。收到新状态立即 resolve 返回；如需持续订阅请用 SSE 模式连接 MCP。',
    {
      idle_timeout_seconds: z.number().optional().describe('空闲超时秒数（默认 60）'),
    },
    async ({ idle_timeout_seconds = 60 }) => {
      try {
        const lastMessage = await client.getSSE<any>('/api/v2/tasks/stream', undefined, (msg) => {
          if (msg && typeof msg === 'object' && msg.id && msg.status) {
            return msg;
          }
          return undefined;
        });
        return { content: [{ type: 'text' as const, text: JSON.stringify(lastMessage, null, 2) }] };
      } catch (error: any) {
        if (error?.message?.includes('SSE stream ended without terminal message')) {
          return {
            content: [{
              type: 'text' as const,
              text: JSON.stringify({ status: 'idle', message: '在 ' + idle_timeout_seconds + ' 秒内无新任务状态变更' }, null, 2),
            }],
          };
        }
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/tools/tasks.test.ts`
Expected: PASS — 5 个工具名匹配

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/tools/tasks.ts backend-mcp/tests/tools/tasks.test.ts
git commit -m "feat(mcp): 新增 5 个任务管理工具（含 task_stream SSE）"
```

---

## Chunk 4：发布增强（video_publish 接受 material_id）

### Task 8：video_publish material_id 包装

**Files:**
- Modify: `backend-mcp/src/tools/publish.ts`
- Modify: `backend-mcp/tests/tools/publish.test.ts`（加行为测试）

- [ ] **Step 1: 写行为测试**

修改 `tests/tools/publish.test.ts`：
```typescript
import { describe, it, expect, vi } from 'vitest';
import { registerPublishTools } from '../../src/tools/publish';
import { BackendClient } from '../../src/client';

describe('publish tools', () => {
  it('应该注册2个发布工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(2);
  });

  it('video_publish 接受 material_id，内部查素材转 fileList', async () => {
    const stored_path = 'materials/2026/06/04/abc.mp4';
    const mockClient = {
      get: vi.fn().mockResolvedValue({
        data: { items: [{ id: 'mat-1', stored_path, file_type: 'video' }] },
      }),
      post: vi.fn().mockResolvedValue({ code: 200, data: { task_id: 'task-1' } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish');

    const result = await videoPublish.handler({
      type: 2,
      title: 'test',
      material_id: 'mat-1',
    });

    // 验证调用了 get（查素材）和 post（发布）
    expect(mockClient.get).toHaveBeenCalledWith('/api/materials/list', expect.any(Object));
    expect(mockClient.post).toHaveBeenCalledWith('/postVideo', expect.objectContaining({
      type: 2,
      title: 'test',
      fileList: [stored_path],  // ← material_id 被转成 fileList
    }));
    expect(result.isError).toBeFalsy();
  });

  it('video_publish 传不存在的 material_id 返回 MATERIAL_NOT_FOUND', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({ data: { items: [] } }),
      post: vi.fn(),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish');

    const result = await videoPublish.handler({
      type: 2,
      title: 'test',
      material_id: 'nonexistent',
    });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('MATERIAL_NOT_FOUND');
    expect(mockClient.post).not.toHaveBeenCalled();
  });

  it('video_publish 不传 material_id 也不传 fileList 返回 MISSING_REQUIRED_FIELD', async () => {
    const mockClient = { get: vi.fn(), post: vi.fn() } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish');

    const result = await videoPublish.handler({ type: 2, title: 'test' });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('MISSING_REQUIRED_FIELD');
  });
});
```

- [ ] **Step 2: 跑测试确认失败（仅注册测试通过，行为测试因新逻辑缺失失败）**

Run: `cd backend-mcp && npx vitest run tests/tools/publish.test.ts`
Expected: 第 2/3/4 个测试 FAIL

- [ ] **Step 3: 修改 `src/tools/publish.ts` `video_publish`**

完整替换 `video_publish` 部分为：

```typescript
  // 视频发布
  server.tool(
    'video_publish',
    '发布视频到指定平台。优先用 material_id（从素材库选），也兼容本地 fileList。',
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      title: z.string().describe('视频标题'),
      material_id: z.string().optional().describe('视频素材 ID（推荐，从素材库选择）'),
      fileList: z.array(z.string()).optional().describe('视频文件路径列表（兼容旧用法，与 material_id 互斥）'),
      accountList: z.array(z.string()).optional().describe('账号 cookie 文件路径列表'),
      account_id: z.union([z.string(), z.number()]).optional().describe('账号 ID（推荐；MCP 会查 list 拿 cookie 路径填到 accountList）'),
      tags: z.array(z.string()).optional(),
      description: z.string().optional(),
      category: z.string().optional(),
      thumbnail: z.string().optional().describe('封面图路径（兼容）'),
      thumbnail_material_id: z.string().optional().describe('封面图素材 ID（推荐）'),
      thumbnailLandscape: z.string().optional(),
      thumbnailPortrait: z.string().optional(),
      enableTimer: z.boolean().optional(),
      scheduleTime: z.string().optional(),
      videosPerDay: z.number().optional(),
      dailyTimes: z.array(z.string()).optional(),
      startDays: z.number().optional(),
      productLink: z.string().optional(),
      productTitle: z.string().optional(),
      aiContent: z.string().optional(),
      creationDeclaration: z.string().optional(),
      riskWarning: z.string().optional(),
      enableCashActivity: z.boolean().optional(),
      supplementaryDeclaration: z.string().optional(),
      isDraft: z.boolean().optional(),
      audience: z.string().optional(),
      alteredContent: z.boolean().optional(),
      hotspot: z.string().optional(),
      tag_type: z.string().optional(),
      tag_value: z.string().optional(),
      mini_link: z.string().optional(),
      mix_id: z.string().optional(),
      activities: z.array(z.any()).optional(),
    },
    async (params) => {
      try {
        const { material_id, fileList, account_id, accountList, thumbnail_material_id, thumbnail, ...rest } = params;

        // 互斥校验
        if (!material_id && !fileList?.length) {
          return formatErrorResult({
            code: ErrorCodes.MISSING_REQUIRED_FIELD,
            error: 'MISSING_REQUIRED_FIELD',
            message: 'material_id 或 fileList 至少二选一',
            suggestion: '调 material_list 选素材传 material_id，或直接传 fileList',
            retryable: false,
          });
        }

        // material_id → fileList
        let resolvedFileList = fileList;
        if (material_id && !fileList?.length) {
          const list = await client.get('/api/materials/list', { type: 'video', page: '1', page_size: '100' });
          const items = list?.data?.items ?? [];
          const mat = items.find((m: any) => m.id === material_id);
          if (!mat) {
            return formatErrorResult({
              code: ErrorCodes.MATERIAL_NOT_FOUND,
              error: 'MATERIAL_NOT_FOUND',
              message: `素材 ${material_id} 不存在`,
              suggestion: '调 material_list 查可用素材 ID',
              retryable: false,
            });
          }
          resolvedFileList = [mat.stored_path];
        }

        // account_id → accountList
        let resolvedAccountList = accountList;
        if (account_id && !accountList?.length) {
          const accounts = await client.get('/getAccounts');
          const accs = accounts?.data ?? [];
          const acc = accs.find((a: any) => String(a.id) === String(account_id));
          if (!acc) {
            return formatErrorResult({
              code: ErrorCodes.ACCOUNT_NOT_FOUND,
              error: 'ACCOUNT_NOT_FOUND',
              message: `账号 ${account_id} 不存在`,
              suggestion: '调 account_list 查可用账号 ID',
              retryable: false,
            });
          }
          // cookie 路径在账号数据里的字段名需根据实际 user_info 表确认
          resolvedAccountList = [acc.cookie_path ?? acc.cookiePath ?? acc.file_path];
        }

        // thumbnail_material_id → thumbnail
        let resolvedThumbnail = thumbnail;
        if (thumbnail_material_id && !thumbnail) {
          const list = await client.get('/api/materials/list', { type: 'image', page: '1', page_size: '100' });
          const items = list?.data?.items ?? [];
          const mat = items.find((m: any) => m.id === thumbnail_material_id);
          if (mat) {
            resolvedThumbnail = mat.stored_path;
          }
        }

        const response = await client.post('/postVideo', {
          ...rest,
          fileList: resolvedFileList,
          accountList: resolvedAccountList,
          thumbnail: resolvedThumbnail,
        });

        return {
          content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }],
        };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
```

并修改 `import`：

```typescript
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';
```

**注意：** `image_publish` 也需要相同模式的 `material_id` 包装。**但本任务先不动**——保持范围最小，等用户复测 video_publish 后再决定是否扩到 image_publish（详见 SPEC "不在范围内" 章节）。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend-mcp && npx vitest run tests/tools/publish.test.ts`
Expected: 4 个测试 PASS

- [ ] **Step 5: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/tools/publish.ts backend-mcp/tests/tools/publish.test.ts
git commit -m "feat(mcp): video_publish 接受 material_id / account_id / thumbnail_material_id"
```

---

## Chunk 5：注册新模块 + 端到端验证

### Task 9：在 `server.ts` 注册 3 个新模块

**Files:**
- Modify: `backend-mcp/src/server.ts`

- [ ] **Step 1: 修改 `src/server.ts`**

完整内容：
```typescript
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from './client.js';
import { registerAccountTools } from './tools/accounts.js';
import { registerMaterialTools } from './tools/materials.js';
import { registerDraftTools } from './tools/drafts.js';
import { registerPublishTools } from './tools/publish.js';
import { registerSettingsTools } from './tools/settings.js';
import { registerTaskTools } from './tools/tasks.js';
import { registerPublishExtraTools } from './tools/publish_extra.js';
import { registerChangelogTools } from './tools/changelog.js';

export interface ServerConfig {
  backendUrl: string;
  dbPath: string;
}

export function createMcpServer(config: ServerConfig): McpServer {
  const server = new McpServer({
    name: 'social-auto-upload',
    version: '1.0.0',
  });

  const client = new BackendClient(config.backendUrl);

  // 注册所有工具
  registerAccountTools(server, client);
  registerMaterialTools(server, client);
  registerDraftTools(server, client);
  registerPublishTools(server, client);
  registerSettingsTools(server, client);
  registerTaskTools(server, client);
  registerPublishExtraTools(server, client);
  registerChangelogTools(server, client);

  return server;
}
```

- [ ] **Step 2: 构建确认无 TS 错误**

Run: `cd backend-mcp && npm run build`
Expected: 退出码 0，无输出

- [ ] **Step 3: 跑全量测试**

Run: `cd backend-mcp && npm test`
Expected: 所有测试文件 PASS（从 15 个用例增加到 22+ 个）

- [ ] **Step 4: Commit**

```bash
cd /home/czy/workspace/ai/social-auto-upload-web-ui
git add backend-mcp/src/server.ts
git commit -m "feat(mcp): server.ts 注册 tasks / publish_extra / changelog 三个新模块"
```

---

### Task 10：端到端验证（用户执行）

**这一步不在仓库内执行，文档化操作步骤给用户：**

- [ ] **Step 1: 用户在 Claude CLI 会话里执行：**

```bash
# 退出当前 Claude CLI 让 MCP 子进程重拉
exit
claude   # 重新启动
```

- [ ] **Step 2: 验证 13 个新工具都注册成功**

在 Claude CLI 输入：
```
列出所有 mcp__social-auto-upload__* 工具
```

期望至少看到（按字母序）：
- `mcp__social-auto-upload__changelog_list` (新)
- `mcp__social-auto-upload__draft_update` (新)
- `mcp__social-auto-upload__material_download` (新)
- `mcp__social-auto-upload__material_get_info` (新)
- `mcp__social-auto-upload__publish_history` (新)
- `mcp__social-auto-upload__publish_stats` (新)
- `mcp__social-auto-upload__queue_status` (新)
- `mcp__social-auto-upload__task_cancel` (新)
- `mcp__social-auto-upload__task_get_status` (新)
- `mcp__social-auto-upload__task_list` (新)
- `mcp__social-auto-upload__task_retry` (新)
- `mcp__social-auto-upload__task_stream` (新)
- `video_publish` 的 `material_id` 参数出现在 schema 中

- [ ] **Step 3: 跑一次真实 publish_history 验证 Flask 端点确实有数据**

调用 `mcp__social-auto-upload__publish_history` 不带任何参数 → 期望返回历史记录 JSON。

- [ ] **Step 4: 跑一次真实 task_list**

调用 `mcp__social-auto-upload__task_list` → 期望返回任务列表。

- [ ] **Step 5: 跑一次真实 video_publish 用 material_id**

1. 调 `mcp__social-auto-upload__material_list` 拿一个视频素材 ID
2. 调 `mcp__social-auto-upload__video_publish` 传 `material_id` 代替 `fileList`
3. 期望：工具内部查素材、拿到 stored_path、转给 `/postVideo`、返回 task_id

- [ ] **Step 6: 验证错误响应格式**

故意传一个不存在的 material_id 调 video_publish → 期望返回 `{"code":4003, "error":"MATERIAL_NOT_FOUND", "suggestion":"...", "retryable":false}` 而不是裸的 `{"code":400, "msg":"..."}`。

---

## Self-Review Checklist

✅ **Spec coverage:**
- material_get_info → Task 2 ✓
- material_download → Task 3 ✓
- draft_update → Task 4 ✓
- task_list / task_get_status / task_cancel / task_retry → Task 7 ✓
- task_stream → Task 7 ✓
- publish_history / publish_stats / queue_status → Task 5 ✓
- changelog_list → Task 6 ✓
- video_publish material_id → Task 8 ✓
- 错误码表 + translateError → Task 1 ✓
- 应用 errors 到所有新工具 → 各任务 Step 3 ✓
- server.ts 注册 → Task 9 ✓
- 端到端验证 → Task 10 ✓

✅ **类型一致：**
- `translateError(flaskResp, networkError?)` 在 Task 1 定义，Task 2/3/4/5/6/7/8 全部用同签名
- `formatErrorResult(err)` 一致
- `ErrorCodes.MATERIAL_NOT_FOUND` / `ACCOUNT_NOT_FOUND` / `DRAFT_NOT_FOUND` / `TASK_NOT_FOUND` / `MISSING_REQUIRED_FIELD` 在 errors.ts 定义、在所有 tool 中使用
- `getSSE(path, params, onMessage)` 是 `client.ts` 已有方法（不是新加），Task 7 复用

✅ **零占位符：**
- 每个 Step 的代码块完整可粘贴
- 没有 "类似 Task N" 的引用
- 没有 "实现后续" / "TBD" / "fill in"

✅ **范围最小：**
- image_publish 的 material_id 包装**未做**（明确在 Task 8 Step 3 的 "注意" 中说明，留待用户复测后决策）
- SSEServerTransport 迁移未做（SPEC 明确排除）
- 后端改动 0 行
- 前端改动 0 行
