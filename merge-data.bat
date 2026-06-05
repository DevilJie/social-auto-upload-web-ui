@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: 旧版数据迁移脚本 — Windows
:: ============================================================
::
:: 调用 scripts\migrate_legacy_data.py 把指定目录的旧版数据迁移到 data\。

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_DATA=%SCRIPT_DIR%\data"

echo.
echo ============================================================
echo   旧版数据迁移到新版 data 目录
echo ============================================================
echo.
echo 目标目录：
echo %PROJECT_DATA%
echo.
echo 请输入需要迁移的源数据目录完整路径
echo C:\Users\foo\AppData\Local\Social Auto Upload Web UI
echo.

set "SOURCE="
set /p "SOURCE=源数据目录: "
if errorlevel 1 (
    echo [错误] 读取输入失败
    pause
    goto :end
)

:: 去掉可能的首尾引号
set "SOURCE=!SOURCE:"=!"

if "!SOURCE!"=="" (
    echo [错误] 未输入路径
    pause
    goto :end
)

if not exist "!SOURCE!" (
    echo [错误] 目录不存在: !SOURCE!
    pause
    goto :end
)

echo.
echo 源目录：
echo !SOURCE!
echo 目标目录：
echo %PROJECT_DATA%
echo.
echo 提示：先执行 start.bat 启动后端，再运行本脚本。
echo.

python "%SCRIPT_DIR%\scripts\migrate_legacy_data.py" --source "!SOURCE!" --target "%PROJECT_DATA%" --yes
pause

:end
endlocal
