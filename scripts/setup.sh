#!/bin/bash

# Exit on any error
set -e

# Check if running in Cloud Build
if [ -n "$CLOUD_BUILD" ]; then
    echo "Running in Cloud Build environment"
    NON_INTERACTIVE=1
else
    NON_INTERACTIVE=0
fi

# Get the current directory
CURRENT_DIR=$(pwd)
echo "Current directory is: $CURRENT_DIR"

# Set PYTHONPATH to include current directory
export PYTHONPATH="$CURRENT_DIR:$PYTHONPATH"
echo "Set PYTHONPATH to include current directory: $PYTHONPATH"

# Install pyyaml if needed
echo "Installing required Python packages..."
pip install pyyaml --quiet

# Read project configuration from config.yaml
echo "Reading project configuration..."
echo "import yaml" > read_config.py
echo "with open('config.yaml', 'r') as f:" >> read_config.py
echo "    config = yaml.safe_load(f)" >> read_config.py
echo "print('PROJECT_ID=' + str(config['gcp']['project_id']).strip())" >> read_config.py
echo "print('REGION=' + str(config['gcp']['region']).strip())" >> read_config.py

# Get project ID and region from config.yaml
python3 read_config.py > config_output.tmp
while IFS='=' read -r key value; do
    if [ "$key" = "PROJECT_ID" ]; then
        PROJECT_ID="$value"
    elif [ "$key" = "REGION" ]; then
        REGION="$value"
    fi
done < config_output.tmp

# Clean up temporary files
rm read_config.py
rm config_output.tmp

echo "Using project ID: $PROJECT_ID"
echo "Using region: $REGION"

# Check if Terraform is installed
echo "Checking for Terraform installation..."
if ! command -v terraform &> /dev/null; then
    echo "Terraform is not installed or not in PATH."
    echo

    if [ "$NON_INTERACTIVE" = "1" ]; then
        echo "Running in non-interactive mode, installing Terraform automatically..."
        # Download and install Terraform directly in Cloud Build environment
        echo "Downloading Terraform..."
        wget https://releases.hashicorp.com/terraform/1.7.4/terraform_1.7.4_linux_amd64.zip
        if [ $? -ne 0 ]; then
            echo "Error: Failed to download Terraform."
            USE_TERRAFORM=0
        else
            echo "Unzipping Terraform..."
            unzip terraform_1.7.4_linux_amd64.zip
            if [ $? -ne 0 ]; then
                echo "Error: Failed to unzip Terraform."
                USE_TERRAFORM=0
            else
                echo "Installing Terraform..."
                chmod +x terraform
                mv terraform /usr/local/bin/
                if [ $? -ne 0 ]; then
                    echo "Error: Failed to install Terraform. Trying current directory..."
                    mv terraform ./terraform
                    export PATH=$PATH:$PWD
                    USE_TERRAFORM=1
                else
                    echo "Terraform installed successfully."
                    USE_TERRAFORM=1
                fi
                rm terraform_1.7.4_linux_amd64.zip
            fi
        fi
    else
        echo "Options:"
        echo "[1] Automatic installation (will install package manager if needed)"
        echo "[2] Skip Terraform and continue with deployment"
        echo "[3] Exit and install Terraform manually"
        echo
        read -p "Enter your choice (1-3): " TERRAFORM_CHOICE
        
        if [ "$TERRAFORM_CHOICE" = "1" ]; then
            # Check the OS and use appropriate package manager
            if [ "$(uname)" = "Darwin" ]; then
                # macOS - use Homebrew
                if ! command -v brew &> /dev/null; then
                    echo "Homebrew not found. Installing Homebrew..."
                    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
                    if [ $? -ne 0 ]; then
                        echo "Error: Failed to install Homebrew."
                        echo "Please run this script as administrator or install Terraform manually."
                        exit 1
                    fi
                    echo "Homebrew installed successfully."
                fi
                echo "Installing Terraform using Homebrew..."
                brew install terraform
                if [ $? -ne 0 ]; then
                    echo "Error: Failed to install Terraform using Homebrew."
                    echo "Please try running the script as administrator."
                    USE_TERRAFORM=0
                else
                    echo "Terraform installed successfully."
                    USE_TERRAFORM=1
                fi
            elif [ "$(expr substr $(uname -s) 1 5)" = "Linux" ]; then
                # Linux - use apt-get or yum
                if command -v apt-get &> /dev/null; then
                    echo "Installing Terraform using apt-get..."
                    sudo apt-get update
                    sudo apt-get install -y terraform
                    if [ $? -ne 0 ]; then
                        echo "Error: Failed to install Terraform using apt-get."
                        echo "Please try running the script as administrator."
                        USE_TERRAFORM=0
                    else
                        echo "Terraform installed successfully."
                        USE_TERRAFORM=1
                    fi
                elif command -v yum &> /dev/null; then
                    echo "Installing Terraform using yum..."
                    sudo yum install -y terraform
                    if [ $? -ne 0 ]; then
                        echo "Error: Failed to install Terraform using yum."
                        echo "Please try running the script as administrator."
                        USE_TERRAFORM=0
                    else
                        echo "Terraform installed successfully."
                        USE_TERRAFORM=1
                    fi
                else
                    echo "Error: No supported package manager found."
                    echo "Please install Terraform manually."
                    USE_TERRAFORM=0
                fi
            else
                echo "Error: Unsupported operating system."
                echo "Please install Terraform manually."
                USE_TERRAFORM=0
            fi
            
            # Verify Terraform is now available
            if ! command -v terraform &> /dev/null; then
                echo "Error: Terraform installation succeeded but command not found."
                echo "Please close this window and run the script again."
                exit 1
            fi
            
            terraform --version
        elif [ "$TERRAFORM_CHOICE" = "2" ]; then
            echo "Skipping Terraform installation and continuing with deployment..."
            USE_TERRAFORM=0
        else
            echo "Please install Terraform manually:"
            echo "1. Download from: https://www.terraform.io/downloads.html"
            echo "2. Add to your system PATH"
            echo "3. Run setup.sh again"
            exit 1
        fi
    fi
