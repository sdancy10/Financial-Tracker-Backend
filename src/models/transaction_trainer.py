import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import FunctionTransformer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import GridSearchCV
from sklearn.multioutput import MultiOutputClassifier
from google.cloud import aiplatform
from google.cloud import storage
import os
import json
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import joblib
import tempfile
from typing import List, Tuple, Dict, Any
import logging
from datetime import datetime


def extract_vendor_features(df):
    """Extract vendor-specific features as a standalone function"""
    if isinstance(df, pd.Series):
        df = df.to_frame()

    if 'vendor' not in df.columns:
        raise ValueError("The DataFrame does not contain the column 'vendor'")

    # Handle null values and convert to string before using str accessor
    df['vendor'] = df['vendor'].fillna('').astype(str).str.lower()
    
    vendor_list = [
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

    for _, vendor_name in vendor_list:
        df[vendor_name] = 0
    for vendor_code, vendor_name in vendor_list:
        df[vendor_name] = df['vendor'].apply(lambda x: vendor_code in str(x) if x else False).astype(int) + df[vendor_name]
    return df

    
class TransactionModelTrainer:
    def __init__(self, project_id: str, region: str = "us-central1", use_free_tier: bool = True):
        self.project_id = project_id
        self.region = region
        self.bucket_name = f"{project_id}-ml-artifacts"
        self.ml_data_bucket = f"{project_id}-ml-data"
        self.use_free_tier = use_free_tier
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Initialize clients
        self.storage_client = storage.Client(project=project_id)
        
        # Ensure ML artifacts bucket exists
        bucket = self.storage_client.bucket(self.bucket_name)
        if not bucket.exists():
            self.logger.info(f"Creating bucket: {self.bucket_name}")
            bucket = self.storage_client.create_bucket(self.bucket_name, location=region)
        
        # Initialize AI Platform with staging bucket
        aiplatform.init(project=project_id, location=region, staging_bucket=f"gs://{self.bucket_name}")
    
    def _get_machine_types(self):
        """Get machine types based on tier configuration"""
        if self.use_free_tier:
            return {
                'training': 'e2-standard-2',  # 2 vCPUs, 8GB RAM
                'inference': 'e2-standard-2' #'e2-micro'        # 0.25-2 vCPUs, 1GB RAM
            }
        else:
            return {
                'training': 'n1-standard-4',   # 4 vCPUs, 15GB RAM
                'inference': 'n1-standard-2'   # 2 vCPUs, 7.5GB RAM
            }
        
    def load_training_data_from_parquet(self) -> pd.DataFrame:
        """Load training data from Parquet files in Cloud Storage"""
        self.logger.info("Loading training data from Parquet files @ " + self.ml_data_bucket)
        
        # List all parquet files in the training directory
        bucket = self.storage_client.bucket(self.ml_data_bucket)
        blobs = bucket.list_blobs(prefix='training/')
        
        dfs = []
        file_count = 0
        
        for blob in blobs:
            if blob.name.endswith('.parquet'):
                self.logger.info(f"Loading {blob.name}")
                # Read parquet file directly from GCS
                df = pd.read_parquet(f"gs://{self.ml_data_bucket}/{blob.name}")
                dfs.append(df)
                file_count += 1
                
        if not dfs:
            raise ValueError("No Parquet files found in training directory")
            
        # Concatenate all dataframes
        combined_df = pd.concat(dfs, ignore_index=True)
        self.logger.info(f"Loaded {len(combined_df)} records from {file_count} files")
        
        return combined_df
        
    def prepare_training_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """Prepare data for training with proper splits and sample weights"""
        
        # Ensure all required columns exist
        required_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone', 
                          'amount', 'account', 'template_used', 
                          'day', 'month', 'year', 'day_name',
                          'category', 'subcategory', 'is_user_corrected']
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
            
        # Create sample weights - give more weight to user-corrected examples
        df['sample_weight'] = df['is_user_corrected'].apply(lambda x: 3.0 if x else 1.0)
        
        # Balance categories to prevent bias
        df = self._balance_categories(df)
        
        # Split by time to avoid data leakage
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Use 80% for training, 20% for testing
        train_cutoff = int(len(df) * 0.8)
        train_df = df.iloc[:train_cutoff]
        test_df = df.iloc[train_cutoff:]
        
        self.logger.info(f"Training set: {len(train_df)} records")
        self.logger.info(f"Test set: {len(test_df)} records")
        
        return train_df, test_df, train_df['sample_weight']
        
    def _balance_categories(self, df: pd.DataFrame, max_imbalance_ratio: float = 5.0) -> pd.DataFrame:
        """Balance categories to prevent model bias"""
        category_counts = df['category'].value_counts()
        
        # Handle case where there are no categories or only one category
        if len(category_counts) == 0:
            self.logger.warning("No categories found in data")
            return df
        
        if len(category_counts) == 1:
            self.logger.warning(f"Only one category found: {category_counts.index[0]}")
            return df
        
        # Find the minimum count
        min_count = category_counts.min()
        if pd.isna(min_count) or min_count == 0:
            self.logger.warning("Invalid minimum count, skipping balancing")
            return df
            
        max_allowed = int(min_count * max_imbalance_ratio)
        
        balanced_dfs = []
        for category in category_counts.index:
            category_df = df[df['category'] == category]
            
            if len(category_df) > max_allowed:
                # Prioritize user-corrected examples
                user_corrected = category_df[category_df['is_user_corrected'] == True]
                auto_labeled = category_df[category_df['is_user_corrected'] == False]
                
                # Keep all user-corrected examples
                n_to_sample = max_allowed - len(user_corrected)
                
                if n_to_sample > 0 and len(auto_labeled) > 0:
                    sampled_auto = auto_labeled.sample(n=min(n_to_sample, len(auto_labeled)), 
                                                      random_state=42)
                    balanced_dfs.append(pd.concat([user_corrected, sampled_auto]))
                else:
                    balanced_dfs.append(user_corrected)
            else:
                balanced_dfs.append(category_df)
        
        balanced_df = pd.concat(balanced_dfs, ignore_index=True)
        self.logger.info(f"Balanced dataset: {len(balanced_df)} records")
        
        return balanced_df

    def create_pipeline(self):
        """Create the ML pipeline with feature extraction and classification
        
        IMPORTANT: Column order must match exactly with _build_and_train_pipeline:
        Index 0-8: text columns ['vendor', 'vendor_cleaned', 'cleaned_metaphone', 
                                 'template_used', 'account', 'day', 'month', 'year', 'day_name']
        Index 9-17: vendor features ['amazon', 'aramark', 'great_clips', 'ohio_state', 
                                     'student_loan', 'bar', 'supplements', 'best_buy', 'loan']
        """
        # Define text column indices (matching the order in _build_and_train_pipeline)
        # Using indices instead of column names for Vertex AI compatibility
        text_column_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8]  # First 9 columns are text features
        
        # Create transformers using column indices instead of names
        # IMPORTANT: Set sparse=False to output dense arrays for Vertex AI compatibility
        text_transformers = [(f'tfidf_{i}', TfidfVectorizer(min_df=1, max_df=1.0, ngram_range=(1, 2)), i) 
                            for i in text_column_indices]

        column_transformer = ColumnTransformer(
            text_transformers,
            remainder='passthrough',
            sparse_threshold=0  # Force dense output
        )

        multi_target_classifier = MultiOutputClassifier(
            RandomForestClassifier(n_estimators=100, min_samples_split=2, min_samples_leaf=1, random_state=42)
        )

        return Pipeline([
            ('column_transformer', column_transformer),
            ('multi_target_classifier', multi_target_classifier)
        ])

    def _build_and_train_pipeline(self, train_df: pd.DataFrame, test_df: pd.DataFrame, sample_weights: pd.Series):
        """Build and train the ML pipeline"""
        # Create pipeline
        pipeline = self.create_pipeline()
        
        # Apply vendor feature extraction before training
        train_df = extract_vendor_features(train_df.copy())
        test_df = extract_vendor_features(test_df.copy())
        
        # Prepare features and labels - include vendor features
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']
        
        # Add vendor-specific feature columns
        vendor_features = ['amazon', 'aramark', 'great_clips', 'ohio_state', 'student_loan', 
                          'bar', 'supplements', 'best_buy', 'loan']
        
        # Combine all features
        feature_columns = text_columns + vendor_features
        
        # Convert text features to string to avoid TfidfVectorizer errors
        X_train = train_df[feature_columns].copy()
        for col in text_columns:
            X_train[col] = X_train[col].astype(str)
        
        y_train = train_df[['category', 'subcategory']].astype('string')
        
        X_test = test_df[feature_columns].copy()
        for col in text_columns:
            X_test[col] = X_test[col].astype(str)
        
        y_test = test_df[['category', 'subcategory']].astype('string')
        
        # Train the model with sample weights
        self.logger.info("Training model...")
        pipeline.fit(X_train, y_train, multi_target_classifier__sample_weight=sample_weights)
        
        # Evaluate the model
        self.logger.info("Evaluating model...")
        predictions = pipeline.predict(X_test)
        
        # Calculate accuracy
        category_accuracy = accuracy_score(y_test['category'], predictions[:, 0])
        subcategory_accuracy = accuracy_score(y_test['subcategory'], predictions[:, 1])
        
        self.logger.info(f"Category Accuracy: {category_accuracy:.2%}")
        self.logger.info(f"Subcategory Accuracy: {subcategory_accuracy:.2%}")
        
        # Print detailed classification report
        self.logger.info("\nCategory Classification Report:")
        self.logger.info(classification_report(y_test['category'], predictions[:, 0]))
        
        return pipeline

    def train_and_deploy_model(self, model_display_name: str, use_cloud_training: bool = False) -> tuple:
        """Train and deploy model using Vertex AI with Parquet data
        
        Args:
            model_display_name: Display name for the model
            use_cloud_training: If True, uses Vertex AI training. If False (default), trains locally.
            
        Returns:
            Tuple of (Model, Endpoint)
        """
        self.logger.info(f"Training model: {model_display_name} (cloud training: {use_cloud_training})")
        
        # Load data from Parquet files
        df = self.load_training_data_from_parquet()
        
        if df.empty:
            raise ValueError("No training data found")
            
        # Validate data quality
        unique_categories = df['category'].nunique()
        if unique_categories < 2:
            category_dist = df['category'].value_counts()
            self.logger.error(f"Insufficient category diversity: {unique_categories} unique categories")
            self.logger.error(f"Category distribution: {category_dist.to_dict()}")
            raise ValueError(
                f"Model training requires at least 2 different categories, but found {unique_categories}. "
                f"Please ensure your transactions have proper categories assigned. "
                f"Current distribution: {category_dist.head().to_dict()}"
            )
            
        self.logger.info(f"Found {unique_categories} unique categories in training data")
        
        # Prepare data
        train_df, test_df, sample_weights = self.prepare_training_data(df)
        
        # Get machine types based on tier
        machine_types = self._get_machine_types()
        
        if use_cloud_training:
            # Cloud training for scheduled retraining
            self.logger.info("Using cloud training (not yet implemented)")
            # TODO: Implement cloud training using CustomJob or CustomPythonPackageTrainingJob
            # For now, fall back to local training
            use_cloud_training = False
            
        # Train model locally and upload - simpler approach
        self.logger.info("Training model locally...")
        
        # Build and train the pipeline
        pipeline = self._build_and_train_pipeline(train_df, test_df, sample_weights)
        
        # Save model to Cloud Storage
        model_path = f"models/{model_display_name}/model.joblib"
        gcs_model_uri = f"gs://{self.bucket_name}/{model_path}"
        
        # Save locally first, then upload
        import tempfile
        tmp_file_path = None
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.joblib') as tmp_file:
                tmp_file_path = tmp_file.name
                joblib.dump(pipeline, tmp_file)
                tmp_file.flush()
            
            # Upload to GCS (file is closed now)
            bucket = self.storage_client.bucket(self.bucket_name)
            blob = bucket.blob(model_path)
            blob.upload_from_filename(tmp_file_path)
            self.logger.info(f"Model saved to {gcs_model_uri}")
            
            # Also save locally to ml_models folder
            local_ml_models_dir = "ml_models"
            if not os.path.exists(local_ml_models_dir):
                os.makedirs(local_ml_models_dir)
            
            local_model_path = os.path.join(local_ml_models_dir, f"{model_display_name}.joblib")
            with open(local_model_path, 'wb') as local_file:
                joblib.dump(pipeline, local_file)
            self.logger.info(f"Model also saved locally to {local_model_path}")
            
        finally:
            # Clean up temp file
            if tmp_file_path and os.path.exists(tmp_file_path):
                try:
                    os.unlink(tmp_file_path)
                except PermissionError:
                    # On Windows, sometimes the file is still locked
                    self.logger.warning(f"Could not delete temporary file {tmp_file_path}, will be cleaned up by OS")
        
        # Upload to Model Registry
        # Use sklearn 1.3 container to match our training environment
        model = aiplatform.Model.upload(
            display_name=model_display_name,
            artifact_uri=f"gs://{self.bucket_name}/models/{model_display_name}",
            serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-3:latest",
            serving_container_environment_variables={
                "SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE": "True"
            }
        )

        # Deploy model to endpoint
        endpoint = model.deploy(
            machine_type=machine_types['inference'],
            min_replica_count=1,
            max_replica_count=1,  # Reduced to 1 for cost savings
            accelerator_type=None,
            accelerator_count=None
        )

        self.logger.info(f"Model deployed to endpoint: {endpoint.resource_name}")
        return model, endpoint


