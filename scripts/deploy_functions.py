import os
import sys
import re
import shutil
import zipfile
import hashlib
import json
import logging
import time
import base64
import subprocess
import venv
from pathlib import Path
from google.protobuf import duration_pb2

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from google.cloud import storage
from google.cloud import functions_v1
from google.cloud import pubsub_v1
from google.cloud import scheduler_v1
from src.utils.config import Config
from test_deployment import DeploymentTester
from deploy_scheduler import SchedulerDeployer

class FunctionDeployer:
    def __init__(self):
        # Set up logging first
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
        
        # Get function config
        self.function_config = self.config.get('cloud_function')
        if not self.function_config:
            raise ValueError("Missing 'cloud_function' configuration in config.yaml")
            
        self.function_name = self.function_config.get('name', 'transaction-processor')
        self.runtime = self.function_config.get('runtime', 'python310')
        self.entry_point = self.function_config.get('entry_point', 'process_transactions')
        self.timeout = self.function_config.get('timeout', 540)  # Default to 540 seconds (9 minutes)
        
        # Get storage config
        storage_config = self.config.get('storage')
        if not storage_config:
            self.logger.warning("No storage configuration found, using default bucket names")
            self.source_bucket = f"{self.project_id}-functions".lower()
        else:
            buckets_config = storage_config.get('buckets', {})
            self.source_bucket = buckets_config.get('functions', f"{self.project_id}-functions").lower()
        self.source_object = 'function-source.zip'
        
        # Get testing config
        self.testing_config = self.config.get('testing')
        if not self.testing_config:
            self.logger.warning("No testing configuration found in config.yaml, using defaults")
            self.testing_config = {
                'run_after_deployment': False,
                'wait_time': 10,
                'components': {
                    'function': True,
                    'scheduler': True,
                    'pubsub': True,
                    'http': True,
                    'pubsub_trigger': True
                }
            }
        else:
            # Ensure all required fields exist with defaults if not specified
            if 'run_after_deployment' not in self.testing_config:
                self.logger.warning("No run_after_deployment specified in testing config, defaulting to False")
                self.testing_config['run_after_deployment'] = False
                
            if 'wait_time' not in self.testing_config:
                self.logger.warning("No wait_time specified in testing config, defaulting to 10 seconds")
                self.testing_config['wait_time'] = 10
                
            if 'components' not in self.testing_config:
                self.logger.warning("No components specified in testing config, enabling all tests")
                self.testing_config['components'] = {
                    'function': True,
                    'scheduler': True,
                    'pubsub': True,
                    'http': True,
                    'pubsub_trigger': True
                }
            else:
                # Ensure all component flags exist
                default_components = {
                    'function': True,
                    'scheduler': True,
                    'pubsub': True,
                    'http': True,
                    'pubsub_trigger': True
                }
                for component, default_value in default_components.items():
                    if component not in self.testing_config['components']:
                        self.logger.warning(f"Component '{component}' not specified in testing config, defaulting to {default_value}")
                        self.testing_config['components'][component] = default_value
        
        self.logger.debug(f"Final testing configuration: {self.testing_config}")
        
        # Initialize clients
        self.storage_client = storage.Client(project=self.project_id)
        self.functions_client = functions_v1.CloudFunctionsServiceClient()
        
        # Hash file for tracking changes
        self.hash_file = '.function_hashes.json'
        self.deployment_hashes = self._load_deployment_hashes()
        
        # Get module mapping from config or use defaults
        self.module_mapping = self.function_config.get('module_mapping', {
            'src.utils.config': 'utils_config',
            'src.utils.transaction_dao': 'utils_transaction_dao',
            'src.utils.credentials_manager': 'utils_credentials_manager',
            'src.utils.gmail_util': 'utils_gmail_util',
            'src.utils.validation': 'utils_validation',
            'src.utils.transaction_parser': 'utils_transaction_parser',
            'src.utils.auth_util': 'utils_auth_util',
            'src.utils.data_sync': 'utils_data_sync',
            'src.models.transaction': 'models_transaction',
            'src.services.transaction_service': 'services_transaction_service',
            'src.services.transaction_processor': 'services_transaction_processor',
            'src.services.transaction_trainer': 'services_transaction_trainer',
            'src.services.transaction_scheduler': 'services_transaction_scheduler',
            'src.api.routes': 'api_routes'
        })
        
        # Add Terraform state checking
        self.terraform_state = self._load_terraform_state()
        self.is_terraform_managed = self.terraform_state is not None
        self.is_free_tier = self._check_if_free_tier()
    
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
    
    def _calculate_function_hash(self, zip_path):
        """Calculate hash of function code"""
        try:
            sha256_hash = hashlib.sha256()
            with open(zip_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b''):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            self.logger.warning(f"Failed to calculate function hash: {e}")
            return None
    
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
    
    def get_exclusion_patterns(self) -> set:
        """Get exclusion patterns from .gitignore, config, and mandatory patterns"""
        patterns = set()
        
        # Add mandatory patterns that should always be excluded
        mandatory_patterns = {
            '__pycache__',
            '*.pyc',
            '*.pyo',
            '*.pyd',
            '.Python',
            'env/',
            'venv/',
            '.env',
            '.venv',
        }
        patterns.update(mandatory_patterns)
        
        # Read from .gitignore if it exists
        gitignore_path = '.gitignore'
        if os.path.exists(gitignore_path):
            with open(gitignore_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if line and not line.startswith('#'):
                        patterns.add(line)
        
        # Read deployment-specific exclusions from config
        try:
            exclude_patterns = self.function_config.get('exclude_patterns')
            if exclude_patterns and isinstance(exclude_patterns, (list, tuple)):
                patterns.update(exclude_patterns)
            elif exclude_patterns:
                self.logger.warning(f"Invalid exclude_patterns format in config: {exclude_patterns}")
        except Exception as e:
            self.logger.warning(f"Could not read exclusions from config: {str(e)}")
        
        return patterns
    
    def should_include(self, path: str, exclusion_patterns: set) -> bool:
        """Check if a path should be included in the package"""
        # Convert Windows paths to forward slashes for consistency
        path = path.replace('\\', '/')
        
        for pattern in exclusion_patterns:
            # Handle directory patterns (ending with /)
            if pattern.endswith('/'):
                if pattern[:-1] in path.split('/'):
                    return False
            # Handle file patterns with wildcards
            elif '*' in pattern:
                import fnmatch
                if fnmatch.fnmatch(path, pattern):
                    return False
            # Handle exact matches
            elif pattern in path:
                return False
        return True
    
    def update_imports(self, content):
        """Update import statements to use flattened module names"""
        # Pattern to match 'from src.xxx import' or 'from services.xxx import' etc.
        pattern = r'from (src\.|)(services|utils|models|api)\.([a-zA-Z_]+) import'
        
        def replace_import(match):
            prefix = match.group(1)  # 'src.' or ''
            module_type = match.group(2)  # 'services', 'utils', etc.
            module_name = match.group(3)  # actual module name
            
            # Construct original module path
            if prefix:
                original = f"{prefix}{module_type}.{module_name}"
            else:
                original = f"{module_type}.{module_name}"
            
            # Look up the flattened name
            if original in self.module_mapping:
                return f"from {self.module_mapping[original]} import"
            elif f"src.{original}" in self.module_mapping:
                return f"from {self.module_mapping[f'src.{original}']} import"
            
            # If no mapping found, return original
            return match.group(0)
        
        # Replace all matching imports
        updated_content = re.sub(pattern, replace_import, content)
        return updated_content

    def get_flattened_name(self, file_path):
        """Get the flattened name for a source file path."""
        # Check special files first
        special_files = self.get_special_files()
        if file_path in special_files:
            return special_files[file_path]
        
        # Remove src/ prefix if present
        if file_path.startswith('src/'):
            file_path = file_path[4:]
        
        # Convert path to module path
        module_path = file_path.replace('\\', '/').replace('/', '.')
        if module_path.startswith('.'):
            module_path = module_path[1:]
        
        # Remove .py extension if present
        if module_path.endswith('.py'):
            module_path = module_path[:-3]
        
        # Check if we have a mapping for this module
        full_module_path = f"src.{module_path}"
        if full_module_path in self.module_mapping:
            return f"{self.module_mapping[full_module_path]}.py"
        
        # For files without a mapping, use a consistent naming convention
        parts = module_path.split('.')
        if len(parts) == 1:
            return file_path
        else:
            # For __init__.py files
            if parts[-1] == '__init__':
                return f"{parts[-2]}_init.py"
            # For other files
            return f"{parts[-2]}_{parts[-1]}.py"

    def copy_with_imports(self, src_path: str, dest_path: str) -> bool:
        """Copy file and update imports if needed"""
        try:
            # Create destination directory if it doesn't exist
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # For Python files, update imports
            if src_path.endswith('.py'):
                with open(src_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Update imports using module mapping
                for old_path, new_name in self.module_mapping.items():
                    # Escape dots in the old path for regex
                    escaped_path = old_path.replace('.', r'\.')
                    # Create the regex patterns
                    from_pattern = r'from ' + escaped_path + r' import'
                    import_pattern = r'import ' + escaped_path
                    # Replace the imports
                    content = re.sub(from_pattern, f'from {new_name} import', content)
                    content = re.sub(import_pattern, f'import {new_name}', content)
                
                with open(dest_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                # For non-Python files, just copy
                shutil.copy2(src_path, dest_path)
            
            # Get file size in KB
            size_kb = os.path.getsize(dest_path) / 1024
            self.logger.info(f"[OK] Processed {src_path} to {os.path.basename(dest_path)} ({size_kb:.1f} KB)")
            return True
            
        except Exception as e:
            self.logger.error(f"Error processing {src_path}: {str(e)}")
            return False

    def package_function(self) -> bool:
        """Package function code into ZIP file"""
        try:
            # Create temp directory for function code
            os.makedirs('temp/function', exist_ok=True)
            
            # Get exclusion patterns
            exclusion_patterns = self.get_exclusion_patterns()
            print("\nExclusion patterns:")
            for pattern in sorted(exclusion_patterns):
                print(f"  - {pattern}")
            
            def get_file_size(size_bytes):
                """Get human readable file size"""
                try:
                    if isinstance(size_bytes, str):
                        return size_bytes
                    for unit in ['B', 'KB', 'MB', 'GB']:
                        if size_bytes < 1024.0:
                            return f"{size_bytes:.1f} {unit}"
                        size_bytes /= 1024.0
                    return f"{size_bytes:.1f} TB"
                except (TypeError, ValueError):
                    return "Unknown size"
            
            print("\nPackaging function code...")
            total_size = 0
            file_count = 0
            
            # Copy and process Python files
            for root, _, files in os.walk('src'):
                python_files = [f for f in files if f.endswith('.py')]
                for file in python_files:
                    src_path = os.path.join(root, file)
                    if self.should_include(src_path, exclusion_patterns):
                        dest_name = self.get_flattened_name(src_path)
                        dest_path = os.path.join('temp/function', dest_name)
                        
                        if self.copy_with_imports(src_path, dest_path):
                            size = os.path.getsize(src_path)
                            total_size += size
                            file_count += 1
                            print(f"[OK] Processed {src_path} to {dest_name} ({get_file_size(size)})")
            
            # Copy special non-Python files
            special_files = self.get_special_files()
            for src, dest in special_files.items():
                if not src.endswith('.py') and os.path.exists(src):
                    dest_path = os.path.join('temp/function', dest)
                    if self.copy_with_imports(src, dest_path):
                        size = os.path.getsize(src)
                        total_size += size
                        file_count += 1
                        print(f"[OK] Copied {dest} ({get_file_size(size)})")
            
            # Create ZIP file
            zip_path = 'temp/function.zip'
            print(f"\nCreating zip file at {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
                for root, _, files in os.walk('temp/function'):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, 'temp/function')
                        zipf.write(file_path, arcname)
            
            final_size = os.path.getsize(zip_path)
            print(f"\nPackage Summary:")
            print(f"Total files: {file_count}")
            print(f"Total uncompressed: {get_file_size(total_size)}")
            print(f"Final zip size: {get_file_size(final_size)}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error packaging function: {str(e)}")
            return False
        finally:
            # Clean up temporary files
            try:
                if os.path.exists('temp/function'):
                    shutil.rmtree('temp/function')
            except Exception as e:
                self.logger.warning(f"Failed to clean up temporary files: {e}")
    
    def upload_source(self) -> bool:
        """Upload function source to GCS"""
        try:
            print(f"Uploading function source to gs://{self.source_bucket}/{self.source_object}")
            bucket = self.storage_client.bucket(self.source_bucket)
            
            # Create bucket if it doesn't exist
            if not bucket.exists():
                print(f"Creating bucket {self.source_bucket}")
                bucket.create()
                
            blob = bucket.blob(self.source_object)
            blob.upload_from_filename('temp/function.zip')
            print("✓ Successfully uploaded function source")
            return True
        except Exception as e:
            print(f"Error uploading function source: {str(e)}")
            return False
    
    def deploy_function(self) -> bool:
        """Deploy the Cloud Function if changed"""
        try:
            # Check if function is managed by Terraform
            function_name = self.function_name
            if self.is_terraform_managed:
                tf_function = self._get_terraform_resource(
                    "google_cloudfunctions_function",
                    "free_tier_function" if self.is_free_tier else "transaction_processor"
                )
                if tf_function:
                    self.logger.info("Function is managed by Terraform, checking for manual updates...")
                    # Only proceed if we have changes not in Terraform
                    if not self._has_manual_updates():
                        self.logger.info("No manual updates needed, function is managed by Terraform")
                        return True
                    function_name = tf_function.get("name", self.function_name)
            
            # Rest of the existing deployment code...
            # Update function name if needed
            self.function_name = function_name
            
            # Package the function first
            if not self.package_function():
                return False
            
            # Calculate new hash
            new_hash = self._calculate_function_hash('temp/function.zip')
            if not new_hash:
                return False
            
            # Check if function has changed
            if new_hash == self.deployment_hashes.get('function'):
                self.logger.info("Function code hasn't changed since last deployment, skipping...")
                return True
            
            # Continue with deployment if changed...
            parent = f'projects/{self.project_id}/locations/{self.region}'
            
            # Create a Pub/Sub topic for the trigger if it doesn't exist
            topic_name = f"projects/{self.project_id}/topics/scheduled-transactions"
            try:
                publisher = pubsub_v1.PublisherClient()
                publisher.create_topic(request={"name": topic_name})
                self.logger.info(f"✓ Created Pub/Sub topic: {topic_name}")
            except Exception as e:
                if "Resource already exists" in str(e) or "AlreadyExists" in str(e):
                    self.logger.info(f"✓ Pub/Sub topic already exists: {topic_name}")
                else:
                    self.logger.error(f"✗ Error creating Pub/Sub topic: {str(e)}")
                    return False
            
            # Upload source code
            if not self.upload_source():
                return False
            
            # Convert timeout to duration format
            timeout_duration = duration_pb2.Duration()
            timeout_duration.seconds = self.timeout
            
            function = {
                'name': f'{parent}/functions/{self.function_name}',
                'source_archive_url': f'gs://{self.source_bucket}/{self.source_object}',
                'entry_point': self.entry_point,
                'runtime': self.runtime,
                'environment_variables': {
                    'GOOGLE_CLOUD_PROJECT': self.project_id,
                    'CONFIG_PATH': 'config.yaml',
                },
                'event_trigger': {
                    'event_type': 'google.pubsub.topic.publish',
                    'resource': topic_name,
                    'service': 'pubsub.googleapis.com'
                },
                'description': "Processes financial transactions",
                'timeout': timeout_duration
            }
            
            try:
                operation = self.functions_client.create_function(
                    request={'location': parent, 'function': function}
                )
                result = operation.result()
                self.logger.info(f"✓ Function deployed successfully: {result.name}")
                
                # Save new hash after successful deployment
                self.deployment_hashes['function'] = new_hash
                self._save_deployment_hashes()
                return True
                
            except Exception as e:
                if "already exists" in str(e).lower():
                    self.logger.info("Function already exists, attempting update...")
                    try:
                        operation = self.functions_client.update_function(
                            request={'function': function}
                        )
                        result = operation.result()
                        self.logger.info(f"✓ Function updated successfully: {result.name}")
                        
                        # Save new hash after successful update
                        self.deployment_hashes['function'] = new_hash
                        self._save_deployment_hashes()
                        return True
                    except Exception as update_e:
                        self.logger.error(f"✗ Error updating function: {str(update_e)}")
                        return False
                else:
                    self.logger.error(f"✗ Error creating function: {str(e)}")
                    return False
            
        except Exception as e:
            self.logger.error(f"Error in function deployment: {str(e)}")
            return False
    
    def _has_manual_updates(self) -> bool:
        """Check if there are manual updates needed beyond Terraform"""
        try:
            # Compare source code hash with Terraform state
            if not self.package_function():
                return False
                
            new_hash = self._calculate_function_hash('temp/function.zip')
            tf_function = self._get_terraform_resource(
                "google_cloudfunctions_function",
                "free_tier_function" if self.is_free_tier else "transaction_processor"
            )
            
            if tf_function and tf_function.get("source_code_hash") == new_hash:
                return False
                
            return True
        except Exception as e:
            self.logger.warning(f"Error checking for manual updates: {e}")
            return True  # Assume updates needed on error
    
    def deploy(self):
        """Deploy the Cloud Function and set up the scheduler"""
        try:
            # Check if we should proceed with deployment
            if self.is_terraform_managed and not self._has_manual_updates():
                self.logger.info("All resources are managed by Terraform, no manual deployment needed")
                return True
                
            # Proceed with manual deployment for non-Terraform resources
            self.logger.info("\n=== Deploying Cloud Function ===")
            success = self.deploy_function()
            if not success:
                return False
                
            # Set up scheduler only if not managed by Terraform
            if not self.is_terraform_managed:
                scheduler_deployer = SchedulerDeployer()
                success = scheduler_deployer.deploy()
                if not success:
                    return False
                    
            # Run tests if configured
            should_run_tests = self.testing_config.get('run_after_deployment', False)
            self.logger.info(f"\nTest configuration - run_after_deployment: {should_run_tests}")
            
            if should_run_tests:
                wait_time = self.testing_config.get('wait_time', 10)
                self.logger.info(f"Waiting {wait_time} seconds for deployment to stabilize before testing...")
                time.sleep(wait_time)
                
                self.logger.info("\n=== Running Deployment Tests ===")
                test_components = self.testing_config.get('components', {})
                if not test_components:
                    self.logger.warning("No test components configured, using defaults (all tests enabled)")
                    test_components = {
                        'function': True,
                        'scheduler': True,
                        'pubsub': True,
                        'http': True,
                        'pubsub_trigger': True
                    }
                
                self.logger.info("Test components to run:")
                for component, enabled in test_components.items():
                    self.logger.info(f"  - {component}: {'enabled' if enabled else 'disabled'}")
                
                tester = DeploymentTester()
                success = tester.run_selected_tests(
                    test_function=test_components.get('function', True),
                    test_scheduler=test_components.get('scheduler', True),
                    test_pubsub=test_components.get('pubsub', True),
                    test_http=test_components.get('http', True),
                    test_pubsub_trigger=test_components.get('pubsub_trigger', True)
                )
                
                if not success:
                    self.logger.error("Deployment tests failed")
                    return False
                
                self.logger.info("Deployment tests completed successfully")
            else:
                self.logger.info("Skipping deployment tests (disabled in configuration)")

            self.logger.info("\n=== Deployment Completed Successfully ===")
            return True

        except Exception as e:
            self.logger.error(f"Error during deployment: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

    def get_special_files(self) -> dict:
        """Get special files that need to be included in the package"""
        return {
            'requirements.txt': 'requirements.txt',
            'config.yaml': 'config.yaml',
            '__init__.py': '__init__.py',
            os.path.join('src', 'services', 'transaction_processor.py'): 'main.py'  # Entry point needs to be main.py
        }
    
    def analyze_dependencies(self, module_path):
        """Analyze Python file dependencies"""
        dependencies = set()
        try:
            with open(module_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Handle from imports
                    if line.startswith('from '):
                        parts = line.split('import')[0].split('from')[1].strip().split('.')
                        if any(pkg in parts[0] for pkg in ['services', 'models', 'utils', 'api']):
                            module_path = '/'.join(parts) + '.py'
                            dependencies.add(module_path)
                    # Handle direct imports
                    elif line.startswith('import '):
                        parts = line.split('import')[1].strip().split(',')
                        for part in parts:
                            part = part.strip()
                            if any(pkg in part for pkg in ['services', 'models', 'utils', 'api']):
                                module_path = part.replace('.', '/') + '.py'
                                dependencies.add(module_path)
        except Exception as e:
            self.logger.warning(f"Warning: Error analyzing dependencies for {module_path}: {e}")
        return dependencies
    
    def get_essential_modules(self, src_dir):
        """Get set of essential modules needed for deployment"""
        essential_modules = {'transaction_processor.py'}
        
        # First pass: analyze dependencies
        for root, _, files in os.walk(src_dir):
            python_files = [f for f in files if f.endswith('.py')]
            for file in python_files:
                src_path = os.path.join(root, file)
                if self.should_include(src_path, self.get_exclusion_patterns()):
                    deps = self.analyze_dependencies(src_path)
                    essential_modules.update(deps)
        
        return essential_modules
    
    def should_include_file(self, path, exclusion_patterns, essential_modules):
        """Check if a file should be included in the deployment package"""
        if not self.should_include(path, exclusion_patterns):
            return False
            
        rel_path = os.path.relpath(path, 'src')
        is_essential = rel_path in essential_modules
        is_in_essential_dir = os.path.dirname(rel_path) in essential_modules
        is_special = path in self.get_special_files()
        is_init = (os.path.basename(path) == '__init__.py' and 
                  any(m.startswith(os.path.dirname(rel_path)) for m in essential_modules))
        
        return is_essential or is_in_essential_dir or is_special or is_init

    def test_imports(self):
        """Test importing the required modules"""
        print("\n=== Testing Imports ===\n")
        
        # Create virtual environment
        venv.create(self.venv_dir, with_pip=True)
        
        # Get python executable path
        if os.name == 'nt':  # Windows
            python_path = os.path.join(self.venv_dir, "Scripts", "python.exe")
        else:  # Unix/Linux
            python_path = os.path.join(self.venv_dir, "bin", "python")
            
        # Install requirements with suppressed output
        print("Installing requirements...")
        try:
            subprocess.check_call(
                [python_path, "-m", "pip", "install", "-r", os.path.join(self.temp_dir, "requirements.txt")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            print(f"Error installing requirements: {e.stderr.decode()}")
            return False
        
        # Create test script
        test_script = os.path.join(self.temp_dir, "test_imports.py")
        with open(test_script, "w", encoding='utf-8') as f:
            f.write("""
import sys
import os

# Add the temp directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try importing required modules
try:
    from services_transaction_service import TransactionService
    from main import process_transactions
    print("[OK] Successfully imported TransactionService")
    print("[OK] Successfully imported process_transactions")
    print("[OK] All imports successful!")
except ImportError as e:
    print(f"[ERROR] During import testing: {str(e)}")
    sys.exit(1)
""")
        
        # Run test script
        try:
            subprocess.check_call([python_path, test_script])
            print("\n[OK] All tests passed!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] Deployment package tests failed!")
            return False

    def _load_terraform_state(self):
        """Load Terraform state if it exists"""
        try:
            terraform_dir = Path(project_root) / "terraform"
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
        
    def _get_terraform_resource(self, resource_type, resource_name):
        """Get resource details from Terraform state"""
        if not self.terraform_state:
            return None
            
        resources = self.terraform_state.get("resources", [])
        for resource in resources:
            if (resource.get("type") == resource_type and 
                resource.get("name") == resource_name):
                return resource.get("instances", [{}])[0].get("attributes", {})
        return None

def main():
    deployer = FunctionDeployer()
    success = deployer.deploy()
    if not success:
        exit(1)

if __name__ == "__main__":
    main() 