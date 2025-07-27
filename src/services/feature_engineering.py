import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
import joblib
from google.cloud import storage
import logging
from datetime import datetime
import calendar
import re
from metaphone import doublemetaphone
from sklearn.feature_extraction.text import TfidfVectorizer
from src.models.transaction_trainer import extract_vendor_features


class FeatureEngineer:
    """Service for transforming transaction data into ML model features"""
    
    def __init__(self, project_id: str, model_version: Optional[str] = None):
        self.project_id = project_id
        self.model_version = model_version
        self.logger = logging.getLogger(__name__)
        
        # Storage client for loading model artifacts
        self.storage_client = storage.Client(project=project_id)
        self.bucket_name = f"{project_id}-ml-artifacts"
        
        # Feature columns expected by the model
        self.feature_columns = [
            'vendor', 'vendor_cleaned', 'cleaned_metaphone',
            'template_used', 'account', 'day', 'month', 'year', 'day_name'
        ]
        
        # Vendor patterns for feature extraction
        self.vendor_patterns = [
            ('amz', 'amazon'),
            ('a.mazon', 'amazon'),
            ('amazon', 'amazon'),
            ('aramark', 'aramark'),
            ('jpmc', 'aramark'),
            ('great clips', 'great_clips'),
            ('osu', 'ohio_state'),
            ('ohio state', 'ohio_state'),
            ('firstma', 'student_loan'),
            ('mohela', 'student_loan'),
            ('spirits', 'bar'),
            ('brewery', 'bar'),
            ('tavern', 'bar'),
            ('bar', 'bar'),
            ('supplement', 'supplements'),
            ('best buy', 'best_buy'),
            ('lending', 'loan')
        ]
        
        # Load model artifacts if available
        self.tfidf_vectorizers = {}
        self.model_metadata = {}
        if model_version:
            self._load_model_artifacts(model_version)
    
    def _load_model_artifacts(self, model_version: str):
        """Load TF-IDF vectorizers and metadata from model artifacts"""
        try:
            # Load metadata
            metadata_path = f"models/{model_version}/metadata.json"
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(metadata_path)
            
            if blob.exists():
                metadata_content = blob.download_as_text()
                import json
                self.model_metadata = json.loads(metadata_content)
                self.logger.info(f"Loaded model metadata for {model_version}")
            
            # TODO: Load TF-IDF vectorizers when we implement model serialization
            # For now, we'll use fresh vectorizers
            
        except Exception as e:
            self.logger.warning(f"Could not load model artifacts: {e}")
    
    def transform_transaction(self, transaction: Dict[str, Any]) -> pd.DataFrame:
        """Transform a single transaction into model features"""
        return self.transform_transactions([transaction])
    
    def transform_transactions(self, transactions: List[Dict[str, Any]]) -> pd.DataFrame:
        """Transform multiple transactions into model features"""
        # Convert to DataFrame for easier manipulation
        df = pd.DataFrame(transactions)
        
        # Clean vendor and generate metaphone
        df = self._process_vendors(df)
        
        # Extract date components
        df = self._extract_date_features(df)
        
        # Apply vendor-specific features
        df = self._apply_vendor_features(df)
        
        # Ensure all required columns exist
        for col in self.feature_columns:
            if col not in df.columns:
                df[col] = ''
        
        # Get vendor feature column names in a consistent order
        # IMPORTANT: This order must match exactly with transaction_trainer.py
        vendor_feature_columns = ['amazon', 'aramark', 'great_clips', 'ohio_state', 
                                  'student_loan', 'bar', 'supplements', 'best_buy', 'loan']
        
        # Return feature columns plus vendor feature columns
        return df.loc[:, self.feature_columns + vendor_feature_columns]
    
    def _process_vendors(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean vendor names and generate metaphone codes"""
        if 'vendor' not in df.columns:
            df['vendor'] = df['description'] if 'description' in df.columns else 'Unknown'
        
        # Clean vendor names
        df['vendor_cleaned'] = df['vendor'].apply(self._clean_vendor_name)
        
        # Generate metaphone codes
        df['cleaned_metaphone'] = df['vendor_cleaned'].apply(self._generate_metaphone)
        
        return df
    
    def _clean_vendor_name(self, vendor: str) -> str:
        """Clean vendor name by removing special characters"""
        if pd.isna(vendor):
            return ''
        
        # Remove special characters and convert to lowercase
        cleaned = re.sub('[^A-Za-z ]+', ' ', str(vendor).lower())
        # Remove multiple spaces
        cleaned = re.sub(' +', ' ', cleaned).strip()
        
        return cleaned
    
    def _generate_metaphone(self, text: str) -> str:
        """Generate metaphone codes for text"""
        if not text:
            return ''
        
        try:
            primary, secondary = doublemetaphone(text)
            # Return primary code, or secondary if primary is None
            return primary or secondary or ''
        except:
            return ''
    
    def _extract_date_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract date components from transaction dates"""
        if 'date' not in df.columns:
            # Use current date if no date provided
            df['date'] = datetime.now()
        
        # Convert to datetime if not already
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        
        # Extract components
        df['day'] = df['date'].dt.day
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year
        df['day_name'] = df['date'].dt.day_name()
        
        # Handle missing values
        df['day'] = df['day'].fillna(1).astype(int)
        df['month'] = df['month'].fillna(1).astype(int)
        df['year'] = df['year'].fillna(datetime.now().year).astype(int)
        df['day_name'] = df['day_name'].fillna('Monday')
        
        return df
    
    def _apply_vendor_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply vendor-specific binary features using the same logic as training"""
        # Use the exact same function used during training
        return extract_vendor_features(df)
    
    def prepare_for_prediction(self, transactions: List[Dict[str, Any]]) -> pd.DataFrame:
        """Prepare transactions for model prediction
        
        Returns a pandas DataFrame that can be used by both sklearn pipelines and Vertex AI
        """
        # Transform to features
        features_df = self.transform_transactions(transactions)
        
        # The model pipeline expects input in this exact column order:
        # First the text columns (for TF-IDF), then the numeric vendor features
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']
        
        # Get vendor feature names in consistent order (must match exactly what was used in training)
        # IMPORTANT: This order must match exactly with transaction_trainer.py
        vendor_feature_columns = ['amazon', 'aramark', 'great_clips', 'ohio_state', 
                                  'student_loan', 'bar', 'supplements', 'best_buy', 'loan']
        
        # Create the final feature order matching what the model expects
        all_columns = text_columns + vendor_feature_columns
        
        # Ensure all columns exist and are in the right order
        for col in all_columns:
            if col not in features_df.columns:
                if col in vendor_feature_columns:
                    features_df[col] = 0  # Default vendor features to 0
                else:
                    features_df[col] = ''  # Default text features to empty string
        
        # Select columns in the exact order
        features_df = features_df.loc[:, all_columns].copy()
        
        # Convert text columns to string type as expected by TfidfVectorizer
        for col in text_columns:
            features_df[col] = features_df[col].astype(str)
        
        # Convert numeric columns to proper type
        for col in vendor_feature_columns:
            features_df[col] = features_df[col].astype(int)
        
        # Return the DataFrame - sklearn pipelines can handle DataFrames directly
        return features_df
    
    def get_feature_names(self) -> List[str]:
        """Get the list of feature names in order"""
        # Match the exact order used in prepare_for_prediction
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']
        # IMPORTANT: This order must match exactly with transaction_trainer.py
        vendor_feature_columns = ['amazon', 'aramark', 'great_clips', 'ohio_state', 
                                  'student_loan', 'bar', 'supplements', 'best_buy', 'loan']
        return text_columns + vendor_feature_columns
    
    def validate_transaction_data(self, transaction: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate that transaction has required fields for feature engineering"""
        errors = []
        
        # Check for vendor or description
        if not transaction.get('vendor') and not transaction.get('description'):
            errors.append("Missing vendor or description field")
        
        # Check for amount (though not used in features, it's required)
        if 'amount' not in transaction:
            errors.append("Missing amount field")
        
        # Date is optional (will use current date if missing)
        # Template and account are optional (will be empty strings)
        
        return len(errors) == 0, errors 