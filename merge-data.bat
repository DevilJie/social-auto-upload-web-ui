@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: 优先使用 dependency 目录下的 Python（与 start.bat 一致）
if exist "%SCRIPT_DIR%\dependency\python" (
    set "PATH=%SCRIPT_DIR%\dependency\python;%SCRIPT_DIR%\dependency\python\Scripts;%PATH%"
)

set "VENV_PYTHON=%SCRIPT_DIR%\backend\.venv\Scripts\python.exe"
set "PROJECT_DATA=%SCRIPT_DIR%\data"

if not exist "%VENV_PYTHON%" (
    echo [错误] 未找到虚拟环境 Python: %VENV_PYTHON%
    echo 请先执行 start.bat 启动后端
    pause
    exit /b 1
)

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
    exit /b 1
)

set "SOURCE=%SOURCE:"=%"

if "%SOURCE%"=="" (
    echo [错误] 未输入路径
    pause
    exit /b 1
)

if not exist "%SOURCE%" (
    echo [错误] 目录不存在: %SOURCE%
    pause
    exit /b 1
)

echo.
echo 源目录：
echo %SOURCE%
echo 目标目录：
echo %PROJECT_DATA%
echo.
echo 提示：先执行 start.bat 启动后端，再运行本脚本。
echo.

"%VENV_PYTHON%" "%SCRIPT_DIR%\scripts\migrate_legacy_data.py" --source "%SOURCE%" --target "%PROJECT_DATA%" --yes
pause

endlocal
