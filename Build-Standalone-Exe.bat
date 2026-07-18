@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0Setup-Environment.bat"
if errorlevel 1 goto :fail

echo Cleaning previous build output...
if exist "%CD%\build" rmdir /s /q "%CD%\build"
if exist "%CD%\dist" rmdir /s /q "%CD%\dist"

echo Building standalone executable...
"%BLAST_PYTHON%" -m PyInstaller --noconfirm --clean "BlastFromTheAds.spec"
if errorlevel 1 goto :fail

mkdir "dist\BlastFromTheAds-package" >nul 2>nul
copy /Y "dist\BlastFromTheAds.exe" "dist\BlastFromTheAds-package\BlastFromTheAds.exe" >nul
if errorlevel 1 goto :fail
copy /Y ".env.example" "dist\BlastFromTheAds-package\.env.example" >nul
if errorlevel 1 goto :fail
copy /Y "settings.example.json" "dist\BlastFromTheAds-package\settings.example.json" >nul
if errorlevel 1 goto :fail
copy /Y "README.md" "dist\BlastFromTheAds-package\README.md" >nul
if errorlevel 1 goto :fail
copy /Y "CHANGELOG.md" "dist\BlastFromTheAds-package\CHANGELOG.md" >nul
if errorlevel 1 goto :fail

echo Writing release checksums and SBOM...
"%BLAST_PYTHON%" "scripts\release_artifacts.py" --artifact-root "dist" --requirements "requirements-windows-py313.txt" --output-dir "dist\release-metadata"
if errorlevel 1 goto :fail

echo.
echo Build complete.
echo EXE: %CD%\dist\BlastFromTheAds.exe
echo Package folder: %CD%\dist\BlastFromTheAds-package
echo Metadata: %CD%\dist\release-metadata
echo Private .env and local settings.json were not copied.
exit /b 0

:fail
echo.
echo Standalone build failed.
exit /b 1
