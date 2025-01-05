"""
Common test utilities and decorators.
"""

import os
import sys
from functools import wraps
from unittest.mock import patch, MagicMock
from typing import Dict, Any, Callable, Optional, Tuple

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from src.mock.models.mock_credentials import (
    create_mock_oauth2_credentials,
    MockServiceAccountCredentials,
    MockOAuth2Credentials
)
from src.mock.services.mock_gmail_service import create_mock_gmail_service
from src.mock.services.mock_secret_service import create_mock_secret_manager_client
from src.mock.utils.mock_environment import create_mock_env_vars, mock_getenv

# Re-export unittest.mock utilities
__all__ = ['mock_credentials', 'get_user_credentials', 'patch', 'MagicMock']

def get_user_credentials(email: str = None, config: Any = None) -> Tuple[str, str, Dict[str, Any]]:
    """Get user credentials for testing
    
    Args:
        email: Optional email address to get credentials for
        config: Optional config object (if not provided, will use default test config)
        
    Returns:
        Tuple of (user_id, email, credentials)
    """
    from src.utils.config import Config
    from src.utils.test_utils import get_test_user
    from src.utils.credentials_manager import CredentialsManager
    
    if config is None:
        config = Config()
    
    # Get test user from config if email not provided
    if not email:
        user_id, email, _ = get_test_user(config)
    else:
        # Look up user ID for the provided email
        auth_config = config.get('auth', 'gmail')
        email_to_account = auth_config.get('email_to_account', {})
        accounts = auth_config.get('accounts', {})
        account_name = email_to_account.get(email)
        if not account_name:
            raise ValueError(f"Email {email} not found in config.yaml auth.gmail.email_to_account")
        account_config = accounts.get(account_name)
        if not account_config:
            raise ValueError(f"Account {account_name} not found in config.yaml auth.gmail.accounts")
        user_id = account_config.get('user_id')
    
    # Create mock credentials
    mock_creds = create_mock_oauth2_credentials()
    
    # Mock environment variables
    env_vars = create_mock_env_vars()
    
    # Mock environment and credentials manager
    with patch.dict(os.environ, env_vars), \
         patch('os.getenv', side_effect=mock_getenv(env_vars)), \
         patch('google.auth.default', side_effect=Exception("No default credentials")), \
         patch('google.oauth2.credentials.Credentials', return_value=MockOAuth2Credentials()), \
         patch('google.oauth2.service_account.Credentials', MockServiceAccountCredentials), \
         patch('src.utils.credentials_manager.secretmanager') as mock_secretmanager, \
         patch('googleapiclient.discovery.build') as mock_build:
        
        # Mock Secret Manager client
        mock_secretmanager.SecretManagerServiceClient.return_value = create_mock_secret_manager_client()
        
        # Mock Gmail service
        mock_build.return_value = create_mock_gmail_service()
        
        # Initialize credentials manager without real service account
        cred_manager = CredentialsManager(config.get('project', 'id'), config)
        
        # Get Gmail credentials
        creds = cred_manager.get_user_gmail_credentials(user_id, email)
        return user_id, email, creds

def mock_credentials(func: Callable) -> Callable:
    """Decorator to mock credentials for testing"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Create mock credentials
        mock_creds = create_mock_oauth2_credentials()
        
        # Set up environment variables
        env_vars = create_mock_env_vars()
        
        # Create a mock credentials instance
        mock_credentials_instance = MagicMock()
        for key, value in mock_creds.items():
            setattr(mock_credentials_instance, key, value)
        mock_credentials_instance.refresh = MagicMock()
        mock_credentials_instance.has_scopes = MagicMock(return_value=True)
        mock_credentials_instance.to_json = MagicMock(return_value=mock_creds)
        
        with patch.dict(os.environ, env_vars), \
             patch('os.getenv', side_effect=mock_getenv(env_vars)), \
             patch('google.auth.default', side_effect=Exception("No default credentials")), \
             patch('src.utils.credentials_manager.Credentials', return_value=mock_credentials_instance), \
             patch('google.oauth2.service_account.Credentials', MockServiceAccountCredentials), \
             patch('src.utils.credentials_manager.secretmanager') as mock_secretmanager, \
             patch('googleapiclient.discovery.build') as mock_build:
            
            # Mock Secret Manager client
            mock_secretmanager.SecretManagerServiceClient.return_value = create_mock_secret_manager_client()
            
            # Mock Gmail service
            mock_build.return_value = create_mock_gmail_service()
            
            return func(*args, **kwargs)
    
    return wrapper 