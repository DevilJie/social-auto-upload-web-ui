import { describe, it, expect, vi } from 'vitest';
import { registerMaterialTools } from '../../src/tools/materials';
import { BackendClient } from '../../src/client';

describe('material tools', () => {
  it('应该注册5个素材相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerMaterialTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(5);
    expect(tools.map(t => t.name)).toEqual([
      'material_upload',
      'material_list',
      'material_delete',
      'material_get_info',
      'material_download',
    ]);
  });

  it('material_get_info 找到素材时返回完整对象', async () => {
    const stored = { id: 'mat-1', original_filename: 'a.mp4', url: 'http://x/a.mp4' };
    const mockClient = {
      get: vi.fn().mockResolvedValue({ data: { items: [stored, { id: 'mat-2' }] } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerMaterialTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'material_get_info')!.handler;

    const result = await handler({ id: 'mat-1' });

    expect(result.isError).toBeFalsy();
    expect(JSON.parse(result.content[0].text)).toEqual(stored);
  });

  it('material_get_info 找不到素材时返回 MATERIAL_NOT_FOUND', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({ data: { items: [{ id: 'mat-2' }] } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerMaterialTools(mockServer as any, mockClient);
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
    const mockClient = {
      get: vi.fn().mockResolvedValue({ data: { items: [stored] } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerMaterialTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'material_download')!.handler;

    const result = await handler({ id: 'mat-1' });

    expect(result.isError).toBeFalsy();
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed).toEqual({
      id: 'mat-1',
      filename: 'a.mp4',
      mime_type: 'video/mp4',
      file_size: 12345,
      url: 'http://x/a.mp4',
      thumbnail_url: 'http://x/a.jpg',
    });
  });

  it('material_download 找不到素材时返回 MATERIAL_NOT_FOUND', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({ data: { items: [{ id: 'mat-2' }] } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerMaterialTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'material_download')!.handler;

    const result = await handler({ id: 'nonexistent' });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('MATERIAL_NOT_FOUND');
    expect(parsed.message).toContain('不存在');
  });
});
