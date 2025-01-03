#!/usr/bin/env python3

import os
import sys
import webbrowser
from google.cloud.devtools import cloudbuild_v1
from google.api_core import exceptions

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.utils.config import Config

def check_cloud_build_status(project_id):
    """Check if Cloud Build API is enabled and repository is connected."""
    client = cloudbuild_v1.CloudBuildClient()
    
    try:
        # Try to list triggers to check if API is enabled and working
        request = cloudbuild_v1.ListBuildTriggersRequest(project_id=project_id)
        client.list_build_triggers(request=request)
        return True
    except exceptions.PermissionDenied:
        print("Error: Cloud Build API is not enabled or credentials lack permission.")
        return False
    except exceptions.ServiceUnavailable:
        print("Error: Cloud Build API is not enabled.")
        return False

def open_cloud_build_console(project_id):
    """Open the Cloud Build triggers page in the default browser."""
    url = f"https://console.cloud.google.com/cloud-build/triggers/connect?project={project_id}"
    print(f"\nOpening Cloud Build console in your browser...")
    webbrowser.open(url)

def main():
    print("Setting up Cloud Build repository connection...")
    
    # Load configuration using Config class
    config = Config()
    project_id = config.get('project', 'id')
    if not project_id:
        print("Error: Could not find project ID in configuration")
        sys.exit(1)
    
    # Check Cloud Build status
    if not check_cloud_build_status(project_id):
        print("\nPlease follow these steps to set up Cloud Build:")
        print("1. Enable the Cloud Build API in your Google Cloud project")
        print("2. Ensure your service account has the necessary permissions")
        print("3. Run this script again")
        sys.exit(1)
    
    # Instructions for repository connection
    print("\nTo connect your GitHub repository to Cloud Build:")
    print("1. Click the link that opens in your browser")
    print("2. Select 'GitHub' as your source code repository")
    print("3. Authenticate with GitHub if prompted")
    print("4. Select the 'Financial-Tracker-Backend' repository")
    print("5. Click 'Connect repository'")
    
    # Open Cloud Build console
    open_cloud_build_console(project_id)
    
    print("\nAfter connecting the repository:")
    print("1. Return to your terminal")
    print("2. Run 'terraform apply' to create the Cloud Build trigger")

if __name__ == "__main__":
    main() 