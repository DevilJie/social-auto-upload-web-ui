import * as fs from 'fs';
import * as path from 'path';
import { spawnSync } from 'child_process';
import { resolvePaths } from './paths';
import { log } from './log';

export interface RuntimeStatus {
  id: 'python' | 'node' | 'git' | 'cloakbrowser' | 'ffmpeg';
  ready: boolean;
  path?: string;
  version?: string;
  source: 'bundled' | 'system' | 'missing';
  message?: string;
}

export class RuntimeManager {
  private p = resolvePaths();
  private _cache: RuntimeStatus[] = [];

  /** 首次启动：把 resources/runtime-seed/* 复制到 userData/runtime/ */
  bootstrap(): { copied: boolean; source: string } {
    if (!fs.existsSync(this.p.runtimeSeed)) {
      log('runtime-seed 缺失 → 开发模式（electron 直接 npm run dev），跳过拷贝');
      return { copied: false, source: 'no-seed' };
    }
    if (this._hasCompleteRuntime()) {
      log(`runtime/ 已就绪: ${this.p.runtimeDir}`);
      return { copied: false, source: 'already-ready' };
    }
    if (fs.existsSync(this.p.runtimeDir)) {
      // 残留但不完整（上次复制中途退出/被杀）→ 删除重建，半成品没法用
      log('runtime/ 不完整（上次复制被打断）→ 清理后重新复制');
      fs.rmSync(this.p.runtimeDir, { recursive: true, force: true });
    }
    log(`首次启动：复制 runtime-seed → ${this.p.runtimeDir}`);
    this.copyDir(this.p.runtimeSeed, this.p.runtimeDir);
    return { copied: true, source: this.p.runtimeSeed };
  }

  /**
   * 运行时完整性判定：关键可执行文件**全部存在**才算就绪。
   * 旧实现只查 cloakbrowser 目录是否存在——1.3GB 拷贝按字母序进行
   * （bin → cloakbrowser → git → node → python），中途退出会留下
   * 「cloakbrowser 已复制、python 还没有」的半成品，再次启动被误判
   * 为已就绪，最终报「缺少可用的 python.exe」。
   */
  private _hasCompleteRuntime(): boolean {
    const win = process.platform === 'win32';
    const must: Array<[string, string]> = [
      ['cloakbrowser', win ? 'chrome.exe' : 'chrome'],
      ['python', win ? 'python.exe' : 'bin/python'],
      ['bin', win ? 'ffmpeg.exe' : 'ffmpeg'],
      ['node', win ? 'node.exe' : 'bin/node'],
      ['git', win ? 'cmd/git.exe' : 'bin/git'],
    ];
    return must.every(([dir, exe]) =>
      fs.existsSync(path.join(this.p.runtimeDir, dir, exe)));
  }

  detectAll(): RuntimeStatus[] {
    this._cache = [
      this._detectPython(),
      this._detectNode(),
      this._detectGit(),
      this._detectCloakBrowser(),
      this._detectFfmpeg(),
    ];
    return this._cache;
  }

  get(id: RuntimeStatus['id']): RuntimeStatus | undefined {
    return this._cache.find((s) => s.id === id);
  }

  /** 生成后端进程环境变量：PATH 前置 + CLOAKBROWSER_BINARY_PATH */
  buildEnv(extra: NodeJS.ProcessEnv = {}): NodeJS.ProcessEnv {
    const binDirs = [
      path.join(this.p.runtimeDir, 'bin'),
      path.join(this.p.runtimeDir, 'python'),
      path.join(this.p.runtimeDir, 'python', 'Scripts'),
      path.join(this.p.runtimeDir, 'node'),
      path.join(this.p.runtimeDir, 'git', 'cmd'),
      path.join(this.p.runtimeDir, 'git', 'bin'),
    ].filter((d) => fs.existsSync(d));

    const sep = process.platform === 'win32' ? ';' : ':';
    // 注意：不设 PYTHONHOME —— 便携解释器自带完整 stdlib（设错会崩），
    // venv 场景由 pyvenv.cfg 自动定位 base 解释器。
    const env: NodeJS.ProcessEnv = {
      ...process.env,
      ...extra,
      PATH: [...binDirs, process.env.PATH ?? ''].join(sep),
    };
    const cb = this.get('cloakbrowser');
    if (cb?.path) env.CLOAKBROWSER_BINARY_PATH = cb.path;
    return env;
  }

