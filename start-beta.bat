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
set "MCP_DIR=%PROJECT_ROOT%\backend-mcp"

:: --- 本地依赖目录（优先使用）---
if exist "%PROJECT_ROOT%\dependency\bin" (
    set "PATH=%PROJECT_ROOT%\dependency\bin;%PATH%"
)
if exist "%PROJECT_ROOT%\dependency\python" (
    set "PATH=%PROJECT_ROOT%\dependency\python;%PROJECT_ROOT%\dependency\python\Scripts;%PATH%"
)
if exist "%PROJECT_ROOT%\dependency\git\cmd" (
    set "PATH=%PROJECT_ROOT%\dependency\git\cmd;%PATH%"
)
if exist "%PROJECT_ROOT%\dependency\node" (
    set "PATH=%PROJECT_ROOT%\dependency\node;%PATH%"
)
if exist "%PROJECT_ROOT%\dependency\cloakbrowser\chrome.exe" (
    set "CLOAKBROWSER_BINARY_PATH=%PROJECT_ROOT%\dependency\cloakbrowser\chrome.exe"
)
:: --- 项目代码管理（git clone / update）---
set "REPO_URL=https://github.com/DevilJie/social-auto-upload-web-ui.git"
set "MAIN_BRANCH=beta"

if not exist "%BACKEND_DIR%" (
    rem 首次使用：没有项目代码，从 GitHub 克隆
    where git >nul 2>&1
    if !errorlevel! neq 0 (
        echo   X 未找到 git，无法克隆项目代码
        pause
        exit /b 1
    )
    echo.
    echo   首次使用，正在从 GitHub 拉取项目代码...
    cd /d "%PROJECT_ROOT%"
    git init
    git remote add origin "%REPO_URL%" 2>nul || git remote set-url origin "%REPO_URL%"
    git fetch
    git fetch origin "%MAIN_BRANCH%"
    if !errorlevel! neq 0 (
        echo   X 无法连接 GitHub，请检查网络连接
        echo     如果无法访问 GitHub，请手动下载项目代码到当前目录
        echo     仓库地址: %REPO_URL%
        pause
        exit /b 1
    )
    git checkout -f "%MAIN_BRANCH%"
    echo   √ 项目代码拉取完成
    echo.
    call "%PROJECT_ROOT%\start-beta.bat"
    exit /b
)

:: 已有项目代码：检查 beta 分支是否有更新
if exist "%PROJECT_ROOT%\.git" (
    where git >nul 2>&1
    if !errorlevel! equ 0 (
        cd /d "%PROJECT_ROOT%"
        git fetch origin "%MAIN_BRANCH%" >nul 2>&1
        git checkout -f "%MAIN_BRANCH%"
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%l in ('git rev-parse "%MAIN_BRANCH%" 2^>nul') do set "LOCAL_HASH=%%l"
            for /f "tokens=*" %%r in ('git rev-parse "origin/%MAIN_BRANCH%" 2^>nul') do set "REMOTE_HASH=%%r"
            if defined REMOTE_HASH (
                if not "!LOCAL_HASH!"=="!REMOTE_HASH!" (
                    echo.
                    <nul set /p "_=发现新版本！是否更新？（更新将覆盖本地修改，未提交的代码将丢失） [Y/n]："
                    set /p "UPDATE_ANS="
                    if /i not "!UPDATE_ANS!"=="n" (
                        git reset --hard "origin/%MAIN_BRANCH%" >nul 2>&1
                        echo   √ 更新完成，重新启动...
                        call "%PROJECT_ROOT%\start-beta.bat"
                        exit /b
                    )
                )
            )
        )
    )
)


:: --- 日志文件 ---
set "BACKEND_LOG=%PROJECT_ROOT%\backend.log"
set "FRONTEND_LOG=%PROJECT_ROOT%\frontend.log"
set "MCP_LOG=%PROJECT_ROOT%\mcp.log"

