"""
Mock implementations of Secret Manager API responses and structures.
"""

import os
import sys
import json
from typing import Dict, Any
from google.api_core import exceptions

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

class MockSecretVersion:
    """Mock Secret Version response"""
    def __init__(self, payload: str):
        self.payload = MockPayload(payload)

class MockPayload:
    """Mock Secret Payload"""
    def __init__(self, data: str):
        self._data = data
    
    def decode(self) -> str:
        return self._data

def create_mock_secret_version(secret_data: Dict[str, Any]) -> MockSecretVersion:
    """Create a mock secret version response"""
    return MockSecretVersion(json.dumps(secret_data))

def create_mock_secret_not_found(secret_id: str) -> exceptions.NotFound:
    """Create a mock NotFound error"""
    return exceptions.NotFound(f'Secret [{secret_id}] not found') 