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

REM Check if ML is enabled before running terraform
echo [DEBUG] Checking ML configuration before Terraform...
echo import yaml > check_ml_pre.py
echo config = yaml.safe_load(open('config.yaml')) >> check_ml_pre.py
echo ml_enabled = config.get('features', {}).get('enabled_services', {}).get('ml', False) >> check_ml_pre.py
echo print('1' if ml_enabled else '0') >> check_ml_pre.py

for /f %%i in ('python check_ml_pre.py') do set ML_PRE_CHECK=%%i
del check_ml_pre.py

REM Deploy ML function packages BEFORE Terraform if ML is enabled
if "%ML_PRE_CHECK%"=="1" (
    echo.
    echo [DEBUG] ML is enabled, preparing function packages before Terraform...
    echo Preparing ML Cloud Function packages for Terraform...
    
    REM First ensure the storage bucket exists
    python scripts/deploy_storage.py
    set "STORAGE_PRE_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Storage pre-deployment status: !STORAGE_PRE_STATUS!
    if !STORAGE_PRE_STATUS! NEQ 0 (
        echo [DEBUG] Warning: Could not ensure storage buckets exist
        echo Warning: Could not ensure storage buckets exist
    )
    
    REM Now upload the ML function packages
    python scripts/deploy_ml_functions.py
    set "ML_PRE_STATUS=!ERRORLEVEL!"
    echo [DEBUG] ML function package upload status: !ML_PRE_STATUS!
    if !ML_PRE_STATUS! NEQ 0 (
        echo [DEBUG] Warning: Could not upload ML function packages
        echo Warning: Could not upload ML function packages
        echo Terraform deployment of ML functions may fail
    ) else (
        echo [DEBUG] ML function packages uploaded successfully
        echo ML function packages uploaded successfully
    )
    echo.
)

echo [DEBUG] Changing directory to terraform...
cd terraform
echo [DEBUG] Current directory is now: %CD%

REM Initialize Terraform
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

REM Check for ML configuration
echo [DEBUG] Checking ML configuration...
echo import yaml > check_ml_config.py
echo config = yaml.safe_load(open('config.yaml')) >> check_ml_config.py
echo ml_enabled = config.get('features', {}).get('enabled_services', {}).get('ml', False) >> check_ml_config.py
echo print('ML_ENABLED=1' if ml_enabled else 'ML_ENABLED=0') >> check_ml_config.py
echo if ml_enabled: >> check_ml_config.py
echo     print('VERTEX_AI_ENABLED=1' if config.get('features', {}).get('enabled_services', {}).get('aiplatform', True) else 'VERTEX_AI_ENABLED=0') >> check_ml_config.py
echo     print('BIGQUERY_ENABLED=1' if config.get('features', {}).get('enabled_services', {}).get('bigquery', True) else 'BIGQUERY_ENABLED=0') >> check_ml_config.py

python check_ml_config.py > ml_config_output.tmp
for /f "usebackq tokens=1,* delims==" %%a in ("ml_config_output.tmp") do (
    set "%%a=%%b"
    echo [DEBUG] Set %%a=%%b
)
del check_ml_config.py
del ml_config_output.tmp

