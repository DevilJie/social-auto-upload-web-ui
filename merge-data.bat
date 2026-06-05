@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: ============================================================
:: 旧版数据迁移脚本 — Windows
:: ============================================================
::
:: 用法:
::   merge-data.bat "C:\old\data\dir"              直接传入源目录
::   merge-data.bat                                 交互式输入
::   merge-data.bat --target "D:\target" "source"   指定目标目录
::
:: 调用 scripts\migrate_legacy_data.py 把旧版数据迁移到 data\。

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_DATA=%SCRIPT_DIR%\data"

set "SOURCE="
set "TARGET="

:: ----------------------------------------------------------
:: 解析命令行参数
:: ----------------------------------------------------------
:parse_args
if "%~1"=="" goto :after_args
if /i "%~1"=="--target" (
    set "TARGET=%~2"
    shift
    shift
    goto :parse_args
)
if /i "%~1"=="--yes" (
    set "AUTO_YES=--yes"
    shift
    goto :parse_args
)
:: 第一个非选项参数作为源目录；后续非选项参数忽略
if "!SOURCE!"=="" (
    set "SOURCE=%~1"
)
shift
goto :parse_args

:after_args

:: 如未通过参数指定目标目录，使用默认值
if "!TARGET!"=="" set "TARGET=%PROJECT_DATA%"

echo.
echo ============================================================
echo   旧版数据迁移到新版 data 目录
echo ============================================================
echo.
echo 目标目录: !TARGET!
echo.

:: ----------------------------------------------------------
:: 未通过参数传入源目录 → 交互式输入
:: ----------------------------------------------------------
if not "!SOURCE!"=="" goto :check_source

echo 请输入需要迁移的源数据目录完整路径。
echo （例如：C:\Users\foo\AppData\Local\Social Auto Upload Web UI）
echo.

set "SOURCE="
set /p "SOURCE=源数据目录: "
if errorlevel 1 (
    echo [错误] 读取输入失败
    pause
    goto :end
)

:check_source
if "!SOURCE!"=="" (
    echo [错误] 未输入路径
    pause
    goto :end
)

:: 去掉可能的首尾引号
set "SOURCE=!SOURCE:"=!"

if not exist "!SOURCE!" (
    echo [错误] 目录不存在: !SOURCE!
    pause
    goto :end
)

echo.
echo 源目录: !SOURCE!
echo 目标目录: !TARGET!
echo.
echo 提示：先执行 start.bat 启动后端，再运行本脚本。
echo.

python "%SCRIPT_DIR%\scripts\migrate_legacy_data.py" --source "!SOURCE!" --target "!TARGET!" !AUTO_YES!
pause

:end
endlocal
