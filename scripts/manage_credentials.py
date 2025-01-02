from google.cloud import secretmanager
import argparse
import json
import os

def create_user_credentials(project_id: str, user_id: str, email: str, credentials_file: str):
    """Create or update user-specific Gmail credentials"""
    client = secretmanager.SecretManagerServiceClient()
    
    # Read credentials file
    with open(credentials_file, 'r') as f:
        secret_data = f.read()
    
    # Create secret name
    secret_id = f"gmail-credentials-{user_id}-{email}"
    parent = f"projects/{project_id}"
    
    try:
        # Try to create new secret
        secret = client.create_secret(
            request={
                "parent": parent,
                "secret_id": secret_id,
                "secret": {"replication": {"automatic": {}}}
            }
        )
    except Exception:
        # Secret might already exist
        secret = client.get_secret(name=f"{parent}/secrets/{secret_id}")
    
    # Add new version
    client.add_secret_version(
        request={
            "parent": secret.name,
            "payload": {"data": secret_data.encode("UTF-8")}
        }
    )
    
    print(f"Successfully stored credentials for user {user_id} with email {email}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Manage user Gmail credentials')
    parser.add_argument('--project-id', required=True, help='GCP Project ID')
    parser.add_argument('--user-id', required=True, help='User ID')
    parser.add_argument('--email', required=True, help='User Gmail address')
    parser.add_argument('--credentials-file', required=True, help='Path to credentials JSON file')
    
    args = parser.parse_args()
    create_user_credentials(args.project_id, args.user_id, args.email, args.credentials_file) 