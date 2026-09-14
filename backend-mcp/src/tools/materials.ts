import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

/** 单查素材（后端有专用端点，不再翻页 list 过滤） */
async function fetchMaterial(client: BackendClient, id: string): Promise<any | null> {
  try {
    const resp = await client.get(`/api/materials/${id}`);
    return resp?.data ?? null;
  } catch (error: any) {
    if (error?.response?.status === 404) return null;
    throw error;
  }
}

function materialNotFound(id: string) {
  return formatErrorResult({
    code: ErrorCodes.MATERIAL_NOT_FOUND,
    error: 'MATERIAL_NOT_FOUND',
    message: `素材 ${id} 不存在`,
    suggestion: '调 material_list 查可用素材 ID',
    retryable: false,
  });
}

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
      page_size: z.number().optional().describe('每页数量（默认24，最大96）'),
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

  // 获取素材详情
  server.tool(
    'material_get_info',
    '获取素材的详细信息（单查接口：公开 URL、缩略图、文件大小、时长、方向等）',
    {
      id: z.string().describe('素材 ID（UUID）'),
    },
    async ({ id }) => {
      try {
        const item = await fetchMaterial(client, id);
        if (!item) return materialNotFound(id);
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

  // 获取素材下载 URL
  server.tool(
    'material_download',
    '获取素材的可访问 URL（指向后端 /api/materials/file/<path>）。AI 客户端无持久化文件系统，本工具返回 URL 而非二进制。',
    {
      id: z.string().describe('素材 ID'),
    },
    async ({ id }) => {
      try {
        const item = await fetchMaterial(client, id);
        if (!item) return materialNotFound(id);
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify({
              id: item.id,
              filename: item.original_filename,
              mime_type: item.mime_type,
              file_size: item.file_size,
              duration: item.duration,
              orientation: item.orientation,
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

  // 批量删除素材
  server.tool(
    'material_batch_delete',
    '批量删除素材（单条失败不中断其余，返回成功/失败明细）',
    {
      ids: z.array(z.string()).min(1).describe('素材 ID 列表'),
    },
    async ({ ids }) => {
      try {
        const response = await client.post('/api/materials/batch-delete', { ids });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 素材探测（补全时长/大小元数据）
  server.tool(
    'material_probe',
    '探测视频素材的时长与文件大小并写库（存量素材元数据缺失时补全），返回最新素材记录',
    {
      id: z.string().describe('视频素材 ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.post(`/api/materials/${id}/probe`);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        if (error?.response?.status === 404) return materialNotFound(id);
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
