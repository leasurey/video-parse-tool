@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   视频解析下载工具 - 一键启动
echo ============================================
if not exist venv\Scripts\python.exe (
    echo [错误] 未找到虚拟环境, 请先双击运行 install.bat 安装依赖
    pause
    exit /b 1
)
venv\Scripts\python.exe backend\main.py
pause
