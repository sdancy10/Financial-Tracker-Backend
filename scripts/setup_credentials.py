"""Script to set up initial credentials and sync settings"""
import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.services.transaction_service import TransactionService
from src.utils.config import Config

def main():
    """Set up initial credentials and sync settings"""
    try:
        print("\n=== Setting up Initial Credentials and Sync Settings ===")
        
        # Initialize config and service
        config = Config()
        service = TransactionService(config.get('project', 'id'))
        
        # Run first time setup
        service.setup_first_run()
        print("\n✓ Successfully set up initial credentials and sync settings")
        
    except Exception as e:
        print(f"\nError setting up credentials: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 