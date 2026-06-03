import { describe, it, expect } from 'vitest';
import { createMcpServer } from '../src/server';

describe('MCP Server', () => {
  it('应该创建MCP服务器实例', () => {
    const server = createMcpServer({
      backendUrl: 'http://localhost:5409',
      dbPath: ':memory:',
    });

    expect(server).toBeDefined();
  });
});
