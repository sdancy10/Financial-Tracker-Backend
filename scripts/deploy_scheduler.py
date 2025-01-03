import os
import sys
import json
import base64
import logging
import hashlib
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from google.cloud import scheduler_v1

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.utils.config import Config

class SchedulerDeployer:
    def __init__(self):
        # Set up logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        
        # Initialize configuration
        self.config = Config()
        
        # Get project config
        project_config = self.config.get('project')
        if not project_config:
            raise ValueError("Missing 'project' configuration in config.yaml")
        self.project_id = project_config.get('id')
        self.region = project_config.get('region', 'us-central1')
        
        # Get scheduler config
        self.scheduler_config = self.config.get('scheduler')
        if not self.scheduler_config:
            self.logger.warning("No scheduler configuration found, using default values")
            self.schedule = '*/10 * * * *'  # Every 10 minutes
            self.timezone = 'UTC'
            self.retry_count = 3
            self.retry_interval = 300
            self.timeout = 540
        else:
            transaction_sync = self.scheduler_config.get('transaction_sync', {})
            self.schedule = transaction_sync.get('schedule', '*/10 * * * *')
            self.timezone = transaction_sync.get('timezone', 'UTC')
            self.retry_count = transaction_sync.get('retry_count', 3)
            self.retry_interval = transaction_sync.get('retry_interval', 300)
            self.timeout = transaction_sync.get('timeout', 540)
        
        # Hash file for tracking changes
        self.hash_file = '.scheduler_hashes.json'
        self.deployment_hashes = self._load_deployment_hashes()
        
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
    
    def _get_terraform_scheduler(self, job_name):
        """Get scheduler job details from Terraform state"""
        if not self.terraform_state:
            return None
            
        resources = self.terraform_state.get("resources", [])
        for resource in resources:
            if resource.get("type") == "google_cloud_scheduler_job":
                instances = resource.get("instances", [{}])
                for instance in instances:
                    attrs = instance.get("attributes", {})
                    if attrs.get("name") == job_name:
                        return attrs
        return None
    
    def _load_deployment_hashes(self):
        """Load saved deployment hashes"""
        try:
            if os.path.exists(self.hash_file):
                with open(self.hash_file, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.warning(f"Failed to load deployment hashes: {e}")
            return {}

    def _save_deployment_hashes(self):
        """Save deployment hashes"""
        try:
            with open(self.hash_file, 'w') as f:
                json.dump(self.deployment_hashes, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Failed to save deployment hashes: {e}")
    
    def _calculate_scheduler_hash(self):
        """Calculate hash of scheduler configuration"""
        try:
            config = {
                'schedule': self.schedule,
                'timezone': self.timezone,
                'retry_count': self.retry_count,
                'retry_interval': self.retry_interval,
                'timeout': self.timeout
            }
            return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        except Exception as e:
            self.logger.warning(f"Failed to calculate scheduler hash: {e}")
            return None

    def _create_pubsub_message(self):
        """Create the PubSub message with proper format"""
        message = {
            'timestamp': datetime.utcnow().isoformat(),
            'check_from': (datetime.utcnow() - timedelta(hours=24)).isoformat(),
            'force_sync': True
        }
        return json.dumps(message)

    def setup_scheduler(self) -> bool:
        """Set up Cloud Scheduler with proper message format"""
        try:
            # Get job name based on tier
            job_name = "process-scheduled-transactions-free" if self.is_free_tier else "process-scheduled-transactions"
            
            # Check if scheduler is managed by Terraform
            if self.is_terraform_managed:
                tf_scheduler = self._get_terraform_scheduler(job_name)
                if tf_scheduler:
                    self.logger.info(f"Scheduler job {job_name} is managed by Terraform")
                    return True
            
            # Calculate new hash
            new_hash = self._calculate_scheduler_hash()
            if not new_hash:
                return False
                
            # Check if scheduler config has changed
            if new_hash == self.deployment_hashes.get('scheduler'):
                self.logger.info("Scheduler configuration hasn't changed since last deployment, skipping...")
                return True
            
            # Create Cloud Scheduler client
            scheduler = scheduler_v1.CloudSchedulerClient()
            
            # Get the location path
            parent = f'projects/{self.project_id}/locations/{self.region}'
            
            # Create scheduler job
            job_path = f"{parent}/jobs/{job_name}"
            topic_name = f"projects/{self.project_id}/topics/scheduled-transactions"
            
            retry_config = scheduler_v1.RetryConfig(
                retry_count=self.retry_count,
                min_backoff_duration=f"{self.retry_interval}s"
            )
            
            # Create properly formatted message
            message_data = self._create_pubsub_message()
            
            job = scheduler_v1.Job(
                name=job_path,
                description='Trigger scheduled transaction processing',
                schedule=self.schedule,
                time_zone=self.timezone,
                pubsub_target=scheduler_v1.PubsubTarget(
                    topic_name=topic_name,
                    data=message_data.encode()
                ),
                retry_config=retry_config
            )
            
            try:
                scheduler.create_job(
                    request=scheduler_v1.CreateJobRequest(
                        parent=parent,
                        job=job
                    )
                )
                self.logger.info(f"Created scheduler job: {job_path}")
                
                # Save new hash after successful creation
                self.deployment_hashes['scheduler'] = new_hash
                self._save_deployment_hashes()
                return True
                
            except Exception as e:
                if "already exists" in str(e).lower():
                    self.logger.info(f"Scheduler job already exists: {job_path}")
                    try:
                        scheduler.update_job(
                            request=scheduler_v1.UpdateJobRequest(
                                job=job
                            )
                        )
                        self.logger.info(f"Updated scheduler job: {job_path}")
                        
                        # Save new hash after successful update
                        self.deployment_hashes['scheduler'] = new_hash
                        self._save_deployment_hashes()
                        return True
                    except Exception as update_e:
                        self.logger.error(f"Error updating scheduler job: {str(update_e)}")
                        return False
                else:
                    self.logger.error(f"Error creating scheduler job: {str(e)}")
                    return False
            
            return True
        except Exception as e:
            self.logger.error(f"Error setting up scheduler: {str(e)}")
            return False

    def deploy(self):
        """Deploy the Cloud Scheduler job"""
        try:
            # Check if we should proceed with deployment
            if self.is_terraform_managed:
                self.logger.info("Scheduler is managed by Terraform, checking for manual updates...")
                job_name = "process-scheduled-transactions-free" if self.is_free_tier else "process-scheduled-transactions"
                tf_scheduler = self._get_terraform_scheduler(job_name)
                if tf_scheduler:
                    self.logger.info("No manual updates needed, scheduler is managed by Terraform")
                    return True
            
            # Proceed with manual deployment
            self.logger.info("\n=== Setting up Cloud Scheduler ===")
            success = self.setup_scheduler()
            if not success:
                return False

            self.logger.info("\n=== Scheduler Deployment Completed Successfully ===")
            return True

        except Exception as e:
            self.logger.error(f"Error during scheduler deployment: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def main():
    deployer = SchedulerDeployer()
    if not deployer.deploy():
        sys.exit(1)

if __name__ == "__main__":
    main() 