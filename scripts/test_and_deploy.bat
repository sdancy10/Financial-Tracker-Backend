@echo off
setlocal

REM =====================================================================
REM  Python version: This project requires Python 3.11 to match the
REM  Cloud Functions runtime and pinned dependency versions (e.g.
REM  scikit-learn 1.3.1, pyarrow 13.0.0).  The Windows "py" launcher
REM  is used so the system-default Python (which may be 3.14) is never
REM  picked up.  Global Python installations are NOT modified.
REM  To recreate the venv (e.g. after a Python upgrade), simply delete
REM  the "venv" folder in the project root and re-run this script.
REM =====================================================================

set "REQUIRED_PY_MAJOR=3"
set "REQUIRED_PY_MINOR=11"

REM Set GOOGLE_APPLICATION_CREDENTIALS for Python and Google SDKs
set "GOOGLE_APPLICATION_CREDENTIALS=%CD%\credentials\service-account-key.json"
echo Set GOOGLE_APPLICATION_CREDENTIALS to: %GOOGLE_APPLICATION_CREDENTIALS%

REM Get the current directory
set "CURRENT_DIR=%CD%"
echo Current directory is: %CURRENT_DIR%

REM Set PYTHONPATH to include current directory
set "PYTHONPATH=%CURRENT_DIR%;%PYTHONPATH%"
echo Set PYTHONPATH to include current directory: %PYTHONPATH%

REM --- Verify the py launcher can find the required Python version -----
py -%REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR% --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python %REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR% is not installed.
    echo Available versions:
    py --list
    echo Install Python %REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR% or update REQUIRED_PY_MINOR in this script.
    exit /b 1
)

REM --- Create or validate venv -----------------------------------------
if exist "venv\Scripts\activate.bat" (
    echo Found existing virtual environment, checking Python version...
    call venv\Scripts\activate.bat

    REM Grab the venv Python's version string (e.g. "Python 3.11.9")
    for /f "tokens=2 delims= " %%V in ('python --version 2^>^&1') do set "VENV_VER=%%V"
    REM Extract major.minor (e.g. "3.11")
    for /f "tokens=1,2 delims=." %%A in ("%VENV_VER%") do set "VENV_MAJOR=%%A" & set "VENV_MINOR=%%B"

    if not "%VENV_MAJOR%"=="%REQUIRED_PY_MAJOR%" (
        echo WARNING: venv uses Python %VENV_VER% but %REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR% is required.
        echo Delete the "venv" folder and re-run this script to recreate it.
        exit /b 1
    )
    if not "%VENV_MINOR%"=="%REQUIRED_PY_MINOR%" (
        echo WARNING: venv uses Python %VENV_VER% but %REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR% is required.
        echo Delete the "venv" folder and re-run this script to recreate it.
        exit /b 1
    )
    echo   venv Python version: %VENV_VER% [OK]
) else (
    echo Creating virtual environment with Python %REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR%...
    py -%REQUIRED_PY_MAJOR%.%REQUIRED_PY_MINOR% -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to create virtual environment.
        exit /b 1
    )
    call venv\Scripts\activate.bat
)

REM Upgrade pip silently
python -m pip install --upgrade pip --quiet

REM Install requirements
echo Installing requirements...
python -m pip install -r requirements.txt --quiet --no-warn-script-location
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to install requirements
    echo Retrying with full output for debugging...
    python -m pip install -r requirements.txt
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