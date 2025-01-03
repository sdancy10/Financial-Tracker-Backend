@echo off
setlocal EnableDelayedExpansion

REM Check if running in Cloud Build
if defined CLOUD_BUILD (
    echo Running in Cloud Build environment
    set "NON_INTERACTIVE=1"
    echo Using Cloud Build service account authentication
    REM Skip GCP auth check in Cloud Build as it uses service account
    echo Using service account credentials for Terraform
    set "USE_GCP_AUTH=0"
) else (
    set "NON_INTERACTIVE=0"
    set "USE_GCP_AUTH=1"
)

REM Get the current directory
set "CURRENT_DIR=%CD%"
echo Current directory is: %CURRENT_DIR%

REM Set PYTHONPATH to include current directory
set "PYTHONPATH=%CURRENT_DIR%;%PYTHONPATH%"
echo Set PYTHONPATH to include current directory: %PYTHONPATH%

REM Install pyyaml if needed
echo Installing required Python packages...
pip install pyyaml --quiet

REM Create a temporary Python script to read config
echo import yaml > read_config.py
echo with open('config.yaml', 'r') as f: >> read_config.py
echo     config = yaml.safe_load(f) >> read_config.py
echo print('PROJECT_ID=' + str(config['gcp']['project_id']).strip()) >> read_config.py
echo print('REGION=' + str(config['gcp']['region']).strip()) >> read_config.py

REM Get project ID and region from config.yaml
echo Reading project configuration...
python read_config.py > config_output.tmp
for /f "usebackq tokens=1,* delims==" %%a in ("config_output.tmp") do (
    if "%%a"=="PROJECT_ID" (
        set "PROJECT_ID=%%b"
    ) else if "%%a"=="REGION" (
        set "REGION=%%b"
    )
)

REM Clean up temporary files
del read_config.py
del config_output.tmp

echo Using project ID: %PROJECT_ID%
echo Using region: %REGION%

REM Check if Terraform is installed
echo Checking for Terraform installation...
where terraform > nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo Terraform is not installed or not in PATH.
    echo.

    if "%NON_INTERACTIVE%"=="1" (
        echo Running in non-interactive mode, installing Terraform automatically...
        
        REM Download and install Terraform directly
        echo Downloading Terraform...
        powershell -Command "Invoke-WebRequest -Uri 'https://releases.hashicorp.com/terraform/1.7.4/terraform_1.7.4_windows_amd64.zip' -OutFile 'terraform.zip' -UseBasicParsing"
        if !ERRORLEVEL! NEQ 0 (
            echo Error: Failed to download Terraform.
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        )

        echo Cleaning up any existing Terraform files...
        REM Only remove existing terraform binary/directory, not the zip
        if exist "terraform" rmdir /S /Q terraform
        if exist "terraform.exe" del /F /Q terraform.exe
        for /f %%i in ('dir /b terraform_*.exe 2^>nul') do del /F /Q "%%i"

        echo Unzipping Terraform...
        powershell -Command "$ProgressPreference = 'SilentlyContinue'; Expand-Archive -Path terraform.zip -DestinationPath . -Force"
        if !ERRORLEVEL! NEQ 0 (
            echo Error: Failed to unzip Terraform.
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        )

        echo Installing Terraform...
        if exist "C:\Windows\System32" (
            move /Y terraform.exe C:\Windows\System32\ > nul 2>&1
            if !ERRORLEVEL! NEQ 0 (
                echo Error: Failed to install Terraform to System32. Trying current directory...
                set "PATH=%PATH%;%CD%"
            ) else (
                echo Terraform installed successfully to System32.
            )
        ) else (
            echo System32 not accessible. Using current directory...
            set "PATH=%PATH%;%CD%"
        )
        
        del /F /Q terraform.zip
        set "USE_TERRAFORM=1"
        
        REM Verify Terraform is now available
        where terraform > nul 2>&1
        if !ERRORLEVEL! NEQ 0 (
            echo Error: Terraform installation succeeded but command not found.
            echo Please ensure Terraform is in your PATH.
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        )
        
        terraform --version
    ) else (
        echo Options:
        echo [1] Automatic installation ^(will install Chocolatey if needed^)
        echo [2] Skip Terraform and continue with deployment
        echo [3] Exit and install Terraform manually
        echo.
        choice /C 123 /N /M "Enter your choice (1-3): "
        set TERRAFORM_CHOICE=!ERRORLEVEL!
        
        if "!TERRAFORM_CHOICE!"=="1" (
            REM Check if Chocolatey is installed
            where choco > nul 2>&1
            if !ERRORLEVEL! NEQ 0 (
                echo Chocolatey not found. Installing Chocolatey...
                echo This will require administrator privileges.
                echo.
                powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
                if !ERRORLEVEL! NEQ 0 (
                    echo Error: Failed to install Chocolatey.
                    echo Please run this script as administrator or install Terraform manually.
                    exit /b 1
                )
                echo Chocolatey installed successfully.
                
                REM Refresh environment variables
                echo Refreshing environment variables...
                call refreshenv
                
                REM Verify Chocolatey is now available
                where choco > nul 2>&1
                if !ERRORLEVEL! NEQ 0 (
                    echo Error: Chocolatey installation succeeded but command not found.
                    echo Please close this window and run the script again as administrator.
                    exit /b 1
                )
            )
            
            echo Installing Terraform using Chocolatey...
            choco install terraform -y
            if !ERRORLEVEL! NEQ 0 (
                echo Error: Failed to install Terraform using Chocolatey.
                echo Please try running the script as administrator.
                set "USE_TERRAFORM=0"
                goto :skip_terraform
            )
            echo Terraform installed successfully.
            
            REM Refresh environment variables
            echo Refreshing environment variables...
            call refreshenv
            
            REM Update PATH for current session
            for /f "tokens=*" %%i in ('where terraform') do set "TERRAFORM_PATH=%%i"
            if not "!TERRAFORM_PATH!"=="" (
                set "PATH=%PATH%;%TERRAFORM_PATH%"
                echo Added Terraform to current session PATH
            )
            
            REM Verify Terraform is now available
            where terraform > nul 2>&1
            if !ERRORLEVEL! NEQ 0 (
                echo Error: Terraform installation succeeded but command not found.
                echo Please close this window and run the script again.
                exit /b 1
            )
            
            terraform --version
            set "USE_TERRAFORM=1"
        ) else if "!TERRAFORM_CHOICE!"=="2" (
            echo Skipping Terraform installation and continuing with deployment...
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        ) else if "!TERRAFORM_CHOICE!"=="3" (
            echo Please install Terraform manually:
            echo 1. Download from: https://www.terraform.io/downloads.html
            echo 2. Add to your system PATH
            echo 3. Run setup.bat again
            exit /b 1
        )
    )
) else (
    set "USE_TERRAFORM=1"
)

