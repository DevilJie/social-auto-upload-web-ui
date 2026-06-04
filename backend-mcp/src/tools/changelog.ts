import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { formatErrorResult, translateError } from '../errors.js';

export function registerChangelogTools(server: McpServer, client: BackendClient): void {
  server.tool(
    'changelog_list',
    '获取系统更新日志列表（按日期倒序）',
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/changelog');
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
