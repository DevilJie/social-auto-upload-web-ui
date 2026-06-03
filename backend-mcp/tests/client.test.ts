import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BackendClient } from '../src/client';

describe('BackendClient', () => {
  const baseUrl = 'http://localhost:5409';

  it('应该能创建客户端实例', () => {
    const client = new BackendClient(baseUrl);
    expect(client).toBeDefined();
  });

  it('应该正确格式化GET请求路径', () => {
    const client = new BackendClient(baseUrl);
    const url = client.buildUrl('/getAccounts', { id: '123' });
    expect(url).toBe('http://localhost:5409/getAccounts?id=123');
  });

  it('应该正确格式化多个查询参数', () => {
    const client = new BackendClient(baseUrl);
    const url = client.buildUrl('/api/materials/list', {
      type: 'video',
      page: '1',
      page_size: '24'
    });
    expect(url).toBe('http://localhost:5409/api/materials/list?type=video&page=1&page_size=24');
  });
});
