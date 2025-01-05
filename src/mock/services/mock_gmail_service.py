"""
Mock Gmail service for testing.
"""

import os
import sys
import base64

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)

from unittest.mock import MagicMock
from typing import Dict, Any, Optional
from src.mock.api.mock_gmail_api import MOCK_MESSAGES

def create_mock_gmail_service() -> MagicMock:
    """Create a mock Gmail service"""
    # Create mock message with realistic test data
    test_body = """
        <html>
        <body>
        <table>
            <tr>
                <td>You made a $150.00 transaction with AMAZON.COM*DIGITAL</td>
            </tr>
            <tr>
                <td>Chase Sapphire Preferred Card (...4321)</td>
            </tr>
            <tr>
                <td>Merchant:</td>
                <td>AMAZON.COM*DIGITAL</td>
            </tr>
            <tr>
                <td>Date</td>
                <td>Jan 2, 2025 6:33:33 AM ET</td>
            </tr>
        </table>
        </body>
        </html>
    """
    
    mock_message = MagicMock()
    mock_message.execute.return_value = {
        'id': '19416464ae1c66b6',
        'threadId': '19416464ae1c66b6',
        'labelIds': ['INBOX', 'UNREAD', 'Transactions'],
        'snippet': 'You made a transaction with AMAZON.COM*DIGITAL',
        'payload': {
            'headers': [
                {'name': 'From', 'value': 'no-reply@chase.com'},
                {'name': 'Subject', 'value': 'Your $150.00 transaction with AMAZON.COM*DIGITAL'},
                {'name': 'Date', 'value': 'Thu, 2 Jan 2025 06:33:33 +0000'}
            ],
            'body': {
                'data': base64.urlsafe_b64encode(test_body.encode()).decode()
            }
        }
    }
    
    # Create mock messages collection
    mock_messages = MagicMock()
    mock_messages.get.return_value = mock_message
    
    # Create mock users collection
    mock_users = MagicMock()
    mock_users.messages.return_value = mock_messages
    
    # Create mock service
    mock_service = MagicMock()
    mock_service.users.return_value = mock_users
    mock_service._universe_domain = 'googleapis.com'
    
    return mock_service

def set_mock_message_response(service: MagicMock, message_key: str):
    """Set the mock message response for a service"""
    if message_key not in MOCK_MESSAGES:
        raise ValueError(f"Unknown message key: {message_key}")
    
    service.users().messages().get().execute.return_value = MOCK_MESSAGES[message_key] 