import { describe, it, expect, vi } from 'vitest';
import { registerTaskTools } from '../../src/tools/tasks';
import { BackendClient } from '../../src/client';

describe('task tools', () => {
  it('应该注册5个任务管理工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerTaskTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(5);
    expect(tools.map(t => t.name)).toEqual([
      'task_list',
      'task_get_status',
      'task_cancel',
      'task_retry',
      'task_stream',
    ]);
  });

  it('task_get_status 404 时返回 TASK_NOT_FOUND', async () => {
    const mockClient = {
      get: vi.fn().mockRejectedValue({ response: { status: 404 } }),
    } as any;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerTaskTools(mockServer as any, mockClient);
    const handler = tools.find(t => t.name === 'task_get_status')!.handler;

    const result = await handler({ task_id: 'nonexistent' });

    expect(result.isError).toBe(true);
    const parsed = JSON.parse(result.content[0].text);
    expect(parsed.error).toBe('TASK_NOT_FOUND');
    expect(parsed.message).toContain('不存在');
  });
});
