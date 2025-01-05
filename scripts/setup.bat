@echo off
setlocal EnableDelayedExpansion
echo [DEBUG] Starting script...

REM Check if running in Cloud Build
echo [DEBUG] Checking if running in Cloud Build...
if defined CLOUD_BUILD (
    echo [DEBUG] Running in Cloud Build environment
    set "NON_INTERACTIVE=1"
    echo [DEBUG] Set NON_INTERACTIVE=1
    echo Using Cloud Build service account authentication
    REM Skip GCP auth check in Cloud Build as it uses service account
    echo Using service account credentials for Terraform
    set "USE_GCP_AUTH=0"
    echo [DEBUG] Set USE_GCP_AUTH=0
) else (
    echo [DEBUG] Running in local environment
    set "NON_INTERACTIVE=0"
    echo [DEBUG] Set NON_INTERACTIVE=0
    set "USE_GCP_AUTH=1"
    echo [DEBUG] Set USE_GCP_AUTH=1
)

REM Get the current directory
echo [DEBUG] Getting current directory...
set "CURRENT_DIR=%CD%"
echo [DEBUG] Current directory is: %CURRENT_DIR%

REM Set PYTHONPATH to include current directory
echo [DEBUG] Setting PYTHONPATH...
set "PYTHONPATH=%CURRENT_DIR%;%PYTHONPATH%"
echo [DEBUG] PYTHONPATH is now: %PYTHONPATH%

REM Install pyyaml if needed
echo [DEBUG] Installing pyyaml...
pip install pyyaml --quiet
echo [DEBUG] pyyaml installation complete

REM Create a temporary Python script to read config
echo [DEBUG] Creating Python script to read config...
echo import yaml > read_config.py
echo with open('config.yaml', 'r') as f: >> read_config.py
echo     config = yaml.safe_load(f) >> read_config.py
echo print('PROJECT_ID=' + str(config['project']['id']).strip()) >> read_config.py
echo print('REGION=' + str(config['project']['region']).strip()) >> read_config.py
echo [DEBUG] Created read_config.py

REM Get project ID and region from config.yaml
echo [DEBUG] Reading project configuration...
python read_config.py > config_output.tmp
echo [DEBUG] Python script executed
for /f "usebackq tokens=1,* delims==" %%a in ("config_output.tmp") do (
    if "%%a"=="PROJECT_ID" (
        set "PROJECT_ID=%%b"
        echo [DEBUG] Set PROJECT_ID to: %%b
    ) else if "%%a"=="REGION" (
        set "REGION=%%b"
        echo [DEBUG] Set REGION to: %%b
    )
)

REM Clean up temporary files
echo [DEBUG] Cleaning up temporary files...
del read_config.py
del config_output.tmp
echo [DEBUG] Temporary files cleaned up

echo [DEBUG] Using project ID: %PROJECT_ID%
echo [DEBUG] Using region: %REGION%

REM Check if Terraform is installed
echo [DEBUG] Checking for Terraform installation...
where terraform > nul 2>&1
set "TERRAFORM_CHECK=!ERRORLEVEL!"
echo [DEBUG] Terraform check result: !TERRAFORM_CHECK!

