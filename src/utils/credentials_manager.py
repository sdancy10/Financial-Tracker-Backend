from typing import Dict, Any
from google.cloud import secretmanager
from google.oauth2.credentials import Credentials
import google.auth.transport.requests
from googleapiclient.discovery import build
import json
import base64
import os
import logging
from src.utils.config import Config

class CredentialsManager:
    """Manages credentials for the application"""
    
    def __init__(self, project_id: str, config: Config):
        """Initialize the credentials manager"""
        self.project_id = project_id
        self.config = config
        self.client = secretmanager.SecretManagerServiceClient()
        self.logger = logging.getLogger(__name__)
        
    def initialize_from_file(self, credentials_path: str, auth_system: str = 'google'):
        """Initialize credentials from service account key - only used during initial deployment"""
        service_account_path = self.config.get('gcp', 'service_account_key_path')
        with open(service_account_path, 'r') as f:
            sa_creds = json.load(f)
        return {
            'user_nm': sa_creds['client_email'],
            'user_pw': sa_creds['private_key']
        }

    def get_secret(self, secret_id: str) -> Dict[str, str]:
        """Get a secret from Secret Manager"""
        try:
            # Get the secret
            name = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
            response = self.client.access_secret_version(request={"name": name})
            
            # Parse and return the secret data
            # Add padding if needed
            data = response.payload.data
            self.logger.debug(f"Raw data length: {len(data)}")
            self.logger.debug(f"Raw data: {data[:50]}...")  # Only log first 50 chars for security
            
            # Try to decode as string first
            try:
                str_data = data.decode('utf-8')
                self.logger.debug(f"String data length: {len(str_data)}")
                self.logger.debug(f"String data: {str_data[:50]}...")
                
                # If it's JSON, parse it directly
                try:
                    return json.loads(str_data)
                except json.JSONDecodeError:
                    pass
            except UnicodeDecodeError:
                pass
            
            # If not directly JSON, try base64 decoding
            try:
                padding = 4 - (len(data) % 4)
                if padding != 4:
                    data += b'=' * padding
                secret_data = base64.urlsafe_b64decode(data).decode()
                self.logger.debug(f"Decoded data length: {len(secret_data)}")
                self.logger.debug(f"Decoded data: {secret_data[:50]}...")
                return json.loads(secret_data)
            except Exception as e:
                self.logger.error(f"Error decoding base64: {str(e)}")
                raise
            
        except Exception as e:
            self.logger.error(f"Error retrieving secret: {str(e)}")
            raise

    def deploy_to_secret_manager(self, secret_data: Dict, secret_id: str) -> bool:
        """Deploy secret to GCP Secret Manager using discovery API"""
        try:
            # Build the Secret Manager API client
            service = build('secretmanager', 'v1')
            
            # Create secret if it doesn't exist
            secret_path = f"projects/{self.project_id}/secrets/{secret_id}"
            try:
                # Check if secret exists first
                service.projects().secrets().get(
                    name=secret_path
                ).execute()
                self.logger.debug(f"Secret {secret_id} already exists, adding new version")
            except Exception:
                # Secret doesn't exist, create it
                try:
                    service.projects().secrets().create(
                        parent=f"projects/{self.project_id}",
                        secretId=secret_id,
                        body={
                            "replication": {"automatic": {}}
                        }
                    ).execute()
                    self.logger.debug(f"Created new secret: {secret_id}")
                except Exception as e:
                    if "alreadyExists" in str(e):
                        self.logger.debug(f"Secret {secret_id} already exists, adding new version")
                    else:
                        self.logger.error(f"Error creating secret: {str(e)}")
                        return False

            try:
                # Add new version with secret data
                self.logger.debug(f"Deploying secret data with keys: {list(secret_data.keys())}")
                secret_data_bytes = json.dumps(secret_data).encode('UTF-8')
                
                # Use urlsafe base64 encoding with proper padding
                encoded_data = base64.urlsafe_b64encode(secret_data_bytes).decode('UTF-8')
                # Add padding if needed
                padding = 4 - (len(encoded_data) % 4)
                if padding != 4:
                    encoded_data += '=' * padding
                self.logger.debug(f"Encoded data length: {len(encoded_data)}")
                
                service.projects().secrets().addVersion(
                    parent=secret_path,
                    body={
                        "payload": {
                            "data": encoded_data
                        }
                    }
                ).execute()
                self.logger.debug(f"Successfully added new version to secret: {secret_id}")
                return True
            except Exception as e:
                self.logger.error(f"Error adding version to secret {secret_id}: {str(e)}")
                return False
            
        except Exception as e:
            self.logger.error(f"Error deploying secret {secret_id}: {str(e)}")
            return False

    def check_secrets_exist(self) -> bool:
        """Check if required secrets are already in GCP"""
        try:
            # Check both Google and Firebase credentials
            if not self.get_secret('google-credentials-default'):
                return False
            if not self.get_secret('firebase-credentials-default'):
                return False
            return True
        except Exception:
            return False

    def load_credentials_file(self) -> Dict:
        """Load and parse credentials using AuthUtil"""
        credentials = {}
        
        # Load Google credentials
        google_creds = self.auth_util.get_local_credentials('google')
        credentials['google'] = {
            'username': google_creds['user_nm'],
            'password': google_creds['user_pw']
        }
        
        # Load Firebase credentials
        firebase_creds = self.auth_util.get_local_credentials('firebase')
        credentials['firebase'] = {
            'username': firebase_creds['user_nm'],
            'password': firebase_creds['user_pw']
        }
        
        # Load user-specific credentials
        user_ids = [
            'aDer8RS94NPmPdAYGHQQpI3iWm13',
            '5oZfUgtSn0g1VaEa6VNpHVC51Zq2'
        ]
        
        for user_id in user_ids:
            user_creds = self.auth_util.get_local_credentials(user_id)
            credentials[user_id] = {
                'email': self.auth_util.get_email_for_user(user_id),
                'username': user_creds['user_nm'],
                'password': user_creds['user_pw']
            }
        
        return credentials

    def store_user_gmail_credentials(self, user_id: str, email: str, username: str, password: str, refresh_token: str) -> None:
        """Store Gmail credentials for a user in Secret Manager"""
        try:
            # Create a valid secret ID using only lowercase alphanumeric characters and underscores
            encoded_email = base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')
            user_id_clean = user_id.lower()  # Convert to lowercase
            secret_id = f"gmail_credentials_{user_id_clean}_{encoded_email}"
            
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
                        "userid": user_id_clean  # Use lowercase and no underscore in label key
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

            # Store credentials as secret version with OAuth2 fields
            credentials = {
                "username": username,  # This is the client_id
                "password": password,  # This is the client_secret
                "email": email,
                "client_id": username,  # Store client_id explicitly
                "client_secret": password,  # Store client_secret explicitly
                "refresh_token": refresh_token,  # Use the provided refresh token
                "token_uri": token_uri,
                "scopes": scopes
            }
            
            # Log credentials being stored (redacting sensitive info)
            self.logger.debug("Storing credentials in Secret Manager:")
            self.logger.debug(f"  username/client_id: {credentials['username']}")
            self.logger.debug(f"  password/client_secret: {'*' * (len(credentials['password']) if credentials['password'] else 0)}")
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
            
            self.logger.info(f"Successfully stored Gmail credentials for user {user_id}")
            
        except Exception as e:
            self.logger.error(f"Error storing Gmail credentials: {str(e)}")
            raise

    def store_default_credentials(self, credentials_type: str, username: str, password: str):
        """Store default credentials (Google or Firebase)"""
        secret_id = f"{credentials_type}-credentials-default"
        credentials = {
            'username': username,
            'password': password
        }
        self._store_secret(secret_id, credentials)

    def _store_secret(self, secret_id: str, data: Dict):
        """Store a secret in Secret Manager"""
        parent = f"projects/{self.project_id}"
        
        try:
            secret = self.client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": secret_id,
                    "secret": {"replication": {"automatic": {}}}
                }
            )
        except Exception:
            secret = self.client.get_secret(name=f"{parent}/secrets/{secret_id}")
        
        self.client.add_secret_version(
            request={
                "parent": secret.name,
                "payload": {"data": json.dumps(data).encode("UTF-8")}
            }
        ) 

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

    def get_user_gmail_credentials(self, user_id: str, email: str) -> Dict[str, Any]:
        """Get Gmail credentials for a user from Secret Manager or local file"""
        try:
            # Create a valid secret ID using only lowercase alphanumeric characters and underscores
            encoded_email = base64.urlsafe_b64encode(email.encode()).decode().replace('-', '_').replace('=', '')
            user_id_clean = user_id.lower()  # Convert to lowercase
            secret_id = f"gmail_credentials_{user_id_clean}_{encoded_email}"
            
            # First try to get credentials from Secret Manager
            try:
                secret_path = f"projects/{self.project_id}/secrets/{secret_id}/versions/latest"
                response = self.client.access_secret_version(request={"name": secret_path})
                credentials = json.loads(response.payload.data.decode())
                
                # Map username/password to client_id/client_secret if needed
                if 'username' in credentials and 'client_id' not in credentials:
                    credentials['client_id'] = credentials['username']
                if 'password' in credentials and 'client_secret' not in credentials:
                    credentials['client_secret'] = credentials['password']
                
                # Get token URI and scopes from config
                token_uri = self.config.get('auth', 'gmail', 'token_uri', default="https://oauth2.googleapis.com/token")
                scopes = self.config.get('auth', 'gmail', 'scopes')
                
                # Ensure token_uri is present
                if 'token_uri' not in credentials:
                    credentials['token_uri'] = token_uri
                
                # Ensure scopes are present
                if 'scopes' not in credentials:
                    credentials['scopes'] = scopes
                
                # Validate required fields
                required_fields = ['client_id', 'client_secret', 'refresh_token', 'token_uri', 'scopes']
                missing_fields = [field for field in required_fields if field not in credentials or not credentials[field]]
                if missing_fields:
                    raise ValueError(f"Missing or empty required fields in Secret Manager credentials: {missing_fields}")
                
                self.logger.info(f"Successfully retrieved credentials from Secret Manager for {email}")
                self.logger.debug(f"Retrieved credentials fields from Secret Manager: {list(credentials.keys())}")
                self.logger.debug(f"Refresh token present: {bool(credentials.get('refresh_token'))}")
            except Exception as e:
                self.logger.warning(f"Failed to retrieve credentials from Secret Manager: {str(e)}")
                
                # Check if running in GCP environment
                is_gcp = os.getenv('GOOGLE_CLOUD_PROJECT') is not None
                if is_gcp:
                    self.logger.error("Running in GCP but failed to retrieve credentials from Secret Manager")
                    raise
                
                # If running locally, try to load from local file
                self.logger.info("Running locally, attempting to load credentials from local file")
                credentials_file = os.path.join('credentials', f'gmail_oauth_credentials_{email.split("@")[0].lower()}.json')
                self.logger.debug(f"Loading credentials from: {credentials_file}")
                
                try:
                    with open(credentials_file, 'r') as f:
                        credentials = json.load(f)
                    
                    self.logger.debug(f"Loaded credentials fields: {list(credentials.keys())}")
                    
                    # Ensure required fields are present
                    required_fields = ['client_id', 'client_secret', 'refresh_token', 'token_uri']
                    missing_fields = [field for field in required_fields if field not in credentials]
                    if missing_fields:
                        raise ValueError(f"Missing required fields in credentials file: {missing_fields}")
                    
                    # Ensure scopes are present
                    if 'scopes' not in credentials:
                        credentials['scopes'] = self.config.get('auth', 'gmail', 'scopes')
                    
                    # Add email and user_id to credentials
                    credentials['email'] = email
                    credentials['user_id'] = user_id
                    
                    # Store credentials in Secret Manager for future use
                    try:
                        self.store_user_gmail_credentials(
                            user_id=user_id,
                            email=email,
                            username=credentials['client_id'],  # Use client_id from file
                            password=credentials['client_secret'],  # Use client_secret from file
                            refresh_token=credentials['refresh_token']  # Use refresh_token from file
                        )
                        self.logger.info(f"Successfully stored credentials in Secret Manager for {email}")
                    except Exception as store_error:
                        self.logger.warning(f"Failed to store credentials in Secret Manager: {str(store_error)}")
                except Exception as local_error:
                    self.logger.error(f"Error reading local credentials file {credentials_file}: {str(local_error)}")
                    raise
            
            # Create OAuth2 credentials object
            self.logger.debug("Creating OAuth2 credentials...")
            oauth2_credentials = self._create_oauth2_credentials(credentials)
            self.logger.debug(f"Created OAuth2 credentials with fields: refresh_token={oauth2_credentials.refresh_token is not None}, token_uri={oauth2_credentials.token_uri}, client_id={oauth2_credentials.client_id}, client_secret={oauth2_credentials.client_secret is not None}, scopes={oauth2_credentials.scopes}")
            
            # Return both the OAuth2 credentials and the original dictionary
            credentials['oauth2_credentials'] = oauth2_credentials
            return credentials
                
        except Exception as e:
            self.logger.error(f"Error retrieving Gmail credentials: {str(e)}")
            raise 