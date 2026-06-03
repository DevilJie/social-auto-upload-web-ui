import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerPublishTools(server: McpServer, client: BackendClient): void {
  // 视频发布
  server.tool(
    'video_publish',
    '发布视频到指定平台',
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      title: z.string().describe('视频标题'),
      fileList: z.array(z.string()).describe('视频文件路径列表'),
      accountList: z.array(z.string()).describe('账号cookie文件路径列表'),
      tags: z.array(z.string()).optional().describe('标签列表'),
      description: z.string().optional().describe('视频描述'),
      category: z.string().optional().describe('视频分类'),
      thumbnail: z.string().optional().describe('封面图路径'),
      thumbnailLandscape: z.string().optional().describe('横版封面路径'),
      thumbnailPortrait: z.string().optional().describe('竖版封面路径'),
      enableTimer: z.boolean().optional().describe('是否定时发布'),
      scheduleTime: z.string().optional().describe('定时发布时间'),
      videosPerDay: z.number().optional().describe('每天发布数量'),
      dailyTimes: z.array(z.string()).optional().describe('每天发布时间点'),
      startDays: z.number().optional().describe('开始天数'),
      productLink: z.string().optional().describe('商品链接'),
      productTitle: z.string().optional().describe('商品标题'),
      aiContent: z.string().optional().describe('AI生成内容'),
      creationDeclaration: z.string().optional().describe('创作声明'),
      riskWarning: z.string().optional().describe('风险提示'),
      enableCashActivity: z.boolean().optional().describe('是否启用现金活动'),
      supplementaryDeclaration: z.string().optional().describe('补充声明'),
      isDraft: z.boolean().optional().describe('是否保存为草稿'),
      audience: z.string().optional().describe('受众类型'),
      alteredContent: z.boolean().optional().describe('是否altered content'),
      hotspot: z.string().optional().describe('热点'),
      tag_type: z.string().optional().describe('标签类型'),
      tag_value: z.string().optional().describe('标签值'),
      mini_link: z.string().optional().describe('小程序链接'),
      mix_id: z.string().optional().describe('合集ID'),
      activities: z.array(z.any()).optional().describe('活动列表'),
    },
    async (params) => {
      try {
        const response = await client.post('/postVideo', params);

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
            text: `发布视频失败: ${error.message}`
          }],
          isError: true
        };
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
