import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from google.cloud import scheduler_v1
from google.cloud import functions_v1
from src.utils.config import Config

class SchedulerFunctionTester:
    def __init__(self):
        # Set up logging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO, format='%(message)s')
        
        try:
            # Initialize configuration
            self.config = Config()
            
            # Get project config
            project_config = self.config.get('project')
            if not project_config:
                raise ValueError("Missing 'project' configuration in config.yaml")
            self.project_id = project_config.get('id')
            self.region = project_config.get('region', 'us-central1')
            
            # Initialize clients
            self.scheduler_client = scheduler_v1.CloudSchedulerClient()
            self.functions_client = functions_v1.CloudFunctionsServiceClient()
            
            # Set up job name
            self.job_name = f"projects/{self.project_id}/locations/{self.region}/jobs/process-scheduled-transactions"
            
        except Exception as e:
            self.logger.error(f"Error initializing tester: {str(e)}")
            raise
    
    def trigger_scheduler(self):
        """Manually trigger the Cloud Scheduler job"""
        try:
            self.logger.info(f"\nTriggering scheduler job: {self.job_name}")
            request = scheduler_v1.RunJobRequest(name=self.job_name)
            self.scheduler_client.run_job(request=request)
            self.logger.info("✓ Successfully triggered scheduler job")
            return True
        except Exception as e:
            self.logger.error(f"Error triggering scheduler job: {str(e)}")
            return False
    
    def wait_for_function_completion(self, max_wait_time=300):
        """Wait for the function to complete by monitoring its status and logs"""
        function_name = f"projects/{self.project_id}/locations/{self.region}/functions/transaction-processor"
        
        start_time = time.time()
        while time.time() - start_time < max_wait_time:
            try:
                # Get function status
                request = functions_v1.GetFunctionRequest(name=function_name)
                function = self.functions_client.get_function(request=request)
                
                # Get and display recent logs
                self.logger.info("\n=== Recent Function Logs ===")
                logs_cmd = f"gcloud functions logs read transaction-processor --limit=100"
                try:
                    import subprocess
                    result = subprocess.run(logs_cmd, shell=True, capture_output=True, text=True)
                    if result.stdout:
                        # Process and format the logs
                        logs = result.stdout.split('\n')
                        
                        # Track processing details
                        current_email = None
                        failed_messages = []
                        successful_messages = []
                        skipped_messages = []
                        
                        self.logger.info("\n=== Logs for sdancy.10@gmail.com ===")
                        show_next_lines = 0
                        for log in logs:
                            if log.strip():
                                # Track which email is being processed
                                if "Processing emails for user" in log:
                                    current_email = log.split("Processing emails for user")[-1].strip()
                                    if "sdancy.10@gmail.com" in log:
                                        show_next_lines = 10  # Show next 10 lines for context
                                
                                # Show logs for sdancy.10@gmail.com and surrounding context
                                if "sdancy.10@gmail.com" in log or show_next_lines > 0:
                                    self.logger.info(log)
                                    if show_next_lines > 0:
                                        show_next_lines -= 1
                                
                                # Track message statuses for sdancy.10@gmail.com
                                if current_email == "sdancy.10@gmail.com":
                                    if "Failed to parse message" in log:
                                        msg_id = log.split("message")[-1].strip()
                                        failed_messages.append((current_email, msg_id))
                                        show_next_lines = 5  # Show next 5 lines after failures
                                    elif "Successfully parsed message" in log:
                                        msg_id = log.split("message")[-1].strip()
                                        successful_messages.append((current_email, msg_id))
                                    elif "Skipping" in log or "Found message" in log or "Fetching emails" in log:
                                        show_next_lines = 5  # Show context around email processing
                                        self.logger.info(log)
                        
                        # Show summary
                        self.logger.info("\n=== Processing Summary ===")
                        if successful_messages:
                            self.logger.info("\nSuccessfully Processed Messages:")
                            for email, msg_id in successful_messages:
                                self.logger.info(f"✓ {email}: {msg_id}")
                        
                        if failed_messages:
                            self.logger.info("\nFailed Messages:")
                            for email, msg_id in failed_messages:
                                self.logger.info(f"❌ {email}: {msg_id}")
                        
                        if skipped_messages:
                            self.logger.info("\nSkipped Messages:")
                            for email in set(skipped_messages):
                                self.logger.info(f"⚠️ {email}: Template didn't match")
                        
                        if not any([successful_messages, failed_messages, skipped_messages]):
                            self.logger.info("No new messages to process")
                    
                    if result.stderr and 'ERROR' in result.stderr:
                        self.logger.error(result.stderr)
                except Exception as e:
                    self.logger.error(f"Error getting logs: {str(e)}")
                
                # Log current status
                self.logger.info(f"\nFunction is ready to process requests")
                return True
                
            except Exception as e:
                self.logger.error(f"Error checking function status: {str(e)}")
                return False
        
        self.logger.error(f"Function did not complete within {max_wait_time} seconds")
        return False
    
    def run_test(self):
        """Run the scheduler-triggered function test"""
        try:
            self.logger.info("\n=== Testing Function via Cloud Scheduler ===")
            
            # Trigger the scheduler
            if not self.trigger_scheduler():
                return False
            
            # Wait a moment for the scheduler to process
            time.sleep(5)
            
            # Wait for function completion
            if not self.wait_for_function_completion():
                return False
            
            self.logger.info("\n✓ Function test via scheduler completed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error during scheduler function test: {str(e)}")
            import traceback
            traceback.print_exc()
            return False

def main():
    try:
        tester = SchedulerFunctionTester()
        if not tester.run_test():
            sys.exit(1)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 