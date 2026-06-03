import { describe, it, expect } from 'vitest';
import { registerMaterialTools } from '../../src/tools/materials';
import { BackendClient } from '../../src/client';

describe('material tools', () => {
  it('应该注册3个素材相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];

    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };

    registerMaterialTools(mockServer as any, mockClient);

    expect(tools).toHaveLength(3);
    expect(tools.map(t => t.name)).toEqual([
      'material_upload',
      'material_list',
      'material_delete'
    ]);
  });
});
