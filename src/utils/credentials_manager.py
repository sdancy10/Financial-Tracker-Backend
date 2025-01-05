from typing import Dict, Any, Optional
from google.cloud import secretmanager
from google.oauth2.credentials import Credentials
from google.oauth2 import service_account
import google.auth.transport.requests
from googleapiclient.discovery import build
import json
import base64
import os
import logging
from src.utils.config import Config

class CredentialsManager:
    """Manages both service account and OAuth2 credentials."""
    
    def __init__(self, project_id: str, config: Config):
        """Initialize the credentials manager.
        
        Args:
            project_id: GCP project ID
            config: Application configuration
        """
        self.project_id = project_id
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize service account credentials for GCP operations
        self.service_account_credentials = self._get_service_account_credentials()
        
        # Initialize Secret Manager client with service account credentials
        self.client = secretmanager.SecretManagerServiceClient(credentials=self.service_account_credentials)
    
    def _get_service_account_credentials(self) -> service_account.Credentials:
        """Get service account credentials for GCP operations."""
        try:
            self.logger.info("Attempting to get service account credentials")
            # First try to use ADC (Application Default Credentials)
            self.logger.info("Trying Application Default Credentials (ADC)...")
            credentials, project = google.auth.default()
            self.logger.info(f"Successfully obtained ADC credentials for project: {project}")
            if hasattr(credentials, 'service_account_email'):
                self.logger.info(f"Using service account: {credentials.service_account_email}")
            return credentials
        except Exception as e:
            self.logger.info(f"ADC not found: {str(e)}, trying service account key file")
            
            # Try to get service account key path from config
            key_path = self.config.get('gcp', 'service_account_key_path')
            if not key_path:
                self.logger.error("No service account key path found in config")
                raise ValueError("No service account key path found in config")
            
            self.logger.info(f"Loading service account key from: {key_path}")
            
            # Load service account credentials from file
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    key_path,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                self.logger.info(f"Successfully loaded service account credentials from {key_path}")
                if hasattr(credentials, 'service_account_email'):
                    self.logger.info(f"Service account email: {credentials.service_account_email}")
                return credentials
            except Exception as key_error:
                self.logger.error(f"Error loading service account key: {str(key_error)}")
                if hasattr(key_error, 'details'):
                    self.logger.error(f"Error details: {key_error.details}")
                raise

    def get_user_gmail_credentials(self, user_id: str, email: str) -> Dict[str, Any]:
        """Get Gmail OAuth2 credentials for a user from Secret Manager or local file."""
        try:
            self.logger.info(f"Attempting to get Gmail credentials for user_id={user_id}, email={email}")
            
            # Get the secret pattern from config
            secret_pattern = self.config.get('data', 'credentials', 'secret_pattern')
            self.logger.info(f"Using secret pattern: {secret_pattern}")
            if not secret_pattern:
                secret_pattern = "gmail-credentials-{user_id}-{email}"  # Default pattern
                self.logger.info(f"No pattern found in config, using default: {secret_pattern}")
            
            # Create the secret ID using the pattern from config
            encoded_email = base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')
            user_id_clean = user_id.lower()  # Convert to lowercase
            secret_id = secret_pattern.format(user_id=user_id_clean, email=encoded_email)
            self.logger.info(f"Generated secret ID: {secret_id}")
            
            # First try to get OAuth2 credentials from Secret Manager
            try:
                response = None
                # Try with string project ID first
                secret_path = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
                self.logger.info(f"Attempting to access secret at path: {secret_path}")
                self.logger.info(f"Using project ID: {self.project_id}")
                self.logger.info(f"Current service account email: {self.service_account_credentials.service_account_email if hasattr(self.service_account_credentials, 'service_account_email') else 'default'}")
                
                try:
                    self.logger.info("Making request to Secret Manager...")
                    request = {"name": secret_path}
                    self.logger.info(f"Request details: {request}")
                    response = self.client.access_secret_version(request=request)
                    self.logger.info("Successfully retrieved secret from Secret Manager")
                except Exception as e:
                    self.logger.error(f"Failed to access secret: {str(e)}")
                    self.logger.error(f"Error type: {type(e).__name__}")
                    if hasattr(e, 'details'):
                        self.logger.error(f"Error details: {e.details}")
                    if hasattr(e, 'response'):
                        self.logger.error(f"Response status: {e.response.status if hasattr(e.response, 'status') else 'unknown'}")
                        self.logger.error(f"Response headers: {e.response.headers if hasattr(e.response, 'headers') else 'unknown'}")
                    
                    if "not found" in str(e).lower():
                        # If not found, try with numeric project ID from credentials
                        _, project = google.auth.default()
                        if project and project != self.project_id:
                            self.logger.info(f"Retrying with numeric project ID: {project}")
                            secret_path = f"projects/{project}/secrets/{secret_id}/versions/latest"
                            self.logger.info(f"New secret path: {secret_path}")
                            response = self.client.access_secret_version(request={"name": secret_path})
                    else:
                        raise
                
                if response is None:
                    raise ValueError("Failed to access secret in both project formats")
                
                credentials = json.loads(response.payload.data.decode())
                self.logger.debug("Successfully decoded secret data")
                
                # Get token URI and scopes from config
                token_uri = self.config.get('auth', 'gmail', 'token_uri', default="https://oauth2.googleapis.com/token")
                scopes = self.config.get('auth', 'gmail', 'scopes')
                self.logger.debug(f"Using token URI: {token_uri}")
                self.logger.debug(f"Using scopes: {scopes}")
                
                # Ensure token_uri and scopes are present
                if 'token_uri' not in credentials:
                    self.logger.debug("Adding token_uri to credentials")
                    credentials['token_uri'] = token_uri
                if 'scopes' not in credentials:
                    self.logger.debug("Adding scopes to credentials")
                    credentials['scopes'] = scopes
                
                # Validate required OAuth2 fields
                required_fields = ['client_id', 'client_secret', 'refresh_token', 'token_uri', 'scopes']
                missing_fields = [field for field in required_fields if field not in credentials or not credentials[field]]
                if missing_fields:
                    self.logger.error(f"Missing required fields in credentials: {missing_fields}")
                    raise ValueError(f"Missing or empty required OAuth2 fields in Secret Manager credentials: {missing_fields}")
                
                self.logger.info(f"Successfully retrieved OAuth2 credentials from Secret Manager for {email}")
                self.logger.debug(f"Retrieved OAuth2 credentials fields: {list(credentials.keys())}")
                self.logger.debug(f"Refresh token present: {bool(credentials.get('refresh_token'))}")
                
            except Exception as e:
                self.logger.warning(f"Failed to retrieve OAuth2 credentials from Secret Manager: {str(e)}")
                self.logger.debug(f"Full error details: {repr(e)}")
                
                # Check if running in GCP environment
                is_gcp = os.getenv('GOOGLE_CLOUD_PROJECT') is not None
                self.logger.debug(f"Running in GCP environment: {is_gcp}")
                if is_gcp:
                    self.logger.error("Running in GCP but failed to retrieve OAuth2 credentials from Secret Manager")
                    raise
                
                # Check if this user is configured in config.yaml
                auth_config = self.config.get('auth', 'gmail')
                email_to_account = auth_config.get('email_to_account', {})
                accounts = auth_config.get('accounts', {})
                
                # Find the account name for this email
                account_name = email_to_account.get(email)
                if not account_name:
                    raise ValueError(f"Email {email} not found in config.yaml auth.gmail.email_to_account")
                
                # Get the account config
                account_config = accounts.get(account_name)
                if not account_config:
                    raise ValueError(f"Account {account_name} not found in config.yaml auth.gmail.accounts")
                
                # Verify user_id matches
                if account_config.get('user_id') != user_id:
                    raise ValueError(f"User ID mismatch for {email}: expected {account_config.get('user_id')}, got {user_id}")
                
                # Get credentials file path from config
                credentials_file = account_config.get('credentials_file')
                if not credentials_file:
                    raise ValueError(f"No credentials_file specified for account {account_name} in config.yaml")
                
                # If running locally, try to load from local file
                self.logger.info("Running locally, attempting to load OAuth2 credentials from local file")
                self.logger.debug(f"Loading OAuth2 credentials from: {credentials_file}")
                
                try:
                    with open(credentials_file, 'r') as f:
                        credentials = json.load(f)
                    
                    self.logger.debug(f"Loaded OAuth2 credentials fields: {list(credentials.keys())}")
                    
                    # Ensure required OAuth2 fields are present
                    required_fields = ['client_id', 'client_secret', 'refresh_token', 'token_uri']
                    missing_fields = [field for field in required_fields if field not in credentials]
                    if missing_fields:
                        raise ValueError(f"Missing required OAuth2 fields in credentials file: {missing_fields}")
                    
                    # Ensure scopes are present
                    if 'scopes' not in credentials:
                        credentials['scopes'] = self.config.get('auth', 'gmail', 'scopes')
                    
                    # Add email and user_id to credentials
                    credentials['email'] = email
                    credentials['user_id'] = user_id
                    
                    # Store OAuth2 credentials in Secret Manager for future use
                    try:
                        self.store_user_gmail_credentials(
                            user_id=user_id,
                            email=email,
                            username=credentials['client_id'],
                            password=credentials['client_secret'],
                            refresh_token=credentials['refresh_token']
                        )
                        self.logger.info(f"Successfully stored OAuth2 credentials in Secret Manager for {email}")
                    except Exception as store_error:
                        self.logger.warning(f"Failed to store OAuth2 credentials in Secret Manager: {str(store_error)}")
                except Exception as local_error:
                    self.logger.error(f"Error reading local OAuth2 credentials file {credentials_file}: {str(local_error)}")
                    raise
            
            # Create OAuth2 credentials object for Gmail API
            self.logger.debug("Creating OAuth2 credentials for Gmail API...")
            oauth2_credentials = self._create_oauth2_credentials(credentials)
            self.logger.debug(f"Created OAuth2 credentials with fields: refresh_token={oauth2_credentials.refresh_token is not None}, token_uri={oauth2_credentials.token_uri}, client_id={oauth2_credentials.client_id}, client_secret={oauth2_credentials.client_secret is not None}, scopes={oauth2_credentials.scopes}")
            
            # Return both the OAuth2 credentials and the original dictionary
            credentials['oauth2_credentials'] = oauth2_credentials
            return credentials
                
        except Exception as e:
            self.logger.error(f"Error retrieving Gmail OAuth2 credentials: {str(e)}")
            raise

    def store_user_gmail_credentials(self, user_id: str, email: str, username: str, password: str, refresh_token: str) -> None:
        """Store Gmail OAuth2 credentials for a user in Secret Manager"""
        try:
            # Get the secret pattern from config
            secret_pattern = self.config.get('data', 'credentials', 'secret_pattern')
            if not secret_pattern:
                secret_pattern = "gmail-credentials-{user_id}-{email}"  # Default pattern
            
            # Create the secret ID using the pattern from config
            encoded_email = base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')
            user_id_clean = user_id.lower()  # Convert to lowercase
            secret_id = secret_pattern.format(user_id=user_id_clean, email=encoded_email)
            
            # Create secret if it doesn't exist
            parent = f"projects/{self.project_id}"
            secret_path = f"{parent}/secrets/{secret_id}"
            
            try:
                self.client.get_secret(request={"name": secret_path})
            except Exception:
                # Secret doesn't exist, create it
                secret = {
                    "replication": {"automatic": {}},
                    "labels": {
                        "email": encoded_email.lower(),  # Ensure label value is lowercase
                        "userid": user_id_clean,  # Use lowercase and no underscore in label key
                        "type": "gmail_oauth2"  # Mark this as Gmail OAuth2 credentials
                    }
                }
                self.client.create_secret(
                    request={
                        "parent": parent,
                        "secret_id": secret_id,
                        "secret": secret
                    }
                )

            # Get scopes and token URI from config
            scopes = self.config.get('auth', 'gmail', 'scopes')
            token_uri = self.config.get('auth', 'gmail', 'token_uri', default="https://oauth2.googleapis.com/token")
            if not scopes:
                raise ValueError("No Gmail scopes found in config file")

            # Store OAuth2 credentials as secret version
            credentials = {
                "client_id": username,  # OAuth2 client ID
                "client_secret": password,  # OAuth2 client secret
                "email": email,
                "refresh_token": refresh_token,  # OAuth2 refresh token
                "token_uri": token_uri,
                "scopes": scopes
            }
            
            # Log credentials being stored (redacting sensitive info)
            self.logger.debug("Storing OAuth2 credentials in Secret Manager:")
            self.logger.debug(f"  email: {credentials['email']}")
            self.logger.debug(f"  client_id: {credentials['client_id']}")
            self.logger.debug(f"  client_secret: {'*' * (len(credentials['client_secret']) if credentials['client_secret'] else 0)}")
            self.logger.debug(f"  refresh_token: {'*' * (len(credentials['refresh_token']) if credentials['refresh_token'] else 0)} (is_none={credentials['refresh_token'] is None})")
            self.logger.debug(f"  token_uri: {credentials['token_uri']}")
            self.logger.debug(f"  scopes: {credentials['scopes']}")
            
            payload = json.dumps(credentials).encode()
            
            self.client.add_secret_version(
                request={
                    "parent": secret_path,
                    "payload": {"data": payload}
                }
            )
            
            self.logger.info(f"Successfully stored Gmail OAuth2 credentials for user {user_id}")
            
        except Exception as e:
            self.logger.error(f"Error storing Gmail OAuth2 credentials: {str(e)}")
            raise

    def _create_oauth2_credentials(self, credentials: Dict[str, Any]) -> Credentials:
        """Create OAuth2 credentials object from dictionary"""
        # Map username/password to client_id/client_secret if needed
        if 'username' in credentials and 'client_id' not in credentials:
            credentials['client_id'] = credentials['username']
        if 'password' in credentials and 'client_secret' not in credentials:
            credentials['client_secret'] = credentials['password']

        # Ensure all required fields are present
        required_fields = ['client_id', 'client_secret', 'refresh_token', 'token_uri', 'scopes']
        missing_fields = [field for field in required_fields if field not in credentials]
        if missing_fields:
            raise ValueError(f"Missing required OAuth2 fields: {missing_fields}")
        
        # Log values for debugging (redacting sensitive info)
        self.logger.debug("Creating OAuth2 credentials with values:")
        self.logger.debug(f"  client_id: {credentials['client_id']}")
        self.logger.debug(f"  client_secret: {'*' * (len(credentials['client_secret']) if credentials['client_secret'] else 0)}")
        self.logger.debug(f"  refresh_token: {'*' * (len(credentials['refresh_token']) if credentials['refresh_token'] else 0)} (is_none={credentials['refresh_token'] is None})")
        self.logger.debug(f"  token_uri: {credentials['token_uri']}")
        self.logger.debug(f"  scopes: {credentials['scopes']}")
        
        # Create OAuth2 credentials object
        oauth2_credentials = Credentials(
            token=None,  # Start with no token, will be obtained through refresh
            refresh_token=credentials['refresh_token'],
            token_uri=credentials['token_uri'],
            client_id=credentials['client_id'],
            client_secret=credentials['client_secret'],
            scopes=credentials['scopes']
        )
        
        # Force a refresh to get a valid access token
        request = google.auth.transport.requests.Request()
        oauth2_credentials.refresh(request)
        
        return oauth2_credentials 