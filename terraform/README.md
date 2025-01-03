# Terraform Infrastructure Configuration

This directory contains the Terraform configuration for deploying the Financial Tracker Backend infrastructure to Google Cloud Platform.

## Prerequisites

1. Install Terraform:
   - Windows (using Chocolatey): `choco install terraform`
   - Or download from [Terraform Downloads](https://www.terraform.io/downloads.html)

2. Configure Google Cloud credentials:
   ```bash
   # Set up application default credentials
   gcloud auth application-default login
   ```

3. Make sure your `config.yaml` file is properly configured in the root directory

## Usage

1. **Initialize Terraform**:
   ```bash
   cd terraform
   terraform init
   ```

2. **Format and Validate**:
   ```bash
   # Format configuration
   terraform fmt

   # Validate configuration
   terraform validate
   ```

3. **Plan Changes**:
   ```bash
   # See what changes will be made
   terraform plan
   ```

4. **Apply Changes**:
   ```bash
   # Apply the changes (will prompt for confirmation)
   terraform apply
   ```

5. **Clean Up**:
   ```bash
   # Remove all resources (use with caution!)
   terraform destroy
   ```

## Resources Created

This Terraform configuration manages the following GCP resources:

1. **API Services**:
   - AI Platform
   - Cloud Storage
   - Container Registry
   - Cloud Build
   - Cloud Run
   - Pub/Sub
   - Firestore
   - Secret Manager
   - Cloud Functions
   - Cloud Scheduler

2. **Storage**:
   - Data bucket
   - ML artifacts bucket
   - Functions bucket

3. **Compute**:
   - Cloud Function for transaction processing
   - Cloud Run service for API
   - Cloud Scheduler job

4. **Messaging**:
   - Pub/Sub topic for transaction processing

5. **Security**:
   - Secret Manager secrets for credentials
   - IAM configurations

## Outputs

After applying the configuration, you'll get:
- Function URL
- Cloud Run URL
- Storage bucket names

## Important Notes

1. Always review the plan before applying changes
2. Be careful with `terraform destroy` as it will remove ALL resources
3. Keep your `config.yaml` up to date
4. Make sure you have appropriate GCP permissions
5. Consider using a remote backend for state management in production 