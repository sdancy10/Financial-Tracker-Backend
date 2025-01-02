from typing import Dict, Any, List
from src.models.transaction import Transaction
from src.utils.transaction_dao import TransactionDAO
from src.utils.credentials_manager import CredentialsManager
from src.utils.gmail_util import GmailUtil
from src.utils.validation import TransactionValidator
from src.utils.config import Config
import logging
from datetime import datetime
from google.cloud import firestore
import os

class TransactionService:
    """Service for handling transaction processing operations"""
    
    # Default users to enable email sync for first run
    DEFAULT_SYNC_USERS = [
        'aDer8RS94NPmPdAYGHQQpI3iWm13',
        '5oZfUgtSn0g1VaEa6VNpHVC51Zq2'
    ]
    
    def __init__(self, project_id: str):
        """Initialize the transaction service"""
        self.project_id = project_id
        self.config = Config()
        self.dao = TransactionDAO(project_id)
        self.cred_manager = CredentialsManager(project_id, self.config)
        self.validator = TransactionValidator()
        self.db = firestore.Client(project=project_id)
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        logging_config = self.config.get('logging')
        logging.basicConfig(
            level=logging_config['level'],
            format=logging_config['format']
        )
        
        # Get sync interval from config
        self.sync_interval = self.config.get('data', 'sync_interval')
    
    def setup_first_run(self) -> None:
        """Set up initial sync settings for default users"""
        try:
            batch = self.db.batch()
            now = datetime.utcnow()
            
            # Default user credentials
            default_credentials = {
                'aDer8RS94NPmPdAYGHQQpI3iWm13': {
                    'email': 'clairejablonski@gmail.com',
                    'username': 'clairejablonski@gmail.com',
                    'password': 'your_app_specific_password',  # Replace with actual app-specific password
                    'client_id': os.environ.get('GMAIL_CLIENT_ID'),
                    'client_secret': os.environ.get('GMAIL_CLIENT_SECRET'),
                    'refresh_token': os.environ.get('GMAIL_REFRESH_TOKEN'),
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'scopes': ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']
                },
                '5oZfUgtSn0g1VaEa6VNpHVC51Zq2': {
                    'email': 'sdancy.10@gmail.com',
                    'username': 'sdancy.10@gmail.com',
                    'password': 'your_app_specific_password',  # Replace with actual app-specific password
                    'client_id': os.environ.get('GMAIL_CLIENT_ID'),
                    'client_secret': os.environ.get('GMAIL_CLIENT_SECRET'),
                    'refresh_token': os.environ.get('GMAIL_REFRESH_TOKEN'),
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'scopes': ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']
                }
            }
            
            for user_id in self.DEFAULT_SYNC_USERS:
                user_ref = self.db.collection('users').document(user_id)
                user_doc = user_ref.get()
                
                if user_doc.exists:
                    user_data = user_doc.to_dict()
                    sync_settings = {
                        'email_sync_enabled': True,
                        'last_sync': None,
                        'last_sync_status': None,
                        'sync_settings': {
                            'created_at': now.isoformat(),
                            'updated_at': now.isoformat(),
                            'created_by': 'system',
                            'updated_by': 'system'
                        }
                    }
                    
                    # Update user document
                    batch.update(user_ref, sync_settings)
                    self.logger.info(f"Enabled email sync for default user {user_id}")
                    
                    # Store Gmail credentials in Secret Manager
                    if user_id in default_credentials:
                        creds = default_credentials[user_id]
                        self.cred_manager.store_user_gmail_credentials(
                            user_id=user_id,
                            email=creds['email'],
                            username=creds['username'],
                            password=creds['password'],
                            refresh_token=creds.get('refresh_token', '')  # Add refresh token
                        )
                        self.logger.info(f"Stored Gmail credentials for user {user_id}")
            
            batch.commit()
            self.logger.info("Completed first run setup")
            
        except Exception as e:
            self.logger.error(f"Error in first run setup: {str(e)}")
    
    def get_user_credentials(self) -> List[Dict[str, Any]]:
        """Get all user credentials from Secret Manager for users in Firebase"""
        user_creds = []
        
        try:
            # Check if first run setup is needed
            first_run = True
            for user_id in self.DEFAULT_SYNC_USERS:
                user_ref = self.db.collection('users').document(user_id)
                user_doc = user_ref.get()
                if user_doc.exists and user_doc.to_dict().get('email_sync_enabled') is not None:
                    first_run = False
                    break
            
            if first_run:
                self.logger.info("First run detected, setting up default users")
                self.setup_first_run()
            
            # Get all users from Firebase
            users_ref = self.db.collection('users')
            users = users_ref.stream()
            
            # Process users in batches to avoid memory issues
            batch_size = self.config.get('data', 'user_batch_size') or 10
            user_batch = []
            
            for user in users:
                user_data = user.to_dict()
                user_id = user.id
                
                # Check if user has email sync enabled
                if not user_data.get('email_sync_enabled', False):
                    self.logger.info(f"Email sync disabled for user {user_id}")
                    continue
                
                # Get email from contact information
                email = user_data.get('contactInformation', {}).get('_email')
                if not email:
                    self.logger.warning(f"No email found for user {user_id}")
                    continue
                
                # Get user's Gmail credentials from Secret Manager
                try:
                    creds = self.cred_manager.get_user_gmail_credentials(user_id, email)
                    if creds:
                        user_creds.append({
                            'user_id': user_id,
                            'email': email,
                            'username': creds.get('username'),
                            'password': creds.get('password'),
                            'client_id': creds.get('client_id'),
                            'client_secret': creds.get('client_secret'),
                            'refresh_token': creds.get('refresh_token'),
                            'token_uri': creds.get('token_uri', 'https://oauth2.googleapis.com/token'),
                            'scopes': creds.get('scopes', ['https://www.googleapis.com/auth/gmail.readonly']),
                            'last_sync': user_data.get('last_sync')
                        })
                        self.logger.info(f"Retrieved credentials for user {email}")
                        
                        user_batch.append(user_id)
                        if len(user_batch) >= batch_size:
                            # Update last sync time for batch
                            self._update_last_sync(user_batch)
                            user_batch = []
                except Exception as e:
                    self.logger.error(f"Error retrieving credentials for user {user_id}: {str(e)}")
                    continue
            
            # Update last sync time for remaining users
            if user_batch:
                self._update_last_sync(user_batch)
            
            return user_creds
        except Exception as e:
            self.logger.error(f"Error retrieving user credentials: {str(e)}")
            return user_creds
    
    def _update_last_sync(self, user_ids: List[str]) -> None:
        """Update last sync time for a batch of users"""
        try:
            batch = self.db.batch()
            now = datetime.utcnow()
            
            for user_id in user_ids:
                user_ref = self.db.collection('users').document(user_id)
                batch.update(user_ref, {
                    'last_sync': now.isoformat(),
                    'last_sync_status': 'success'
                })
            
            batch.commit()
        except Exception as e:
            self.logger.error(f"Error updating last sync time: {str(e)}")
    
    def process_user_transactions(self, user_credentials: Dict[str, Any]) -> bool:
        """Process transactions for a single user"""
        try:
            # Create OAuth2 credentials
            oauth2_creds = self.cred_manager._create_oauth2_credentials(user_credentials)
            user_credentials['oauth2_credentials'] = oauth2_creds
            
            # Initialize Gmail utility with OAuth credentials
            gmail = GmailUtil(user_credentials)
            
            # Always check unread transaction emails
            unread_query = 'label:Transactions is:unread'
            self.logger.info(f"Fetching unread transaction emails with query: {unread_query}")
            unread_transactions = gmail.fetch_transaction_emails(unread_query)
            
            # Check for additional emails after last sync if available
            sync_transactions = []
            if user_credentials.get('last_sync'):
                sync_query = f'label:Transactions after:{user_credentials["last_sync"]}'
                self.logger.info(f"Fetching additional emails after last sync with query: {sync_query}")
                sync_transactions = gmail.fetch_transaction_emails(sync_query)
            
            # Combine results, ensuring no duplicates by message ID
            seen_message_ids = set()
            raw_transactions_with_ids = []
            
            # Add unread transactions first
            for transaction, message_id in unread_transactions:
                if message_id not in seen_message_ids:
                    seen_message_ids.add(message_id)
                    if transaction:  # Transaction was successfully parsed
                        self.logger.info(f"Found unread transaction with message ID: {message_id}")
                        raw_transactions_with_ids.append((transaction, message_id))
                    else:  # Failed to parse transaction
                        self.logger.warning(f"Failed to parse transaction from email {message_id} for {user_credentials['email']}")
            
            # Add transactions after last sync
            for transaction, message_id in sync_transactions:
                if message_id not in seen_message_ids:
                    seen_message_ids.add(message_id)
                    if transaction:  # Transaction was successfully parsed
                        raw_transactions_with_ids.append((transaction, message_id))
                    else:  # Failed to parse transaction
                        self.logger.warning(f"Failed to parse transaction from email {message_id} for {user_credentials['email']}")
            
            if not raw_transactions_with_ids:
                self.logger.info(f"No new transactions found for {user_credentials['email']}")
                return True
            
            self.logger.info(f"Found {len(raw_transactions_with_ids)} raw transactions")
            
            # Process and store transactions
            successful_transactions = 0
            failed_transactions = 0
            
            for raw_transaction, message_id in raw_transactions_with_ids:
                self.logger.info(f"Processing message ID: {message_id}")
                # Add user info
                raw_transaction['user_id'] = user_credentials['user_id']
                raw_transaction['account_id'] = f"gmail_{user_credentials['email']}"
                
                self.logger.info(f"Processing transaction: {raw_transaction}")
                
                # Remove fields not in Transaction model
                template_used = raw_transaction.pop('template_used', None)
                account = raw_transaction.pop('account', None)
                self.logger.debug(f"Using template: {template_used}, Account: {account}")
                
                # Get vendor value, defaulting to 'Unknown transaction'
                vendor = raw_transaction.get('vendor', 'Unknown transaction')
                
                # Ensure date is in ISO format with UTC timezone
                date_str = raw_transaction.get('date', '')
                if date_str:
                    try:
                        # If date doesn't have time info, append UTC midnight time
                        if 'T' not in date_str:
                            date_str = f"{date_str}T00:00:00+00:00"
                        # Ensure UTC timezone
                        elif not date_str.endswith('Z') and '+' not in date_str and '-' not in date_str:
                            date_str = f"{date_str}+00:00"
                    except ValueError:
                        self.logger.error(f"Invalid date format in transaction: {date_str}")
                        date_str = datetime.utcnow().isoformat()
                else:
                    date_str = datetime.utcnow().isoformat()
                
                # Map fields to Transaction model with all possible fields
                transaction_data = {
                    # Required fields
                    'id': raw_transaction.get('id'),  # Original Message-ID
                    'id_api': raw_transaction.get('id_api'),  # Gmail API ID
                    'amount': raw_transaction.get('amount'),
                    'vendor': vendor,
                    'account': account,  # Keep the account field
                    'template_used': template_used,  # Keep the template field
                    
                    # Date and time fields
                    'date': date_str,
                    
                    # Metadata fields
                    'description': vendor,  # Use vendor as description
                    'account_id': raw_transaction.get('account_id'),
                    'user_id': raw_transaction.get('user_id'),
                    
                    # Vendor processing fields
                    'vendor_cleaned': None,  # Will be populated by DAO
                    'cleaned_metaphone': None,  # Will be populated by DAO
                    
                    # Categorization fields (defaults)
                    'predicted_category': 'Uncategorized',
                    'predicted_subcategory': None,
                    
                    # Status fields
                    'status': 'processed',
                    
                    # Date components will be populated by DAO
                    'day': None,
                    'day_name': None,
                    'month': None,
                    'year': None
                }
                
                # Validate transaction
                is_valid, errors = self.validator.validate_transaction(transaction_data)
                if not is_valid:
                    self.logger.error(
                        f"Invalid transaction for email {message_id}. "
                        f"Missing or invalid fields: {errors}. "
                        f"Email will remain unread."
                    )
                    failed_transactions += 1
                    continue
                
                # Convert to Transaction model
                try:
                    # Create a copy of transaction_data for the Transaction model
                    # Remove fields not in Transaction model before creating the object
                    model_data = transaction_data.copy()
                    fields_to_remove = [
                        'account', 'template_used', 'vendor_cleaned', 'cleaned_metaphone',
                        'predicted_category', 'predicted_subcategory', 'day', 'day_name',
                        'month', 'year'
                    ]
                    for field in fields_to_remove:
                        model_data.pop(field, None)
                    
                    transaction = Transaction.from_dict(model_data)
                    
                    # Convert back to dict and merge with the original data to preserve all fields
                    final_data = transaction.to_dict()
                    final_data.update({
                        'account': account,
                        'template_used': template_used,
                        'vendor_cleaned': transaction_data['vendor_cleaned'],
                        'cleaned_metaphone': transaction_data['cleaned_metaphone'],
                        'predicted_category': transaction_data['predicted_category'],
                        'predicted_subcategory': transaction_data['predicted_subcategory'],
                        'day': transaction_data['day'],
                        'day_name': transaction_data['day_name'],
                        'month': transaction_data['month'],
                        'year': transaction_data['year'],
                        'id_api': transaction_data['id_api']  # Ensure id_api is preserved
                    })
                    
                except Exception as e:
                    self.logger.error(
                        f"Failed to create Transaction object for email {message_id}: {str(e)}. "
                        f"Email will remain unread."
                    )
                    failed_transactions += 1
                    continue
                
                # Store transaction with all fields
                self.logger.info(f"Storing transaction data: {final_data}")  # Add debug logging
                self.logger.info(f"Required fields: id={final_data.get('id')}, amount={final_data.get('amount')}, vendor={final_data.get('vendor')}, account={final_data.get('account')}, template_used={final_data.get('template_used')}")  # Add debug logging for required fields
                if self.dao.store_transaction(final_data, user_credentials['user_id']):
                    successful_transactions += 1
                    # Only mark as read after successful storage
                    if gmail.mark_as_read(message_id):
                        self.logger.info(
                            f"Successfully processed and marked email {message_id} as read. "
                            f"Transaction stored with ID: {transaction.id}"
                        )
                    else:
                        self.logger.error(
                            f"Transaction stored but failed to mark email {message_id} as read. "
                            f"Transaction ID: {transaction.id}"
                        )
                else:
                    self.logger.error(
                        f"Failed to store transaction {transaction.id} from email {message_id}. "
                        f"Email will remain unread."
                    )
                    failed_transactions += 1
            
            self.logger.info(
                f"Processed {len(raw_transactions_with_ids)} transactions for {user_credentials['email']} "
                f"(Success: {successful_transactions}, Failed: {failed_transactions})"
            )
            
            # Consider the process successful if at least some transactions were processed
            return successful_transactions > 0
            
        except Exception as e:
            self.logger.error(
                f"Error processing transactions for {user_credentials['email']}: {str(e)}"
            )
            return False
    
    def process_all_users(self) -> Dict[str, Any]:
        """Process transactions for all users"""
        results = {
            'success': [],
            'failed': [],
            'start_time': datetime.now().isoformat(),
            'end_time': None,
            'total_users': 0,
            'processed_users': 0
        }
        
        try:
            user_credentials = self.get_user_credentials()
            results['total_users'] = len(user_credentials)
            
            for creds in user_credentials:
                if self.process_user_transactions(creds):
                    results['success'].append(creds['email'])
                else:
                    results['failed'].append(creds['email'])
                results['processed_users'] += 1
            
        except Exception as e:
            self.logger.error(f"Error in process_all_users: {str(e)}")
        finally:
            results['end_time'] = datetime.now().isoformat()
            self.logger.info(f"Processing complete: {results}")
        
        return results 