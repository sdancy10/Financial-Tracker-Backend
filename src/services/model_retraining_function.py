import functions_framework
import os
import json
import logging
from datetime import datetime, timedelta
from google.cloud import bigquery, aiplatform, firestore
from src.services.data_export_service import DataExportService
from src.models.transaction_trainer import TransactionModelTrainer
from typing import Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@functions_framework.cloud_event
def trigger_model_retraining(cloud_event):
    """Cloud Function triggered by Cloud Scheduler for automated retraining"""
    project_id = os.environ.get('PROJECT_ID')
    if not project_id:
        logger.error("PROJECT_ID environment variable not set")
        return
    
    try:
        # Parse event data
        event_data = json.loads(cloud_event.data.get('message', {}).get('data', '{}'))
        min_feedback_count = event_data.get('min_feedback_count', 100)
        days_lookback = event_data.get('days_lookback', 7)
        
        # Check if we have enough new feedback data
        if not _has_sufficient_feedback(project_id, min_feedback_count, days_lookback):
            logger.info("Insufficient feedback data for retraining")
            return
        
        # Export fresh data from Firestore to BigQuery
        logger.info("Exporting data to BigQuery")
        export_service = DataExportService(project_id)
        export_service.setup_bigquery_dataset()
        job_id = export_service.export_firestore_to_bigquery()
        logger.info(f"BigQuery export completed: {job_id}")
        
        # Export to Parquet for training
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
        parquet_files = export_service.export_bigquery_to_parquet(start_date, end_date)
        logger.info(f"Parquet export completed: {len(parquet_files)} files")
        
        # Get next model version
        next_version = _get_next_model_version(project_id)
        model_display_name = f"transaction_model_v{next_version}"
        
        # Train new model
        logger.info(f"Starting training for {model_display_name}")
        trainer = TransactionModelTrainer(project_id)
        model, endpoint = trainer.train_and_deploy_model(model_display_name)
        
        # Deploy with traffic split for A/B testing
        if endpoint:
            _deploy_with_traffic_split(endpoint, model, traffic_percentage=20)
            logger.info(f"Model {model_display_name} deployed with 20% traffic")
        
        # Update model registry
        _update_model_registry(project_id, model, endpoint, next_version)
        
        # Log success metrics
        _log_training_metrics(project_id, model_display_name, len(parquet_files))
        
    except Exception as e:
        logger.error(f"Error during model retraining: {e}", exc_info=True)
        raise


def _has_sufficient_feedback(project_id: str, min_count: int, days: int) -> bool:
    """Check if we have enough new feedback data"""
    try:
        bq_client = bigquery.Client(project=project_id)
        dataset_id = f"{project_id.replace('-', '_')}_transactions"
        
        query = f"""
        SELECT COUNT(*) as feedback_count
        FROM `{project_id}.{dataset_id}.ml_feedback`
        WHERE feedback_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
        """
        
        query_job = bq_client.query(query)
        results = list(query_job)
        
        if results:
            feedback_count = results[0].feedback_count
            logger.info(f"Found {feedback_count} feedback entries in last {days} days")
            return feedback_count >= min_count
        
        return False
        
    except Exception as e:
        logger.warning(f"Could not check feedback count: {e}")
        return False


def _get_next_model_version(project_id: str) -> int:
    """Get the next model version number"""
    try:
        # List existing models in Vertex AI
        aiplatform.init(project=project_id, location='us-central1')
        models = aiplatform.Model.list(
            filter='display_name:"transaction_model_v*"',
            order_by="create_time desc"
        )
        
        if not models:
            return 1
        
        # Extract version numbers
        versions = []
        for model in models:
            try:
                version = int(model.display_name.split('_v')[-1])
                versions.append(version)
            except:
                continue
        
        return max(versions) + 1 if versions else 1
        
    except Exception as e:
        logger.warning(f"Could not get model versions: {e}")
        return 1


def _deploy_with_traffic_split(endpoint, model, traffic_percentage: int = 20):
    """Deploy model with traffic split for A/B testing"""
    try:
        # Get currently deployed models
        deployed_models = endpoint.list_models()
        
        if deployed_models:
            # Calculate traffic split
            existing_traffic = 100 - traffic_percentage
            traffic_split = {
                deployed_models[0].id: existing_traffic,
                model.resource_name: traffic_percentage
            }
            
            # Deploy with traffic split
            endpoint.deploy(
                model=model,
                traffic_split=traffic_split,
                machine_type="e2-micro",  # Cost-effective option
                min_replica_count=1,
                max_replica_count=1  # Reduced for cost savings
            )
        else:
            # First deployment, full traffic
            endpoint.deploy(
                model=model,
                deployed_model_display_name=model.display_name,
                machine_type="e2-micro",  # Cost-effective option
                min_replica_count=1,
                max_replica_count=1  # Reduced for cost savings
            )
            
    except Exception as e:
        logger.error(f"Error deploying with traffic split: {e}")
        raise


