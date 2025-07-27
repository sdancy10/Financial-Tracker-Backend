#!/usr/bin/env python3
"""
Local Trained Model Testing Script
Tests existing transaction categorization models (pickle files) without requiring GCP services
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock Google Cloud services before importing any modules that use them
from unittest.mock import Mock, MagicMock, patch

# Create mock modules for Google Cloud services
sys.modules['google.cloud.storage'] = MagicMock()
sys.modules['google.cloud.aiplatform'] = MagicMock()
sys.modules['google.cloud.bigquery'] = MagicMock()
sys.modules['google.cloud.firestore'] = MagicMock()
sys.modules['google.cloud.monitoring'] = MagicMock()
sys.modules['google.cloud.monitoring_dashboard'] = MagicMock()

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import random
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix
import joblib
import json
from typing import Dict, List, Tuple, Any

# Now import our ML components (with mocked GCP services)
from src.models.transaction_trainer import TransactionModelTrainer, extract_vendor_features
from src.services.feature_engineering import FeatureEngineer


class MockFeatureEngineer:
    """Mock version of FeatureEngineer for local testing without GCP"""
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.feature_columns = [
            'vendor', 'vendor_cleaned', 'cleaned_metaphone',
            'template_used', 'account', 'day', 'month', 'year', 'day_name'
        ]
    
    def transform_transaction(self, transaction: Dict[str, Any]) -> pd.DataFrame:
        """Transform single transaction (simplified)"""
        df = pd.DataFrame([transaction])
        # Add computed features
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df['day'] = df['date'].dt.day
            df['month'] = df['date'].dt.month
            df['year'] = df['date'].dt.year
            df['day_name'] = df['date'].dt.day_name()
        return df[self.feature_columns]
    
    def transform_transactions(self, transactions: List[Dict[str, Any]]) -> pd.DataFrame:
        """Transform multiple transactions"""
        df = pd.DataFrame(transactions)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df['day'] = df['date'].dt.day
            df['month'] = df['date'].dt.month
            df['year'] = df['date'].dt.year
            df['day_name'] = df['date'].dt.day_name()
        return df[self.feature_columns]
    
    def validate_transaction_data(self, transaction: Dict[str, Any]) -> tuple:
        """Validate transaction data"""
        errors = []
        if not transaction.get('vendor'):
            errors.append('Missing vendor')
        if not transaction.get('amount'):
            errors.append('Missing amount')
        return len(errors) == 0, errors


class LocalMLTester:
    """Test ML model locally without GCP dependencies"""
    
    def __init__(self):
        self.categories = [
            'Food & Dining', 'Shopping', 'Transportation', 'Bills & Utilities',
            'Entertainment', 'Healthcare', 'Education', 'Travel', 'Income'
        ]
        
        self.subcategories = {
            'Food & Dining': ['Groceries', 'Restaurants', 'Fast Food', 'Coffee Shops'],
            'Shopping': ['Clothing', 'Electronics', 'Home & Garden', 'General Merchandise'],
            'Transportation': ['Gas', 'Public Transit', 'Rideshare', 'Parking'],
            'Bills & Utilities': ['Electric', 'Internet', 'Phone', 'Insurance'],
            'Entertainment': ['Movies', 'Games', 'Streaming', 'Events'],
            'Healthcare': ['Doctor', 'Pharmacy', 'Dental', 'Vision'],
            'Education': ['Tuition', 'Books', 'Courses', 'Supplies'],
            'Travel': ['Flights', 'Hotels', 'Car Rental', 'Activities'],
            'Income': ['Salary', 'Freelance', 'Investment', 'Other']
        }
        
        self.vendor_mappings = {
            'walmart': ('Shopping', 'General Merchandise'),
            'target': ('Shopping', 'General Merchandise'),
            'amazon': ('Shopping', 'General Merchandise'),
            'starbucks': ('Food & Dining', 'Coffee Shops'),
            'mcdonalds': ('Food & Dining', 'Fast Food'),
            'shell': ('Transportation', 'Gas'),
            'uber': ('Transportation', 'Rideshare'),
            'netflix': ('Entertainment', 'Streaming'),
            'cvs': ('Healthcare', 'Pharmacy'),
            'att': ('Bills & Utilities', 'Phone')
        }
    
    def generate_sample_data(self, n_samples: int = 1000) -> pd.DataFrame:
        """Generate synthetic transaction data for testing"""
        print(f"Generating {n_samples} sample transactions...")
        
        data = []
        vendors = list(self.vendor_mappings.keys())
        accounts = ['Checking', 'Credit Card', 'Savings']
        templates = ['BANK_TEMPLATE_A', 'BANK_TEMPLATE_B', 'CREDIT_CARD_TEMPLATE']
        
        for i in range(n_samples):
            # Random vendor
            vendor = random.choice(vendors)
            category, subcategory = self.vendor_mappings[vendor]
            
            # Add some noise - 10% misclassified initially
            if random.random() < 0.1:
                category = random.choice([c for c in self.categories if c != category])
                subcategory = random.choice(self.subcategories[category])
            
            # Random amount based on category
            if category == 'Income':
                amount = round(random.uniform(1000, 5000), 2)
            elif category == 'Bills & Utilities':
                amount = round(random.uniform(50, 300), 2)
            else:
                amount = round(random.uniform(5, 200), 2)
            
            # Random date in last 180 days
            date = datetime.now() - timedelta(days=random.randint(0, 180))
            
            # Create transaction
            transaction = {
                'transaction_id': f'txn_{i:06d}',
                'user_id': f'user_{random.randint(1, 10):03d}',
                'vendor': f"{vendor.upper()} #{random.randint(1000, 9999)}",
                'vendor_cleaned': vendor,
                'cleaned_metaphone': self._get_metaphone(vendor),
                'amount': amount,
                'account': random.choice(accounts),
                'template_used': random.choice(templates),
                'date': date,
                'day': date.day,
                'month': date.month,
                'year': date.year,
                'day_name': date.strftime('%A'),
                'category': category,
                'subcategory': subcategory,
                'is_user_corrected': random.random() < 0.2  # 20% user corrections
            }
            
            data.append(transaction)
        
        df = pd.DataFrame(data)
        print(f"Generated {len(df)} transactions with {df['category'].nunique()} categories")
        return df
    
    def _get_metaphone(self, text: str) -> str:
        """Simple metaphone simulation"""
        # Simple phonetic reduction for testing
        replacements = {
            'ph': 'f', 'ck': 'k', 'qu': 'kw', 'x': 'ks',
            'wr': 'r', 'wh': 'w', 'gh': 'g'
        }
        result = text.lower()
        for old, new in replacements.items():
            result = result.replace(old, new)
        return result.upper()[:6]
    
    def test_feature_engineering(self, df: pd.DataFrame):
        """Test feature engineering pipeline"""
        print("\n=== Testing Feature Engineering ===")
        
        fe = MockFeatureEngineer('test-project')
        
        # Test single transaction
        sample_transaction = df.iloc[0].to_dict()
        print(f"\nSample transaction: {sample_transaction['vendor']}")
        
        # Transform transaction
        features = fe.transform_transaction(sample_transaction)
        print(f"Generated {len(features.columns)} features")
        print(f"Feature names: {list(features.columns)[:10]}...")
        
        # Test batch transformation
        batch_features = fe.transform_transactions(df.head(10).to_dict('records'))
        print(f"\nBatch transformation: {batch_features.shape}")
        
        # Test validation
        valid, errors = fe.validate_transaction_data(sample_transaction)
        print(f"\nValidation: {'Valid' if valid else f'Invalid - {errors}'}")
        
        return True
    
    def test_model_training(self, df: pd.DataFrame) -> Any:
        """Test model training locally"""
        print("\n=== Testing Model Training ===")
        
        # Split data
        train_df, test_df = train_test_split(df, test_size=0.2, random_state=42)
        print(f"Training set: {len(train_df)} samples")
        print(f"Test set: {len(test_df)} samples")
        
        # Initialize trainer (mock the GCP parts)
        trainer = MockLocalTrainer()
        
        # Train model
        print("\nTraining model...")
        model = trainer.train_local_model(train_df)
        
        # Evaluate on test set
        print("\nEvaluating model...")
        accuracy = trainer.evaluate_model(model, test_df)
        print(f"Overall accuracy: {accuracy:.2%}")
        
        return model
    
    def test_predictions(self, model: Any, df: pd.DataFrame):
        """Test making predictions"""
        print("\n=== Testing Predictions ===")
        
        # Take some test samples
        test_samples = df.sample(n=5, random_state=42)
        
        # Prepare features in the same format as training
        feature_cols = ['vendor_cleaned', 'amount', 'account', 'template_used']
        X_test = test_samples[feature_cols]
        
        # Make predictions
        predictions = model.predict(X_test)
        
        # Display results
        for i, (idx, transaction) in enumerate(test_samples.iterrows()):
            print(f"\nVendor: {transaction['vendor']}")
            print(f"Amount: ${transaction['amount']:.2f}")
            print(f"Account: {transaction['account']}")
            print(f"Actual category: {transaction['category']}")
            print(f"Predicted category: {predictions[i]}")
            print(f"Match: {'✓' if predictions[i] == transaction['category'] else '✗'}")
    
    def test_saved_pickle_model(self, pickle_path: str, test_transactions: List[Dict[str, Any]] = None):
        """Test a saved pickle model file with production-like feature engineering"""
        print(f"\n=== Testing Saved Model: {pickle_path} ===")
        
        # Load the model
        try:
            with open(pickle_path, 'rb') as f:
                model = joblib.load(f)
            print(f"✓ Successfully loaded model from {pickle_path}")
        except Exception as e:
            print(f"✗ Failed to load model: {e}")
            return
        
        # Use provided test transactions or create sample ones
        if test_transactions is None:
            test_transactions = [
                {
                    'vendor': 'AMAZON.COM',
                    'vendor_cleaned': 'amazon',
                    'cleaned_metaphone': 'AMSN',
                    'amount': 49.99,
                    'date': '2024-11-01',
                    'template_used': 'CREDIT_CARD_TEMPLATE',
                    'account': 'Credit Card',
                    'description': 'Amazon purchase'
                },
                {
                    'vendor': 'STARBUCKS COFFEE',
                    'vendor_cleaned': 'starbucks',
                    'cleaned_metaphone': 'STRBKS',
                    'amount': 5.75,
                    'date': '2024-11-02',
                    'template_used': 'BANK_TEMPLATE_A',
                    'account': 'Checking',
                    'description': 'Morning coffee'
                },
                {
                    'vendor': 'UBER TRIP',
                    'vendor_cleaned': 'uber',
                    'cleaned_metaphone': 'UBR',
                    'amount': 23.50,
                    'date': '2024-11-03',
                    'template_used': 'CREDIT_CARD_TEMPLATE',
                    'account': 'Credit Card',
                    'description': 'Ride to airport'
                },
                {
                    'vendor': 'WHOLE FOODS',
                    'vendor_cleaned': 'whole foods',
                    'cleaned_metaphone': 'HL FTS',
                    'amount': 127.43,
                    'date': '2024-11-04',
                    'template_used': 'CREDIT_CARD_TEMPLATE',
                    'account': 'Credit Card',
                    'description': 'Grocery shopping'
                }
            ]
        
        # Convert to DataFrame
        df = pd.DataFrame(test_transactions)
        
        # Apply vendor feature extraction (same as production)
        df = extract_vendor_features(df.copy())
        
        # Extract date features (same as production FeatureEngineer)
        df['date'] = pd.to_datetime(df['date'])
        df['day'] = df['date'].dt.day.astype(str)
        df['month'] = df['date'].dt.month.astype(str)
        df['year'] = df['date'].dt.year.astype(str)
        df['day_name'] = df['date'].dt.day_name()
        
        # Prepare features in the exact order expected by the model (same as production)
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']
        # Use the same vendor patterns as production
        vendor_patterns = [
            ('amz', 'amazon'), ('a.mazon', 'amazon'), ('amazon', 'amazon'),
            ('aramark', 'aramark'), ('jpmc', 'aramark'),
            ('great clips', 'great_clips'), ('osu', 'ohio_state'), ('ohio state', 'ohio_state'),
            ('firstma', 'student_loan'), ('mohela', 'student_loan'),
            ('spirits', 'bar'), ('brewery', 'bar'), ('tavern', 'bar'), ('bar', 'bar'),
            ('supplement', 'supplements'), ('best buy', 'best_buy'), ('lending', 'loan')
        ]
        vendor_feature_columns = list(set([pattern[1] for pattern in vendor_patterns]))
        
        all_columns = text_columns + vendor_feature_columns
        
        # Ensure all columns exist (same as production)
        for col in all_columns:
            if col not in df.columns:
                if col in vendor_feature_columns:
                    df[col] = 0  # Default vendor features to 0
                else:
                    df[col] = ''  # Default text features to empty string
        
        # Select features in correct order
        X = df[all_columns].copy()
        
        # Convert text columns to string (same as production)
        for col in text_columns:
            X[col] = X[col].astype(str)
        
        # Convert numeric columns to proper type (same as production)
        for col in vendor_feature_columns:
            X[col] = X[col].astype(int)
        
        try:
            # Make predictions
            predictions = model.predict(X)
            
            print("\n=== Predictions (Production-like Format) ===")
            for i, transaction in enumerate(test_transactions):
                # Format prediction like production ML service
                if hasattr(model, 'named_steps') and 'multi_target_classifier' in model.named_steps:
                    # Multi-output model (production format)
                    category = predictions[i][0] if len(predictions[i]) > 0 else 'Unknown'
                    subcategory = predictions[i][1] if len(predictions[i]) > 1 else 'Unknown'
                else:
                    # Single-output model (fallback)
                    category = predictions[i] if isinstance(predictions[i], str) else str(predictions[i])
                    subcategory = 'Unknown'
                
                # Create production-like result format
                result = {
                    'category': category,
                    'subcategory': subcategory,
                    'confidence': 0.85,  # Mock confidence
                    'model_version': os.path.basename(pickle_path),
                    'predicted_at': datetime.now().isoformat()
                }
                
                print(f"\nTransaction {i+1}:")
                print(f"  Vendor: {transaction['vendor']}")
                print(f"  Amount: ${transaction['amount']:.2f}")
                print(f"  Date: {transaction['date']}")
                print(f"  Predicted Category: {result['category']}")
                print(f"  Predicted Subcategory: {result['subcategory']}")
                print(f"  Confidence: {result['confidence']:.2f}")
                print(f"  Model Version: {result['model_version']}")
            
            print("\n✓ Model predictions completed successfully!")
            
            # Test model structure
            print("\n=== Model Structure ===")
            if hasattr(model, 'steps'):
                print(f"Pipeline steps: {[step[0] for step in model.steps]}")
            if hasattr(model, 'named_steps'):
                if 'column_transformer' in model.named_steps:
                    ct = model.named_steps['column_transformer']
                    print(f"ColumnTransformer features: {len(ct.transformers)} transformers")
                if 'multi_target_classifier' in model.named_steps:
                    clf = model.named_steps['multi_target_classifier']
                    print(f"Classifier type: {type(clf).__name__}")
                    print(f"Multi-output: {hasattr(clf, 'estimators_')}")
            
            # Test feature engineering compatibility
            print("\n=== Feature Engineering Compatibility ===")
            print(f"Expected text columns: {text_columns}")
            print(f"Expected vendor features: {vendor_feature_columns}")
            print(f"Total features: {len(all_columns)}")
            print(f"Model input shape: {X.shape}")
            
        except Exception as e:
            print(f"\n✗ Error making predictions: {e}")
            import traceback
            traceback.print_exc()
    
    def test_production_like_features(self, pickle_path: str):
        """Test feature engineering that exactly matches production ML service"""
        print(f"\n=== Testing Production-like Feature Engineering ===")
        
        # Load the model
        try:
            with open(pickle_path, 'rb') as f:
                model = joblib.load(f)
            print(f"✓ Successfully loaded model from {pickle_path}")
        except Exception as e:
            print(f"✗ Failed to load model: {e}")
            return
        
        # Test transactions that match production format
        test_transactions = [
            {
                'vendor': 'AMAZON.COM',
                'amount': 49.99,
                'date': '2024-11-01',
                'template_used': 'CREDIT_CARD_TEMPLATE',
                'account': 'Credit Card',
                'description': 'Amazon purchase'
            },
            {
                'vendor': 'STARBUCKS COFFEE',
                'amount': 5.75,
                'date': '2024-11-02',
                'template_used': 'BANK_TEMPLATE_A',
                'account': 'Checking',
                'description': 'Morning coffee'
            }
        ]
        
        # Simulate production FeatureEngineer.prepare_for_prediction
        print("\n--- Simulating Production Feature Engineering ---")
        
        # Step 1: Transform transactions (like production)
        df = pd.DataFrame(test_transactions)
        
        # Step 2: Apply vendor feature extraction (same as production)
        df = extract_vendor_features(df.copy())
        print(f"✓ Applied vendor feature extraction")
        
        # Step 3: Extract date features (same as production)
        df['date'] = pd.to_datetime(df['date'])
        df['day'] = df['date'].dt.day.astype(str)
        df['month'] = df['date'].dt.month.astype(str)
        df['year'] = df['date'].dt.year.astype(str)
        df['day_name'] = df['date'].dt.day_name()
        print(f"✓ Extracted date features")
        
        # Step 4: Prepare features in exact production order
        text_columns = ['vendor', 'vendor_cleaned', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']
        # Use the same vendor patterns as production
        vendor_patterns = [
            ('amz', 'amazon'), ('a.mazon', 'amazon'), ('amazon', 'amazon'),
            ('aramark', 'aramark'), ('jpmc', 'aramark'),
            ('great clips', 'great_clips'), ('osu', 'ohio_state'), ('ohio state', 'ohio_state'),
            ('firstma', 'student_loan'), ('mohela', 'student_loan'),
            ('spirits', 'bar'), ('brewery', 'bar'), ('tavern', 'bar'), ('bar', 'bar'),
            ('supplement', 'supplements'), ('best buy', 'best_buy'), ('lending', 'loan')
        ]
        vendor_feature_columns = list(set([pattern[1] for pattern in vendor_patterns]))
        
        all_columns = text_columns + vendor_feature_columns
        
        # Step 5: Ensure all columns exist (same as production)
        for col in all_columns:
            if col not in df.columns:
                if col in vendor_feature_columns:
                    df[col] = 0  # Default vendor features to 0
                else:
                    df[col] = ''  # Default text features to empty string
        
        # Step 6: Select columns in exact order
        features_df = df[all_columns].copy()
        
        # Step 7: Convert text columns to string (same as production)
        for col in text_columns:
            features_df[col] = features_df[col].astype(str)
        
        # Step 8: Convert numeric columns to proper type (same as production)
        for col in vendor_feature_columns:
            features_df[col] = features_df[col].astype(int)
        
        # Step 9: Convert to list of lists (same as production)
        features_list = features_df.values.tolist()
        
        print(f"✓ Prepared features in production format")
        print(f"  Text columns: {text_columns}")
        print(f"  Vendor features: {vendor_feature_columns}")
        print(f"  Total features: {len(all_columns)}")
        print(f"  Input shape: {features_df.shape}")
        
        # Step 10: Make predictions
        try:
            predictions = model.predict(features_list)
            
            print("\n--- Production-like Predictions ---")
            for i, transaction in enumerate(test_transactions):
                # Format like production ML service
                if hasattr(model, 'named_steps') and 'multi_target_classifier' in model.named_steps:
                    category = predictions[i][0] if len(predictions[i]) > 0 else 'Unknown'
                    subcategory = predictions[i][1] if len(predictions[i]) > 1 else 'Unknown'
                else:
                    category = predictions[i] if isinstance(predictions[i], str) else str(predictions[i])
                    subcategory = 'Unknown'
                
                result = {
                    'category': category,
                    'subcategory': subcategory,
                    'confidence': 0.85,
                    'model_version': os.path.basename(pickle_path),
                    'predicted_at': datetime.now().isoformat()
                }
                
                print(f"\nTransaction {i+1}:")
                print(f"  Vendor: {transaction['vendor']}")
                print(f"  Amount: ${transaction['amount']:.2f}")
                print(f"  Result: {result}")
            
            print("\n✓ Production-like feature engineering test completed!")
            
        except Exception as e:
            print(f"\n✗ Error in production-like prediction: {e}")
            import traceback
            traceback.print_exc()

    def generate_report(self, df: pd.DataFrame):
        """Generate a test report"""
        print("\n=== Test Report ===")
        print(f"Total transactions: {len(df)}")
        print(f"Date range: {df['date'].min()} to {df['date'].max()}")
        print(f"Unique users: {df['user_id'].nunique()}")
        print(f"User corrections: {df['is_user_corrected'].sum()} ({df['is_user_corrected'].mean():.1%})")
        
        print("\nCategory distribution:")
        category_dist = df['category'].value_counts()
        for cat, count in category_dist.items():
            print(f"  {cat}: {count} ({count/len(df):.1%})")
        
        print("\nTop vendors:")
        top_vendors = df['vendor_cleaned'].value_counts().head(10)
        for vendor, count in top_vendors.items():
            print(f"  {vendor}: {count}")


class MockLocalTrainer:
    """Mock trainer for local testing without GCP"""
    
    def train_local_model(self, df: pd.DataFrame):
        """Train a simple model locally"""
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.feature_extraction.text import CountVectorizer
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.compose import ColumnTransformer
        
        # Prepare features and labels
        feature_cols = ['vendor_cleaned', 'amount', 'account', 'template_used']
        X = df[feature_cols]
        y = df[['category', 'subcategory']]
        
        # Create preprocessing pipeline
        numeric_features = ['amount']
        text_features = ['vendor_cleaned', 'account', 'template_used']
        
        numeric_transformer = StandardScaler()
        text_transformer = CountVectorizer(max_features=100)
        
        # Note: This is simplified - real model uses TfidfVectorizer and more features
        preprocessor = ColumnTransformer(
            transformers=[
                ('num', numeric_transformer, ['amount']),
                ('vendor', text_transformer, 'vendor_cleaned')
            ])
        
        # Create and train model
        model = Pipeline([
            ('preprocessor', preprocessor),
            ('classifier', RandomForestClassifier(n_estimators=100, random_state=42))
        ])
        
        # Train on category only for simplicity
        model.fit(X, y['category'])
        
        return model
    
    def evaluate_model(self, model, test_df: pd.DataFrame) -> float:
        """Evaluate model performance"""
        feature_cols = ['vendor_cleaned', 'amount', 'account', 'template_used']
        X_test = test_df[feature_cols]
        y_test = test_df['category']
        
        # Make predictions
        y_pred = model.predict(X_test)
        
        # Calculate accuracy
        accuracy = (y_pred == y_test).mean()
        
        # Print classification report
        print("\nClassification Report:")
        print(classification_report(y_test, y_pred))
        
        return accuracy


def main():
    """Run local ML tests"""
    print("=== Transaction ML Model - Local Testing ===\n")
    
    tester = LocalMLTester()
    
    # Check if user wants to test a saved model
    if len(sys.argv) > 1 and sys.argv[1] == '--test-pickle':
        # Test saved pickle model
        pickle_path = sys.argv[2] if len(sys.argv) > 2 else 'ml_models/transaction_model_v20250726.joblib'
        if os.path.exists(pickle_path):
            tester.test_saved_pickle_model(pickle_path)
            # Also test production-like features
            tester.test_production_like_features(pickle_path)
        else:
            print(f"Error: Pickle file not found: {pickle_path}")
        return
    
    # Otherwise run full test suite
    # Generate sample data
    df = tester.generate_sample_data(n_samples=2000)
    
    # Save sample data for inspection
    df.to_csv('test_data/sample_transactions.csv', index=False)
    print(f"\nSample data saved to test_data/sample_transactions.csv")
    
    # Test feature engineering
    tester.test_feature_engineering(df)
    
    # Test model training
    model = tester.test_model_training(df)
    
    # Test predictions
    tester.test_predictions(model, df)
    
    # Generate report
    tester.generate_report(df)
    
    # Demo real-time prediction
    print("\n=== Real-time Prediction Demo ===")
    demo_transactions = pd.DataFrame([
        {'vendor_cleaned': 'amazon', 'amount': 49.99, 'account': 'Credit Card', 'template_used': 'CREDIT_CARD_TEMPLATE'},
        {'vendor_cleaned': 'starbucks', 'amount': 5.75, 'account': 'Checking', 'template_used': 'BANK_TEMPLATE_A'},
        {'vendor_cleaned': 'uber', 'amount': 23.50, 'account': 'Credit Card', 'template_used': 'CREDIT_CARD_TEMPLATE'}
    ])
    
    demo_predictions = model.predict(demo_transactions)
    for i, (_, row) in enumerate(demo_transactions.iterrows()):
        print(f"\n{row['vendor_cleaned'].upper()} - ${row['amount']:.2f}")
        print(f"Predicted: {demo_predictions[i]}")
    
    print("\n=== Testing Complete ===")
    print("\nNext steps:")
    print("1. Review the sample data in test_data/sample_transactions.csv")
    print("2. If results look good, proceed with GCP deployment")
    print("3. Use 'python scripts/test_ml_integration.py' to test with real GCP services")
    print("\nTo test a saved pickle model:")
    print("  python scripts/test_trained_models_locally.py --test-pickle ml_models/transaction_model_v20250726.joblib")


if __name__ == "__main__":
    # Create test data directory
    os.makedirs('test_data', exist_ok=True)
    main() 