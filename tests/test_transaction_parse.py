"""
Test transaction parsing functionality with mock messages.
"""

import unittest
import logging
import sys
from typing import Dict, Any
import os
from colorama import init, Fore, Style
import re
import codecs
# Add the project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(project_root)
from src.utils.transaction_parser import TransactionParser
from src.mock.api.mock_gmail_api import get_all_mock_messages, get_mock_message_by_template

# Initialize colorama for Windows support
init()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler with custom formatter
ch = logging.StreamHandler()
ch.stream = codecs.getwriter('utf-8')(sys.stdout.buffer)
ch.setLevel(logging.INFO)

# Create file handler with utf-8 encoding
fh = logging.FileHandler('template_test_log_results.log', mode='w', encoding='utf-8')
fh.setLevel(logging.INFO)

def sanitize_for_console(text):
    """Clean text for console output by removing problematic characters"""
    if text is None:
        return None
    # Remove zero-width characters and other invisible unicode
    text = re.sub(r'[\u200b-\u200f\u2028-\u202f\u205f-\u206f]', '', str(text))
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored output"""
    
    def format(self, record):
        # Sanitize only for console output
        if isinstance(record.msg, str):
            record.msg = sanitize_for_console(record.msg)
        
        if record.levelno == logging.INFO:
            record.msg = f"{Style.BRIGHT}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.ERROR:
            record.msg = f"{Fore.RED}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.WARNING:
            record.msg = f"{Fore.YELLOW}{record.msg}{Style.RESET_ALL}"
        elif record.levelno == logging.SUCCESS:
            record.msg = f"{Fore.GREEN}{record.msg}{Style.RESET_ALL}"
        return super().format(record)

class FileFormatter(logging.Formatter):
    """Plain text formatter for file output"""
    
    def format(self, record):
        # Don't sanitize for file output
        if record.levelno == logging.SUCCESS:
            record.levelname = 'SUCCESS'
        return super().format(record)

# Add custom logging level for success messages
logging.SUCCESS = 25  # Between INFO and WARNING
logging.addLevelName(logging.SUCCESS, 'SUCCESS')

def success(self, message, *args, **kwargs):
    if self.isEnabledFor(logging.SUCCESS):
        self._log(logging.SUCCESS, message, args, **kwargs)

logging.Logger.success = success

# Add formatters to handlers
console_formatter = ColoredFormatter('%(message)s')
file_formatter = FileFormatter('%(message)s')

ch.setFormatter(console_formatter)
fh.setFormatter(file_formatter)

logger.addHandler(ch)
logger.addHandler(fh)

class CustomTestResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_results = {}

    def startTest(self, test):
        super().startTest(test)
        # Log available templates only once at the start of each test
        if not hasattr(self, 'templates_logged'):
            logger.info("\nAvailable templates for testing:")
            mock_messages = get_all_mock_messages()
            for template in mock_messages.keys():
                logger.info(f"  - {template}")
            logger.info("")
            self.templates_logged = True

    def addSuccess(self, test):
        super().addSuccess(test)
        self.test_results[test.id()] = "PASS"

    def addError(self, test, err):
        super().addError(test, err)
        self.test_results[test.id()] = "ERROR"

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.test_results[test.id()] = "FAIL"

    def printErrors(self):
        # Print summary before error details
        logger.info("\n" + "="*50)
        logger.info("Test Summary")
        logger.info("="*50)
        
        # Sort test results by template name
        sorted_results = sorted(self.test_results.items(), 
                              key=lambda x: x[0].split('.')[-1])
        
        for test_id, result in sorted_results:
            template_name = test_id.split('.')[-1].replace('test_template_', '').replace('_', ' ').title()
            if 'test_' in template_name and 'template' not in template_name.lower():
                template_name = template_name.split('Test_')[-1]
            
            if result == "PASS":
                logger.success(f"{template_name}: {result}")
            else:
                logger.error(f"{template_name}: {result}")
        logger.info("="*50 + "\n")
        
        # Now print error details
        super().printErrors()

class CustomTestRunner(unittest.TextTestRunner):
    def _makeResult(self):
        return CustomTestResult(self.stream, self.descriptions, self.verbosity)

class TestTransactionParse(unittest.TestCase):
    """Test transaction parsing functionality"""
    
    def setUp(self):
        """Set up test environment"""
        self.parser = TransactionParser()
    
    def _test_template(self, template_name: str) -> None:
        """Helper method to test a specific template"""
        # Get the mock message for this template
        mock_msg = get_mock_message_by_template(template_name)
        self.assertIsNotNone(mock_msg, f"No mock message found for template: {template_name}")
        
        # Parse the message using the production entry point
        result = self.parser.parse_gmail_message(mock_msg)
        
        # Get the message body
        body, raw_body = self.parser._get_message_body(mock_msg['payload'])
        api_id = mock_msg.get('id', 'unknown')
        
        # Get the template that was matched
        template = self.parser.TEMPLATES.get(template_name, {})
        
        # Header
        logger.info("\n" + "="*30)
        logger.info(f"Template Used: {template_name}")
        logger.info("="*30)
        
        # First, log all fields and their patterns/values
        fields = ['api_id', 'account', 'vendor', 'amount', 'date', 'body']
        validation_errors = []
        
        for field in fields:
            pattern = template.get(field, 'No pattern defined')
            value = result.get(field, None) if result else None
            
            # Special handling for api_id and body which don't have regex patterns
            if field == 'api_id':
                pattern = 'N/A'
                value = mock_msg.get('id', None)
            elif field == 'body':
                pattern = 'N/A'
                value = mock_msg.get('snippet', None)
            
            logger.info(f"{field.title()} -- Regex: {pattern}")
            logger.info(f"   Value: {value}\n")
            
            # Collect validation errors instead of failing immediately
            if field == 'amount' and pattern != 'No pattern defined':
                if value is None:
                    # Try to match against both bodies before declaring failure
                    if pattern:
                        sanitized_match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
                        raw_match = re.search(pattern, raw_body, re.IGNORECASE | re.DOTALL)
                        if not (sanitized_match or raw_match):
                            validation_errors.append(f"Amount not found for template: {template_name}")
                elif not isinstance(value, (int, float)):
                    validation_errors.append(f"Amount should be numeric for template: {template_name}")
            elif field in ['vendor', 'account'] and pattern != 'No pattern defined':
                if field == 'vendor':
                    logger.info(f'result: {result}')
                    logger.info(f"Vendor: {value}")
                    logger.info(f"Pattern: {pattern}")
                    logger.info(f"Sanitized Body: {body}")
                    logger.info(f"Raw Body: {raw_body}")
                if value is None:
                    # Try to match against both bodies before declaring failure
                    if pattern:
                        sanitized_match = re.search(pattern, body, re.IGNORECASE | re.DOTALL)
                        raw_match = re.search(pattern, raw_body, re.IGNORECASE | re.DOTALL)
                        if not (sanitized_match or raw_match):
                            validation_errors.append(f"{field} not found for template: {template_name}")
                elif not isinstance(value, str):
                    validation_errors.append(f"{field} should be string for template: {template_name}")
        
        # After logging everything, handle any validation errors
        logger.info("="*30)
        if validation_errors:
            # Write both raw and sanitized body text to separate files
            # Sanitize template name for filename
            safe_template_name = template_name.replace("/", "_").replace("?", "Q").replace(" ", "_")
            failed_test_file = f'template_test_log_{api_id}_{safe_template_name}.log'
            with open(failed_test_file, 'w', encoding='utf-8') as f:
                f.write("=== Sanitized Body ===\n")
                f.write(body if isinstance(body, str) else str(body))
                f.write("\n\n=== Raw Body ===\n")
                f.write(raw_body if isinstance(raw_body, str) else str(raw_body))
            
            logger.error("FAILED")
            logger.error(validation_errors[0])
            logger.info("="*30 + "\n")
            
            raise AssertionError(validation_errors[0])
        else:
            logger.success("PASSED")
            logger.info("="*30 + "\n")

def generate_test_methods():
    """Dynamically generate test methods for each template"""
    mock_messages = get_all_mock_messages()
    
    for template_name in mock_messages.keys():
        test_name = f"test_template_{template_name.replace('/', '_').replace(' ', '_').lower()}"
        
        def create_test(name):
            def test(self):
                self._test_template(name)
            return test
        
        setattr(TestTransactionParse, test_name, create_test(template_name))

# Generate test methods for each template
generate_test_methods()

if __name__ == '__main__':
    program = unittest.main(testRunner=CustomTestRunner(verbosity=2), exit=False)
    sys.exit(not program.result.wasSuccessful()) 