import initSqlJs, { Database } from 'sql.js';

export class AuthManager {
  private token: string = '';
  private dbPath: string;
  private db: Database | null = null;

  constructor(dbPath: string) {
    this.dbPath = dbPath;
  }

  async init(): Promise<void> {
    try {
      const SQL = await initSqlJs();

      // 如果是内存数据库或者文件不存在，创建新数据库
      if (this.dbPath === ':memory:') {
        this.db = new SQL.Database();
        // 创建 settings 表用于测试
        this.db.run("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)");
      } else {
        // 尝试读取现有数据库文件
        const fs = await import('fs');
        if (fs.existsSync(this.dbPath)) {
          const fileBuffer = fs.readFileSync(this.dbPath);
          this.db = new SQL.Database(fileBuffer);
        } else {
          this.db = new SQL.Database();
        }
      }

      this.loadToken();
    } catch (error) {
      console.error('Failed to initialize auth database:', error);
    }
  }

  private loadToken(): void {
    if (!this.db) return;

    try {
      const result = this.db.exec(
        "SELECT value FROM settings WHERE key = 'mcp_api_token'"
      );

      if (result.length > 0 && result[0].values.length > 0) {
        this.token = result[0].values[0][0] as string;
      }
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
