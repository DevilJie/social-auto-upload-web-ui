import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { SSEServerTransport } from '@modelcontextprotocol/sdk/server/sse.js';
import express, { Request, Response, NextFunction } from 'express';
import { loadConfig } from './config.js';
import { createMcpServer } from './server.js';
import { AuthManager } from './auth.js';

async function main() {
  const config = loadConfig();
  const server = createMcpServer({
    backendUrl: config.backendUrl,
    dbPath: config.dbPath,
  });

  const auth = new AuthManager(config.dbPath);
  await auth.init();

  console.log(`[MCP] Starting in ${config.transportMode} mode...`);
  console.log(`[MCP] Backend URL: ${config.backendUrl}`);
  console.log(`[MCP] DB Path: ${config.dbPath}`);
  console.log(`[MCP] Auth enabled: ${auth.isAuthEnabled()}`);

  if (config.transportMode === 'stdio' || config.transportMode === 'both') {
    const stdioTransport = new StdioServerTransport();
    await server.connect(stdioTransport);
    console.log('[MCP] Stdio transport connected');
  }

  if (config.transportMode === 'sse' || config.transportMode === 'both') {
    const app = express();

    // 存储活跃的SSE传输实例
    const transports: Map<string, SSEServerTransport> = new Map();

    // SSE 端点鉴权：未配置 token 时放行；配置了则要求 Bearer header 或 ?token= query
    const requireAuth = (req: Request, res: Response, next: NextFunction) => {
      if (!auth.isAuthEnabled()) return next();
      const header = req.headers.authorization;
      const bearer = header?.startsWith('Bearer ') ? header.slice(7) : undefined;
      const token = bearer ?? (req.query.token as string | undefined);
      if (!auth.validateToken(token ?? '')) {
        res.status(401).json({ error: 'Invalid or missing MCP API token' });
        return;
      }
      next();
    };

    app.get('/sse', requireAuth, async (req, res) => {
      const sseTransport = new SSEServerTransport('/messages', res);
      transports.set(sseTransport.sessionId, sseTransport);

      sseTransport.onclose = () => {
        transports.delete(sseTransport.sessionId);
      };

      await server.connect(sseTransport);
      await sseTransport.start();
    });

    app.post('/messages', requireAuth, async (req, res) => {
      const sessionId = req.query.sessionId as string;
      const transport = transports.get(sessionId);
      if (transport) {
        await transport.handlePostMessage(req, res);
      } else {
        res.status(400).json({ error: 'No transport found for sessionId' });
      }
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
