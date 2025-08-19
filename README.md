# Financial Transaction Tracker

A serverless application that automatically processes financial transaction emails and provides a structured way to track, categorize, and analyze your financial data.

## Features

- 📧 Automatic email processing for financial transactions
- 🏷️ Smart transaction categorization
- 📊 Transaction analysis and reporting
- 🔒 Secure credential management with GCP Secret Manager
- 🔄 Automated scheduled processing
- 🎯 Template-based transaction parsing
- 🏗️ Infrastructure as Code with Terraform
- 🧪 Mock data generation for testing
- 🆔 Email API ID tracking
- ✨ Advanced template matching system
- 🤖 ML-powered transaction categorization

## Documentation

- [Architecture Overview](ARCHITECTURE.md) - System design and component interactions
- [Setup Guide](SETUP.md) - Detailed setup and deployment instructions
- [Credential Management](CREDENTIAL_MANAGEMENT.md) - Guide for managing OAuth and service account credentials
- [Testing Guide](TESTING.md) - Comprehensive testing and mock data generation guide

## Quick Start

1. **Prerequisites**
   - Python 3.10+
   - Google Cloud SDK
   - Terraform
   - Active Google Cloud Project
   - Gmail API access

2. **Initial Setup**
   ```bash
   # Clone the repository
   git clone <repository-url>
   cd financial-tracker-backend

   # Copy configuration file
   cp config.yaml.example config.yaml
   # Edit config.yaml with your settings

   # Deploy backend (Windows)
   scripts/setup.bat
   # OR for Unix/Linux
   chmod +x scripts/setup.sh
   ./scripts/setup.sh
   ```

3. **Configuration**
   - Update `config.yaml` with your settings
   - Configure enabled services in the `features` section
   - Set up OAuth credentials
   - Deploy credentials to GCP Secret Manager

For detailed setup instructions, see [SETUP.md](SETUP.md).

## Development

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-test.txt  # For testing dependencies

# Configure your settings
cp config.yaml.example config.yaml
# Edit config.yaml with your settings (required for mock data generation)

# Generate mock data for testing (replace with your values)
python scripts/generate_mock_template_messages.py \
    --email your.email@example.com \
    --start-date 2024-01-01

# Run tests
python -m pytest tests/  # Most tests use mock credentials automatically
python -m pytest tests/test_gmail_integration.py  # Requires real Gmail credentials

# Run local server
python src/main.py
```

> **Note**: Most tests use mock credentials and can run without any additional setup. Only Gmail API integration tests require real credentials configured in config.yaml. The mock data generation script requires a valid email address from your config.yaml to generate realistic test data.

## ML Model Management

**Important**: Activate your virtual environment before working with Python model script files.

### Model Training and Deployment

```bash
# Train model and save artifacts for Cloud Function inference (default)
python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3

# Deploy only to Vertex AI (optional)
python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 --deploy-target vertex_ai

# Test a specific joblib model locally
python scripts/ml_training_workflow.py --project-id shanedancy-9f2a3 --train-only
```

### Model Testing

```bash
# Test the model using GCP endpoint (falls back to local joblib version)
scripts/test_endpoint.bat

# Test to confirm the joblib version of the model is loaded correctly as a pipeline
python scripts/test_model_ck_gcp.py
```

### Data Preparation

```bash
# Prepare ML training data based on start/end dates (currently set to >= 2024-01-01 for default users)
scripts/prepare_ml_data_2024.bat
```

### Backend Deployment

```bash
# Deploy the full backend
scripts/setup.bat
```

### Inference Modes

- Default inference mode is via a Cloud Function to reduce costs. Configure in `config.yaml`:

```yaml
ml:
  inference:
    mode: cloud_function  # or vertex_ai or local
    function_url: "https://us-central1-YOUR_PROJECT.cloudfunctions.net/ml-inference-function"
    timeout_seconds: 15
```

- To use Vertex AI endpoint instead, set `mode: vertex_ai`.

- URL resolution (no manual URL needed): If `function_url` is omitted or empty, the service will automatically:
  - use env `ML_INFERENCE_FUNCTION_URL` if set; otherwise
  - construct the default URL `https://{REGION}-{PROJECT}.cloudfunctions.net/{FUNCTION_NAME}` using:
    - `REGION` (env or `project.region` in `config.yaml`),
    - `GOOGLE_CLOUD_PROJECT` (env) or `project.id`,
    - `FUNCTION_NAME` from `ml.inference.function_name` (default `ml-inference-function`) or env `ML_INFERENCE_FUNCTION_NAME`.
  - The provided `function_url` in `config.yaml` still takes precedence when non-empty.


## Support and Troubleshooting

For support:
1. Check the documentation
2. Review existing issues
3. Create a new issue if needed

Common troubleshooting commands:

```bash
# View recent Cloud Function logs
gcloud logging read "resource.type=cloud_function" --limit 10

# View logs for specific message ID
gcloud logging read "resource.type=cloud_function AND textPayload:YOUR_MESSAGE_ID" --limit 10

# View transaction processing failures
gcloud logging read "resource.type=cloud_function AND severity>=WARNING" --limit 10
```

## Infrastructure Management

The application uses Terraform to manage Google Cloud Platform services:
- Cloud Functions for serverless compute
- Firestore for data storage
- Cloud Storage for email archives
- Cloud Scheduler for automated processing
- Secret Manager for secure credentials
- Pub/Sub for event handling

Infrastructure management commands:
```bash
# Initialize Terraform
cd terraform
terraform init

# Plan changes
terraform plan

# Apply changes
terraform apply
```

See [SETUP.md](SETUP.md) for detailed deployment instructions.

## Architecture

The system is built on a serverless architecture using Google Cloud Platform services. Key components:

- Email Processor Function (processes transaction emails)
- Transaction Parser (extracts transaction data)
- Storage Systems (Firestore and Cloud Storage)
- API Function (handles user requests)

For detailed architecture information, see [ARCHITECTURE.md](ARCHITECTURE.md).

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, please:
1. Check the documentation
2. Review existing issues
3. Create a new issue if needed 