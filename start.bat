@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: 一键启动脚本 — Windows
:: ============================================================

:: --- 项目根目录（脚本所在目录）---
set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"

:: --- 日志文件 ---
set "BACKEND_LOG=%PROJECT_ROOT%\backend.log"
set "FRONTEND_LOG=%PROJECT_ROOT%\frontend.log"

:: ============================================================
:: Step 1: 检查运行时环境
:: ============================================================
echo.
echo [1/6] 检查运行时环境...

:: 检查 Python
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 Python，请先安装 Python 3.8+
    echo     下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VER=%%i"
echo   √ Python !PYTHON_VER!

:: 检查 Node.js
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 Node.js，请先安装 Node.js 16+
    echo     下载地址: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do set "NODE_VER=%%i"
echo   √ Node !NODE_VER!

:: 检查 npm
where npm >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 npm，请重新安装 Node.js
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('npm --version 2^>^&1') do set "NPM_VER=%%i"
echo   √ npm !NPM_VER!

:: 检查 curl
where curl >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 curl，请先安装 curl
    echo     下载地址: https://curl.se/windows/
    pause
    exit /b 1
)
echo   √ curl 已安装

:: 检查 ffmpeg
where ffmpeg >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 ffmpeg，请先安装 ffmpeg
    echo     下载地址: https://ffmpeg.org/download.html
    pause
    exit /b 1
)
echo   √ ffmpeg 已安装

:: 检查 ffprobe
where ffprobe >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 ffprobe，请先安装 ffmpeg（包含 ffprobe）
    pause
    exit /b 1
)
echo   √ ffprobe 已安装

:: 清除系统代理，避免 httpx/cloakbrowser 读取到不支持的 socks:// 代理
set "http_proxy="
set "https_proxy="
set "all_proxy="
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "ALL_PROXY="

:: ============================================================
:: Step 2: 处理端口冲突
:: ============================================================
echo.
echo [2/6] 处理端口冲突...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5409 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   √ 端口 5409 空闲

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   √ 端口 5173 空闲

:: ============================================================
:: Step 3: 准备后端环境
:: ============================================================
echo.
echo [3/6] 准备后端环境...

set "VENV_DIR=%BACKEND_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "HASH_FILE=%PROJECT_ROOT%\.backend_deps_hash"

:: 获取 backend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- backend 2^>nul') do set "CURRENT_HASH=%%i"
if "!CURRENT_HASH!"=="" set "CURRENT_HASH=no-git"

:: 检查 venv 是否完整（目录 + pip + flask 都存在）
set "VENV_OK=0"
if exist "%VENV_DIR%" if exist "%VENV_PIP%" (
    :: 检查 flask 是否已安装
    "%VENV_PYTHON%" -c "import flask" >nul 2>&1
    if !errorlevel! equ 0 set "VENV_OK=1"
)

if "!VENV_OK!"=="0" (
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%" >nul 2>&1
    echo     创建虚拟环境...
    python -m venv "%VENV_DIR%"
    if !errorlevel! neq 0 (
        echo   X 虚拟环境创建失败，请先安装 python3-venv 或使用管理员权限运行
        pause
        exit /b 1
    )
    echo     安装 Python 依赖，请稍候...
    echo.
    "%VENV_PIP%" cache purge >nul 2>&1
    "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --no-cache-dir
    if !errorlevel! neq 0 (
        echo.
        echo   X Python 依赖安装失败
        pause
        exit /b 1
    )
    echo.
    echo !CURRENT_HASH!> "%HASH_FILE%"
    echo   √ 后端环境就绪
) else (
    echo   √ 依赖无变更，跳过
)

:: 检查 CloakBrowser 二进制文件
set "CLOAKBROWSER_DIR=%USERPROFILE%\.cloakbrowser"
set "CHROME_FOUND=0"
for /d %%d in ("%CLOAKBROWSER_DIR%\chromium-*") do (
    if exist "%%d\chrome.exe" set "CHROME_FOUND=1"
)

if "!CHROME_FOUND!"=="0" (
    echo     首次使用，下载 CloakBrowser 浏览器（约 200MB）...

    :: 获取下载信息
    for /f "tokens=*" %%u in ('"%VENV_PYTHON%" -c "import cloakbrowser.download as d; print(d.get_fallback_download_url())"') do set "DOWNLOAD_URL=%%u"
    for /f "tokens=*" %%d in ('"%VENV_PYTHON%" -c "import cloakbrowser.download as d; print(d.get_binary_dir())"') do set "BINARY_DIR=%%d"

    echo     下载地址: !DOWNLOAD_URL!
    echo.

    :: 使用 curl 下载（带进度条）
    set "TMP_FILE=%TEMP%\cloakbrowser.tar.gz"
    curl -L -# -o "!TMP_FILE!" "!DOWNLOAD_URL!"
    if !errorlevel! neq 0 (
        echo.
        echo     主下载失败，尝试 GitHub 备用地址...
        set "GITHUB_URL=!DOWNLOAD_URL:cloakbrowser.dev=github.com/CloakHQ/cloakbrowser/releases/download!"
        curl -L -# -o "!TMP_FILE!" "!GITHUB_URL!"
        if !errorlevel! neq 0 (
            del /f "!TMP_FILE!" >nul 2>&1
            echo   X CloakBrowser 下载失败，请检查网络连接
            pause
            exit /b 1
        )
    )

    echo.
    echo     解压中...

    :: 解压
    if not exist "!BINARY_DIR!" mkdir "!BINARY_DIR!"
    tar -xzf "!TMP_FILE!" -C "!BINARY_DIR!" >nul 2>&1
    del /f "!TMP_FILE!" >nul 2>&1

    :: 检查是否成功
    set "EXTRACT_OK=0"
    for /d %%d in ("!BINARY_DIR!\chromium-*") do (
        if exist "%%d\chrome.exe" set "EXTRACT_OK=1"
    )

    if "!EXTRACT_OK!"=="1" (
        echo   √ CloakBrowser 下载完成
    ) else (
        echo   X CloakBrowser 解压失败
        pause
        exit /b 1
    )
) else (
    echo   √ CloakBrowser 已安装
)

