import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

export function registerMaterialTools(server: McpServer, client: BackendClient): void {
  // 上传素材
  server.tool(
    'material_upload',
    '上传图片或视频素材',
    {
      file_path: z.string().describe('本地文件路径'),
    },
    async ({ file_path }) => {
      try {
        const response = await client.uploadFile('/api/materials/upload', file_path);

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
            text: `上传素材失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 素材列表
  server.tool(
    'material_list',
    '获取素材列表，支持分页和筛选',
    {
      type: z.enum(['all', 'video', 'image']).optional().describe('素材类型筛选'),
      keyword: z.string().optional().describe('文件名搜索关键词'),
      page: z.number().optional().describe('页码（从1开始）'),
      page_size: z.number().optional().describe('每页数量（默认24）'),
    },
    async ({ type, keyword, page, page_size }) => {
      try {
        const params: Record<string, string> = {};
        if (type) params.type = type;
        if (keyword) params.keyword = keyword;
        if (page) params.page = String(page);
        if (page_size) params.page_size = String(page_size);

        const response = await client.get('/api/materials/list', params);

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
            text: `获取素材列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 删除素材
  server.tool(
    'material_delete',
    '删除指定素材',
    {
      id: z.string().describe('素材ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.delete(`/api/materials/${id}`);

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
            text: `删除素材失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

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
            message: `素材 ${id} 不存在或不在前 100 条之内`,
            suggestion: '调 material_list 翻页查找，或用 keyword 过滤',
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
}