if !TERRAFORM_CHECK! NEQ 0 (
    echo [DEBUG] Terraform is not installed or not in PATH
    echo Terraform is not installed or not in PATH.
    echo.

    if "!NON_INTERACTIVE!"=="1" (
        echo [DEBUG] Running in non-interactive mode, installing Terraform automatically...
        REM Download and install Terraform directly
        echo [DEBUG] Starting Terraform download...
        powershell -Command "Invoke-WebRequest -Uri 'https://releases.hashicorp.com/terraform/1.7.4/terraform_1.7.4_windows_amd64.zip' -OutFile 'terraform.zip' -UseBasicParsing"
        set "DOWNLOAD_STATUS=!ERRORLEVEL!"
        echo [DEBUG] Download status: !DOWNLOAD_STATUS!
        if !DOWNLOAD_STATUS! NEQ 0 (
            echo [DEBUG] Failed to download Terraform
            echo Error: Failed to download Terraform.
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        )

        echo [DEBUG] Cleaning up existing Terraform files...
        if exist "terraform" rmdir /S /Q terraform
        if exist "terraform.exe" del /F /Q terraform.exe
        for /f "tokens=*" %%i in ('dir /b terraform_*.exe 2^>nul') do del /F /Q "%%i"
        echo [DEBUG] Cleanup complete

        echo [DEBUG] Unzipping Terraform...
        powershell -Command "$ProgressPreference = 'SilentlyContinue'; Expand-Archive -Path terraform.zip -DestinationPath . -Force"
        set "UNZIP_STATUS=!ERRORLEVEL!"
        echo [DEBUG] Unzip status: !UNZIP_STATUS!
        if !UNZIP_STATUS! NEQ 0 (
            echo [DEBUG] Failed to unzip Terraform
            echo Error: Failed to unzip Terraform.
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        )

        echo [DEBUG] Installing Terraform...
        if exist "C:\Windows\System32" (
            echo [DEBUG] Attempting to move Terraform to System32...
            move /Y terraform.exe C:\Windows\System32\ > nul 2>&1
            set "MOVE_STATUS=!ERRORLEVEL!"
            echo [DEBUG] Move status: !MOVE_STATUS!
            if !MOVE_STATUS! NEQ 0 (
                echo [DEBUG] Failed to install to System32, using current directory
                echo Error: Failed to install Terraform to System32. Trying current directory...
                set "PATH=!PATH!;!CD!"
                echo [DEBUG] Updated PATH with current directory
            ) else (
                echo [DEBUG] Successfully installed to System32
                echo Terraform installed successfully to System32.
            )
        ) else (
            echo [DEBUG] System32 not accessible, using current directory
            echo System32 not accessible. Using current directory...
            set "PATH=!PATH!;!CD!"
            echo [DEBUG] Updated PATH with current directory
        )
        
        echo [DEBUG] Cleaning up zip file...
        del /F /Q terraform.zip
        set "USE_TERRAFORM=1"
        echo [DEBUG] Set USE_TERRAFORM=1
        
        REM Verify Terraform is now available
        echo [DEBUG] Verifying Terraform installation...
        where terraform > nul 2>&1
        set "VERIFY_STATUS=!ERRORLEVEL!"
        echo [DEBUG] Verify status: !VERIFY_STATUS!
        if !VERIFY_STATUS! NEQ 0 (
            echo [DEBUG] Terraform command not found after installation
            echo Error: Terraform installation succeeded but command not found.
            echo Please ensure Terraform is in your PATH.
            set "USE_TERRAFORM=0"
            goto :skip_terraform
        )
        
        echo [DEBUG] Running terraform version check...
        terraform --version
    ) else (
        echo [DEBUG] Interactive mode - showing options
        echo Options:
        echo [1] Automatic installation ^(will install Chocolatey if needed^)
        echo [2] Skip Terraform and continue with deployment
        echo [3] Exit and install Terraform manually
        echo.
        choice /C 123 /N /M "Enter your choice (1-3): "
        set "TERRAFORM_CHOICE=!ERRORLEVEL!"
        echo [DEBUG] User choice: !TERRAFORM_CHOICE!
        
        if "!TERRAFORM_CHOICE!"=="1" (
            REM Check if Chocolatey is installed
            echo [DEBUG] Checking for Chocolatey installation...
            where choco > nul 2>&1
            set "CHOCO_CHECK=!ERRORLEVEL!"
            echo [DEBUG] Chocolatey check result: !CHOCO_CHECK!
            if !CHOCO_CHECK! NEQ 0 (
                echo [DEBUG] Chocolatey not found, starting installation...
                echo Chocolatey not found. Installing Chocolatey...
                echo This will require administrator privileges.
                echo.
                powershell -Command "Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))"
                set "CHOCO_INSTALL=!ERRORLEVEL!"
                echo [DEBUG] Chocolatey installation status: !CHOCO_INSTALL!
                if !CHOCO_INSTALL! NEQ 0 (
                    echo [DEBUG] Failed to install Chocolatey
                    echo Error: Failed to install Chocolatey.
                    echo Please run this script as administrator or install Terraform manually.
                    exit /b 1
                )
                echo [DEBUG] Chocolatey installed successfully
                echo Chocolatey installed successfully.
                
                REM Refresh environment variables
                echo [DEBUG] Refreshing environment variables...
                call refreshenv
                
                REM Verify Chocolatey is now available
                echo [DEBUG] Verifying Chocolatey installation...
                where choco > nul 2>&1
                set "CHOCO_VERIFY=!ERRORLEVEL!"
                echo [DEBUG] Chocolatey verify status: !CHOCO_VERIFY!
                if !CHOCO_VERIFY! NEQ 0 (
                    echo [DEBUG] Chocolatey command not found after installation
                    echo Error: Chocolatey installation succeeded but command not found.
                    echo Please close this window and run the script again as administrator.
                    exit /b 1
                )
            )
            
            echo [DEBUG] Installing Terraform using Chocolatey...
            choco install terraform -y
            set "TERRAFORM_INSTALL=!ERRORLEVEL!"
            echo [DEBUG] Terraform installation status: !TERRAFORM_INSTALL!
            if !TERRAFORM_INSTALL! NEQ 0 (
                echo [DEBUG] Failed to install Terraform using Chocolatey
                echo Error: Failed to install Terraform using Chocolatey.
                echo Please try running the script as administrator.
                set "USE_TERRAFORM=0"
                goto :skip_terraform
            )
            echo [DEBUG] Terraform installed successfully
            echo Terraform installed successfully.
            
            REM Refresh environment variables
            echo [DEBUG] Refreshing environment variables...
            call refreshenv
            
            REM Update PATH for current session
            echo [DEBUG] Updating PATH for current session...
            for /f "tokens=*" %%i in ('where terraform') do set "TERRAFORM_PATH=%%i"
            echo [DEBUG] Found Terraform at: !TERRAFORM_PATH!
            if not "!TERRAFORM_PATH!"=="" (
                set "PATH=!PATH!;!TERRAFORM_PATH!"
                echo [DEBUG] Added Terraform to current session PATH
                echo Added Terraform to current session PATH
            )
            
            REM Verify Terraform is now available
            echo [DEBUG] Verifying Terraform installation...
            where terraform > nul 2>&1
            set "TERRAFORM_VERIFY=!ERRORLEVEL!"
            echo [DEBUG] Terraform verify status: !TERRAFORM_VERIFY!
            if !TERRAFORM_VERIFY! NEQ 0 (
                echo [DEBUG] Terraform command not found after installation
                echo Error: Terraform installation succeeded but command not found.
                echo Please close this window and run the script again.
                exit /b 1
            )
            
            echo [DEBUG] Running terraform version check...
            terraform --version
            set "USE_TERRAFORM=1"
            echo [DEBUG] Set USE_TERRAFORM=1
        ) else if "!TERRAFORM_CHOICE!"=="2" (
            echo [DEBUG] User chose to skip Terraform installation
            echo Skipping Terraform installation and continuing with deployment...
            set "USE_TERRAFORM=0"
            echo [DEBUG] Set USE_TERRAFORM=0
            goto :skip_terraform
        ) else if "!TERRAFORM_CHOICE!"=="3" (
            echo [DEBUG] User chose to exit and install manually
            echo Please install Terraform manually:
            echo 1. Download from: https://www.terraform.io/downloads.html
            echo 2. Add to your system PATH
            echo 3. Run setup.bat again
            exit /b 1
        )
    )
) else (
    echo [DEBUG] Terraform is already installed
    set "USE_TERRAFORM=1"
    echo [DEBUG] Set USE_TERRAFORM=1
)

