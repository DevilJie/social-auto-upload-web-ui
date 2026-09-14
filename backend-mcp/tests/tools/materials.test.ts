import { describe, it, expect, vi } from 'vitest';
import { registerMaterialTools } from '../../src/tools/materials';
import { BackendClient } from '../../src/client';

function makeMockServer(tools: any[]) {
  return {
    tool: (name: string, description: string, schema: any, handler: Function) => {
      tools.push({ name, description, schema, handler });
    },
  } as any;
}

/** 单查端点 mock：/api/materials/<id> 存在返回素材行，不存在抛 404 */
function makeSingleGetClient(stored: any | null) {
  return {
    get: vi.fn(async (path: string) => {
      if (path.startsWith('/api/materials/')) {
        if (!stored) {
          const err: any = new Error('not found');
          err.response = { status: 404 };
          throw err;
        }
        return { data: stored };
      }
      return { data: null };
    }),
    post: vi.fn(async () => ({ code: 200 })),
    delete: vi.fn(async () => ({ code: 200 })),
  } as any;
}

describe('material tools', () => {
  it('应该注册7个素材相关工具', () => {
    const tools: any[] = [];
    registerMaterialTools(makeMockServer(tools), {} as BackendClient);
    expect(tools).toHaveLength(7);
    expect(tools.map(t => t.name)).toEqual([
      'material_upload',
      'material_list',
      'material_get_info',
      'material_download',
      'material_delete',
      'material_batch_delete',
      'material_probe',
    ]);
  });

  it('material_get_info 走单查端点，找到时返回完整对象', async () => {
    const stored = { id: 'mat-1', original_filename: 'a.mp4', url: 'http://x/a.mp4' };
    const mockClient = makeSingleGetClient(stored);
    const tools: any[] = [];
    registerMaterialTools(makeMockServer(tools), mockClient);
    const handler = tools.find(t => t.name === 'material_get_info')!.handler;

    const result = await handler({ id: 'mat-1' });

    expect(result.isError).toBeFalsy();
    expect(mockClient.get).toHaveBeenCalledWith('/api/materials/mat-1');
    expect(JSON.parse(result.content[0].text)).toEqual(stored);
  });

  it('material_get_info 404 时返回 MATERIAL_NOT_FOUND', async () => {
    const mockClient = makeSingleGetClient(null);
    const tools: any[] = [];
    registerMaterialTools(makeMockServer(tools), mockClient);
    const handler = tools.find(t => t.name === 'material_get_info')!.handler;

    const result = await handler({ id: 'nonexistent' });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('MATERIAL_NOT_FOUND');
    expect(parsed.message).toContain('不存在');
  });

  it('material_download 找到素材时返回精简 payload（filename 而非 original_filename）', async () => {
    const stored = {
      id: 'mat-1',
      original_filename: 'a.mp4',
      url: 'http://x/a.mp4',
      thumbnail_url: 'http://x/a.jpg',
      mime_type: 'video/mp4',
      file_size: 12345,
    };
    const mockClient = makeSingleGetClient(stored);
    const tools: any[] = [];
    registerMaterialTools(makeMockServer(tools), mockClient);
    const handler = tools.find(t => t.name === 'material_download')!.handler;

    const result = await handler({ id: 'mat-1' });

    expect(result.isError).toBeFalsy();
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed).toEqual(expect.objectContaining({
      id: 'mat-1',
      filename: 'a.mp4',
      mime_type: 'video/mp4',
      file_size: 12345,
      url: 'http://x/a.mp4',
      thumbnail_url: 'http://x/a.jpg',
    }));
  });

  it('material_batch_delete 调批量删除端点', async () => {
    const mockClient = makeSingleGetClient(null);
    const tools: any[] = [];
    registerMaterialTools(makeMockServer(tools), mockClient);
    const handler = tools.find(t => t.name === 'material_batch_delete')!.handler;

    await handler({ ids: ['mat-1', 'mat-2'] });

    expect(mockClient.post).toHaveBeenCalledWith('/api/materials/batch-delete', { ids: ['mat-1', 'mat-2'] });
  });
});
