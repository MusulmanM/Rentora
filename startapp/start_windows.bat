@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.11+ first.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv >nul 2>nul
  if errorlevel 1 (
    py -3.13 -m venv .venv >nul 2>nul
    if errorlevel 1 (
      py -3.11 -m venv .venv >nul 2>nul
      if errorlevel 1 (
        echo Python 3.11, 3.12, or 3.13 was not found. Install a supported version.
        pause
        exit /b 1
      )
    )
  )
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
if errorlevel 1 goto failed
python -m pip install -r requirements.txt
if errorlevel 1 goto failed
python manage.py migrate
if errorlevel 1 goto failed
python manage.py seed_demo
if errorlevel 1 goto failed
echo.
set /p create_admin=Create a Django admin user now? [Y/N]: 
if /I "%create_admin%"=="Y" (
  python manage.py createsuperuser
  if errorlevel 1 goto failed
)
echo.
echo Rentora is ready. Open http://127.0.0.1:8000 in your browser.
python manage.py runserver
exit /b 0
:failed
echo Setup failed. Check the error above, internet connection, and Python installation.
pause
exit /b 1
