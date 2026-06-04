# MCP服务设计文档

## 概述

将现有Flask后端的功能通过MCP（Model Context Protocol）协议暴露给AI客户端，使AI助手能够直接调用系统的账号管理、素材管理、草稿箱、发布等功能。

## 架构设计

### 整体架构

```
┌─────────────────┐     MCP协议      ┌─────────────────┐     HTTP      ┌─────────────────┐
│   AI客户端       │ ───────────────→ │   backend-mcp   │ ────────────→ │   Flask后端     │
│ (Claude等)      │ ←─────────────── │   (Node.js)     │ ←──────────── │   (5409端口)    │
└─────────────────┘                  └─────────────────┘               └─────────────────┘
                                            │
                                            │ 直接读取
                                            ▼
                                     ┌─────────────────┐
                                     │   SQLite数据库   │
                                     │ (Token认证)      │
                                     └─────────────────┘
```

### 技术栈

- **运行时：** Node.js + TypeScript
- **MCP SDK：** @modelcontextprotocol/sdk
- **HTTP客户端：** axios
- **数据库：** better-sqlite3（读取Token）
- **传输方式：** stdio + SSE（可配置）

### 目录结构

```
backend-mcp/
├── package.json
├── tsconfig.json
├── src/
│   ├── index.ts          # MCP服务入口
│   ├── server.ts         # MCP服务器配置
│   ├── tools/            # MCP工具定义
│   │   ├── accounts.ts   # 账号管理工具
│   │   ├── materials.ts  # 素材管理工具
│   │   ├── drafts.ts     # 草稿箱工具
│   │   ├── publish.ts    # 发布工具（视频+图文）
│   │   └── settings.ts   # 系统设置工具
│   ├── client.ts         # Flask后端HTTP客户端
│   └── auth.ts           # Token认证中间件
├── .env.example          # 环境变量示例
└── README.md
```

## 功能设计

### MCP工具清单

#### 1. 账号管理

| 工具名 | 描述 | 参数 | 返回 |
|--------|------|------|------|
| `account_login` | 账号登录 | `type`: 平台类型(1-10), `account_id`: 账号ID(可选) | 登录状态（成功/失败/进行中） |
| `account_list` | 获取账号列表 | 无 | 账号列表 |
| `account_check` | 检查账号状态 | `id`: 账号ID | 账号状态 |
| `account_delete` | 删除账号 | `id`: 账号ID | 删除结果 |

**登录流程说明：**
- MCP服务调用Flask后端的`/login`接口
- Flask后端返回SSE流，MCP服务收集所有状态更新
- 登录完成后，返回最终状态（成功/失败）
- 如果需要扫码，会返回二维码信息供用户操作

#### 2. 素材管理

| 工具名 | 描述 | 参数 | 返回 |
|--------|------|------|------|
| `material_upload` | 上传素材 | `file_path`: 本地文件路径 | 上传结果（包含素材ID） |
| `material_list` | 获取素材列表 | `type`: all/video/image, `keyword`: 搜索关键词, `page`: 页码, `page_size`: 每页数量 | 素材列表 |
| `material_delete` | 删除素材 | `id`: 素材ID | 删除结果 |

**文件上传说明：**
- MCP服务读取本地文件，通过multipart/form-data转发到Flask后端
- 支持图片和视频文件
- 返回素材ID，后续发布时使用

#### 3. 草稿箱

| 工具名 | 描述 | 参数 | 返回 |
|--------|------|------|------|
| `draft_list` | 获取草稿列表 | `type`: video/image(可选) | 草稿列表 |
| `draft_create` | 创建草稿 | `type`: video/image, `draft_data`: 草稿数据 | 创建结果 |
| `draft_update` | 更新草稿 | `id`: 草稿ID, `draft_data`: 草稿数据 | 更新结果 |
| `draft_delete` | 删除草稿 | `id`: 草稿ID | 删除结果 |

#### 4. 视频发布

| 工具名 | 描述 | 参数 | 返回 |
|--------|------|------|------|
| `video_publish` | 发布视频 | 见下方详细参数 | 发布结果 |

