# Setup Instructions

This document provides detailed setup and deployment instructions for the Financial Transaction Tracker. For a high-level overview of the system architecture and components, please see [ARCHITECTURE.md](ARCHITECTURE.md).

## Prerequisites

- Python 3.9 or higher
- Google Cloud SDK
- Terraform
- A Google Cloud Project with billing enabled
- Git (for version control)

## Credentials Setup

The project uses a hybrid approach for credential management:

1. **Initial Setup (Local Development)**:
   Place the following files in the `credentials/` folder:
   - `service-account-key.json` - GCP service account key
   - `gmail_oauth_credentials_[user].json` - User-specific Gmail OAuth tokens (created by setup_oauth.py)

2. **Deployment to GCP**:
   Use the provided scripts to manage credentials:
   ```bash
   # Deploy credentials to Secret Manager
   python scripts/deploy_credentials.py

   # Verify deployment
   python scripts/list_secrets.py

   # Remove secrets if needed
   python scripts/remove_secrets.py
   ```

3. **Production Mode**:
   After deployment, credentials are managed entirely through GCP Secret Manager:
   - Credentials are securely stored with proper encoding
   - All required fields are maintained (client_id, client_secret, refresh_token, etc.)
   - Local credential files are no longer needed

See [CREDENTIAL_MANAGEMENT.md](CREDENTIAL_MANAGEMENT.md) for detailed instructions on:
- Obtaining the necessary credentials
- Setting up OAuth2 for Gmail
- Creating service accounts
- Managing credentials in GCP Secret Manager

## GCloud CLI and Terraform Setup (Windows)

1. Install Google Cloud SDK:
   - Download from: https://cloud.google.com/sdk/docs/install
   - Run the installer and follow the prompts
   - Restart your terminal/PowerShell after installation

2. Install Terraform:
   - Using Chocolatey: `choco install terraform`
   - Or download from: https://www.terraform.io/downloads.html
   - Add to your system PATH
   - Verify installation: `terraform --version`

3. Initialize GCloud and authenticate:
   ```powershell
   # Login to your Google Account
   gcloud auth login

   # Set up application default credentials (required for Terraform)
   gcloud auth application-default login

   # Set your project
   gcloud config set project YOUR_PROJECT_ID
   ```

4. Create a service account in GCP Console:
   - Go to IAM & Admin > Service Accounts
   - Click "Create Service Account"
   - Name: `python-etl`
   - Grant necessary roles:
     - Secret Manager Admin
     - Storage Admin
     - Cloud Functions Developer
     - Cloud Scheduler Admin
   - Create and download key as JSON

5. Place the downloaded service account key in:
   ```
   credentials/service-account-key.json
   ```

6. Create and configure environment files:
   - Copy `config.yaml.example` to `config.yaml`
   - Update configuration with your settings:
   ```yaml
   gcp:
     project_id: "YOUR_PROJECT_ID"
     region: "YOUR_REGION"
     service_account_key_path: "credentials/service-account-key.json"

   features:
      enabled_services:
         cloud_api: false      # Cloud Run API and services
         cloud_functions: true # Cloud Functions API and services
         cloud_build: true    # Cloud Build API and triggers
         storage: true        # Cloud Storage API and buckets
         pubsub: true        # Pub/Sub API and topics
         scheduler: true     # Cloud Scheduler API and jobs
         firestore: true     # Firestore API
         secrets: true       # Secret Manager API and secrets
         bigquery: true      # BigQuery API for ML data warehouse
         ml: true            # Machine Learning features (Vertex AI, etc.)
         aiplatform: true    # Vertex AI API for model training/deployment
   ```

## Project Setup

1. Clone the repository and navigate to the project directory:
   ```bash
   git clone <repository-url>
   cd financial-tracker-backend
   ```

2. Run setup script:
   ```bash
   # For Windows:
   scripts/setup.bat

   # For Unix/Linux:
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

   The setup script will:
   - Create and activate a virtual environment
   - Install required dependencies
   - Set up GCP authentication
   - Initialize and apply Terraform configuration
   - Run configured tests

## Infrastructure Management

The project uses Terraform to manage infrastructure:

1. **Infrastructure Deployment**:
   ```bash
   cd terraform
   terraform init
   terraform plan    # Review changes
   terraform apply   # Apply changes
   ```

2. **Infrastructure Updates**:
   - Edit Terraform configurations in `terraform/` directory
   - Run `terraform plan` to review changes
   - Run `terraform apply` to apply changes

3. **Feature Management**:
   - Use `config.yaml` to enable/disable features
   - Terraform will respect these settings
   - Changes require re-running `terraform apply`

## Configuration

### Test Configuration

Tests can be configured in `config.yaml`:

```yaml
testing:
  run_after_deployment: true  # Enable/disable tests
  run_all_tests: false       # Run all tests or only specified paths
  wait_time: 5              # Wait time between deployment steps
  components:
    unit_tests: true
    package_tests: true
    config_tests: false
    integration_tests: false
  test_paths:
    unit_tests:
      - tests/test_gmail_integration.py
      - tests/test_transaction_parser.py
    package_tests:
      - scripts/test_deployment_package.py
    post_deployment:
      - scripts/test_function.py
```

## Running the Project

1. Local Development:
   ```bash
   # Run local development server
   python src/main.py

   # Run unit tests
   python -m pytest tests/
   ```

2. Testing Deployed Functions:
   ```bash
   # Test function deployment
   python scripts/test_function.py
   python scripts/test_deployment.py
   ```

## Troubleshooting

1. Terraform Issues:
   ```bash
   # Clean Terraform state
   terraform init -reconfigure

   # Import existing resources
   terraform import [resource_address] [resource_id]

   # Remove resource from state
   terraform state rm [resource_address]
   ```

2. Permission Issues:
   ```powershell
   # Verify GCloud login
   gcloud auth list

   # Check application default credentials
   gcloud auth application-default print-access-token
   ```

3. Environment Variables:
   ```powershell
   # Windows
   echo %GOOGLE_APPLICATION_CREDENTIALS%
   echo %GOOGLE_CLOUD_PROJECT%

   # Unix/Linux
   echo $GOOGLE_APPLICATION_CREDENTIALS
   echo $GOOGLE_CLOUD_PROJECT
   ``` 