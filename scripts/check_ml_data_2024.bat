@echo off
echo ================================
echo Checking ML Data Quality
echo ================================
echo.

REM Activate virtual environment if it exists
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

REM Check data quality
python scripts/check_ml_data_quality.py --project-id shanedancy-9f2a3

echo.
echo ================================
echo Data quality check complete!
echo ================================
pause 