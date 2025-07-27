from google.cloud import firestore, bigquery, storage
from google.cloud.exceptions import NotFound
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Any, Optional
import os

class DataExportService:
    """Service for exporting transaction data from Firestore to BigQuery and Parquet files"""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.firestore = firestore.Client(project=project_id)
        self.bigquery = bigquery.Client(project=project_id)
        self.storage = storage.Client(project=project_id)
        
        # Dataset and bucket names
        self.dataset_id = f"{project_id.replace('-', '_')}_transactions"
        self.ml_data_bucket = f"{project_id}-ml-data"
        self.table_id = f"{project_id}.{self.dataset_id}.training_data"
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
    def setup_bigquery_dataset(self) -> None:
        """Create BigQuery dataset and table if they don't exist"""
        # Create dataset
        dataset_id_full = f"{self.project_id}.{self.dataset_id}"
        dataset = bigquery.Dataset(dataset_id_full)
        dataset.location = "US"
        dataset.description = "Transaction data for ML training"
        
        try:
            dataset = self.bigquery.create_dataset(dataset, exists_ok=True)
            self.logger.info(f"Dataset {dataset.dataset_id} created or already exists")
        except Exception as e:
            self.logger.error(f"Error creating dataset: {e}")
            raise
            
        # Create table with schema
        table_schema = [
            bigquery.SchemaField("transaction_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("user_id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("vendor", "STRING"),
            bigquery.SchemaField("vendor_cleaned", "STRING"),
            bigquery.SchemaField("cleaned_metaphone", "STRING", mode="REPEATED"),
            bigquery.SchemaField("amount", "FLOAT64", mode="REQUIRED"),
            bigquery.SchemaField("account", "STRING"),
            bigquery.SchemaField("template_used", "STRING"),
            bigquery.SchemaField("date", "TIMESTAMP", mode="REQUIRED"),
            bigquery.SchemaField("day", "INT64"),
            bigquery.SchemaField("month", "INT64"),
            bigquery.SchemaField("year", "INT64"),
            bigquery.SchemaField("day_name", "STRING"),
            bigquery.SchemaField("category", "STRING"),
            bigquery.SchemaField("subcategory", "STRING"),
            bigquery.SchemaField("is_user_corrected", "BOOL"),
            bigquery.SchemaField("prediction_confidence", "FLOAT64"),
            bigquery.SchemaField("model_version", "STRING"),
            bigquery.SchemaField("created_at", "TIMESTAMP"),
            bigquery.SchemaField("updated_at", "TIMESTAMP"),
        ]
        
        table = bigquery.Table(self.table_id, schema=table_schema)
        
        # Add partitioning and clustering
        table.time_partitioning = bigquery.TimePartitioning(
            type_=bigquery.TimePartitioningType.DAY,
            field="date"
        )
        table.clustering_fields = ["user_id", "category"]
        
        try:
            table = self.bigquery.create_table(table, exists_ok=True)
            self.logger.info(f"Table {table.table_id} created or already exists")
        except Exception as e:
            self.logger.error(f"Error creating table: {e}")
            raise
            
    def setup_storage_bucket(self) -> None:
        """Create Cloud Storage bucket for ML data if it doesn't exist"""
        try:
            bucket = self.storage.bucket(self.ml_data_bucket)
            if not bucket.exists():
                bucket = self.storage.create_bucket(
                    self.ml_data_bucket,
                    location="US"
                )
                
                # Set lifecycle rule to delete old files
                rule = storage.Lifecycle.Rule(
                    action={"type": "Delete"},
                    condition={"age": 90}  # Delete files older than 90 days
                )
                bucket.lifecycle_rules = [rule]
                bucket.patch()
                
                self.logger.info(f"Created bucket {self.ml_data_bucket}")
            else:
                self.logger.info(f"Bucket {self.ml_data_bucket} already exists")
        except Exception as e:
            self.logger.error(f"Error creating storage bucket: {e}")
            raise
            
    def export_firestore_to_bigquery(self, start_date: Optional[datetime] = None,
                                   end_date: Optional[datetime] = None) -> str:
        """Export transaction data from Firestore to BigQuery"""
        if not start_date:
            start_date = datetime.now() - timedelta(days=180)
        if not end_date:
            end_date = datetime.now()
            
        self.logger.info(f"Exporting data from {start_date} to {end_date}")
        
        # Get all users
        users = self.firestore.collection('users').stream()
        
        all_transactions = []
        for user_doc in users:
            user_id = user_doc.id
            user_data = user_doc.to_dict()
            
            # Skip users without email sync enabled
            if not user_data.get('email_sync_enabled', False):
                continue
                
            # Get transactions for this user
            transactions_query = (
                self.firestore.collection('users')
                .document(user_id)
                .collection('transactions')
                .where('date', '>=', start_date)
                .where('date', '<=', end_date)
            )
            
            for trans_doc in transactions_query.stream():
                trans_data = trans_doc.to_dict()
                
                # Prepare data for BigQuery
                bq_record = {
                    'transaction_id': trans_doc.id,
                    'user_id': user_id,
                    'vendor': trans_data.get('vendor'),
                    'vendor_cleaned': trans_data.get('vendor_cleaned'),
                    'cleaned_metaphone': trans_data.get('cleaned_metaphone', []),
                    'amount': float(trans_data.get('amount', 0)),
                    'account': trans_data.get('account'),
                    'template_used': trans_data.get('template_used'),
                    'date': trans_data.get('date'),
                    'day': trans_data.get('day'),
                    'month': trans_data.get('month'),
                    'year': trans_data.get('year'),
                    'day_name': trans_data.get('day_name'),
                }
                
                # Prioritize user_category over predicted_category
                # Treat "Uncategorized" as null for predicted values
                pred_cat = trans_data.get('predicted_category')
                if pred_cat == 'Uncategorized':
                    pred_cat = None
                bq_record['category'] = trans_data.get('user_category') or pred_cat or 'Uncategorized'
                
                # Same for subcategory
                pred_subcat = trans_data.get('predicted_subcategory')
                if pred_subcat == 'Uncategorized':
                    pred_subcat = None
                bq_record['subcategory'] = trans_data.get('user_subcategory') or pred_subcat or 'Uncategorized'
                
                # Mark as user corrected if user provided category
                bq_record['is_user_corrected'] = bool(trans_data.get('user_category') or trans_data.get('user_subcategory')) or trans_data.get('user_corrected', False)
                bq_record['prediction_confidence'] = trans_data.get('prediction_confidence')
                bq_record['model_version'] = trans_data.get('model_version')
                bq_record['created_at'] = trans_data.get('created_at')
                bq_record['updated_at'] = trans_data.get('last_modified')
                
                all_transactions.append(bq_record)
                
        if not all_transactions:
            self.logger.warning("No transactions found to export")
            return "No data exported"
            
        # Load data to BigQuery
        df = pd.DataFrame(all_transactions)
        
        # Configure load job
        job_config = bigquery.LoadJobConfig(
            write_disposition="WRITE_APPEND",
            schema_update_options=[bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION],
            time_partitioning=bigquery.TimePartitioning(field="date"),
        )
        
        # Load data
        job = self.bigquery.load_table_from_dataframe(
            df, self.table_id, job_config=job_config
        )
        job.result()  # Wait for job to complete
        
        self.logger.info(f"Exported {len(all_transactions)} transactions to BigQuery")
        return job.job_id
        
    def export_bigquery_to_parquet(self, start_date: str, end_date: str) -> List[str]:
        """Export BigQuery data to Parquet files for ML training"""
        # Create query to extract data with feedback
        query = f"""
        WITH feedback_data AS (
            SELECT 
                transaction_id,
                user_id,
                user_category as category,
                user_subcategory as subcategory,
                feedback_timestamp
            FROM `{self.project_id}.{self.dataset_id}.ml_feedback`
            WHERE DATE(feedback_timestamp) <= '{end_date}'
        )
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
            COALESCE(f.category, t.category) as category,
            COALESCE(f.subcategory, t.subcategory) as subcategory,
            (f.transaction_id IS NOT NULL) as is_user_corrected,
            t.model_version,
            t.date
        FROM `{self.table_id}` t
        LEFT JOIN feedback_data f
            ON t.transaction_id = f.transaction_id
            AND t.user_id = f.user_id
        WHERE DATE(t.date) BETWEEN '{start_date}' AND '{end_date}'
            AND COALESCE(f.category, t.category) != 'Uncategorized'  -- Only export categorized transactions
        ORDER BY is_user_corrected DESC, t.date DESC  -- Prioritize user-corrected data
        """
        
        # Execute query
        query_job = self.bigquery.query(query)
        df = query_job.to_dataframe()
        
        if df.empty:
            self.logger.warning("No data to export to Parquet")
            return []
            
        # Split data into chunks for better performance
        chunk_size = 10000
        parquet_files = []
        
        for i in range(0, len(df), chunk_size):
            chunk = df[i:i + chunk_size]
            
            # Generate filename
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"training/transactions_{timestamp}_{i//chunk_size}.parquet"
            
            # Convert to PyArrow table for better schema control
            table = pa.Table.from_pandas(chunk)
            
            # Upload to GCS
            bucket = self.storage.bucket(self.ml_data_bucket)
            blob = bucket.blob(filename)
            
            with blob.open('wb') as f:
                pq.write_table(table, f, compression='snappy')
                
            parquet_files.append(f"gs://{self.ml_data_bucket}/{filename}")
            
        self.logger.info(f"Exported {len(df)} records to {len(parquet_files)} Parquet files")
        return parquet_files
        
    def get_training_data_stats(self) -> Dict[str, Any]:
        """Get statistics about training data in BigQuery"""
        query = f"""
        SELECT 
            COUNT(*) as total_records,
            COUNT(DISTINCT user_id) as unique_users,
            COUNT(DISTINCT category) as unique_categories,
            COUNT(DISTINCT subcategory) as unique_subcategories,
            SUM(CASE WHEN is_user_corrected THEN 1 ELSE 0 END) as user_corrected_count,
            MIN(date) as earliest_date,
            MAX(date) as latest_date
        FROM `{self.table_id}`
        """
        
        result = list(self.bigquery.query(query))[0]
        
        return {
            'total_records': result.total_records,
            'unique_users': result.unique_users,
            'unique_categories': result.unique_categories,
            'unique_subcategories': result.unique_subcategories,
            'user_corrected_count': result.user_corrected_count,
            'date_range': {
                'start': result.earliest_date,
                'end': result.latest_date
            }
        }
        
    def cleanup_old_parquet_files(self, days_to_keep: int = 30) -> None:
        """Clean up old Parquet files from Cloud Storage"""
        bucket = self.storage.bucket(self.ml_data_bucket)
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        deleted_count = 0
        for blob in bucket.list_blobs(prefix='training/'):
            if blob.time_created < cutoff_date:
                blob.delete()
                deleted_count += 1
                
        self.logger.info(f"Deleted {deleted_count} old Parquet files") 