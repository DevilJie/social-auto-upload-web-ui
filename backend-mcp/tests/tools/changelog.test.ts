import { describe, it, expect } from 'vitest';
import { registerChangelogTools } from '../../src/tools/changelog';
import { BackendClient } from '../../src/client';

describe('changelog tools', () => {
  it('应该注册1个更新日志工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    registerChangelogTools(mockServer as any, mockClient);
    expect(tools).toHaveLength(1);
    expect(tools[0].name).toBe('changelog_list');
  });
});
