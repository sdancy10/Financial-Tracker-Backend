@echo off
echo === Running ML Tests Locally (No GCP Required) ===
echo.

REM Set environment variable to indicate local testing mode
set "LOCAL_ML_TEST=1"
set "GOOGLE_AUTH_SUPPRESS_CREDENTIALS_WARNINGS=1"

REM Check if virtual environment exists
if exist venv (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
)

REM Install required packages
echo Installing required packages...
pip install pandas scikit-learn numpy matplotlib seaborn --quiet

REM Run the local ML test
echo.
echo Running ML tests with synthetic data...
python scripts\test_trained_models_locally.py

echo.
echo === ML Test Complete ===
echo.
echo Test data saved to: test_data\sample_transactions.csv
echo.
pause 