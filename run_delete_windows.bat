@echo off
setlocal
cd /d "%~dp0"
call run_with_browser_windows.bat --threshold 4 --delete
set "EXIT_CODE=%errorlevel%"
pause
exit /b %EXIT_CODE%
