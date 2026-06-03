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
