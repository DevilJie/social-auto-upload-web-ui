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
      timeout: 60000,
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

  async get<T>(path: string, params?: Record<string, string>): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.http.get(path, { params });
    return response.data;
  }

  async getStream(path: string, params?: Record<string, string>): Promise<string> {
    const response = await this.http.get(path, {
      params,
      responseType: 'stream',
      timeout: 120000, // 登录可能需要较长时间
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

  async post<T>(path: string, data?: any): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.http.post(path, data);
    return response.data;
  }

  async put<T>(path: string, data?: any): Promise<ApiResponse<T>> {
    const response: AxiosResponse<ApiResponse<T>> = await this.http.put(path, data);
    return response.data;
  }

  async delete<T>(path: string): Promise<ApiResponse<T>> {
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
