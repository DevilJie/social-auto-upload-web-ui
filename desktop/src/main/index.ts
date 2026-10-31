import { app, BrowserWindow, shell, dialog, ipcMain } from 'electron';
import * as path from 'path';
import { initLogger, log, closeLogger } from './log';
import { resolvePaths, setActiveDataDir, resetPathsCache, dumpPaths } from './paths';
import { RuntimeManager } from './runtime';
import { startBackend, BackendHandle } from './backend';
import { runProfileGate, needsProfileGate, injectHubButton } from './wizard';
import { Profile, readRegistry, writeRegistry } from './profiles';
import { isMcpRunning, getMcpPort, startMcp, stopMcp } from './mcp';

const SHELL_VERSION = '1.3.0-alpha.1';
let mainWindow: BrowserWindow | null = null;
let backend: BackendHandle | null = null;

// 单实例锁：第二个实例触发 first 实例的 second-instance
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
  bootstrap().catch(async (e) => {
    const msg = e?.stack ?? String(e);
    log('[FATAL]', msg);
    // 兜底清理子进程，绝不留孤儿
    try { backend?.stop(); } catch {}
    await showFatal(msg);
    app.exit(1);
  });
}

const LOADING_HTML = `<!doctype html><html><head><meta charset='utf-8'>
<style>
  body{margin:0;font-family:'Microsoft YaHei',system-ui,sans-serif;background:linear-gradient(160deg,#4f46e5,#2563eb 55%,#06b6d4);
       color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;}
  .box{text-align:center;}
  h1{font-size:42px;margin:0 0 12px;letter-spacing:2px;}
  p{opacity:.85;margin:4px 0;font-size:14px;}
  .spin{width:34px;height:34px;border:3px solid rgba(255,255,255,.35);border-top-color:#fff;border-radius:50%;
        margin:22px auto 0;animation:s 0.9s linear infinite;}
  @keyframes s{to{transform:rotate(360deg)}}
</style></head><body><div class='box'>
<h1>千帆云递</h1><p id='s'>正在启动后端服务，请稍候…</p><div class='spin'></div>
</div></body></html>`;

function dataUrl(html: string): string {
  return 'data:text/html;charset=utf-8,' + encodeURIComponent(html);
}

async function setStatus(text: string): Promise<void> {
  try {
    await mainWindow?.webContents.executeJavaScript(
      `document.getElementById('s').textContent = ${JSON.stringify(text)}`);
  } catch { /* 窗口可能还没就绪 */ }
}

/** 致命错误：既弹原生框又在窗口里留错误页（若窗口可用） */
async function showFatal(msg: string): Promise<void> {
  const short = msg.split('\n').slice(0, 3).join('\n');
  try {
    dialog.showErrorBox('千帆云递 启动失败', short);
  } catch {}
  if (mainWindow && !mainWindow.isDestroyed()) {
    const html = `<!doctype html><html><head><meta charset='utf-8'><style>
      body{font-family:'Microsoft YaHei',monospace;background:#1e293b;color:#e2e8f0;padding:28px;}
      h2{color:#f87171;margin-top:0} pre{white-space:pre-wrap;background:#0f172a;padding:14px;border-radius:8px;}
    </style></head><body><h2>启动失败</h2><pre>
      ${msg.replace(/</g, '&lt;')}
    </pre></body></html>`;
    try { await mainWindow.loadURL(dataUrl(html)); } catch {}
  }
}

let rt: RuntimeManager | null = null;
let switchHandlerRegistered = false;

async function selectProfile(): Promise<Profile> {
  if (needsProfileGate()) {
    log('[profiles] 尚无账户，进入创建向导');
  } else {
    log('[profiles] 显示账户选择');
  }
  return new Promise<Profile>((resolve) => runProfileGate(resolve));
}

