import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';
import { formatErrorResult, translateError } from '../errors.js';

export function registerFrameTools(server: McpServer, client: BackendClient): void {
  // 抽帧
  server.tool(
    'frame_extract',
    '从视频素材抽取帧（后台异步执行）。首次调用返回 processing + 已有帧，稍后调 frames_list 或再次调用获取全部帧',
    {
      material_id: z.string().describe('视频素材 ID'),
    },
    async ({ material_id }) => {
      try {
        const response = await client.post('/api/extract-frames', { material_id });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 抽帧状态
  server.tool(
    'frames_status',
    '查询视频抽帧任务状态（processing / done）',
    {
      material_id: z.string().describe('视频素材 ID'),
    },
    async ({ material_id }) => {
      try {
        const response = await client.get('/api/frames-status', { material_id });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 帧列表
  server.tool(
    'frames_list',
    '获取视频的抽帧列表（帧时间点数组）',
    {
      material_id: z.string().describe('视频素材 ID'),
    },
    async ({ material_id }) => {
      try {
        const response = await client.get('/api/frames', { material_id });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );

  // 帧存为封面
  server.tool(
    'frame_save_cover',
    '把视频某一帧按 4 个比例（4:3 / 16:9 / 3:4 / 9:16）中心裁剪生成为封面文件，返回 4 个封面对象（可直接用于 video_publish 的封面）',
    {
      material_id: z.string().describe('视频素材 ID'),
      seconds: z.number().describe('帧时间点（秒）'),
    },
    async ({ material_id, seconds }) => {
      try {
        const response = await client.post('/api/frames/save-cover', {
          material_id, seconds: Math.round(seconds),
        });
        return { content: [{ type: 'text' as const, text: JSON.stringify(response, null, 2) }] };
      } catch (error: any) {
        return formatErrorResult(translateError(null, error));
      }
    }
  );
}
