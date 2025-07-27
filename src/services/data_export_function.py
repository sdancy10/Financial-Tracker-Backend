import functions_framework
import os
import json
from datetime import datetime, timedelta
from src.services.data_export_service import DataExportService
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@functions_framework.cloud_event
def export_training_data(cloud_event):
    """Cloud Function triggered by Cloud Scheduler to export training data"""
    
    # Get project ID from environment
    project_id = os.environ.get('PROJECT_ID')
    if not project_id:
        logger.error("PROJECT_ID environment variable not set")
        return
        
    # Parse event data
    try:
        event_data = json.loads(cloud_event.data.get('message', {}).get('data', '{}'))
        action = event_data.get('action', 'export_all')
    except Exception as e:
        logger.error(f"Error parsing event data: {e}")
        action = 'export_all'
        
    # Initialize export service
    export_service = DataExportService(project_id)
    
    try:
        # Setup infrastructure if needed
        export_service.setup_bigquery_dataset()
        export_service.setup_storage_bucket()
        
        if action == 'export_all':
            # Export last 180 days of data
            logger.info("Starting full data export")
            job_id = export_service.export_firestore_to_bigquery()
            logger.info(f"BigQuery export completed: {job_id}")
            
            # Export to Parquet for training
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            
            parquet_files = export_service.export_bigquery_to_parquet(start_date, end_date)
            logger.info(f"Parquet export completed: {len(parquet_files)} files created")
            
            # Clean up old files
            export_service.cleanup_old_parquet_files(days_to_keep=30)
            
        elif action == 'export_incremental':
            # Export only last 7 days
            logger.info("Starting incremental data export")
            start_date = datetime.now() - timedelta(days=7)
            job_id = export_service.export_firestore_to_bigquery(start_date=start_date)
            logger.info(f"Incremental BigQuery export completed: {job_id}")
            
        elif action == 'stats':
            # Get and log statistics
            stats = export_service.get_training_data_stats()
            logger.info(f"Training data statistics: {json.dumps(stats, default=str)}")
            
        else:
            logger.warning(f"Unknown action: {action}")
            
    except Exception as e:
        logger.error(f"Error during data export: {e}", exc_info=True)
        raise

@functions_framework.http
def export_training_data_http(request):
    """HTTP endpoint for manual triggering of data export"""
    
    # Get project ID
    project_id = os.environ.get('PROJECT_ID')
    if not project_id:
        return {"error": "PROJECT_ID environment variable not set"}, 500
        
    # Parse request
    request_json = request.get_json(silent=True)
    action = request_json.get('action', 'stats') if request_json else 'stats'
    
    # Initialize export service
    export_service = DataExportService(project_id)
    
    try:
        if action == 'stats':
            stats = export_service.get_training_data_stats()
            return stats, 200
            
        elif action == 'export':
            # Setup infrastructure
            export_service.setup_bigquery_dataset()
            export_service.setup_storage_bucket()
            
            # Export data
            job_id = export_service.export_firestore_to_bigquery()
            
            # Export to Parquet
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            parquet_files = export_service.export_bigquery_to_parquet(start_date, end_date)
            
            return {
                "status": "success",
                "bigquery_job_id": job_id,
                "parquet_files": len(parquet_files)
            }, 200
            
        else:
            return {"error": f"Unknown action: {action}"}, 400
            
    except Exception as e:
        logger.error(f"Error during data export: {e}", exc_info=True)
        return {"error": str(e)}, 500 