@echo off
cd /d %~dp0
title Allow LAN access (firewall)

rem --- Require administrator: relaunch with UAC if not elevated ---
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [i] Administrator rights are required. Asking for elevation...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

if not exist config.json (
  echo [!] config.json not found.
  pause
  exit /b 1
)

rem --- Read host / port from config.json ---
for /f "delims=" %%P in ('venv\Scripts\python.exe -c "import json;print(json.load(open('config.json',encoding='utf-8')).get('port',8000))"') do set PORT=%%P
for /f "delims=" %%H in ('venv\Scripts\python.exe -c "import json;print(json.load(open('config.json',encoding='utf-8')).get('host','127.0.0.1'))"') do set HOST=%%H

echo.
echo Config: host=%HOST%  port=%PORT%
echo.

if not "%HOST%"=="0.0.0.0" (
  echo [!] host in config.json is not 0.0.0.0 - the server only listens on this PC.
  echo     Set "host": "0.0.0.0" in config.json, restart start.bat, then run this again.
  pause
  exit /b 1
)

echo Allowing inbound TCP %PORT% (private/domain profiles, local subnet only)...
netsh advfirewall firewall delete rule name="VideoParseTool-LAN" >nul 2>&1
netsh advfirewall firewall add rule name="VideoParseTool-LAN" dir=in action=allow protocol=TCP localport=%PORT% profile=private,domain remoteip=localsubnet

if %errorlevel% equ 0 (
  echo.
  echo [OK] Firewall rule added for TCP %PORT% (local subnet only).
  echo      Open one of these addresses in your phone browser:
  venv\Scripts\python.exe -c "import socket,json;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('223.5.5.5',80));print('        http://'+s.getsockname()[0]+':'+str(json.load(open('config.json',encoding='utf-8')).get('port',8000)))"
  echo.
  echo To remove the rule later:
  echo      netsh advfirewall firewall delete rule name="VideoParseTool-LAN"
) else (
  echo [!] Failed to add the rule. Make sure you allowed the UAC prompt.
)
echo.
pause
