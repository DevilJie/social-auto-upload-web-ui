@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: 停止服务脚本
:: ============================================================

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"

echo 正在停止服务...

:: 尝试从 PID 文件停止
if exist "%PROJECT_ROOT%\.backend.pid" (
    set /p BACKEND_PID=<"%PROJECT_ROOT%\.backend.pid"
    if not "!BACKEND_PID!"=="" (
        taskkill /F /PID !BACKEND_PID! >nul 2>&1
        echo   √ 后端已停止 (PID: !BACKEND_PID!)
    )
    del /f "%PROJECT_ROOT%\.backend.pid" >nul 2>&1
)

if exist "%PROJECT_ROOT%\.frontend.pid" (
    set /p FRONTEND_PID=<"%PROJECT_ROOT%\.frontend.pid"
    if not "!FRONTEND_PID!"=="" (
        taskkill /F /PID !FRONTEND_PID! >nul 2>&1
        echo   √ 前端已停止 (PID: !FRONTEND_PID!)
    )
    del /f "%PROJECT_ROOT%\.frontend.pid" >nul 2>&1
)

:: 备用：按端口停止
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5409 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5173 ^| findstr LISTENING 2^>nul') do (
    taskkill /F /PID %%a >nul 2>&1
)

echo 服务已停止
endlocal
