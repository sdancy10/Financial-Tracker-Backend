#!/bin/bash

echo "================================"
echo "ML Model Training with 2024 Data"
echo "================================"
echo
echo "This will train the model using data from:"
echo "- User: 5oZfUgtSn0g1VaEa6VNpHVC51Zq2"
echo "- User: aDer8RS94NPmPdAYGHQQpI3iWm13"
echo "- Date: 2024-01-01 onwards"
echo

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Ask user if they want to prepare data or use existing
echo "Do you want to:"
echo "1. Use existing parquet data (train only)"
echo "2. Prepare fresh data and train"
echo
read -p "Enter your choice (1 or 2): " choice

if [ "$choice" = "1" ]; then
    echo
    echo "Training model with existing parquet data..."
    python scripts/ml_training_workflow.py \
        --project-id shanedancy-9f2a3 \
        --train-only
else
    echo
    echo "Preparing fresh data and training model..."
    python scripts/ml_training_workflow.py \
        --project-id shanedancy-9f2a3 \
        --source firestore \
        --user-ids 5oZfUgtSn0g1VaEa6VNpHVC51Zq2 aDer8RS94NPmPdAYGHQQpI3iWm13 \
        --start-date 2024-01-01
fi

echo
echo "================================"
echo "Training complete!"
echo "================================" 