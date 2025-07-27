#!/bin/bash
echo "=== Testing ML Deployment Script ==="
echo

# Test creating ML function packages locally
echo "Testing ML function packaging..."
python scripts/deploy_ml_functions.py --prepare-only

if [ $? -eq 0 ]; then
    echo
    echo "SUCCESS: ML function packages created successfully!"
    echo
    echo "Check the temp/ directory for:"
    echo "  - data-export-function.zip"
    echo "  - model-retraining-function.zip"
    echo "  - model-performance-checker.zip"
else
    echo
    echo "FAILED: ML function packaging encountered errors"
    echo "Please check the error messages above"
fi 