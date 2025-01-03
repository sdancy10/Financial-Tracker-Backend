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

## Documentation

- [Architecture Overview](ARCHITECTURE.md) - System design and component interactions
- [Setup Guide](SETUP.md) - Detailed setup and deployment instructions
- [Credential Management](CREDENTIAL_MANAGEMENT.md) - Guide for managing OAuth and service account credentials

## Quick Start

1. **Prerequisites**
   - Python 3.9+
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

   # Run setup script (Windows)
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

# Run tests
python -m pytest tests/

# Run local server
python src/main.py
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