@echo off
setlocal
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo Chua cai dat. Hay chay setup_windows.bat truoc.
  pause
  exit /b 1
)
echo Tool se dry-run truoc, sau do yeu cau nhap MOVE_TO_TRASH.
echo Khuyen nghi chay run_delete_test3_windows.bat truoc.
.venv\Scripts\python.exe gphotos_short_video_cleaner.py --threshold 4 --delete --language vi-VN --close-browser
pause
