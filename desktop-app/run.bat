@echo off
:: GhostWire launcher — Windows
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python 3 is required. Download from https://python.org
    pause
    exit /b 1
)

python -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Installing dependencies...
    pip install -r requirements.txt
)

python main.py
pause
