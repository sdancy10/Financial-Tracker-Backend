@echo off
setlocal

REM Get the current directory
set "CURRENT_DIR=%CD%"
echo Current directory is: %CURRENT_DIR%

REM Set PYTHONPATH to include current directory
set "PYTHONPATH=%CURRENT_DIR%;%PYTHONPATH%"
echo Set PYTHONPATH to include current directory: %PYTHONPATH%

REM Check for virtual environment
if exist "venv\Scripts\activate.bat" (
    echo Found existing virtual environment
) else (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Upgrade pip silently
python -m pip install --upgrade pip --quiet

REM Install requirements
echo Installing requirements...
python -m pip install -r requirements.txt --quiet --no-warn-script-location
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to install requirements
    python -m pip install -r requirements.txt  REM Run again with full output for debugging
    exit /b 1
)

echo.
echo === Running Tests in Order ===
echo.

REM 1. Run unit tests first (fastest)
echo Step 1: Running unit tests...
python -m pytest tests/test_gmail_integration.py -v
if %ERRORLEVEL% NEQ 0 (
    echo Error: Unit tests failed
    exit /b 1
)

REM 2. Test deployment package (checks imports and dependencies)
echo.
echo Step 2: Testing deployment package...
python scripts/test_deployment_package.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Deployment package tests failed
    exit /b 1
)

REM 3. Test deployment configuration
echo.
echo Step 3: Testing deployment configuration...
python scripts/test_deployment.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Deployment configuration tests failed
    exit /b 1
)

REM If all tests pass, proceed with deployment
echo.
echo === All Tests Passed - Starting Deployment ===
echo.

REM Deploy storage buckets
echo Step 4: Deploying storage buckets...
python scripts/deploy_storage.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy storage buckets
    exit /b 1
)

REM Set up service accounts
echo Step 5: Setting up service accounts...
python scripts/setup_service_accounts.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to set up service accounts
    exit /b 1
)

REM Deploy credentials
echo Step 6: Deploying credentials...
python scripts/deploy_credentials.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy credentials
    exit /b 1
)

REM Wait for a moment to ensure all resources are ready
echo.
echo Waiting for 5 seconds to ensure all resources are ready...
timeout /t 5 /nobreak > nul

REM Deploy Cloud Function and Scheduler
echo Step 7: Deploying Cloud Function and Scheduler...
python scripts/deploy_functions.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy Cloud Function and Scheduler
    exit /b 1
)

REM Final test - Test the deployed function
echo.
echo Step 8: Testing deployed function...
python scripts/test_function.py
if %ERRORLEVEL% NEQ 0 (
    echo Warning: Deployed function test failed
    echo Please check the logs above for details
    exit /b 1
)

echo.
echo === Deployment and Testing Completed Successfully ===
exit /b 0 