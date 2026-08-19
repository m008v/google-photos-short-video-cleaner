@echo off
setlocal
cd /d "%~dp0"
call run_with_browser_windows.bat --threshold 4 --delete --limit 3 --batch-size 3
set "EXIT_CODE=%errorlevel%"
pause
exit /b %EXIT_CODE%
