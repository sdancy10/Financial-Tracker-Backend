import unittest
from unittest.mock import patch, Mock, MagicMock
import base64
import logging
import os
from google.cloud import firestore
from googleapiclient.discovery import build
from src.services.transaction_service import TransactionService
from src.utils.transaction_dao import TransactionDAO
from src.utils.transaction_parser import TransactionParser
from src.utils.gmail_util import GmailUtil
from src.utils.credentials_manager import CredentialsManager
from src.utils.config import Config
from src.utils.test_utils import get_test_users
from src.mock.api.mock_gmail_synthetic_api import (
    create_mock_message, 
    INTEGRATION_TEST_MESSAGES,
    get_mock_gmail_service
)

class TestGmailIntegration(unittest.TestCase):
    """Test Gmail integration functionality"""
    
    def setUp(self):
        """Set up test environment"""
        # Enable debug logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            force=True
        )
        self.logger = logging.getLogger(__name__)
        
        # Initialize config
        self.config = Config()
        self.project_id = self.config.get('gcp', 'project_id')
        
        # Initialize credentials manager with real credentials
        self.creds_manager = CredentialsManager(self.project_id, self.config)
        
        # Get service account credentials from the credentials manager
        self.service_account_creds = self.creds_manager.service_account_credentials

        # Initialize real Firestore client with service account credentials
        self.real_db = firestore.Client(
            project=self.project_id,
            credentials=self.service_account_creds
        )
        
        # Get real credentials for test users
        try:
            test_users = get_test_users(self.config)
            user1, user2 = list(test_users.values())[:2]  # Get first two users
            
            self.user1_creds = self.creds_manager.get_user_gmail_credentials(
                user1['user_id'], 
                user1['email']
            )
            self.user2_creds = self.creds_manager.get_user_gmail_credentials(
                user2['user_id'], 
                user2['email']
            )
            self.logger.info("Successfully loaded real credentials for test users")
        except Exception as e:
            self.logger.error(f"Failed to load real credentials: {str(e)}")
            raise
        
        # Initialize Gmail clients with real credentials but mock the service
        with patch('src.utils.gmail_util.build') as mock_build:
            mock_service = MagicMock()
            mock_build.return_value = mock_service
            self.user1_gmail = GmailUtil(self.user1_creds)
            self.user2_gmail = GmailUtil(self.user2_creds)
            self.user1_gmail.service = mock_service
            self.user2_gmail.service = mock_service
        
        self.parser = TransactionParser()
    
    def _fetch_sample_transactions(self) -> dict:
        """Fetch one transaction for each template from Firestore"""
        samples = {}
        templates = ['Chase Transaction Alert - New', 'Chase Direct Deposit']
        
        # Get user IDs from test users
        test_users = get_test_users(self.config)
        user_ids = [user['user_id'] for user in test_users.values()][:2]  # Get first two users
        
        self.logger.info("Fetching sample transactions from Firestore")
        
        # List all collections
        for user_id in user_ids:
            self.logger.info(f"Looking for transactions for user: {user_id}")
            # Query transactions for this user
            transactions_ref = self.real_db.collection('users').document(user_id).collection('transactions')
            
            for template in templates:
                if template not in samples:  # Only get one sample per template
                    query = transactions_ref.where('template_used', '==', template).limit(1)
                    docs = query.stream()
                    for doc in docs:
                        data = doc.to_dict()
                        samples[template] = data
                        self.logger.info(f"Found sample transaction for template {template} from user {user_id}: {data.get('id_api')}")
        
        if not samples:
            self.logger.error("No sample transactions found in Firestore")
        else:
            self.logger.info(f"Found {len(samples)} sample transactions")
        
        return samples
    
    def _fetch_email_data(self) -> dict:
        """Fetch email data for sample transactions from Gmail"""
        emails = {}
        
        self.logger.info("Fetching email data from Gmail")
        for template, transaction in self.sample_transactions.items():
            if 'id_api' in transaction:
                try:
                    self.logger.info(f"Fetching email for transaction {transaction['id_api']}")
                    # Get test users for email lookup
                    test_users = get_test_users(self.config)
                    user_emails = {user['user_id']: user['email'] for user in test_users.values()}
                    
                    # Determine which Gmail client to use based on the user's email
                    user_id = transaction.get('user_id')
                    gmail_client = self.user1_gmail if user_id == list(test_users.values())[0]['user_id'] else self.user2_gmail
                    
                    # Fetch email data from Gmail
                    message = gmail_client.service.users().messages().get(
                        userId='me',
                        id=transaction['id_api'],
                        format='full'
                    ).execute()
                    
                    if message:
                        emails[transaction['id_api']] = message
                        self.logger.info(f"Found email data for transaction {transaction['id_api']}")
                    else:
                        self.logger.warning(f"No email found for transaction {transaction['id_api']}")
                except Exception as e:
                    self.logger.error(f"Error fetching email data for {transaction['id_api']}: {str(e)}")
        
        if not emails:
            self.logger.error("No email data found in Gmail")
        else:
            self.logger.info(f"Found {len(emails)} emails")
        
        return emails
    
    @patch('src.utils.transaction_dao.firestore')
    @patch('src.utils.gmail_util.build')
    @patch('src.services.transaction_service.TransactionValidator')
    @patch('src.services.transaction_service.firestore')
    def test_end_to_end_transaction_processing(self, mock_firestore_service, mock_validator, mock_build, mock_firestore_dao):
        """Test end-to-end transaction processing for a test user"""
        self.logger.info("Starting end-to-end transaction processing test")
        
        # Mock Firestore client for both service and DAO
        mock_db = Mock()
        mock_firestore_service.Client.return_value = mock_db
        mock_firestore_dao.Client.return_value = mock_db
        
        # Mock batch operations
        mock_batch = Mock()
        mock_batch._write_pbs = []  # Mock the internal write_pbs list
        mock_batch.set = Mock(side_effect=lambda ref, data, **kwargs: mock_batch._write_pbs.append(1))  # Simulate adding to batch
        mock_db.batch.return_value = mock_batch
        
        # Mock user collection query
        test_users = get_test_users(self.config)
        user1 = list(test_users.values())[0]  # Get first test user
        
        mock_users_ref = Mock()
        mock_users_ref.stream.return_value = [
            Mock(id=user1['user_id'], to_dict=lambda: {
                'email': user1['email'],
                'last_sync': '2024-01-01T00:00:00Z',
                'email_sync_enabled': True,
                'contactInformation': {'_email': user1['email']}
            })
        ]
        
        # Mock transactions collection
        mock_transactions_ref = Mock()
        mock_user_doc = Mock()
        mock_transaction_doc = Mock()
        mock_transaction_doc.get.return_value = Mock(exists=False)
        mock_transactions_ref.document.return_value = mock_transaction_doc
        mock_user_doc.collection.return_value = mock_transactions_ref
        mock_users_ref.document.return_value = mock_user_doc
        
        def mock_collection(name):
            if name == 'users':
                return mock_users_ref
            return Mock()
        
        mock_db.collection = mock_collection
        
        # Mock Gmail API with real transaction examples
        mock_service = MagicMock()
        mock_messages = []
        mock_emails = {}
        
        # Create mock messages with the Transactions label
        mock_messages = [
            create_mock_message(
                subject="Chase Direct Deposit",
                body='''
                    <html>
                    <body>
                    <table>
                    <tr><td>You have a direct deposit of $1000.00</td></tr>
                    <tr><td>Account ending in (...5678)</td></tr>
                    <tr><td>2:49:50 PM ET</td></tr>
                    </table>
                    </body>
                    </html>
                '''.strip(),
                from_addr="no.reply.alerts@chase.com",
                date="2024-01-01T14:49:50-05:00"
            )
        ]
        
        # Mock list messages
        mock_list = MagicMock()
        mock_list.execute.return_value = {'messages': mock_messages}
        mock_messages_api = MagicMock()
        mock_messages_api.list.return_value = mock_list
        
        # Mock get message
        def mock_get_message(*args, **kwargs):
            mock_get = MagicMock()
            if 'id' in kwargs and kwargs['id'] == 'test_message_1':
                mock_get.execute.return_value = mock_messages[0]
            else:
                mock_get.execute.return_value = None
            return mock_get
        
        mock_messages_api.get = mock_get_message
        
        # Mock users API
        mock_users = MagicMock()
        mock_users.messages.return_value = mock_messages_api
        mock_service.users.return_value = mock_users
        
        mock_build.return_value = mock_service
        
        # Mock transaction validator
        mock_validator_instance = mock_validator.return_value
        mock_validator_instance.validate_transaction.return_value = (True, None)
        
        # Mock Gmail client initialization but use real credentials
        mock_gmail_client = MagicMock()
        mock_gmail_client.service = mock_service
        mock_gmail_client.fetch_transaction_emails.return_value = [(
            {
                'id': '<test_message_1@chase.com>',
                'id_api': 'test_message_1',
                'template_used': 'Chase Transaction Alert - New',
                'amount': 100.00,
                'vendor': 'TEST VENDOR',
                'account': '1234',
                'date': '2024-01-01T00:00:00Z',
                'user_id': user1['user_id'],
                'account_id': 'test_account_1',
                'status': 'pending',
                'description': 'Test transaction',
                'predicted_category': 'Shopping',
                'predicted_subcategory': 'Retail',
                'vendor_cleaned': 'TEST VENDOR',
                'cleaned_metaphone': 'TST FNTR'
            },
            'test_message_1'
        )]
        
        # Use real credentials manager but mock the service
        with patch('src.services.transaction_service.GmailUtil', return_value=mock_gmail_client):
            # Run test
            service = TransactionService(self.project_id)
            
            # Use real credentials for test user
            test_user = {
                'user_id': user1['user_id'],
                'email': user1['email'],
                **self.user1_creds  # Use real credentials
            }
            
            self.logger.info("Processing transactions for test user")
            success = service.process_user_transactions(test_user)
            self.assertTrue(success, "Failed to process transactions for test user")
            
            # Verify validator was called
            mock_validator_instance.validate_transaction.assert_called()
            
            # Verify batch operations
            mock_batch.commit.assert_called()
            self.logger.info("End-to-end transaction processing test completed")
    
    @patch('src.utils.transaction_dao.firestore')
    @patch('src.utils.gmail_util.build')
    @patch('src.services.transaction_service.TransactionValidator')
    @patch('src.services.transaction_service.firestore')
    def test_mock_transaction_processing(self, mock_firestore_service, mock_validator, mock_build, mock_firestore_dao):
        """Test transaction processing with mocked dependencies"""
        # Mock Firestore client for both service and DAO
        mock_db = Mock()
        mock_firestore_service.Client.return_value = mock_db
        mock_firestore_dao.Client.return_value = mock_db
        
        # Mock batch operations
        mock_batch = Mock()
        mock_batch._write_pbs = []  # Mock the internal write_pbs list
        mock_batch.set = Mock(side_effect=lambda ref, data, **kwargs: mock_batch._write_pbs.append(1))  # Simulate adding to batch
        mock_db.batch.return_value = mock_batch
        
        # Get test users
        test_users = get_test_users(self.config)
        user2 = list(test_users.values())[1]  # Get second test user
        
        # Mock user collection query
        mock_users_ref = Mock()
        mock_users_ref.stream.return_value = [
            Mock(id=user2['user_id'], to_dict=lambda: {
                'email': user2['email'],
                'last_sync': '2024-01-01T00:00:00Z',
                'email_sync_enabled': True,
                'contactInformation': {'_email': user2['email']}
            })
        ]
        
        # Mock transactions collection
        mock_transactions_ref = Mock()
        mock_user_doc = Mock()
        mock_transaction_doc = Mock()
        mock_transaction_doc.get.return_value = Mock(exists=False)
        mock_transactions_ref.document.return_value = mock_transaction_doc
        mock_user_doc.collection.return_value = mock_transactions_ref
        mock_users_ref.document.return_value = mock_user_doc
        
        def mock_collection(name):
            if name == 'users':
                return mock_users_ref
            return Mock()
        
        mock_db.collection = mock_collection
        
        # Use mock service with predefined test data
        mock_build.return_value = get_mock_gmail_service()

        # Mock Gmail client with predefined responses
        mock_gmail_client = MagicMock()
        mock_gmail_client.service = mock_build.return_value
        
        # Use predefined test data for transaction responses
        test_message = INTEGRATION_TEST_MESSAGES['chase_direct_deposit_1']
        mock_gmail_client.fetch_transaction_emails.return_value = [(
            {
                **test_message['parsed_data'],
                'user_id': user2['user_id'],
                'account_id': 'test_account_2'
            },
            test_message['parsed_data']['id_api']
        )]
        
        # Mock transaction validator
        mock_validator_instance = mock_validator.return_value
        mock_validator_instance.validate_transaction.return_value = (True, None)
        
        # Mock CredentialsManager
        mock_creds_manager = MagicMock()
        mock_creds_manager.get_credentials.return_value = {
            'refresh_token': 'test_refresh_token',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'scopes': ['https://www.googleapis.com/auth/gmail.readonly']
        }
        mock_creds_manager.get_user_gmail_credentials.return_value = {
            'refresh_token': 'test_refresh_token',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'client_id': 'test_client_id',
            'client_secret': 'test_client_secret',
            'scopes': ['https://www.googleapis.com/auth/gmail.readonly']
        }
        
        # Patch GmailUtil and CredentialsManager
        with patch('src.services.transaction_service.GmailUtil', return_value=mock_gmail_client), \
             patch('src.services.transaction_service.CredentialsManager', return_value=mock_creds_manager):
            # Run test
            service = TransactionService(self.project_id)
            
            # Use test credentials directly instead of getting from service
            test_user = {
                'user_id': user2['user_id'],
                'email': user2['email'],
                **self.user2_creds
            }
            
            success = service.process_user_transactions(test_user)
            self.assertTrue(success, "Failed to process transactions for test user")
            
            # Verify batch operations
            mock_batch.commit.assert_called()

if __name__ == '__main__':
    unittest.main() 