import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

export function registerDraftTools(server: McpServer, client: BackendClient): void {
  // 草稿列表
  server.tool(
    'draft_list',
    '获取草稿列表，支持按类型筛选',
    {
      type: z.enum(['video', 'image']).optional().describe('草稿类型筛选'),
    },
    async ({ type }) => {
      try {
        const params: Record<string, string> = {};
        if (type) params.type = type;

        const response = await client.get('/api/v2/drafts', params);

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取草稿列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 获取草稿详情
  server.tool(
    'draft_get',
    '获取指定草稿的详细信息',
    {
      id: z.string().describe('草稿ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get(`/api/v2/drafts/${id}`);

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取草稿详情失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 创建草稿
  server.tool(
    'draft_create',
    '创建新草稿',
    {
      type: z.enum(['video', 'image']).describe('草稿类型'),
      draft_data: z.record(z.string(), z.any()).describe('草稿数据JSON'),
    },
    async ({ type, draft_data }) => {
      try {
        const response = await client.post('/api/v2/drafts', {
          type,
          draft_data,
        });

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `创建草稿失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 删除草稿
  server.tool(
    'draft_delete',
    '删除指定草稿',
    {
      id: z.string().describe('草稿ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.delete(`/api/v2/drafts/${id}`);

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `删除草稿失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

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
}
