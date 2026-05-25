# build-installer.ps1 — 构建完整的一键安装包
# 使用 Python 官方 Embedded Distribution 实现真正的独立部署
# 不依赖系统 Python，直接下载 python.org 的 embeddable 包
# 包含: Python 运行环境 + Flask 后端 + 前端

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = Split-Path $PSScriptRoot -Parent
$BACKEND_DIR = Join-Path $PROJECT_ROOT "backend"
$FRONTEND_DIR = Join-Path $PROJECT_ROOT "frontend"
$TAURI_DIR = Join-Path $PROJECT_ROOT "src-tauri"
$PYTHON_DIR = Join-Path $PROJECT_ROOT "python"

# Python 版本 — 直接从 python.org 下载，不依赖系统安装
$PYTHON_FULL = "3.11.9"
$PYTHON_VERSION_NODOT = "311"

function Write-Step {
    param($msg)
    Write-Host "[BUILD] $msg" -ForegroundColor Cyan
}

Write-Step "Starting installer build (Python $PYTHON_FULL)..."

# Clean up
if (Test-Path $PYTHON_DIR) {
    Remove-Item $PYTHON_DIR -Recurse -Force
}

# Step 1: Download and extract Python embedded distribution
# 这个包包含: python.exe (独立可执行文件), python311.zip (标准库), .pyd (C 扩展)
Write-Step "Downloading Python $PYTHON_FULL embedded distribution..."
$EMBED_URL = "https://www.python.org/ftp/python/$PYTHON_FULL/python-$PYTHON_FULL-embed-amd64.zip"
$EMBED_ZIP = Join-Path $PROJECT_ROOT "python-embed.zip"
Invoke-WebRequest -Uri $EMBED_URL -OutFile $EMBED_ZIP

New-Item -ItemType Directory -Path $PYTHON_DIR -Force | Out-Null
Expand-Archive -Path $EMBED_ZIP -DestinationPath $PYTHON_DIR -Force
Remove-Item $EMBED_ZIP -Force
Write-Host "[BUILD] Embedded dist extracted"

# Step 2: Configure _pth file — enable site packages (needed for pip)
# MUST use UTF-8 WITHOUT BOM, otherwise Python reads '﻿Lib' as the path
$PTH_FILE = Join-Path $PYTHON_DIR "python$PYTHON_VERSION_NODOT._pth"
$PTH_CONTENT = @"
python311.zip
.
Lib\site-packages
import site
"@
[System.IO.File]::WriteAllText($PTH_FILE, $PTH_CONTENT, [System.Text.UTF8Encoding]::new($false))

# Step 3: Verify embedded Python works
Write-Step "Verifying embedded Python..."
$PYTHON_EXE = Join-Path $PYTHON_DIR "python.exe"
$testOutput = & $PYTHON_EXE -c "import sys; print(sys.executable)" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Embedded Python is broken:" -ForegroundColor Red
    Write-Host $testOutput
    exit 1
}
Write-Host "[BUILD] python.exe: $testOutput"

# Step 4: Install pip
Write-Step "Installing pip..."
$GET_PIP = Join-Path $PYTHON_DIR "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GET_PIP
& $PYTHON_EXE $GET_PIP
Remove-Item $GET_PIP -Force

# Step 5: Install Python dependencies (force into embedded Python, not user site-packages)
Write-Step "Installing Python dependencies..."
$env:PYTHONNOUSERSITE = "1"
& $PYTHON_EXE -m pip install --no-user --upgrade pip
& $PYTHON_EXE -m pip install --no-user -r "$BACKEND_DIR\requirements.txt"
Remove-Item Env:PYTHONNOUSERSITE

# Step 6: Final verification
Write-Step "Verifying critical packages..."
& $PYTHON_EXE -c @"
import sqlite3, pathlib, waitress, flask, flask_cors, loguru
print('All critical packages OK')
print(f'sqlite3: {sqlite3.sqlite_version}')
import flask as _f
assert 'site-packages' in _f.__file__, f'Flask not in embedded Python: {_f.__file__}'
print(f'flask at: {_f.__file__}')
"@
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Package verification failed" -ForegroundColor Red
    exit 1
}

Write-Step "Python embedded distribution validated!"

# Step 6.5: Download CloakBrowser stealth Chromium (full directory, includes DLLs)
# CloakBrowser bundles its own stealth Chromium — no need for Playwright's Chromium (saves ~683 MB)
Write-Step "Downloading CloakBrowser stealth Chromium..."
& $PYTHON_EXE (Join-Path $PROJECT_ROOT "scripts\download-cloakbrowser-binary.py")
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] CloakBrowser download failed!" -ForegroundColor Red
    exit 1
}
$cloakBrowserDir = Join-Path $TAURI_DIR "bundle-resources\cloakbrowser"
if (-not (Test-Path (Join-Path $cloakBrowserDir "chrome.exe"))) {
    Write-Host "[ERROR] CloakBrowser chrome.exe not found in $cloakBrowserDir!" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path (Join-Path $cloakBrowserDir "chrome.dll"))) {
    Write-Host "[ERROR] CloakBrowser chrome.dll not found — incomplete download!" -ForegroundColor Red
    exit 1
}
$cloakSize = (Get-ChildItem $cloakBrowserDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host "[BUILD] CloakBrowser: $([math]::Round($cloakSize, 1)) MB"

# Step 7: Build frontend
Write-Step "Building frontend..."
Set-Location $FRONTEND_DIR
npm install
npm run build
Set-Location $TAURI_DIR

Write-Step "Build complete! Run: npx tauri build"
