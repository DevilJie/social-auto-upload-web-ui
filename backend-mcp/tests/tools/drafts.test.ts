import { describe, it, expect, vi } from 'vitest';
import { registerDraftTools } from '../../src/tools/drafts';
import { BackendClient } from '../../src/client';

describe('draft tools', () => {
  it('应该注册5个草稿相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerDraftTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(5);
    expect(tools.map(t => t.name)).toEqual([
      'draft_list',
      'draft_get',
      'draft_create',
      'draft_delete',
      'draft_update',
    ]);
  });

  it('draft_update 成功时返回后端响应', async () => {
    const mockClient = {
      put: vi.fn().mockResolvedValue({ code: 200, data: { id: 42, title: 'updated' } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerDraftTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'draft_update')!.handler;

    const result = await handler({ id: 42, draft_data: { foo: 'bar' } });

    expect(result.isError).toBeFalsy();
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.code).toBe(200);
    expect(parsed.data.id).toBe(42);
    expect(mockClient.put).toHaveBeenCalledWith('/api/v2/drafts/42', { draft_data: { foo: 'bar' } });
  });

  it('draft_update 404 时返回 DRAFT_NOT_FOUND', async () => {
    const mockClient = {
      put: vi.fn().mockRejectedValue({ response: { status: 404 } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerDraftTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'draft_update')!.handler;

    const result = await handler({ id: 999, draft_data: { foo: 'bar' } });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('DRAFT_NOT_FOUND');
    expect(parsed.message).toContain('不存在');
  });
});
