@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

:: ============================================================
:: 项目代码更新脚本 — Windows
:: ============================================================

set "PROJECT_ROOT=%~dp0"
set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
set "BACKEND_DIR=%PROJECT_ROOT%\backend"
set "REPO_URL=https://github.com/DevilJie/social-auto-upload-web-ui.git"
set "MAIN_BRANCH=master"

where git >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 未找到 git，无法更新
    pause
    exit /b 1
)

:: 首次使用：没有项目代码，从 GitHub 克隆
if not exist "%BACKEND_DIR%" (
    echo.
    echo   首次使用，正在从 GitHub 拉取项目代码...
    cd /d "%PROJECT_ROOT%"
    git init
    git remote add origin "%REPO_URL%" 2>nul || git remote set-url origin "%REPO_URL%"
    git fetch origin "%MAIN_BRANCH%"
    if !errorlevel! neq 0 (
        echo   X 无法连接 GitHub，请检查网络连接
        echo     仓库地址: %REPO_URL%
        pause
        exit /b 1
    )
    git checkout -f "%MAIN_BRANCH%"
    echo   √ 项目代码拉取完成
    pause
    exit /b 0
)

:: 已有项目代码：检查当前分支是否有更新
cd /d "%PROJECT_ROOT%"
set "CURRENT_BRANCH="
for /f "tokens=*" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "CURRENT_BRANCH=%%b"
if not defined CURRENT_BRANCH (
    echo   X 无法获取当前分支
    pause
    exit /b 1
)
if "!CURRENT_BRANCH!"=="HEAD" (
    echo   X 当前处于分离 HEAD 状态，无法更新
    pause
    exit /b 1
)

echo.
echo   当前分支: !CURRENT_BRANCH!
echo   正在检查更新...
git fetch origin "!CURRENT_BRANCH!" >nul 2>&1
if !errorlevel! neq 0 (
    echo   X 无法连接远端仓库，请检查网络连接
    pause
    exit /b 1
)

set "LOCAL_HASH="
set "REMOTE_HASH="
for /f "tokens=*" %%l in ('git rev-parse HEAD 2^>nul') do set "LOCAL_HASH=%%l"
for /f "tokens=*" %%r in ('git rev-parse "origin/!CURRENT_BRANCH!" 2^>nul') do set "REMOTE_HASH=%%r"

if not defined REMOTE_HASH (
    echo   X 无法获取远端版本信息
    pause
    exit /b 1
)

if "!LOCAL_HASH!"=="!REMOTE_HASH!" (
    echo   √ 已是最新版本
    pause
    exit /b 0
)

echo.
echo   发现新版本！
echo     本地: !LOCAL_HASH:~0,7!
echo     远端: !REMOTE_HASH:~0,7!
echo.
<nul set /p "_=是否更新？（更新将覆盖本地修改，未提交的代码将丢失） [Y/n]："
set /p "UPDATE_ANS="
if /i not "!UPDATE_ANS!"=="n" (
    git reset --hard "origin/!CURRENT_BRANCH!" >nul 2>&1
    echo   √ 更新完成
) else (
    echo   已取消更新
)
pause
