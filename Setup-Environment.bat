@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYTHON_PATH=%CD%\.venv\Scripts\python.exe"

if not exist "%PYTHON_PATH%" (
  echo Creating CPython 3.13 virtual environment...
  py -3.13 -m venv .venv
  if errorlevel 1 goto :fail
)

"%PYTHON_PATH%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 13) else 1)"
if errorlevel 1 (
  echo The existing .venv is not CPython 3.13. Recreate .venv with py -3.13 -m venv .venv.
  goto :fail
)

echo Synchronizing locked Python dependencies...
"%PYTHON_PATH%" -m pip install --disable-pip-version-check --require-hashes --upgrade -r "%CD%\requirements-windows-py313.txt"
if errorlevel 1 goto :fail

endlocal & set "BLAST_PYTHON=%PYTHON_PATH%"
exit /b 0

:fail
endlocal & exit /b 1
