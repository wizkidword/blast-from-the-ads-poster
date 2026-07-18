@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0Setup-Environment.bat"
if errorlevel 1 goto :fail

if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" "scripts\social_batch_app.py"
) else (
  start "" "%BLAST_PYTHON%" "scripts\social_batch_app.py"
)
exit /b 0

:fail
echo.
echo Launcher setup failed. See the messages above, then rerun this file.
pause
exit /b 1