:: --- MCP transport mode（默认 sse 适合后台 daemon；stdio 需父进程喂 stdin）---
if defined MCP_TRANSPORT_MODE (
    set "TRANSPORT_MODE=%MCP_TRANSPORT_MODE%"
) else (
    set "TRANSPORT_MODE=sse"
)

:: ============================================================
:: Step 1: 检查运行时环境
:: ============================================================
echo.
echo [1/6] 检查运行时环境...

:: --- 判断命令来源：内置还是系统 ---
set "DEP_PREFIX=%PROJECT_ROOT%\dependency"
set "DEP_PREFIX_UNIX=%DEP_PREFIX:\=/%"

:: 检查 Python
where python >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 Python，请先安装 Python 3.8+
    echo     下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set "PYTHON_VER=%%i"
set "PY_SRC=系统"
set "PY_PATH="
for /f "tokens=*" %%p in ('where python 2^>nul') do (
    if not defined PY_PATH (
        set "PY_PATH=%%p"
        set "_CHK=%%p"
        if not "!_CHK:%DEP_PREFIX%=!"=="!_CHK!" set "PY_SRC=内置"
    )
)
echo   √ Python !PYTHON_VER! (!PY_SRC!) [!PY_PATH!]

:: 检查 Node.js
where node >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 Node.js，请先安装 Node.js 16+
    echo     下载地址: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version 2^>^&1') do set "NODE_VER=%%i"
set "NODE_SRC=系统"
set "NODE_PATH="
for /f "tokens=*" %%p in ('where node 2^>nul') do (
    if not defined NODE_PATH (
        set "NODE_PATH=%%p"
        set "_CHK=%%p"
        if not "!_CHK:%DEP_PREFIX%=!"=="!_CHK!" set "NODE_SRC=内置"
    )
)

:: 检查 npm
where npm >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 npm，请重新安装 Node.js
    pause
    exit /b 1
)
for /f "tokens=*" %%i in ('npm --version 2^>^&1') do set "NPM_VER=%%i"
echo   √ Node !NODE_VER! / npm !NPM_VER! (!NODE_SRC!) [!NODE_PATH!]

:: 检查 curl
where curl >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 curl，请先安装 curl
    echo     下载地址: https://curl.se/windows/
    pause
    exit /b 1
)
set "CURL_SRC=系统"
set "CURL_PATH="
for /f "tokens=*" %%p in ('where curl 2^>nul') do (
    if not defined CURL_PATH (
        set "CURL_PATH=%%p"
        set "_CHK=%%p"
        if not "!_CHK:%DEP_PREFIX%=!"=="!_CHK!" set "CURL_SRC=内置"
    )
)
echo   √ curl 已安装 (!CURL_SRC!) [!CURL_PATH!]

:: 检查 ffmpeg
where ffmpeg >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 ffmpeg，请先安装 ffmpeg
    echo     下载地址: https://ffmpeg.org/download.html
    pause
    exit /b 1
)
set "FF_SRC=系统"
set "FF_PATH="
for /f "tokens=*" %%p in ('where ffmpeg 2^>nul') do (
    if not defined FF_PATH (
        set "FF_PATH=%%p"
        set "_CHK=%%p"
        if not "!_CHK:%DEP_PREFIX%=!"=="!_CHK!" set "FF_SRC=内置"
    )
)
echo   √ ffmpeg 已安装 (!FF_SRC!) [!FF_PATH!]

:: 检查 ffprobe
where ffprobe >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 ffprobe，请先安装 ffmpeg（包含 ffprobe）
    pause
    exit /b 1
)
set "FP_SRC=系统"
set "FP_PATH="
for /f "tokens=*" %%p in ('where ffprobe 2^>nul') do (
    if not defined FP_PATH (
        set "FP_PATH=%%p"
        set "_CHK=%%p"
        if not "!_CHK:%DEP_PREFIX%=!"=="!_CHK!" set "FP_SRC=内置"
    )
)
echo   √ ffprobe 已安装 (!FP_SRC!) [!FP_PATH!]

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

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5410 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   √ 端口 5410 空闲

:: ============================================================
:: Step 3: 准备后端环境
:: ============================================================
echo.
echo [3/6] 准备后端环境...

