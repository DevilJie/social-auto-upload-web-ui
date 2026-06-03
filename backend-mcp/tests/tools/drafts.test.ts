import { describe, it, expect } from 'vitest';
import { registerDraftTools } from '../../src/tools/drafts';
import { BackendClient } from '../../src/client';

describe('draft tools', () => {
  it('应该注册4个草稿相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];

    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };

    registerDraftTools(mockServer as any, mockClient);

    expect(tools).toHaveLength(4);
    expect(tools.map(t => t.name)).toEqual([
      'draft_list',
      'draft_get',
      'draft_create',
      'draft_delete'
    ]);
  });
});
