// MCP 客户端冒烟测试：连接 SSE 端点 → 列工具 → 调一个工具
// 用法: node smoke-client.mjs [工具名] (默认 platform_list)
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { SSEClientTransport } from '@modelcontextprotocol/sdk/client/sse.js';

const url = process.env.MCP_URL || 'http://127.0.0.1:5410/sse';
const tool = process.argv[2] || 'platform_list';

const client = new Client({ name: 'smoke-client', version: '1.0.0' }, { capabilities: {} });
await client.connect(new SSEClientTransport(new URL(url)));
console.log(`[smoke] connected: ${url}`);

const { tools } = await client.listTools();
console.log(`[smoke] tools: ${tools.length}`);
console.log(`[smoke] names: ${tools.map(t => t.name).join(', ')}`);

const args = tool === 'platform_list' ? {} : {};
const res = await client.callTool({ name: tool, arguments: args });
const text = res.content?.[0]?.text ?? JSON.stringify(res);
const parsed = JSON.parse(text);
const plats = parsed?.data?.platforms;
if (plats) {
  console.log(`[smoke] callTool(${tool}) OK: ${plats.length} platforms — ` +
    plats.slice(0, 5).map(p => `${p.id}:${p.key}`).join(', ') + ' ...');
} else {
  console.log(`[smoke] callTool(${tool}) OK: ${text.slice(0, 400)}`);
}

await client.close();
console.log('[smoke] done');
