import { describe, it, expect, vi } from 'vitest';
import { registerAccountTools } from '../../src/tools/accounts';
import { BackendClient } from '../../src/client';

describe('account tools', () => {
  it('应该注册4个账号相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];

    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };

    registerAccountTools(mockServer as any, mockClient);

    expect(tools).toHaveLength(4);
    expect(tools.map(t => t.name)).toEqual([
      'account_login',
      'account_list',
      'account_check',
      'account_delete'
    ]);
  });
});
