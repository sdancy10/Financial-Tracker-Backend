"""
Helper functions for testing template matching functionality.
"""

import os
import sys
from typing import Dict, Optional

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

def get_template_patterns(templates: Dict, template_name: str) -> Dict[str, str]:
    """Get patterns for a specific template
    
    Args:
        templates: Dictionary of all available templates
        template_name: Name of the template to get patterns for
        
    Returns:
        Dictionary of field names to regex patterns
    """
    template = templates.get(template_name)
    if not template:
        return {}
    return {
        'amount': template.get('amount', ''),
        'account': template.get('account', ''),
        'vendor': template.get('vendor', ''),
        'date': template.get('date', '')
    } 