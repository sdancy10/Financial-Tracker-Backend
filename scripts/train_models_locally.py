#!/usr/bin/env python3
"""
Train ML models locally using sample CSV data
This avoids the need for Cloud Storage access during development
"""

import os
import sys
import pandas as pd
import logging
from datetime import datetime

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(project_root)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import our modules
from src.models.transaction_trainer import TransactionModelTrainer, extract_vendor_features
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import FunctionTransformer
from sklearn.multioutput import MultiOutputClassifier

class LocalTransactionTrainer(TransactionModelTrainer):
    """Extended trainer that can load from local CSV files and uses production logic"""
    
    def __init__(self, project_id: str, local_mode: bool = True):
        # Skip parent init if in local mode to avoid GCS client initialization
        if local_mode:
            self.project_id = project_id
            self.region = "us-central1"
            self.bucket_name = f"{project_id}-ml-artifacts"
            self.ml_data_bucket = f"{project_id}-ml-data"
            self.logger = logging.getLogger(__name__)
            self.storage_client = None  # No storage client in local mode
        else:
            super().__init__(project_id)
            
    # Use the parent's create_pipeline method (no need to duplicate)
    # The production logic is already correct
            
    def load_training_data_from_csv(self, csv_path: str) -> pd.DataFrame:
        """Load training data from local CSV file and apply proper transformations"""
        self.logger.info(f"Loading training data from CSV: {csv_path}")
        
        # Load CSV data
        df = pd.read_csv(csv_path)
        self.logger.info(f"Loaded {len(df)} records from CSV")
        
        # Ensure date column is datetime
        df['date'] = pd.to_datetime(df['date'])
        
        # Apply the same transformations as production FeatureEngineer
        # Clean vendor names and generate metaphone codes
        if 'vendor' in df.columns:
            # Clean vendor names
            df['vendor_cleaned'] = df['vendor'].apply(self._clean_vendor_name)
            # Generate metaphone codes
            df['cleaned_metaphone'] = df['vendor_cleaned'].apply(self._generate_metaphone)
        
        # Extract date components
        df['day'] = df['date'].dt.day
        df['month'] = df['date'].dt.month
        df['year'] = df['date'].dt.year
        df['day_name'] = df['date'].dt.day_name()
        
        # Ensure text columns have content (fill empty values)
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone', 'template_used', 'account']
        for col in text_columns:
            if col in df.columns:
                df[col] = df[col].fillna('unknown')
                # Ensure no empty strings
                df[col] = df[col].replace('', 'unknown')
        
        return df
    
    def _clean_vendor_name(self, vendor: str) -> str:
        """Clean vendor name by removing special characters (same as FeatureEngineer)"""
        import re
        if pd.isna(vendor):
            return 'unknown'
        
        # Remove special characters and convert to lowercase
        cleaned = re.sub('[^A-Za-z ]+', ' ', str(vendor).lower())
        # Remove multiple spaces
        cleaned = re.sub(' +', ' ', cleaned).strip()
        
        return cleaned if cleaned else 'unknown'
    
    def _generate_metaphone(self, text: str) -> str:
        """Generate metaphone codes for text (same as FeatureEngineer)"""
        from metaphone import doublemetaphone
        
        if not text or text == 'unknown':
            return 'unknown'
        
        try:
            primary, secondary = doublemetaphone(text)
            # Return primary code, or secondary if primary is None
            return primary or secondary or 'unknown'
        except:
            return 'unknown'
        
    def train_model_locally(self, csv_path: str = None):
        """Train model using local CSV data with production logic"""
        # Use default sample data if no path provided
        if csv_path is None:
            csv_path = os.path.join(project_root, 'test_data', 'sample_transactions.csv')
            
        # Load data from CSV
        df = self.load_training_data_from_csv(csv_path)
        
        # Prepare training data (uses parent's method)
        train_df, test_df, sample_weights = self.prepare_training_data(df)
        
        # Use parent's _build_and_train_pipeline method (contains all production logic)
        pipeline = self._build_and_train_pipeline(train_df, test_df, sample_weights)
        
        # Calculate accuracy for return values
        from sklearn.metrics import accuracy_score
        
        # Prepare test data for evaluation (same as parent method)
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']
        vendor_features = ['amazon', 'aramark', 'great_clips', 'ohio_state', 'student_loan', 
                          'bar', 'supplements', 'best_buy', 'loan']
        feature_columns = text_columns + vendor_features
        
        # Apply vendor features to test data
        test_df = extract_vendor_features(test_df.copy())
        
        X_test = test_df[feature_columns].copy()
        for col in text_columns:
            X_test[col] = X_test[col].astype(str)
        y_test = test_df[['category', 'subcategory']].astype('string')
        
        # Make predictions
        predictions = pipeline.predict(X_test)
        
        # Calculate accuracy
        category_accuracy = accuracy_score(y_test['category'], predictions[:, 0])
        subcategory_accuracy = accuracy_score(y_test['subcategory'], predictions[:, 1])
        
        # Save model locally
        import joblib
        model_path = os.path.join('ml_models', f'local_model_{datetime.now().strftime("%Y%m%d_%H%M%S")}.joblib')
        os.makedirs('ml_models', exist_ok=True)
        
        with open(model_path, 'wb') as f:
            joblib.dump(pipeline, f)
        
        self.logger.info(f"Model saved locally to: {model_path}")
        
        return pipeline, category_accuracy, subcategory_accuracy
        
    def test_predictions(self, pipeline, sample_count: int = 5):
        """Test the model with some sample predictions"""
        # Load some test data
        csv_path = os.path.join(project_root, 'test_data', 'sample_transactions.csv')
        df = pd.read_csv(csv_path)
        
        # Take a random sample
        sample_df = df.sample(n=min(sample_count, len(df)))
        
        feature_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                          'template_used', 'account', 'day', 'month', 'year', 'day_name']
        
        X_sample = sample_df[feature_columns].copy()
        for col in feature_columns:
            X_sample[col] = X_sample[col].astype(str)
        
        # Make predictions
        predictions = pipeline.predict(X_sample)
        
        print("\n" + "="*80)
        print("Sample Predictions:")
        print("="*80)
        
        for idx, (_, row) in enumerate(sample_df.iterrows()):
            print(f"\nTransaction {idx + 1}:")
            print(f"  Vendor: {row['vendor']}")
            print(f"  Amount: ${row['amount']:.2f}")
            print(f"  Account: {row['account']}")
            print(f"  Date: {row['date']}")
            print(f"  Actual Category: {row['category']}")
            print(f"  Predicted Category: {predictions[idx, 0]}")
            print(f"  Actual Subcategory: {row['subcategory']}")
            print(f"  Predicted Subcategory: {predictions[idx, 1]}")
            print(f"  Match: {'✓' if predictions[idx, 0] == row['category'] else '✗'}")

def main():
    """Main function to train ML model locally"""
    print("ML Model Local Training")
    print("=" * 80)
    
    # Use a dummy project ID for local testing
    project_id = "local-test"
    
    # Create trainer instance
    trainer = LocalTransactionTrainer(project_id, local_mode=True)
    
    # Train the model
    print("\nTraining model with sample data...")
    pipeline, cat_acc, subcat_acc = trainer.train_model_locally()
    
    print(f"\nTraining Complete!")
    print(f"Category Accuracy: {cat_acc:.2%}")
    print(f"Subcategory Accuracy: {subcat_acc:.2%}")
    
    # Test with some predictions
    trainer.test_predictions(pipeline, sample_count=10)
    
    print("\n" + "="*80)
    print("Local training complete!")
    print("\nTo deploy this model to production:")
    print("1. Ensure you have training data in Cloud Storage")
    print("2. Run: python -c \"from src.models.transaction_trainer import TransactionModelTrainer; " +
          "trainer = TransactionModelTrainer('your-project-id'); " +
          "trainer.train_and_deploy_model('model_name')\"")

if __name__ == "__main__":
    main() 