/** 用指定账户启动/重启后端并加载主界面（MCP 开启时随账户重启，DB_PATH 跟随数据目录） */
async function startForProfile(profile: Profile): Promise<void> {
  if (!rt) throw new Error('运行时未初始化');
  setActiveDataDir(profile.dataDir);
  resetPathsCache();
  log(`[profiles] 启动账户: ${profile.name} dataDir=${profile.dataDir}`);
  log(dumpPaths());
  await setStatus(`账户「${profile.name}」，正在启动后端服务…`);

  backend?.stop();
  backend = await startBackend(rt, (s) => { void setStatus(s); }, { profileName: profile.name });

  // MCP 开启状态随账户重启（DB_PATH 指向新账户数据库）
  const reg = readRegistry();
  if (reg.mcpEnabled) {
    stopMcp();
    await setStatus('正在启动 MCP 服务…');
    const r = await startMcp(rt, backend.port, path.join(profile.dataDir, 'db', 'database.db'));
    log('[mcp] 随账户启动' + (r.ok ? `成功（端口 ${r.port}）` : `失败: ${r.error}`));
  }

  await setStatus('服务就绪，正在加载界面…');
  const target = `http://127.0.0.1:${backend.port}/`;
  log('loading', target);
  if (mainWindow && !mainWindow.isDestroyed()) {
    await mainWindow.loadURL(target);
    injectHubButton(mainWindow, profile.name, { running: isMcpRunning(), port: getMcpPort() });
  }
}

async function bootstrap(): Promise<void> {
  initLogger();
  log(`==== QianFan Sync Desktop ${SHELL_VERSION} ====`);
  log(dumpPaths());

  await app.whenReady();

  // 先把窗口立起来：任何后续失败用户都能看到，而不是"双击没反应"
  mainWindow = new BrowserWindow({
    width: 1280, height: 820, minWidth: 1024, minHeight: 640,
    title: '千帆云递',
    show: true,
    backgroundColor: '#2563eb',
    webPreferences: {
      preload: path.join(__dirname, '..', 'preload', 'index.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });
  mainWindow.removeMenu();
  await mainWindow.loadURL(dataUrl(LOADING_HTML));

  rt = new RuntimeManager();
  await setStatus('正在准备运行时环境（首次启动约 1-2 分钟），请勿关闭窗口…');
  rt.bootstrap();
  log('--- runtime detect ---');
  const statuses = rt.detectAll();
  for (const s of statuses) {
    log(`  ${s.id.padEnd(13)} ${s.ready ? 'OK ' : 'NO '} ${s.path ?? '-'}  ${s.version ?? ''}`);
  }
  await setStatus(`检测运行时：${statuses.filter(s => s.ready).length}/${statuses.length} 就绪`);

  // 注册切换账户 + MCP 开关入口（主界面右下角齿轮菜单）
  if (!switchHandlerRegistered) {
    switchHandlerRegistered = true;
    ipcMain.handle('app:switch-profile', async () => {
      try {
        log('[profiles] 用户请求切换账户，停止当前后端…');
        backend?.stop();
        backend = null;
        stopMcp();
        const profile = await selectProfile();
        await startForProfile(profile);
        return { ok: true, name: profile.name };
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        log('[profiles] 切换账户失败:', msg);
        try { await showFatal('切换账户失败：' + msg); } catch {}
        return { ok: false, error: msg };
      }
    });
    ipcMain.handle('app:mcp-toggle', async () => {
      try {
        if (isMcpRunning()) {
          stopMcp();
          const reg = readRegistry();
          reg.mcpEnabled = false;
          writeRegistry(reg);
          log('[mcp] 用户已关闭 MCP 服务');
          return { ok: true, running: false, port: null };
        }
        if (!backend) return { ok: false, error: '后端服务未就绪' };
        const dbPath = path.join(resolvePaths().dataDir, 'db', 'database.db');
        const r = await startMcp(rt!, backend.port, dbPath);
        const reg = readRegistry();
        reg.mcpEnabled = r.ok;
        writeRegistry(reg);
        if (!r.ok) return { ok: false, running: false, error: r.error };
        return { ok: true, running: true, port: r.port };
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        return { ok: false, running: false, error: msg };
      }
    });
  }

  const profile = await selectProfile();
  await startForProfile(profile);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
  });
}

app.on('will-quit', () => {
  log('app will-quit, cleaning up...');
  try { stopMcp(); } catch {}
  try { backend?.stop(); } catch {}
  closeLogger();
});

// app.exit() 不触发 will-quit —— 进程退出兜底，确保不留 python 孤儿
process.on('exit', () => {
  try { backend?.proc.kill(); } catch {}
});