"""
Mock credential objects and factories.
"""

import os
import sys
from typing import Dict, Any
from unittest.mock import MagicMock

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

class MockOAuth2Credentials(object):
    """Mock OAuth2 credentials"""
    def __init__(self, token=None, refresh_token=None, token_uri=None, client_id=None, client_secret=None, scopes=None, **kwargs):
        self.token = token or 'mock_token'
        self.refresh_token = refresh_token or 'mock_refresh_token'
        self.token_uri = token_uri or 'https://oauth2.googleapis.com/token'
        self.client_id = client_id or 'mock_client_id'
        self.client_secret = client_secret or 'mock_client_secret'
        self.scopes = scopes or ['https://www.googleapis.com/auth/gmail.readonly']
        self.universe_domain = 'googleapis.com'
        self.expiry = None
        self.expired = False
        self.valid = True
    
    def refresh(self, request):
        """Mock refresh method"""
        self.token = 'refreshed_mock_token'
        self.expired = False
    
    def has_scopes(self, scopes):
        """Mock has_scopes method"""
        return all(scope in self.scopes for scope in scopes)
    
    def to_json(self):
        """Mock to_json method"""
        return {
            'token': self.token,
            'refresh_token': self.refresh_token,
            'token_uri': self.token_uri,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scopes': self.scopes,
            'universe_domain': self.universe_domain
        }

def create_mock_oauth2_credentials() -> Dict[str, Any]:
    """Create mock OAuth2 credentials for testing"""
    # Create mock credentials
    creds = MockOAuth2Credentials()
    
    # Return serializable version
    return creds.to_json()

class MockServiceAccountCredentials:
    """Mock service account credentials"""
    def __init__(self):
        self.project_id = ''
        self.service_account_email = 'test@project.iam.gserviceaccount.com'
        self.universe_domain = 'googleapis.com'
    
    @property
    def signer(self):
        return None
    
    @property
    def signer_email(self):
        return self.service_account_email
    
    @classmethod
    def from_service_account_file(cls, filename, **kwargs):
        """Mock loading credentials from a service account file"""
        return cls() 