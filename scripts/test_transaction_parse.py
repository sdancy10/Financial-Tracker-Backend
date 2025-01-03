import os
import sys
import re
import json
import base64
from datetime import datetime
from typing import Dict, Any, List

# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from src.utils.gmail_util import GmailUtil
from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config
from src.utils.transaction_parser import TransactionParser

def get_gmail_service(email: str):
    """Set up Gmail API client"""
    config = Config()
    cred_manager = CredentialsManager(config.get('project', 'id'), config)
    user_id = 'aDer8RS94NPmPdAYGHQQpI3iWm13'
    creds = cred_manager.get_user_gmail_credentials(user_id, email)
    gmail_util = GmailUtil(creds)
    return gmail_util.service

def get_recent_messages(gmail_service, message_ids: List[str] = None) -> List[Dict[str, Any]]:
    """Get recent messages with label:Transactions
    
    Args:
        gmail_service: Gmail API service object
        message_ids: Optional list of specific message IDs to retrieve
    """
    if message_ids:
        # If specific IDs provided, get those messages
        messages = []
        for msg_id in message_ids:
            try:
                message = gmail_service.users().messages().get(userId='me', id=msg_id).execute()
                messages.append({'id': msg_id})
            except Exception as e:
                print(f"Error retrieving message {msg_id}: {str(e)}")
        return messages
    
    # Otherwise get recent messages with Transactions label
    result = gmail_service.users().messages().list(
        userId='me',
        q='label:Transactions',
        maxResults=3
    ).execute()
    return result.get('messages', [])


def get_message_body(payload: Dict[str, Any]) -> str:
        """Extract message body from Gmail API payload and sanitize it."""
        raw_body = ''
        if 'body' in payload and payload['body'].get('data'):
            raw_body = base64.urlsafe_b64decode(payload['body']['data']).decode()
        elif 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    raw_body = base64.urlsafe_b64decode(part['body']['data']).decode()
                    break
        
        # Sanitize the body before returning
        sanitized_body = _sanitize_body(raw_body)
        return sanitized_body

def decode_message_parts(parts):
    message_body = ""
    for part in parts:
        if part.get('mimeType') == 'text/html':
            data = part.get('body', {}).get('data', '')
            if data:
                message_body = base64.urlsafe_b64decode(data).decode('utf-8')
                break
    return message_body

def test_regex_pattern(pattern, text, pattern_name):
    print(f"\nTesting {pattern_name}:")
    print(f"Pattern: {pattern}")
    matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
    found = False
    for match in matches:
        found = True
        print(f"Match found: {match.group()}")
        for i, group in enumerate(match.groups()):
            if group:
                print(f"  Group {i+1}: {group}")
    if not found:
        print("No matches")

def analyze_message(message_id: str, gmail_service, suppress_html: bool = False):
    """Analyze a specific message"""
    print("=" * 50)
    print(f"Analyzing message {message_id}")
    print("=" * 50)
    print()

    # Get the message
    message = gmail_service.users().messages().get(userId='me', id=message_id).execute()
    
    # Extract headers
    headers = {h['name']: h['value'] for h in message['payload']['headers']}
    print("=== Message Details ===")
    print(f"Subject: {headers.get('Subject', '')}")
    print(f"From: {headers.get('From', '')}")
    print(f"Date: {headers.get('Date', '')}")
    print()

    # Get message body
    body = get_message_body(message['payload'])
    
    if not suppress_html:
        print("=== Raw Message Body ===")
        print(body)
        print()

    # Create a TransactionParser instance
    parser = TransactionParser()
    
    # First show the template matching process
    print("=== Template Matching Process ===")
    template_name, matches = parser._find_matching_template(message['payload']['headers'], body)
    if template_name:
        print(f"Template matched during search: {template_name}")
        if matches and matches.get('found'):
            print("\nMatches found:")
            for field, value in matches['found'].items():
                print(f"  {field}: {value}")
    else:
        print("No template matched during search")
    print()

    # Now parse the message and show results
    result = parser.parse_gmail_message(message)
    
    if result and result.get('template_used'):
        print(f"=== Final Template Used: {result['template_used']} ===")
        print()
        template = parser.TEMPLATES[result['template_used']]
        print("Template patterns:")
        for field, pattern in template.items():
            if field in ['iterate_results', 'subject_pattern', 'email_from']:
                continue
            print(f"  {field}: {pattern}")
        print()
        
        print("=== Testing Final Template Patterns ===")
        # Test each pattern in the template
        for field, pattern in template.items():
            if field in ['iterate_results', 'subject_pattern', 'email_from']:
                continue
                
            if not pattern:  # Skip empty patterns
                continue
                
            print(f"\nTesting {field}_pattern:")
            print(f"Pattern: {pattern}")
            
            if field == 'date':
                # For date pattern, show context around "as of" if present
                print("\nSearching for 'as of' in text:")
                for match in re.finditer(r'as of[^<\n]*', body):
                    print(f"Found 'as of' context: {match.group()}")
            
            matches = re.finditer(pattern, body, re.IGNORECASE | re.MULTILINE)
            found = False
            for match in matches:
                found = True
                print(f"Match found: {match.group()}")
                for i, group in enumerate(match.groups()):
                    if group:
                        print(f"  Group {i+1}: {group}")
            if not found:
                print("No matches")

    # Show the parser result
    print("\n=== Final Parser Result ===")
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Failed to parse with any template:")
        print(f"Subject: {headers.get('Subject', '')}")
        print(f"From: {headers.get('From', '')}")
        if not suppress_html:
            print(f"Body: {_sanitize_body(body)}")
        else:
            print("Body: [HTML content suppressed]")
        print("No transaction parsed")
    print()
def _sanitize_body(body: str) -> str:
        """
        Remove potentially malicious or unwanted HTML/scripts/styles,
        and return a cleaned version of the body text.
        """
        # Remove script tags and content
        body = re.sub(r'<script.*?>.*?</script>', '', body, flags=re.DOTALL | re.IGNORECASE)
        # Remove style tags and content
        body = re.sub(r'<style.*?>.*?</style>', '', body, flags=re.DOTALL | re.IGNORECASE)
        # Remove all other HTML tags
        body = re.sub(r'<[^>]+>', '', body)
        return body
def main():
    # Set up Gmail API client
    gmail_service = get_gmail_service("sdancy.10@gmail.com")
    
    # Test specific message IDs
    message_ids = ["1942a6a83abbf97b"]
    # messages = get_recent_messages(gmail_service, message_ids)
    
    # # Analyze each message
    # for msg in messages:
    #     analyze_message(msg['id'], gmail_service)
    analyze_message("1942a6a83abbf97b", gmail_service)

if __name__ == "__main__":
    main() 