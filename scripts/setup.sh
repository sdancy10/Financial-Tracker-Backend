#!/bin/bash

# Exit on any error
set -e

echo "[DEBUG] Starting setup script..."
echo "[DEBUG] Current working directory: $(pwd)"
echo "[DEBUG] Script location: $0"
echo "[DEBUG] All script parameters: $@"

# Check if running in Cloud Build
if [ -n "$CLOUD_BUILD" ]; then
    echo "[DEBUG] Detected Cloud Build environment"
    echo "[DEBUG] CLOUD_BUILD value: $CLOUD_BUILD"
    NON_INTERACTIVE=1
    echo "Running in Cloud Build environment"
    echo "Using Cloud Build service account authentication"
    # Skip GCP auth check in Cloud Build as it uses service account
    echo "Using service account credentials for Terraform"
    export USE_GCP_AUTH=0
else
    echo "[DEBUG] Running in local environment"
    NON_INTERACTIVE=0
    export USE_GCP_AUTH=1
fi

# Get the current directory
CURRENT_DIR=$(pwd)
echo "[DEBUG] Setting up environment variables..."
echo "[DEBUG] CURRENT_DIR: $CURRENT_DIR"

# Set PYTHONPATH to include current directory
export PYTHONPATH="$CURRENT_DIR:$PYTHONPATH"
echo "[DEBUG] Updated PYTHONPATH: $PYTHONPATH"

# Function to ensure virtual environment is activated
ensure_venv() {
    if [ -n "$CLOUD_BUILD" ] && [ -z "$VIRTUAL_ENV" ]; then
        echo "[DEBUG] Virtual environment not active, reactivating..."
        source /workspace/venv/bin/activate
        echo "[DEBUG] Virtual environment reactivated, Python path: $(which python3)"
    fi
}

# Activate virtual environment in Cloud Build
if [ -n "$CLOUD_BUILD" ]; then
    echo "[DEBUG] Checking for virtual environment..."
    if [ ! -f "/workspace/venv/bin/activate" ]; then
        echo "[ERROR] Virtual environment not found at /workspace/venv"
        echo "[DEBUG] Contents of /workspace:"
        ls -la /workspace
        echo "[DEBUG] Contents of /workspace/venv (if exists):"
        ls -la /workspace/venv || echo "venv directory not found"
        exit 1
    fi
    echo "[DEBUG] Activating virtual environment in Cloud Build..."
    source /workspace/venv/bin/activate
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to activate virtual environment"
        exit 1
    fi
    echo "[DEBUG] Virtual environment activated, Python path: $(which python3)"
    echo "[DEBUG] Python version: $(python3 --version)"
fi

# Install Python dependencies (skip in Cloud Build)
if [ -n "$CLOUD_BUILD" ]; then
    echo "[DEBUG] Skipping Python package installation in Cloud Build environment (handled by cloudbuild.yaml)"
else
    echo "[DEBUG] Installing Python dependencies..."
    echo "Installing required Python packages..."
    pip install pyyaml --quiet
    echo "[DEBUG] pip install result: $?"
fi

# Read project configuration from config.yaml
echo "[DEBUG] Reading project configuration..."
ensure_venv

# Create temporary Python script for config reading
echo "[DEBUG] Creating temporary Python script for config reading..."
echo "import yaml" > read_config.py
echo "with open('config.yaml', 'r') as f:" >> read_config.py
echo "    config = yaml.safe_load(f)" >> read_config.py
echo "print('PROJECT_ID=' + str(config['gcp']['project_id']).strip())" >> read_config.py
echo "print('REGION=' + str(config['gcp']['region']).strip())" >> read_config.py

# Get project ID and region from config.yaml
echo "[DEBUG] Executing config reading script..."
python3 read_config.py > config_output.tmp
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to read config.yaml"
    echo "[DEBUG] Current directory contents:"
    ls -la
    exit 1
fi

while IFS='=' read -r key value; do
    if [ "$key" = "PROJECT_ID" ]; then
        PROJECT_ID="$value"
        echo "[DEBUG] Found PROJECT_ID: $PROJECT_ID"
    elif [ "$key" = "REGION" ]; then
        REGION="$value"
        echo "[DEBUG] Found REGION: $REGION"
    fi
done < config_output.tmp

# Clean up temporary files
echo "[DEBUG] Cleaning up temporary files..."
rm read_config.py
rm config_output.tmp

echo "Using project ID: $PROJECT_ID"
echo "Using region: $REGION"

