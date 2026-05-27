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

python --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 python，请先安装 Python 3.8+
    echo   下载地址: https://www.python.org/downloads/
    exit /b 1
)
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set "PYTHON_VER=%%i"
echo   ✓ %PYTHON_VER%

node --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 node，请先安装 Node.js 16+
    echo   下载地址: https://nodejs.org/
    exit /b 1
)
for /f "tokens=*" %%i in ('node --version') do set "NODE_VER=%%i"

npm --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 npm，请重新安装 Node.js
    exit /b 1
)
for /f "tokens=*" %%i in ('npm --version') do set "NPM_VER=%%i"
echo   ✓ Node %NODE_VER% / npm %NPM_VER%

curl --version >nul 2>&1
if errorlevel 1 (
    echo   X 未找到 curl，请先安装 curl
    echo   下载地址: https://curl.se/windows/
    exit /b 1
)
for /f "tokens=*" %%i in ('curl --version 2^>^&1') do set "CURL_VER=%%i"
echo   ✓ curl %CURL_VER%

:: ============================================================
:: Step 2: 处理端口冲突
:: ============================================================
echo.
echo [2/6] 处理端口冲突...

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5409 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   ✓ 端口 5409 空闲

for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   ✓ 端口 5173 空闲

:: ============================================================
:: Step 3: 准备后端环境 (venv)
:: ============================================================
echo.
echo [3/6] 准备后端环境 (venv)...

set "VENV_DIR=%BACKEND_DIR%\.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "HASH_FILE=%PROJECT_ROOT%\.backend_deps_hash"

:: 获取 backend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- backend 2^>nul') do set "CURRENT_HASH=%%i"
if "%CURRENT_HASH%"=="" set "CURRENT_HASH=no-git"

if not exist "%VENV_DIR%" (
    echo   ✓ 创建 venv...
    python -m venv "%VENV_DIR%"
    echo   ✓ 安装 Python 依赖...
    "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --quiet
    echo %CURRENT_HASH%> "%HASH_FILE%"
    echo   ✓ 后端环境就绪
) else (
    :: 检查 hash 是否变更
    set "SAVED_HASH="
    if exist "%HASH_FILE%" (
        for /f "tokens=*" %%i in ('type "%HASH_FILE%"') do set "SAVED_HASH=%%i"
    ) else (
        set "SAVED_HASH=none"
    )
    if "%CURRENT_HASH%"=="!SAVED_HASH!" (
        echo   ✓ venv 已存在，依赖无变更，跳过
    ) else (
        echo   ✓ 检测到 backend/ 有变更，更新依赖...
        "%VENV_PIP%" install -r "%BACKEND_DIR%\requirements.txt" --quiet
        echo %CURRENT_HASH%> "%HASH_FILE%"
        echo   ✓ 依赖更新完成
    )
)

:: ============================================================
:: Step 4: 准备前端环境 (npm)
:: ============================================================
echo.
echo [4/6] 准备前端环境 (npm)...

set "HASH_FILE=%PROJECT_ROOT%\.frontend_deps_hash"

:: 获取 frontend 目录最近 git commit hash
set "CURRENT_HASH="
for /f "tokens=*" %%i in ('git -C "%PROJECT_ROOT%" log -1 --format^=%%H -- frontend 2^>nul') do set "CURRENT_HASH=%%i"
if "%CURRENT_HASH%"=="" set "CURRENT_HASH=no-git"

if not exist "%FRONTEND_DIR%\node_modules" (
    echo   ✓ 安装前端依赖...
    cd /d "%FRONTEND_DIR%"
    call npm install --silent
    echo %CURRENT_HASH%> "%HASH_FILE%"
    echo   ✓ 前端依赖就绪
) else (
    set "SAVED_HASH="
    if exist "%HASH_FILE%" (
        for /f "tokens=*" %%i in ('type "%HASH_FILE%"') do set "SAVED_HASH=%%i"
    ) else (
        set "SAVED_HASH=none"
    )
    if "%CURRENT_HASH%"=="!SAVED_HASH!" (
        echo   ✓ node_modules 已存在，依赖无变更，跳过
    ) else (
        echo   ✓ 检测到 frontend/ 有变更，更新依赖...
        cd /d "%FRONTEND_DIR%"
        call npm install --silent
        echo %CURRENT_HASH%> "%HASH_FILE%"
        echo   ✓ 依赖更新完成
    )
)

:: ============================================================
:: Step 5: 启动服务
:: ============================================================
echo.
echo [5/6] 启动服务...

cd /d "%BACKEND_DIR%"
start "SAU-Backend" /B cmd /c ""%VENV_PYTHON%" app.py > "%BACKEND_LOG%" 2>&1"
echo   ✓ 后端已启动

cd /d "%FRONTEND_DIR%"
start "SAU-Frontend" /B cmd /c "npm run dev > "%FRONTEND_LOG%" 2>&1"
echo   ✓ 前端已启动

cd /d "%PROJECT_ROOT%"

:: ============================================================
:: Step 6: 等待服务就绪并显示入口
:: ============================================================
echo.
echo [6/6] 等待服务就绪...

:: 等待后端
echo   等待后端...
set /a "COUNT=0"
:wait_backend
set /a "COUNT+=1"
if !COUNT! GTR 30 (
    echo   X 后端启动超时，请查看 %BACKEND_LOG%
    exit /b 1
)
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:5409/api/health 2>nul | findstr "200" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_backend
)
echo   ✓ 后端就绪

:: 等待前端
echo   等待前端...
set /a "COUNT=0"
:wait_frontend
set /a "COUNT+=1"
if !COUNT! GTR 30 (
    echo   X 前端启动超时，请查看 %FRONTEND_LOG%
    exit /b 1
)
curl -s -o nul -w "%%{http_code}" http://127.0.0.1:5173 2>nul | findstr "200" >nul
if errorlevel 1 (
    timeout /t 1 /nobreak >nul
    goto wait_frontend
)
echo   ✓ 前端就绪

:: 显示访问入口
echo.
echo ============================================
echo   前端界面: http://localhost:5173
echo   后端 API: http://localhost:5409
echo ============================================
echo.
echo 按任意键停止所有服务...
pause >nul

:: 停止服务
taskkill /FI "WINDOWTITLE eq SAU-Backend*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq SAU-Frontend*" >nul 2>&1
echo 服务已停止

endlocal
