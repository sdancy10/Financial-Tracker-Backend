# Terraform Infrastructure Configuration

This directory contains the Terraform configurations for deploying the Financial Tracker Backend infrastructure to Google Cloud Platform. It provides two deployment options: production (`main.tf`) and free tier (`free_tier.tf`).

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

## Configuration Options

### Production Configuration (`main.tf`)
Optimized for production workloads with:
- Multiple instance support
- Higher memory allocations
- More frequent scheduling
- Longer timeouts
- No automatic cleanup

Resource Specifications:
- Cloud Run: 1-10 instances, 256Mi memory
- Cloud Functions: 256MB memory, 9-minute timeout
- Cloud Scheduler: Runs every 10 minutes
- Storage: No quota limits
- Pub/Sub: Standard configuration
- Secret Manager: Multiple secrets

### Free Tier Configuration (`free_tier.tf`)
Optimized to stay within GCP's free tier limits:

1. **Cloud Run (Free Tier Limits: 2M requests/month, 180K vCPU-sec, 360K GiB-sec)**
   - Scales to zero when not in use
   - Single instance maximum
   - 128Mi memory limit
   - Suffix: `-free`

2. **Cloud Functions (Free Tier: 2M invocations/month)**
   - 128MB memory (minimum)
   - 60-second timeout
   - Suffix: `-free`
   - Reduced concurrent executions

3. **Cloud Storage (Free Tier: 5GB/month)**
   - 1GB quota per bucket
   - Files auto-delete after 1 day
   - Suffix: `-free`

4. **Cloud Scheduler**
   - Runs every 12 hours (vs 10 minutes in production)
   - Single retry
   - 60-second timeout
   - Suffix: `-free`

5. **Pub/Sub (Free Tier: 10GB/month)**
   - Minimal message size
   - Suffix: `-free`

6. **Secret Manager (Free Tier: 10K operations)**
   - Minimal secrets
   - Suffix: `-free`

7. **Budget Controls**
   - $1 maximum budget
   - Alerts at 50 cents and 90 cents
   - Automatic notifications

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

3. **Deploy Production**:
   ```bash
   # See what changes will be made
   terraform plan

   # Apply the changes
   terraform apply
   ```

4. **Deploy Free Tier**:
   ```bash
   # Plan free tier changes only
   terraform plan -target=module.free_tier

   # Apply free tier configuration
   terraform apply -target=module.free_tier
   ```

5. **Clean Up**:
   ```bash
   # Remove all resources
   terraform destroy

   # Remove only free tier resources
   terraform destroy -target=module.free_tier
   ```

## Resource Comparison

| Resource          | Production (`main.tf`)      | Free Tier (`free_tier.tf`)    |
|------------------|----------------------------|------------------------------|
| Cloud Run        | 1-10 instances, 256Mi     | 0-1 instances, 128Mi        |
| Cloud Functions  | 256MB, 9m timeout         | 128MB, 1m timeout           |
| Cloud Scheduler  | Every 10 minutes          | Every 12 hours              |
| Storage         | No quota limits           | 1GB per bucket              |
| File Retention   | Permanent                 | 1-day auto-delete           |
| Pub/Sub         | Standard config           | Minimal message size        |
| Secret Manager  | Multiple secrets          | Single secret              |

## Important Notes

1. **Free Tier Limitations**:
   - Suitable for development/testing
   - Limited processing capacity
   - Data auto-cleanup
   - Reduced functionality

2. **Cost Management**:
   - Free tier has strict budget controls
   - Production needs separate budget setup
   - Monitor usage regularly

3. **Deployment Considerations**:
   - Don't run both configurations simultaneously
   - Use different project IDs for prod/free
   - Test thoroughly before production

4. **Security**:
   - Both configs use same security settings
   - IAM permissions are identical
   - Encryption remains enabled

5. **Maintenance**:
   - Free tier requires less maintenance
   - Auto-cleanup reduces manual work
   - Monitoring still recommended 