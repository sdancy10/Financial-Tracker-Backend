# Credentials Directory

This directory contains credential files used by the application. The actual credential files are ignored by git for security, but sample files are provided to show the expected format.

## Files

### Gmail OAuth Credentials
- File pattern: `gmail_oauth_credentials_*.json`
- Sample: `sample_gmail_oauth_credentials.json`
- Purpose: Used for Gmail API access
- Format:
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

### GCP Service Account Key
- File: `service-account-key.json`
- Sample: `sample_service_account_key.json`
- Purpose: Used for GCP service authentication (Firestore, Secret Manager, etc.)
- Format:
```json
{
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key_id": "your-private-key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nyour-private-key\n-----END PRIVATE KEY-----\n",
    "client_email": "service-account-name@your-project-id.iam.gserviceaccount.com",
    "client_id": "your-client-id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/service-account-name%40your-project-id.iam.gserviceaccount.com"
}
```

## Security Notes

1. Never commit actual credential files to git
2. Keep credentials secure and never share them
3. Use environment variables or Secret Manager in production
4. The sample files are for format reference only - they contain dummy values 