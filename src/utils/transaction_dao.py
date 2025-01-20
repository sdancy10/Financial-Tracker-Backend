import logging
from typing import Dict, Any, Optional, List, Iterator
from google.cloud import firestore
from datetime import datetime, timezone
from google.cloud.firestore_v1.base_query import FieldFilter, Or
import re
from metaphone import doublemetaphone
import calendar

class TransactionDAO:
    """Data Access Object for transaction operations"""
    
    def __init__(self, project_id: str):
        self.db = firestore.Client(project=project_id)
        self.batch_size = 500  # Firestore batch limit
        self.logger = logging.getLogger(__name__)
    
    def _clean_vendor(self, vendor: str) -> Dict[str, str]:
        """Clean vendor name and generate metaphone code"""
        # Remove special characters and convert to lowercase
        cleaned = re.sub('[^A-Za-z ]+', ' ', vendor.lower())
        # Remove multiple spaces
        cleaned = re.sub(' +', ' ', cleaned).strip()
        # Generate both metaphone codes
        primary, secondary = doublemetaphone(cleaned) if cleaned else (None, None)
        # Create array of metaphone codes, filtering out None values
        metaphone_codes = [code for code in [primary, secondary] if code]
        return {
            'vendor_cleaned': cleaned,
            'cleaned_metaphone': metaphone_codes
        }
    
    def _get_date_components(self, dt: datetime) -> Dict[str, Any]:
        """Extract date components from datetime object"""
        return {
            'day': dt.day,
            'day_name': calendar.day_name[dt.weekday()],
            'month': dt.month,
            'year': dt.year
        }
    
    def store_transactions_batch(self, transactions: List[Dict[str, Any]], user_id: str) -> bool:
        """Store multiple transactions in batches"""
        try:
            # Process in batches of 500 (Firestore batch limit)
            for i in range(0, len(transactions), self.batch_size):
                batch = self.db.batch()
                batch_transactions = transactions[i:i + self.batch_size]
                
                for transaction in batch_transactions:
                    # Validate required fields
                    required_fields = ['amount', 'vendor', 'account', 'template_used']
                    if not all(field in transaction and transaction[field] for field in required_fields):
                        missing_fields = [field for field in required_fields if field not in transaction or not transaction[field]]
                        self.logger.error(f"Transaction data: {transaction}")
                        self.logger.error(f"Skipping transaction {transaction.get('id', 'unknown')}: Missing required fields: {missing_fields}")
                        continue
                    
                    # Clean vendor and generate metaphone if vendor is present
                    if transaction.get('vendor'):
                        vendor_data = self._clean_vendor(transaction['vendor'])
                        transaction.update(vendor_data)
                    
                    # Handle category to predicted_category conversion
                    if 'category' in transaction and 'predicted_category' not in transaction:
                        transaction['predicted_category'] = transaction.pop('category')
                    elif 'predicted_category' not in transaction:
                        transaction['predicted_category'] = 'Uncategorized'
                    
                    # Ensure we have at least one valid ID
                    if not transaction.get('id') and not transaction.get('id_api'):
                        self.logger.error(f"Skipping transaction: No valid ID found (neither Message-ID nor Gmail API ID)")
                        continue
                    
                    # Use original Message-ID if available, otherwise use Gmail API ID
                    doc_id = transaction.get('id') or transaction.get('id_api')
                    
                    # Get document reference
                    doc_ref = self.db.collection('users').document(user_id)\
                                .collection('transactions').document(doc_id)
                    
                    # Prepare transaction data
                    transaction_data = transaction.copy()
                    transaction_data['id'] = doc_id
                    
                    # Handle date field
                    if isinstance(transaction_data.get('date'), str):
                        try:
                            # Parse ISO format string to datetime
                            dt = datetime.fromisoformat(transaction_data['date'].replace('Z', '+00:00'))
                            # Convert to UTC if it has timezone info
                            if dt.tzinfo is not None:
                                dt = dt.astimezone(timezone.utc)
                            # Convert to Firestore Timestamp
                            timestamp = firestore.SERVER_TIMESTAMP if dt > datetime.now(timezone.utc) else dt
                            transaction_data['date'] = timestamp
                            # Add date components
                            if timestamp != firestore.SERVER_TIMESTAMP:
                                transaction_data.update(self._get_date_components(dt))
                        except (ValueError, TypeError) as e:
                            self.logger.warning(f"Error parsing date string: {str(e)}")
                            transaction_data['date'] = firestore.SERVER_TIMESTAMP
                    elif isinstance(transaction_data.get('date'), datetime):
                        # Convert to UTC if it has timezone info
                        dt = transaction_data['date']
                        if dt.tzinfo is not None:
                            dt = dt.astimezone(timezone.utc)
                        # Convert to Firestore Timestamp
                        timestamp = firestore.SERVER_TIMESTAMP if dt > datetime.now(timezone.utc) else dt
                        transaction_data['date'] = timestamp
                        # Add date components
                        if timestamp != firestore.SERVER_TIMESTAMP:
                            transaction_data.update(self._get_date_components(dt))
                    else:
                        # Default to server timestamp if date is invalid or missing
                        self.logger.warning(f"Invalid date format: {transaction_data.get('date')}")
                        transaction_data['date'] = firestore.SERVER_TIMESTAMP
                    
                    # Check if document already exists
                    existing_doc = doc_ref.get()
                    
                    if existing_doc.exists:
                        # Get existing data
                        existing_data = existing_doc.to_dict()
                        
                        # Prepare updates with only the fields we explicitly handle
                        updates = {
                            # Required fields
                            'id': transaction_data.get('id'),
                            'id_api': transaction_data.get('id_api'),
                            'amount': transaction_data.get('amount'),
                            'vendor': transaction_data.get('vendor'),
                            'vendor_cleaned': transaction_data.get('vendor_cleaned'),
                            'account': transaction_data.get('account'),
                            'template_used': transaction_data.get('template_used'),
                            'cleaned_metaphone': transaction_data.get('cleaned_metaphone'),
                            
                            # Date field
                            'date': transaction_data.get('date'),
                            
                            # Metadata fields
                            'description': transaction_data.get('description'),
                            'account_id': transaction_data.get('account_id'),
                            'user_id': transaction_data.get('user_id'),
                            
                            # Category fields
                            'predicted_category': transaction_data.get('predicted_category', 'Uncategorized'),
                            'predicted_subcategory': transaction_data.get('predicted_subcategory', 'Uncategorized'),
                            
                            # Status and metadata
                            'status': 'processed',
                            'last_modified': firestore.SERVER_TIMESTAMP,
                            
                            # Preserve created_at from existing data
                            'created_at': existing_data.get('created_at', firestore.SERVER_TIMESTAMP)
                        }
                        
                        # Add date components if present
                        date_components = {
                            'day': transaction_data.get('day'),
                            'day_name': transaction_data.get('day_name'),
                            'month': transaction_data.get('month'),
                            'year': transaction_data.get('year')
                        }
                        updates.update({k: v for k, v in date_components.items() if v is not None})
                        
                        # Only include non-None values
                        updates = {k: v for k, v in updates.items() if v is not None}
                        
                        # Log the update operation
                        self.logger.info(f"Updating existing transaction: {doc_id}")
                        self.logger.debug(f"Update data: {updates}")
                        
                        # Use update instead of set to preserve other fields
                        batch.update(doc_ref, updates)
                    else:
                        # For new documents, use set with the full transaction_data
                        metadata = {
                            'created_at': firestore.SERVER_TIMESTAMP,
                            'last_modified': firestore.SERVER_TIMESTAMP,
                            'status': 'processed',
                            'predicted_category': transaction_data.get('predicted_category', 'Uncategorized'),
                            'predicted_subcategory': transaction_data.get('predicted_subcategory', 'Uncategorized')
                        }
                        transaction_data.update(metadata)
                        batch.set(doc_ref, transaction_data)
                        self.logger.info(f"Creating new transaction: {doc_id}")
                    
                    # Add to category index if present
                    if transaction_data.get('predicted_category'):
                        category_ref = self.db.collection('users').document(user_id)\
                                        .collection('categories').document(transaction_data['predicted_category'])
                        batch.set(category_ref, {
                            'last_used': firestore.SERVER_TIMESTAMP,
                            'transaction_count': firestore.Increment(1)
                        }, merge=True)
                
                # Only commit if there are operations in the batch
                if batch._write_pbs:
                    self.logger.info(f"Committing batch of {len(batch._write_pbs)} transactions")
                    batch.commit()
                    self.logger.info("Batch committed successfully")
            
            return True
        except Exception as e:
            self.logger.error(f"Error storing transaction batch: {str(e)}", exc_info=True)
            return False
    
    def store_transaction(self, transaction: Dict[str, Any], user_id: str) -> bool:
        """Store single transaction"""
        return self.store_transactions_batch([transaction], user_id)
    
    def get_transactions(self, user_id: str, 
                        filters: Optional[Dict[str, Any]] = None,
                        order_by: str = 'date',
                        desc: bool = True,
                        limit: int = 100) -> Iterator[Dict[str, Any]]:
        """
        Query transactions with filters
        filters format: {
            'predicted_category': 'groceries',
            'date_from': '2024-01-01',
            'date_to': '2024-02-01',
            'amount_min': 0,
            'amount_max': 1000,
            'search': 'walmart'  # Searches description and merchant
        }
        """
        try:
            # Start with base query
            query = self.db.collection('users').document(user_id)\
                        .collection('transactions')
            
            if filters:
                # Apply date range
                if 'date_from' in filters:
                    query = query.where(filter=FieldFilter('date', '>=', filters['date_from']))
                if 'date_to' in filters:
                    query = query.where(filter=FieldFilter('date', '<=', filters['date_to']))
                
                # Apply amount range
                if 'amount_min' in filters:
                    query = query.where(filter=FieldFilter('amount', '>=', str(filters['amount_min'])))
                if 'amount_max' in filters:
                    query = query.where(filter=FieldFilter('amount', '<=', str(filters['amount_max'])))
                
                # Apply category filter
                if 'predicted_category' in filters:
                    query = query.where(filter=FieldFilter('predicted_category', '==', filters['predicted_category']))
                
                # Apply text search
                if 'search' in filters:
                    search_term = filters['search'].lower()
                    query = query.where(filter=Or(
                        FieldFilter('description_lower', '>=', search_term),
                        FieldFilter('merchant_lower', '>=', search_term)
                    ))
            
            # Apply ordering
            query = query.order_by(order_by, direction=firestore.Query.DESCENDING if desc else firestore.Query.ASCENDING)
            
            # Apply limit
            if limit:
                query = query.limit(limit)
            
            # Return iterator
            return (doc.to_dict() for doc in query.stream())
            
        except Exception as e:
            print(f"Error querying transactions: {str(e)}")
            return iter([])  # Return empty iterator on error
    
    def get_categories(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's transaction categories with stats"""
        try:
            categories = []
            category_refs = self.db.collection('users').document(user_id)\
                            .collection('categories').stream()
            
            for doc in category_refs:
                category_data = doc.to_dict()
                category_data['name'] = doc.id
                categories.append(category_data)
            
            return sorted(categories, key=lambda x: x.get('last_used', datetime.min), reverse=True)
        except Exception as e:
            print(f"Error retrieving categories: {str(e)}")
            return []
    
    def update_transaction_category(self, transaction_id: str, user_id: str, 
                                  new_category: str, old_category: Optional[str] = None) -> bool:
        """Update transaction category and maintain category index"""
        try:
            batch = self.db.batch()
            
            # Update transaction
            transaction_ref = self.db.collection('users').document(user_id)\
                                .collection('transactions').document(transaction_id)
            batch.update(transaction_ref, {
                'predicted_category': new_category,
                'last_modified': firestore.SERVER_TIMESTAMP
            })
            
            # Update category stats
            new_category_ref = self.db.collection('users').document(user_id)\
                                .collection('categories').document(new_category)
            batch.set(new_category_ref, {
                'last_used': firestore.SERVER_TIMESTAMP,
                'transaction_count': firestore.Increment(1)
            }, merge=True)
            
            if old_category:
                old_category_ref = self.db.collection('users').document(user_id)\
                                    .collection('categories').document(old_category)
                batch.set(old_category_ref, {
                    'transaction_count': firestore.Increment(-1)
                }, merge=True)
            
            batch.commit()
            return True
        except Exception as e:
            print(f"Error updating transaction category: {str(e)}")
            return False
    
    def get_transaction(self, transaction_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a specific transaction"""
        try:
            doc_ref = self.db.collection('users').document(user_id)\
                        .collection('transactions').document(transaction_id)
            doc = doc_ref.get()
            
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"Error retrieving transaction: {str(e)}")
            return None
    
    def get_sample_transactions_by_template(self) -> Dict[str, Dict[str, Any]]:
        """Get one sample transaction for each template type"""
        try:
            samples = {}
            # Get all users
            users = self.db.collection('users').stream()
            
            for user in users:
                # Get transactions for each user
                transactions = self.db.collection('users').document(user.id)\
                                .collection('transactions')\
                                .where(filter=FieldFilter('template_used', '>', ''))\
                                .stream()
                
                # Group transactions by template
                for transaction in transactions:
                    data = transaction.to_dict()
                    template = data.get('template_used')
                    if template and template not in samples:
                        samples[template] = data
            
            return samples
        except Exception as e:
            self.logger.error(f"Error getting sample transactions: {str(e)}")
            return {}
    
    def update_transaction(self, transaction_id: str, user_id: str, 
                         updates: Dict[str, Any]) -> bool:
        """Update an existing transaction"""
        try:
            doc_ref = self.db.collection('users').document(user_id)\
                        .collection('transactions').document(transaction_id)
            
            # Add update timestamp
            updates['last_modified'] = firestore.SERVER_TIMESTAMP
            
            doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error updating transaction: {str(e)}")
            return False 