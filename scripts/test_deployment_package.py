import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path
from deploy_functions import FunctionDeployer

class DeploymentPackageTester:
    def __init__(self):
        self.temp_dir = os.path.join(os.getcwd(), "temp_test")
        self.venv_dir = os.path.join(self.temp_dir, "venv")
        self.deployer = FunctionDeployer()

    def create_test_environment(self):
        """Create a test environment with necessary files"""
        print("\n=== Creating Test Environment ===\n")
        
        # Create temp directory
        os.makedirs(self.temp_dir, exist_ok=True)
        
        # Get exclusion patterns from deployer
        exclusion_patterns = self.deployer.get_exclusion_patterns()
        
        print("\nExclusion patterns:")
        for pattern in sorted(exclusion_patterns):
            print(f"  - {pattern}")
        
        print("\nCopying files...")
        
        # Process Python files
        for root, _, files in os.walk("src"):
            for file in files:
                if file.endswith('.py'):
                    src_path = os.path.join(root, file)
                    if self.deployer.should_include(src_path, exclusion_patterns):
                        dest_name = self.deployer.get_flattened_name(src_path)
                        dest_path = os.path.join(self.temp_dir, dest_name)
                        if self.deployer.copy_with_imports(src_path, dest_path):
                            print(f"[OK] Copied and updated {src_path} to {dest_name}")
        
        # Copy special files that aren't Python files
        special_files = self.deployer.get_special_files()
        for src, dest in special_files.items():
            if not src.endswith('.py') and os.path.exists(src):
                dest_path = os.path.join(self.temp_dir, dest)
                if self.deployer.copy_with_imports(src, dest_path):
                    print(f"[OK] Copied {dest}")
        
        # Create an __init__.py in the temp directory
        init_path = os.path.join(self.temp_dir, "__init__.py")
        with open(init_path, "w", encoding='utf-8') as f:
            f.write("# Package initialization")
        print("[OK] Created __init__.py")

    def test_imports(self):
        """Test importing the required modules"""
        print("\n=== Testing Imports ===\n")
        
        # Create virtual environment
        venv.create(self.venv_dir, with_pip=True)
        
        # Get python executable path
        if os.name == 'nt':  # Windows
            python_path = os.path.join(self.venv_dir, "Scripts", "python.exe")
        else:  # Unix/Linux
            python_path = os.path.join(self.venv_dir, "bin", "python")
            
        # Install requirements with suppressed output
        print("Installing requirements...")
        try:
            subprocess.check_call(
                [python_path, "-m", "pip", "install", "-r", os.path.join(self.temp_dir, "requirements.txt")],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE
            )
        except subprocess.CalledProcessError as e:
            print(f"Error installing requirements: {e.stderr.decode()}")
            return False
        
        # Create test script
        test_script = os.path.join(self.temp_dir, "test_imports.py")
        with open(test_script, "w", encoding='utf-8') as f:
            f.write("""
import sys
import os

# Add the temp directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try importing required modules
try:
    from services_transaction_service import TransactionService
    from main import process_transactions
    print("[OK] Successfully imported TransactionService")
    print("[OK] Successfully imported process_transactions")
    print("[OK] All imports successful!")
except ImportError as e:
    print(f"[ERROR] During import testing: {str(e)}")
    sys.exit(1)
""")
        
        # Run test script
        try:
            subprocess.check_call([python_path, test_script])
            print("\n[OK] All tests passed!")
            return True
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] Deployment package tests failed!")
            return False

    def cleanup(self):
        """Clean up the test environment"""
        print("\n=== Cleaning Up ===")
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
            print("[OK] Test environment cleaned up")

def main():
    tester = DeploymentPackageTester()
    try:
        tester.create_test_environment()
        success = tester.test_imports()
        if not success:
            sys.exit(1)
    finally:
        tester.cleanup()

if __name__ == "__main__":
    main() 