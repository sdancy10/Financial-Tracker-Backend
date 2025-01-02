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

from src.utils.transaction_parser import TransactionParser
from src.utils.gmail_util import GmailUtil
from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config
from src.utils.test_utils import get_test_user

def get_gmail_service(email: str = None):
    """Set up Gmail API client"""
    config = Config()
    cred_manager = CredentialsManager(config.get('project', 'id'), config)
    
    # Get test user from config if email not provided
    if not email:
        user_id, email, _ = get_test_user(config)
    else:
        # For backward compatibility, use default test user ID
        user_id, _, _ = get_test_user(config)
    
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
    
    def _create_gmail_message(self, subject: str, body: str, from_addr: str, date: str = None, is_html: bool = False) -> Dict[str, Any]:
        """Create a test Gmail message"""
        if is_html:
            mime_type = 'text/html'
            body_data = f'<html><body>{body}</body></html>'
        else:
            mime_type = 'text/plain'
            body_data = body

        # Create headers
        headers = [
            {'name': 'Subject', 'value': subject},
            {'name': 'From', 'value': from_addr},
            {'name': 'Message-ID', 'value': '<test_message@test.com>'}
        ]
        
        # Add date header if provided
        if date:
            headers.append({'name': 'Date', 'value': date})

        # Create message payload
        payload = {
            'headers': headers,
            'mimeType': mime_type,
            'body': {
                'data': base64.urlsafe_b64encode(body_data.encode()).decode()
            }
        }

        # Create full message structure
        message = {
            'id': 'test_message_id',
            'threadId': 'test_thread_id',
            'labelIds': ['INBOX', 'UNREAD'],
            'payload': payload,
            'message_id': '<test_message@test.com>',  # Original Message-ID
            'gmail_id': 'test_message_id'  # Gmail API ID
        }

        return message
    
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
        message = self._create_gmail_message(
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
        
        message = self._create_gmail_message(
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
        message1 = self._create_gmail_message(
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
        message2 = self._create_gmail_message(
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
        message3 = self._create_gmail_message(
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
        email = "sdancy.10@gmail.com"  # The email we're testing
        message_id = "19416464ae1c66b6"
        
        # Get Gmail service
        service = get_gmail_service(email)
        
        # Get the specific message
        message = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        
        # Get message details for debugging
        headers = {h['name']: h['value'] for h in message['payload']['headers']}
        subject = headers.get('Subject', 'No subject')
        body = self._get_message_body(message['payload'])
        
        # Print exact content we're matching against
        print("\n=== Content Being Matched ===")
        print(f"Subject: {subject}")
        print(f"Body (first 1000 chars):\n{body[:1000]}")
        
        # Try to parse it
        result = self.parser.parse_gmail_message(message)
        
        # Get patterns from the template that should match
        template_name = 'Chase Payment Sent'  # The template we expect to match
        patterns = self._get_template_patterns(template_name)
        
        # Try manual regex matches for debugging
        print("\n=== Manual Regex Tests ===")
        for field, pattern in patterns.items():
            if pattern:
                matches = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
                print(f"\n{field.upper()} Pattern: {pattern}")
                if matches:
                    print(f"Match object: {matches}")
                    print(f"Groups: {matches.groups()}")
                    print(f"Group dict: {matches.groupdict()}")
                    print(f"Group 0 (full match): {matches.group(0)}")
                    try:
                        print(f"Group 1: {matches.group(1)}")
                    except:
                        pass
                else:
                    print("No match found")
        
        # Record test results with detailed logging
        test_result = {
            'test_name': f'Specific Message Test (ID: {message_id})',
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
            print(f"Body: {body[:500]}...")
            
        self.__class__.test_results.append(test_result)

if __name__ == '__main__':
    unittest.main() 