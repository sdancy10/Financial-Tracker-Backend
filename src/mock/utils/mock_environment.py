"""
Mock environment variables for testing.
"""

import os
import sys
from typing import Dict, Any, Optional

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

# Default mock environment variables
DEFAULT_ENV_VARS = {
    'GOOGLE_CLOUD_PROJECT': '',  # Empty for non-GCP environment
    'FUNCTION_TARGET': '',
    'K_SERVICE': '',
    'GOOGLE_API_USE_CLIENT_CERTIFICATE': 'false',
    'GOOGLE_API_USE_MTLS_ENDPOINT': 'never',
    'GOOGLE_CLOUD_UNIVERSE_DOMAIN': 'googleapis.com'
}

def create_mock_env_vars(additional_vars: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Create mock environment variables"""
    env_vars = DEFAULT_ENV_VARS.copy()
    if additional_vars:
        env_vars.update(additional_vars)
    return env_vars

def mock_getenv(env_vars: Dict[str, str]):
    """Create a mock getenv function"""
    def _getenv(key: str, default: Any = None) -> Any:
        return env_vars.get(key, default)
    return _getenv 