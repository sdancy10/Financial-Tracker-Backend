from google.cloud import bigquery
from google.cloud import firestore
from datetime import datetime
import logging
from typing import Dict, Any, Optional, List
import json


class MLFeedbackService:
    """Service for collecting and managing ML prediction feedback"""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.bigquery = bigquery.Client(project=project_id)
        self.firestore = firestore.Client(project=project_id)
        self.logger = logging.getLogger(__name__)
        
        # BigQuery configuration
        self.dataset_id = f"{project_id.replace('-', '_')}_transactions"
        self.feedback_table_id = f"{self.project_id}.{self.dataset_id}.ml_feedback"
        
        # Ensure feedback table exists
        self._setup_feedback_table()
    
    def _setup_feedback_table(self):
        """Create BigQuery feedback table if it doesn't exist"""
        try:
            # Define schema
            schema = [
                bigquery.SchemaField("feedback_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("original_category", "STRING"),
                bigquery.SchemaField("original_subcategory", "STRING"),
                bigquery.SchemaField("user_category", "STRING", mode="REQUIRED"),
                bigquery.SchemaField("user_subcategory", "STRING"),
                bigquery.SchemaField("prediction_confidence", "FLOAT64"),
                bigquery.SchemaField("model_version", "STRING"),
                bigquery.SchemaField("vendor", "STRING"),
                bigquery.SchemaField("vendor_cleaned", "STRING"),
                bigquery.SchemaField("amount", "FLOAT64"),
                bigquery.SchemaField("template_used", "STRING"),
                bigquery.SchemaField("feedback_timestamp", "TIMESTAMP", mode="REQUIRED"),
                bigquery.SchemaField("transaction_date", "TIMESTAMP"),
            ]
            
            table = bigquery.Table(self.feedback_table_id, schema=schema)
            
            # Create table if it doesn't exist
            self.bigquery.create_table(table, exists_ok=True)
            self.logger.info(f"Feedback table {self.feedback_table_id} ready")
            
        except Exception as e:
            self.logger.error(f"Error setting up feedback table: {e}")
    
    def record_feedback(
        self,
        transaction_id: str,
        user_id: str,
        transaction_data: Dict[str, Any],
        original_category: str,
        original_subcategory: Optional[str],
        user_category: str,
        user_subcategory: Optional[str],
        model_version: Optional[str] = None,
        prediction_confidence: Optional[float] = None
    ) -> bool:
        """Record user feedback on ML prediction"""
        try:
            # Generate feedback ID
            feedback_id = f"{transaction_id}_{datetime.utcnow().timestamp()}"
            
            # Prepare feedback record
            feedback_record = {
                "feedback_id": feedback_id,
                "transaction_id": transaction_id,
                "user_id": user_id,
                "original_category": original_category,
                "original_subcategory": original_subcategory,
                "user_category": user_category,
                "user_subcategory": user_subcategory,
                "prediction_confidence": prediction_confidence,
                "model_version": model_version,
                "vendor": transaction_data.get("vendor"),
                "vendor_cleaned": transaction_data.get("vendor_cleaned"),
                "amount": float(transaction_data.get("amount", 0)),
                "template_used": transaction_data.get("template_used"),
                "feedback_timestamp": datetime.utcnow(),
                "transaction_date": transaction_data.get("date")
            }
            
            # Insert into BigQuery
            errors = self.bigquery.insert_rows_json(
                self.feedback_table_id,
                [feedback_record]
            )
            
            if errors:
                self.logger.error(f"Error inserting feedback: {errors}")
                return False
            
            self.logger.info(f"Recorded feedback for transaction {transaction_id}")
            
            # Also update Firestore for immediate effect
            self._update_firestore_feedback_flag(transaction_id, user_id)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error recording feedback: {e}")
            return False
    
    def _update_firestore_feedback_flag(self, transaction_id: str, user_id: str):
        """Mark transaction as having user feedback in Firestore"""
        try:
            transaction_ref = (
                self.firestore.collection('users')
                .document(user_id)
                .collection('transactions')
                .document(transaction_id)
            )
            
            # Get existing document to preserve all fields
            doc = transaction_ref.get()
            if not doc.exists:
                self.logger.warning(f"Transaction {transaction_id} not found for feedback flag update")
                return
            
            # Get all existing data
            existing_data = doc.to_dict()
            
            # Prepare update with all fields (existing + new)
            update_data = existing_data.copy()
            update_data['user_corrected'] = True
            update_data['feedback_timestamp'] = firestore.SERVER_TIMESTAMP
            
            # Use update() for efficiency - Firestore will only write changed fields
            transaction_ref.update(update_data)
            
        except Exception as e:
            self.logger.warning(f"Could not update Firestore feedback flag: {e}")
    
    def get_feedback_stats(self, days: int = 30) -> Dict[str, Any]:
        """Get feedback statistics for monitoring"""
        try:
            query = f"""
            SELECT 
                COUNT(*) as total_feedback,
                COUNT(DISTINCT user_id) as unique_users,
                COUNT(DISTINCT transaction_id) as unique_transactions,
                AVG(prediction_confidence) as avg_confidence,
                COUNT(DISTINCT model_version) as model_versions,
                COUNTIF(original_category != user_category) as category_changes,
                COUNT(DISTINCT user_category) as unique_categories
            FROM `{self.feedback_table_id}`
            WHERE feedback_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
            """
            
            query_job = self.bigquery.query(query)
            results = list(query_job)
            
            if results:
                row = results[0]
                return {
                    'total_feedback': row.total_feedback,
                    'unique_users': row.unique_users,
                    'unique_transactions': row.unique_transactions,
                    'avg_confidence': float(row.avg_confidence) if row.avg_confidence else 0.0,
                    'model_versions': row.model_versions,
                    'category_changes': row.category_changes,
                    'unique_categories': row.unique_categories,
                    'accuracy_rate': 1 - (row.category_changes / row.total_feedback) if row.total_feedback > 0 else 0
                }
            
            return {}
            
        except Exception as e:
            self.logger.error(f"Error getting feedback stats: {e}")
            return {}
    
    def get_category_accuracy(self, model_version: Optional[str] = None) -> Dict[str, float]:
        """Get accuracy by category"""
        try:
            version_filter = f"AND model_version = '{model_version}'" if model_version else ""
            
            query = f"""
            SELECT 
                original_category,
                COUNT(*) as total,
                COUNTIF(original_category = user_category) as correct,
                COUNT(DISTINCT user_category) as confusion_count
            FROM `{self.feedback_table_id}`
            WHERE feedback_timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            {version_filter}
            GROUP BY original_category
            ORDER BY total DESC
            """
            
            query_job = self.bigquery.query(query)
            results = {}
            
            for row in query_job:
                accuracy = row.correct / row.total if row.total > 0 else 0
                results[row.original_category] = {
                    'accuracy': accuracy,
                    'total_predictions': row.total,
                    'correct_predictions': row.correct,
                    'confusion_categories': row.confusion_count
                }
            
            return results
            
        except Exception as e:
            self.logger.error(f"Error getting category accuracy: {e}")
            return {}
    
    def export_training_feedback(self, start_date: str, end_date: str) -> str:
        """Export feedback data for model retraining"""
        try:
            query = f"""
            SELECT 
                t.transaction_id,
                t.user_id,
                t.vendor,
                t.vendor_cleaned,
                t.cleaned_metaphone,
                t.amount,
                t.account,
                t.template_used,
                EXTRACT(DAY FROM t.date) as day,
                EXTRACT(MONTH FROM t.date) as month,
                EXTRACT(YEAR FROM t.date) as year,
                FORMAT_TIMESTAMP('%A', t.date) as day_name,
                COALESCE(f.user_category, t.category) as category,
                COALESCE(f.user_subcategory, t.subcategory) as subcategory,
                (f.feedback_id IS NOT NULL) as is_user_corrected,
                t.model_version,
                t.date
            FROM `{self.project_id}.{self.dataset_id}.training_data` t
            LEFT JOIN `{self.feedback_table_id}` f
                ON t.transaction_id = f.transaction_id
                AND t.user_id = f.user_id
            WHERE DATE(t.date) BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY is_user_corrected DESC, t.date DESC
            """
            
            # Export to temporary table for training
            job_config = bigquery.QueryJobConfig(
                destination=f"{self.project_id}.{self.dataset_id}.training_data_with_feedback",
                write_disposition="WRITE_TRUNCATE"
            )
            
            query_job = self.bigquery.query(query, job_config=job_config)
            query_job.result()
            
            return f"{self.project_id}.{self.dataset_id}.training_data_with_feedback"
            
        except Exception as e:
            self.logger.error(f"Error exporting training feedback: {e}")
            raise 