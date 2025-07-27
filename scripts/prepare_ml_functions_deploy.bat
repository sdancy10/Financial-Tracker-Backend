@echo off
echo ================================
echo Preparing ML Functions for Deployment
echo ================================
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

echo Step 1: Testing import transformations...
python scripts/test_ml_function_imports.py
if errorlevel 1 (
    echo.
    echo ERROR: Import transformation test failed!
    echo Please fix the import issues before continuing.
    pause
    exit /b 1
)

echo.
echo Step 2: Cleaning up previous packages...
if exist temp rmdir /s /q temp
echo.

echo Step 3: Packaging ML functions...
python scripts/deploy_ml_functions.py --prepare-only
if errorlevel 1 (
    echo.
    echo ERROR: Function packaging failed!
    pause
    exit /b 1
)

echo.
echo ================================
echo ML Functions Ready for Deployment!
echo ================================
echo.
echo Next steps:
echo 1. cd terraform
echo 2. terraform plan
echo 3. terraform apply
echo.
pause 