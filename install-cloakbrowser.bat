@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: CloakBrowser 一键升级脚本 — Windows
:: 用法：把本脚本和 cloakbrowser-windows-x64.zip 一起放到
::       项目根目录（和 start.bat 同级、有 dependency 文件夹的目录），
::       双击运行即可。
:: 本文件为 GBK 编码，请勿用 UTF-8 保存。
:: ============================================================

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "DEP_DIR=%SCRIPT_DIR%\dependency\cloakbrowser"
set "ARCHIVE=%SCRIPT_DIR%\cloakbrowser-windows-x64.zip"
set "VERSION=146.0.7680.177.5"

echo.
echo ============================================
echo   CloakBrowser 升级 ^(Windows x64^)
echo   目标版本: %VERSION%
echo ============================================
echo.

if not exist "%ARCHIVE%" (
    echo   [X] 未找到 cloakbrowser-windows-x64.zip
    echo       请把压缩包和本脚本放在同一目录（项目根目录）
    pause
    exit /b 1
)

if not exist "%SCRIPT_DIR%\dependency" (
    echo   [X] 未找到 dependency 目录
    echo       请把本脚本放到项目根目录（和 start.bat 同级）
    pause
    exit /b 1
)

:: --- 备份旧版本 ---
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMddHHmmss"') do set "TS=%%i"
if exist "%DEP_DIR%" (
    echo   备份旧版本...
    rename "%DEP_DIR%" "cloakbrowser.bak-!TS!" >nul 2>&1
    if exist "%DEP_DIR%" (
        echo   [X] 备份失败，请先关闭正在运行的程序后重试
        pause
        exit /b 1
    )
)

:: --- 解压新版本（显式使用系统自带 bsdtar，避免 PATH 里 GNU tar 把 D:\ 当远程主机）---
echo   解压新版本，请稍候（约 1-2 分钟）...
mkdir "%DEP_DIR%" 2>nul
%SystemRoot%\System32\tar.exe -xf "%ARCHIVE%" -C "%DEP_DIR%"
if not exist "%DEP_DIR%\chrome.exe" (
    echo   [X] 解压失败，正在恢复旧版本...
    rmdir /s /q "%DEP_DIR%" >nul 2>&1
    if exist "%SCRIPT_DIR%\dependency\cloakbrowser.bak-!TS!" rename "%SCRIPT_DIR%\dependency\cloakbrowser.bak-!TS!" "cloakbrowser" >nul 2>&1
    echo       已恢复，请重新下载压缩包后再试
    pause
    exit /b 1
)

>"%DEP_DIR%\.version" echo %VERSION%

echo.
echo   [OK] 升级完成！
echo        旧版本备份在: dependency\cloakbrowser.bak-!TS!
echo        确认程序启动正常后，可手动删除备份目录释放空间
echo        重新运行 start.bat 即可使用新版本
echo.
pause
