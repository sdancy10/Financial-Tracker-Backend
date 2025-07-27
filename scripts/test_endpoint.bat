@echo off
echo Testing ML Endpoint Connection with Local Fallback...
echo.

REM Prompt user for testing mode
echo Choose testing mode:
echo 1. Vertex AI with local fallback (default)
echo 2. Local model only
echo 3. Specific local model
echo.
set /p choice="Enter your choice (1-3) [default=1]: "

REM Set default choice if user just presses Enter
if "%choice%"=="" set choice=1

REM Execute based on user choice
if "%choice%"=="1" (
    echo.
    echo 🌐 Testing Vertex AI with local fallback...
    python scripts/test_endpoint_connection.py
) else if "%choice%"=="2" (
    echo.
    echo 🔧 Testing local model only...
    python scripts/test_endpoint_connection.py --local-only
) else if "%choice%"=="3" (
    echo.
    set /p model_path="Enter local model path (e.g., ml_models/transaction_model_v20250727.joblib): "
    if "%model_path%"=="" (
        echo ❌ No model path provided. Using default local model...
        python scripts/test_endpoint_connection.py --local-only
    ) else (
        echo 🔧 Testing specified local model: %model_path%
        python scripts/test_endpoint_connection.py --local-only --local-model "%model_path%"
    )
) else (
    echo ❌ Invalid choice. Using default mode...
    echo.
    echo 🌐 Testing Vertex AI with local fallback...
    python scripts/test_endpoint_connection.py
)

if errorlevel 1 (
    echo.
    echo ❌ Test failed!
    echo.
    echo Possible solutions:
    echo 1. Check if the model is deployed: python scripts/ml_training_workflow.py --check-model
    echo 2. Redeploy the model: python scripts/ml_training_workflow.py --model-name transaction_model_v20250727
    echo 3. Check Vertex AI console for endpoint status
    echo 4. Verify network connectivity and IAM permissions
    echo 5. Run this script again and choose option 2 (Local model only)
    echo 6. Run this script again and choose option 3 (Specific local model)
    echo.
    pause
) else (
    echo.
    echo ✅ Test passed!
    echo The ML endpoint/model is working correctly.
    echo.
    pause
) 