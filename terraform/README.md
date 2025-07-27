# Terraform Infrastructure Configuration

This directory contains the Terraform configurations for deploying the Financial Tracker Backend infrastructure to Google Cloud Platform.

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

## Configuration

The infrastructure deployment is controlled by the `features` section in your `config.yaml`:

```yaml
features:
  enabled_services:
    cloud_run: false      # Cloud Run API and services
    cloud_functions: true # Cloud Functions API and services
    storage: true        # Cloud Storage API and buckets
    pubsub: true        # Pub/Sub API and topics
    scheduler: true     # Cloud Scheduler API and jobs
    firestore: true     # Firestore API
    secrets: true       # Secret Manager API and secrets
```

## Resource Configuration

1. **Cloud Functions**
   - Name: `transaction-processor`
   - Runtime: Python 3.10
   - Memory: Configurable via config.yaml (default: 512MB)
   - Timeout: 540s
   - Source: Uploaded from local directory

2. **Cloud Storage**
   - Buckets:
     - Data bucket: For storing processed data
     - ML artifacts bucket: For machine learning models
     - Functions bucket: For Cloud Functions code
   - Location: US-CENTRAL1
   - Uniform bucket-level access: Enabled

3. **Cloud Scheduler**
   - Job name: `process-scheduled-transactions`
   - Schedule: Every 10 minutes
   - Timezone: America/Chicago
   - Retry policy: 3 attempts
   - Timeout: 540s

4. **Secret Manager**
   - Secrets:
     - Default credentials
     - Firebase credentials
   - Automatic replication
   - Customer-managed encryption keys

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
   # Apply the changes
   terraform apply
   ```

5. **Clean Up**:
   ```bash
   # Remove all resources
   terraform destroy
   ```

## Managing Existing Resources

If you have existing resources that were created manually or through scripts:

1. **Import Resources**:
   ```bash
   # Import Cloud Function
   terraform import "google_cloudfunctions_function.transaction_processor[0]" "projects/YOUR_PROJECT_ID/locations/us-central1/functions/transaction-processor"

   # Import Storage Buckets
   terraform import "google_storage_bucket.data_bucket[0]" "YOUR_PROJECT_ID-data"
   terraform import "google_storage_bucket.ml_artifacts_bucket[0]" "YOUR_PROJECT_ID-ml-artifacts"
   terraform import "google_storage_bucket.functions_bucket[0]" "YOUR_PROJECT_ID-functions"

   # Import Pub/Sub Topic
   terraform import "google_pubsub_topic.scheduled_transactions[0]" "projects/YOUR_PROJECT_ID/topics/scheduled-transactions"

   # Import Cloud Scheduler Job
   terraform import "google_cloud_scheduler_job.transaction_scheduler[0]" "projects/YOUR_PROJECT_ID/locations/us-central1/jobs/process-scheduled-transactions"

   # Import Secrets
   terraform import "google_secret_manager_secret.default_credentials[0]" "projects/YOUR_PROJECT_ID/secrets/google-credentials-default"
   terraform import "google_secret_manager_secret.firebase_credentials[0]" "projects/YOUR_PROJECT_ID/secrets/firebase-credentials-default"
   ```

2. **Remove from State**:
   ```bash
   # Remove resource from state if needed
   terraform state rm [resource_address]
   ```

## Integration with Setup Scripts

The setup scripts (`setup.bat` and `setup.sh`) will:
1. Check for Terraform installation
2. Initialize Terraform if available
3. Plan and apply changes with user confirmation
4. Handle application deployment after infrastructure is ready

## Important Notes

1. **State Management**:
   - Keep `terraform.tfstate` secure
   - Consider using remote state storage
   - Don't commit state files to version control

2. **Resource Naming**:
   - Resources use project ID in names
   - Names are consistent with existing resources
   - Follow GCP naming conventions

3. **Security**:
   - Use service account authentication
   - Enable audit logging
   - Follow least privilege principle

4. **Cost Management**:
   - Monitor resource usage
   - Set up budget alerts
   - Clean up unused resources 