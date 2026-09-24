@echo off
cd /d "%~dp0"
set "PY=%USERPROFILE%\anaconda3\envs\subtranslator\python.exe"
if not exist "%PY%" (
    echo 找不到 Python 环境：%PY%
    echo 请先让 Claude Code 完成「阶段 0：环境准备」。
    pause
    exit /b 1
)
"%PY%" -m app.main
if errorlevel 1 (
    echo.
    echo 程序异常退出，请把上面的信息发给 Claude Code。
    pause
)
