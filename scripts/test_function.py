import os
import sys
import json
import logging
from datetime import datetime, timedelta
from google.cloud import pubsub_v1
from google.cloud import logging as cloud_logging

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

from src.utils.config import Config

def setup_logging():
    """Set up logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def get_function_logs(cloud_logger, start_time, filter_extra=""):
    """Get and return function logs for a specific time period"""
    filter_str = (
        'resource.type="cloud_function" '
        f'resource.labels.function_name="transaction-processor" '
        f'timestamp >= "{start_time.isoformat()}Z" '
        f'{filter_extra}'
    )
    
    entries = cloud_logger.list_entries(filter_=filter_str, order_by=cloud_logging.DESCENDING, page_size=200)
    
    logs = []
    for entry in entries:
        # Format the log entry for better readability
        timestamp = entry.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        severity = entry.severity
        message = entry.payload
        
        # If message is a dict, format it nicely
        if isinstance(message, dict):
            try:
                message = json.dumps(message, indent=2)
            except:
                pass
        
        logs.append((timestamp, severity, message))
        
    return sorted(logs, key=lambda x: x[0])

def trigger_function():
    """Manually trigger the Cloud Function to process Gmail transactions and compare with scheduled runs"""
    logger = setup_logging()
    config = Config()
    project_id = config.get('project', 'id')
    topic_name = 'scheduled-transactions'
    
    logger.info(f"\n=== Triggering Transaction Processing ===")
    logger.info(f"Project: {project_id}")
    logger.info(f"Topic: {topic_name}")
    
    try:
        # Initialize Pub/Sub publisher
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_name)
        
        # Create message with current timestamp
        message = {
            'timestamp': datetime.utcnow().isoformat(),
            'check_from': (datetime.utcnow() - timedelta(hours=24)).isoformat(),
            'force_sync': True
        }
        
        logger.info(f"\nMessage payload:")
        logger.info(json.dumps(message, indent=2))
        
        # Initialize Cloud Logging client
        cloud_logger = cloud_logging.Client(project=project_id)
        start_time = datetime.utcnow()
        
        # Publish message
        future = publisher.publish(topic_path, json.dumps(message).encode())
        message_id = future.result()
        logger.info(f"\n✓ Message published: {message_id}")
        
        # Wait a moment for function to start
        import time
        time.sleep(5)
        
        # Get and display function logs
        logger.info("\n=== Function Logs ===")
        logs = get_function_logs(cloud_logger, start_time)
        
        if not logs:
            logger.warning("No logs found. The function might still be starting...")
            time.sleep(5)
            logs = get_function_logs(cloud_logger, start_time)
        
        for timestamp, severity, message in logs:
            # Use different colors/symbols for different severity levels
            if severity == 'ERROR':
                prefix = "❌"
            elif severity == 'WARNING':
                prefix = "⚠️"
            else:
                prefix = "ℹ️"
            
            logger.info(f"\n{prefix} [{timestamp}] {severity}:")
            logger.info(message)
        
        logger.info("\n=== Function Test Completed ===")
        return True
        
    except Exception as e:
        logger.error(f"\n❌ Error triggering function: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = trigger_function()
    if not success:
        sys.exit(1) 