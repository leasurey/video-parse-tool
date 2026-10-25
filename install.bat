@echo off
rem Pure ASCII on purpose: cmd reads .bat with the OEM codepage (GBK on zh-CN),
rem so UTF-8 Chinese here would be garbled and break command parsing.
cd /d %~dp0
echo ============================================
echo   Video Parse Tool - Install dependencies
echo ============================================

rem Try the py launcher first, then fall back to python
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [ERROR] Python not found. Please install Python 3.10 or newer.
    echo         Download: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [INFO] Interpreter: %PY%
%PY% --version
if errorlevel 1 (
    echo [ERROR] Python cannot run properly.
    pause
    exit /b 1
)

echo [INFO] Creating virtual environment...
if not exist venv (
    %PY% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo [INFO] Installing dependencies (first run takes 1-3 minutes)...
venv\Scripts\python.exe -m pip install --upgrade pip --timeout 60 --retries 5
venv\Scripts\python.exe -m pip install -r requirements.txt --timeout 60 --retries 5
if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check your network and retry.
    pause
    exit /b 1
)

if not exist config.json (
    if exist config.example.json (
        copy /y config.example.json config.json >nul
        echo [INFO] config.json created from config.example.json
    )
)

echo.
echo [OK] Done. Double-click start.bat to launch the tool.
pause