:skip_terraform
echo [DEBUG] Reached skip_terraform label

REM Check GCP authentication (only if not in Cloud Build)
if not defined CLOUD_BUILD (
    echo [DEBUG] Starting GCP authentication check (local environment^)...
    echo.
    echo Step 1: Checking service account credentials...
    
    REM Read service account key path from config
    echo [DEBUG] Creating Python script to read service account key path...
    echo import yaml > read_sa_config.py
    echo with open^('config.yaml', 'r'^) as f: >> read_sa_config.py
    echo     config = yaml.safe_load^(f^) >> read_sa_config.py
    echo print^('SA_KEY_PATH=' + str^(config['gcp']['service_account_key_path']^).strip^(^)^) >> read_sa_config.py
    echo [DEBUG] Created read_sa_config.py
    
    echo [DEBUG] Executing Python script to read service account key path...
    python read_sa_config.py > sa_config_output.tmp
    echo [DEBUG] Python script executed
    for /f "usebackq tokens=1,* delims==" %%a in ("sa_config_output.tmp") do (
        if "%%a"=="SA_KEY_PATH" (
            set "SA_KEY_PATH=%%b"
            echo [DEBUG] Set SA_KEY_PATH to: %%b
        )
    )
    
    REM Clean up temporary files
    echo [DEBUG] Cleaning up temporary files...
    del read_sa_config.py
    del sa_config_output.tmp
    echo [DEBUG] Temporary files cleaned up
    
    echo [DEBUG] Using service account key from: !SA_KEY_PATH!
    
    REM Activate service account
    echo [DEBUG] Attempting to activate service account...
    call gcloud auth activate-service-account --key-file=!SA_KEY_PATH!
    set "SA_AUTH_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Service account activation status: !SA_AUTH_STATUS!
    if !SA_AUTH_STATUS! NEQ 0 (
        echo [DEBUG] Failed to authenticate with service account
        echo Error: Failed to authenticate with service account.
        exit /b 1
    )
    
    REM Set project and region
    echo [DEBUG] Setting GCP project...
    call gcloud config set project !PROJECT_ID!
    set "PROJECT_SET_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Project set status: !PROJECT_SET_STATUS!
    if !PROJECT_SET_STATUS! NEQ 0 (
        echo [DEBUG] Failed to set project
        echo Error: Failed to set project.
        exit /b 1
    )

    echo [DEBUG] Setting GCP region...
    call gcloud config set compute/region !REGION!
    set "REGION_SET_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Region set status: !REGION_SET_STATUS!
    if !REGION_SET_STATUS! NEQ 0 (
        echo [DEBUG] Failed to set region
        echo Error: Failed to set region.
        exit /b 1
    )
    
    echo [DEBUG] Successfully authenticated using service account
) else (
    echo [DEBUG] Skipping GCP auth check (Cloud Build environment^)
)

