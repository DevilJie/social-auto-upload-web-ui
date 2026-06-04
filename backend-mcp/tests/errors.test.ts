import { describe, it, expect } from 'vitest';
import { translateError, ErrorCodes, type McpError } from '../src/errors';

describe('translateError', () => {
  it('Flask 400 + "缺少必填字段" → MISSING_REQUIRED_FIELD', () => {
    const e = translateError({ code: 400, msg: '缺少必填字段: type', data: null });
    expect(e.code).toBe(4001);
    expect(e.error).toBe('MISSING_REQUIRED_FIELD');
    expect(e.retryable).toBe(false);
  });

  it('Flask 401 + Cookie 失效 → AUTH_FAILED + retryable', () => {
    const e = translateError({ code: 401, msg: 'Cookie 已失效', data: null });
    expect(e.code).toBe(4011);
    expect(e.error).toBe('AUTH_FAILED');
    expect(e.retryable).toBe(true);
  });

  it('Flask 404 → ENDPOINT_NOT_FOUND', () => {
    const e = translateError({ code: 404, msg: '素材不存在', data: null });
    expect(e.code).toBe(4003);
    expect(e.error).toBe('MATERIAL_NOT_FOUND');
  });

  it('Flask 500 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 500, msg: '数据库连接失败', data: null });
    expect(e.code).toBe(5001);
    expect(e.error).toBe('INTERNAL_ERROR');
    expect(e.retryable).toBe(false);
  });

  it('网络错误（无响应）→ NETWORK_ERROR', () => {
    const e = translateError(null, new Error('ECONNREFUSED'));
    expect(e.code).toBe(6001);
    expect(e.error).toBe('NETWORK_ERROR');
    expect(e.retryable).toBe(true);
  });

  it('未知错误码 → INTERNAL_ERROR', () => {
    const e = translateError({ code: 418, msg: '我是茶壶', data: null });
    expect(e.code).toBe(5001);
  });
});
