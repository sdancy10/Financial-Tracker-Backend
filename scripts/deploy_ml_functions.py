#!/usr/bin/env python3
"""
Deploy ML Cloud Functions for the Financial Tracker Backend
Handles packaging and deployment of ML-specific functions
"""

import os
import sys
import zipfile
import shutil
import argparse
import logging
from pathlib import Path

# Suppress Google auth warnings
os.environ['GOOGLE_AUTH_SUPPRESS_CREDENTIALS_WARNINGS'] = '1'

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from google.cloud import storage
from src.utils.config import Config

class MLFunctionDeployer:
    def __init__(self):
        # Set up logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        
        # Initialize configuration
        try:
            self.config = Config()
        except Exception as e:
            self.logger.error(f"Failed to initialize Config: {e}")
            raise
        
        # Get project config
        project_config = self.config.get('project')
        if not project_config:
            raise ValueError("Missing 'project' configuration in config.yaml")
        if not isinstance(project_config, dict):
            raise ValueError(f"Invalid 'project' configuration type: {type(project_config)}")
        
        self.project_id = project_config.get('id')
        if not self.project_id:
            raise ValueError("Missing 'project.id' in config.yaml")
        self.region = project_config.get('region', 'us-central1')
        
        # Initialize storage client
        try:
            self.storage_client = storage.Client(project=self.project_id)
        except Exception as e:
            self.logger.warning(f"Could not initialize storage client: {e}")
            self.storage_client = None
        
        # Define ML functions to deploy
        self.ml_functions = [
            {
                'name': 'data-export-function',
                'source_file': 'src/services/data_export_function.py',
                'entry_point': 'export_training_data_http',
                'trigger_type': 'http',
                'dependencies': [
                    'src/services/data_export_service.py',
                    'src/utils/config.py',
                    'src/utils/__init__.py',
                    'src/services/__init__.py'
                ]
            },
            {
                'name': 'ml-inference-function',
                'source_file': 'src/services/ml_inference_function.py',
                'entry_point': 'predict_categories_http',
                'trigger_type': 'http',
                'dependencies': [
                    'src/services/feature_engineering.py',
                    'src/models/transaction_trainer.py',
                    'src/utils/config.py',
                    'src/services/__init__.py',
                    'src/models/__init__.py',
                    'src/utils/__init__.py'
                ]
            },
            {
                'name': 'model-retraining-function',
                'source_file': 'src/services/model_retraining_function.py',
                'entry_point': 'trigger_model_retraining',
                'trigger_type': 'pubsub',
                'dependencies': [
                    'src/services/data_export_service.py',
                    'src/models/transaction_trainer.py',
                    'src/utils/config.py',
                    'src/utils/__init__.py',
                    'src/models/__init__.py',
                    'src/services/__init__.py',
                    'src/services/feature_engineering.py'
                ]
            },
            {
                'name': 'model-performance-checker',
                'source_file': 'src/services/model_retraining_function.py',
                'entry_point': 'check_model_performance',
                'trigger_type': 'http',
                'dependencies': [
                    'src/services/data_export_service.py',
                    'src/models/transaction_trainer.py',
                    'src/utils/config.py',
                    'src/utils/__init__.py',
                    'src/models/__init__.py',
                    'src/services/__init__.py',
                    'src/services/feature_engineering.py'
                ]
            }
        ]
        
        # Get bucket name from config
        storage_config = self.config.get('storage', {})
        if storage_config is None:
            storage_config = {}
        
        buckets_config = storage_config.get('buckets', {})
        if buckets_config is None:
            buckets_config = {}
            
        self.bucket_name = buckets_config.get('functions', f"{self.project_id}-functions")
        if self.bucket_name:
            self.bucket_name = self.bucket_name.replace('%PROJECT_ID%', self.project_id)

    def prepare_function_package(self, function_config, prepare_only=False):
        """Prepare a function package for deployment"""
        function_name = function_config['name']
        self.logger.info(f"\nPreparing {function_name}...")
        
        # Create temp directory
        temp_dir = f'temp/{function_name}'
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        try:
            # Copy main function file (must be named main.py for Cloud Functions)
            main_file = function_config['source_file']
            if os.path.exists(main_file):
                # Read the file and update import paths
                with open(main_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Fix imports for Cloud Functions environment
                content = content.replace('from src.', 'from ')
                content = content.replace('import src.', 'import ')
                
                # Write to main.py in temp directory
                with open(os.path.join(temp_dir, 'main.py'), 'w', encoding='utf-8') as f:
                    f.write(content)
                    
                self.logger.info(f"  Copied main function file: {main_file} -> main.py")
            else:
                self.logger.error(f"  Main function file not found: {main_file}")
                return False
            
            # Copy dependencies
            for dep in function_config.get('dependencies', []):
                if os.path.exists(dep):
                    # Create directory structure without 'src' prefix
                    dep_path = Path(dep)
                    if dep_path.parts[0] == 'src':
                        # Remove 'src' prefix from path
                        relative_path = Path(*dep_path.parts[1:])
                        dest_dir = os.path.join(temp_dir, relative_path.parent)
                        dest_file = os.path.join(temp_dir, relative_path)
                    else:
                        dest_dir = os.path.join(temp_dir, dep_path.parent)
                        dest_file = os.path.join(temp_dir, dep)
                    
                    if dest_dir != temp_dir:
                        os.makedirs(dest_dir, exist_ok=True)
                    
                    # Copy file and fix imports
                    with open(dep, 'r', encoding='utf-8') as f:
                        content = f.read()
                    content = content.replace('from src.', 'from ')
                    content = content.replace('import src.', 'import ')
                    
                    with open(dest_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    self.logger.info(f"  Copied dependency: {dep}")
                else:
                    self.logger.warning(f"  Dependency not found: {dep}")
            
            # Copy requirements from ml_requirements.txt
            ml_requirements_path = 'ml_requirements.txt'
            if os.path.exists(ml_requirements_path):
                with open(ml_requirements_path, 'r') as f:
                    ml_requirements = f.read()
                
                # Also need base Google Cloud libraries for functions
                base_requirements = [
                    'google-cloud-firestore>=2.7.0',
                    'google-cloud-storage>=2.5.0',
                    'google-cloud-secret-manager>=2.12.0'
                ]
                
                # Combine requirements
                all_requirements = ml_requirements + '\n' + '\n'.join(base_requirements)
            else:
                # Fallback to minimal requirements
                self.logger.warning("ml_requirements.txt not found, using minimal requirements")
                requirements = [
                    'functions-framework',
                    'google-cloud-firestore',
                    'google-cloud-storage',
                    'google-cloud-bigquery',
                    'google-cloud-aiplatform',
                    'pyyaml',
                    'pandas',
                    'pyarrow',
                    'numpy',
                    'scikit-learn==1.3.1',
                    'metaphone'
                ]
                all_requirements = '\n'.join(requirements)
            
            with open(os.path.join(temp_dir, 'requirements.txt'), 'w') as f:
                f.write(all_requirements)
            self.logger.info("  Created requirements.txt")
            
            # Create __init__.py files
            for root, dirs, _ in os.walk(temp_dir):
                for dir_name in dirs:
                    init_file = os.path.join(root, dir_name, '__init__.py')
                    if not os.path.exists(init_file):
                        open(init_file, 'a').close()
            
            # Create zip file
            zip_filename = f"{function_name}.zip"
            os.makedirs('temp', exist_ok=True)  # Ensure temp directory exists
            zip_path = os.path.join('temp', zip_filename)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, _, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arcname)
            
            self.logger.info(f"  Created zip package: {zip_path}")
            
            # Upload to GCS unless prepare-only mode
            if not prepare_only:
                return self.upload_to_gcs(zip_path, zip_filename)
            
            return True
            
        except Exception as e:
            self.logger.error(f"  Error preparing {function_name}: {str(e)}")
            return False
        finally:
            # Clean up temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
    
    def upload_to_gcs(self, local_path, gcs_filename):
        """Upload function package to Google Cloud Storage"""
        if not self.storage_client:
            self.logger.warning("  Storage client not available, skipping upload")
            return True  # Return True in prepare-only mode
            
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(gcs_filename)
            
            # Delete old package if exists
            if blob.exists():
                blob.delete()
                self.logger.info(f"  Deleted old package: {gcs_filename}")
            
            self.logger.info(f"  Uploading to gs://{self.bucket_name}/{gcs_filename}")
            blob.upload_from_filename(local_path)
            self.logger.info("  Upload successful")
            
            return True
        except Exception as e:
            self.logger.error(f"  Upload failed: {str(e)}")
            return False
    
    def deploy(self, prepare_only=False):
        """Deploy all ML functions"""
        self.logger.info("ML Function Deployment")
        self.logger.info("=" * 50)
        
        # Ensure bucket exists
        if self.storage_client:
            try:
                bucket = self.storage_client.bucket(self.bucket_name)
                if not bucket.exists():
                    self.logger.info(f"Creating bucket: {self.bucket_name}")
                    bucket = self.storage_client.create_bucket(self.bucket_name, location=self.region)
                else:
                    self.logger.info(f"Using existing bucket: {self.bucket_name}")
            except Exception as e:
                self.logger.warning(f"Could not check/create bucket: {e}")
        else:
            self.logger.warning("Storage client not available, skipping bucket check")
        
        # Deploy each function
        success_count = 0
        for function_config in self.ml_functions:
            if self.prepare_function_package(function_config, prepare_only):
                success_count += 1
            else:
                self.logger.error(f"Failed to prepare {function_config['name']}")
        
        self.logger.info(f"\nDeployment Summary: {success_count}/{len(self.ml_functions)} functions prepared")
        
        if prepare_only:
            self.logger.info("\nFunction packages prepared. Terraform will handle deployment.")
        else:
            self.logger.info("\nFunction packages uploaded. Use Terraform to create Cloud Functions.")
        
        return success_count == len(self.ml_functions)

def main():
    parser = argparse.ArgumentParser(description='Deploy ML Cloud Functions')
    parser.add_argument('--prepare-only', action='store_true', 
                        help='Only prepare packages without uploading to GCS')
    args = parser.parse_args()
    
    try:
        deployer = MLFunctionDeployer()
        success = deployer.deploy(prepare_only=args.prepare_only)
        sys.exit(0 if success else 1)
    except Exception as e:
        logging.error(f"Deployment failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 