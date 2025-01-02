"""Authentication Utility for managing credentials"""
import logging
import json
from typing import Dict, Any, Optional
from os import path
from src.utils.config import Config

class AuthUtil:
    """Authentication Utility to aid with retrieval of user credentials"""
    
    # Add mapping between credential file sections and auth systems
    AUTH_SYSTEM_MAP = {
        'google': 'gmail',
        'gmail': 'gmail',
        'firebase': 'firebase',
        'ntlm': 'ntlm'
    }
    
    def __init__(self,
                 local_path: Optional[str] = None,
                 cred_file_nm: Optional[str] = None,
                 auth_system: Optional[str] = None):
        """Initialize AuthUtil with paths"""
        self.config = Config()
        
        self.local_path = local_path or path.dirname(path.dirname(path.dirname(__file__)))
        self.cred_file_nm = cred_file_nm
        
        # Map credential section to auth system
        self.auth_system = auth_system
        self.config_auth_system = self.AUTH_SYSTEM_MAP.get(auth_system)
        
        # Only get auth config if it's a system auth type (not a user ID)
        if self.config_auth_system:
            # Get auth config for the selected system
            auth_config = self.config.get('auth', self.config_auth_system)
            self.service_url = auth_config.get('service_url')
            
            # For Gmail, also get port
            if self.config_auth_system == 'gmail':
                self.port = auth_config.get('port')
        
        self.logger = logging.getLogger(__name__)
    
    def get_local_oauth_credentials(self, email: str) -> Optional[Dict[str, Any]]:
        """Get OAuth credentials from local file"""
        try:
            # Get account mapping from config
            email_to_account = self.config.get('auth', 'gmail', 'email_to_account')
            account_id = email_to_account.get(email)
            
            if not account_id:
                self.logger.warning(f"No account mapping found for email: {email}")
                return None
            
            # Get credentials file path from config
            account_config = self.config.get('auth', 'gmail', 'accounts', account_id)
            if not account_config or 'credentials_file' not in account_config:
                self.logger.warning(f"No credentials file configured for account: {account_id}")
                return None
            
            credentials_file = path.join(self.local_path, account_config['credentials_file'])
            
            # Load credentials from file
            try:
                with open(credentials_file, 'r') as f:
                    credentials = json.load(f)
                self.logger.info(f"Retrieved OAuth credentials from local file for {email}")
                
                # Add email to credentials
                credentials['email'] = email
                return credentials
            except Exception as e:
                self.logger.error(f"Error reading OAuth credentials file {credentials_file}: {str(e)}")
                return None
            
        except Exception as e:
            self.logger.error(f"Error retrieving OAuth credentials: {str(e)}")
            return None
    
    def get_email_for_user(self, user_id: str) -> Optional[str]:
        """Get email address for a user ID from config"""
        try:
            # Look through account configurations
            accounts = self.config.get('auth', 'gmail', 'accounts')
            for account_id, account_data in accounts.items():
                if account_data.get('user_id') == user_id:
                    # Find email from email_to_account mapping
                    email_to_account = self.config.get('auth', 'gmail', 'email_to_account')
                    for email, mapped_account in email_to_account.items():
                        if mapped_account == account_id:
                            return email
            
            self.logger.warning(f"No email mapping found for user ID: {user_id}")
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting email for user: {str(e)}")
            return None



