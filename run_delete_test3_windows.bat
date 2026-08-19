@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Chua cai dat. Hay chay setup_windows.bat truoc.
  pause
  exit /b 1
)
echo Tool se dry-run truoc, sau do chi chuyen toi da 3 video vao Thung rac.
.venv\Scripts\python.exe gphotos_short_video_cleaner.py --threshold 4 --delete --limit 3 --batch-size 3 --language vi-VN --close-browser
pause
