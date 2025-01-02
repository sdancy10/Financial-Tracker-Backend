from googleapiclient.discovery import build
from google.api_core import exceptions
from src.utils.config import Config

def setup_service_accounts():
    """Set up required service accounts for the project"""
    config = Config()
    project_id = config.get('project', 'id')

    # Build the IAM Admin API client
    service = build("iam", "v1")
    
    # The ID (short name) of your desired service account
    service_account_id = f"{project_id}-compute"
    
    # The full email Google auto-generates for the new service account:
    compute_sa_email = f"{service_account_id}@{project_id}.iam.gserviceaccount.com"
    
    try:
        print(f"Setting up compute service account: {compute_sa_email}")
        
        try:
            # First check if the service account exists
            service.projects().serviceAccounts().get(
                name=f"projects/{project_id}/serviceAccounts/{compute_sa_email}"
            ).execute()
            print("✓ Compute service account already exists and is ready to use")
            return True
        except Exception:
            # Service account doesn't exist, create it
            try:
                request = service.projects().serviceAccounts().create(
                    name=f"projects/{project_id}",
                    body={
                        "accountId": service_account_id,
                        "serviceAccount": {
                            "displayName": "Compute Engine default service account",
                            "description": "Service account for compute engine operations"
                        }
                    }
                )
                response = request.execute()
                print(f"✓ Successfully created compute service account: {response['email']}")
                return True
            except Exception as e:
                if "alreadyExists" in str(e):
                    print("✓ Compute service account already exists and is ready to use")
                    return True
                print(f"Error creating service account: {str(e)}")
                return False

    except Exception as e:
        print(f"Unexpected error in service account setup: {str(e)}")
        return False

if __name__ == "__main__":
    setup_service_accounts()
