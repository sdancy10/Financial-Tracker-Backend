"""Remove secrets from GCP Secret Manager"""
import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from google.cloud import secretmanager
from src.utils.config import Config

def remove_secrets():
    """Remove Gmail credentials from Secret Manager"""
    try:
        print("\n=== Removing Secrets from GCP Secret Manager ===")
        
        # Initialize config
        config = Config()
        project_id = config.get('project', 'id')
        client = secretmanager.SecretManagerServiceClient()
        
        # List of secret IDs to remove
        secret_ids = [
            'gmail_credentials_5ozfugtsn0g1vaea6vnphvc51zq2_c2RhbmN5LjEwQGdtYWlsLmNvbQ',  # sdancy
            'gmail_credentials_ader8rs94npmpdayghqqpi3iwm13_Y2xhaXJlamFibG9uc2tpQGdtYWlsLmNvbQ'  # claire
        ]
        
        # Remove each secret
        for secret_id in secret_ids:
            try:
                secret_path = f"projects/{project_id}/secrets/{secret_id}"
                client.delete_secret(request={"name": secret_path})
                print(f"✓ Removed secret: {secret_id}")
            except Exception as e:
                print(f"Error removing secret {secret_id}: {str(e)}")
        
        print("\n✓ Successfully removed all secrets")
        
    except Exception as e:
        print(f"\nError removing secrets: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    remove_secrets() 