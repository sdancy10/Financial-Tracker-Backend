#!/usr/bin/env python3
"""
Prepare ML training data from existing transaction data in Firestore or BigQuery
This script loads transaction data and converts it to Parquet format for ML training
"""

import os
import sys
import pandas as pd
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from google.cloud import firestore
from google.cloud import bigquery
from google.cloud import storage
from src.utils.config import Config
from src.services.feature_engineering import FeatureEngineer

class MLDataPreparer:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.firestore_client = firestore.Client(project=project_id)
        self.bigquery_client = bigquery.Client(project=project_id)
        self.storage_client = storage.Client(project=project_id)
        self.feature_engineer = FeatureEngineer(project_id)
        
        # Get ML bucket name from config
        config = Config()
        storage_config = config.get('storage')
        if storage_config is None:
            storage_config = {}
        
        buckets_config = storage_config.get('buckets', {})
        self.ml_bucket_name = buckets_config.get('ml_data', f"{project_id}-ml-data")
        self.ml_bucket_name = self.ml_bucket_name.replace('%PROJECT_ID%', project_id)
        
        logger.info(f"Initialized MLDataPreparer for project: {project_id}")
        logger.info(f"ML data bucket: {self.ml_bucket_name}")
    def print_wide_df_head(self,df, rows=5, cols_per_batch=5):
        """
        Pretty prints the head of a wide DataFrame by splitting into batches of columns,
        showing the same rows for each batch to maintain context.
        
        Args:
        - df: pandas DataFrame
        - rows: Number of rows to show (default: 5)
        - cols_per_batch: Number of columns per printed batch (adjust based on your terminal width; default: 5)
        """
        head = df.head(rows)  # Get the first N rows
        columns = head.columns.tolist()  # List of all columns
        
        for i in range(0, len(columns), cols_per_batch):
            batch_cols = columns[i:i + cols_per_batch]  # Slice columns for this batch
            print(f"Columns {i+1} to {i+len(batch_cols)}:")
            print(head[batch_cols])  # Print the batch with rows
            print("\n")  # Add spacing between batches
        
    def load_from_firestore(self, 
                           collection: str = 'transactions',
                           user_id: Optional[str] = None,
                           user_ids: Optional[List[str]] = None,
                           start_date: Optional[datetime] = None,
                           end_date: Optional[datetime] = None,
                           limit: Optional[int] = None) -> pd.DataFrame:
        """Load transaction data from Firestore
        
        Args:
            collection: Collection name (default 'transactions')
            user_id: Single user ID (deprecated, use user_ids)
            user_ids: List of user IDs to load transactions for
            start_date: Start date filter
            end_date: End date filter
            limit: Limit number of records per user
        """
        all_transactions = []
        
        # Handle backward compatibility
        if user_id and not user_ids:
            user_ids = [user_id]
        
        # If user_ids provided, load from user-specific collections
        if user_ids:
            for uid in user_ids:
                logger.info(f"Loading transactions for user: {uid}")
                
                # Use hierarchical collection path: users/{user_id}/transactions
                user_collection = self.firestore_client.collection('users').document(uid).collection('transactions')
                
                # Build query
                query = user_collection
                
                if start_date:
                    query = query.where('date', '>=', start_date)
                    
                if end_date:
                    query = query.where('date', '<=', end_date)
                    
                if limit:
                    query = query.limit(limit)
                    
                # Execute query and convert to list of dicts
                user_transactions = []
                for doc in query.stream():
                    data = doc.to_dict()
                    data['transaction_id'] = doc.id
                    data['user_id'] = uid  # Ensure user_id is set
                    user_transactions.append(data)
                    
                logger.info(f"Loaded {len(user_transactions)} transactions for user {uid}")
                all_transactions.extend(user_transactions)
        else:
            # Load from root collection (original behavior)
            logger.info(f"Loading transactions from root collection: {collection}")
            
            # Build query
            query = self.firestore_client.collection(collection)
            
            if start_date:
                query = query.where('date', '>=', start_date)
                
            if end_date:
                query = query.where('date', '<=', end_date)
                
            if limit:
                query = query.limit(limit)
                
            # Execute query and convert to list of dicts
            for doc in query.stream():
                data = doc.to_dict()
                data['transaction_id'] = doc.id
                all_transactions.append(data)
                
        logger.info(f"Total transactions loaded from Firestore: {len(all_transactions)}")
        
        if not all_transactions:
            return pd.DataFrame()
            
        # Convert to DataFrame
        df = pd.DataFrame(all_transactions)
        pd.set_option('display.width', None)  # No limit on overall output width (prevents forced wrapping/truncation)
        pd.set_option('display.max_columns', None)  # Show all columns without summarizing
        print(f"  - First 5 rows (batched):\n")
        self.print_wide_df_head(df, rows=5, cols_per_batch=5)  # Adjust cols_per_batch as needed
        # Drop old category/subcategory columns if they exist - we only use user_* and predicted_* fields
        if 'category' in df.columns:
            logger.info("Dropping old 'category' column from Firestore data - will use user_/predicted_ fields")
            df = df.drop('category', axis=1)
        if 'subcategory' in df.columns:
            logger.info("Dropping old 'subcategory' column from Firestore data - will use user_/predicted_ fields")
            df = df.drop('subcategory', axis=1)
        
        # Ensure date column is datetime
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            
        return df
        
    def load_from_bigquery(self,
                          dataset_id: str = 'financial_tracker',
                          table_id: str = 'transactions',
                          user_id: Optional[str] = None,
                          start_date: Optional[str] = None,
                          end_date: Optional[str] = None,
                          limit: Optional[int] = None) -> pd.DataFrame:
        """Load transaction data from BigQuery"""
        logger.info(f"Loading transactions from BigQuery: {dataset_id}.{table_id}")
        
        # Build query
        query = f"""
        SELECT *
        FROM `{self.project_id}.{dataset_id}.{table_id}`
        WHERE 1=1
        """
        
        if user_id:
            query += f"\n  AND user_id = '{user_id}'"
            
        if start_date:
            query += f"\n  AND date >= '{start_date}'"
            
        if end_date:
            query += f"\n  AND date <= '{end_date}'"
            
        if limit:
            query += f"\n LIMIT {limit}"
            
        logger.info(f"Executing query: {query}")
        
        # Execute query
        df = self.bigquery_client.query(query).to_dataframe()
        
        logger.info(f"Loaded {len(df)} transactions from BigQuery")
        
        # Drop old category/subcategory columns if they exist - we only use user_* and predicted_* fields
        if 'category' in df.columns:
            logger.info("Dropping old 'category' column from BigQuery data - will use user_/predicted_ fields")
            df = df.drop('category', axis=1)
        if 'subcategory' in df.columns:
            logger.info("Dropping old 'subcategory' column from BigQuery data - will use user_/predicted_ fields")
            df = df.drop('subcategory', axis=1)
        
        # Handle JSON columns if present
        json_columns = ['metadata', 'ml_features', 'user_feedback']
        for col in json_columns:
            if col in df.columns:
                df[col] = df[col].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
                
        return df
        
    def prepare_ml_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare ML features from raw transaction data"""
        logger.info(f"Preparing ML features for {len(df)} transactions")
        logger.info(f"Input columns: {', '.join(df.columns)}")
        
        # Create a copy to avoid modifying the original
        df = df.copy()
        pd.set_option('display.width', None)  # No limit on overall output width (prevents forced wrapping/truncation)
        pd.set_option('display.max_columns', None)  # Show all columns without summarizing
        print(f"  - First 5 rows (batched):\n")
        self.print_wide_df_head(df, rows=5, cols_per_batch=5)  # Adjust cols_per_batch as needed
        # Handle field mapping from Firestore
        # PRIORITY ORDER: user_category > predicted_category > default
        
        # Handle category mapping
        if 'user_category' in df.columns:
            logger.info("Found user_category column - prioritizing user-provided categories")
            # Log some examples before mapping
            sample_idx = df.index[:5]
            logger.info("Sample data before mapping:")
            for idx in sample_idx:
                if idx in df.index:
                    logger.info(f"  Row {idx}: user_cat='{df.loc[idx, 'user_category']}', pred_cat='{df.loc[idx, 'predicted_category'] if 'predicted_category' in df.columns else 'N/A'}'")
            
            # Use user_category where available, fall back to predicted_category
            if 'predicted_category' in df.columns:
                # Create a series for final category values
                # Start with predicted_category, but replace "Uncategorized" with NaN
                predicted_values = df['predicted_category'].copy()
                predicted_values[predicted_values == 'Uncategorized'] = None
                
                # Use user_category where available, otherwise use cleaned predicted values
                df['category'] = df['user_category'].combine_first(predicted_values).fillna('Uncategorized')
                
                user_count = df['user_category'].notna().sum()
                pred_count = (df['user_category'].isna() & predicted_values.notna()).sum()
                logger.info(f"Category sources: user={user_count}, predicted={pred_count}, uncategorized={len(df) - user_count - pred_count}")
            else:
                df['category'] = df['user_category'].fillna('Uncategorized')
                logger.info(f"Only user categories available: {df['user_category'].notna().sum()}")
                
            # Log examples after mapping
            logger.info("Sample data after category mapping:")
            for idx in sample_idx[:3]:  # Just show first 3
                if idx in df.index:
                    user_cat = df.loc[idx, 'user_category'] if 'user_category' in df.columns else 'N/A'
                    pred_cat = df.loc[idx, 'predicted_category'] if 'predicted_category' in df.columns else 'N/A'
                    final_cat = df.loc[idx, 'category']
                    logger.info(f"  Row {idx}: user='{user_cat}', pred='{pred_cat}' -> final='{final_cat}'")
        elif 'predicted_category' in df.columns:
            logger.info("Mapping predicted_category -> category (no user_category found)")
            df['category'] = df['predicted_category']
        elif 'category' not in df.columns:
            logger.warning("No category columns found, will add default")
            
        # Handle subcategory mapping  
        if 'user_subcategory' in df.columns:
            logger.info("Found user_subcategory column - prioritizing user-provided subcategories")
            # Use user_subcategory where available, fall back to predicted_subcategory
            if 'predicted_subcategory' in df.columns:
                # Create a series for final subcategory values
                # Start with predicted_subcategory, but replace "Uncategorized" with NaN
                predicted_sub_values = df['predicted_subcategory'].copy()
                predicted_sub_values[predicted_sub_values == 'Uncategorized'] = None
                
                # Use user_subcategory where available, otherwise use cleaned predicted values
                df['subcategory'] = df['user_subcategory'].combine_first(predicted_sub_values).fillna('Uncategorized')
                
                user_sub_count = df['user_subcategory'].notna().sum()
                pred_sub_count = (df['user_subcategory'].isna() & predicted_sub_values.notna()).sum()
                logger.info(f"Subcategory sources: user={user_sub_count}, predicted={pred_sub_count}, uncategorized={len(df) - user_sub_count - pred_sub_count}")
            else:
                df['subcategory'] = df['user_subcategory'].fillna('Uncategorized')
                logger.info(f"Only user subcategories available: {df['user_subcategory'].notna().sum()}")
        elif 'predicted_subcategory' in df.columns:
            logger.info("Mapping predicted_subcategory -> subcategory (no user_subcategory found)")
            df['subcategory'] = df['predicted_subcategory']
        elif 'subcategory' not in df.columns:
            logger.warning("No subcategory columns found, will add default")
            
        # Handle vendor mapping - user can also override vendor
        if 'user_vendor' in df.columns and 'vendor' in df.columns:
            logger.info("Found user_vendor column - using user-provided vendors where available")
            df['vendor'] = df['user_vendor'].fillna(df['vendor'])
            
        # Handle account_id to account mapping
        if 'account_id' in df.columns and 'account' not in df.columns:
            logger.info("Mapping account_id -> account")
            df['account'] = df['account_id']
            
        # Log current state
        logger.info(f"After field mapping, columns: {', '.join(df.columns)}")
        
        # Check for category column specifically
        if 'category' in df.columns:
            category_counts = df['category'].value_counts()
            logger.info(f"Category distribution: {category_counts.head().to_dict()}")
        else:
            logger.warning("No 'category' column found after mapping!")
            
        # Ensure required columns exist
        required_columns = ['vendor', 'amount', 'account', 'date', 'category', 'subcategory']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            logger.warning(f"Missing required columns: {missing_columns}")
            # Add default values for missing columns
            for col in missing_columns:
                if col == 'subcategory':
                    df[col] = 'Uncategorized'
                    logger.info(f"Added default '{col}' = 'Uncategorized'")
                elif col == 'category':
                    df[col] = 'Uncategorized'
                    logger.info(f"Added default '{col}' = 'Uncategorized'")
                elif col == 'vendor':
                    # Try to use description field if vendor is missing
                    if 'description' in df.columns:
                        df[col] = df['description']
                        logger.info(f"Using 'description' for missing 'vendor'")
                    else:
                        df[col] = 'Unknown'
                        logger.info(f"Added default '{col}' = 'Unknown'")
                else:
                    logger.warning(f"Missing required column {col}, unable to add default")
                    
            # Check again after adding defaults
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")
        
        # Replace null/None values in category and subcategory with 'Uncategorized'
        df['category'] = df['category'].fillna('Uncategorized')
        df['subcategory'] = df['subcategory'].fillna('Uncategorized')
            
        # Add feature engineering columns if not present
        if 'vendor_cleaned' not in df.columns:
            logger.info("Adding vendor_cleaned column")
            df['vendor_cleaned'] = df['vendor'].apply(self.feature_engineer._clean_vendor_name)
            
        if 'cleaned_metaphone' not in df.columns:
            logger.info("Adding cleaned_metaphone column")
            # Import metaphone if available
            try:
                from metaphone import doublemetaphone
                df['cleaned_metaphone'] = df['vendor_cleaned'].apply(
                    lambda x: doublemetaphone(x)[0] if x else ''
                )
            except ImportError:
                logger.warning("metaphone package not available, using simplified version")
                df['cleaned_metaphone'] = df['vendor_cleaned'].str.upper().str.replace(r'[^A-Z]', '', regex=True)
                
        if 'template_used' not in df.columns:
            logger.info("Adding template_used column")
            # Infer template from account type
            def infer_template(account):
                account_lower = str(account).lower()
                if 'credit' in account_lower:
                    return 'CREDIT_CARD_TEMPLATE'
                elif 'checking' in account_lower:
                    return 'BANK_TEMPLATE_A'
                elif 'savings' in account_lower:
                    return 'BANK_TEMPLATE_B'
                else:
                    return 'GENERIC_TEMPLATE'
            df['template_used'] = df['account'].apply(infer_template)
            
        # Ensure date components exist
        df['date'] = pd.to_datetime(df['date'])
        df['day'] = df['date'].dt.day
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year
        df['day_name'] = df['date'].dt.day_name()
        
        # Add is_user_corrected flag if not present
        if 'is_user_corrected' not in df.columns:
            # Mark as user corrected if user_category or user_subcategory was provided
            if 'user_category' in df.columns or 'user_subcategory' in df.columns:
                df['is_user_corrected'] = (
                    df.get('user_category', pd.Series()).notna() | 
                    df.get('user_subcategory', pd.Series()).notna()
                )
                user_corrected_count = df['is_user_corrected'].sum()
                logger.info(f"Marked {user_corrected_count} transactions as user-corrected based on user_category/user_subcategory")
            elif 'user_feedback' in df.columns:
                df['is_user_corrected'] = df['user_feedback'].apply(
                    lambda x: x.get('corrected', False) if isinstance(x, dict) else False
                )
            else:
                df['is_user_corrected'] = False
                
        # Ensure user_id exists
        if 'user_id' not in df.columns:
            logger.warning("No user_id column found, adding default")
            df['user_id'] = 'unknown'
            
        # Select and order columns for ML training
        ml_columns = [
            'transaction_id', 'user_id', 'vendor', 'vendor_cleaned', 'cleaned_metaphone',
            'amount', 'account', 'template_used', 'date', 'day', 'month', 'year', 
            'day_name', 'category', 'subcategory', 'is_user_corrected',
            # Include original fields for debugging and tracking
            'user_category', 'user_subcategory', 'predicted_category', 'predicted_subcategory'
        ]
        
        # Only include columns that exist
        ml_columns = [col for col in ml_columns if col in df.columns]
        df_ml = df[ml_columns].copy()
        
        logger.info(f"Prepared {len(df_ml)} transactions with {len(ml_columns)} features")
        logger.info(f"Final columns: {', '.join(df_ml.columns)}")
        
        # Final check for category diversity
        if 'category' in df_ml.columns:
            unique_categories = df_ml['category'].nunique()
            logger.info(f"Unique categories in prepared data: {unique_categories}")
            if unique_categories < 2:
                logger.warning(f"Only {unique_categories} unique categories found - this may cause training issues!")
        
        return df_ml
        
    def save_to_parquet(self, df: pd.DataFrame, output_prefix: str = 'training') -> str:
        """Save DataFrame to Parquet format in Cloud Storage"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{output_prefix}/transactions_{timestamp}.parquet"
        
        # Ensure bucket exists
        bucket = self.storage_client.bucket(self.ml_bucket_name)
        if not bucket.exists():
            logger.info(f"Creating bucket: {self.ml_bucket_name}")
            bucket = self.storage_client.create_bucket(self.ml_bucket_name, location='us-central1')
            
        # Save to Cloud Storage
        gcs_path = f"gs://{self.ml_bucket_name}/{filename}"
        logger.info(f"Saving {len(df)} records to: {gcs_path}")
        
        df.to_parquet(gcs_path, compression='snappy', index=False)
        
        logger.info(f"Successfully saved training data to: {gcs_path}")
        return gcs_path
        
    def prepare_training_data(self, 
                            source: str = 'firestore',
                            **kwargs) -> str:
        """Main method to prepare training data from specified source"""
        logger.info(f"Preparing training data from {source}")
        
        # Load data from specified source
        if source == 'firestore':
            df = self.load_from_firestore(**kwargs)
        elif source == 'bigquery':
            df = self.load_from_bigquery(**kwargs)
        else:
            raise ValueError(f"Unknown source: {source}. Use 'firestore' or 'bigquery'")
            
        if df.empty:
            logger.warning("No data loaded from source")
            return None
            
        # Prepare ML features
        df_ml = self.prepare_ml_features(df)
        
        # Save to Parquet
        output_path = self.save_to_parquet(df_ml)
        
        return output_path

