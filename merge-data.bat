@echo off
chcp 65001 >nul
setlocal

:: ============================================================
:: 旧版数据迁移脚本 — Windows
:: ============================================================
::
:: 本脚本会调用 scripts\migrate_legacy_data.py，
:: 把旧版 Windows 客户端的用户数据迁移到当前项目的 data\ 目录。
::
:: 迁移前请先执行 start.bat 启动后端（需要 5409 端口可达）。
:: 脚本会先备份当前 data\ 到 data.bak.YYYYMMDD_HHMMSS\，再迁移数据。

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "PROJECT_DATA=%SCRIPT_DIR%\data"

echo.
echo ============================================================
echo   旧版数据迁移到新版 data 目录
echo ============================================================
echo.
echo 此目录是需要迁移的源数据目录。请根据你的使用场景选择：
echo.
echo   [场景 A] Windows 一键 EXE 安装包用户
echo     数据目录: C:\Users\%%USERNAME%%\AppData\Local\Social Auto Upload Web UI
echo     包含 cookies\、cookiesFile\、db\、videoFile\ 四个子目录
echo.
echo   [场景 B] 从 GitHub clone 源代码启动
echo     数据目录: 项目根目录下的 data 目录
echo     （即 merge-data.bat 所在目录的 data 子目录）
echo.
echo   [场景 C] 其他情况（如从备份恢复 .zip 解压）
echo     直接输入数据目录的完整路径
echo.
echo 目标目录（自动计算）: %PROJECT_DATA%
echo.
echo ============================================================
echo.

set "SOURCE="
set /p "SOURCE=请输入需要迁移的源数据目录完整路径: "

if "%SOURCE%"=="" (
    echo.
    echo [错误] 未输入路径
    pause
    exit /b 1
)

if not exist "%SOURCE%" (
    echo.
    echo [错误] 目录不存在: %SOURCE%
    pause
    exit /b 1
)

echo.
echo 源目录: %SOURCE%
echo 目标目录: %PROJECT_DATA%
echo.
echo 提示：先执行 start.bat 启动后端，再运行本脚本。
echo 脚本会先备份当前 data 到 data.bak.YYYYMMDD_HHMMSS，再迁移数据。
echo.
pause

python "%SCRIPT_DIR%\scripts\migrate_legacy_data.py" --source "%SOURCE%" --target "%PROJECT_DATA%" --yes

endlocal
