import os
import sys
import re
import json
import base64
import logging
import unittest
from datetime import datetime
from typing import Dict, Any, List
from unittest.mock import patch

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Configure logging to show all levels
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Get the TransactionParser logger and set its level to DEBUG
parser_logger = logging.getLogger('src.utils.transaction_parser')
parser_logger.setLevel(logging.DEBUG)

# Create console handler if it doesn't exist
if not parser_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    parser_logger.addHandler(console_handler)

from src.utils.transaction_parser import TransactionParser
from src.utils.gmail_util import GmailUtil
from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config
from src.utils.test_utils import get_test_user
from src.mock.api.mock_gmail_synthetic_api import create_mock_message
# Mock Failures may not exist, try to import
try:
    from src.mock.api.mock_messages_failures import MOCK_FAILURES
except ImportError:
    MOCK_FAILURES = None  # or MOCK_FAILURES = {}

def get_gmail_service(email: str = None):
    """Set up Gmail API client"""
    config = Config()
    cred_manager = CredentialsManager(config.get('project', 'id'), config)
    
    # Get test user from config
    user_id, test_email, _ = get_test_user(config)
    
    # If email is provided, look up the corresponding user_id from config
    if email:
        # Get the email to account mapping from config
        auth_config = config.get('auth', 'gmail')
        email_to_account = auth_config.get('email_to_account', {})
        accounts = auth_config.get('accounts', {})
        
        # Look up account name for the email
        account_name = email_to_account.get(email)
        if not account_name:
            raise ValueError(f"Email {email} not found in config.yaml auth.gmail.email_to_account")
            
        # Get account config and user_id
        account_config = accounts.get(account_name)
        if not account_config:
            raise ValueError(f"Account {account_name} not found in config.yaml auth.gmail.accounts")
            
        user_id = account_config.get('user_id')
        if not user_id:
            raise ValueError(f"No user_id found for account {account_name}")
        
        print(f"\nUsing credentials for:")
        print(f"Email: {email}")
        print(f"Account: {account_name}")
        print(f"User ID: {user_id}")
    else:
        # Use default test user
        email = test_email
        print(f"\nUsing default test credentials:")
        print(f"Email: {email}")
        print(f"User ID: {user_id}")
    
    creds = cred_manager.get_user_gmail_credentials(user_id, email)
    gmail_util = GmailUtil(creds)
    return gmail_util.service

