@echo off
cd /d "%~dp0"
set "PY=%USERPROFILE%\anaconda3\envs\subtranslator\python.exe"
echo 正在打包独立程序，请稍候（大约 1 到 3 分钟）...
"%PY%" -m PyInstaller --noconfirm --clean SubTranslator.spec
if errorlevel 1 (
    echo.
    echo 打包失败，请把上面的信息发给 Claude Code。
    pause
    exit /b 1
)
echo.
echo 打包完成：dist\SubTranslator\SubTranslator.exe
pause