set "VENV_DIR=%BACKEND_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "PIP_MIRROR=https://mirrors.aliyun.com/pypi/simple/"
set "HASH_FILE=%PROJECT_ROOT%\.backend_deps_hash"

:: 获取 backend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- backend 2^>nul') do set "CURRENT_HASH=%%i"
if "!CURRENT_HASH!"=="" set "CURRENT_HASH=no-git"

:: 检查 venv 是否完整（目录 + pip + flask 都存在）
set "VENV_OK=0"
if exist "%VENV_DIR%" if exist "%VENV_PIP%" (
    rem 检查 flask 是否已安装
    "%VENV_PYTHON%" -c "import flask" >nul 2>&1
    if !errorlevel! equ 0 set "VENV_OK=1"
)

if "!VENV_OK!"=="0" (
    if exist "%VENV_DIR%" rmdir /s /q "%VENV_DIR%" >nul 2>&1
    echo     创建虚拟环境...

    rem 检查 venv 模块是否可用
    python -c "import venv" >nul 2>&1
    if !errorlevel! neq 0 (
        echo   X Python venv 模块不可用
        echo     请确保安装了完整版 Python（从 python.org 下载）
        echo     或运行: python -m ensurepip --default-pip
        pause
        exit /b 1
    )

    python -m venv "%VENV_DIR%" --clear
    if !errorlevel! neq 0 (
        echo   X 虚拟环境创建失败
        echo     可能原因:
        echo       1. 目录权限不足（尝试以管理员运行）
        echo       2. 路径包含中文或特殊字符
        echo       3. 防病毒软件阻止
        echo     当前路径: %VENV_DIR%
        pause
        exit /b 1
    )
    echo     安装 Python 依赖，请稍候...
    echo.
    "%VENV_PIP%" cache purge >nul 2>&1
    "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --no-cache-dir -i "%PIP_MIRROR%"
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
    rem venv 存在，检查依赖是否有变更
    set "SAVED_HASH="
    if exist "%HASH_FILE%" (
        for /f "tokens=*" %%i in ('type "%HASH_FILE%"') do set "SAVED_HASH=%%i"
    ) else (
        set "SAVED_HASH=none"
    )
    if "!CURRENT_HASH!"=="!SAVED_HASH!" (
        echo   √ 依赖无变更，跳过
    ) else (
        echo     检测到变更，更新后端依赖，请稍候...
        echo.
        "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --no-cache-dir -i "%PIP_MIRROR%"
        if !errorlevel! neq 0 (
            echo.
            echo   X Python 依赖更新失败
            pause
            exit /b 1
        )
        echo.
        echo !CURRENT_HASH!> "%HASH_FILE%"
        echo   √ 后端依赖更新完成
    )
)

:: 检查 CloakBrowser 二进制文件
set "CB_SRC=系统"
set "CB_PATH="
set "CHROME_FOUND=0"
set "CB_BUILTIN=!PROJECT_ROOT!\dependency\cloakbrowser\chrome.exe"
if exist "!CB_BUILTIN!" (
    set "CLOAKBROWSER_BINARY_PATH=!CB_BUILTIN!"
    set "CB_SRC=内置"
    set "CB_PATH=!CB_BUILTIN!"
    set "CHROME_FOUND=1"
)
if "!CHROME_FOUND!"=="0" (
    set "CLOAKBROWSER_DIR=!USERPROFILE!\.cloakbrowser"
    for /d %%d in ("!CLOAKBROWSER_DIR!\chromium-*") do (
        if exist "%%d\chrome.exe" set "CHROME_FOUND=1" & set "CB_PATH=%%d\chrome.exe"
    )
)

