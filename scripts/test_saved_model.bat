@echo off
echo ================================
echo Testing Saved ML Model
echo ================================
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Default model path
set MODEL_PATH=ml_models/transaction_model_v20250726.joblib

REM Check if custom path provided
if not "%1"=="" (
    set MODEL_PATH=%1
)

echo Testing model: %MODEL_PATH%
echo.

python scripts/test_trained_models_locally.py --test-pickle "%MODEL_PATH%"

echo.
pause 