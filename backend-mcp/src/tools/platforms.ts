import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError } from '../errors.js';

// api_call 黑名单：流式/浏览器交互/静态资源端点不适合一次性 HTTP 调用
const API_CALL_BLOCKED_PATHS = new Set([
  '/login',                      // SSE：打开浏览器登录
  '/importAccount/stream',       // SSE
  '/api/v2/tasks/stream',        // SSE 长连接
  '/sse', '/messages',           // MCP 自身
]);
const API_CALL_BLOCKED_PREFIXES = ['/assets/', '/changelog/', '/static/', '/uploads/'];

function isBlockedPath(path: string): boolean {
  return API_CALL_BLOCKED_PATHS.has(path) || API_CALL_BLOCKED_PREFIXES.some((p) => path.startsWith(p));
}

export function registerPlatformTools(server: McpServer, client: BackendClient): void {
  // 平台清单（含发布配置元数据）
  server.tool(
    'platform_list',
    `获取全部支持的平台清单及各平台发布配置元数据。

返回每个平台的：id（数字，登录/发布用）、key（英文标识）、name（中文名）、
default_config（发布配置初始值）、fields（发布设置字段定义：字段名/类型/必填/选项/联动规则）、
schedule（定时发布约束，如最多未来天数、分钟粒度）。

【发布前必看】各平台的声明字段（如 aiContent/creationDeclaration/authorStatement）选项各不相同，
请以本工具返回的 fields 为准（与网页发布页完全一致），不要凭记忆填写。
后端新增平台后本工具自动可见。`,
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/platforms');
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 后端 API 目录
  server.tool(
    'api_catalog',
    `枚举后端全部 HTTP API（路径/方法/说明）。后端新增任何端点本工具自动可见。

用于发现尚未封装为专用 MCP 工具的新能力；配合 api_call 可直接调用。
可选 prefix 参数按路径前缀过滤（如 "prefix": "/api/materials"）。`,
    {
      prefix: z.string().optional().describe('路径前缀过滤，如 /api/materials、/api/v2'),
    },
    async ({ prefix }) => {
      try {
        const params: Record<string, string> = {};
        if (prefix) params.prefix = prefix;
        const response = await client.get('/api/v2/api-catalog', params);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 通用 API 调用（逃生舱）
  server.tool(
    'api_call',
    `直接调用后端任意 HTTP API（逃生舱：专用工具未覆盖的新能力按 api_catalog 的路径直接调用）。

先调 api_catalog 查目标端点的路径与方法，再用本工具调用。
- GET：参数放 query（对象，值自动转字符串）
- POST/PUT：参数放 body（JSON 对象）
- DELETE：无 body

注意：流式端点（SSE：/login、/api/v2/tasks/stream 等）与浏览器交互端点被禁用，
请改用对应的专用工具（如 account_login）。`,
    {
      method: z.enum(['GET', 'POST', 'PUT', 'DELETE']).describe('HTTP 方法'),
      path: z.string().describe('API 路径，如 /api/v2/history（以 / 开头，不含域名）'),
      query: z.record(z.string(), z.any()).optional().describe('查询参数（GET 用，也可用于其他方法）'),
      body: z.record(z.string(), z.any()).optional().describe('请求体（POST/PUT 用）'),
    },
    async ({ method, path, query, body }) => {
      if (isBlockedPath(path)) {
        return formatErrorResult({
          code: 4001,
          error: 'MISSING_REQUIRED_FIELD',
          message: `路径 ${path} 不允许通过 api_call 调用（流式/浏览器交互端点）`,
          suggestion: '改用对应的专用 MCP 工具（如 account_login / task_stream）',
          retryable: false,
        });
      }
      try {
        const q: Record<string, string> | undefined = query
          ? Object.fromEntries(Object.entries(query).map(([k, v]) => [k, String(v)]))
          : undefined;
        let response;
        if (method === 'GET') response = await client.get(path, q);
        else if (method === 'POST') response = await client.post(path, body ?? {});
        else if (method === 'PUT') response = await client.put(path, body ?? {});
        else response = await client.delete(path);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
