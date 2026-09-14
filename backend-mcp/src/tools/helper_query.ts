import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError } from '../errors.js';

/**
 * 发布链辅助查询（与网页发布页同源端点）。
 * 这些端点通过账号 cookie 在真实平台侧查询，结果与网页发布页下拉一致。
 */
export function registerHelperQueryTools(server: McpServer, client: BackendClient): void {
  // ── 抖音 ──

  server.tool(
    'douyin_hotspot_search',
    '搜索抖音热点（发布时热点话题选择）',
    {
      account_id: z.string().describe('抖音账号 ID'),
      keyword: z.string().describe('搜索关键词'),
      count: z.number().optional().describe('返回数量（默认 50）'),
    },
    async ({ account_id, keyword, count }) => {
      try {
        const q: Record<string, string> = { account_id, keyword };
        if (count) q.count = String(count);
        const response = await client.get('/api/douyin-image/hotspot-search', q);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  server.tool(
    'douyin_music_search',
    '搜索抖音音乐（发布时音乐选择）',
    {
      account_id: z.string().describe('抖音账号 ID'),
      keyword: z.string().describe('搜索关键词'),
      cursor: z.number().optional().describe('翻页游标（默认 0）'),
      count: z.number().optional().describe('返回数量（默认 20）'),
    },
    async ({ account_id, keyword, cursor, count }) => {
      try {
        const q: Record<string, string> = { account_id, keyword };
        if (cursor) q.cursor = String(cursor);
        if (count) q.count = String(count);
        const response = await client.get('/api/douyin-image/music-search', q);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  server.tool(
    'douyin_mix_list',
    '获取抖音账号的合集列表（发布时加入合集）',
    {
      account_id: z.string().describe('抖音账号 ID'),
    },
    async ({ account_id }) => {
      try {
        const response = await client.get('/api/douyin-image/mix-list', { account_id });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  server.tool(
    'douyin_activity_list',
    '获取抖音官方活动列表（发布时活动选择）',
    {
      account_id: z.string().describe('抖音账号 ID'),
    },
    async ({ account_id }) => {
      try {
        const response = await client.get('/api/douyin-image/activity-list', { account_id });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // ── 快手 ──

  server.tool(
    'kuaishou_music_search',
    '搜索快手音乐（发布时音乐选择）',
    {
      account_id: z.string().describe('快手账号 ID'),
      keyword: z.string().describe('搜索关键词'),
    },
    async ({ account_id, keyword }) => {
      try {
        const response = await client.get('/api/kuaishou-image/music-search', { account_id, keyword });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // ── 各平台合集 ──

  const COLLECTION_ROUTES: Record<string, string> = {
    bilibili: '/api/bilibili/collections',
    weibo: '/api/weibo/collections',
    weixin_gzh: '/api/weixin_gzh/collections',
    channels: '/api/channels/collections',
    xiaohongshu: '/api/xiaohongshu/collections',
  };

  server.tool(
    'platform_collections',
    '获取账号在该平台的合集列表（B站/微博/微信公众号/视频号/小红书，发布时选择合集）',
    {
      platform: z.enum(['bilibili', 'weibo', 'weixin_gzh', 'channels', 'xiaohongshu']).describe('平台 key'),
      account_id: z.string().describe('账号 ID'),
    },
    async ({ platform, account_id }) => {
      try {
        const route = COLLECTION_ROUTES[platform];
        const response = await client.get(route, { account_id });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // ── 支付宝 / 头条 合集搜索 ──

  server.tool(
    'alipay_compilation_search',
    '搜索支付宝合集（发布时加入合集）',
    {
      account_id: z.string().describe('支付宝账号 ID'),
      keyword: z.string().describe('搜索关键词'),
    },
    async ({ account_id, keyword }) => {
      try {
        const response = await client.get('/api/alipay/compilation-search', { account_id, keyword });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  server.tool(
    'toutiao_compilation_search',
    '搜索今日头条合集（发布时加入合集）',
    {
      account_id: z.string().describe('头条账号 ID'),
      keyword: z.string().describe('搜索关键词'),
    },
    async ({ account_id, keyword }) => {
      try {
        const response = await client.get('/api/toutiao/compilation-search', { account_id, keyword });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // ── VIVO 位置 ──

  server.tool(
    'vivo_search_position',
    '搜索 VIVO 平台的地理位置（发布时添加位置）',
    {
      account_id: z.string().describe('VIVO 账号 ID'),
      keyword: z.string().describe('位置搜索关键词'),
    },
    async ({ account_id, keyword }) => {
      try {
        const response = await client.get('/api/vivo/search-position', { account_id, keyword });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