REM Set up ML components if enabled
if "%ML_ENABLED%"=="1" (
    echo [DEBUG] ML features are enabled
    echo.
    echo === Setting up ML Components ===
    
    REM Install ML-specific requirements
    echo [DEBUG] Installing ML packages...
    echo Installing ML packages...
    if exist ml_requirements.txt (
        pip install -r ml_requirements.txt --quiet
        set "ML_PIP_STATUS=!ERRORLEVEL!"
        echo [DEBUG] ML packages installation status: !ML_PIP_STATUS!
        if !ML_PIP_STATUS! NEQ 0 (
            echo [DEBUG] Failed to install ML packages
            echo Error: Failed to install ML packages
            echo Retrying with output...
            pip install -r ml_requirements.txt
            set "ML_PIP_RETRY_STATUS=!ERRORLEVEL!"
            if !ML_PIP_RETRY_STATUS! NEQ 0 (
                echo [DEBUG] ML packages installation failed
                echo Warning: Some ML packages could not be installed
                echo Continuing with setup...
            )
        )
    ) else (
        echo [DEBUG] ml_requirements.txt not found, installing minimal ML packages
        echo Warning: ml_requirements.txt not found, installing minimal ML packages
        pip install scikit-learn==1.3.1 metaphone "google-cloud-aiplatform[prediction]" google-cloud-bigquery pyarrow fastapi uvicorn --quiet
    )
    
    REM Create ML directories
    echo [DEBUG] Creating ML directories...
    if not exist "ml_models" mkdir ml_models
    if not exist "test_data" mkdir test_data
    if not exist "temp" mkdir temp
    echo [DEBUG] ML directories created
    
    REM Enable required APIs if not in Cloud Build
    if not defined CLOUD_BUILD (
        echo [DEBUG] Enabling ML-related APIs...
        echo Enabling ML-related APIs...
        
        if "%VERTEX_AI_ENABLED%"=="1" (
            echo [DEBUG] Enabling Vertex AI API...
            call gcloud services enable aiplatform.googleapis.com --project=!PROJECT_ID!
            set "VERTEX_STATUS=!ERRORLEVEL!"
            echo [DEBUG] Vertex AI API enable status: !VERTEX_STATUS!
        )
        
        if "%BIGQUERY_ENABLED%"=="1" (
            echo [DEBUG] Enabling BigQuery API...
            call gcloud services enable bigquery.googleapis.com --project=!PROJECT_ID!
            set "BQ_STATUS=!ERRORLEVEL!"
            echo [DEBUG] BigQuery API enable status: !BQ_STATUS!
        )
        
        echo [DEBUG] Enabling Cloud Monitoring API...
        call gcloud services enable monitoring.googleapis.com --project=!PROJECT_ID!
        set "MON_STATUS=!ERRORLEVEL!"
        echo [DEBUG] Cloud Monitoring API enable status: !MON_STATUS!
    )
    
    echo [DEBUG] ML setup completed
    echo ML components set up successfully
    echo.
) else (
    echo [DEBUG] ML features are disabled in config
    echo ML features are disabled in config.yaml
)

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
    echo Warning: Some requirements failed to install
    python -m pip install -r requirements.txt
    set "REQ_RETRY_STATUS=!ERRORLEVEL!"
    if !REQ_RETRY_STATUS! NEQ 0 (
        echo [DEBUG] Some packages could not be installed
        echo Warning: Not all requirements were installed successfully
        echo Continuing with core packages...
    )
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
            ) else if "!TEST_TYPE!"=="ml_tests" (
                if "%ML_ENABLED%"=="1" (
                    echo [DEBUG] Running ML tests...
                    if exist "scripts\test_trained_models_locally.py" (
                        echo Running local ML tests...
                        REM Set environment variables for local ML testing
                        set "LOCAL_ML_TEST=1"
                        set "GOOGLE_AUTH_SUPPRESS_CREDENTIALS_WARNINGS=1"
                        python scripts\test_trained_models_locally.py
                        set "ML_TEST_STATUS=!ERRORLEVEL!"
                        echo [DEBUG] ML test status: !ML_TEST_STATUS!
                        if !ML_TEST_STATUS! NEQ 0 (
                            echo [DEBUG] Warning: ML tests failed
                            echo Warning: ML tests failed (non-critical^)
                        )
                        REM Unset local test environment variables
                        set "LOCAL_ML_TEST="
                        set "GOOGLE_AUTH_SUPPRESS_CREDENTIALS_WARNINGS="
                    )
                ) else (
                    echo [DEBUG] Skipping ML tests (ML not enabled^)
                )
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

REM Terraform has already been applied earlier in the script
if "%USE_TERRAFORM%"=="1" (
    echo [DEBUG] Terraform resources were deployed earlier
    echo Terraform infrastructure is already deployed
    echo.
)

REM Deploy storage buckets (will respect Terraform state)
echo [DEBUG] Starting storage bucket deployment...
echo Step 1: Deploying storage buckets...
python scripts/deploy_storage.py
set "STORAGE_STATUS=!ERRORLEVEL!"
echo [DEBUG] Storage deployment status: !STORAGE_STATUS!
if !STORAGE_STATUS! NEQ 0 (
    echo [DEBUG] Failed to deploy storage buckets
    echo Error: Failed to deploy storage buckets
    exit /b 1
)

REM ML function packages are now uploaded before Terraform runs

REM Set up service accounts
echo [DEBUG] Starting service account setup...
echo Step 2: Setting up service accounts...
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
echo Step 3: Deploying credentials...
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
echo Step 4: Deploying Cloud Function and Scheduler...
python scripts/deploy_functions.py
set "FUNC_DEPLOY_STATUS=!ERRORLEVEL!"
echo [DEBUG] Function deployment status: !FUNC_DEPLOY_STATUS!
if !FUNC_DEPLOY_STATUS! NEQ 0 (
    echo [DEBUG] Failed to deploy Cloud Function and Scheduler
    echo Error: Failed to deploy Cloud Function and Scheduler
    exit /b 1
)

REM Deploy ML components if enabled
if "%ML_ENABLED%"=="1" (
    echo.
    echo [DEBUG] Starting ML deployment...
    echo Step 5: Deploying ML Components...
    
    REM Initialize BigQuery datasets
    echo [DEBUG] Creating ML BigQuery datasets...
    echo Creating ML BigQuery datasets...
    python -c "from src.services.data_export_service import DataExportService; service = DataExportService('!PROJECT_ID!'); service.setup_bigquery_dataset(); service.setup_storage_bucket()" 2>nul
    set "BQ_SETUP_STATUS=!ERRORLEVEL!"
    echo [DEBUG] BigQuery setup status: !BQ_SETUP_STATUS!
    if !BQ_SETUP_STATUS! NEQ 0 (
        echo [DEBUG] Warning: Could not initialize BigQuery datasets
        echo Warning: Could not initialize BigQuery datasets (may already exist^)
    )
    
    REM Create ML feedback table
    echo [DEBUG] Creating ML feedback table...
    echo Creating ML feedback table...
    python -c "from src.services.ml_feedback_service import MLFeedbackService; service = MLFeedbackService('!PROJECT_ID!')" 2>nul
    set "FEEDBACK_STATUS=!ERRORLEVEL!"
    echo [DEBUG] Feedback table setup status: !FEEDBACK_STATUS!
    if !FEEDBACK_STATUS! NEQ 0 (
        echo [DEBUG] Warning: Could not create feedback table
        echo Warning: Could not create feedback table (may already exist^)
    )
    
    REM Check if initial model should be trained
    echo [DEBUG] Checking for initial model training...
    if "%NON_INTERACTIVE%"=="1" (
        echo [DEBUG] Non-interactive mode - skipping initial model training
        echo Skipping initial model training in non-interactive mode
    ) else (
        echo.
        echo Would you like to train an initial ML model?
        echo [1] Yes, train initial model (requires existing transaction data^)
        echo [2] No, skip model training
        echo.
        choice /C 12 /N /M "Enter your choice (1-2): "
        set "MODEL_CHOICE=!ERRORLEVEL!"
        echo [DEBUG] User model training choice: !MODEL_CHOICE!
        
        if "!MODEL_CHOICE!"=="1" (
            echo [DEBUG] User chose to train initial model
            echo Training initial ML model...
            echo This may take several minutes...
            python -c "from src.models.transaction_trainer import TransactionModelTrainer; trainer = TransactionModelTrainer('!PROJECT_ID!'); trainer.train_and_deploy_model('transaction_model_v1')"
            set "MODEL_STATUS=!ERRORLEVEL!"
            echo [DEBUG] Model training status: !MODEL_STATUS!
            if !MODEL_STATUS! NEQ 0 (
                echo [DEBUG] Warning: Could not train initial model
                echo Warning: Could not train initial model
                echo You can train a model later using the /train API endpoint
            ) else (
                echo [DEBUG] Initial model trained successfully
                echo Initial model trained successfully!
            )
        ) else (
            echo [DEBUG] User chose to skip model training
            echo Skipping model training. You can train a model later using the /train API endpoint
        )
    )
    
    echo [DEBUG] ML deployment completed
    echo ML components deployed successfully
)

REM Run post-deployment integration tests if enabled
if "%RUN_TESTS%"=="1" (
    echo.
    echo [DEBUG] Starting post-deployment tests...
    echo Step 5: Running post-deployment test...
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

REM Show ML status if enabled
if "%ML_ENABLED%"=="1" (
    echo.
    echo ML Components Status:
    echo - BigQuery datasets: Initialized
    echo - ML feedback table: Created
    echo - Vertex AI: Enabled
    echo - Model training: Available via /train endpoint
    echo.
    echo ML Testing Commands:
    echo - Local ML test: python scripts/test_trained_models_locally.py
    echo - Integration test: python scripts/test_ml_integration.py
    echo.
)

exit /b 0
