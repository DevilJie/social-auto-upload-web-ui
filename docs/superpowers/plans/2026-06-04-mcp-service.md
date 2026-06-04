# MCP服务实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建一个MCP服务，将Flask后端的功能通过MCP协议暴露给AI客户端

**Architecture:** 中转模式，MCP服务接收JSON-RPC请求，转发到Flask后端HTTP API，返回结果。支持stdio和SSE两种传输方式。

**Tech Stack:** Node.js + TypeScript + @modelcontextprotocol/sdk + axios + better-sqlite3

---

## 文件结构

```
backend-mcp/
├── package.json                    # 项目配置和依赖
├── tsconfig.json                   # TypeScript配置
├── .env.example                    # 环境变量示例
├── .gitignore                      # Git忽略文件
├── src/
│   ├── index.ts                    # 入口文件，启动MCP服务
│   ├── config.ts                   # 配置管理
│   ├── auth.ts                     # Token认证模块
│   ├── client.ts                   # Flask后端HTTP客户端
│   ├── server.ts                   # MCP服务器配置和工具注册
│   └── tools/
│       ├── accounts.ts             # 账号管理工具
│       ├── materials.ts            # 素材管理工具
│       ├── drafts.ts               # 草稿箱工具
│       ├── publish.ts              # 发布工具（视频+图文）
│       └── settings.ts             # 系统设置工具
└── tests/
    ├── auth.test.ts                # 认证模块测试
    ├── client.test.ts              # HTTP客户端测试
    └── tools/
        ├── accounts.test.ts        # 账号工具测试
        ├── materials.test.ts       # 素材工具测试
        ├── drafts.test.ts          # 草稿工具测试
        ├── publish.test.ts         # 发布工具测试
        └── settings.test.ts        # 设置工具测试
```

---

### Task 1: 项目初始化

**Files:**
- Create: `backend-mcp/package.json`
- Create: `backend-mcp/tsconfig.json`
- Create: `backend-mcp/.env.example`
- Create: `backend-mcp/.gitignore`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "social-auto-upload-mcp",
  "version": "1.0.0",
  "description": "MCP服务 - 社交媒体自动上传工具",
  "main": "dist/index.js",
  "scripts": {
    "dev": "tsx watch src/index.ts",
    "build": "tsc",
    "start": "node dist/index.js",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0",
    "axios": "^1.6.0",
    "better-sqlite3": "^11.0.0",
    "dotenv": "^16.3.0",
    "form-data": "^4.0.0"
  },
  "devDependencies": {
    "@types/better-sqlite3": "^7.6.0",
    "@types/node": "^20.0.0",
    "tsx": "^4.0.0",
    "typescript": "^5.3.0",
    "vitest": "^1.0.0"
  }
}
```

- [ ] **Step 2: 创建 tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "commonjs",
    "lib": ["ES2022"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

- [ ] **Step 3: 创建 .env.example**

```env
# Flask后端地址
BACKEND_URL=http://localhost:5409

# MCP服务端口（SSE模式）
MCP_PORT=5410

# 传输模式：stdio | sse | both
TRANSPORT_MODE=both

# 数据库路径（用于读取Token）
DB_PATH=../data/db/database.db
```

- [ ] **Step 4: 创建 .gitignore**

```
node_modules/
dist/
.env
*.js
*.js.map
*.d.ts
!src/**/*.ts
```

- [ ] **Step 5: 安装依赖并提交**

```bash
cd backend-mcp && npm install
git add package.json package-lock.json tsconfig.json .env.example .gitignore
git commit -m "feat(mcp): 初始化MCP服务项目"
```

---

### Task 2: 配置管理模块

**Files:**
- Create: `backend-mcp/src/config.ts`
- Test: `backend-mcp/tests/config.test.ts`

- [ ] **Step 1: 编写配置模块测试**

```typescript
// tests/config.test.ts
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/config.test.ts
```

- [ ] **Step 3: 实现配置模块**

```typescript
// src/config.ts
import dotenv from 'dotenv';
import path from 'path';

dotenv.config();

export interface Config {
  backendUrl: string;
  mcpPort: number;
  transportMode: 'stdio' | 'sse' | 'both';
  dbPath: string;
}