:: ============================================================
:: Step 4: 准备前端环境
:: ============================================================
echo.
echo [4/6] 准备前端环境...

set "HASH_FILE=%PROJECT_ROOT%\.frontend_deps_hash"

:: 获取 frontend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- frontend 2^>nul') do set "CURRENT_HASH=%%i"
if "!CURRENT_HASH!"=="" set "CURRENT_HASH=no-git"

if not exist "%FRONTEND_DIR%\node_modules" (
    echo     安装前端依赖，请稍候...
    echo.
    cd /d "%FRONTEND_DIR%"
    call npm install --prefer-offline
    echo.
    echo !CURRENT_HASH!> "%HASH_FILE%"
    echo   √ 前端依赖就绪
) else (
    set "SAVED_HASH="
    if exist "%HASH_FILE%" (
        for /f "tokens=*" %%i in ('type "%HASH_FILE%"') do set "SAVED_HASH=%%i"
    ) else (
        set "SAVED_HASH=none"
    )
    if "!CURRENT_HASH!"=="!SAVED_HASH!" (
        echo   √ 依赖无变更，跳过
    ) else (
        echo     检测到变更，更新前端依赖，请稍候...
        echo.
        cd /d "%FRONTEND_DIR%"
        call npm install --prefer-offline
        echo.
        echo !CURRENT_HASH!> "%HASH_FILE%"
        echo   √ 依赖更新完成
    )
)

:: ============================================================
:: Step 5: 启动服务
:: ============================================================
echo.
echo [5/6] 启动服务...

:: 确保端口完全释放
timeout /t 1 /nobreak >nul

:: 启动后端（使用完整路径避免变量展开问题）
cd /d "%BACKEND_DIR%"
set "SAU_PORT=5409"
start "SAU-Backend" /B cmd /c ""%VENV_DIR%\Scripts\python.exe" app.py > "%BACKEND_LOG%" 2>&1"
echo   √ 后端已启动

:: 启动前端
cd /d "%FRONTEND_DIR%"
start "SAU-Frontend" /B cmd /c "npm run dev > "%FRONTEND_LOG%" 2>&1"
echo   √ 前端已启动

cd /d "%PROJECT_ROOT%"

:: ============================================================
:: Step 6: 等待服务就绪并显示入口
:: ============================================================
echo.
echo [6/6] 等待服务就绪...

:: 等待后端（自动检测端口）
set "BACKEND_PORT=5409"
set /a "COUNT=0"
:wait_backend
set /a "COUNT+=1"
if !COUNT! GTR 60 (
    echo   X 后端启动超时，请查看日志: %BACKEND_LOG%
    echo.
    echo   最后 10 行日志:
    powershell -Command "Get-Content '%BACKEND_LOG%' -Tail 10"
    pause
    exit /b 1
)

:: 从日志检测实际端口
if exist "%BACKEND_LOG%" (
    for /f "tokens=*" %%p in ('powershell -Command "Select-String -Path '%BACKEND_LOG%' -Pattern 'Serving on http://0\.0\.0\.0:(\d+)' | ForEach-Object { $_.Matches.Groups[1].Value } | Select-Object -Last 1" 2^>nul') do set "BACKEND_PORT=%%p"
)

curl -s -o nul -w "%%{http_code}" http://127.0.0.1:!BACKEND_PORT!/api/health 2>nul | findstr "200" >nul
if !errorlevel! neq 0 (
    timeout /t 1 /nobreak >nul
    goto wait_backend
)
echo   √ 后端就绪 (端口: !BACKEND_PORT!)

:: 等待前端
set /a "COUNT=0"
:wait_frontend
set /a "COUNT+=1"
if !COUNT! GTR 60 (
    echo   X 前端启动超时（60秒），但服务可能仍在运行
    echo   请手动访问 http://localhost:5173 检查
    echo.
    goto show_info
)
:: 使用 PowerShell 检查前端是否就绪
powershell -Command "(Invoke-WebRequest -Uri 'http://127.0.0.1:5173' -UseBasicParsing -TimeoutSec 2).StatusCode" 2>nul | findstr "200" >nul
if !errorlevel! neq 0 (
    timeout /t 1 /nobreak >nul
    goto wait_frontend
)
echo   √ 前端就绪

:show_info
:: 显示访问入口
echo.
echo ============================================
echo   前端界面: http://localhost:5173
echo   后端 API: http://localhost:!BACKEND_PORT!
echo ============================================
echo.
echo   后端日志: %BACKEND_LOG%
echo   前端日志: %FRONTEND_LOG%
echo.

:: 显示最新日志
echo --- 后端最新日志 ---
powershell -Command "Get-Content '%BACKEND_LOG%' -Tail 10 2>$null"
echo.

echo 按任意键停止所有服务...
pause >nul

:: 停止服务
taskkill /FI "WINDOWTITLE eq SAU-Backend*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq SAU-Frontend*" >nul 2>&1
echo 服务已停止

endlocal
