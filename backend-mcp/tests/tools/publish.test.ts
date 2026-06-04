import { describe, it, expect, vi } from 'vitest';
import { registerPublishTools } from '../../src/tools/publish';
import { BackendClient } from '../../src/client';

describe('publish tools', () => {
  it('应该注册2个发布工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(2);
  });

  it('video_publish 接受 account_id，从位置数组里查 cookie 路径', async () => {
    // /getAccounts 返回的是位置数组 [id, type, filePath, userName, status, avatar]
    const mockClient = {
      get: vi.fn().mockResolvedValue({
        data: [
          [1, 1, '/path/to/xhs.json', '账号1', 1, 'avatar1'],
          [7, 2, '/path/to/channels.json', '账号7', 1, 'avatar7'],
        ],
      }),
      post: vi.fn().mockResolvedValue({ code: 200, data: { task_id: 'task-1' } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({
      type: 2,
      title: 'test',
      fileList: ['/local/video.mp4'],
      account_id: 7,
    });

    expect(result.isError).toBeFalsy();
    expect(mockClient.post).toHaveBeenCalledWith('/postVideo', expect.objectContaining({
      accountList: ['/path/to/channels.json'],  // ← 从位置数组里拿到的 filePath
    }));
  });

  it('video_publish 接受 material_id，内部查素材转 fileList', async () => {
    const stored_path = 'materials/2026/06/04/abc.mp4';
    const mockClient = {
      get: vi.fn().mockResolvedValue({
        data: { items: [{ id: 'mat-1', stored_path, file_type: 'video' }] },
      }),
      post: vi.fn().mockResolvedValue({ code: 200, data: { task_id: 'task-1' } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({
      type: 2,
      title: 'test',
      material_id: 'mat-1',
    });

    // 验证调用了 get（查素材）和 post（发布）
    expect(mockClient.get).toHaveBeenCalledWith('/api/materials/list', expect.any(Object));
    expect(mockClient.post).toHaveBeenCalledWith('/postVideo', expect.objectContaining({
      type: 2,
      title: 'test',
      fileList: [stored_path],  // ← material_id 被转成 fileList
    }));
    expect(result.isError).toBeFalsy();
  });

  it('video_publish 传不存在的 material_id 返回 MATERIAL_NOT_FOUND', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({ data: { items: [] } }),
      post: vi.fn(),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({
      type: 2,
      title: 'test',
      material_id: 'nonexistent',
    });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('MATERIAL_NOT_FOUND');
    expect(mockClient.post).not.toHaveBeenCalled();
  });

  it('video_publish 不传 material_id 也不传 fileList 返回 MISSING_REQUIRED_FIELD', async () => {
    const mockClient = { get: vi.fn(), post: vi.fn() } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerPublishTools(mockServer as any, mockClient);
    const videoPublish = tools.find(t => t.name === 'video_publish')!;

    const result = await videoPublish.handler({ type: 2, title: 'test' });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('MISSING_REQUIRED_FIELD');
  });
});