export function loadConfig(): Config {
  return {
    backendUrl: process.env.BACKEND_URL || 'http://localhost:5409',
    mcpPort: parseInt(process.env.MCP_PORT || '5410', 10),
    transportMode: (process.env.TRANSPORT_MODE as Config['transportMode']) || 'both',
    dbPath: process.env.DB_PATH || path.resolve(__dirname, '../../data/db/database.db'),
  };
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/config.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/config.ts backend-mcp/tests/config.test.ts
git commit -m "feat(mcp): 添加配置管理模块"
```

---

### Task 3: Token认证模块

**Files:**
- Create: `backend-mcp/src/auth.ts`
- Test: `backend-mcp/tests/auth.test.ts`

- [ ] **Step 1: 编写认证模块测试**

```typescript
// tests/auth.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { AuthManager } from '../src/auth';

describe('auth', () => {
  const mockDbPath = ':memory:';

  it('应该从数据库读取Token', () => {
    const auth = new AuthManager(mockDbPath);
    // 模拟数据库中有token
    auth.setTokenForTest('test-token-123');
    
    expect(auth.getToken()).toBe('test-token-123');
  });

  it('应该验证有效的Token', () => {
    const auth = new AuthManager(mockDbPath);
    auth.setTokenForTest('valid-token');
    
    expect(auth.validateToken('valid-token')).toBe(true);
  });

  it('应该拒绝无效的Token', () => {
    const auth = new AuthManager(mockDbPath);
    auth.setTokenForTest('valid-token');
    
    expect(auth.validateToken('invalid-token')).toBe(false);
  });

  it('未配置Token时应该跳过验证', () => {
    const auth = new AuthManager(mockDbPath);
    auth.setTokenForTest('');
    
    expect(auth.validateToken('any-token')).toBe(true);
    expect(auth.isAuthEnabled()).toBe(false);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/auth.test.ts
```

- [ ] **Step 3: 实现认证模块**

```typescript
// src/auth.ts
import Database from 'better-sqlite3';

export class AuthManager {
  private token: string = '';
  private dbPath: string;

  constructor(dbPath: string) {
    this.dbPath = dbPath;
    this.loadToken();
  }

  private loadToken(): void {
    try {
      const db = new Database(this.dbPath, { readonly: true });
      const row = db.prepare(
        "SELECT value FROM settings WHERE key = 'mcp_api_token'"
      ).get() as { value: string } | undefined;
      
      if (row) {
        this.token = row.value;
      }
      db.close();
    } catch (error) {
      console.error('Failed to load MCP token:', error);
    }
  }

  getToken(): string {
    return this.token;
  }

  isAuthEnabled(): boolean {
    return this.token.length > 0;
  }

  validateToken(providedToken: string): boolean {
    if (!this.isAuthEnabled()) {
      return true;
    }
    return this.token === providedToken;
  }

  // 用于测试
  setTokenForTest(token: string): void {
    this.token = token;
  }
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/auth.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/auth.ts backend-mcp/tests/auth.test.ts
git commit -m "feat(mcp): 添加Token认证模块"
```

---

### Task 4: HTTP客户端模块

**Files:**
- Create: `backend-mcp/src/client.ts`
- Test: `backend-mcp/tests/client.test.ts`

- [ ] **Step 1: 编写HTTP客户端测试**

```typescript
// tests/client.test.ts
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/client.test.ts
```

- [ ] **Step 3: 实现HTTP客户端**

```typescript
// src/client.ts
import axios, { AxiosInstance, AxiosResponse } from 'axios';
import FormData from 'form-data';
import fs from 'fs';
import path from 'path';

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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/client.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/client.ts backend-mcp/tests/client.test.ts
git commit -m "feat(mcp): 添加HTTP客户端模块"
```

---

### Task 5: 账号管理工具

**Files:**
- Create: `backend-mcp/src/tools/accounts.ts`
- Test: `backend-mcp/tests/tools/accounts.test.ts`

- [ ] **Step 1: 编写账号工具测试**

```typescript
// tests/tools/accounts.test.ts
import { describe, it, expect, vi } from 'vitest';
import { registerAccountTools } from '../../src/tools/accounts';
import { BackendClient } from '../../src/client';

describe('account tools', () => {
  it('应该注册4个账号相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    
    registerAccountTools(mockServer as any, mockClient);
    
    expect(tools).toHaveLength(4);
    expect(tools.map(t => t.name)).toEqual([
      'account_login',
      'account_list',
      'account_check',
      'account_delete'
    ]);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/tools/accounts.test.ts
```

- [ ] **Step 3: 实现账号管理工具**

```typescript
// src/tools/accounts.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerAccountTools(server: McpServer, client: BackendClient): void {
  // 账号登录
  server.tool(
    'account_login',
    '登录指定平台的账号，会打开浏览器进行登录',
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      account_id: z.string().optional().describe('账号ID（可选，用于更新已有账号）'),
    },
    async ({ type, account_id }) => {
      try {
        const params: Record<string, string> = { type: String(type), id: '' };
        if (account_id) {
          params.account_id = account_id;
        }
        
        const response = await client.get('/login', params);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `登录失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 账号列表
  server.tool(
    'account_list',
    '获取所有账号列表',
    {},
    async () => {
      try {
        const response = await client.get('/getAccounts');
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取账号列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 检查账号状态
  server.tool(
    'account_check',
    '检查指定账号的Cookie是否有效',
    {
      id: z.string().describe('账号ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get('/checkAccount', { id });
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `检查账号状态失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 删除账号
  server.tool(
    'account_delete',
    '删除指定账号',
    {
      id: z.string().describe('账号ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get('/deleteAccount', { id });
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `删除账号失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/tools/accounts.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/tools/accounts.ts backend-mcp/tests/tools/accounts.test.ts
git commit -m "feat(mcp): 添加账号管理工具"
```

---

### Task 6: 素材管理工具

**Files:**
- Create: `backend-mcp/src/tools/materials.ts`
- Test: `backend-mcp/tests/tools/materials.test.ts`

- [ ] **Step 1: 编写素材工具测试**

```typescript
// tests/tools/materials.test.ts
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/tools/materials.test.ts
```

- [ ] **Step 3: 实现素材管理工具**

```typescript
// src/tools/materials.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerMaterialTools(server: McpServer, client: BackendClient): void {
  // 上传素材
  server.tool(
    'material_upload',
    '上传图片或视频素材',
    {
      file_path: z.string().describe('本地文件路径'),
    },
    async ({ file_path }) => {
      try {
        const response = await client.uploadFile('/api/materials/upload', file_path);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `上传素材失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 素材列表
  server.tool(
    'material_list',
    '获取素材列表，支持分页和筛选',
    {
      type: z.enum(['all', 'video', 'image']).optional().describe('素材类型筛选'),
      keyword: z.string().optional().describe('文件名搜索关键词'),
      page: z.number().optional().describe('页码（从1开始）'),
      page_size: z.number().optional().describe('每页数量（默认24）'),
    },
    async ({ type, keyword, page, page_size }) => {
      try {
        const params: Record<string, string> = {};
        if (type) params.type = type;
        if (keyword) params.keyword = keyword;
        if (page) params.page = String(page);
        if (page_size) params.page_size = String(page_size);
        
        const response = await client.get('/api/materials/list', params);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取素材列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 删除素材
  server.tool(
    'material_delete',
    '删除指定素材',
    {
      id: z.string().describe('素材ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.delete(`/api/materials/${id}`);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `删除素材失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/tools/materials.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/tools/materials.ts backend-mcp/tests/tools/materials.test.ts
git commit -m "feat(mcp): 添加素材管理工具"
```

---

### Task 7: 草稿箱工具

**Files:**
- Create: `backend-mcp/src/tools/drafts.ts`
- Test: `backend-mcp/tests/tools/drafts.test.ts`

- [ ] **Step 1: 编写草稿箱工具测试**

```typescript
// tests/tools/drafts.test.ts
import { describe, it, expect } from 'vitest';
import { registerDraftTools } from '../../src/tools/drafts';
import { BackendClient } from '../../src/client';

describe('draft tools', () => {
  it('应该注册4个草稿相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    
    registerDraftTools(mockServer as any, mockClient);
    
    expect(tools).toHaveLength(4);
    expect(tools.map(t => t.name)).toEqual([
      'draft_list',
      'draft_get',
      'draft_create',
      'draft_delete'
    ]);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/tools/drafts.test.ts
```

- [ ] **Step 3: 实现草稿箱工具**

```typescript
// src/tools/drafts.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerDraftTools(server: McpServer, client: BackendClient): void {
  // 草稿列表
  server.tool(
    'draft_list',
    '获取草稿列表，支持按类型筛选',
    {
      type: z.enum(['video', 'image']).optional().describe('草稿类型筛选'),
    },
    async ({ type }) => {
      try {
        const params: Record<string, string> = {};
        if (type) params.type = type;
        
        const response = await client.get('/api/v2/drafts', params);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取草稿列表失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 获取草稿详情
  server.tool(
    'draft_get',
    '获取指定草稿的详细信息',
    {
      id: z.string().describe('草稿ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.get(`/api/v2/drafts/${id}`);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取草稿详情失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 创建草稿
  server.tool(
    'draft_create',
    '创建新草稿',
    {
      type: z.enum(['video', 'image']).describe('草稿类型'),
      draft_data: z.record(z.any()).describe('草稿数据JSON'),
    },
    async ({ type, draft_data }) => {
      try {
        const response = await client.post('/api/v2/drafts', {
          type,
          draft_data,
        });
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `创建草稿失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 删除草稿
  server.tool(
    'draft_delete',
    '删除指定草稿',
    {
      id: z.string().describe('草稿ID'),
    },
    async ({ id }) => {
      try {
        const response = await client.delete(`/api/v2/drafts/${id}`);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `删除草稿失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/tools/drafts.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/tools/drafts.ts backend-mcp/tests/tools/drafts.test.ts
git commit -m "feat(mcp): 添加草稿箱工具"
```

---

### Task 8: 发布工具

**Files:**
- Create: `backend-mcp/src/tools/publish.ts`
- Test: `backend-mcp/tests/tools/publish.test.ts`

- [ ] **Step 1: 编写发布工具测试**

```typescript
// tests/tools/publish.test.ts
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/tools/publish.test.ts
```

- [ ] **Step 3: 实现发布工具**

```typescript
// src/tools/publish.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerPublishTools(server: McpServer, client: BackendClient): void {
  // 视频发布
  server.tool(
    'video_publish',
    '发布视频到指定平台',
    {
      type: z.number().min(1).max(10).describe('平台类型: 1=小红书, 2=视频号, 3=抖音, 4=快手, 5=B站, 6=百家号, 7=TikTok, 8=YouTube, 9=腾讯视频, 10=爱奇艺'),
      title: z.string().describe('视频标题'),
      fileList: z.array(z.string()).describe('视频文件路径列表'),
      accountList: z.array(z.string()).describe('账号cookie文件路径列表'),
      tags: z.array(z.string()).optional().describe('标签列表'),
      description: z.string().optional().describe('视频描述'),
      category: z.string().optional().describe('视频分类'),
      thumbnail: z.string().optional().describe('封面图路径'),
      thumbnailLandscape: z.string().optional().describe('横版封面路径'),
      thumbnailPortrait: z.string().optional().describe('竖版封面路径'),
      enableTimer: z.boolean().optional().describe('是否定时发布'),
      scheduleTime: z.string().optional().describe('定时发布时间'),
      videosPerDay: z.number().optional().describe('每天发布数量'),
      dailyTimes: z.array(z.string()).optional().describe('每天发布时间点'),
      startDays: z.number().optional().describe('开始天数'),
      productLink: z.string().optional().describe('商品链接'),
      productTitle: z.string().optional().describe('商品标题'),
      aiContent: z.string().optional().describe('AI生成内容'),
      creationDeclaration: z.string().optional().describe('创作声明'),
      riskWarning: z.string().optional().describe('风险提示'),
      enableCashActivity: z.boolean().optional().describe('是否启用现金活动'),
      supplementaryDeclaration: z.string().optional().describe('补充声明'),
      isDraft: z.boolean().optional().describe('是否保存为草稿'),
      audience: z.string().optional().describe('受众类型'),
      alteredContent: z.boolean().optional().describe('是否altered content'),
      hotspot: z.string().optional().describe('热点'),
      tag_type: z.string().optional().describe('标签类型'),
      tag_value: z.string().optional().describe('标签值'),
      mini_link: z.string().optional().describe('小程序链接'),
      mix_id: z.string().optional().describe('合集ID'),
      activities: z.array(z.any()).optional().describe('活动列表'),
    },
    async (params) => {
      try {
        const response = await client.post('/postVideo', params);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `发布视频失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 图文发布
  server.tool(
    'image_publish',
    '发布图文内容到指定平台',
    {
      image_ids: z.array(z.string()).describe('图片ID列表'),
      account_configs: z.array(z.object({
        account_id: z.number().describe('账号ID'),
        platform: z.string().describe('平台类型'),
        filePath: z.string().describe('cookie文件路径'),
        title: z.string().optional().describe('标题'),
        description: z.string().optional().describe('描述'),
        tags: z.array(z.string()).optional().describe('标签列表'),
        cover_path: z.string().optional().describe('封面路径'),
        mix_id: z.string().optional().describe('合集ID'),
        music_name: z.string().optional().describe('音乐名称'),
        hotspot: z.string().optional().describe('热点'),
        tag_type: z.string().optional().describe('标签类型'),
        tag_value: z.string().optional().describe('标签值'),
        mini_link: z.string().optional().describe('小程序链接'),
        scheduleTime: z.string().optional().describe('定时发布时间'),
        aiContent: z.string().optional().describe('AI生成内容'),
        isOriginal: z.boolean().optional().describe('是否原创'),
        activities: z.array(z.any()).optional().describe('活动列表'),
        music_id: z.string().optional().describe('音乐ID'),
        music_title: z.string().optional().describe('音乐标题'),
        dry_run: z.boolean().optional().describe('是否试运行'),
      })).describe('账号配置列表'),
    },
    async (params) => {
      try {
        const response = await client.post('/api/image-publish/publish', params);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `发布图文失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/tools/publish.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/tools/publish.ts backend-mcp/tests/tools/publish.test.ts
git commit -m "feat(mcp): 添加发布工具"
```

---

### Task 9: 系统设置工具

**Files:**
- Create: `backend-mcp/src/tools/settings.ts`
- Test: `backend-mcp/tests/tools/settings.test.ts`

- [ ] **Step 1: 编写设置工具测试**

```typescript
// tests/tools/settings.test.ts
import { describe, it, expect } from 'vitest';
import { registerSettingsTools } from '../../src/tools/settings';
import { BackendClient } from '../../src/client';

describe('settings tools', () => {
  it('应该注册2个设置相关工具', () => {
    const mockClient = {} as BackendClient;
    const tools: any[] = [];
    
    const mockServer = {
      tool: (name: string, description: string, schema: any, handler: Function) => {
        tools.push({ name, description, schema, handler });
      }
    };
    
    registerSettingsTools(mockServer as any, mockClient);
    
    expect(tools).toHaveLength(2);
    expect(tools.map(t => t.name)).toEqual([
      'settings_get',
      'settings_update'
    ]);
  });
});
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/tools/settings.test.ts
```

- [ ] **Step 3: 实现系统设置工具**

```typescript
// src/tools/settings.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from '../client.js';
import { z } from 'zod';

export function registerSettingsTools(server: McpServer, client: BackendClient): void {
  // 获取系统设置
  server.tool(
    'settings_get',
    '获取所有系统设置',
    {},
    async () => {
      try {
        const response = await client.get('/api/v2/settings');
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `获取系统设置失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );

  // 更新系统设置
  server.tool(
    'settings_update',
    '更新系统设置',
    {
      settings: z.record(z.any()).describe('要更新的设置键值对'),
    },
    async ({ settings }) => {
      try {
        const response = await client.put('/api/v2/settings', settings);
        
        return {
          content: [{
            type: 'text' as const,
            text: JSON.stringify(response, null, 2)
          }]
        };
      } catch (error: any) {
        return {
          content: [{
            type: 'text' as const,
            text: `更新系统设置失败: ${error.message}`
          }],
          isError: true
        };
      }
    }
  );
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/tools/settings.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/tools/settings.ts backend-mcp/tests/tools/settings.test.ts
git commit -m "feat(mcp): 添加系统设置工具"
```

---

### Task 10: MCP服务器主模块

**Files:**
- Create: `backend-mcp/src/server.ts`
- Test: `backend-mcp/tests/server.test.ts`

- [ ] **Step 1: 编写服务器模块测试**

```typescript
// tests/server.test.ts
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
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend-mcp && npm test -- tests/server.test.ts
```

- [ ] **Step 3: 实现MCP服务器主模块**

```typescript
// src/server.ts
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from './client.js';
import { AuthManager } from './auth.js';
import { registerAccountTools } from './tools/accounts.js';
import { registerMaterialTools } from './tools/materials.js';
import { registerDraftTools } from './tools/drafts.js';
import { registerPublishTools } from './tools/publish.js';
import { registerSettingsTools } from './tools/settings.js';

export interface ServerConfig {
  backendUrl: string;
  dbPath: string;
}

export function createMcpServer(config: ServerConfig): McpServer {
  const server = new McpServer({
    name: 'social-auto-upload',
    version: '1.0.0',
  });

  const client = new BackendClient(config.backendUrl);
  
  // 注册所有工具
  registerAccountTools(server, client);
  registerMaterialTools(server, client);
  registerDraftTools(server, client);
  registerPublishTools(server, client);
  registerSettingsTools(server, client);

  return server;
}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend-mcp && npm test -- tests/server.test.ts
```

- [ ] **Step 5: 提交**

```bash
git add backend-mcp/src/server.ts backend-mcp/tests/server.test.ts
git commit -m "feat(mcp): 添加MCP服务器主模块"
```

---

### Task 11: 入口文件和启动逻辑

**Files:**
- Create: `backend-mcp/src/index.ts`

- [ ] **Step 1: 实现入口文件**

```typescript
// src/index.ts
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import express from 'express';
import { loadConfig } from './config.js';
import { createMcpServer } from './server.js';

async function main() {
  const config = loadConfig();
  const server = createMcpServer({
    backendUrl: config.backendUrl,
    dbPath: config.dbPath,
  });

  console.log(`[MCP] Starting in ${config.transportMode} mode...`);

  if (config.transportMode === 'stdio' || config.transportMode === 'both') {
    const stdioTransport = new StdioServerTransport();
    await server.connect(stdioTransport);
    console.log('[MCP] Stdio transport connected');
  }

  if (config.transportMode === 'sse' || config.transportMode === 'both') {
    const app = express();
    
    app.get('/sse', async (req, res) => {
      const sseTransport = new SSEServerTransport('/messages', res);
      await server.connect(sseTransport);
    });

    app.post('/messages', async (req, res) => {
      // SSE消息处理由SDK内部管理
      res.status(200).json({ ok: true });
    });

    app.listen(config.mcpPort, () => {
      console.log(`[MCP] SSE server listening on http://localhost:${config.mcpPort}`);
      console.log(`[MCP] SSE endpoint: http://localhost:${config.mcpPort}/sse`);
    });
  }

  console.log('[MCP] Server ready');
}

main().catch((error) => {
  console.error('[MCP] Fatal error:', error);
  process.exit(1);
});
```

- [ ] **Step 2: 更新package.json添加express依赖**

```bash
cd backend-mcp && npm install express @types/express
```

- [ ] **Step 3: 测试启动服务**

```bash
cd backend-mcp && npm run dev
```

- [ ] **Step 4: 提交**

```bash
git add backend-mcp/src/index.ts backend-mcp/package.json backend-mcp/package-lock.json
git commit -m "feat(mcp): 添加入口文件和启动逻辑"
```

---

### Task 12: 集成测试和文档

**Files:**
- Create: `backend-mcp/README.md`

- [ ] **Step 1: 创建README文档**

```markdown
# Social Auto Upload MCP Service

社交媒体自动上传工具的MCP服务，允许AI客户端通过MCP协议调用系统功能。

## 功能

- 账号管理（登录、列表、检查、删除）
- 素材管理（上传、列表、删除）
- 草稿箱（列表、创建、删除）
- 视频发布
- 图文发布
- 系统设置

## 安装

```bash
npm install
```

## 配置

复制 `.env.example` 为 `.env`，根据需要修改配置：

```env
BACKEND_URL=http://localhost:5409
MCP_PORT=5410
TRANSPORT_MODE=both
DB_PATH=../data/db/database.db
```

## 启动

```bash
# 开发模式
npm run dev

# 生产模式
npm run build
npm start
```

## 使用

### Claude Desktop 配置

在 Claude Desktop 的配置文件中添加：

```json
{
  "mcpServers": {
    "social-auto-upload": {
      "command": "node",
      "args": ["/path/to/backend-mcp/dist/index.js"],
      "env": {
        "TRANSPORT_MODE": "stdio"
      }
    }
  }
}
```

### SSE 模式连接

```bash
# 启动SSE服务
TRANSPORT_MODE=sse npm start

# 连接到 http://localhost:5410/sse
```

## API Token

在系统设置界面配置 MCP API Token，用于认证MCP客户端连接。
```

- [ ] **Step 2: 运行所有测试**

```bash
cd backend-mcp && npm test
```

- [ ] **Step 3: 构建项目**

```bash
cd backend-mcp && npm run build
```

- [ ] **Step 4: 提交**

```bash
git add backend-mcp/README.md
git commit -m "docs(mcp): 添加README文档"
```

---

## 完成

所有任务完成后，MCP服务即可使用。启动Flask后端后，启动MCP服务，AI客户端即可通过MCP协议调用系统功能。
