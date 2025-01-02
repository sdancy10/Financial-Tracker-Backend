from google.cloud import storage
from google.api_core import exceptions
from src.utils.config import Config

def deploy_storage():
    """Deploy required storage buckets"""
    config = Config()
    
    # Get bucket names from config
    data_bucket = config.get('storage', 'buckets', 'data')
    ml_bucket = config.get('storage', 'buckets', 'ml_artifacts')
    
    # Create storage client
    storage_client = storage.Client()
    
    # Create or verify buckets
    buckets = [data_bucket, ml_bucket]
    for bucket_name in buckets:
        try:
            bucket = storage_client.get_bucket(bucket_name)
            print(f"Bucket {bucket_name} already exists")
        except exceptions.NotFound:
            bucket = storage_client.create_bucket(bucket_name)
            print(f"Created bucket {bucket_name}")
    
    print("Storage deployment completed successfully")

if __name__ == "__main__":
    deploy_storage() 