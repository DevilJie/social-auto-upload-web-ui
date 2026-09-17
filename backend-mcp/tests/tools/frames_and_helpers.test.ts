import { describe, it, expect, vi } from 'vitest';
import { registerFrameTools } from '../../src/tools/frames';
import { registerHelperQueryTools } from '../../src/tools/helper_query';
import { BackendClient } from '../../src/client';

function makeMockServer(tools: any[]) {
  return {
    tool: (name: string, description: string, schema: any, handler: Function) => {
      tools.push({ name, description, schema, handler });
    },
  } as any;
}

describe('frame tools', () => {
  it('应该注册4个抽帧工具', () => {
    const tools: any[] = [];
    registerFrameTools(makeMockServer(tools), {} as BackendClient);
    expect(tools.map(t => t.name)).toEqual([
      'frame_extract', 'frames_status', 'frames_list', 'frame_save_cover',
    ]);
  });

  it('frame_extract POST /api/extract-frames {material_id}', async () => {
    const mockClient = { post: vi.fn().mockResolvedValue({ code: 200 }) } as any;
    const tools: any[] = [];
    registerFrameTools(makeMockServer(tools), mockClient);
    await tools.find(t => t.name === 'frame_extract')!.handler({ material_id: 'mat-1' });
    expect(mockClient.post).toHaveBeenCalledWith('/api/extract-frames', { material_id: 'mat-1' });
  });

  it('frame_save_cover 秒数取整后提交', async () => {
    const mockClient = { post: vi.fn().mockResolvedValue({ code: 200 }) } as any;
    const tools: any[] = [];
    registerFrameTools(makeMockServer(tools), mockClient);
    await tools.find(t => t.name === 'frame_save_cover')!.handler({ material_id: 'mat-1', seconds: 3.7 });
    expect(mockClient.post).toHaveBeenCalledWith('/api/frames/save-cover', { material_id: 'mat-1', seconds: 4 });
  });
});

describe('helper query tools', () => {
  it('应该注册9个辅助查询工具', () => {
    const tools: any[] = [];
    registerHelperQueryTools(makeMockServer(tools), {} as BackendClient);
    expect(tools.map(t => t.name)).toEqual([
      'douyin_hotspot_search',
      'douyin_music_search',
      'douyin_mix_list',
      'douyin_activity_list',
      'kuaishou_music_search',
      'platform_collections',
      'alipay_compilation_search',
      'toutiao_compilation_search',
      'vivo_search_position',
    ]);
  });

  it('platform_collections 按平台路由到对应合集端点', async () => {
    const mockClient = { get: vi.fn().mockResolvedValue({ code: 200, data: { list: [] } }) } as any;
    const tools: any[] = [];
    registerHelperQueryTools(makeMockServer(tools), mockClient);
    const handler = tools.find(t => t.name === 'platform_collections')!.handler;

    await handler({ platform: 'bilibili', account_id: '5' });
    expect(mockClient.get).toHaveBeenCalledWith('/api/bilibili/collections', { account_id: '5' });

    await handler({ platform: 'weibo', account_id: '5' });
    expect(mockClient.get).toHaveBeenCalledWith('/api/weibo/collections', { account_id: '5' });
  });
});
