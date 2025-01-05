"""Deploy credentials to GCP Secret Manager"""
import os
import sys
import json
import base64
import logging
import subprocess
from pathlib import Path

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config

class CredentialsDeployer:
    def __init__(self):
        # Set up logging
        logging.basicConfig(level=logging.DEBUG)
        self.logger = logging.getLogger(__name__)
        
        # Initialize config and credentials manager
        self.config = Config()
        self.project_id = self.config.get('project', 'id')
        self.cred_manager = CredentialsManager(self.project_id, self.config)
        
        # Add Terraform state checking
        self.terraform_state = self._load_terraform_state()
        self.is_terraform_managed = self.terraform_state is not None
        self.is_free_tier = self._check_if_free_tier()
    
    def _load_terraform_state(self):
        """Load Terraform state if it exists"""
        try:
            terraform_dir = Path(__file__).parent.parent / "terraform"
            if not terraform_dir.exists():
                return None
                
            # Try to get Terraform state
            result = subprocess.run(
                ["terraform", "show", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except Exception as e:
            self.logger.warning(f"Could not load Terraform state: {e}")
            return None
    
    def _check_if_free_tier(self):
        """Check if we're using free tier configuration"""
        if not self.terraform_state:
            return False
            
        # Check for free tier resources in state
        resources = self.terraform_state.get("resources", [])
        return any(r.get("name", "").endswith("-free") for r in resources)
    
    def _get_terraform_secret(self, secret_id):
        """Get secret details from Terraform state"""
        if not self.terraform_state:
            return None
            
        resources = self.terraform_state.get("resources", [])
        for resource in resources:
            if resource.get("type") == "google_secret_manager_secret":
                instances = resource.get("instances", [{}])
                for instance in instances:
                    attrs = instance.get("attributes", {})
                    if attrs.get("secret_id") == secret_id:
                        return attrs
        return None
    
    def _has_manual_updates(self) -> bool:
        """Check if there are manual updates needed beyond Terraform"""
        try:
            # Get Gmail accounts from config
            gmail_accounts = self.config.get('auth', 'gmail', 'accounts')
            email_to_account = self.config.get('auth', 'gmail', 'email_to_account')
            
            if not gmail_accounts or not email_to_account:
                return False
            
            # Check each user's credentials
            for email, account_name in email_to_account.items():
                if account_name in gmail_accounts:
                    account_config = gmail_accounts[account_name]
                    user_id = account_config['user_id']
                    
                    # Create secret ID
                    secret_id = f"gmail-credentials-{user_id.lower()}-{base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')}"
                    if self.is_free_tier:
                        secret_id += "-free"
                    
                    # If any secret is not in Terraform state, we need manual updates
                    if not self._get_terraform_secret(secret_id):
                        self.logger.info(f"Found manual update needed for {secret_id}")
                        return True
            
            return False
            
        except Exception as e:
            self.logger.warning(f"Error checking for manual updates: {e}")
            return True  # Assume updates needed on error
    
    def deploy(self):
        """Deploy credentials to GCP Secret Manager"""
        try:
            # Check if we should proceed with deployment
            if self.is_terraform_managed:
                self.logger.info("Credentials are managed by Terraform, checking for manual updates...")
                if not self._has_manual_updates():
                    self.logger.info("No manual updates needed, credentials are managed by Terraform")
                    return True
            
            self.logger.info("\n=== Deploying Credentials to Secret Manager ===")
            
            # Deploy user-specific Gmail credentials from config
            gmail_accounts = self.config.get('auth', 'gmail', 'accounts')
            email_to_account = self.config.get('auth', 'gmail', 'email_to_account')
            
            if not gmail_accounts or not email_to_account:
                self.logger.info("No Gmail accounts configured, skipping credential deployment")
                return True
            
            # Deploy credentials for each configured user
            for email, account_name in email_to_account.items():
                if account_name in gmail_accounts:
                    account_config = gmail_accounts[account_name]
                    
                    # Load credentials from file
                    cred_file = account_config['credentials_file']
                    try:
                        with open(cred_file, 'r') as f:
                            account_creds = json.load(f)
                            self.logger.debug(f"Loaded credentials for {account_name} from {cred_file}:")
                            self.logger.debug(f"Keys present: {list(account_creds.keys())}")
                    except Exception as e:
                        self.logger.error(f"Error loading credentials for {account_name}: {str(e)}")
                        continue
                    
                    # Get user_id from config
                    user_id = account_config['user_id']
                    
                    try:
                        # Create secret ID
                        secret_id = f"gmail-credentials-{user_id.lower()}-{base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')}"
                        if self.is_free_tier:
                            secret_id += "-free"
                        
                        # Check if secret is managed by Terraform
                        if self.is_terraform_managed and self._get_terraform_secret(secret_id):
                            self.logger.info(f"Secret {secret_id} is managed by Terraform")
                            continue
                        
                        # Store Gmail credentials in Secret Manager
                        self.cred_manager.store_user_gmail_credentials(
                            user_id=user_id,
                            email=email,
                            username=account_creds['client_id'],
                            password=account_creds['client_secret'],
                            refresh_token=account_creds['refresh_token']
                        )
                        self.logger.info(f"Deployed credentials for user {user_id} ({email})")
                        
                    except Exception as e:
                        self.logger.error(f"Error deploying credentials for {user_id} ({email}): {str(e)}")
            
            self.logger.info("\nSuccessfully deployed all credentials")
            return True
            
        except Exception as e:
            self.logger.error(f"\nError deploying credentials: {str(e)}")
            return False

def main():
    deployer = CredentialsDeployer()
    success = deployer.deploy()
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main() 