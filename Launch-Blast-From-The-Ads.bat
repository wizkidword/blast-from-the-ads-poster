@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail

  echo Installing Python requirements...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  if errorlevel 1 goto :fail
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
)

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "scripts\social_batch_app.py"
) else (
  start "" ".venv\Scripts\python.exe" "scripts\social_batch_app.py"
)
exit /b 0

:fail
echo.
echo Launcher setup failed. Run these commands manually:
echo   py -3 -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
pause
exit /b 1
