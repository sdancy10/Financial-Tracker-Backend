# Credential Management Guide

This guide explains how to manage credentials for the Financial Transaction Tracker. The project uses an automated approach that starts with local credentials during development and automatically migrates them to GCP Secret Manager during setup.

## Initial Development Setup

### Service Account Credentials

1. Create a service account in GCP Console:
   ```bash
   # Create service account
   gcloud iam service-accounts create python-etl \
       --display-name="Python ETL Service Account"

   # Download key
   gcloud iam service-accounts keys create credentials/service-account-key.json \
       --iam-account=python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

2. Grant necessary permissions:
   ```bash
   # Grant roles
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
       --member="serviceAccount:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
       --role="roles/secretmanager.admin"
   ```

### Gmail OAuth2 Credentials

1. Create OAuth2 credentials in Google Cloud Console:
   - Go to APIs & Services > Credentials
   - Create OAuth 2.0 Client ID
   - Download JSON and save as `credentials/gmail_oauth_credentials.json`

2. Generate user tokens:
   ```bash
   # Run OAuth setup script
   python scripts/setup_oauth.py
   ```
   This creates user-specific token files: `gmail_oauth_credentials_[user].json`

   Each user's OAuth credentials file should contain:
   ```json
   {
       "client_id": "your-client-id.apps.googleusercontent.com",
       "client_secret": "your-client-secret",
       "refresh_token": "your-refresh-token",
       "token_uri": "https://oauth2.googleapis.com/token",
       "scopes": [
           "https://www.googleapis.com/auth/gmail.readonly",
           "https://www.googleapis.com/auth/gmail.modify"
       ]
   }
   ```

## Deployment to GCP Secret Manager

The project provides scripts to manage credentials in GCP Secret Manager:

1. **Deploy Credentials**:
   ```bash
   # Deploy all credentials to Secret Manager
   python scripts/deploy_credentials.py
   ```
   This script:
   - Creates secrets with appropriate naming convention
   - Deploys service account and OAuth credentials
   - Properly encodes all fields including refresh tokens
   - Maintains consistent secret structure across deployments

2. **List Secrets**:
   ```bash
   # View all secrets and their contents
   python scripts/list_secrets.py
   ```
   This shows:
   - All deployed secrets
   - Current values and fields
   - Verification of required fields

3. **Remove Secrets**:
   ```bash
   # Remove secrets if needed
   python scripts/remove_secrets.py
   ```
   Use this to:
   - Clean up old secrets
   - Prepare for fresh deployment
   - Remove specific secrets

## Secret Structure

Gmail credentials in Secret Manager follow this structure:
```json
{
    "username": "client-id.apps.googleusercontent.com",
    "password": "client-secret",
    "email": "user@gmail.com",
    "client_id": "client-id.apps.googleusercontent.com",
    "client_secret": "client-secret",
    "refresh_token": "oauth-refresh-token",
    "token_uri": "https://oauth2.googleapis.com/token",
    "scopes": [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify"
    ]
}
```

## Production Credential Management

After deployment, credentials are managed entirely through GCP Secret Manager:

### Viewing Credentials
```bash
# List all secrets
python scripts/list_secrets.py

# Or use gcloud
gcloud secrets list
gcloud secrets versions access latest --secret="SECRET_NAME"
```

### Managing Credentials
```bash
# Deploy/update credentials
python scripts/deploy_credentials.py

# Remove credentials
python scripts/remove_secrets.py
```

## Security Best Practices

1. **Access Control**:
   - Use minimal IAM roles
   - Rotate service account keys regularly
   - Use separate service accounts for development/production

2. **Secret Management**:
   - Never commit credentials to version control
   - Use Secret Manager in production
   - Implement secret rotation
   - Verify all required fields are present after deployment

3. **OAuth Security**:
   - Use separate OAuth credentials per environment
   - Regularly audit authorized applications
   - Implement token refresh monitoring
   - Ensure refresh tokens are properly stored and secured

## Troubleshooting

### Common Issues

1. **Missing Fields in Secrets**:
   ```bash
   # List secrets to verify all fields
   python scripts/list_secrets.py
   
   # If fields are missing, redeploy credentials
   python scripts/remove_secrets.py
   python scripts/deploy_credentials.py
   ```

2. **OAuth Token Issues**:
   ```bash
   # Force token refresh
   python scripts/setup_oauth.py --force-refresh
   
   # Verify token in Secret Manager
   python scripts/list_secrets.py
   ```

3. **Secret Manager Access**:
   ```bash
   # Verify IAM permissions
   gcloud projects get-iam-policy YOUR_PROJECT_ID \
       --flatten="bindings[].members" \
       --format='table(bindings.role)' \
       --filter="bindings.members:python-etl@YOUR_PROJECT_ID.iam.gserviceaccount.com"
   ```

## Environment Variables

For local development:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="credentials/service-account-key.json"
export USE_SECRET_MANAGER="false"  # Set to "true" for production
```

For production (automatically set during deployment):
```bash
export USE_SECRET_MANAGER="true"
# GOOGLE_APPLICATION_CREDENTIALS managed by Cloud Functions environment
``` 