"""List secrets stored in GCP Secret Manager"""
import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config

def list_secrets():
    """List secrets from GCP Secret Manager"""
    try:
        print("\n=== Stored Secrets in GCP Secret Manager ===")
        
        # Initialize config and credentials manager
        config = Config()
        project_id = config.get('project', 'id')
        cred_manager = CredentialsManager(project_id, config)
        
        # List of secret IDs to check
        secret_ids = [
            'gmail_credentials_5ozfugtsn0g1vaea6vnphvc51zq2_c2RhbmN5LjEwQGdtYWlsLmNvbQ',  # sdancy
            'gmail_credentials_ader8rs94npmpdayghqqpi3iwm13_Y2xhaXJlamFibG9uc2tpQGdtYWlsLmNvbQ'  # claire
        ]
        
        # Try to retrieve each secret
        for secret_id in secret_ids:
            try:
                creds = cred_manager.get_secret(secret_id)
                print(f"\nSecret ID: {secret_id}")
                print("Contents:")
                for key, value in creds.items():
                    # Mask sensitive values
                    if key in ['password', 'client_secret', 'refresh_token']:
                        value = '*' * 8
                    print(f"  {key}: {value}")
            except Exception as e:
                print(f"\nError retrieving {secret_id}: {str(e)}")
        
    except Exception as e:
        print(f"\nError listing secrets: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    list_secrets() 