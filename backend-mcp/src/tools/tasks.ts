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
