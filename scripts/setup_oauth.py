import os
import sys
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import logging

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

def setup_oauth(account_identifier: str = None):
    """Set up OAuth2 credentials for Gmail access"""
    try:
        print("\n=== Setting up OAuth2 for Gmail ===")
        
        # Get account identifier if not provided
        if not account_identifier:
            print("\nAvailable accounts:")
            print("1. sdancy.10@gmail.com")
            print("2. clairejablonski@gmail.com")
            choice = input("\nSelect account (1 or 2): ").strip()
            account_identifier = "sdancy" if choice == "1" else "claire" if choice == "2" else None
            if not account_identifier:
                print("Invalid choice. Please select 1 or 2.")
                return
        
        # Enable detailed logging
        logging.basicConfig(level=logging.DEBUG)
        
        # Check if credentials file exists
        client_secrets_file = os.path.join(project_root, 'credentials', 'financial-tracker-gmail-access-oauth2.json')
        if not os.path.exists(client_secrets_file):
            print("\nError: OAuth2 credentials file not found!")
            print(f"Expected location: {client_secrets_file}")
            return
        
        # Define the required scopes
        SCOPES = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.modify'
        ]
        
        # Create the flow
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_file,
            scopes=SCOPES,
            redirect_uri='http://localhost:8080/'
        )
        
        # Run the OAuth flow
        print(f"\nOpening browser for OAuth authorization...")
        print("Please sign in with the selected Gmail account!")
        print("Using redirect URI: http://localhost:8080/")
        credentials = flow.run_local_server(
            port=8080,
            prompt='consent',
            access_type='offline'
        )
        
        # Save the credentials
        creds_data = {
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'scopes': credentials.scopes
        }
        
        output_file = os.path.join(project_root, 'credentials', f'gmail_oauth_credentials_{account_identifier}.json')
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, 'w') as f:
            json.dump(creds_data, f, indent=2)
        
        print(f"\n✓ OAuth2 credentials saved to {output_file}")
        print("\nYou can now use these credentials to update the config.yaml file")
        print("or set them as environment variables:")
        print(f"GMAIL_CLIENT_ID_{account_identifier.upper()}={credentials.client_id}")
        print(f"GMAIL_CLIENT_SECRET_{account_identifier.upper()}={credentials.client_secret}")
        print(f"GMAIL_REFRESH_TOKEN_{account_identifier.upper()}={credentials.refresh_token}")
        
    except Exception as e:
        print(f"\nError setting up OAuth2: {str(e)}")
        print("\nPlease make sure you have configured the following redirect URI in Google Cloud Console:")
        print("http://localhost:8080/")
        sys.exit(1)

if __name__ == "__main__":
    # Check if account identifier was provided as command line argument
    account_id = sys.argv[1] if len(sys.argv) > 1 else None
    setup_oauth(account_id) 