@echo off
setlocal EnableDelayedExpansion

REM Get the current directory
set "CURRENT_DIR=%CD%"
echo Current directory is: %CURRENT_DIR%

REM Set PYTHONPATH to include current directory
set "PYTHONPATH=%CURRENT_DIR%;%PYTHONPATH%"
echo Set PYTHONPATH to include current directory: %PYTHONPATH%

REM Check if virtual environment exists
if exist venv (
    echo Found existing virtual environment
) else (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Set test environment variable
set TEST_ENV=true

REM Install requirements if needed
echo Installing requirements...
pip install -r requirements.txt > nul 2>&1

REM Run tests and deployment
echo Checking test configuration...
echo === Running Pre-deployment Tests ===

REM Run unit tests first
echo.
echo Step 1: Running unit_tests tests...

REM Upgrade pip silently
python -m pip install --upgrade pip --quiet

REM Install requirements
echo Installing requirements...
python -m pip install -r requirements.txt --quiet --no-warn-script-location
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to install requirements
    python -m pip install -r requirements.txt
    exit /b 1
)

REM Run pre-deployment tests if enabled in config
echo.
echo Checking test configuration...

REM Create Python script content in a variable
set PYTHON_SCRIPT=import yaml^

import json^

config = yaml.safe_load(open('config.yaml'))^

test_config = config.get('testing', {})^

components = test_config.get('components', {})^

test_paths = test_config.get('test_paths', {})^

test_order = test_config.get('test_order', ['unit_tests', 'package_tests', 'config_tests', 'integration_tests'])^

run_tests = '1' if test_config.get('run_after_deployment', False) else '0'^

run_all = '1' if test_config.get('run_all_tests', False) else '0'^

print(f'RUN_TESTS={run_tests}')^

print(f'RUN_ALL={run_all}')^

print(f'TEST_ORDER={",".join(test_order)}')^

for test_type in test_order:^

    enabled = '1' if components.get(test_type, True) else '0'^

    print(f'{test_type.upper()}_ENABLED={enabled}')^

    paths = test_paths.get(test_type, [])^

    if paths:^

        print(f'{test_type.upper()}_PATHS={" ".join(paths)}')

REM Write Python script to file
echo !PYTHON_SCRIPT! > temp_config.py

REM Execute the temporary script and capture output
for /f "usebackq tokens=1,* delims==" %%a in (`python temp_config.py`) do (
    set "%%a=%%b"
)
del temp_config.py

if "%RUN_TESTS%"=="1" (
    echo === Running Pre-deployment Tests ===
    echo.
    
    set STEP=1
    
    REM Execute tests in order
    for %%t in (%TEST_ORDER:,= %) do (
        set "TEST_TYPE=%%t"
        set "ENABLED=!%%t_ENABLED!"
        set "PATHS=!%%t_PATHS!"
        
        if "!ENABLED!"=="1" (
            echo.
            echo Step !STEP!: Running !TEST_TYPE! tests...
            
            if "!TEST_TYPE!"=="unit_tests" (
                if "%RUN_ALL%"=="1" (
                    python -m pytest tests -v
                ) else (
                    for %%f in (!PATHS!) do (
                        echo Running tests in: %%f
                        python -m pytest %%f -v
                        if !ERRORLEVEL! NEQ 0 (
                            echo Error: Unit tests failed in %%f
                            exit /b 1
                        )
                    )
                )
            ) else if "!TEST_TYPE!"=="package_tests" (
                for %%f in (!PATHS!) do (
                    python %%f
                    if !ERRORLEVEL! NEQ 0 (
                        echo Error: Package tests failed
                        exit /b 1
                    )
                )
            ) else if "!TEST_TYPE!"=="config_tests" (
                for %%f in (!PATHS!) do (
                    python %%f
                    if !ERRORLEVEL! NEQ 0 (
                        echo Error: Configuration tests failed
                        exit /b 1
                    )
                )
            ) else if "!TEST_TYPE!"=="integration_tests" (
                REM Integration tests are run after deployment
                echo Integration tests will run after deployment
            )
        ) else (
            echo Skipping !TEST_TYPE! ^(disabled in config^)
        )
        
        set /a STEP+=1
    )
    
    echo.
    echo === All Pre-deployment Tests Passed ===
    echo.
) else (
    echo Skipping tests (disabled in config.yaml)
    echo.
)

echo === Starting Deployment ===
echo.

REM Deploy storage buckets
echo Step 1: Deploying storage buckets...
python scripts/deploy_storage.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy storage buckets
    exit /b 1
)

REM Set up service accounts
echo Step 2: Setting up service accounts...
python scripts/setup_service_accounts.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to set up service accounts
    exit /b 1
)

REM Deploy credentials
echo Step 3: Deploying credentials...
python scripts/deploy_credentials.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy credentials
    exit /b 1
)

REM Wait for a moment to ensure all resources are ready
echo.
set PYTHON_WAIT=import yaml^

config = yaml.safe_load(open('config.yaml'))^

print(config.get('testing', {}).get('wait_time', 5))

echo !PYTHON_WAIT! > temp_wait.py

for /f %%i in ('python temp_wait.py') do set WAIT_TIME=%%i
del temp_wait.py

echo Waiting for %WAIT_TIME% seconds to ensure all resources are ready...
timeout /t %WAIT_TIME% /nobreak > nul

REM Deploy Cloud Function and Scheduler
echo Step 4: Deploying Cloud Function and Scheduler...
python scripts/deploy_functions.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy Cloud Function and Scheduler
    exit /b 1
)

REM Run post-deployment integration tests if enabled
if "%RUN_TESTS%"=="1" (
    echo.
    echo Step 5: Running post-deployment test...
    for %%f in (%POST_DEPLOYMENT_PATHS%) do (
        python %%f
        if !ERRORLEVEL! NEQ 0 (
            echo Warning: Post-deployment test failed
            echo Please check the logs above for details
            exit /b 1
        )
    )
)

echo.
echo === Deployment Completed Successfully ===
exit /b 0