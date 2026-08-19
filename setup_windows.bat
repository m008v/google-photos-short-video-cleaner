@echo off
setlocal
cd /d "%~dp0"
py -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo Can Python 3.10 tro len. Kiem tra bang lenh: py --version
  pause
  exit /b 1
)
py -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt
if errorlevel 1 goto :error
python -m unittest discover -s tests -v
if errorlevel 1 goto :error
echo.
echo Cai dat va kiem thu hoan tat.
pause
exit /b 0
:error
echo.
echo Cai dat that bai. Kiem tra Python, Internet va quyen ghi thu muc.
pause
exit /b 1
