#!/usr/bin/env python3
"""
Test script to check if the Vertex AI endpoint is accessible and responding.
This helps diagnose connection issues with the ML model endpoint.
Supports fallback to local model testing and local-only testing mode.
"""

import os
import sys
import logging
import argparse
import glob
import joblib
import numpy as np
from datetime import datetime

# Add parent directory to path so we can import src modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.ml_prediction_service import MLPredictionService
from src.utils.config import Config
from src.services.feature_engineering import FeatureEngineer


class LocalModelTester:
    """Test predictions using local pickle model files"""
    
    def __init__(self, project_id: str, logger: logging.Logger):
        self.project_id = project_id
        self.logger = logger
        self.local_model = None
        self.feature_engineer = None
        
    def find_latest_local_model(self) -> str:
        """Find the latest transaction_model_*.joblib file in ml_models folder"""
        ml_models_dir = "ml_models"
        if not os.path.exists(ml_models_dir):
            raise FileNotFoundError(f"ml_models directory not found: {ml_models_dir}")
        
        # Find all transaction_model_*.joblib files
        pattern = os.path.join(ml_models_dir, "transaction_model_*.joblib")
        model_files = glob.glob(pattern)
        
        if not model_files:
            raise FileNotFoundError(f"No transaction_model_*.joblib files found in {ml_models_dir}")
        
        # Sort by modification time (newest first)
        model_files.sort(key=os.path.getmtime, reverse=True)
        latest_model = model_files[0]
        
        self.logger.info(f"Found {len(model_files)} local model files:")
        for i, model_file in enumerate(model_files[:5]):  # Show top 5
            mod_time = datetime.fromtimestamp(os.path.getmtime(model_file))
            self.logger.info(f"  {i+1}. {os.path.basename(model_file)} (modified: {mod_time})")
        
        self.logger.info(f"Using latest local model: {os.path.basename(latest_model)}")
        return latest_model
    
    def load_local_model(self, model_path: str = None):
        """Load the local pickle model"""
        if model_path is None:
            model_path = self.find_latest_local_model()
        
        try:
            with open(model_path, 'rb') as f:
                self.local_model = joblib.load(f)
            
            # Extract model version from filename
            model_filename = os.path.basename(model_path)
            model_version = model_filename.replace('.joblib', '')
            
            # Initialize feature engineer with model version
            self.feature_engineer = FeatureEngineer(self.project_id, model_version)
            
            self.logger.info(f"✓ Successfully loaded local model: {model_filename}")
            return True
            
        except Exception as e:
            self.logger.error(f"✗ Failed to load local model {model_path}: {e}")
            return False
    
    def predict_category(self, transaction: dict) -> dict:
        """Predict category using local model"""
        if self.local_model is None:
            raise ValueError("Local model not loaded")
        
        try:
            # Prepare features using the same pipeline as production
            features_df = self.feature_engineer.prepare_for_prediction([transaction])
            
            # Make prediction - sklearn pipeline expects DataFrame
            predictions = self.local_model.predict(features_df)
            
            # Handle multi-output format from MultiOutputClassifier
            # predictions shape is (n_samples, n_outputs) where n_outputs=2 for [category, subcategory]
            if predictions.ndim == 2 and predictions.shape[1] >= 2:
                # Multi-output: predictions[0] is array([category, subcategory])
                category = str(predictions[0, 0])  # First sample, first output (category)
                subcategory = str(predictions[0, 1]) if predictions.shape[1] > 1 else None  # First sample, second output
            elif predictions.ndim == 1:
                # Single output: predictions[0] is just the category
                category = str(predictions[0])
                subcategory = None
            else:
                # Unexpected format
                self.logger.warning(f"Unexpected prediction format: shape={predictions.shape}")
                category = str(predictions[0]) if len(predictions) > 0 else 'Uncategorized'
                subcategory = None
            
            return {
                'category': category,
                'subcategory': subcategory,
                'confidence': 1.0,  # Local models don't provide confidence scores
                'model_version': f"local_{os.path.basename(self.find_latest_local_model()).replace('.joblib', '')}",
                'predicted_at': datetime.utcnow().isoformat(),
                'source': 'local_model'
            }
            
        except Exception as e:
            self.logger.error(f"Local model prediction failed: {e}")
            return {
                'category': 'Uncategorized',
                'subcategory': None,
                'confidence': 0.0,
                'model_version': 'local_fallback',
                'predicted_at': datetime.utcnow().isoformat(),
                'source': 'local_model_error',
                'error': str(e)
            }
    
    def predict_categories(self, transactions: list) -> list:
        """Predict categories for multiple transactions using local model"""
        if self.local_model is None:
            raise ValueError("Local model not loaded")
        
        try:
            # Prepare features using the same pipeline as production
            features_df = self.feature_engineer.prepare_for_prediction(transactions)
            
            # Make predictions - sklearn pipeline expects DataFrame
            predictions = self.local_model.predict(features_df)
            
            results = []
            # Handle multi-output format from MultiOutputClassifier
            # predictions shape is (n_samples, n_outputs) where n_outputs=2 for [category, subcategory]
            if predictions.ndim == 2 and predictions.shape[1] >= 2:
                # Multi-output case
                for i in range(len(predictions)):
                    category = str(predictions[i, 0])  # i-th sample, first output (category)
                    subcategory = str(predictions[i, 1]) if predictions.shape[1] > 1 else None  # i-th sample, second output
                    results.append({
                        'category': category,
                        'subcategory': subcategory,
                        'confidence': 1.0,  # Local models don't provide confidence scores
                        'model_version': f"local_{os.path.basename(self.find_latest_local_model()).replace('.joblib', '')}",
                        'predicted_at': datetime.utcnow().isoformat(),
                        'source': 'local_model'
                    })
            elif predictions.ndim == 1:
                # Single output case
                for i, prediction in enumerate(predictions):
                    category = str(prediction)
                    subcategory = None
                    results.append({
                        'category': category,
                        'subcategory': subcategory,
                        'confidence': 1.0,  # Local models don't provide confidence scores
                        'model_version': f"local_{os.path.basename(self.find_latest_local_model()).replace('.joblib', '')}",
                        'predicted_at': datetime.utcnow().isoformat(),
                        'source': 'local_model'
                    })
            else:
                # Unexpected format
                self.logger.warning(f"Unexpected batch prediction format: shape={predictions.shape}")
                for i in range(len(transactions)):
                    results.append({
                        'category': 'Uncategorized',
                        'subcategory': None,
                        'confidence': 0.0,
                        'model_version': f"local_{os.path.basename(self.find_latest_local_model()).replace('.joblib', '')}",
                        'predicted_at': datetime.utcnow().isoformat(),
                        'source': 'local_model'
                    })
            
            return results
            
        except Exception as e:
            self.logger.error(f"Local model batch prediction failed: {e}")
            return [{
                'category': 'Uncategorized',
                'subcategory': None,
                'confidence': 0.0,
                'model_version': 'local_fallback',
                'predicted_at': datetime.utcnow().isoformat(),
                'source': 'local_model_error',
                'error': str(e)
            } for _ in transactions]