**video_publish 参数：**
- `type`: 平台类型(1-10)
- `title`: 标题
- `fileList`: 视频文件路径列表
- `tags`: 标签列表
- `accountList`: 账号cookie文件路径列表
- `category`: 分类
- `description`: 描述
- `thumbnail`: 封面路径
- `thumbnailLandscape`: 横版封面路径
- `thumbnailPortrait`: 竖版封面路径
- `enableTimer`: 是否定时发布
- `scheduleTime`: 定时发布时间
- `videosPerDay`: 每天发布数量
- `dailyTimes`: 每天发布时间点
- `startDays`: 开始天数
- `productLink`: 商品链接
- `productTitle`: 商品标题
- `aiContent`: AI生成内容
- `creationDeclaration`: 创作声明
- `riskWarning`: 风险提示
- `enableCashActivity`: 是否启用现金活动
- `supplementaryDeclaration`: 补充声明
- `isDraft`: 是否保存为草稿
- `audience`: 受众类型
- `alteredContent`: 是否 altered content
- `hotspot`: 热点
- `tag_type`: 标签类型
- `tag_value`: 标签值
- `mini_link`: 小程序链接
- `mix_id`: 合集ID
- `activities`: 活动列表

#### 5. 图文发布

| 工具名 | 描述 | 参数 | 返回 |
|--------|------|------|------|
| `image_publish` | 发布图文 | 见下方详细参数 | 发布结果 |

**image_publish 参数：**
- `image_ids`: 图片ID列表
- `account_configs`: 账号配置列表，每个配置包含：
  - `account_id`: 账号ID
  - `platform`: 平台类型
  - `filePath`: cookie文件路径
  - `title`: 标题
  - `description`: 描述
  - `tags`: 标签列表
  - `cover_path`: 封面路径
  - `mix_id`: 合集ID
  - `music_name`: 音乐名称
  - `hotspot`: 热点
  - `tag_type`: 标签类型
  - `tag_value`: 标签值
  - `mini_link`: 小程序链接
  - `scheduleTime`: 定时发布时间
  - `aiContent`: AI生成内容
  - `isOriginal`: 是否原创
  - `activities`: 活动列表
  - `music_id`: 音乐ID
  - `music_title`: 音乐标题
  - `dry_run`: 是否试运行

#### 6. 系统设置

| 工具名 | 描述 | 参数 | 返回 |
|--------|------|------|------|
| `settings_get` | 获取系统设置 | 无 | 系统设置 |
| `settings_update` | 更新系统设置 | `settings`: 设置对象 | 更新结果 |

## 认证设计

### Token存储

API Token存储在SQLite数据库的`settings`表中：
- key: `mcp_api_token`
- value: Token值

### 认证流程

1. MCP服务启动时，从SQLite数据库读取`mcp_api_token`
2. AI客户端连接时，在请求头中提供Token：`Authorization: Bearer <token>`
3. MCP服务验证Token是否匹配
4. 验证通过后，转发请求到Flask后端

### Token配置

用户可以在前端设置界面配置MCP API Token：
- 在"系统设置"页面添加"MCP API Token"配置项
- 保存后存储到SQLite的settings表

## 配置设计

### 环境变量

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

### 启动方式

```bash
# 开发模式
npm run dev

# 生产模式
npm run build
npm start

# 指定传输模式
TRANSPORT_MODE=stdio npm start
TRANSPORT_MODE=sse npm start
```

## 错误处理

### 错误码映射

| Flask后端HTTP状态码 | MCP错误类型 |
|---------------------|-------------|
| 400 | InvalidRequest |
| 401 | AuthenticationError |
| 404 | NotFound |
| 500 | InternalError |

### 错误响应格式

```json
{
  "error": {
    "type": "InvalidRequest",
    "message": "缺少必填字段: type"
  }
}
```

## 测试策略

### 单元测试

- 测试每个MCP工具的参数验证
- 测试Token认证逻辑
- 测试HTTP客户端的错误处理

### 集成测试

- 测试MCP服务与Flask后端的集成
- 测试stdio和SSE两种传输模式
- 测试完整的请求-响应流程

## 部署说明

### 开发环境

1. 进入`backend-mcp`目录
2. 安装依赖：`npm install`
3. 复制`.env.example`为`.env`，配置环境变量
4. 启动开发服务器：`npm run dev`

### 生产环境

1. 构建项目：`npm run build`
2. 启动服务：`npm start`
3. 或使用PM2管理进程：`pm2 start dist/index.js --name backend-mcp`

### 与Flask后端集成

在`start.sh`或`start.bat`中添加MCP服务启动命令：

```bash
# 启动Flask后端
cd backend && python app.py &

# 启动MCP服务
cd backend-mcp && npm start &
```

## 后续扩展

### 可能的增强功能

1. **批量操作** - 支持批量发布、批量删除等
2. **异步任务** - 支持长时间运行的任务，返回任务ID
3. **WebSocket** - 替代SSE，支持双向通信
4. **权限控制** - 细粒度的Token权限管理
5. **日志审计** - 记录所有MCP调用日志
