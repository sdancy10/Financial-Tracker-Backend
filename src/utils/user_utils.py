from typing import Optional, Dict
from .config import load_config

def get_user_id_by_email(email: str) -> Optional[str]:
    """Get user ID from email address using config"""
    config = load_config()
    email_to_account = config['auth']['gmail']['email_to_account']
    
    if email in email_to_account:
        account_name = email_to_account[email]
        return config['auth']['gmail']['accounts'][account_name]['user_id']
    return None

def get_default_test_account() -> Dict[str, str]:
    """Get default test account (first account in config)"""
    config = load_config()
    accounts = config['auth']['gmail']['accounts']
    # Get first account in config
    default_account = next(iter(accounts.items()))
    return {
        'account_name': default_account[0],
        'user_id': default_account[1]['user_id'],
        'credentials_file': default_account[1]['credentials_file']
    } 