else
    USE_TERRAFORM=1
fi

# Check GCP authentication
echo "[DEBUG] Starting GCP authentication check..."
echo
echo "Step 1: Checking user authentication..."
echo "[DEBUG] Getting active account..."

# Get active account directly
ACTIVE_ACCOUNT=$(gcloud auth list --format="value(account)" --filter="status=ACTIVE" 2>/dev/null)
if [ -n "$ACTIVE_ACCOUNT" ]; then
    echo "[DEBUG] Found active account: $ACTIVE_ACCOUNT"
else
    echo "[DEBUG] No active account found"
fi

if [ -z "$ACTIVE_ACCOUNT" ]; then
    echo "No active account found."
    echo
    echo "NOTE: The next step will open a browser window for authentication."
    echo "After authenticating, return to this window to continue."
    echo
    read -p "Press Enter to continue..."
    
    echo "[DEBUG] Starting user login..."
    gcloud auth login --no-launch-browser
    
    # Verify the login was successful
    ACTIVE_ACCOUNT=$(gcloud auth list --format="value(account)" --filter="status=ACTIVE" 2>/dev/null)
    if [ -z "$ACTIVE_ACCOUNT" ]; then
        echo "Error: Failed to authenticate with GCP."
        exit 1
    fi
    echo "[DEBUG] Successfully authenticated as: $ACTIVE_ACCOUNT"
    
    # Set project and region
    echo "[DEBUG] Setting project and region..."
    if ! gcloud config set project "$PROJECT_ID"; then
        echo "Error: Failed to set project."
        exit 1
    fi
    if ! gcloud config set compute/region "$REGION"; then
        echo "Error: Failed to set region."
        exit 1
    fi
    echo "[DEBUG] Project and region configured successfully."
else
    echo "[DEBUG] Using existing authentication for account: $ACTIVE_ACCOUNT"
    
    # Verify project and region are set correctly
    echo "[DEBUG] Verifying project and region configuration..."
    
    CURRENT_PROJECT=$(gcloud config get-value project 2>/dev/null)
    CURRENT_REGION=$(gcloud config get-value compute/region 2>/dev/null)
    
    if [ "$CURRENT_PROJECT" != "$PROJECT_ID" ]; then
        echo "[DEBUG] Setting project to $PROJECT_ID..."
        if ! gcloud config set project "$PROJECT_ID"; then
            echo "Error: Failed to set project."
            exit 1
        fi
    fi
    
    if [ "$CURRENT_REGION" != "$REGION" ]; then
        echo "[DEBUG] Setting region to $REGION..."
        if ! gcloud config set compute/region "$REGION"; then
            echo "Error: Failed to set region."
            exit 1
        fi
    fi
fi

echo "[DEBUG] Starting application default credentials check..."
echo "Step 2: Checking application default credentials..."
echo "Testing access token retrieval..."
if ! gcloud auth application-default print-access-token >/dev/null 2>&1; then
    echo "[DEBUG] No ADC found, entering setup..."
    echo "No application default credentials found (required for Terraform)."
    echo
    echo "NOTE: The next step will open a browser window for authentication."
    echo "After authenticating, return to this window to continue."
    echo
    read -p "Press Enter to continue..."
    
    echo "[DEBUG] Starting ADC login..."
    if ! gcloud auth application-default login --no-launch-browser; then
        echo
        echo "Error: Failed to set up application default credentials."
        exit 1
    else
        echo
        echo "Successfully configured application default credentials."
    fi
