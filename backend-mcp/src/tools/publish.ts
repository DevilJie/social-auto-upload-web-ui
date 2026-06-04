import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError, ErrorCodes } from '../errors.js';

export function registerPublishTools(server: McpServer, client: BackendClient): void {
  // 视频发布
  server.tool(
    'video_publish',
    '发布视频到指定平台。优先用 material_id（从素材库选），也兼容本地 fileList。',
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      title: z.string().describe('视频标题'),
      material_id: z.string().optional().describe('视频素材 ID（推荐，从素材库选择）'),
      fileList: z.array(z.string()).optional().describe('视频文件路径列表（兼容旧用法，与 material_id 互斥）'),
      accountList: z.array(z.string()).optional().describe('账号 cookie 文件路径列表'),
      account_id: z.union([z.string(), z.number()]).optional().describe('账号 ID（推荐；MCP 会查 list 拿 cookie 路径填到 accountList）'),
      tags: z.array(z.string()).optional(),
      description: z.string().optional(),
      category: z.string().optional(),
      thumbnail: z.string().optional().describe('封面图路径（兼容）'),
      thumbnail_material_id: z.string().optional().describe('封面图素材 ID（推荐）'),
      thumbnailLandscape: z.string().optional(),
      thumbnailPortrait: z.string().optional(),
      enableTimer: z.boolean().optional(),
      scheduleTime: z.string().optional(),
      videosPerDay: z.number().optional(),
      dailyTimes: z.array(z.string()).optional(),
      startDays: z.number().optional(),
      productLink: z.string().optional(),
      productTitle: z.string().optional(),
      aiContent: z.string().optional(),
      creationDeclaration: z.string().optional(),
      riskWarning: z.string().optional(),
      enableCashActivity: z.boolean().optional(),
      supplementaryDeclaration: z.string().optional(),
      isDraft: z.boolean().optional(),
      audience: z.string().optional(),
      alteredContent: z.boolean().optional(),
      hotspot: z.string().optional(),
      tag_type: z.string().optional(),
      tag_value: z.string().optional(),
      mini_link: z.string().optional(),
      mix_id: z.string().optional(),
      activities: z.array(z.any()).optional(),
    },
    async (params) => {
      try {
        const { material_id, fileList, account_id, accountList, thumbnail_material_id, thumbnail, ...rest } = params;

        // 互斥校验
        if (!material_id && !fileList?.length) {
          return formatErrorResult({
            code: ErrorCodes.MISSING_REQUIRED_FIELD,
            error: 'MISSING_REQUIRED_FIELD',
            message: 'material_id 或 fileList 至少二选一',
            suggestion: '调 material_list 选素材传 material_id，或直接传 fileList',
            retryable: false,
          });
        }

        // material_id → fileList
        let resolvedFileList = fileList;
        if (material_id && !fileList?.length) {
          const list = await client.get('/api/materials/list', { type: 'video', page: '1', page_size: '100' });
          const items = list?.data?.items ?? [];
          const mat = items.find((m: any) => m.id === material_id);
          if (!mat) {
            return formatErrorResult({
              code: ErrorCodes.MATERIAL_NOT_FOUND,
              error: 'MATERIAL_NOT_FOUND',
              message: `素材 ${material_id} 不存在或不在前 100 条之内`,
              suggestion: '调 material_list 翻页查找，或用 keyword 过滤',
              retryable: false,
            });
          }
          resolvedFileList = [mat.stored_path];
        }

        // account_id → accountList
        // /getAccounts 返回的是位置数组 [id, type, filePath, userName, status, avatar]，
        // 需要先转换为字典
        let resolvedAccountList = accountList;
        if (account_id && !accountList?.length) {
          const accounts = await client.get('/getAccounts');
          const rawAccs: any[] = accounts?.data ?? [];
          // 兼容位置数组和字典两种返回
          const accs = rawAccs.map((row: any) => Array.isArray(row)
            ? { id: row[0], type: row[1], filePath: row[2], userName: row[3], status: row[4], avatar: row[5] }
            : row
          );
          const acc = accs.find((a: any) => String(a.id) === String(account_id));
          if (!acc) {
            return formatErrorResult({
              code: ErrorCodes.ACCOUNT_NOT_FOUND,
              error: 'ACCOUNT_NOT_FOUND',
              message: `账号 ${account_id} 不存在`,
              suggestion: '调 account_list 查可用账号 ID',
              retryable: false,
            });
          }
          resolvedAccountList = [acc.filePath ?? acc.cookie_path ?? acc.cookiePath];
        }

        // thumbnail_material_id → thumbnail
        let resolvedThumbnail = thumbnail;
        if (thumbnail_material_id && !thumbnail) {
          const list = await client.get('/api/materials/list', { type: 'image', page: '1', page_size: '100' });
          const items = list?.data?.items ?? [];
          const mat = items.find((m: any) => m.id === thumbnail_material_id);
          if (mat) {
            resolvedThumbnail = mat.stored_path;
          }
        }

        const response = await client.post('/postVideo', {
          ...rest,
          fileList: resolvedFileList,
          accountList: resolvedAccountList,
          thumbnail: resolvedThumbnail,
        });

        return {
          content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }],
        };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 图文发布
  server.tool(
    'image_publish',
    '发布图文内容到指定平台',
    {
      image_ids: z.array(z.string()).describe('图片ID列表'),
      account_configs: z.array(z.object({
        account_id: z.number().describe('账号ID'),
        platform: z.string().describe('平台类型'),
        filePath: z.string().describe('cookie文件路径'),
        title: z.string().optional().describe('标题'),
        description: z.string().optional().describe('描述'),
        tags: z.array(z.string()).optional().describe('标签列表'),
        cover_path: z.string().optional().describe('封面路径'),
        mix_id: z.string().optional().describe('合集ID'),
        music_name: z.string().optional().describe('音乐名称'),
        hotspot: z.string().optional().describe('热点'),
        tag_type: z.string().optional().describe('标签类型'),
        tag_value: z.string().optional().describe('标签值'),
        mini_link: z.string().optional().describe('小程序链接'),
        scheduleTime: z.string().optional().describe('定时发布时间'),
        aiContent: z.string().optional().describe('AI生成内容'),
        isOriginal: z.boolean().optional().describe('是否原创'),
        activities: z.array(z.any()).optional().describe('活动列表'),
        music_id: z.string().optional().describe('音乐ID'),
        music_title: z.string().optional().describe('音乐标题'),
        dry_run: z.boolean().optional().describe('是否试运行'),
      })).describe('账号配置列表'),
    },
    async (params) => {
      try {
        const response = await client.post('/api/image-publish/publish', params);

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
            text: `发布图文失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