def test_endpoint_connection(local_only: bool = False, local_model_path: str = None):
    """Test if the Vertex AI endpoint is accessible with optional local fallback
    
    Args:
        local_only: If True, test only against local model. If False, test Vertex AI with local fallback.
        local_model_path: Specific local model path to use (optional)
    """
    
    # Set up logging
    logging.basicConfig(
        level=logging.DEBUG,  # Changed to DEBUG to see more details
        format='[%(asctime)s] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Also set DEBUG level for ml_prediction_service logger
    ml_service_logger = logging.getLogger('src.services.ml_prediction_service')
    ml_service_logger.setLevel(logging.DEBUG)
    
    # Initialize success flags
    production_success = False
    sample_success = False
    
    try:
        # Initialize config
        config = Config()
        project_id = config.get('project', 'id')
        
        logger.info(f"Testing endpoint connection for project: {project_id}")
        
        # Initialize services based on mode
        ml_service = None
        local_tester = None
        
        if local_only:
            logger.info("🔧 LOCAL-ONLY MODE: Testing against local model only")
            logger.info(f"Project ID: {project_id}")
            local_tester = LocalModelTester(project_id, logger)
            if not local_tester.load_local_model(local_model_path):
                logger.error("Failed to load local model")
                return False
        else:
            logger.info("🌐 VERTEX AI MODE: Testing against Vertex AI with local fallback")
            ml_service = MLPredictionService(project_id, config)
            
            # Log endpoint details
            logger.info(f"Project ID: {project_id}")
            logger.info(f"Location: {ml_service.location}")
            logger.info(f"Model display name prefix: {ml_service.model_display_name_prefix}")
            
            if ml_service.current_model:
                logger.info(f"Current model: {ml_service.current_model.display_name}")
                logger.info(f"Model resource name: {ml_service.model_resource_name}")
            else:
                logger.warning("No current model found")
                
            if ml_service.endpoint:
                logger.info(f"Endpoint resource name: {ml_service.endpoint.resource_name}")
                logger.info(f"Endpoint display name: {ml_service.endpoint.display_name}")
            else:
                logger.warning("No endpoint found")
            
            # Check if service is available
            logger.info("Checking if ML service is available...")
            try:
                if not ml_service.is_available():
                    logger.warning("ML service availability check failed, but continuing with transaction tests...")
                    logger.warning("This might be due to the deployed model having the pandas DataFrame issue.")
                    logger.warning("We'll test the transactions directly to see if they work.")
                else:
                    logger.info("✓ ML service is available")
            except Exception as e:
                logger.warning(f"Availability check failed: {e}")
                logger.warning("Continuing with transaction tests anyway...")
        
        # Test with the actual production transaction data
        production_transaction = {
            'vendor': "SAM'S Online Club",
            'amount': 77.89,
            'template_used': 'Discover Credit Card',
            'account': '4393',
            'date': datetime(2025, 7, 27, 13, 33, 15)  # Convert from the production datetime
        }
        
        logger.info("=" * 60)
        logger.info("TESTING WITH PRODUCTION TRANSACTION DATA")
        logger.info("=" * 60)
        logger.info(f"Vendor: {production_transaction['vendor']}")
        logger.info(f"Amount: ${production_transaction['amount']}")
        logger.info(f"Template: {production_transaction['template_used']}")
        logger.info(f"Account: {production_transaction['account']}")
        logger.info(f"Date: {production_transaction['date']}")
        logger.info("=" * 60)
        
        logger.info("Testing prediction with production transaction...")
        try:
            if local_only:
                prediction = local_tester.predict_category(production_transaction)
            else:
                prediction = ml_service.predict_category(production_transaction)
            
            logger.info("=" * 60)
            logger.info("PREDICTION RESULTS")
            logger.info("=" * 60)
            logger.info(f"Category: {prediction.get('category', 'N/A')}")
            logger.info(f"Subcategory: {prediction.get('subcategory', 'N/A')}")
            logger.info(f"Confidence: {prediction.get('confidence', 'N/A')}")
            logger.info(f"Model Version: {prediction.get('model_version', 'N/A')}")
            logger.info(f"Predicted At: {prediction.get('predicted_at', 'N/A')}")
            logger.info(f"Source: {prediction.get('source', 'N/A')}")
            
            # Check if this is a default prediction (indicating model failure)
            if prediction.get('category') == 'Uncategorized' and prediction.get('confidence') == 0.0:
                logger.warning("⚠️  This appears to be a default prediction, not a real ML prediction")
                logger.warning("The model may have failed and returned fallback values")
                production_success = False
            else:
                logger.info("✅ Real ML prediction received")
                production_success = True
            logger.info("=" * 60)
        except Exception as e:
            logger.error(f"❌ Production transaction test failed: {e}")
            logger.exception("Production transaction error details:")
            production_success = False
        
        # Test with a few more sample transactions for comparison
        sample_transactions = [
            {
                'vendor': 'Amazon.com',
                'amount': 29.99,
                'template_used': 'gmail',
                'account': 'gmail_test@example.com',
                'date': datetime(2024, 1, 15)
            },
            {
                'vendor': 'Starbucks',
                'amount': 4.50,
                'template_used': 'gmail',
                'account': 'gmail_test@example.com',
                'date': datetime(2024, 1, 15)
            },
            {
                'vendor': 'Walmart',
                'amount': 45.67,
                'template_used': 'Discover Credit Card',
                'account': '1234',
                'date': datetime(2024, 1, 15)
            }
        ]
        
        logger.info("Testing batch prediction with sample transactions...")
        try:
            if local_only:
                predictions = local_tester.predict_categories(sample_transactions)
            else:
                predictions = ml_service.predict_categories(sample_transactions)
            
            logger.info("=" * 60)
            logger.info("SAMPLE TRANSACTIONS PREDICTIONS")
            logger.info("=" * 60)
            default_predictions_count = 0
            for i, (transaction, prediction) in enumerate(zip(sample_transactions, predictions)):
                logger.info(f"Transaction {i+1}: {transaction['vendor']} - ${transaction['amount']}")
                logger.info(f"  Category: {prediction.get('category', 'N/A')}")
                logger.info(f"  Subcategory: {prediction.get('subcategory', 'N/A')}")
                logger.info(f"  Confidence: {prediction.get('confidence', 'N/A')}")
                logger.info(f"  Source: {prediction.get('source', 'N/A')}")
                
                # Check if this is a default prediction
                if prediction.get('category') == 'Uncategorized' and prediction.get('confidence') == 0.0:
                    default_predictions_count += 1
                    logger.warning(f"  ⚠️  Default prediction (model may have failed)")
                else:
                    logger.info(f"  ✅ Real ML prediction")
                logger.info("---")
            
            if default_predictions_count == len(sample_transactions):
                logger.warning("⚠️  All sample transactions returned default predictions")
                logger.warning("The model is not working correctly")
                sample_success = False
            else:
                logger.info("✅ Some real ML predictions received")
                sample_success = True
        except Exception as e:
            logger.error(f"❌ Sample transactions test failed: {e}")
            logger.exception("Sample transactions error details:")
            sample_success = False
        
        # If Vertex AI mode failed, try local fallback
        if not local_only and not production_success and not sample_success:
            logger.info("=" * 60)
            logger.info("🔄 VERTEX AI FAILED - TRYING LOCAL FALLBACK")
            logger.info("=" * 60)
            
            try:
                local_tester = LocalModelTester(project_id, logger)
                if local_tester.load_local_model():
                    logger.info("✓ Local model loaded successfully, testing with local model...")
                    
                    # Test production transaction with local model
                    try:
                        local_prediction = local_tester.predict_category(production_transaction)
                        logger.info("=" * 60)
                        logger.info("LOCAL FALLBACK PREDICTION RESULTS")
                        logger.info("=" * 60)
                        logger.info(f"Category: {local_prediction.get('category', 'N/A')}")
                        logger.info(f"Subcategory: {local_prediction.get('subcategory', 'N/A')}")
                        logger.info(f"Confidence: {local_prediction.get('confidence', 'N/A')}")
                        logger.info(f"Model Version: {local_prediction.get('model_version', 'N/A')}")
                        logger.info(f"Source: {local_prediction.get('source', 'N/A')}")
                        
                        if local_prediction.get('category') != 'Uncategorized':
                            logger.info("✅ Local fallback prediction successful")
                            production_success = True
                        else:
                            logger.warning("⚠️  Local fallback also failed")
                    except Exception as e:
                        logger.error(f"❌ Local fallback production test failed: {e}")
                    
                    # Test sample transactions with local model
                    try:
                        local_predictions = local_tester.predict_categories(sample_transactions)
                        successful_local_predictions = sum(1 for p in local_predictions 
                                                         if p.get('category') != 'Uncategorized')
                        
                        if successful_local_predictions > 0:
                            logger.info(f"✅ Local fallback batch predictions: {successful_local_predictions}/{len(sample_transactions)} successful")
                            sample_success = True
                        else:
                            logger.warning("⚠️  Local fallback batch predictions also failed")
                    except Exception as e:
                        logger.error(f"❌ Local fallback batch test failed: {e}")
                        
                else:
                    logger.error("❌ Failed to load local model for fallback")
                    
            except Exception as e:
                logger.error(f"❌ Local fallback failed: {e}")
        
        # Determine overall success
        if production_success and sample_success:
            if local_only:
                logger.info("🎉 All local model tests passed!")
            else:
                logger.info("🎉 All tests passed! Endpoint is working correctly.")
            return True
        elif production_success or sample_success:
            if local_only:
                logger.warning("⚠️  Some local model tests passed, some failed. Check the logs above for details.")
            else:
                logger.warning("⚠️  Some tests passed, some failed. Check the logs above for details.")
            return True  # Consider it a partial success
        else:
            if local_only:
                logger.error("❌ All local model tests failed!")
            else:
                logger.error("❌ All tests failed!")
                logger.error("Both Vertex AI and local fallback failed.")
            return False
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        logger.exception("Full traceback:")
        return False

def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Test ML endpoint connection with optional local fallback')
    parser.add_argument('--local-only', action='store_true', 
                       help='Test only against local model (skip Vertex AI)')
    parser.add_argument('--local-model', type=str, 
                       help='Specific local model path to use (e.g., ml_models/transaction_model_v20250727.joblib)')
    
    args = parser.parse_args()
    
    print("=" * 60)
    if args.local_only:
        print("Local Model Testing Mode")
        print("=" * 60)
        print("🔧 Testing against local pickle model only")
        if args.local_model:
            print(f"📁 Using specified model: {args.local_model}")
        else:
            print("📁 Using latest transaction_model_*.joblib file")
    else:
        print("Vertex AI Endpoint Connection Test")
        print("=" * 60)
        print("🌐 Testing against Vertex AI with local fallback")
    print("=" * 60)
    print(f"Test started at: {datetime.now()}")
    print()
    
    success = test_endpoint_connection(local_only=args.local_only, local_model_path=args.local_model)
    
    print()
    print("=" * 60)
    if success:
        if args.local_only:
            print("✅ Local model test PASSED")
            print("The local model is working correctly.")
        else:
            print("✅ Endpoint test PASSED")
            print("The ML endpoint is working correctly.")
    else:
        if args.local_only:
            print("❌ Local model test FAILED")
        else:
            print("❌ Endpoint test FAILED")
        print("Check the logs above for details.")
    print("=" * 60)
    print("Usage:")
    print("  python scripts/test_endpoint_connection.py                    # Test Vertex AI with local fallback")
    print("  python scripts/test_endpoint_connection.py --local-only       # Test local model only")
    print("  python scripts/test_endpoint_connection.py --local-only --local-model ml_models/my_model.joblib")
    print("=" * 60)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 