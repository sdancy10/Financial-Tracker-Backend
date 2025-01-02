from typing import Dict, Any, List, Tuple
from googleapiclient.discovery import build
import logging
from src.utils.config import Config
from src.utils.transaction_parser import TransactionParser

class GmailUtil:
    """Utility for interacting with Gmail API"""
    
    def __init__(self, credentials: Dict[str, Any]):
        """Initialize Gmail API client with OAuth2 credentials"""
        self.config = Config()
        self.logger = logging.getLogger(__name__)
        
        # Get OAuth2 credentials from the credentials dictionary
        if 'oauth2_credentials' not in credentials:
            raise ValueError("OAuth2 credentials not found in credentials dictionary")
        
        self.credentials = credentials['oauth2_credentials']
        
        # Build Gmail API service
        self.service = build('gmail', 'v1', credentials=self.credentials)
        self.logger.info(f"Gmail API service initialized for {credentials.get('email')}")
        self.user_id = credentials.get('user_id')
        self.email = credentials.get('email')
        self.parser = TransactionParser()
    
    def _get_message_id(self, headers: List[Dict[str, str]], gmail_id: str) -> str:
        """Extract Message-ID from headers, falling back to Gmail ID if not found"""
        for header in headers:
            if header['name'].lower() == 'message-id':
                # Remove any < > brackets from the Message-ID
                return header['value'].strip('<>').strip()
        return gmail_id
    
    def fetch_transaction_emails(self, query: str) -> List[Tuple[Dict[str, Any], str]]:
        """Fetch transaction emails from Gmail"""
        try:
            self.logger.info(f"Fetching emails with query: {query}")
            response = self.service.users().messages().list(
                userId='me',
                q=query
            ).execute()
            
            messages = response.get('messages', [])
            self.logger.info(f"Found {len(messages)} messages matching query")
            
            results = []
            for message in messages:
                gmail_id = message['id']
                self.logger.info(f"Processing message {gmail_id}")
                
                # Get full message details
                msg = self.service.users().messages().get(
                    userId='me',
                    id=gmail_id,
                    format='full'
                ).execute()
                
                # Get the original Message-ID from headers
                headers = msg['payload']['headers']
                message_id = self._get_message_id(headers, gmail_id)
                
                # Store both IDs in the message for reference
                msg['gmail_id'] = gmail_id
                msg['message_id'] = message_id
                
                # Parse transaction from email
                transaction = self.parser.parse_gmail_message(msg)
                
                # Only include successfully parsed transactions
                if transaction:
                    self.logger.info(f"Successfully parsed message {gmail_id}")
                    results.append((transaction, gmail_id))
                else:
                    self.logger.warning(f"Failed to parse message {gmail_id}")
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error fetching emails: {str(e)}")
            raise
    
    def mark_as_read(self, message_id: str) -> bool:
        """Mark a Gmail message as read"""
        try:
            self.logger.info(f"Marking message {message_id} as read")
            # First check if message exists and is unread
            msg = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='minimal'
            ).execute()
            
            labels = msg.get('labelIds', [])
            if 'UNREAD' not in labels:
                self.logger.info(f"Message {message_id} is already marked as read")
                return True
                
            self.logger.info(f"Removing UNREAD label from message {message_id}")
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            return True
        except Exception as e:
            self.logger.error(f"Error marking message {message_id} as read: {str(e)}")
            return False 