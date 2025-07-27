#!/bin/bash

echo "================================"
echo "Preparing ML Training Data"
echo "================================"
echo
echo "Loading transactions for users:"
echo "- 5oZfUgtSn0g1VaEa6VNpHVC51Zq2"
echo "- aDer8RS94NPmPdAYGHQQpI3iWm13"
echo
echo "Filter: Transactions from 2024-01-01 onwards"
echo

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi

# Run the data preparation script with specific parameters
python scripts/prepare_ml_training_data.py \
    --project-id shanedancy-9f2a3 \
    --source firestore \
    --user-ids 5oZfUgtSn0g1VaEa6VNpHVC51Zq2 aDer8RS94NPmPdAYGHQQpI3iWm13 \
    --start-date 2024-01-01

echo
echo "================================"
echo "Data preparation complete!"
echo "================================" 