@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0Setup-Environment.bat"
if errorlevel 1 goto :fail

echo Running repository hygiene checks...
"%BLAST_PYTHON%" "scripts\repo_hygiene.py"
if errorlevel 1 goto :fail

echo Running unit tests...
"%BLAST_PYTHON%" -m unittest discover -s tests -v
if errorlevel 1 goto :fail

echo.
echo Checking Python compilation...
"%BLAST_PYTHON%" -m compileall -q scripts tests
if errorlevel 1 goto :fail

echo.
echo Building standalone executable...
call "%~dp0Build-Standalone-Exe.bat"
if errorlevel 1 goto :fail

echo.
echo Smoke-testing standalone executable...
"%CD%\dist\BlastFromTheAds.exe" --smoke-test
if errorlevel 1 goto :fail

echo.
echo Checking package secrets and metadata...
if exist "dist\.env" goto :secretfail
if exist "dist\BlastFromTheAds-package\.env" goto :secretfail
if not exist "dist\release-metadata\SHA256SUMS.txt" goto :metadatafail
if not exist "dist\release-metadata\sbom.spdx.json" goto :metadatafail

echo.
echo Release verification complete.
exit /b 0

:secretfail
echo.
echo Release verification failed: packaged .env file found.
exit /b 1

:metadatafail
echo.
echo Release verification failed: release metadata is missing.
exit /b 1

:fail
echo.
echo Release verification failed.
exit /b 1
