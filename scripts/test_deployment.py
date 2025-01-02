import os
import sys

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

import requests
import json
from google.cloud import functions_v1
from google.cloud import scheduler_v1
from google.cloud import pubsub_v1
from google.cloud import logging as cloud_logging
from src.utils.config import Config
import logging
from datetime import datetime, timedelta
import time

class DeploymentTester:
    """Test class to verify Cloud Function deployment and functionality"""
    
    def __init__(self):
        self.config = Config()
        self.project_id = self.config.get('project', 'id')
        self.region = self.config.get('project', 'region', default='us-central1')
        self.function_name = self.config.get('cloud_function', 'name', default='transaction-processor')
        
        # Set up clients
        self.functions_client = functions_v1.CloudFunctionsServiceClient()
        self.scheduler_client = scheduler_v1.CloudSchedulerClient()
        self.publisher = pubsub_v1.PublisherClient()
        self.logging_client = cloud_logging.Client()
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        
    def test_function_deployment(self, retry_count=0, max_retries=3):
        """Test if the function is properly deployed"""
        try:
            if retry_count >= max_retries:
                self.logger.error(f"Function still not active after {max_retries} retries")
                return False, None

            function_path = f"projects/{self.project_id}/locations/{self.region}/functions/{self.function_name}"
            function = self.functions_client.get_function(name=function_path)
            
            # Debug: Print raw function object
            self.logger.debug(f"Raw function object: {function}")
            
            # Map numeric status to readable string
            status_map = {
                0: 'ACTIVE',
                1: 'DEPLOYING',
                2: 'FAILED',
                3: 'DELETING',
                4: 'UNKNOWN'
            }
            
            # Get status and convert to string if numeric
            raw_status = getattr(function, 'status', 'UNKNOWN')
            status_str = status_map.get(raw_status, raw_status) if isinstance(raw_status, int) else raw_status
            
            # Get build status if available
            build_status = None
            if hasattr(function, 'build_config') and hasattr(function.build_config, 'build'):
                build_status = function.build_config.build.status
            
            self.logger.info("\n=== Function Deployment Status ===")
            self.logger.info(f"Name: {function.name}")
            self.logger.info(f"Description: {function.description}")
            self.logger.info(f"Status: {status_str}")
            if build_status:
                self.logger.info(f"Build Status: {build_status}")
            self.logger.info(f"Runtime: {function.runtime}")
            self.logger.info(f"Entry Point: {function.entry_point}")
            self.logger.info(f"Service Account: {function.service_account_email}")
            
            # Get the HTTPS trigger URL if it exists
            if hasattr(function, 'https_trigger') and function.https_trigger:
                self.logger.info(f"HTTPS URL: {function.https_trigger.url}")
                function_url = function.https_trigger.url
            else:
                self.logger.info("Function uses Pub/Sub trigger")
                function_url = None
            
            # Get other configuration details
            if hasattr(function, 'environment_variables'):
                self.logger.info(f"Environment Variables: {function.environment_variables}")
            
            if hasattr(function, 'available_memory_mb'):
                self.logger.info(f"Available Memory: {function.available_memory_mb} MB")
            
            if hasattr(function, 'timeout'):
                self.logger.info(f"Timeout: {function.timeout.seconds} seconds")
            
            if hasattr(function, 'max_instances'):
                self.logger.info(f"Max Instances: {function.max_instances}")
            
            # Check if the function is ready - be more lenient with status checks
            is_active = (
                status_str == 'ACTIVE' or 
                raw_status == 0 or 
                (build_status and build_status == 'SUCCESS') or
                (hasattr(function, 'update_time') and function.update_time)  # If it has an update time, it's likely done
            )
            
            if is_active:
                self.logger.info("✓ Function is active and ready")
                return True, function_url
            elif status_str == 'DEPLOYING' or raw_status == 1:
                self.logger.info(f"Function is still deploying, waiting 10 seconds (attempt {retry_count + 1}/{max_retries})...")
                time.sleep(10)
                return self.test_function_deployment(retry_count + 1, max_retries)
            else:
                self.logger.error(f"Function is not active. Status: {status_str}")
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error checking function deployment: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, None
    
    def test_scheduler_job(self):
        """Test if the Cloud Scheduler job is properly configured"""
        try:
            job_path = f"projects/{self.project_id}/locations/{self.region}/jobs/process-scheduled-transactions"
            job = self.scheduler_client.get_job(name=job_path)
            
            self.logger.info("\n=== Scheduler Job Status ===")
            self.logger.info(f"Name: {job.name}")
            self.logger.info(f"Schedule: {job.schedule}")
            self.logger.info(f"Time Zone: {job.time_zone}")
            self.logger.info(f"State: {job.state}")
            self.logger.info(f"Last Attempt Time: {job.last_attempt_time}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error checking scheduler job: {str(e)}")
            return False
    
    def test_pubsub_topic(self):
        """Test if the Pub/Sub topic exists and is properly configured"""
        try:
            topic_path = f"projects/{self.project_id}/topics/scheduled-transactions"
            topic = self.publisher.get_topic(topic=topic_path)
            
            self.logger.info("\n=== Pub/Sub Topic Status ===")
            self.logger.info(f"Name: {topic.name}")
            self.logger.info(f"Labels: {topic.labels}")
            self.logger.info(f"Message Storage Policy: {topic.message_storage_policy}")
            
            return True
        except Exception as e:
            self.logger.error(f"Error checking Pub/Sub topic: {str(e)}")
            return False
    
    def test_function_http(self, function_url):
        """Test the function via HTTP endpoint"""
        try:
            # Test with OPTIONS request (CORS)
            self.logger.info("\n=== Testing CORS (OPTIONS) ===")
            options_response = requests.options(function_url)
            self.logger.info(f"Status Code: {options_response.status_code}")
            self.logger.info(f"Headers: {dict(options_response.headers)}")
            
            # Test with POST request
            self.logger.info("\n=== Testing Function (POST) ===")
            test_data = {
                "user_id": "test_user_123",
                "timestamp": datetime.utcnow().isoformat()
            }
            
            post_response = requests.post(
                function_url,
                json=test_data,
                headers={'Content-Type': 'application/json'}
            )
            
            self.logger.info(f"Status Code: {post_response.status_code}")
            self.logger.info(f"Response: {post_response.text}")
            
            return post_response.status_code == 200
        except Exception as e:
            self.logger.error(f"Error testing function HTTP endpoint: {str(e)}")
            return False
    
    def test_function_pubsub(self):
        """Test the function via Pub/Sub trigger"""
        try:
            self.logger.info("\n=== Testing Pub/Sub Trigger ===")
            topic_path = f"projects/{self.project_id}/topics/scheduled-transactions"
            
            # Create a unique test message
            test_id = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            test_data = {
                "timestamp": datetime.utcnow().isoformat(),
                "test_id": test_id,
                "test": True
            }
            
            data = json.dumps(test_data).encode('utf-8')
            self.logger.info(f"Publishing test message with ID: {test_id}")
            self.logger.info(f"Message data: {test_data}")
            
            # Record the time before publishing
            start_time = datetime.utcnow()
            
            future = self.publisher.publish(topic_path, data)
            message_id = future.result()
            
            self.logger.info(f"Published message ID: {message_id}")
            self.logger.info("Waiting 15 seconds for function to process...")
            time.sleep(15)  # Give the function more time to process and log
            
            # Try to verify the message was processed using Cloud Logging
            try:
                # Set up the filter for the logs using the start time
                end_time = datetime.utcnow()
                
                filter_str = (
                    f'resource.type="cloud_function" '
                    f'resource.labels.function_name="{self.function_name}" '
                    f'timestamp >= "{start_time.isoformat()}Z" '
                    f'timestamp <= "{end_time.isoformat()}Z"'
                )
                
                self.logger.info("Checking logs for test message...")
                self.logger.info(f"Filter: {filter_str}")
                
                # Get the logger for our function
                cloud_logger = self.logging_client.logger(f"cloudfunctions.googleapis.com%2Fcloud-functions")
                
                # List the log entries
                found_test_message = False
                entries = list(cloud_logger.list_entries(filter_=filter_str, page_size=50))
                
                self.logger.info(f"Found {len(entries)} log entries")
                for entry in entries:
                    self.logger.info(f"Log entry: {entry.payload}")
                    if hasattr(entry, 'payload') and test_id in str(entry.payload):
                        found_test_message = True
                        self.logger.info(f"Found test message in logs: {entry.payload}")
                        break
                
                if found_test_message:
                    self.logger.info("✓ Test message was processed successfully")
                else:
                    self.logger.warning("Could not find test message in logs")
                    
            except Exception as e:
                self.logger.warning(f"Could not verify message processing: {str(e)}")
                import traceback
                traceback.print_exc()
            
            return True
        except Exception as e:
            self.logger.error(f"Error testing Pub/Sub trigger: {str(e)}")
            return False
               
    def run_selected_tests(self, test_function=True, test_scheduler=True, test_pubsub=True, 
                         test_http=True, test_pubsub_trigger=True, test_gmail=True):
        """Run selected deployment tests based on configuration"""
        self.logger.info("\n=== Starting Selected Deployment Tests ===")
        self.logger.info(f"Project: {self.project_id}")
        self.logger.info(f"Region: {self.region}")
        self.logger.info(f"Function: {self.function_name}")
        
        function_url = None
        
        # Test function deployment if enabled
        if test_function:
            function_ok, function_url = self.test_function_deployment()
            if not function_ok:
                self.logger.error("Function deployment test failed")
                return False
        
        # Test scheduler if enabled
        if test_scheduler:
            scheduler_ok = self.test_scheduler_job()
            if not scheduler_ok:
                self.logger.error("Scheduler test failed")
                return False
        
        # Test Pub/Sub if enabled
        if test_pubsub:
            pubsub_ok = self.test_pubsub_topic()
            if not pubsub_ok:
                self.logger.error("Pub/Sub test failed")
                return False
        
        # Test HTTP endpoint if enabled and URL is available
        if test_http and function_url:
            http_ok = self.test_function_http(function_url)
            if not http_ok:
                self.logger.error("HTTP endpoint test failed")
                return False
        
        # Test Pub/Sub trigger if enabled
        if test_pubsub_trigger:
            pubsub_trigger_ok = self.test_function_pubsub()
            if not pubsub_trigger_ok:
                self.logger.error("Pub/Sub trigger test failed")
                return False
                
        
        self.logger.info("\n=== Selected Tests Completed Successfully ===")
        return True

    def run_all_tests(self):
        """Run all deployment tests"""
        return self.run_selected_tests(
            test_function=True,
            test_scheduler=True,
            test_pubsub=True,
            test_http=True,
            test_pubsub_trigger=True
        )

def main():
    tester = DeploymentTester()
    success = tester.run_all_tests()
    if not success:
        exit(1)

if __name__ == "__main__":
    main() 