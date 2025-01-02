"""Deploy credentials to GCP Secret Manager"""
import os
import sys
import json
import base64
import logging

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config

def deploy_credentials():
    """Deploy credentials to GCP Secret Manager"""
    try:
        print("\n=== Deploying Credentials to Secret Manager ===")
        
        # Set up logging
        logging.basicConfig(level=logging.DEBUG)
        logger = logging.getLogger(__name__)
        
        # Initialize config and credentials manager
        config = Config()
        project_id = config.get('project', 'id')
        cred_manager = CredentialsManager(project_id, config)
        
        # Initialize from service account credentials
        service_account_path = config.get('gcp', 'service_account_key_path')
        oauth_creds = cred_manager.initialize_from_file(service_account_path)
        
        # Deploy Google credentials
        if oauth_creds:
            cred_manager.store_default_credentials(
                'google',
                oauth_creds['user_nm'],
                oauth_creds['user_pw']
            )
            print("✓ Deployed Google credentials")
        
        # Deploy user-specific credentials from config
        gmail_accounts = config.get('auth', 'gmail', 'accounts')
        email_to_account = config.get('auth', 'gmail', 'email_to_account')
        
        # Deploy credentials for each configured user
        for email, account_name in email_to_account.items():
            if account_name in gmail_accounts:
                account_config = gmail_accounts[account_name]
                
                # Load credentials from file
                cred_file = account_config['credentials_file']
                try:
                    with open(cred_file, 'r') as f:
                        account_creds = json.load(f)
                        logger.debug(f"Loaded credentials for {account_name} from {cred_file}:")
                        logger.debug(f"Keys present: {list(account_creds.keys())}")
                except Exception as e:
                    print(f"Error loading credentials for {account_name}: {str(e)}")
                    continue
                
                # Get user_id from config
                user_id = account_config['user_id']
                
                try:
                    # Create secret ID
                    secret_id = f"gmail_credentials_{user_id.lower()}_{base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')}"
                    
                    # Prepare secret data
                    secret_data = {
                        "username": account_creds['client_id'],
                        "password": account_creds['client_secret'],
                        "email": email,
                        "client_id": account_creds['client_id'],
                        "client_secret": account_creds['client_secret'],
                        "refresh_token": account_creds['refresh_token'],
                        "token_uri": account_creds['token_uri'],
                        "scopes": account_creds['scopes']
                    }
                    logger.debug(f"Deploying secret data for {account_name}:")
                    logger.debug(f"Keys being deployed: {list(secret_data.keys())}")
                    
                    # Store all credentials in Secret Manager
                    success = cred_manager.deploy_to_secret_manager(
                        secret_data=secret_data,
                        secret_id=secret_id
                    )
                    
                    if success:
                        print(f"✓ Deployed credentials for user {user_id} ({email})")
                    else:
                        print(f"Failed to deploy credentials for user {user_id} ({email})")
                        
                except Exception as e:
                    print(f"Error deploying credentials for {user_id} ({email}): {str(e)}")
        
        print("\n✓ Successfully deployed all credentials")
        
    except Exception as e:
        print(f"\nError deploying credentials: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    deploy_credentials() 