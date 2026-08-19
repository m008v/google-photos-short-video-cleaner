@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Chua cai dat. Hay chay setup_windows.bat truoc.
  pause
  exit /b 1
)
.venv\Scripts\python.exe gphotos_short_video_cleaner.py --threshold 4 --language vi-VN --close-browser
pause
