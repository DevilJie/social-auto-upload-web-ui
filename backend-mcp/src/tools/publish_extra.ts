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
