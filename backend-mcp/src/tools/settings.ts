import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerSettingsTools(server: McpServer, client: BackendClient): void {
  // 获取系统设置
  server.tool(
    'settings_get',
    '获取所有系统设置',
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/settings');

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
            text: `获取系统设置失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 更新系统设置
  server.tool(
    'settings_update',
    '更新系统设置',
    {
      settings: z.record(z.any()).describe('要更新的设置键值对'),
    },
    async ({ settings }) => {
      try {
        const response = await client.put('/api/v2/settings', settings);

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
            text: `更新系统设置失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
