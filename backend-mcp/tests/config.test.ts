import { describe, it, expect, beforeEach } from 'vitest';
import { loadConfig } from '../src/config';

describe('config', () => {
  beforeEach(() => {
    delete process.env.BACKEND_URL;
    delete process.env.MCP_PORT;
    delete process.env.TRANSPORT_MODE;
    delete process.env.DB_PATH;
  });

  it('应该返回默认配置', () => {
    const config = loadConfig();
    expect(config.backendUrl).toBe('http://localhost:5409');
    expect(config.mcpPort).toBe(5410);
    expect(config.transportMode).toBe('both');
  });

  it('应该支持环境变量覆盖', () => {
    process.env.BACKEND_URL = 'http://localhost:8080';
    process.env.MCP_PORT = '3000';

    const config = loadConfig();
    expect(config.backendUrl).toBe('http://localhost:8080');
    expect(config.mcpPort).toBe(3000);
  });
});
