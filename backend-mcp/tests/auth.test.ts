import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthManager } from '../src/auth';

describe('auth', () => {
  const mockDbPath = ':memory:';

  it('应该从数据库读取Token', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    // 模拟数据库中有token
    auth.setTokenForTest('test-token-123');

    expect(auth.getToken()).toBe('test-token-123');
  });

  it('应该验证有效的Token', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('valid-token');

    expect(auth.validateToken('valid-token')).toBe(true);
  });

  it('应该拒绝无效的Token', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('valid-token');

    expect(auth.validateToken('invalid-token')).toBe(false);
  });

  it('未配置Token时应该跳过验证', async () => {
    const auth = new AuthManager(mockDbPath);
    await auth.init();
    auth.setTokenForTest('');

    expect(auth.validateToken('any-token')).toBe(true);
    expect(auth.isAuthEnabled()).toBe(false);
  });
});
