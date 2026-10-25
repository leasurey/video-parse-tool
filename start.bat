@echo off
rem Pure ASCII on purpose: cmd reads .bat with the OEM codepage (GBK on zh-CN),
rem so UTF-8 Chinese here would be garbled and break command parsing.
cd /d %~dp0
echo ============================================
echo   Video Parse Tool - Start
echo ============================================
if not exist venv\Scripts\python.exe (
    echo [ERROR] Virtual environment not found.
    echo         Please run install.bat first.
    pause
    exit /b 1
)
if not exist config.json (
    if exist config.example.json (
        copy /y config.example.json config.json >nul
        echo [INFO] config.json created from config.example.json
    )
)
echo [INFO] Starting server, browser will open automatically...
echo [INFO] Keep this window open. Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe backend\main.py
echo.
echo [INFO] Server stopped.
pause
