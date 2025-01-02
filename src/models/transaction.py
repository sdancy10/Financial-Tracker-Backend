from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone

@dataclass
class Transaction:
    """Transaction data model"""
    id: str
    date: Union[datetime, str]  # Allow either datetime or empty string
    description: str
    amount: float
    account_id: str
    user_id: str
    id_api: Optional[str] = None  # Gmail API message ID
    category: Optional[str] = None
    vendor: Optional[str] = None
    notes: Optional[str] = None
    location: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    status: str = 'pending'

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Transaction':
        """Create Transaction from dictionary"""
        # Handle date field
        if hasattr(data['date'], 'toDate'):  # Check if it's a Firestore Timestamp
            data['date'] = data['date'].toDate().replace(tzinfo=timezone.utc)
        elif isinstance(data['date'], str):
            # If date doesn't have time info, append UTC midnight time
            if 'T' not in data['date']:
                data['date'] = f"{data['date']}T00:00:00Z"
            # Ensure UTC timezone
            elif not data['date'].endswith('Z') and '+' not in data['date'] and '-' not in data['date']:
                data['date'] = f"{data['date']}Z"
            # Parse with UTC timezone
            dt = datetime.fromisoformat(data['date'].replace('Z', '+00:00'))
            # Convert to UTC if it has a different timezone
            if dt.tzinfo is not None and dt.tzinfo != timezone.utc:
                dt = dt.astimezone(timezone.utc)
            data['date'] = dt
        elif isinstance(data['date'], datetime):
            # Ensure datetime has UTC timezone
            if data['date'].tzinfo is None:
                data['date'] = data['date'].replace(tzinfo=timezone.utc)
            elif data['date'].tzinfo != timezone.utc:
                data['date'] = data['date'].astimezone(timezone.utc)
        
        # Convert amount to float if it's a string
        if isinstance(data['amount'], str):
            # Remove currency symbols and commas
            amount_str = data['amount'].replace('$', '').replace(',', '')
            data['amount'] = float(amount_str)
        
        # Convert timestamps
        for field in ['created_at', 'updated_at']:
            if field in data:
                if hasattr(data[field], 'toDate'):  # Check if it's a Firestore Timestamp
                    data[field] = data[field].toDate().replace(tzinfo=timezone.utc)
                elif isinstance(data[field], str):
                    dt = datetime.fromisoformat(data[field].replace('Z', '+00:00'))
                    if dt.tzinfo is not None and dt.tzinfo != timezone.utc:
                        dt = dt.astimezone(timezone.utc)
                    data[field] = dt
                elif isinstance(data[field], datetime):
                    if data[field].tzinfo is None:
                        data[field] = data[field].replace(tzinfo=timezone.utc)
                    elif data[field].tzinfo != timezone.utc:
                        data[field] = data[field].astimezone(timezone.utc)
        
        # Set description from vendor if not provided
        if not data.get('description') and data.get('vendor'):
            data['description'] = data['vendor']
        elif not data.get('description'):
            data['description'] = 'Unknown transaction'
        
        # Handle merchant to vendor field conversion for backward compatibility
        if 'merchant' in data and not data.get('vendor'):
            data['vendor'] = data.pop('merchant')
        
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage"""
        # Ensure all datetime fields are in UTC
        date = self.date
        if isinstance(date, datetime):
            if date.tzinfo is None:
                date = date.replace(tzinfo=timezone.utc)
            elif date.tzinfo != timezone.utc:
                date = date.astimezone(timezone.utc)
        
        created_at = self.created_at
        if isinstance(created_at, datetime):
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            elif created_at.tzinfo != timezone.utc:
                created_at = created_at.astimezone(timezone.utc)
        
        updated_at = self.updated_at
        if isinstance(updated_at, datetime):
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            elif updated_at.tzinfo != timezone.utc:
                updated_at = updated_at.astimezone(timezone.utc)
        
        return {
            'id': self.id,
            'id_api': self.id_api,  # Include Gmail API ID
            'date': date,  # Let DAO handle conversion to Firestore Timestamp
            'description': self.description,
            'amount': self.amount,
            'account_id': self.account_id,
            'user_id': self.user_id,
            'category': self.category,
            'vendor': self.vendor,
            'notes': self.notes,
            'location': self.location,
            'tags': self.tags or [],
            'created_at': created_at,  # Let DAO handle conversion to Firestore Timestamp
            'updated_at': updated_at,  # Let DAO handle conversion to Firestore Timestamp
            'status': self.status
        } 