  private _detectPython(): RuntimeStatus {
    // 便携完整解释器：python.exe 在根目录；venv 结构：Windows 在 Scripts/，Linux/macOS 在 bin/
    const candidates = [
      path.join(this.p.runtimeDir, 'python', process.platform === 'win32' ? 'python.exe' : 'bin/python'),
      path.join(this.p.runtimeDir, 'python', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python3'),
      'python', 'python3',
    ];
    const hit = this._firstExisting(candidates);
    if (!hit) return { id: 'python', ready: false, source: 'missing', message: 'Python 未安装' };
    const v = this._execSafe(hit, ['--version']);
    return {
      id: 'python', ready: true, path: hit, version: v ?? 'unknown',
      source: hit.includes(this.p.runtimeDir) ? 'bundled' : 'system',
    };
  }

  private _detectNode(): RuntimeStatus {
    const candidates = [
      path.join(this.p.runtimeDir, 'node', process.platform === 'win32' ? 'node.exe' : 'bin/node'),
      'node',
    ];
    const hit = this._firstExisting(candidates);
    if (!hit) return { id: 'node', ready: false, source: 'missing', message: 'Node 未安装（可选）' };
    const v = this._execSafe(hit, ['--version']);
    return {
      id: 'node', ready: true, path: hit, version: v?.replace(/^v/, '') ?? 'unknown',
      source: hit.includes(this.p.runtimeDir) ? 'bundled' : 'system',
    };
  }

  private _detectGit(): RuntimeStatus {
    const candidates = [
      path.join(this.p.runtimeDir, 'git', 'cmd', 'git.exe'),
      path.join(this.p.runtimeDir, 'git', 'bin', 'git'),
      'git',
    ];
    const hit = this._firstExisting(candidates);
    if (!hit) return { id: 'git', ready: false, source: 'missing', message: 'Git 未安装（可选）' };
    const v = this._execSafe(hit, ['--version']);
    return {
      id: 'git', ready: true, path: hit, version: v?.split(' ').pop() ?? 'unknown',
      source: hit.includes(this.p.runtimeDir) ? 'bundled' : 'system',
    };
  }

  private _detectCloakBrowser(): RuntimeStatus {
    const dir = path.join(this.p.runtimeDir, 'cloakbrowser');
    const candidates = process.platform === 'darwin'
      ? [path.join(dir, 'Chromium.app', 'Contents', 'MacOS', 'Chromium')]
      : process.platform === 'win32'
      ? [path.join(dir, 'chrome.exe')]
      : [path.join(dir, 'chrome')];
    const hit = this._firstExisting(candidates);
    if (!hit) return { id: 'cloakbrowser', ready: false, source: 'missing', message: 'CloakBrowser 未解压到 runtime/cloakbrowser/' };
    // Windows 上禁止用 chrome.exe --version 探测版本：
    // chrome.exe 是 GUI 程序，--version 会短暂拉起一个浏览器窗口再退出
    // （windowsHide 对 GUI 程序无效），用户每次启动都会看到浏览器闪一下。
    // 版本号仅用于日志展示，Windows 上直接跳过探测（保持 unknown）；
    // 非 Windows 平台 --version 是 CLI 行为，无窗口，保持原探测。
    let version = 'unknown';
    if (process.platform !== 'win32') {
      const v = this._execSafe(hit, ['--version', '--no-sandbox'], { timeoutMs: 5000 });
      version = v?.split(' ').pop() ?? 'unknown';
    }
    return {
      id: 'cloakbrowser', ready: true, path: hit, version,
      source: 'bundled',
    };
  }

  private _detectFfmpeg(): RuntimeStatus {
    const candidates = [
      path.join(this.p.runtimeDir, 'bin', process.platform === 'win32' ? 'ffmpeg.exe' : 'ffmpeg'),
      'ffmpeg',
    ];
    const hit = this._firstExisting(candidates);
    if (!hit) return { id: 'ffmpeg', ready: false, source: 'missing', message: 'ffmpeg 未安装（视频帧抽取不可用）' };
    return { id: 'ffmpeg', ready: true, path: hit, version: '?', source: hit.includes(this.p.runtimeDir) ? 'bundled' : 'system' };
  }

  private _firstExisting(paths: string[]): string | null {
    for (const p of paths) {
      if (p.includes(path.sep) && fs.existsSync(p)) return p;
    }
    return null;
  }

  private _execSafe(bin: string, args: string[], opts: { timeoutMs?: number } = {}): string | null {
    try {
      const r = spawnSync(bin, args, { encoding: 'utf8', timeout: opts.timeoutMs ?? 4000, windowsHide: true });
      if (r.error || r.status !== 0) return null;
      return (r.stdout || r.stderr || '').trim().split('\n')[0];
    } catch { return null; }
  }

  private copyDir(src: string, dst: string): void {
    fs.mkdirSync(dst, { recursive: true });
    for (const name of fs.readdirSync(src)) {
      const s = path.join(src, name);
      const d = path.join(dst, name);
      const stat = fs.statSync(s);
      if (stat.isDirectory()) this.copyDir(s, d);
      else fs.copyFileSync(s, d);
    }
  }
}