REM Check application default credentials (only if not in Cloud Build)
if not defined CLOUD_BUILD (
    echo [DEBUG] Starting application default credentials check...
    echo Step 2: Checking application default credentials...
    echo [DEBUG] Testing access token retrieval...
    call gcloud auth application-default print-access-token >nul 2>&1
    set "ADC_STATUS=!ERRORLEVEL!"
    echo [DEBUG] ADC check status: !ADC_STATUS!

    if !ADC_STATUS! NEQ 0 (
        echo [DEBUG] No ADC found, starting setup...
        echo No application default credentials found ^(required for Terraform^).
        echo.
        echo NOTE: The next step will open a browser window for authentication.
        echo After authenticating, return to this window to continue.
        echo.
        echo Press any key to continue...
        pause >nul
        
        echo [DEBUG] Starting ADC login...
        call gcloud auth application-default login --no-launch-browser
        set "ADC_RESULT=!ERRORLEVEL!"
        echo [DEBUG] ADC login status: !ADC_RESULT!
        
        if !ADC_RESULT! NEQ 0 (
            echo [DEBUG] Failed to set up ADC
            echo.
            echo Error: Failed to set up application default credentials.
            exit /b 1
        ) else (
            echo [DEBUG] Successfully configured ADC
            echo.
            echo Successfully configured application default credentials.
        )
    ) else (
        echo [DEBUG] ADC already configured
        echo ✓ Application default credentials are already configured.
        echo ✓ User is authenticated as: !ACTIVE_ACCOUNT!
    )
) else (
    echo [DEBUG] Using Cloud Build service account credentials for Terraform
    REM In Cloud Build, credentials are automatically available to Terraform
    set "GOOGLE_APPLICATION_CREDENTIALS=/workspace/service-account.json"
    echo [DEBUG] Set GOOGLE_APPLICATION_CREDENTIALS to: !GOOGLE_APPLICATION_CREDENTIALS!
)

