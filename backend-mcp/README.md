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