def _update_model_registry(project_id: str, model, endpoint, version: int):
    """Update Firestore model registry"""
    try:
        db = firestore.Client(project=project_id)
        
        # Update current model if this is full deployment
        current_ref = db.collection('models').document('current')
        current_ref.set({
            'model_id': model.display_name,
            'model_resource_name': model.resource_name,
            'endpoint_id': endpoint.resource_name if endpoint else None,
            'version': version,
            'updated_at': firestore.SERVER_TIMESTAMP,
            'status': 'testing'  # Start in testing mode with partial traffic
        })
        
        # Add version history
        version_ref = db.collection('models').document('versions').collection(model.display_name).document('info')
        version_ref.set({
            'model_id': model.display_name,
            'model_resource_name': model.resource_name,
            'endpoint_id': endpoint.resource_name if endpoint else None,
            'version': version,
            'created_at': firestore.SERVER_TIMESTAMP,
            'status': 'testing',
            'traffic_percentage': 20,
            'training_complete': True
        })
        
        logger.info(f"Updated model registry for version {version}")
        
    except Exception as e:
        logger.error(f"Error updating model registry: {e}")


def _log_training_metrics(project_id: str, model_name: str, data_files_count: int):
    """Log training metrics for monitoring"""
    try:
        # In production, this would write to Cloud Monitoring
        logger.info(f"""
        Training completed:
        - Model: {model_name}
        - Training data files: {data_files_count}
        - Timestamp: {datetime.utcnow().isoformat()}
        """)
        
    except Exception as e:
        logger.warning(f"Could not log metrics: {e}")


@functions_framework.http
def check_model_performance(request):
    """HTTP endpoint to check model performance and promote if good"""
    project_id = os.environ.get('PROJECT_ID')
    if not project_id:
        return json.dumps({'error': 'PROJECT_ID not set'}), 500
    
    try:
        # Get model performance metrics
        metrics = _get_model_performance_metrics(project_id)
        
        # Check if new model is performing better
        if metrics['new_model_accuracy'] > metrics['current_model_accuracy'] * 1.05:  # 5% improvement
            # Promote new model to full traffic
            _promote_model_to_production(project_id)
            return json.dumps({
                'status': 'promoted',
                'metrics': metrics
            }), 200
        else:
            return json.dumps({
                'status': 'monitoring',
                'metrics': metrics
            }), 200
            
    except Exception as e:
        logger.error(f"Error checking model performance: {e}")
        return json.dumps({'error': str(e)}), 500


def _get_model_performance_metrics(project_id: str) -> Dict[str, Any]:
    """Get performance metrics for current and new models"""
    try:
        bq_client = bigquery.Client(project=project_id)
        dataset_id = f"{project_id.replace('-', '_')}_transactions"
        
        query = f"""
        WITH model_accuracy AS (
            SELECT 
                model_version,
                COUNT(*) as total_predictions,
                SUM(CASE WHEN original_category = user_category THEN 1 ELSE 0 END) as correct_predictions,
                ROUND(SUM(CASE WHEN original_category = user_category THEN 1 ELSE 0 END) / COUNT(*), 3) as accuracy
            FROM `{project_id}.{dataset_id}.ml_feedback`
            WHERE feedback_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
            GROUP BY model_version
        )
        SELECT * FROM model_accuracy
        ORDER BY model_version DESC
        LIMIT 2
        """
        
        query_job = bq_client.query(query)
        results = list(query_job)
        
        metrics = {
            'current_model_accuracy': 0.0,
            'new_model_accuracy': 0.0
        }
        
        if len(results) >= 2:
            metrics['new_model_accuracy'] = float(results[0].accuracy)
            metrics['current_model_accuracy'] = float(results[1].accuracy)
        
        return metrics
        
    except Exception as e:
        logger.error(f"Error getting model metrics: {e}")
        return {'current_model_accuracy': 0.0, 'new_model_accuracy': 0.0}


def _promote_model_to_production(project_id: str):
    """Promote new model to full production traffic"""
    try:
        db = firestore.Client(project=project_id)
        aiplatform.init(project=project_id, location='us-central1')
        
        # Get current model info
        current_doc = db.collection('models').document('current').get()
        if not current_doc.exists:
            return
        
        model_data = current_doc.to_dict()
        endpoint_id = model_data.get('endpoint_id')
        
        if endpoint_id:
            # Update traffic to 100% for new model
            endpoint = aiplatform.Endpoint(endpoint_id)
            deployed_models = endpoint.list_models()
            
            if deployed_models:
                # Find the newest model
                newest_model = max(deployed_models, key=lambda m: m.create_time)
                
                # Update traffic split to 100% for newest model
                endpoint.update_traffic_split({newest_model.id: 100})
                
                # Update registry
                current_ref = db.collection('models').document('current')
                current_ref.update({
                    'status': 'production',
                    'traffic_percentage': 100,
                    'promoted_at': firestore.SERVER_TIMESTAMP
                })
                
                logger.info(f"Promoted model to production with 100% traffic")
                
    except Exception as e:
        logger.error(f"Error promoting model: {e}") 