:skip_terraform

REM Check GCP authentication (only if not in Cloud Build)
if not defined CLOUD_BUILD (
    echo [DEBUG] Starting GCP authentication check...
    echo.
    echo Step 1: Checking user authentication...
    echo [DEBUG] Getting active account...

    REM Get active account directly
    for /f "tokens=*" %%a in ('gcloud auth list --format="value(account)" --filter="status=ACTIVE" 2^>nul') do set "ACTIVE_ACCOUNT=%%a"
    if defined ACTIVE_ACCOUNT (
        echo [DEBUG] Found active account: %ACTIVE_ACCOUNT%
    ) else (
        echo [DEBUG] No active account found
        set "ACTIVE_ACCOUNT="
    )

    if "%ACTIVE_ACCOUNT%"=="" (
        echo No active account found.
        echo.
        echo NOTE: The next step will open a browser window for authentication.
        echo After authenticating, return to this window to continue.
        echo.
        echo Press any key to continue...
        pause >nul
        
        echo [DEBUG] Starting user login...
        call gcloud auth login --no-launch-browser
        
        REM Verify the login was successful
        for /f "tokens=*" %%a in ('gcloud auth list --format="get(account)" --filter="status=ACTIVE" 2^>nul') do (
            set "ACTIVE_ACCOUNT=%%a"
            echo [DEBUG] Successfully authenticated as: %%a
        )
        
        if "%ACTIVE_ACCOUNT%"=="" (
            echo Error: Failed to authenticate with GCP.
            exit /b 1
        )
        
        REM Set project and region
        echo [DEBUG] Setting project and region...
        call gcloud config set project %PROJECT_ID%
        if !ERRORLEVEL! NEQ 0 (
            echo Error: Failed to set project.
            exit /b 1
        )
        call gcloud config set compute/region %REGION%
        if !ERRORLEVEL! NEQ 0 (
            echo Error: Failed to set region.
            exit /b 1
        )
        echo [DEBUG] Project and region configured successfully.
    ) else (
        echo [DEBUG] Using existing authentication for account: %ACTIVE_ACCOUNT%
        
        REM Verify project and region are set correctly
        echo [DEBUG] Verifying project and region configuration...
        
        for /f "tokens=*" %%a in ('gcloud config get-value project 2^>nul') do set CURRENT_PROJECT=%%a
        for /f "tokens=*" %%a in ('gcloud config get-value compute/region 2^>nul') do set CURRENT_REGION=%%a
        
        if not "%CURRENT_PROJECT%"=="%PROJECT_ID%" (
            echo [DEBUG] Setting project to %PROJECT_ID%...
            call gcloud config set project %PROJECT_ID%
            if !ERRORLEVEL! NEQ 0 (
                echo Error: Failed to set project.
                exit /b 1
            )
        )
        
        if not "%CURRENT_REGION%"=="%REGION%" (
            echo [DEBUG] Setting region to %REGION%...
            call gcloud config set compute/region %REGION%
            if !ERRORLEVEL! NEQ 0 (
                echo Error: Failed to set region.
                exit /b 1
            )
        )
    )
) else (
    echo Skipping GCP auth check in Cloud Build environment
)

