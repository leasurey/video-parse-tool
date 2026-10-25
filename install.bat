@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo   视频解析下载工具 - 依赖安装
echo ============================================

rem 依次尝试 py 启动器 / python，选择可用的 Python 3
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY (
    echo [错误] 未找到 Python，请先安装 Python 3.10 或更高版本
    echo        下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo 使用解释器: %PY%
%PY% --version
if errorlevel 1 (
    echo [错误] Python 无法正常运行
    pause
    exit /b 1
)

echo 正在创建虚拟环境...
if not exist venv (
    %PY% -m venv venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

echo 正在安装依赖 (首次约需 1-3 分钟)...
venv\Scripts\python.exe -m pip install --upgrade pip --timeout 60 --retries 5
venv\Scripts\python.exe -m pip install -r requirements.txt --timeout 60 --retries 5
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络后重试
    pause
    exit /b 1
)

if not exist config.json (
    if exist config.example.json (
        copy /y config.example.json config.json >nul
        echo 已根据 config.example.json 生成 config.json
    )
)

echo.
echo 安装完成! 双击 start.bat 启动工具。
pause
