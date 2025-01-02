import functions_framework
from src.services.transaction_service import TransactionService
from src.utils.config import Config
import json
import logging
from datetime import datetime

# Initialize config and logging
config = Config()
logger = logging.getLogger(__name__)
logging_config = config.get('logging')
logging.basicConfig(
    level=logging_config['level'],
    format=logging_config['format']
)

@functions_framework.cloud_event
def process_scheduled_transactions(cloud_event):
    """Cloud Function triggered by Cloud Scheduler to process transactions"""
    try:
        start_time = datetime.utcnow()
        logger.info(f"Starting scheduled transaction processing at {start_time.isoformat()}")
        
        # Initialize service
        service = TransactionService(config.get('project', 'id'))
        
        # Process all users
        results = service.process_all_users()
        
        # Log results
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(
            f"Completed processing. Duration: {duration}s, "
            f"Success: {len(results['success'])}, "
            f"Failed: {len(results['failed'])}, "
            f"Total: {results['total_users']}"
        )
        
        return json.dumps({
            'success': True,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration_seconds': duration,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error in scheduled transaction processing: {str(e)}")
        raise e  # Re-raise to mark function as failed 