echo [DEBUG] Authentication check complete
echo.
echo [DEBUG] Displaying current GCP configuration...
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
echo [DEBUG] Starting Terraform initialization...

REM Handle GOOGLE_APPLICATION_CREDENTIALS path
if defined GOOGLE_APPLICATION_CREDENTIALS (
    echo [DEBUG] Found GOOGLE_APPLICATION_CREDENTIALS: %GOOGLE_APPLICATION_CREDENTIALS%
    REM Convert relative path to absolute path using full path
    set "CREDENTIALS_PATH=%CURRENT_DIR%\%GOOGLE_APPLICATION_CREDENTIALS%"
    echo [DEBUG] Converted to absolute path: !CREDENTIALS_PATH!
    if exist "!CREDENTIALS_PATH!" (
        echo [DEBUG] Service account key file found
        set "GOOGLE_APPLICATION_CREDENTIALS=!CREDENTIALS_PATH!"
        echo [DEBUG] Updated GOOGLE_APPLICATION_CREDENTIALS to: !CREDENTIALS_PATH!
    ) else (
        echo [DEBUG] Service account key file not found at: !CREDENTIALS_PATH!
        echo [DEBUG] Falling back to application default credentials
        set "GOOGLE_APPLICATION_CREDENTIALS="
        echo [DEBUG] Cleared GOOGLE_APPLICATION_CREDENTIALS
    )
)

echo [DEBUG] Changing directory to terraform...
cd terraform
echo [DEBUG] Current directory is now: %CD%

REM Initialize Terraform first
echo [DEBUG] Running terraform init...
terraform init
set "INIT_STATUS=!ERRORLEVEL!"
echo [DEBUG] Terraform init status: !INIT_STATUS!
if !INIT_STATUS! NEQ 0 (
    echo [DEBUG] Failed to initialize Terraform
    echo Error: Failed to initialize Terraform.
    exit /b 1
)

echo.
echo [DEBUG] Running terraform plan...
terraform plan
set "PLAN_STATUS=!ERRORLEVEL!"
echo [DEBUG] Terraform plan status: !PLAN_STATUS!
if !PLAN_STATUS! NEQ 0 (
    echo [DEBUG] Failed to plan Terraform changes
    echo Error: Failed to plan Terraform changes.
    exit /b 1
)

REM Modify the Terraform apply section to use non-interactive mode
if "%NON_INTERACTIVE%"=="1" (
    echo [DEBUG] Running in non-interactive mode, applying changes automatically...
    terraform apply -auto-approve
    set "APPLY_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Terraform apply status: !APPLY_STATUS!
) else (
    echo.
    echo Would you like to apply these changes?
    echo [1] Yes, apply the changes
    echo [2] No, skip Terraform changes
    echo.
    choice /C 12 /N /M "Enter your choice (1-2): "
    set "APPLY_CHOICE=!ERRORLEVEL!"
    echo [DEBUG] User apply choice: !APPLY_CHOICE!

    if "!APPLY_CHOICE!"=="1" (
        echo [DEBUG] User chose to apply changes
        echo Applying Terraform changes...
        terraform apply -auto-approve
        set "APPLY_STATUS=!ERRORLEVEL!"
        echo [DEBUG] Terraform apply status: !APPLY_STATUS!
    ) else (
        echo [DEBUG] User chose to skip changes
        echo Skipping Terraform changes.
    )
)

