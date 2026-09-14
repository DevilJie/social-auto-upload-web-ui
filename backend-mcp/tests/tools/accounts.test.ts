import { describe, it, expect, vi } from 'vitest';
import { registerAccountTools } from '../../src/tools/accounts';
import { BackendClient } from '../../src/client';

describe('account tools', () => {
  it('应该注册全部账号相关工具（账号 + 标签 + Cookie）', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];

    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };

    registerAccountTools(mockServer as any, mockClient);

    expect(tools.map(t => t.name)).toEqual([
      'account_login',
      'account_list',
      'account_valid_list',
      'account_check',
      'account_delete',
      'account_sync_profile',
      'account_open_creator_center',
      'tag_list',
      'tag_create',
      'tag_delete',
      'account_tags_set',
      'account_tags_batch_add',
      'cookie_download',
    ]);
  });

  it('account_valid_list 调 /getValidAccounts', async () => {
    const mockClient = { get: vi.fn().mockResolvedValue({ code: 200, data: [] }) } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerAccountTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'account_valid_list')!.handler;

    await handler({});
    expect(mockClient.get).toHaveBeenCalledWith('/getValidAccounts');
  });

  it('account_sync_profile 传 {id} 调 /syncProfile', async () => {
    const mockClient = { post: vi.fn().mockResolvedValue({ code: 200 }) } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerAccountTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'account_sync_profile')!.handler;

    await handler({ account_id: '7' });
    expect(mockClient.post).toHaveBeenCalledWith('/syncProfile', { id: '7' });
  });

  it('cookie_download 先解析账号 filePath 再下载', async () => {
    const mockClient = {
      get: vi.fn().mockResolvedValue({
        data: [[7, 3, 'douyin/abc.json', '抖音号', 1, '']],
      }),
      getStream: vi.fn().mockResolvedValue('[{"name": "cookie"}]'),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerAccountTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'cookie_download')!.handler;

    const result = await handler({ id: '7' });
    expect(result.isError).toBeFalsy();
    expect(mockClient.getStream).toHaveBeenCalledWith('/downloadCookie', { filePath: 'douyin/abc.json' });
  });
});
