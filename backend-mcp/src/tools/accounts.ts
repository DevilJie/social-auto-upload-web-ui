import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

const PLATFORM_ID_DESC = '平台 ID（完整清单调 platform_list，含 id/key/name）：1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺, 11=微博, 12=支付宝, 13=今日头条, 14=知乎, 15=CSDN, 16=VIVO, 17=微信公众号, 18=淘宝光合, 19=京东京麦, 21=大鱼号';

export function registerAccountTools(server: McpServer, client: BackendClient): void {
  // 账号登录
  server.tool(
    'account_login',
    '登录指定平台的账号，会打开浏览器进行登录（扫码/账密，人工参与）',
    {
      type: z.number().min(1).describe(PLATFORM_ID_DESC),
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

        // Flask 的 sse_stream 是死循环，必须在收到终态消息后主动断流
        const terminal = await client.getSSE<any>('/login', params, (msg) => {
          if (msg && typeof msg === 'object' && (msg.status === '200' || msg.status === '500')) {
            console.log('[MCP] Login SSE terminal status received:', msg.status);
            return msg;
          }
          return undefined;
        });

        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(terminal, null, 2)
          }],
          isError: terminal?.status !== '200'
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

  // 有效账号列表（秒回：按最近一次校验结果筛选，不开浏览器）
  server.tool(
    'account_valid_list',
    `获取 Cookie 有效的账号列表（按最近一次校验的缓存状态筛选，立即返回，不开浏览器）。

要强制重新校验（会为每个账号打开无头浏览器，约 10~30 秒/账号）请改用 account_check_all，
或用 account_check 校验单个账号。`,
    {},
    async () => {
      try {
        const resp = await client.get('/getAccounts');
        const raw: any[] = resp?.data ?? [];
        const rows = raw.map((row: any) => Array.isArray(row)
          ? { id: row[0], type: row[1], filePath: row[2], userName: row[3], status: row[4], avatar: row[5] }
          : row
        );
        const valid = rows.filter((a: any) => Number(a.status) === 1);
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify({ code: 200, data: valid, total: valid.length }, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取有效账号列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 强制重新校验账号 Cookie（开浏览器，慢）
  server.tool(
    'account_check_all',
    `强制重新校验账号 Cookie 有效性（真实访问各平台创作中心，会为每个账号打开无头浏览器）。

【耗时警告】每个账号约 10~30 秒，多账号会等待很久——校验 10 个账号可能需要 5 分钟。
- 只想按最近结果筛选有效账号：用 account_valid_list（秒回）
- 只想校验个别账号：传 account_ids 过滤，或逐个用 account_check

返回全部账号及最新校验状态（status=1 有效，0 失效），结果已写回数据库。`,
    {
      account_ids: z.array(z.union([z.string(), z.number()])).optional().describe('只校验这些账号 ID（缺省校验全部）'),
    },
    async ({ account_ids }) => {
      try {
        const params: Record<string, string> = {};
        if (account_ids?.length) {
          params.ids = account_ids.map(String).join(',');
        }
        // 每账号 10~30s，全量校验需要超长超时（30 分钟兜底）
        const response = await client.get('/getValidAccounts', params, 30 * 60 * 1000);
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
            text: `批量校验失败: ${error.message}`
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

  // 同步账号资料
  server.tool(
    'account_sync_profile',
    '同步账号最新资料（昵称/头像/粉丝数等，从平台创作者中心抓取）',
    {
      account_id: z.string().describe('账号ID'),
    },
    async ({ account_id }) => {
      try {
        const response = await client.post('/syncProfile', { id: account_id });
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
            text: `同步账号资料失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 打开创作者中心
  server.tool(
    'account_open_creator_center',
    '打开指定账号所属平台的创作者中心页面（浏览器可视化操作，人工参与）',
    {
      account_id: z.string().describe('账号ID'),
    },
    async ({ account_id }) => {
      try {
        const response = await client.post('/openCreatorCenter', { id: account_id });
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
            text: `打开创作者中心失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // ── 账号标签管理 ──

  server.tool(
    'tag_list',
    '获取全部账号标签',
    {},
    async () => {
      try {
        const response = await client.get('/api/tags');
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return {
          content: [{ type: 'text' as const, text: `获取标签失败: ${error.message}` }],
          isError: true
        };
      }
    }
  );

  server.tool(
    'tag_create',
    '创建账号标签（用于给账号分组，如"主号"/"测试"）',
    {
      name: z.string().describe('标签名'),
      color: z.string().optional().describe('颜色（hex，如 #6366f1，默认随机）'),
    },
    async ({ name, color }) => {
      try {
        const body: Record<string, string> = { name };
        if (color) body.color = color;
        const response = await client.post('/api/tags', body);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return {
          content: [{ type: 'text' as const, text: `创建标签失败: ${error.message}` }],
          isError: true
        };
      }
    }
  );

  server.tool(
    'tag_delete',
    '删除账号标签（同时解除所有账号与该标签的关联）',
    {
      tag_id: z.number().describe('标签 ID'),
    },
    async ({ tag_id }) => {
      try {
        const response = await client.delete(`/api/tags/${tag_id}`);
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return {
          content: [{ type: 'text' as const, text: `删除标签失败: ${error.message}` }],
          isError: true
        };
      }
    }
  );

  server.tool(
    'account_tags_set',
    '设置账号的标签（覆盖模式：传入的标签列表即该账号的完整标签集）',
    {
      account_id: z.number().describe('账号 ID'),
      tag_ids: z.array(z.number()).describe('标签 ID 列表（空数组 = 清空该账号标签）'),
    },
    async ({ account_id, tag_ids }) => {
      try {
        const response = await client.put(`/api/accounts/${account_id}/tags`, { tag_ids });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return {
          content: [{ type: 'text' as const, text: `设置账号标签失败: ${error.message}` }],
          isError: true
        };
      }
    }
  );

  server.tool(
    'account_tags_batch_add',
    '批量为多个账号追加相同的标签（追加模式：不清除已有标签）',
    {
      account_ids: z.array(z.number()).min(1).describe('账号 ID 列表'),
      tag_ids: z.array(z.number()).min(1).describe('标签 ID 列表'),
    },
    async ({ account_ids, tag_ids }) => {
      try {
        const response = await client.put('/api/accounts/batch/tags', { account_ids, tag_ids });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return {
          content: [{ type: 'text' as const, text: `批量设置标签失败: ${error.message}` }],
          isError: true
        };
      }
    }
  );

  // ── Cookie 导出（备份/迁移） ──

  server.tool(
    'cookie_download',
    '导出账号的 Cookie 文件内容（JSON），用于备份或迁移账号',
    {
      id: z.string().describe('账号ID'),
    },
    async ({ id }) => {
      try {
        // 后端按 cookie 文件路径（user_info.filePath）下载，先解析账号 → filePath
        const accResp = await client.get('/getAccounts');
        const rawAccs: any[] = accResp?.data ?? [];
        const accs = rawAccs.map((row: any) => Array.isArray(row)
          ? { id: row[0], type: row[1], filePath: row[2], userName: row[3], status: row[4], avatar: row[5] }
          : row
        );
        const acc = accs.find((a: any) => String(a.id) === String(id));
        if (!acc?.filePath) {
          return {
            content: [{ type: 'text' as const, text: `账号 ${id} 不存在（调 account_list 查可用账号）` }],
            isError: true
          };
        }
        const response = await client.getStream('/downloadCookie', { filePath: acc.filePath });
        return { content: [{ type: 'text' as const, text: response }] };
      } catch (error: any) {
        return {
          content: [{ type: 'text' as const, text: `导出 Cookie 失败: ${error.message}` }],
          isError: true
        };
      }
    }
  );
}
