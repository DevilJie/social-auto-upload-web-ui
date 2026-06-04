import { describe, it, expect, vi } from 'vitest';
import { registerPublishExtraTools } from '../../src/tools/publish_extra';
import { BackendClient } from '../../src/client';

describe('publish extra tools', () => {
  it('应该注册3个发布辅助工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishExtraTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(3);
    expect(tools.map(t => t.name)).toEqual([
      'publish_history',
      'publish_stats',
      'queue_status',
    ]);
  });

  it('publish_history 接受过滤参数并正确转发', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({ code: 200, data: { items: [], total: 0 } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishExtraTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'publish_history')!.handler;

    await handler({ platform: 'douyin', status: 'success', time_range: '7days' });

    expect(mockClient.get).toHaveBeenCalledWith('/api/v2/history', expect.objectContaining({
      platform: 'douyin',
      status: 'success',
      timeRange: '7days',
    }));
  });
});
