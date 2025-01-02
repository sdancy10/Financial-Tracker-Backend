# Setup Instructions

This document provides detailed setup and deployment instructions for the Financial Transaction Tracker. For a high-level overview of the system architecture and components, please see [ARCHITECTURE.md](ARCHITECTURE.md).

## Prerequisites

- Python 3.9 or higher
- Google Cloud SDK
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

## GCloud CLI Setup (Windows)

1. Install Google Cloud SDK:
   - Download from: https://cloud.google.com/sdk/docs/install
   - Run the installer and follow the prompts
   - Restart your terminal/PowerShell after installation

2. Initialize GCloud:
   ```powershell
   # Login to your Google Account
   gcloud auth login

   # Set your project
   gcloud config set project YOUR_PROJECT_ID
   ```

3. Enable Required APIs:
   ```powershell
   # Enable Secret Manager API
   gcloud services enable secretmanager.googleapis.com

   # Enable Cloud Storage API
   gcloud services enable storage.googleapis.com

   # Enable Cloud Functions API
   gcloud services enable cloudfunctions.googleapis.com

   # Enable Cloud Scheduler API
   gcloud services enable cloudscheduler.googleapis.com
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

5. Add required IAM policies:
   ```powershell
   # Add Secret Manager Admin role
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID `
       --member="serviceAccount:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com" `
       --role="roles/secretmanager.admin"

   # Add Storage Admin role
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID `
       --member="serviceAccount:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com" `
       --role="roles/storage.admin"

   # Add Cloud Functions Developer role
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID `
       --member="serviceAccount:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com" `
       --role="roles/cloudfunctions.developer"

   # Add Cloud Scheduler Admin role
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID `
       --member="serviceAccount:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com" `
       --role="roles/cloudscheduler.admin"
   ```

6. Place the downloaded service account key in:
   ```
   credentials/service-account-key.json
   ```

7. Create and configure environment files:
   - Copy `.env.example` to `.env`
   - Update `.env` with your settings:
   ```
   GOOGLE_CLOUD_PROJECT=YOUR_PROJECT_ID
   GOOGLE_APPLICATION_CREDENTIALS=credentials/service-account-key.json
   PROJECT_ID=YOUR_PROJECT_ID
   ENCRYPTION_KEY=YOUR_ENCRYPTION_KEY
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
   - Run configured tests
   - Deploy necessary cloud resources

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
    config_tests: true
    integration_tests: true
  test_paths:
    unit_tests:
      - "tests/test_transaction_parser.py"
      - "tests/test_gmail_integration.py"
    package_tests:
      - "scripts/test_deployment_package.py"
    config_tests:
      - "scripts/test_deployment.py"
    integration_tests:
      - "scripts/test_function.py"
```

### Deployment Options

The project supports multiple deployment configurations:

1. Function Deployment:
   - Individual functions can be deployed using `scripts/deploy_functions.py`
   - Functions are automatically versioned
   - Supports rollback to previous versions

2. Storage Deployment:
   - Storage buckets are managed via `scripts/deploy_storage.py`
   - Supports bucket creation and configuration

3. Credentials Management:
   - Secure credential deployment via `scripts/deploy_credentials.py`
   - Supports encryption and secure storage

4. Scheduler Configuration:
   - Cloud Scheduler jobs can be managed via `scripts/deploy_scheduler.py`
   - Supports cron-style scheduling

## Running the Project

1. Local Development:
   ```bash
   # Run local development server
   python src/main.py

   # Run unit tests
   python -m pytest tests/test_transaction_parser.py
   python -m pytest tests/test_gmail_integration.py

   # Run all tests in tests directory
   python -m pytest tests/
   ```

2. Testing Deployed Functions:
   ```bash
   # Test function deployment
   python scripts/test_function.py
   python scripts/test_deployment.py

   # Test scheduled function
   python scripts/test_function_from_scheduler.py

   # Test transaction parsing
   python scripts/test_transaction_parse.py
   ```

## Troubleshooting

1. Permission Issues:
   ```powershell
   # Verify GCloud login
   gcloud auth list

   # Check service account roles
   gcloud projects get-iam-policy YOUR_PROJECT_ID `
       --flatten="bindings[].members" `
       --format='table(bindings.role)' `
       --filter="bindings.members:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com"
   ```

2. Environment Variables:
   ```powershell
   # Windows
   echo %GOOGLE_APPLICATION_CREDENTIALS%
   echo %GOOGLE_CLOUD_PROJECT%

   # Unix/Linux
   echo $GOOGLE_APPLICATION_CREDENTIALS
   echo $GOOGLE_CLOUD_PROJECT
   ```

3. Common Issues:
   - **Missing Dependencies**: Run `pip install -r requirements.txt`
   - **API Not Enabled**: Check GCP Console > APIs & Services
   - **Invalid Credentials**: Verify service account key path
   - **Deployment Failures**: Check Cloud Functions logs in GCP Console

## Maintenance

1. Updating Dependencies:
   ```bash
   pip freeze > requirements.txt
   ```

2. Cleaning Up:
   ```bash
   # Remove virtual environment
   rm -rf venv/

   # Clean Python cache
   find . -type d -name "__pycache__" -exec rm -r {} +
   ```

3. Monitoring:
   - Check Cloud Functions logs in GCP Console
   - Monitor Cloud Scheduler job executions
   - Review Storage bucket access logs 