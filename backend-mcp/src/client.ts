import axios, { AxiosInstance, AxiosResponse } from 'axios';
import FormData from 'form-data';
import fs from 'fs';

export interface ApiResponse<T = any> {
  code: number;
  msg?: string;
  data?: T;
}

export class BackendClient {
  private http: AxiosInstance;

  constructor(baseUrl: string) {
    this.http = axios.create({
      baseURL: baseUrl,
      timeout: 300000,
      headers: {
        'Content-Type': 'application/json',
      },
    });
  }

  buildUrl(path: string, params?: Record<string, string>): string {
    const url = new URL(path, this.http.defaults.baseURL);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, value);
      });
    }
    return url.toString();
  }

  async get<T = any>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.http.get(path, { params });
    return response.data;
  }

  async getStream(path: string, params?: Record<string, string>): Promise<string> {
    const response = await this.http.get(path, {
      params,
      responseType: 'stream',
      timeout: 300000, // 登录需要用户操作，设置5分钟超时
    });

    return new Promise((resolve, reject) => {
      const chunks: string[] = [];

      response.data.on('data', (chunk: Buffer) => {
        chunks.push(chunk.toString());
      });

      response.data.on('end', () => {
        resolve(chunks.join(''));
      });

      response.data.on('error', (err: Error) => {
        reject(err);
      });
    });
  }

  /**
   * 消费 SSE 流；每条消息回调一次，调用方返回非 undefined 值时立即 resolve 并断流。
   * Flask 的 sse_stream 是 while True 死循环，HTTP 响应永远不会自然 end——必须由调用方主动终态。
   * 5 分钟 timeout 仅作兜底，正常路径应在收到终态消息后立即返回。
   */
  async getSSE<T>(
    path: string,
    params: Record<string, string> | undefined,
    onMessage: (msg: any) => T | undefined
  ): Promise<T> {
    const response = await this.http.get(path, {
      params,
      responseType: 'stream',
      timeout: 300000,
    });

    return new Promise((resolve, reject) => {
      let buffer = '';
      let settled = false;

      const finish = (result: T) => {
        if (settled) return;
        settled = true;
        response.data.destroy();
        resolve(result);
      };

      const fail = (err: Error) => {
        if (settled) return;
        settled = true;
        response.data.destroy();
        reject(err);
      };

      response.data.on('data', (chunk: Buffer) => {
        if (settled) return;
        buffer += chunk.toString();
        // SSE 消息以 \n\n 分隔
        const parts = buffer.split('\n\n');
        buffer = parts.pop() ?? '';

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith('data: ')) continue;
          const content = line.slice(6);

          // 尝试解析为 JSON；失败则把原始字符串交给 onMessage
          let parsed: any = content;
          try {
            parsed = JSON.parse(content);
          } catch {
            // 不是 JSON，按原始字符串处理
          }

          try {
            const result = onMessage(parsed);
            if (result !== undefined) {
              finish(result);
              return;
            }
          } catch (err) {
            fail(err instanceof Error ? err : new Error(String(err)));
            return;
          }
        }
      });

      response.data.on('end', () => {
        fail(new Error('SSE stream ended without terminal message'));
      });

      response.data.on('error', (err: Error) => {
        fail(err);
      });
    });
  }

  async post<T = any>(path: string, data?: any, timeout?: number): Promise<ApiResponse<T>> {
    const config = timeout ? { timeout } : undefined;
    const response: AxiosResponse<ApiResponse<T>> = await this.http.post(path, data, config);
    return response.data;
  }

  async put<T = any>(path: string, data?: any): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.http.put(path, data);
    return response.data;
  }

  async delete<T = any>(path: string): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.http.delete(path);
    return response.data;
  }

  async uploadFile<T>(path: string, filePath: string, additionalFields?: Record<string, string>): Promise<ApiResponse<T>> {
    const form = new FormData();
    form.append('file', fs.createReadStream(filePath));

    if (additionalFields) {
      Object.entries(additionalFields).forEach(([key, value]) => {
        form.append(key, value);
      });
    }

    const response: AxiosResponse<ApiResponse<T>> = await this.http.post(path, form, {
      headers: form.getHeaders(),
    });
    return response.data;
  }
}
