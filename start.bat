@echo off
title 交互节律
cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

:: Install deps if needed
if not exist ".venv" (
    echo [交互节律] First run - installing dependencies...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

:: Run
echo [交互节律] Starting...
python main.py
pause
