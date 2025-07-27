#!/bin/bash
echo "=== Running ML Tests Locally (No GCP Required) ==="
echo

# Set environment variable to indicate local testing mode
export LOCAL_ML_TEST=1
export GOOGLE_AUTH_SUPPRESS_CREDENTIALS_WARNINGS=1

# Check if virtual environment exists
if [ -d "venv" ]; then
    echo "Activating virtual environment..."
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
fi

# Install required packages
echo "Installing required packages..."
pip install pandas scikit-learn numpy matplotlib seaborn --quiet

# Run the local ML test
echo
echo "Running ML tests with synthetic data..."
python scripts/test_trained_models_locally.py

echo
echo "=== ML Test Complete ==="
echo
echo "Test data saved to: test_data/sample_transactions.csv"
echo 