echo [DEBUG] Changing directory back to root...
cd ..
echo [DEBUG] Current directory is now: %CD%

REM Check if virtual environment exists
echo [DEBUG] Checking for virtual environment...
if exist venv (
    echo [DEBUG] Found existing virtual environment
    echo Found existing virtual environment
) else (
    echo [DEBUG] Creating new virtual environment...
    echo Creating virtual environment...
    python -m venv venv
    set "VENV_CREATE_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Virtual environment creation status: !VENV_CREATE_STATUS!
)

REM Activate virtual environment
echo [DEBUG] Activating virtual environment...
call venv\Scripts\activate.bat
set "VENV_ACTIVATE_STATUS=!ERRORLEVEL!"
echo [DEBUG] Virtual environment activation status: !VENV_ACTIVATE_STATUS!

REM Set test environment variable
echo [DEBUG] Setting test environment variable...
set TEST_ENV=true
echo [DEBUG] Set TEST_ENV=true

REM Install requirements if needed
echo [DEBUG] Installing requirements...
pip install -r requirements.txt > nul 2>&1
set "PIP_INSTALL_STATUS=!ERRORLEVEL!"
echo [DEBUG] Requirements installation status: !PIP_INSTALL_STATUS!

REM Run tests and deployment
echo [DEBUG] Starting test configuration check...
echo Checking test configuration...
echo === Running Pre-deployment Tests ===

REM Run unit tests first
echo.
echo [DEBUG] Starting unit tests...
echo Step 1: Running unit_tests tests...

REM Upgrade pip silently
echo [DEBUG] Upgrading pip...
python -m pip install --upgrade pip --quiet
set "PIP_UPGRADE_STATUS=!ERRORLEVEL!"
echo [DEBUG] Pip upgrade status: !PIP_UPGRADE_STATUS!

REM Install requirements
echo [DEBUG] Installing requirements...
python -m pip install -r requirements.txt --quiet --no-warn-script-location
set "REQ_INSTALL_STATUS=!ERRORLEVEL!"
echo [DEBUG] Requirements installation status: !REQ_INSTALL_STATUS!
if !REQ_INSTALL_STATUS! NEQ 0 (
    echo [DEBUG] Failed to install requirements quietly, retrying with output...
    echo Error: Failed to install requirements
    python -m pip install -r requirements.txt
    exit /b 1
)

REM Run pre-deployment tests if enabled in config
echo.
echo [DEBUG] Reading test configuration...
echo Checking test configuration...

REM Create Python script content in a variable
echo [DEBUG] Creating test configuration script...
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
echo [DEBUG] Writing test configuration script to file...
echo !PYTHON_SCRIPT! > temp_config.py

REM Execute the temporary script and capture output
echo [DEBUG] Executing test configuration script...
for /f "usebackq tokens=1,* delims==" %%a in (`python temp_config.py`) do (
    set "%%a=%%b"
    echo [DEBUG] Set %%a=%%b
)
echo [DEBUG] Cleaning up temporary script...
del temp_config.py

