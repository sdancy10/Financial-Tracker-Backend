#!/bin/bash

# Exit on any error
set -e

# Get the current directory
CURRENT_DIR=$(pwd)
echo "Current directory is: $CURRENT_DIR"

# Set PYTHONPATH to include current directory
export PYTHONPATH="$CURRENT_DIR:$PYTHONPATH"
echo "Set PYTHONPATH to include current directory: $PYTHONPATH"

# Set test environment variable (to match setup.bat)
export TEST_ENV=true

# Check for virtual environment
if [ -f "venv/bin/activate" ]; then
    echo "Found existing virtual environment"
else
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip silently
python -m pip install --upgrade pip --quiet

# Install requirements
echo "Installing requirements..."
python -m pip install -r requirements.txt --quiet --no-warn-script-location
if [ $? -ne 0 ]; then
    echo "Error: Failed to install requirements"
    python -m pip install -r requirements.txt  # Run again with full output for debugging
    exit 1
fi

# Run pre-deployment tests if enabled in config
echo
echo "Checking test configuration..."

# Read test configuration
eval "$(python3 -c "
import yaml
import json

config = yaml.safe_load(open('config.yaml'))
test_config = config.get('testing', {})
components = test_config.get('components', {})
test_paths = test_config.get('test_paths', {})
test_order = test_config.get('test_order', ['unit_tests', 'package_tests', 'config_tests', 'integration_tests'])

run_tests = '1' if test_config.get('run_after_deployment', False) else '0'
run_all = '1' if test_config.get('run_all_tests', False) else '0'

print(f'RUN_TESTS={run_tests}')
print(f'RUN_ALL={run_all}')
print(f'TEST_ORDER={json.dumps(test_order)}')

for test_type in test_order:
    enabled = '1' if components.get(test_type, True) else '0'
    print(f'{test_type.upper()}_ENABLED={enabled}')
    paths = test_paths.get(test_type, [])
    if paths:
        print(f'{test_type.upper()}_PATHS={json.dumps(paths)}')
")"

if [ "$RUN_TESTS" = "1" ]; then
    echo "=== Running Pre-deployment Tests ==="
    echo
    
    STEP=1
    
    # Execute tests in order
    for TEST_TYPE in $(echo "$TEST_ORDER" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
        ENABLED_VAR="${TEST_TYPE^^}_ENABLED"
        PATHS_VAR="${TEST_TYPE^^}_PATHS"
        
        if [ "${!ENABLED_VAR}" = "1" ]; then
            echo
            echo "Step $STEP: Running $TEST_TYPE tests..."
            
            case "$TEST_TYPE" in
                "unit_tests")
                    if [ "$RUN_ALL" = "1" ]; then
                        python -m pytest tests -v
                        if [ $? -ne 0 ]; then
                            echo "Error: Unit tests failed"
                            exit 1
                        fi
                    else
                        for TEST_PATH in $(echo "${!PATHS_VAR}" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
                            echo "Running tests in: $TEST_PATH"
                            python -m pytest "$TEST_PATH" -v
                            if [ $? -ne 0 ]; then
                                echo "Error: Unit tests failed in $TEST_PATH"
                                exit 1
                            fi
                        done
                    fi
                    ;;
                    
                "package_tests")
                    for TEST_PATH in $(echo "${!PATHS_VAR}" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
                        python "$TEST_PATH"
                        if [ $? -ne 0 ]; then
                            echo "Error: Package tests failed"
                            exit 1
                        fi
                    done
                    ;;
                    
                "config_tests")
                    for TEST_PATH in $(echo "${!PATHS_VAR}" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
                        python "$TEST_PATH"
                        if [ $? -ne 0 ]; then
                            echo "Error: Configuration tests failed"
                            exit 1
                        fi
                    done
                    ;;
                    
                "integration_tests")
                    # Integration tests are run after deployment
                    echo "Integration tests will run after deployment"
                    ;;
            esac
        else
            echo "Skipping $TEST_TYPE (disabled in config)"
        fi
        
        STEP=$((STEP + 1))
    done
    
    echo
    echo "=== All Pre-deployment Tests Passed ==="
    echo
else
    echo "Skipping tests (disabled in config.yaml)"
    echo
fi

echo "=== Starting Deployment ==="
echo

# Deploy storage buckets
echo "Step 1: Deploying storage buckets..."
python scripts/deploy_storage.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy storage buckets"
    exit 1
fi

# Set up service accounts
echo "Step 2: Setting up service accounts..."
python scripts/setup_service_accounts.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to set up service accounts"
    exit 1
fi

# Deploy credentials
echo "Step 3: Deploying credentials..."
python scripts/deploy_credentials.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy credentials"
    exit 1
fi

# Wait for a moment to ensure all resources are ready
echo
WAIT_TIME=$(python3 -c "
import yaml
config = yaml.safe_load(open('config.yaml'))
print(config.get('testing', {}).get('wait_time', 5))
")

echo "Waiting for $WAIT_TIME seconds to ensure all resources are ready..."
sleep "$WAIT_TIME"

# Deploy Cloud Function and Scheduler
echo "Step 4: Deploying Cloud Function and Scheduler..."
python scripts/deploy_functions.py
if [ $? -ne 0 ]; then
    echo "Error: Failed to deploy Cloud Function and Scheduler"
    exit 1
fi

# Run post-deployment integration tests if enabled
if [ "$RUN_TESTS" = "1" ] && [ "$INTEGRATION_TESTS_ENABLED" = "1" ]; then
    echo
    echo "Step 5: Running post-deployment tests..."
    for TEST_PATH in $(echo "$INTEGRATION_TESTS_PATHS" | python3 -c "import json,sys; print(' '.join(json.loads(sys.stdin.read())))"); do
        python "$TEST_PATH"
        if [ $? -ne 0 ]; then
            echo "Warning: Post-deployment test failed"
            echo "Please check the logs above for details"
            exit 1
        fi
    done
fi

echo
echo "=== Deployment Completed Successfully ==="
exit 0