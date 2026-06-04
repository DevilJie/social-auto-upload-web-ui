import { describe, it, expect } from 'vitest';
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
});
