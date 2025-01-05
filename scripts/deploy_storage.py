from google.cloud import storage
from google.api_core import exceptions
from src.utils.config import Config
import json
import subprocess
from pathlib import Path
import logging

class StorageDeployer:
    def __init__(self):
        # Set up logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        
        # Initialize configuration
        self.config = Config()
        self.project_id = self.config.get('project', 'id')
        self.logger.info(f"Using project ID: {self.project_id}")
        
        # Get bucket names from config
        storage_config = self.config.get('storage', 'buckets')
        if not storage_config:
            self.logger.warning("No storage configuration found, using default values from config")
            storage_config = self.config.get('defaults', 'storage', {
                'data': f"{self.project_id}-data",
                'ml_artifacts': f"{self.project_id}-ml-artifacts",
                'functions': f"{self.project_id}-functions"
            })
        
        self.logger.info(f"Raw storage config: {storage_config}")
        self.data_bucket = storage_config.get('data', f"{self.project_id}-data")
        self.ml_bucket = storage_config.get('ml_artifacts', f"{self.project_id}-ml-artifacts")
        self.logger.info(f"Configured bucket names - data: '{self.data_bucket}', ml_artifacts: '{self.ml_bucket}'")
        
        # Initialize client
        self.storage_client = storage.Client()
        
        # Add Terraform state checking
        self.terraform_state = self._load_terraform_state()
        self.is_terraform_managed = self.terraform_state is not None
        self.is_free_tier = self._check_if_free_tier()
    
    def _load_terraform_state(self):
        """Load Terraform state if it exists"""
        try:
            terraform_dir = Path(__file__).parent.parent / "terraform"
            if not terraform_dir.exists():
                return None
                
            # Try to get Terraform state
            result = subprocess.run(
                ["terraform", "show", "-json"],
                cwd=terraform_dir,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                return json.loads(result.stdout)
            return None
        except Exception as e:
            self.logger.warning(f"Could not load Terraform state: {e}")
            return None
    
    def _check_if_free_tier(self):
        """Check if we're using free tier configuration"""
        if not self.terraform_state:
            return False
            
        # Check for free tier resources in state
        resources = self.terraform_state.get("resources", [])
        return any(r.get("name", "").endswith("-free") for r in resources)
    
    def _get_terraform_bucket(self, bucket_name):
        """Get bucket details from Terraform state"""
        if not self.terraform_state:
            return None
            
        resources = self.terraform_state.get("resources", [])
        for resource in resources:
            if resource.get("type") == "google_storage_bucket":
                instances = resource.get("instances", [{}])
                for instance in instances:
                    attrs = instance.get("attributes", {})
                    if attrs.get("name") == bucket_name:
                        return attrs
        return None
    
    def deploy(self):
        """Deploy required storage buckets"""
        try:
            buckets = [self.data_bucket, self.ml_bucket]
            self.logger.info(f"Attempting to deploy buckets: {buckets}")
            
            for bucket_name in buckets:
                self.logger.info(f"Processing bucket: '{bucket_name}'")
                # Check if bucket is managed by Terraform
                if self.is_terraform_managed:
                    tf_bucket = self._get_terraform_bucket(bucket_name)
                    if tf_bucket:
                        self.logger.info(f"Bucket {bucket_name} is managed by Terraform")
                        continue
                
                # Create or verify bucket if not managed by Terraform
                try:
                    bucket = self.storage_client.get_bucket(bucket_name)
                    self.logger.info(f"Bucket {bucket_name} already exists")
                except exceptions.NotFound:
                    bucket = self.storage_client.create_bucket(bucket_name)
                    self.logger.info(f"Created bucket {bucket_name}")
            
            self.logger.info("Storage deployment completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in storage deployment: {str(e)}")
            return False

def main():
    deployer = StorageDeployer()
    success = deployer.deploy()
    if not success:
        exit(1)

if __name__ == "__main__":
    main() 