if "!CHROME_FOUND!"=="0" (
    echo     首次使用，下载 CloakBrowser 浏览器（约 200MB）...

    rem 获取下载信息
    "%VENV_PYTHON%" -c "import cloakbrowser.download as d; f=open(r'%TEMP%\cb_info.txt','w'); f.write(str(d.get_fallback_download_url())+'\n'); f.write(str(d.get_binary_dir())+'\n'); f.close()"
    set "DOWNLOAD_URL="
    set "BINARY_DIR="
    if exist "%TEMP%\cb_info.txt" (
        set /p DOWNLOAD_URL=<"%TEMP%\cb_info.txt"
        for /f "skip=1 tokens=*" %%d in ('type "%TEMP%\cb_info.txt"') do set "BINARY_DIR=%%d"
        del /f "%TEMP%\cb_info.txt" >nul 2>&1
    )

    echo     下载地址: !DOWNLOAD_URL!
    echo.

    rem 使用 curl 下载（带进度条）
    rem 从 URL 检测文件格式（.zip 或 .tar.gz）
    set "TMP_EXT=.zip"
    echo !DOWNLOAD_URL! | findstr /C:".tar.gz" >nul 2>&1
    if !errorlevel! equ 0 set "TMP_EXT=.tar.gz"

    set "TMP_FILE=%TEMP%\cloakbrowser!TMP_EXT!"
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

    rem 解压（tar -xf 自动识别 zip 和 tar.gz 格式）
    if not exist "!BINARY_DIR!" mkdir "!BINARY_DIR!"
    tar -xf "!TMP_FILE!" -C "!BINARY_DIR!" >nul 2>&1
    del /f "!TMP_FILE!" >nul 2>&1

    rem 检查是否成功（chrome.exe 可能直接在 BINARY_DIR 或其子目录中）
    set "EXTRACT_OK=0"
    if exist "!BINARY_DIR!\chrome.exe" set "EXTRACT_OK=1"
    if "!EXTRACT_OK!"=="0" (
        for /d %%d in ("!BINARY_DIR!\chromium-*") do (
            if exist "%%d\chrome.exe" set "EXTRACT_OK=1"
        )
    )

    if "!EXTRACT_OK!"=="1" (
        echo   √ CloakBrowser 下载完成
    ) else (
        echo   X CloakBrowser 解压失败
        pause
        exit /b 1
    )
) else (
    echo   √ CloakBrowser 已安装 ^(!CB_SRC!^) [!CB_PATH!]
)

:: ============================================================
:: Step 4: 准备前端 + MCP 环境
:: ============================================================
echo.
echo [4/6] 准备前端 + MCP 环境...

set "HASH_FILE=%PROJECT_ROOT%\.frontend_deps_hash"

:: 获取 frontend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- frontend 2^>nul') do set "CURRENT_HASH=%%i"
if "!CURRENT_HASH!"=="" set "CURRENT_HASH=no-git"

if not exist "%FRONTEND_DIR%\node_modules" (
    echo     安装前端依赖，请稍候...
    echo.
    cd /d "%FRONTEND_DIR%"
    call npm install --prefer-offline --registry=https://registry.npmmirror.com
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
        call npm install --prefer-offline --registry=https://registry.npmmirror.com
        echo.
        echo !CURRENT_HASH!> "%HASH_FILE%"
        echo   √ 依赖更新完成
    )
)

:: --- MCP: install deps + build ---
set "HASH_FILE=%PROJECT_ROOT%\.mcp_deps_hash"
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- backend-mcp 2^>nul') do set "CURRENT_HASH=%%i"
if "!CURRENT_HASH!"=="" set "CURRENT_HASH=no-git"

if not exist "%MCP_DIR%\node_modules" (
    echo     安装 MCP 依赖，请稍候...
    echo.
    cd /d "%MCP_DIR%"
    call npm install --prefer-offline --registry=https://registry.npmmirror.com
    echo.
    echo !CURRENT_HASH!> "%HASH_FILE%"
    echo   √ MCP 依赖就绪
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
        echo     检测到变更，更新 MCP 依赖，请稍候...
        echo.
        cd /d "%MCP_DIR%"
        call npm install --prefer-offline --registry=https://registry.npmmirror.com
        echo.
        echo !CURRENT_HASH!> "%HASH_FILE%"
        echo   √ 依赖更新完成
    )
)

