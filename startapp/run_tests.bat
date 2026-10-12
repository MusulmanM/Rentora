@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run start_windows.bat first to create the environment.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python manage.py test core
pause