if "%RUN_TESTS%"=="1" (
    echo [DEBUG] Tests are enabled
    echo === Running Pre-deployment Tests ===
    echo.
    
    set STEP=1
    
    REM Execute tests in order
    echo [DEBUG] Starting test execution in order: %TEST_ORDER%
    for %%t in (%TEST_ORDER:,= %) do (
        set "TEST_TYPE=%%t"
        set "ENABLED=!%%t_ENABLED!"
        set "PATHS=!%%t_PATHS!"
        echo [DEBUG] Processing test type: !TEST_TYPE!, Enabled: !ENABLED!, Paths: !PATHS!
        
        if "!ENABLED!"=="1" (
            echo.
            echo Step !STEP!: Running !TEST_TYPE! tests...
            
            if "!TEST_TYPE!"=="unit_tests" (
                if "%RUN_ALL%"=="1" (
                    echo [DEBUG] Running all unit tests...
                    python -m pytest tests -v
                    set "TEST_STATUS=!ERRORLEVEL!"
                    echo [DEBUG] Unit tests status: !TEST_STATUS!
                ) else (
                    for %%f in (!PATHS!) do (
                        echo [DEBUG] Running tests in: %%f
                        python -m pytest %%f -v
                        set "TEST_STATUS=!ERRORLEVEL!"
                        echo [DEBUG] Test status for %%f: !TEST_STATUS!
                        if !TEST_STATUS! NEQ 0 (
                            echo [DEBUG] Unit tests failed in %%f
                            echo Error: Unit tests failed in %%f
                            exit /b 1
                        )
                    )
                )
            ) else if "!TEST_TYPE!"=="package_tests" (
                for %%f in (!PATHS!) do (
                    echo [DEBUG] Running package test: %%f
                    python %%f
                    set "TEST_STATUS=!ERRORLEVEL!"
                    echo [DEBUG] Package test status for %%f: !TEST_STATUS!
                    if !TEST_STATUS! NEQ 0 (
                        echo [DEBUG] Package tests failed
                        echo Error: Package tests failed
                        exit /b 1
                    )
                )
            ) else if "!TEST_TYPE!"=="config_tests" (
                for %%f in (!PATHS!) do (
                    echo [DEBUG] Running config test: %%f
                    python %%f
                    set "TEST_STATUS=!ERRORLEVEL!"
                    echo [DEBUG] Config test status for %%f: !TEST_STATUS!
                    if !TEST_STATUS! NEQ 0 (
                        echo [DEBUG] Configuration tests failed
                        echo Error: Configuration tests failed
                        exit /b 1
                    )
                )
            ) else if "!TEST_TYPE!"=="integration_tests" (
                REM Integration tests are run after deployment
                echo [DEBUG] Integration tests will run after deployment
                echo Integration tests will run after deployment
            )
        ) else (
            echo [DEBUG] Skipping !TEST_TYPE! (disabled in config)
            echo Skipping !TEST_TYPE! ^(disabled in config^)
        )
        
        set /a STEP+=1
        echo [DEBUG] Incremented step counter to !STEP!
    )
    
    echo.
    echo [DEBUG] All pre-deployment tests passed
    echo === All Pre-deployment Tests Passed ===
    echo.
) else (
    echo [DEBUG] Tests are disabled in config.yaml
    echo Skipping tests (disabled in config.yaml)
    echo.
)

echo [DEBUG] Starting deployment phase...
echo === Starting Deployment ===
echo.

REM Check if we should deploy infrastructure with Terraform
if "%USE_TERRAFORM%"=="1" (
    echo [DEBUG] Terraform deployment is enabled
    echo Step 1: Applying Terraform configuration...
    cd terraform
    echo [DEBUG] Changed directory to terraform: %CD%
    terraform init
    set "INIT_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Terraform init status: !INIT_STATUS!
    if !INIT_STATUS! NEQ 0 (
        echo [DEBUG] Failed to initialize Terraform
        echo Error: Failed to initialize Terraform
        exit /b 1
    )
    terraform apply
    set "APPLY_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Terraform apply status: !APPLY_STATUS!
    if !APPLY_STATUS! NEQ 0 (
        echo [DEBUG] Failed to apply Terraform configuration
        echo Error: Failed to apply Terraform configuration
        exit /b 1
    )
    cd ..
    echo [DEBUG] Changed directory back to root: %CD%
    echo [DEBUG] Terraform resources deployed successfully
    echo Terraform resources deployed successfully
    echo.
)

