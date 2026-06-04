import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerAccountTools(server: McpServer, client: BackendClient): void {
  // 账号登录
  server.tool(
    'account_login',
    '登录指定平台的账号，会打开浏览器进行登录',
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      account_id: z.string().optional().describe('账号ID（可选，用于更新已有账号）'),
    },
    async ({ type, account_id }) => {
      try {
        // 生成唯一的登录会话ID
        const loginId = `login_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const params: Record<string, string> = {
          type: String(type),
          id: loginId
        };
        if (account_id) {
          params.account_id = account_id;
        }

        console.log('[MCP] Calling login with params:', params);

        // 调用Flask后端的login接口（返回SSE流）
        const response = await client.getStream('/login', params);

        return {
          content: [{
            type: 'text' as const,
            text: response
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `登录失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 账号列表
  server.tool(
    'account_list',
    '获取所有账号列表',
    {},
    async () => {
      try {
        const response = await client.get('/getAccounts');

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
            text: `获取账号列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 检查账号状态
  server.tool(
    'account_check',
    '检查指定账号的Cookie是否有效',
    {
      id: z.string().describe('账号ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get('/checkAccount', { id });

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
            text: `检查账号状态失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 删除账号
  server.tool(
    'account_delete',
    '删除指定账号',
    {
      id: z.string().describe('账号ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get('/deleteAccount', { id });

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
            text: `删除账号失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
