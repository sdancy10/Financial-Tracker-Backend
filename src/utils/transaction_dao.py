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
    
    def _clean_vendor(self, vendor: str) -> str:
        """Clean vendor name by removing special characters and converting to lowercase"""
        # Remove special characters and convert to lowercase
        cleaned = re.sub('[^A-Za-z ]+', ' ', vendor.lower())
        # Remove multiple spaces
        cleaned = re.sub(' +', ' ', cleaned).strip()
        return cleaned
    
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
            # Process in batches of 500 (Firestore limit)
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
                    
                    # Ensure we have at least one valid ID
                    if not transaction.get('id') and not transaction.get('id_api'):
                        self.logger.error(f"Skipping transaction: No valid ID found (neither Message-ID nor Gmail API ID)")
                        continue
                    
                    # Use original Message-ID if available, otherwise use Gmail API ID
                    doc_id = transaction.get('id') or transaction.get('id_api')
                    
                    # Get document reference
                    doc_ref = self.db.collection('users').document(user_id)\
                                .collection('transactions').document(doc_id)
                    
                    # Add metadata
                    transaction_data = transaction.copy()
                    
                    # Clean and process vendor name
                    if 'vendor' in transaction_data:
                        vendor = transaction_data['vendor']
                        transaction_data['vendor'] = vendor.lower()  # Store original vendor in lowercase
                        transaction_data['vendor_cleaned'] = self._clean_vendor(vendor)
                        transaction_data['cleaned_metaphone'] = list(doublemetaphone(transaction_data['vendor_cleaned']))
                    
                    # Convert date to UTC Firestore Timestamp and extract components
                    if isinstance(transaction_data.get('date'), str):
                        try:
                            # Parse ISO format date string and convert to UTC
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
                        except ValueError as e:
                            # If date parsing fails, use server timestamp
                            self.logger.warning(f"Failed to parse date {transaction_data.get('date')}: {str(e)}")
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
                    
                    # Add metadata
                    metadata = {
                        'updated_at': firestore.SERVER_TIMESTAMP,
                        'status': 'processed',
                        'predicted_category': 'Uncategorized',
                        'predicted_subcategory': None
                    }
                    if not existing_doc.exists:
                        metadata['created_at'] = firestore.SERVER_TIMESTAMP
                    else:
                        # Preserve the original created_at value for existing documents
                        existing_data = existing_doc.to_dict()
                        if existing_data and 'created_at' in existing_data and existing_data['created_at']:
                            metadata['created_at'] = existing_data['created_at']
                        else:
                            # If no created_at exists or it's null, set a new one
                            metadata['created_at'] = firestore.SERVER_TIMESTAMP
                            self.logger.info(f"Adding missing created_at for existing transaction: {transaction.get('id')}")
                    
                    transaction_data.update(metadata)
                    
                    # Add to category index if present
                    if 'category' in transaction_data:
                        category_ref = self.db.collection('users').document(user_id)\
                                        .collection('categories').document(transaction_data['category'])
                        batch.set(category_ref, {
                            'last_used': firestore.SERVER_TIMESTAMP,
                            'transaction_count': firestore.Increment(1)
                        }, merge=True)
                    
                    self.logger.info(f"Adding transaction to batch: {transaction_data['id']}")
                    batch.set(doc_ref, transaction_data)
                
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
            'category': 'groceries',
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
                if 'category' in filters:
                    query = query.where(filter=FieldFilter('category', '==', filters['category']))
                
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
                'category': new_category,
                'updated_at': firestore.SERVER_TIMESTAMP
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
            updates['updated_at'] = firestore.SERVER_TIMESTAMP
            
            doc_ref.update(updates)
            return True
        except Exception as e:
            print(f"Error updating transaction: {str(e)}")
            return False 