# Check if Terraform is installed
echo "[DEBUG] Checking for Terraform installation..."
echo "[DEBUG] Current PATH: $PATH"
if ! command -v terraform &> /dev/null; then
    echo "[DEBUG] Terraform not found in PATH"
    echo "Terraform is not installed or not in PATH."
    echo

    if [ "$NON_INTERACTIVE" = "1" ]; then
        echo "[DEBUG] Running in non-interactive mode, proceeding with automatic installation"
        echo "Running in non-interactive mode, installing Terraform automatically..."
        # Download and install Terraform directly in Cloud Build environment
        echo "Downloading Terraform..."
        echo "[DEBUG] Downloading from: https://releases.hashicorp.com/terraform/1.7.4/terraform_1.7.4_linux_amd64.zip"
        wget https://releases.hashicorp.com/terraform/1.7.4/terraform_1.7.4_linux_amd64.zip
        if [ $? -ne 0 ]; then
            echo "[ERROR] Failed to download Terraform"
            echo "[DEBUG] wget exit code: $?"
            USE_TERRAFORM=0
        else
            echo "[DEBUG] Terraform download successful"
            echo "Cleaning up any existing Terraform binary..."
            echo "[DEBUG] Current directory contents before cleanup:"
            ls -la
            # Only remove the terraform binary file in the current directory, preserving the terraform directory
            rm -f ./terraform.exe
            rm -f ./terraform.exe.old
            rm -f ./terraform_*.exe
            # If it exists, remove the non-Windows terraform binary
            if [ -f "./terraform" ]; then
                echo "[DEBUG] Found existing terraform binary, removing it"
                rm -f "./terraform"
            fi
            echo "[DEBUG] Current directory contents after cleanup:"
            ls -la
            
            echo "Unzipping Terraform..."
            # Force overwrite without prompting
            unzip -o terraform_1.7.4_linux_amd64.zip
            UNZIP_RESULT=$?
            echo "[DEBUG] unzip exit code: $UNZIP_RESULT"
            if [ $UNZIP_RESULT -ne 0 ]; then
                echo "[ERROR] Failed to unzip Terraform"
                USE_TERRAFORM=0
            else
                echo "[DEBUG] Successfully unzipped Terraform"
                echo "Installing Terraform..."
                chmod +x terraform
                echo "[DEBUG] Attempting to move terraform to /usr/local/bin"
                mv -f terraform /usr/local/bin/
                if [ $? -ne 0 ]; then
                    echo "[DEBUG] Failed to move to /usr/local/bin, trying current directory"
                    echo "Error: Failed to install Terraform. Trying current directory..."
                    mv -f terraform ./terraform
                    echo "[DEBUG] Adding current directory to PATH"
                    export PATH=$PATH:$PWD
                    USE_TERRAFORM=1
                else
                    echo "[DEBUG] Successfully installed Terraform to /usr/local/bin"
                    echo "Terraform installed successfully."
                    USE_TERRAFORM=1
                fi
                echo "[DEBUG] Cleaning up zip file"
                rm -f terraform_1.7.4_linux_amd64.zip
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

# Check GCP authentication (only if not in Cloud Build)
if [ -z "$CLOUD_BUILD" ]; then
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
fi

# Print current GCP configuration
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

# Initialize Terraform
echo "[DEBUG] Starting Terraform initialization..."
ensure_venv

# Debug: Check if GOOGLE_APPLICATION_CREDENTIALS is set
if [ -n "$GOOGLE_APPLICATION_CREDENTIALS" ]; then
    echo "[DEBUG] Found GOOGLE_APPLICATION_CREDENTIALS set to: $GOOGLE_APPLICATION_CREDENTIALS"
    # Get absolute path for credentials
    ABSOLUTE_CREDS_PATH="$CURRENT_DIR/$GOOGLE_APPLICATION_CREDENTIALS"
    echo "[DEBUG] Using absolute path for credentials: $ABSOLUTE_CREDS_PATH"
    
    # Check if the file exists
    if [ ! -f "$ABSOLUTE_CREDS_PATH" ]; then
        echo "[DEBUG] Service account key file not found at: $ABSOLUTE_CREDS_PATH"
        echo "[DEBUG] Directory contents:"
        ls -la "$(dirname "$ABSOLUTE_CREDS_PATH")"
        echo "[DEBUG] Falling back to application default credentials"
    else
        echo "[DEBUG] Service account key file found and readable"
    fi
fi

# Change to terraform directory and initialize
echo "[DEBUG] Changing to terraform directory..."
cd terraform || {
    echo "[ERROR] Failed to change to terraform directory"
    echo "[DEBUG] Current directory: $(pwd)"
    echo "[DEBUG] Directory contents:"
    ls -la
    exit 1
}

echo "[DEBUG] Current directory after cd: $(pwd)"
echo "[DEBUG] Terraform directory contents:"
ls -la

echo "[DEBUG] Running terraform init..."
terraform init -input=false
INIT_RESULT=$?
echo "[DEBUG] terraform init exit code: $INIT_RESULT"

# If in Cloud Build, run terraform plan and apply
if [ -n "$CLOUD_BUILD" ]; then
    echo "[DEBUG] Executing Terraform in Cloud Build environment"
    echo "Running Terraform in Cloud Build environment..."
    echo "[DEBUG] Running terraform plan..."
    terraform plan -input=false -out=tfplan
    PLAN_RESULT=$?
    echo "[DEBUG] terraform plan exit code: $PLAN_RESULT"
    
    if [ $PLAN_RESULT -eq 0 ]; then
        echo "[DEBUG] Running terraform apply..."
        terraform apply -input=false -auto-approve tfplan
        APPLY_RESULT=$?
        echo "[DEBUG] terraform apply exit code: $APPLY_RESULT"
    else
        echo "[ERROR] Terraform plan failed, skipping apply"
    fi
fi

echo "[DEBUG] Setup script completed"
echo "Setup complete!"