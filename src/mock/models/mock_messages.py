"""
Mock message structures for testing.
"""

import os
import sys
from typing import Dict, Any
from datetime import datetime

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

def create_mock_transaction_message(
    amount: float,
    account: str,
    vendor: str,
    date: datetime = None
) -> Dict[str, Any]:
    """Create a mock transaction message"""
    if date is None:
        date = datetime.now()
    
    return {
        'amount': amount,
        'account': account,
        'vendor': vendor,
        'date': date.isoformat(),
        'template_used': 'Chase Payment Sent'  # Default template
    } 