REM Check application default credentials (only if not in Cloud Build)
if not defined CLOUD_BUILD (
    echo [DEBUG] Starting application default credentials check...
    echo Step 2: Checking application default credentials...
    echo Testing access token retrieval...
    call gcloud auth application-default print-access-token >nul 2>&1
    set ADC_STATUS=!ERRORLEVEL!
    echo [DEBUG] ADC check complete with status: !ADC_STATUS!

    if !ADC_STATUS! NEQ 0 (
        echo [DEBUG] No ADC found, entering setup...
        echo No application default credentials found ^(required for Terraform^).
        echo.
        echo NOTE: The next step will open a browser window for authentication.
        echo After authenticating, return to this window to continue.
        echo.
        echo Press any key to continue...
        pause >nul
        
        echo [DEBUG] Starting ADC login...
        call gcloud auth application-default login --no-launch-browser
        set ADC_RESULT=!ERRORLEVEL!
        echo [DEBUG] ADC login complete with status: !ADC_RESULT!
        
        if !ADC_RESULT! NEQ 0 (
            echo.
            echo Error: Failed to set up application default credentials.
            exit /b 1
        ) else (
            echo.
            echo Successfully configured application default credentials.
        )
    ) else (
        echo [DEBUG] ADC already configured
        echo ✓ Application default credentials are already configured.
        echo ✓ User is authenticated as: %ACTIVE_ACCOUNT%
    )
) else (
    echo Using Cloud Build service account credentials for Terraform
    REM In Cloud Build, credentials are automatically available to Terraform
    set "GOOGLE_APPLICATION_CREDENTIALS=/workspace/service-account.json"
)

echo [DEBUG] Authentication check complete
echo.
echo Current GCP configuration:
echo ------------------------
echo Project: 
call gcloud config get-value project
echo Account:
call gcloud config get-value account
echo Region:
call gcloud config get-value compute/region
echo ------------------------
echo.

REM Now use Terraform to manage infrastructure
echo Initializing Terraform...

REM Handle GOOGLE_APPLICATION_CREDENTIALS path
if defined GOOGLE_APPLICATION_CREDENTIALS (
    echo [DEBUG] Found GOOGLE_APPLICATION_CREDENTIALS set to: %GOOGLE_APPLICATION_CREDENTIALS%
    REM Convert relative path to absolute path using full path
    set "CREDENTIALS_PATH=%CURRENT_DIR%\%GOOGLE_APPLICATION_CREDENTIALS%"
    echo [DEBUG] Using absolute path for credentials: !CREDENTIALS_PATH!
    if exist "!CREDENTIALS_PATH!" (
        echo [DEBUG] Service account key file found
        set "GOOGLE_APPLICATION_CREDENTIALS=!CREDENTIALS_PATH!"
    ) else (
        echo [DEBUG] Service account key file not found at: !CREDENTIALS_PATH!
        echo [DEBUG] Falling back to application default credentials
        set "GOOGLE_APPLICATION_CREDENTIALS="
    )
)

cd terraform

REM Initialize Terraform first
terraform init
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to initialize Terraform.
    exit /b 1
)

echo.
echo Showing planned changes...
terraform plan
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to plan Terraform changes.
    exit /b 1
)

REM Modify the Terraform apply section to use non-interactive mode
if "%NON_INTERACTIVE%"=="1" (
    echo Running in non-interactive mode, applying Terraform changes automatically...
    terraform apply -auto-approve
) else (
    echo.
    echo Would you like to apply these changes?
    echo [1] Yes, apply the changes
    echo [2] No, skip Terraform changes
    echo.
    choice /C 12 /N /M "Enter your choice (1-2): "
    set APPLY_CHOICE=!ERRORLEVEL!

    if "!APPLY_CHOICE!"=="1" (
        echo Applying Terraform changes...
        terraform apply -auto-approve
    ) else (
        echo Skipping Terraform changes.
    )
)

cd ..

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

REM Check if we should deploy infrastructure with Terraform
if "%USE_TERRAFORM%"=="1" (
    echo Step 1: Applying Terraform configuration...
    cd terraform
    terraform init
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to initialize Terraform
        exit /b 1
    )
    terraform apply
    if %ERRORLEVEL% NEQ 0 (
        echo Error: Failed to apply Terraform configuration
        exit /b 1
    )
    cd ..
    echo Terraform resources deployed successfully
    echo.
)

REM Deploy storage buckets (will respect Terraform state)
echo Step 2: Deploying storage buckets...
python scripts/deploy_storage.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy storage buckets
    exit /b 1
)

REM Set up service accounts
echo Step 3: Setting up service accounts...
python scripts/setup_service_accounts.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to set up service accounts
    exit /b 1
)

REM Deploy credentials (will respect Terraform state)
echo Step 4: Deploying credentials...
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

REM Deploy Cloud Function and Scheduler (will respect Terraform state)
echo Step 5: Deploying Cloud Function and Scheduler...
python scripts/deploy_functions.py
if %ERRORLEVEL% NEQ 0 (
    echo Error: Failed to deploy Cloud Function and Scheduler
    exit /b 1
)

REM Run post-deployment integration tests if enabled
if "%RUN_TESTS%"=="1" (
    echo.
    echo Step 6: Running post-deployment test...
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
