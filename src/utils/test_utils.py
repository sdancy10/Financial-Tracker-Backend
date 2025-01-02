"""Utilities for testing that leverage the auth configuration."""

from typing import Dict, Optional, Tuple
from src.utils.config import Config


def get_test_user(config: Optional[Config] = None) -> Tuple[str, str, str]:
    """Get the first configured user from auth config for testing.
    
    Returns:
        Tuple of (user_id, email, account_name)
    """
    if not config:
        config = Config()
    
    auth_config = config.get('auth', 'gmail')
    email_to_account = auth_config.get('email_to_account', {})
    
    # Get first email and account name
    email = next(iter(email_to_account.keys()))
    account_name = email_to_account[email]
    
    # Get user ID from account config
    account_config = auth_config['accounts'][account_name]
    user_id = account_config['user_id']
    
    return user_id, email, account_name


def get_test_users(config: Optional[Config] = None) -> Dict[str, Dict[str, str]]:
    """Get all configured users from auth config for testing.
    
    Returns:
        Dict mapping account names to dict with keys: user_id, email
    """
    if not config:
        config = Config()
    
    auth_config = config.get('auth', 'gmail')
    email_to_account = auth_config.get('email_to_account', {})
    accounts = auth_config.get('accounts', {})
    
    test_users = {}
    for email, account_name in email_to_account.items():
        account_config = accounts[account_name]
        test_users[account_name] = {
            'user_id': account_config['user_id'],
            'email': email
        }
    
    return test_users 