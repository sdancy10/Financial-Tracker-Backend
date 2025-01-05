"""
Synthetic Gmail API responses for testing edge cases.
These messages are artificially created and should only be used for testing
specific scenarios that are hard to capture from production.
"""

import base64
from typing import Dict, Any, List
from unittest.mock import MagicMock

def create_mock_message(subject: str, body: str, from_addr: str, date: str) -> Dict[str, Any]:
    """
    Create a synthetic Gmail message object for testing.
    
    Args:
        subject: Email subject line
        body: Email body content
        from_addr: Sender's email address
        date: Email date string
        
    Returns:
        Dict matching Gmail API message format
    """
    return {
        'id': '12345',
        'threadId': 'thread123',
        'labelIds': ['INBOX', 'UNREAD'],
        'payload': {
            'headers': [
                {'name': 'From', 'value': from_addr},
                {'name': 'Subject', 'value': subject},
                {'name': 'Date', 'value': date}
            ],
            'body': {
                'data': base64.urlsafe_b64encode(body.encode()).decode()
            }
        }
    }

def create_mock_message_list(messages: list) -> Dict[str, Any]:
    """
    Create a synthetic Gmail message list response.
    
    Args:
        messages: List of message objects
        
    Returns:
        Dict matching Gmail API message list format
    """
    return {
        'messages': messages,
        'nextPageToken': None,
        'resultSizeEstimate': len(messages)
    }

# Example synthetic messages for testing edge cases
SYNTHETIC_MESSAGES = {
    'chase_payment': create_mock_message(
        subject="Chase Alert: Payment Sent",
        body="You sent a payment of $50.00 from your Chase account (...1234)",
        from_addr="no-reply@chase.com",
        date="Thu, 2 Jan 2025 06:33:33 +0000"
    ),
    'chase_deposit': create_mock_message(
        subject="Chase Alert: Direct Deposit",
        body="You have a direct deposit of $1,234.56. Account ending in (...7890).",
        from_addr="no-reply@chase.com",
        date="Thu, 2 Jan 2025 06:33:33 +0000"
    ),
    # Add more synthetic messages for edge cases here
}

INTEGRATION_TEST_MESSAGES = {
    'chase_direct_deposit_1': {
        'subject': "Chase Direct Deposit",
        'body': '''
            <html><body><table>
            <tr><td>You have a direct deposit of $1000.00</td></tr>
            <tr><td>Account ending in (...5678)</td></tr>
            <tr><td>2:49:50 PM ET</td></tr>
            </table></body></html>
        ''',
        'from_addr': "no.reply.alerts@chase.com",
        'date': "2024-01-01T14:49:50-05:00",
        'parsed_data': {
            'id': '<test_message_2@chase.com>',
            'id_api': 'test_message_2',
            'template_used': 'Chase Direct Deposit',
            'amount': 1000.00,
            'vendor': 'Direct Deposit',
            'account': '5678',
            'date': '2024-01-01T00:00:00Z',
            'status': 'pending',
            'description': 'Direct deposit',
            'predicted_category': 'Income',
            'predicted_subcategory': 'Salary',
            'vendor_cleaned': 'DIRECT DEPOSIT',
            'cleaned_metaphone': 'DRKT DPST'
        }
    },
    'chase_transaction_alert_1': {
        'subject': "Chase Transaction Alert",
        'body': '''
            <html><body><table>
            <tr><td>A purchase of $75.50 at WALMART</td></tr>
            <tr><td>Account ending in (...4321)</td></tr>
            <tr><td>3:15:00 PM ET</td></tr>
            </table></body></html>
        ''',
        'from_addr': "no.reply.alerts@chase.com",
        'date': "2024-01-01T15:15:00-05:00",
        'parsed_data': {
            'id': '<test_message_3@chase.com>',
            'id_api': 'test_message_3',
            'template_used': 'Chase Transaction Alert - New',
            'amount': 75.50,
            'vendor': 'WALMART',
            'account': '4321',
            'date': '2024-01-01T00:00:00Z',
            'status': 'pending',
            'description': 'Purchase at WALMART',
            'predicted_category': 'Shopping',
            'predicted_subcategory': 'Retail',
            'vendor_cleaned': 'WALMART',
            'cleaned_metaphone': 'WLMRT'
        }
    }
}

def get_mock_gmail_service():
    """
    Creates a mock Gmail service with predefined responses
    """
    mock_service = MagicMock()
    mock_messages = []
    
    # Create mock messages from test data
    for test_msg in INTEGRATION_TEST_MESSAGES.values():
        mock_messages.append(
            create_mock_message(
                subject=test_msg['subject'],
                body=test_msg['body'].strip(),
                from_addr=test_msg['from_addr'],
                date=test_msg['date']
            )
        )
    
    # Mock list messages
    mock_list = MagicMock()
    mock_list.execute.return_value = {'messages': mock_messages}
    mock_messages_api = MagicMock()
    mock_messages_api.list.return_value = mock_list
    
    # Mock get message
    def mock_get_message(*args, **kwargs):
        mock_get = MagicMock()
        msg_id = kwargs.get('id')
        for test_msg in INTEGRATION_TEST_MESSAGES.values():
            if test_msg['parsed_data']['id_api'] == msg_id:
                mock_get.execute.return_value = create_mock_message(
                    subject=test_msg['subject'],
                    body=test_msg['body'].strip(),
                    from_addr=test_msg['from_addr'],
                    date=test_msg['date']
                )
                return mock_get
        mock_get.execute.return_value = None
        return mock_get
    
    mock_messages_api.get = mock_get_message
    
    # Set up service mock
    mock_users = MagicMock()
    mock_users.messages.return_value = mock_messages_api
    mock_service.users.return_value = mock_users
    
    return mock_service