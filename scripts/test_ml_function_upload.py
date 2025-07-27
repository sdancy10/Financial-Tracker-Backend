#!/usr/bin/env python3
"""Test script to verify ML function upload to Cloud Storage"""

import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

try:
    from google.cloud import storage
    print("✓ google-cloud-storage module imported successfully")
except ImportError as e:
    print(f"✗ Failed to import google-cloud-storage: {e}")
    print("Please activate virtual environment and run: pip install google-cloud-storage")
    sys.exit(1)

from src.utils.config import Config

def test_ml_function_upload():
    """Test ML function package upload"""
    # Initialize configuration
    config = Config()
    project_id = config.get('project', {}).get('id')
    
    if not project_id:
        print("✗ No project ID found in config.yaml")
        return False
    
    print(f"✓ Project ID: {project_id}")
    
    # Get bucket name
    storage_config = config.get('storage', {})
    bucket_name = storage_config.get('buckets', {}).get('functions', f"{project_id}-functions")
    bucket_name = bucket_name.replace('%PROJECT_ID%', project_id)
    
    print(f"✓ Bucket name: {bucket_name}")
    
    # Initialize storage client
    try:
        storage_client = storage.Client(project=project_id)
        print("✓ Storage client initialized")
    except Exception as e:
        print(f"✗ Failed to initialize storage client: {e}")
        return False
    
    # Check if bucket exists
    try:
        bucket = storage_client.bucket(bucket_name)
        if bucket.exists():
            print(f"✓ Bucket {bucket_name} exists")
        else:
            print(f"✗ Bucket {bucket_name} does not exist")
            print("  Creating bucket...")
            bucket = storage_client.create_bucket(bucket_name, location='us-central1')
            print(f"✓ Bucket {bucket_name} created")
    except Exception as e:
        print(f"✗ Error checking/creating bucket: {e}")
        return False
    
    # List contents of bucket
    print(f"\nContents of gs://{bucket_name}/:")
    print("-" * 50)
    
    try:
        blobs = list(bucket.list_blobs())
        if not blobs:
            print("  (empty)")
        else:
            for blob in blobs:
                print(f"  - {blob.name} ({blob.size} bytes)")
        
        # Check for expected ML function packages
        expected_packages = [
            'model-retraining-function.zip',
            'model-performance-checker.zip',
            'data-export-function.zip'
        ]
        
        print(f"\nChecking for expected ML function packages:")
        print("-" * 50)
        
        missing_packages = []
        for package in expected_packages:
            blob = bucket.blob(package)
            if blob.exists():
                print(f"✓ {package} exists")
            else:
                print(f"✗ {package} missing")
                missing_packages.append(package)
        
        if missing_packages:
            print(f"\n⚠ Missing packages: {', '.join(missing_packages)}")
            print("\nTo fix this, run: python scripts/deploy_ml_functions.py")
            return False
        else:
            print("\n✓ All ML function packages are present!")
            return True
            
    except Exception as e:
        print(f"✗ Error listing bucket contents: {e}")
        return False

if __name__ == "__main__":
    print("Testing ML Function Upload to Cloud Storage")
    print("=" * 50)
    
    if test_ml_function_upload():
        print("\n✓ Test passed!")
        sys.exit(0)
    else:
        print("\n✗ Test failed!")
        sys.exit(1) 