:: 始终重新编译 MCP（保证 dist/ 与 src/ 同步）
echo     编译 MCP ...
cd /d "%MCP_DIR%"
call npm run build
if !errorlevel! neq 0 (
    echo   X MCP 编译失败
    pause
    exit /b 1
)
echo   √ MCP 编译完成

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

:: 等待后端进程启动并获取 PID
timeout /t 2 /nobreak >nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5409 ^| findstr LISTENING 2^>nul') do set "BACKEND_PID=%%a"
echo   √ 后端已启动 (PID: !BACKEND_PID!)

:: 启动前端
cd /d "%FRONTEND_DIR%"
start "SAU-Frontend" /B cmd /c "npm run dev > "%FRONTEND_LOG%" 2>&1"

:: 等待前端进程启动并获取 PID
timeout /t 2 /nobreak >nul
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING 2^>nul') do set "FRONTEND_PID=%%a"
echo   √ 前端已启动 (PID: !FRONTEND_PID!)

:: 启动 MCP
cd /d "%MCP_DIR%"
set "TRANSPORT_MODE=%TRANSPORT_MODE%"
start "SAU-MCP" /B cmd /c "set TRANSPORT_MODE=%TRANSPORT_MODE%&& npm start > "%MCP_LOG%" 2>&1"

:: 等待 MCP 进程启动
timeout /t 2 /nobreak >nul
:: 尝试从端口 5410 获取 PID（仅 sse/both 模式有效）
set "MCP_PID="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5410 ^| findstr LISTENING 2^>nul') do set "MCP_PID=%%a"
if defined MCP_PID (
    echo   √ MCP 已启动 (PID: !MCP_PID!, transport: %TRANSPORT_MODE%)
) else (
    echo   √ MCP 已启动 (transport: %TRANSPORT_MODE%, stdio 模式)
)

:: 保存 PID 到文件，用于停止服务
echo !BACKEND_PID!> "%PROJECT_ROOT%\.backend.pid"
echo !FRONTEND_PID!> "%PROJECT_ROOT%\.frontend.pid"
if defined MCP_PID echo !MCP_PID!> "%PROJECT_ROOT%\.mcp.pid"

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
    goto wait_mcp
)
:: 检查端口 5173 是否被占用（前端已启动）
netstat -an | findstr ":5173" | findstr "LISTENING" >nul 2>&1
if !errorlevel! equ 0 (
    echo   √ 前端就绪
    goto wait_mcp
)
timeout /t 1 /nobreak >nul
goto wait_frontend

:: 等待 MCP（通过日志里的 "[MCP] Server ready" 判断；最长 15 秒）
:wait_mcp
set /a "MCP_COUNT=0"
:wait_mcp_loop
set /a "MCP_COUNT+=1"
if !MCP_COUNT! GTR 15 (
    echo   ! MCP 启动检查超时（15秒），请查看日志: %MCP_LOG%
    goto show_info
)
if exist "%MCP_LOG%" (
    findstr /C:"Server ready" "%MCP_LOG%" >nul 2>&1
    if !errorlevel! equ 0 (
        echo   √ MCP 就绪 (transport: %TRANSPORT_MODE%)
        goto show_info
    )
)
timeout /t 1 /nobreak >nul
goto wait_mcp_loop

:show_info
:: 显示访问入口
echo.
echo ============================================
echo   前端界面: http://localhost:5173
echo   后端 API: http://localhost:!BACKEND_PORT!
if /i "%TRANSPORT_MODE%"=="sse" (
    echo   MCP  SSE:   http://localhost:5410/sse
) else if /i "%TRANSPORT_MODE%"=="both" (
    echo   MCP  SSE:   http://localhost:5410/sse
) else (
    echo   MCP  stdio: 启动中 ^(transport=%TRANSPORT_MODE%^)
)
echo ============================================
echo.
echo 按 Ctrl+C 停止所有服务
echo.
echo --- 后端日志 ---
powershell -Command "Get-Content '%BACKEND_LOG%' -Wait -Tail 50"
