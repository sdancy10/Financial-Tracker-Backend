#!/usr/bin/env python3
"""Verify model structure and test predictions locally before deployment"""

import os
import sys
import joblib
import numpy as np
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.services.feature_engineering import FeatureEngineer
from src.utils.config import Config


def verify_model_structure(model_path):
    """Verify the structure of a saved model"""
    print(f"\n=== Verifying Model Structure: {model_path} ===")
    
    try:
        # Load the model
        model = joblib.load(model_path)
        print(f"✓ Model loaded successfully")
        
        # Check if it's a Pipeline
        print(f"\nModel type: {type(model)}")
        
        if hasattr(model, 'steps'):
            print(f"Pipeline steps: {len(model.steps)}")
            for i, (name, step) in enumerate(model.steps):
                print(f"  Step {i}: {name} -> {type(step)}")
                
                # Check for custom transformers
                if hasattr(step, '__module__'):
                    print(f"    Module: {step.__module__}")
                    
                # Special check for DenseTransformer
                if 'DenseTransformer' in str(type(step)):
                    print(f"    ⚠️  Custom DenseTransformer detected")
                    print(f"    Has fit method: {hasattr(step, 'fit')}")
                    print(f"    Has transform method: {hasattr(step, 'transform')}")
        
        # Test prediction with dummy data
        print(f"\n=== Testing Model Prediction ===")
        
        # Create dummy input matching expected format
        # 9 text features + 9 vendor features = 18 total features
        dummy_input = [
            ['sams online', 'sams online', 'SMSN', 'Discover', '4393', '27', '7', '2025', 'Sunday',  # text features
             0, 0, 0, 0, 0, 0, 0, 0, 0]  # vendor features (all zeros)
        ]
        
        print(f"Input shape: {np.array(dummy_input).shape}")
        print(f"Input data: {dummy_input}")
        
        try:
            # Direct prediction
            predictions = model.predict(dummy_input)
            print(f"✓ Direct prediction successful!")
            print(f"  Predictions shape: {predictions.shape}")
            print(f"  Predictions: {predictions}")
        except Exception as e:
            print(f"✗ Direct prediction failed: {e}")
            print(f"  Error type: {type(e).__name__}")
            
            # Try to trace through pipeline steps
            if hasattr(model, 'steps'):
                print(f"\n  Tracing through pipeline steps:")
                current_data = dummy_input
                for i, (name, step) in enumerate(model.steps):
                    print(f"\n  Step {i}: {name}")
                    try:
                        if hasattr(step, 'transform'):
                            current_data = step.transform(current_data)
                            print(f"    ✓ Transform successful, output type: {type(current_data)}")
                            if hasattr(current_data, 'shape'):
                                print(f"    Output shape: {current_data.shape}")
                        elif hasattr(step, 'predict'):
                            current_data = step.predict(current_data)
                            print(f"    ✓ Predict successful, output type: {type(current_data)}")
                            if hasattr(current_data, 'shape'):
                                print(f"    Output shape: {current_data.shape}")
                    except Exception as step_e:
                        print(f"    ✗ Failed: {step_e}")
                        break
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to verify model: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_with_feature_engineering(model_path):
    """Test model with proper feature engineering"""
    print(f"\n=== Testing Model with Feature Engineering ===")
    
    try:
        # Initialize config and feature engineer
        config = Config()
        project_id = config.get('project', 'id')
        
        # Load model to get version
        model = joblib.load(model_path)
        model_version = os.path.basename(model_path).replace('.joblib', '')
        
        # Initialize feature engineer
        feature_engineer = FeatureEngineer(project_id, model_version)
        
        # Test transaction
        test_transaction = {
            'vendor': "SAM'S Online Club",
            'amount': 77.89,
            'template_used': 'Discover Credit Card',
            'account': '4393',
            'date': datetime(2025, 7, 27, 13, 33, 15)
        }
        
        print(f"\nTest transaction: {test_transaction}")
        
        # Prepare features
        features = feature_engineer.prepare_for_prediction([test_transaction])
        print(f"\nPrepared features shape: {features.shape}")
        print(f"Feature columns: {list(features.columns)}")
        
        # Convert to list format for Vertex AI
        instances = features.values.tolist()
        print(f"\nInstances format (for Vertex AI): {instances}")
        
        # Test prediction
        predictions = model.predict(instances)
        print(f"\n✓ Prediction successful!")
        print(f"  Predictions: {predictions}")
        
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    import argparse
    parser = argparse.ArgumentParser(description='Verify model structure')
    parser.add_argument('--model', type=str, 
                       default='ml_models/transaction_model_v20250727.joblib',
                       help='Path to model file')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Model Structure Verification")
    print("=" * 60)
    
    if not os.path.exists(args.model):
        print(f"❌ Model file not found: {args.model}")
        return 1
    
    # Verify model structure
    structure_ok = verify_model_structure(args.model)
    
    # Test with feature engineering
    feature_ok = test_with_feature_engineering(args.model)
    
    print("\n" + "=" * 60)
    if structure_ok and feature_ok:
        print("✅ Model verification PASSED")
        print("The model structure is valid and predictions work locally.")
    else:
        print("❌ Model verification FAILED")
        print("There are issues with the model that need to be fixed.")
    print("=" * 60)
    
    return 0 if (structure_ok and feature_ok) else 1


if __name__ == "__main__":
    sys.exit(main()) 