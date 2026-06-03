import { describe, it, expect } from 'vitest';
import { registerPublishTools } from '../../src/tools/publish';
import { BackendClient } from '../../src/client';

describe('publish tools', () => {
  it('应该注册2个发布相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];

    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };

    registerPublishTools(mockServer as any, mockClient);

    expect(tools).toHaveLength(2);
    expect(tools.map(t => t.name)).toEqual([
      'video_publish',
      'image_publish'
    ]);
  });
});
