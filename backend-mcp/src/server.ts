import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from './client.js';
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
