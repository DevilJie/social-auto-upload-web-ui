import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError } from '../errors.js';

export function registerPublishExtraTools(server: McpServer, client: BackendClient): void {
  // 发布历史
  server.tool(
    'publish_history',
    '获取发布历史记录（支持按类型/平台/状态/日期范围过滤）',
    {
      type: z.enum(['video', 'image']).optional().describe('内容类型：video=视频, image=图文'),
      platform: z.string().optional().describe('平台 key（如 douyin/bilibili/weibo，完整清单调 platform_list）'),
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
        if (params.type) q.type = params.type;
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

  // 发布历史详情
  server.tool(
    'history_detail',
    '获取一次发布批次（batch）的详情：批次内每个账号任务的配置与结果',
    {
      batch_id: z.string().describe('批次 ID（publish_history 返回的 id）'),
    },
    async ({ batch_id }) => {
      try {
        const response = await client.get(`/api/v2/history/${batch_id}`);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 删除发布历史
  server.tool(
    'history_delete',
    '删除发布历史（单条或多条）。删除后不可恢复，请先与用户确认',
    {
      batch_ids: z.array(z.string()).min(1).describe('批次 ID 列表（单条也传数组）'),
    },
    async ({ batch_ids }) => {
      try {
        const response = batch_ids.length === 1
          ? await client.delete(`/api/v2/history/${batch_ids[0]}`)
          : await client.deleteWithBody('/api/v2/history/batch', { batch_ids });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 发布模板（一键填写）
  server.tool(
    'publish_templates',
    '获取可复用的发布模板（从历史成功批次提取的各平台发布配置，用于一键复刻历史配置）',
    {
      type: z.enum(['video', 'image']).describe('内容类型'),
      page: z.number().optional().describe('页码（默认 1）'),
      page_size: z.number().optional().describe('每页数量（默认 20，最大 100）'),
    },
    async ({ type, page, page_size }) => {
      try {
        const q: Record<string, string> = { type };
        if (page) q.page = String(page);
        if (page_size) q.page_size = String(page_size);
        const response = await client.get('/api/v2/publish-templates', q);
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
