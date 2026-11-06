@echo off
chcp 65001 >nul
cd /d "%~dp0"
"%~dp0SpetTest.exe" stable
echo.
pause
