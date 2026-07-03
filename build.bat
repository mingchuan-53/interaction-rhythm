@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ========================================
echo   扣舷打包入口
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_utf8_ps1.ps1" "%~dp0build.ps1"
if errorlevel 1 (
  echo.
  echo [ERROR] 打包失败！
  pause
  exit /b 1
)

echo.
pause
