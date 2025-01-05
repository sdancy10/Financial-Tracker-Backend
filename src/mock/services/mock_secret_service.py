"""
Mock Secret Manager service for testing.
"""

import os
import sys
import json
from unittest.mock import MagicMock
from google.api_core import exceptions

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

def access_secret_version(request):
    """Mock accessing a secret version"""
    # Extract secret ID from path
    secret_path = request.get('name', '')
    if not secret_path:
        raise exceptions.InvalidArgument('Missing name in request')
    
    parts = secret_path.split('/')
    if len(parts) < 3:
        raise exceptions.InvalidArgument(f'Invalid secret path: {secret_path}')
    
    secret_id = parts[-3]  # Extract secret ID from path
    
    # Create mock OAuth2 credentials with all required fields
    mock_creds = {
        'token': 'mock_token',
        'refresh_token': 'mock_refresh_token',
        'token_uri': 'https://oauth2.googleapis.com/token',
        'client_id': 'mock_client_id',
        'client_secret': 'mock_client_secret',
        'scopes': ['https://www.googleapis.com/auth/gmail.readonly']
    }
    
    # Return mock secret data
    mock_secret = MagicMock()
    mock_secret.payload.data = json.dumps(mock_creds).encode()
    return mock_secret

def create_mock_secret_manager_client():
    """Create a mock Secret Manager client"""
    mock_client = MagicMock()
    mock_client.access_secret_version = access_secret_version
    return mock_client 