else
    echo "[DEBUG] ADC already configured"
    echo "✓ Application default credentials are already configured."
    echo "✓ User is authenticated as: $ACTIVE_ACCOUNT"
fi

echo "[DEBUG] Authentication check complete"
echo
echo "Current GCP configuration:"
echo "------------------------"
echo "Project:"
gcloud config get-value project
echo "Account:"
gcloud config get-value account
echo "Region:"
gcloud config get-value compute/region
echo "------------------------"
echo

# Now use Terraform to manage infrastructure
echo "Initializing Terraform..."

# Handle GOOGLE_APPLICATION_CREDENTIALS path
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "[DEBUG] Found GOOGLE_APPLICATION_CREDENTIALS set to: $GOOGLE_APPLICATION_CREDENTIALS"
    # Convert relative path to absolute path
    CREDENTIALS_PATH="$CURRENT_DIR/$GOOGLE_APPLICATION_CREDENTIALS"
    echo "[DEBUG] Using absolute path for credentials: $CREDENTIALS_PATH"
    if [ -f "$CREDENTIALS_PATH" ]; then
        echo "[DEBUG] Service account key file found"
        export GOOGLE_APPLICATION_CREDENTIALS="$CREDENTIALS_PATH"
    else
        echo "[DEBUG] Service account key file not found at: $CREDENTIALS_PATH"
        echo "[DEBUG] Falling back to application default credentials"
        unset GOOGLE_APPLICATION_CREDENTIALS
    fi
fi

cd terraform

# Initialize Terraform first
if ! terraform init; then
    echo "Error: Failed to initialize Terraform."
    exit 1
fi

echo
echo "Showing planned changes..."
if ! terraform plan; then
    echo "Error: Failed to plan Terraform changes."
    exit 1
fi

# Modify the Terraform apply section to use non-interactive mode
if [ "$NON_INTERACTIVE" = "1" ]; then
    echo "Running in non-interactive mode, applying Terraform changes automatically..."
    terraform apply -auto-approve
else
    echo
    echo "Would you like to apply these changes?"
    echo "[1] Yes, apply the changes"
    echo "[2] No, skip Terraform changes"
    echo
    read -p "Enter your choice (1-2): " APPLY_CHOICE

    if [ "$APPLY_CHOICE" = "1" ]; then
        echo "Applying Terraform changes..."
        terraform apply -auto-approve
    else
        echo "Skipping Terraform changes."
    fi
fi

cd ..

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Found existing virtual environment"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Set test environment variable
export TEST_ENV=true

# Install requirements if needed
echo "Installing requirements..."
pip install -r requirements.txt > /dev/null 2>&1

# Run tests and deployment
echo "Checking test configuration..."
echo "=== Running Pre-deployment Tests ==="

# Run unit tests first
echo
echo "Step 1: Running unit tests..."

# Upgrade pip silently
python -m pip install --upgrade pip --quiet

# Install requirements
echo "Installing requirements..."
python -m pip install -r requirements.txt --quiet --no-warn-script-location
if [ $? -ne 0 ]; then
    echo "Error: Failed to install requirements"
    python -m pip install -r requirements.txt
    exit 1
fi

# Run pre-deployment tests if enabled in config
echo
echo "Checking test configuration..."

# Create Python script for test configuration
cat > temp_config.py << 'EOL'
import yaml
import json

config = yaml.safe_load(open('config.yaml'))
test_config = config.get('testing', {})
components = test_config.get('components', {})
test_paths = test_config.get('test_paths', {})
test_order = test_config.get('test_order', ['unit_tests', 'package_tests', 'config_tests', 'integration_tests'])

run_tests = '1' if test_config.get('run_after_deployment', False) else '0'
run_all = '1' if test_config.get('run_all_tests', False) else '0'

print(f'RUN_TESTS={run_tests}')
print(f'RUN_ALL={run_all}')
print(f'TEST_ORDER={",".join(test_order)}')

for test_type in test_order:
    enabled = '1' if components.get(test_type, True) else '0'
    print(f'{test_type.upper()}_ENABLED={enabled}')
    paths = test_paths.get(test_type, [])
    if paths:
        print(f'{test_type.upper()}_PATHS={" ".join(paths)}')
EOL