REM Deploy storage buckets (will respect Terraform state)
echo [DEBUG] Starting storage bucket deployment...
echo Step 2: Deploying storage buckets...
python scripts/deploy_storage.py
set "STORAGE_STATUS=!ERRORLEVEL!"
echo [DEBUG] Storage deployment status: !STORAGE_STATUS!
if !STORAGE_STATUS! NEQ 0 (
    echo [DEBUG] Failed to deploy storage buckets
    echo Error: Failed to deploy storage buckets
    exit /b 1
)

REM Set up service accounts
echo [DEBUG] Starting service account setup...
echo Step 3: Setting up service accounts...
python scripts/setup_service_accounts.py
set "SA_SETUP_STATUS=!ERRORLEVEL!"
echo [DEBUG] Service account setup status: !SA_SETUP_STATUS!
if !SA_SETUP_STATUS! NEQ 0 (
    echo [DEBUG] Failed to set up service accounts
    echo Error: Failed to set up service accounts
    exit /b 1
)

REM Deploy credentials (will respect Terraform state)
echo [DEBUG] Starting credentials deployment...
echo Step 4: Deploying credentials...
python scripts/deploy_credentials.py
set "CRED_DEPLOY_STATUS=!ERRORLEVEL!"
echo [DEBUG] Credentials deployment status: !CRED_DEPLOY_STATUS!
if !CRED_DEPLOY_STATUS! NEQ 0 (
    echo [DEBUG] Failed to deploy credentials
    echo Error: Failed to deploy credentials
    exit /b 1
)

REM Wait for a moment to ensure all resources are ready
echo.
echo [DEBUG] Creating wait time script...
set PYTHON_WAIT=import yaml^

config = yaml.safe_load(open('config.yaml'))^

print(config.get('testing', {}).get('wait_time', 5))

echo !PYTHON_WAIT! > temp_wait.py

echo [DEBUG] Reading wait time from config...
for /f %%i in ('python temp_wait.py') do set WAIT_TIME=%%i
echo [DEBUG] Wait time set to: !WAIT_TIME! seconds
del temp_wait.py
echo [DEBUG] Cleaned up temporary wait script

echo Waiting for %WAIT_TIME% seconds to ensure all resources are ready...
timeout /t %WAIT_TIME% /nobreak > nul
echo [DEBUG] Wait completed

REM Deploy Cloud Function and Scheduler (will respect Terraform state)
echo [DEBUG] Starting Cloud Function and Scheduler deployment...
echo Step 5: Deploying Cloud Function and Scheduler...
python scripts/deploy_functions.py
set "FUNC_DEPLOY_STATUS=!ERRORLEVEL!"
echo [DEBUG] Function deployment status: !FUNC_DEPLOY_STATUS!
if !FUNC_DEPLOY_STATUS! NEQ 0 (
    echo [DEBUG] Failed to deploy Cloud Function and Scheduler
    echo Error: Failed to deploy Cloud Function and Scheduler
    exit /b 1
)

REM Run post-deployment integration tests if enabled
if "%RUN_TESTS%"=="1" (
    echo.
    echo [DEBUG] Starting post-deployment tests...
    echo Step 6: Running post-deployment test...
    for %%f in (%POST_DEPLOYMENT_PATHS%) do (
        echo [DEBUG] Running post-deployment test: %%f
        python %%f
        set "POST_TEST_STATUS=!ERRORLEVEL!"
        echo [DEBUG] Post-deployment test status for %%f: !POST_TEST_STATUS!
        if !POST_TEST_STATUS! NEQ 0 (
            echo [DEBUG] Post-deployment test failed
            echo Warning: Post-deployment test failed
            echo Please check the logs above for details
            exit /b 1
        )
    )
)

echo.
echo [DEBUG] Deployment completed successfully
echo === Deployment Completed Successfully ===
exit /b 0
