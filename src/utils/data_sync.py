from google.cloud import storage
from google.api_core import exceptions
import os
import json
from datetime import datetime
from typing import Dict
from ..utils.config import Config

class DataSync:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.storage_client = storage.Client(project=project_id)
        # Format bucket name to meet GCP requirements:
        # - Must start/end with letter/number
        # - Can only contain lowercase letters, numbers, dashes
        # - Length between 3-63 characters
        bucket_name = f"{project_id.lower()}-data"
        self.data_bucket = ''.join(c if c.isalnum() or c == '-' else '' 
                                  for c in bucket_name).strip('-')
        self.config = Config()
        self.sync_file = 'data/sync/last_sync.json'
        self.training_dir = 'data/training'

    def get_last_sync(self) -> Dict:
        """Get last sync timestamps for data files"""
        if not os.path.exists(self.sync_file):
            return {}
        
        with open(self.sync_file, 'r') as f:
            return json.load(f)

    def save_sync_time(self, file_path: str, timestamp: str):
        """Save sync timestamp for a file"""
        sync_data = self.get_last_sync()
        sync_data[file_path] = timestamp
        
        os.makedirs(os.path.dirname(self.sync_file), exist_ok=True)
        with open(self.sync_file, 'w') as f:
            json.dump(sync_data, f)

    def sync_training_data(self):
        """Sync training data with GCS bucket"""
        try:
            bucket = self.storage_client.bucket(self.data_bucket)
            if not bucket.exists():
                print(f"Creating bucket {self.data_bucket}")
                bucket = self.storage_client.create_bucket(
                    self.data_bucket,
                    location="us-central1"
                )
            return True
        except exceptions.Forbidden:
            print(f"Permission denied: Unable to access/create bucket {self.data_bucket}")
            return False 