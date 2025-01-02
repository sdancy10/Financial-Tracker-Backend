from typing import Dict, Any, List, Tuple
from datetime import datetime
from decimal import Decimal

class TransactionValidator:
    """Validates transaction data against required schema"""
    
    REQUIRED_FIELDS = {
        'id': str,
        'date': str,
        'description': str,
        'amount': (int, float, str),  # Allow numeric or string amounts
        'account_id': str,
        'user_id': str
    }
    
    OPTIONAL_FIELDS = {
        'category': str,
        'notes': str,
        'vendor': str,
        'location': str,
        'tags': list
    }
    
    def validate_transaction(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate transaction data
        Returns: (is_valid, error_messages)
        """
        errors = []
        
        # Check required fields
        for field, field_type in self.REQUIRED_FIELDS.items():
            if field not in data:
                errors.append(f"Missing required field: {field}")
                continue
                
            if not isinstance(data[field], field_type):
                if field == 'amount':
                    try:
                        # Try to convert amount to Decimal
                        Decimal(str(data[field]))
                    except:
                        errors.append(f"Invalid amount format: {data[field]}")
                else:
                    errors.append(f"Invalid type for {field}: expected {field_type}, got {type(data[field])}")
        
        # Validate date format
        if 'date' in data:
            try:
                # Try to parse as ISO format with timezone
                datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
            except ValueError:
                errors.append("Invalid date format. Expected ISO format with timezone (e.g., YYYY-MM-DDTHH:MM:SS+00:00)")
        
        # Validate amount
        if 'amount' in data:
            try:
                amount = Decimal(str(data['amount']))
                if amount == 0:
                    errors.append("Amount cannot be zero")
            except:
                errors.append(f"Invalid amount value: {data['amount']}")
        
        # Check optional fields
        for field, field_type in self.OPTIONAL_FIELDS.items():
            if field in data and not isinstance(data[field], field_type):
                errors.append(f"Invalid type for {field}: expected {field_type}, got {type(data[field])}")
        
        # Additional business rules
        if 'description' in data and len(data['description'].strip()) == 0:
            errors.append("Description cannot be empty")
            
        if 'user_id' in data and not data['user_id'].strip():
            errors.append("User ID cannot be empty")
            
        return len(errors) == 0, errors 