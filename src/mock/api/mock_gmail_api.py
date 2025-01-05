"""
Mock implementations of Gmail API responses and structures.
Loads real transaction messages that were previously validated in production.
"""

import os
import sys
from typing import Dict, Any, List, Optional

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

def get_mock_message_by_template(template_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a mock message for a specific template.
    
    Args:
        template_name (str): The name of the template to get a mock message for.
    
    Returns:
        Optional[Dict[str, Any]]: The mock message if found, None otherwise.
    """
    try:
        from src.mock.api.mock_messages import MOCK_MESSAGES
        return MOCK_MESSAGES.get(template_name)
    except ImportError:
        return None

def get_all_mock_messages() -> Dict[str, Dict[str, Any]]:
    """
    Get all available mock messages.
    
    Returns:
        Dict[str, Dict[str, Any]]: Dictionary of template names to mock messages.
    """
    try:
        from src.mock.api.mock_messages import MOCK_MESSAGES
        return MOCK_MESSAGES
    except ImportError:
        return {}

def get_mock_messages_list() -> List[str]:
    """
    Get a list of all available mock message template names.
    
    Returns:
        List[str]: List of template names.
    """
    try:
        from src.mock.api.mock_messages import MOCK_MESSAGES
        return list(MOCK_MESSAGES.keys())
    except ImportError:
        return []