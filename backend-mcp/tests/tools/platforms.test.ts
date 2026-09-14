import { describe, it, expect, vi } from 'vitest';
import { registerPlatformTools } from '../../src/tools/platforms';
import { BackendClient } from '../../src/client';

function makeMockServer(tools: any[]) {
  return {
    tool: (name: string, description: string, schema: any, handler: Function) => {
      tools.push({ name, description, schema, handler });
    },
  } as any;
}

describe('platform tools', () => {
  it('应该注册3个工具（platform_list / api_catalog / api_call）', () => {
    const tools: any[] = [];
    registerPlatformTools(makeMockServer(tools), {} as BackendClient);
    expect(tools.map(t => t.name)).toEqual(['platform_list', 'api_catalog', 'api_call']);
  });

  it('platform_list 透传 /api/v2/platforms', async () => {
    const mockClient = { get: vi.fn().mockResolvedValue({ code: 200, data: { platforms: [] } }) } as any;
    const tools: any[] = [];
    registerPlatformTools(makeMockServer(tools), mockClient);
    await tools.find(t => t.name === 'platform_list')!.handler({});
    expect(mockClient.get).toHaveBeenCalledWith('/api/v2/platforms');
  });

  it('api_catalog 透传 prefix 参数', async () => {
    const mockClient = { get: vi.fn().mockResolvedValue({ code: 200, data: { total: 0, apis: [] } }) } as any;
    const tools: any[] = [];
    registerPlatformTools(makeMockServer(tools), mockClient);
    await tools.find(t => t.name === 'api_catalog')!.handler({ prefix: '/api/materials' });
    expect(mockClient.get).toHaveBeenCalledWith('/api/v2/api-catalog', { prefix: '/api/materials' });
  });

  it('api_call 调用后端端点并返回响应', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({ code: 200 }),
      post: vi.fn().mockResolvedValue({ code: 200 }),
      put: vi.fn().mockResolvedValue({ code: 200 }),
      delete: vi.fn().mockResolvedValue({ code: 200 }),
    } as any;
    const tools: any[] = [];
    registerPlatformTools(makeMockServer(tools), mockClient);
    const apiCall = tools.find(t => t.name === 'api_call')!;

    await apiCall.handler({ method: 'GET', path: '/api/health' });
    expect(mockClient.get).toHaveBeenCalledWith('/api/health', undefined);

    await apiCall.handler({ method: 'POST', path: '/api/feedback/vote', body: { id: 1 } });
    expect(mockClient.post).toHaveBeenCalledWith('/api/feedback/vote', { id: 1 });
  });

  it('api_call 拒绝 SSE / 浏览器交互端点', async () => {
    const mockClient = { get: vi.fn() } as any;
    const tools: any[] = [];
    registerPlatformTools(makeMockServer(tools), mockClient);
    const apiCall = tools.find(t => t.name === 'api_call')!;

    for (const path of ['/login', '/api/v2/tasks/stream', '/importAccount/stream']) {
      const result = await apiCall.handler({ method: 'GET', path });
      expect(result.isError).toBe(true);
      expect(JSON.parse(result.content[0].text).message).toContain('不允许');
    }
    expect(mockClient.get).not.toHaveBeenCalled();
  });
});
