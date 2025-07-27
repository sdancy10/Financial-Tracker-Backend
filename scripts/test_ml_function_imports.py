#!/usr/bin/env python3
"""
Test that ML function imports work correctly after deployment transformations
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

def test_import_transformation():
    """Test that imports work correctly after removing 'src.' prefix"""
    
    # Create a temporary directory to simulate Cloud Function environment
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Testing in temporary directory: {temp_dir}")
        
        # Copy essential files and transform imports
        files_to_copy = [
            ('src/services/model_retraining_function.py', 'main.py'),
            ('src/services/data_export_service.py', 'services/data_export_service.py'),
            ('src/services/feature_engineering.py', 'services/feature_engineering.py'),
            ('src/models/transaction_trainer.py', 'models/transaction_trainer.py'),
            ('src/utils/config.py', 'utils/config.py'),
            ('src/services/__init__.py', 'services/__init__.py'),
            ('src/models/__init__.py', 'models/__init__.py'),
            ('src/utils/__init__.py', 'utils/__init__.py'),
        ]
        
        for src, dst in files_to_copy:
            dst_path = os.path.join(temp_dir, dst)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            
            if os.path.exists(src):
                # Read and transform imports
                with open(src, 'r') as f:
                    content = f.read()
                
                # Remove 'src.' prefix from imports
                content = content.replace('from src.', 'from ')
                content = content.replace('import src.', 'import ')
                
                # Write transformed content
                with open(dst_path, 'w') as f:
                    f.write(content)
                
                print(f"✓ Copied and transformed: {src} -> {dst}")
            else:
                print(f"✗ File not found: {src}")
        
        # Try to import the main module
        print("\nTesting imports...")
        sys.path.insert(0, temp_dir)
        
        try:
            # Test importing main
            import main
            print("✓ Successfully imported main module")
            
            # Check if entry points exist
            if hasattr(main, 'trigger_model_retraining'):
                print("✓ Found trigger_model_retraining function")
            else:
                print("✗ trigger_model_retraining function not found")
                
            if hasattr(main, 'check_model_performance'):
                print("✓ Found check_model_performance function")
            else:
                print("✗ check_model_performance function not found")
                
        except ImportError as e:
            print(f"✗ Import error: {e}")
            return False
        finally:
            # Clean up sys.path
            sys.path.remove(temp_dir)
    
    return True

if __name__ == "__main__":
    print("=== Testing ML Function Import Transformations ===\n")
    
    # Change to project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)
    
    success = test_import_transformation()
    
    if success:
        print("\n✓ All import transformations successful!")
        print("\nNext steps:")
        print("1. Run: python scripts/deploy_ml_functions.py")
        print("2. Deploy with Terraform: terraform apply")
    else:
        print("\n✗ Import transformation test failed!")
        print("Fix the import issues before deploying.") 