# Execute the temporary script and capture output
while IFS='=' read -r key value; do
    if [ -n "$key" ]; then
        eval "$key=$value"
    fi
done < <(python3 temp_config.py)
rm temp_config.py

if [ "$RUN_TESTS" = "1" ]; then
    echo "=== Running Pre-deployment Tests ==="
    echo
    
    STEP=1
    
    # Execute tests in order
    for TEST_TYPE in ${TEST_ORDER//,/ }; do
        ENABLED_VAR="${TEST_TYPE^^}_ENABLED"
        PATHS_VAR="${TEST_TYPE^^}_PATHS"
        
        if [ "${!ENABLED_VAR}" = "1" ]; then
            echo
            echo "Step $STEP: Running $TEST_TYPE tests..."
            
            case "$TEST_TYPE" in
                "unit_tests")
                    if [ "$RUN_ALL" = "1" ]; then
                        python -m pytest tests -v
                        if [ $? -ne 0 ]; then
                            echo "Error: Unit tests failed"
                            exit 1
                        fi
                    else
                        for TEST_PATH in ${!PATHS_VAR}; do
                            echo "Running tests in: $TEST_PATH"
                            python -m pytest "$TEST_PATH" -v
                            if [ $? -ne 0 ]; then
                                echo "Error: Unit tests failed in $TEST_PATH"
                                exit 1
                            fi
                        done
                    fi
                    ;;
                    
                "package_tests")
                    for TEST_PATH in ${!PATHS_VAR}; do
                        python "$TEST_PATH"
                        if [ $? -ne 0 ]; then
                            echo "Error: Package tests failed"
                            exit 1
                        fi
                    done
                    ;;
                    
                "config_tests")
                    for TEST_PATH in ${!PATHS_VAR}; do
                        python "$TEST_PATH"
                        if [ $? -ne 0 ]; then
                            echo "Error: Configuration tests failed"
                            exit 1
                        fi
                    done
                    ;;
                    
                "integration_tests")
                    # Integration tests are run after deployment
                    echo "Integration tests will run after deployment"
                    ;;
            esac
        else
            echo "Skipping $TEST_TYPE (disabled in config)"
        fi
        
        STEP=$((STEP + 1))
    done
    
    echo
    echo "=== All Pre-deployment Tests Passed ==="
    echo
else
    echo "Skipping tests (disabled in config.yaml)"
    echo
fi

echo "=== Starting Deployment ==="
echo

# Check if we should deploy infrastructure with Terraform
if [ "$USE_TERRAFORM" = "1" ]; then
    echo "Step 1: Applying Terraform configuration..."
    cd terraform
    terraform init
    if [ $? -ne 0 ]; then
        echo "Error: Failed to initialize Terraform"
        exit 1
    fi
    terraform apply
    if [ $? -ne 0 ]; then
        echo "Error: Failed to apply Terraform configuration"
        exit 1
    fi
    cd ..
    echo "Terraform resources deployed successfully"
    echo
fi

# Deploy storage buckets (will respect Terraform state)
echo "Step 2: Deploying storage buckets..."
python scripts/deploy_storage.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy storage buckets"
    exit 1
fi

# Set up service accounts
echo "Step 3: Setting up service accounts..."
python scripts/setup_service_accounts.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to set up service accounts"
    exit 1
fi

# Deploy credentials (will respect Terraform state)
echo "Step 4: Deploying credentials..."
python scripts/deploy_credentials.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy credentials"
    exit 1
fi

# Wait for a moment to ensure all resources are ready
echo
cat > temp_wait.py << 'EOL'
import yaml
config = yaml.safe_load(open('config.yaml'))
print(config.get('testing', {}).get('wait_time', 5))
EOL

WAIT_TIME=$(python3 temp_wait.py)
rm temp_wait.py

echo "Waiting for $WAIT_TIME seconds to ensure all resources are ready..."
sleep "$WAIT_TIME"

# Deploy Cloud Function and Scheduler (will respect Terraform state)
echo "Step 5: Deploying Cloud Function and Scheduler..."
python scripts/deploy_functions.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy Cloud Function and Scheduler"
    exit 1
fi

# Run post-deployment integration tests if enabled
if [ "$RUN_TESTS" = "1" ]; then
    echo
    echo "Step 6: Running post-deployment tests..."
    for TEST_PATH in ${POST_DEPLOYMENT_PATHS}; do
        python "$TEST_PATH"
        if [ $? -ne 0 ]; then
            echo "Warning: Post-deployment test failed"
            echo "Please check the logs above for details"
            exit 1
        fi
    done
fi

echo
echo "=== Deployment Completed Successfully ==="
exit 0