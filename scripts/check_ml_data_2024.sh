#!/bin/bash

echo "================================"
echo "Checking ML Data Quality"
echo "================================"
echo

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Check data quality
python scripts/check_ml_data_quality.py --project-id shanedancy-9f2a3

echo
echo "================================"
echo "Data quality check complete!"
echo "================================" 