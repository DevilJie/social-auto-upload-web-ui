import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

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
      draft_data: z.record(z.any()).describe('草稿数据JSON'),
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
}
