#!/bin/bash

# Exit on any error
set -e

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
PROJECT_ID=$(python3 -c "
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
print(str(config['gcp']['project_id']).strip())
")

REGION=$(python3 -c "
import yaml
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)
print(str(config['gcp']['region']).strip())
")

echo "Using project ID: $PROJECT_ID"
echo "Using region: $REGION"

# Check if Terraform is installed
echo "Checking for Terraform installation..."
if ! command -v terraform &> /dev/null; then
    echo "Terraform is not installed."
    echo
    echo "Options:"
    echo "[1] Skip Terraform and continue with deployment"
    echo "[2] Exit and install Terraform manually"
    echo
    read -p "Enter your choice (1-2): " TERRAFORM_CHOICE
    
    if [ "$TERRAFORM_CHOICE" = "1" ]; then
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

# Check GCP authentication
echo "[DEBUG] Starting GCP authentication check..."
echo
echo "Step 1: Checking user authentication..."
echo "[DEBUG] Getting active account..."

# Get active account
ACTIVE_ACCOUNT=$(gcloud auth list --format="value(account)" --filter="status=ACTIVE" 2>/dev/null)

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

# Set test environment variable (to match setup.bat)
export TEST_ENV=true

# Check for virtual environment
if [ -f "venv/bin/activate" ]; then
    echo "Found existing virtual environment"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip silently
python -m pip install --upgrade pip --quiet

# Install requirements
echo "Installing requirements..."
python -m pip install -r requirements.txt --quiet --no-warn-script-location
if [ $? -ne 0 ]; then
    echo "Error: Failed to install requirements"
    python -m pip install -r requirements.txt  # Run again with full output for debugging
    exit 1
fi

# Run pre-deployment tests if enabled in config
echo
echo "Checking test configuration..."

# Read test configuration
eval "$(python3 -c "
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
print(f'TEST_ORDER={json.dumps(test_order)}')

for test_type in test_order:
    enabled = '1' if components.get(test_type, True) else '0'
    print(f'{test_type.upper()}_ENABLED={enabled}')
    paths = test_paths.get(test_type, [])
    if paths:
        print(f'{test_type.upper()}_PATHS={json.dumps(paths)}')
")"

if [ "$RUN_TESTS" = "1" ]; then
    echo "=== Running Pre-deployment Tests ==="
    echo
    
    STEP=1
    
    # Execute tests in order
    for TEST_TYPE in $(echo "$TEST_ORDER" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
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
                        for TEST_PATH in $(echo "${!PATHS_VAR}" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
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
                    for TEST_PATH in $(echo "${!PATHS_VAR}" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
                        python "$TEST_PATH"
                        if [ $? -ne 0 ]; then
                            echo "Error: Package tests failed"
                            exit 1
                        fi
                    done
                    ;;
                    
                "config_tests")
                    for TEST_PATH in $(echo "${!PATHS_VAR}" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
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

# Initialize and apply Terraform if available
if command -v terraform &> /dev/null; then
    echo
    echo "Initializing Terraform..."
    cd terraform
    if ! terraform init; then
        echo "Error: Failed to initialize Terraform"
        exit 1
    fi
    
    echo
    echo "Showing planned changes..."
    terraform plan
    
    echo
    echo "Would you like to apply these changes?"
    echo "[1] Yes, apply the changes"
    echo "[2] No, skip Terraform changes"
    read -p "Enter your choice (1-2): " APPLY_CHOICE
    
    if [ "$APPLY_CHOICE" = "1" ]; then
        if ! terraform apply -auto-approve; then
            echo "Error: Failed to apply Terraform configuration"
            exit 1
        fi
        echo "Terraform changes applied successfully"
    else
        echo "Skipping Terraform changes"
    fi
    cd ..
fi

# Deploy storage buckets (will respect Terraform state)
echo "Step 2: Deploying storage buckets..."
python scripts/deploy_storage.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy storage buckets"
    exit 1
fi

# Set up service accounts
echo "Step 2: Setting up service accounts..."
python scripts/setup_service_accounts.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to set up service accounts"
    exit 1
fi

# Deploy credentials
echo "Step 3: Deploying credentials..."
python scripts/deploy_credentials.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy credentials"
    exit 1
fi

# Wait for a moment to ensure all resources are ready
echo
WAIT_TIME=$(python3 -c "
import yaml
config = yaml.safe_load(open('config.yaml'))
print(config.get('testing', {}).get('wait_time', 5))
")

echo "Waiting for $WAIT_TIME seconds to ensure all resources are ready..."
sleep "$WAIT_TIME"

# Deploy Cloud Function and Scheduler
echo "Step 4: Deploying Cloud Function and Scheduler..."
python scripts/deploy_functions.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy Cloud Function and Scheduler"
    exit 1
fi

# Run post-deployment integration tests if enabled
if [ "$RUN_TESTS" = "1" ] && [ "$INTEGRATION_TESTS_ENABLED" = "1" ]; then
    echo
    echo "Step 5: Running post-deployment tests..."
    for TEST_PATH in $(echo "$INTEGRATION_TESTS_PATHS" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
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