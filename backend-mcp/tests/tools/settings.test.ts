import { describe, it, expect } from 'vitest';
import { registerSettingsTools } from '../../src/tools/settings';
import { BackendClient } from '../../src/client';

describe('settings tools', () => {
  it('应该注册2个设置相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];

    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };

    registerSettingsTools(mockServer as any, mockClient);

    expect(tools).toHaveLength(2);
    expect(tools.map(t => t.name)).toEqual([
      'settings_get',
      'settings_update'
    ]);
  });
});
