@echo off
rem XferBridge 外部工具启动器（优先使用系统 Python 3.11+）
cd /d "%~dp0"
set "PY="
for %%P in (py python python3) do (
    where %%P >nul 2>nul && set "PY=%%P" && goto found
)
:found
if not defined PY (
    echo [错误] 未找到 Python，请安装 Python 3.11+ 后重试。
    pause
    exit /b 1
)
%PY% run.py
if errorlevel 1 pause
