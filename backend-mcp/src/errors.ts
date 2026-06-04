// 业务错误码表
export const ErrorCodes = {
  MISSING_REQUIRED_FIELD: 4001,
  INVALID_PLATFORM_TYPE: 4002,
  MATERIAL_NOT_FOUND: 4003,
  ACCOUNT_NOT_FOUND: 4004,
  DRAFT_NOT_FOUND: 4005,
  TASK_NOT_FOUND: 4006,
  AUTH_FAILED: 4011,
  ENDPOINT_NOT_FOUND: 4041,
  LOGIN_TIMEOUT: 4081,
  INTERNAL_ERROR: 5001,
  NETWORK_ERROR: 6001,
  STREAM_CLOSED: 6002,
} as const;

export interface McpError {
  code: number;
  error: string;
  message: string;
  suggestion: string;
  retryable: boolean;
  details?: Record<string, any>;
}

const SUGGESTIONS: Record<string, string> = {
  MISSING_REQUIRED_FIELD: '检查工具参数 schema，补全必填字段',
  INVALID_PLATFORM_TYPE: '使用 1-10 的平台 ID（1=小红书, 2=视频号, 3=抖音, ...）',
  MATERIAL_NOT_FOUND: '调 material_list 查可用素材 ID',
  ACCOUNT_NOT_FOUND: '调 account_list 查可用账号 ID',
  DRAFT_NOT_FOUND: '调 draft_list 查可用草稿 ID',
  TASK_NOT_FOUND: '调 task_list 查可用任务 ID',
  AUTH_FAILED: '调 account_login 重新登录该平台账号',
  ENDPOINT_NOT_FOUND: '检查后端版本；如持续请联系管理员',
  LOGIN_TIMEOUT: '重试登录，确认浏览器已打开且二维码有效',
  INTERNAL_ERROR: '查看后端 logs；如持续请联系管理员',
  NETWORK_ERROR: '检查后端是否在 5409 端口运行',
  STREAM_CLOSED: '重试调用；如持续请检查后端 SSE 端点',
};

function detectByMessage(msg: string): string {
  if (msg.includes('Cookie') || msg.includes('未登录') || msg.includes('登录')) {
    return 'AUTH_FAILED';
  }
  if (msg.includes('素材') || msg.includes('material')) return 'MATERIAL_NOT_FOUND';
  if (msg.includes('账号') || msg.includes('account')) return 'ACCOUNT_NOT_FOUND';
  if (msg.includes('草稿') || msg.includes('draft')) return 'DRAFT_NOT_FOUND';
  if (msg.includes('任务') || msg.includes('task')) return 'TASK_NOT_FOUND';
  if (msg.includes('缺少必填字段') || msg.includes('不能为空')) return 'MISSING_REQUIRED_FIELD';
  return 'INTERNAL_ERROR';
}

export function translateError(
  flaskResp: { code: number; msg?: string; data?: any } | null,
  networkError?: Error
): McpError {
  // 网络错误优先
  if (networkError || !flaskResp) {
    return {
      code: ErrorCodes.NETWORK_ERROR,
      error: 'NETWORK_ERROR',
      message: networkError?.message || '无法连接后端',
      suggestion: SUGGESTIONS.NETWORK_ERROR,
      retryable: true,
    };
  }

  const msg = flaskResp.msg || '未知错误';
  const httpCode = flaskResp.code;

  // HTTP 状态映射
  if (httpCode === 401) {
    return mkError('AUTH_FAILED', msg);
  }
  if (httpCode === 404) {
    return mkError(detectByMessage(msg), msg);
  }
  if (httpCode === 500) {
    return mkError('INTERNAL_ERROR', msg);
  }
  if (httpCode === 400) {
    return mkError(detectByMessage(msg), msg);
  }
  return mkError('INTERNAL_ERROR', msg);
}

function mkError(symbol: string, msg: string): McpError {
  return {
    code: (ErrorCodes as any)[symbol] ?? 5001,
    error: symbol,
    message: msg,
    suggestion: SUGGESTIONS[symbol] ?? SUGGESTIONS.INTERNAL_ERROR,
    retryable: symbol === 'AUTH_FAILED' || symbol === 'NETWORK_ERROR' || symbol === 'STREAM_CLOSED' || symbol === 'LOGIN_TIMEOUT',
  };
}

export function formatErrorResult(err: McpError) {
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(err, null, 2) }],
    isError: true,
  };
}
