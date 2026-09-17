import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { BackendClient } from './client.js';
import { registerAccountTools } from './tools/accounts.js';
import { registerMaterialTools } from './tools/materials.js';
import { registerDraftTools } from './tools/drafts.js';
import { registerPublishTools } from './tools/publish.js';
import { registerSettingsTools } from './tools/settings.js';
import { registerTaskTools } from './tools/tasks.js';
import { registerPublishExtraTools } from './tools/publish_extra.js';
import { registerChangelogTools } from './tools/changelog.js';
import { registerPlatformTools } from './tools/platforms.js';
import { registerFrameTools } from './tools/frames.js';
import { registerHelperQueryTools } from './tools/helper_query.js';

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
  registerPlatformTools(server, client);      // 平台元数据 / API 目录 / 通用调用
  registerAccountTools(server, client);       // 账号 + 标签 + Cookie
  registerMaterialTools(server, client);      // 素材
  registerFrameTools(server, client);         // 视频抽帧
  registerDraftTools(server, client);         // 草稿
  registerPublishTools(server, client);       // 发布（与网页同链路）
  registerHelperQueryTools(server, client);   // 发布辅助查询（热点/音乐/合集/位置）
  registerSettingsTools(server, client);      // 设置
  registerTaskTools(server, client);          // 任务
  registerPublishExtraTools(server, client);  // 历史/统计/模板
  registerChangelogTools(server, client);     // 更新日志

  return server;
}
