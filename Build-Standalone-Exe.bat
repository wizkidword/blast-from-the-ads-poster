@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating local virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 goto :fail
)

echo Installing build dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip pyinstaller
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo Cleaning previous build output...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo Building standalone executable...
".venv\Scripts\pyinstaller.exe" ^
  --noconfirm ^
  --clean ^
  --onefile ^
  --windowed ^
  --name "BlastFromTheAds" ^
  --paths "%cd%\scripts" ^
--hidden-import "app_metadata" ^
--hidden-import "app_paths" ^
--hidden-import "ai_analysis" ^
--hidden-import "blast_workflow" ^
--hidden-import "caption_builder" ^
--hidden-import "cancellable_subprocess" ^
--hidden-import "cleanup" ^
--hidden-import "desktop_requeue" ^
--hidden-import "desktop_review" ^
--hidden-import "desktop_settings" ^
--hidden-import "desktop_status" ^
--hidden-import "desktop_theme" ^
--hidden-import "desktop_workflow" ^
--hidden-import "export_packs" ^
--hidden-import "manifest_service" ^
--hidden-import "media_artifacts" ^
--hidden-import "media_rules" ^
--hidden-import "media_processing" ^
--hidden-import "platform_profiles" ^
--hidden-import "process_inbox_social" ^
--hidden-import "processing_orchestrator" ^
--hidden-import "processing_transaction" ^
--hidden-import "publishing" ^
  --hidden-import "requeue" ^
  --hidden-import "recovery_queue" ^
  --hidden-import "review_queue" ^
  --hidden-import "run_ledger" ^
  --hidden-import "run_history" ^
  --hidden-import "settings_store" ^
  --hidden-import "thumbnails" ^
  --hidden-import "workspace_lock" ^
  "scripts\social_batch_app.py"
if errorlevel 1 goto :fail

mkdir "dist\BlastFromTheAds-package" >nul 2>nul
copy /Y "dist\BlastFromTheAds.exe" "dist\BlastFromTheAds-package\BlastFromTheAds.exe" >nul
copy /Y ".env.example" "dist\BlastFromTheAds-package\.env.example" >nul
copy /Y "README.md" "dist\BlastFromTheAds-package\README.md" >nul
copy /Y "CHANGELOG.md" "dist\BlastFromTheAds-package\CHANGELOG.md" >nul

echo.
echo Build complete.
echo EXE: %cd%\dist\BlastFromTheAds.exe
echo Package folder: %cd%\dist\BlastFromTheAds-package
echo Private .env was not copied. Add it beside the EXE only on the machine that runs the app.
exit /b 0

:fail
echo.
echo Standalone build failed.
pause
exit /b 1