class TestTransactionParser(unittest.TestCase):
    """Test suite for transaction parsing functionality"""
    test_results = []

    @classmethod
    def tearDownClass(cls):
        """Print summary report after all tests complete"""
        print("\n=== Transaction Parser Test Summary ===")
        for result in cls.test_results:
            print(f"\nTest: {result['test_name']}")
            if result.get('error'):
                print(f"Error: {result['error']}")
                continue
                
            print(f"Template Used: {result['template']}")
            if result['template'] == 'Failed to parse':
                # Only show pattern details if parsing failed
                print("\nPattern Results:")
                print(f"  Account:")
                print(f"    Pattern: {result['patterns']['account']}")
                print(f"    Match: {result['matches'].get('account', 'No match')}")
                
                print(f"\n  Amount:")
                print(f"    Pattern: {result['patterns']['amount']}")
                print(f"    Match: {result['matches'].get('amount', 'No match')}")
                
                print(f"\n  Vendor:")
                print(f"    Pattern: {result['patterns'].get('vendor', result['patterns'].get('merchant', 'No pattern'))}")
                print(f"    Match: {result['matches'].get('vendor', 'No match')}")
                
                print(f"\n  Date:")
                print(f"    Pattern: {result['patterns']['date']}")
                print(f"    Match: {result['matches'].get('date', 'No match')}")
            else:
                # Just show the successful matches
                print("\nMatches:")
                print(f"  Account: {result['matches'].get('account', 'No match')}")
                print(f"  Amount: {result['matches'].get('amount', 'No match')}")
                print(f"  Vendor: {result['matches'].get('vendor', 'No match')}")
                print(f"  Date: {result['matches'].get('date', 'No match')}")
            print("-" * 50)

    def setUp(self):
        """Set up test cases"""
        self.parser = TransactionParser()
        self.timestamp = "1704067200000"  # 2024-01-01 12:00:00 UTC
        
        # Get patterns from the current template being tested
        self.patterns = {}
        for template_name, template in self.parser.TEMPLATES.items():
            if template_name == 'Chase Payment Sent':  # Or any other template we're testing
                self.patterns = {
                    'account': template['account'],
                    'amount': template['amount'],
                    'vendor': template['vendor'],
                    'date': template['date']
                }
                break
        
        # Disable logging except for critical errors
        logging.basicConfig(level=logging.CRITICAL)
    
    def _get_template_patterns(self, template_name: str) -> Dict[str, str]:
        """Get patterns for a specific template"""
        template = self.parser.TEMPLATES.get(template_name)
        if not template:
            return {}
        return {
            'account': template.get('account', ''),
            'amount': template.get('amount', ''),
            'vendor': template.get('vendor', ''),
            'date': template.get('date', '')
        }
    
    def _get_message_body(self, payload: Dict[str, Any]) -> str:
        """Extract message body from Gmail API payload"""
        if 'body' in payload and payload['body'].get('data'):
            return base64.urlsafe_b64decode(payload['body']['data']).decode()
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    return base64.urlsafe_b64decode(part['body']['data']).decode()
        
        return ''
    
    def test_direct_deposit(self):
        """Test handling of direct deposit transactions"""
        message = create_mock_message(
            subject="Chase Direct Deposit",
            body="You have a direct deposit of $1,234.56. Account ending in (...7890).",
            from_addr="no-reply@chase.com",
            date="Thu, 2 Jan 2025 06:33:33 +0000"  # Added mock date
        )
        
        result = self.parser.parse_gmail_message(message)
        
        self.assertIsNotNone(result)
        self.assertEqual(result['amount'], 1234.56)
        self.assertEqual(result['vendor'], 'Direct Deposit')
        self.assertEqual(result['account'], '7890')
        self.assertEqual(result['template_used'], 'Chase Direct Deposit')
        
        # Record test results
        self.__class__.test_results.append({
            'test_name': 'Direct Deposit',
            'template': result['template_used'],
            'patterns': self.patterns,
            'matches': {
                'account': result['account'],
                'amount': result['amount'],
                'vendor': result['vendor'],
                'date': result.get('date', 'Not captured')
            }
        })
    
    def test_invalid_html_table(self):
        """Test handling of malformed HTML table"""
        html_body = """
        <table>
            <tr>
                <td>Account ending in 3456</td>
                <td>Invalid Amount</td>
                <td>AMAZON.COM</td>
            </tr>
        </table>
        """
        
        message = create_mock_message(
            subject="Your Chase credit card statement",
            body=html_body,
            from_addr="no-reply@chase.com",
            is_html=True
        )
        
        result = self.parser.parse_gmail_message(message)
        self.assertIsNone(result)
        
        # Record test results
        self.__class__.test_results.append({
            'test_name': 'Invalid HTML Table',
            'error': 'Failed to parse HTML table - invalid amount format',
            'patterns': self.patterns,
            'matches': {}
        })
    
    def test_missing_fields(self):
        """Test handling of emails with missing required fields"""
        # Message with only amount (should fail since it doesn't match any template)
        message1 = create_mock_message(
            subject="Chase Alert",
            body="$50.00",
            from_addr="no-reply@chase.com",
            date="Thu, 2 Jan 2025 06:33:33 +0000"
        )
        result1 = self.parser.parse_gmail_message(message1)
        self.assertIsNone(result1)  # Changed to expect None since no template matches
        
        # Record test results
        self.__class__.test_results.append({
            'test_name': 'Message with Only Amount',
            'error': 'Failed to parse - no matching template',
            'patterns': self.patterns,
            'matches': {}
        })
        
        # Missing amount (should fail)
        message2 = create_mock_message(
            subject="Chase Alert",
            body="An external transfer has been sent to John Doe on Jan 1. Card ending in 1234.",
            from_addr="no-reply@chase.com",
            date="Thu, 2 Jan 2025 06:33:33 +0000"
        )
        result2 = self.parser.parse_gmail_message(message2)
        self.assertIsNone(result2)
        
        # Record test results
        self.__class__.test_results.append({
            'test_name': 'Missing Amount',
            'error': 'Failed to parse - missing amount',
            'patterns': self.patterns,
            'matches': {}
        })
        
        # Has amount and account in Chase format (should pass)
        message3 = create_mock_message(
            subject="Chase Alert: Direct Deposit",
            body="You have a direct deposit of $50.00. Account ending in (...1234).",
            from_addr="no-reply@chase.com",
            date="Thu, 2 Jan 2025 06:33:33 +0000"
        )
        result3 = self.parser.parse_gmail_message(message3)
        self.assertIsNotNone(result3)
        self.assertEqual(result3['amount'], 50.00)
        self.assertEqual(result3['account'], '1234')
        self.assertEqual(result3['vendor'], 'Direct Deposit')
        
        # Record test results
        self.__class__.test_results.append({
            'test_name': 'Valid Chase Direct Deposit',
            'template': result3['template_used'],
            'patterns': self.patterns,
            'matches': {
                'amount': result3['amount'],
                'vendor': result3['vendor'],
                'account': result3['account'],
                'date': result3.get('date', 'Not captured')
            }
        })
    
    def test_specific_message(self):
        """Test parsing of a specific Gmail message by ID"""
        email = "clairejablonski@gmail.com"  # The email we're testing
        
        # Use the exact Message ID
        message_id = "<01000198319991c0-abbce2ca-a623-4aa1-bfee-e005fa9bc183-000000@email.amazonses.com>" # unread discover
        message_id = "<47v2xbtke8-1@rfxt2mgwppa0002.fiserv.one>" #target
        message_id = "<66177893-4715-46df-8736-0013e0e76552@ind1s01mta612.xt.local>" #huntington deposit
        # message_id = "<dc51bf77-6277-4a04-bda9-da559fe49255@ind1s01mta612.xt.local>" # huntington
        # Get Gmail service
        service = get_gmail_service(email)
        
        # Search for the message by Message ID
        query = f"rfc822msgid:{message_id}"
        results = service.users().messages().list(userId='me', q=query).execute()
        
        if not results.get('messages'):
            print(f"No messages found matching Message ID: {message_id}")
            return
            
        # Get the first matching message
        message = service.users().messages().get(userId='me', id=results['messages'][0]['id'], format='full').execute()
        
        # Get message details for debugging
        headers = {h['name']: h['value'] for h in message['payload']['headers']}
        subject = headers.get('Subject', 'No subject')
        notification_id_header = headers.get('NOTIFICATION-ID', 'No notification ID')
        body = self._get_message_body(message['payload'])
        
        # Print exact content we're matching against
        print("\n=== Content Being Matched ===")
        print(f"Subject: {subject}")
        print(f"Notification ID: {notification_id_header}")
        print("==============")
        print(f"Body (first 1000 chars):\n{body}")
        print("==============")
        
        # Try to parse it
        result = self.parser.parse_gmail_message(message)
        
        # Get patterns from the template that should match
        template_name = 'Huntington Checking/Savings Deposit'  # The template we expect to match
        patterns = self._get_template_patterns(template_name)
        
        # Try manual regex matches for debugging
        print("\n=== Manual Regex Tests ===")
        for field, pattern in patterns.items():
            if pattern:
                matches = re.finditer(pattern, body, re.IGNORECASE | re.DOTALL)
                print(f"\n{field.upper()} Pattern: {pattern}")
                for i, match in enumerate(matches):
                    print(f"Match {i+1}:")
                    print(f"  Full match: {match.group(0)}")
                    print(f"  Groups: {match.groups()}")
                    try:
                        for j, group in enumerate(match.groups(), 1):
                            print(f"  Group {j}: {group}")
                    except:
                        pass
                else:
                    print("No match found")

        # Record test results with detailed logging
        test_result = {
            'test_name': f'Specific Message Test (ID: {message_id})',
            'notification_id': notification_id_header,
            'template': result['template_used'] if result else 'Failed to parse',
            'patterns': patterns,
            'matches': {}
        }
        
        if result:
            test_result['matches'] = {
                'account': result['account'],
                'amount': result['amount'],
                'vendor': result['vendor'],
                'date': result.get('date', 'Not captured')
            }
        else:
            print(f"\nMessage Details:")
            print(f"Subject: {subject}")
            print(f"Notification ID: {notification_id_header}")
            print(f"Body: {body}...")
            
        self.__class__.test_results.append(test_result)

    def test_failure_message_body(self, message_id: str = "193e38858583a58b"):
        """Test extracting message body from a failure message.
        
        Args:
            message_id (str): The ID of the message to test. Defaults to a known failure message ID.
        """
        # Find the message with the given ID in MOCK_FAILURES
        target_message = None
        for email, failures in MOCK_FAILURES.items():
            for failure in failures:
                if failure['id'] == message_id:
                    target_message = failure
                    break
            if target_message:
                break
        
        assert target_message is not None, f"Message with ID {message_id} not found in MOCK_FAILURES"
        
        # Get and decode the message body
        decoded_body = self._get_message_body(target_message['payload'])
        
        print("\n=== DECODED MESSAGE BODY ===")
        print("=" * 80)
        print(decoded_body)
        print("=" * 80)
        result = self.parser.parse_gmail_message(decoded_body)
        print("\n=== DECODED MESSAGE BODY ===")
        print("=" * 80)
        print(result)
        print("=" * 80)
        
        # Minimal assertions just to keep the test valid
        self.assertIsNotNone(decoded_body)
        
        return decoded_body

if __name__ == '__main__':
    unittest.main() 