def main():
    """Main function to prepare ML training data"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Prepare ML training data from existing transactions')
    parser.add_argument('--project-id', required=True, help='GCP project ID')
    parser.add_argument('--source', choices=['firestore', 'bigquery'], default='firestore',
                       help='Data source to load from')
    parser.add_argument('--user-id', help='Filter by single user ID (deprecated, use --user-ids)')
    parser.add_argument('--user-ids', nargs='+', help='Filter by multiple user IDs')
    parser.add_argument('--start-date', help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='End date (YYYY-MM-DD)')
    parser.add_argument('--limit', type=int, help='Limit number of records per user')
    parser.add_argument('--dataset', default='financial_tracker', help='BigQuery dataset ID')
    parser.add_argument('--table', default='transactions', help='BigQuery table ID')
    parser.add_argument('--collection', default='transactions', help='Firestore collection name')
    
    args = parser.parse_args()
    
    # Initialize preparer
    preparer = MLDataPreparer(args.project_id)
    
    # Prepare kwargs based on source
    kwargs = {}
    if args.source == 'firestore':
        kwargs['collection'] = args.collection
    else:  # bigquery
        kwargs['dataset_id'] = args.dataset
        kwargs['table_id'] = args.table
        
    # Add filters if provided
    if args.user_id:
        kwargs['user_id'] = args.user_id
    if args.user_ids:
        kwargs['user_ids'] = args.user_ids
    if args.start_date:
        # Parse date string to datetime
        kwargs['start_date'] = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.end_date:
        # Parse date string to datetime
        kwargs['end_date'] = datetime.strptime(args.end_date, '%Y-%m-%d')
    if args.limit:
        kwargs['limit'] = args.limit
        
    # Prepare training data
    try:
        output_path = preparer.prepare_training_data(source=args.source, **kwargs)
        if output_path:
            print(f"\nSuccess! Training data saved to: {output_path}")
            print(f"\nTo train a model with this data:")
            print(f"python -c \"from src.models.transaction_trainer import TransactionModelTrainer; " +
                  f"trainer = TransactionModelTrainer('{args.project_id}'); " +
                  f"trainer.train_and_deploy_model('transaction_model_v1')\"")
        else:
            print("\nNo data was prepared.")
    except Exception as e:
        logger.error(f"Error preparing training data: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main() 