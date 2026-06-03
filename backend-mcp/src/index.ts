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

    // 存储活跃的SSE传输实例
    const transports: Map<string, SSEServerTransport> = new Map();

    app.get('/sse', async (req, res) => {
      const sseTransport = new SSEServerTransport('/messages', res);
      transports.set(sseTransport.sessionId, sseTransport);

      sseTransport.onclose = () => {
        transports.delete(sseTransport.sessionId);
      };

      await server.connect(sseTransport);
      await sseTransport.start();
    });

    app.post('/messages', async (req, res) => {
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
