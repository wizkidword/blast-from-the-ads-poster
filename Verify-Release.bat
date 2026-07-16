@echo off
setlocal
cd /d "%~dp0"

echo Running unit tests...
python -m unittest discover -s tests -v
if errorlevel 1 goto :fail

echo.
echo Checking Python compilation...
python -m compileall -q scripts tests
if errorlevel 1 goto :fail

echo.
echo Checking setup...
python scripts\workflow.py setup
if errorlevel 1 goto :fail

echo.
echo Building standalone executable...
cmd /c Build-Standalone-Exe.bat
if errorlevel 1 goto :fail

echo.
echo Checking package secrets...
if exist "dist\.env" goto :secretfail
if exist "dist\BlastFromTheAds-package\.env" goto :secretfail

echo.
echo Release verification complete.
exit /b 0

:secretfail
echo.
echo Release verification failed: packaged .env file found.
exit /b 1

:fail
echo.
echo Release verification failed.
exit /b 1
