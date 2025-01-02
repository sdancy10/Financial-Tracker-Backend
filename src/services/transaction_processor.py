"""Cloud Function for processing transactions from Gmail"""
from typing import Dict, Any
import functions_framework
import json
import logging
import base64
import os

# Set up logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# CORS headers
headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json'
}

@functions_framework.cloud_event
def process_transactions(cloud_event):
    """Cloud Function entry point for Pub/Sub trigger"""
    try:
        # Log the received event with clear marker
        logger.info("=== START PROCESSING PUBSUB MESSAGE ===")
        
        # Extract and log the Pub/Sub message
        if hasattr(cloud_event, 'data') and cloud_event.data:
            logger.info("Received cloud event data")
            if isinstance(cloud_event.data, dict) and "message" in cloud_event.data:
                logger.info("Found message in cloud event data")
                message = cloud_event.data["message"]
                if "data" in message:
                    message_data = base64.b64decode(message["data"]).decode()
                    logger.info(f"Raw message data: {message_data}")
                    
                    # Parse and log the message data
                    try:
                        data = json.loads(message_data)
                        logger.info(f"Parsed message data: {json.dumps(data, indent=2)}")
                        
                        # Special handling for test messages
                        if isinstance(data, dict) and data.get('test'):
                            logger.info(f"Received test message with ID: {data.get('test_id')}")
                            
                            # If this is a Gmail test, try to access Gmail
                            if data.get('test_gmail'):
                                logger.info("Testing Gmail access...")
                                
                                from src.services.transaction_service import TransactionService
                                from src.utils.config import Config
                                
                                # Initialize config and service
                                config = Config()
                                service = TransactionService(config.get('project', 'id'))
                                
                                # Get test user credentials
                                test_creds = service.get_user_credentials()
                                if not test_creds:
                                    logger.error("No test user credentials found")
                                    return json.dumps({"status": "error", "message": "No test user credentials found"})
                                
                                # Try to process transactions for the first user
                                test_user = test_creds[0]
                                logger.info(f"Testing Gmail access for user {test_user.get('email')}")
                                
                                success = service.process_user_transactions(test_user)
                                if success:
                                    logger.info("Successfully accessed Gmail and processed transactions")
                                    return json.dumps({"status": "success", "message": "Gmail test successful"})
                                else:
                                    logger.error("Failed to process transactions")
                                    return json.dumps({"status": "error", "message": "Failed to process transactions"})
                            
                            return json.dumps({"status": "success", "message": "Test message processed"})
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse message data: {e}")
                        return str(e), 400
                else:
                    logger.error("No data field in message")
                    return "No data field in message", 400
            else:
                logger.error("Invalid message format in cloud event data")
                return "Invalid message format", 400
        else:
            logger.error("No data in cloud event")
            return "No data in cloud event", 400
        
        from src.services.transaction_service import TransactionService
        from src.utils.config import Config
        
        # Initialize config and service inside function
        config = Config()
        service = TransactionService(config.get('project', 'id'))
        results = service.process_all_users()
        
        # Log the results
        logger.info(f"Processing completed with results: {json.dumps(results, indent=2)}")
        logger.info("=== END PROCESSING PUBSUB MESSAGE ===")
        return json.dumps(results)
        
    except Exception as e:
        logger.error(f"Error processing transactions: {str(e)}")
        logger.exception("Full traceback:")
        return str(e), 500 