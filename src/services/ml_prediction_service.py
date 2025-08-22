from typing import Optional
import logging
import json
import os
import pandas as pd
from datetime import datetime
from google.cloud import aiplatform
from google.cloud import storage
from src.services.feature_engineering import FeatureEngineer
from src.utils.config import Config
import cachetools
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from src.services.ml_inference_client import CloudFunctionInferenceClient


class MLPredictionService:
    """Service for predicting transaction categories using deployed ML models"""
    
    def __init__(self, project_id: str, config: Optional[Config] = None):
        self.project_id = project_id
        self.config = config or Config()
        self.logger = logging.getLogger(__name__)
        
        # Initialize clients
        self.storage = storage.Client(project=project_id)
        
        # Inference mode: cloud_function (default), vertex_ai, or local
        self.inference_mode = self.config.get('ml', 'inference', 'mode', default='cloud_function')
        self.location = self.config.get('gcp', 'region', 'us-central1')
        
        # Initialize according to mode
        self.cf_client = None
        if self.inference_mode == 'cloud_function':
            # 1) Use config value if provided and non-empty
            function_url = self.config.get('ml', 'inference', 'function_url')
            if function_url:
                self.logger.info(f"ML inference: using configured Cloud Function URL: {function_url}")
            else:
                # 2) Environment override
                function_url = os.getenv('ML_INFERENCE_FUNCTION_URL')
                if function_url:
                    self.logger.info(f"ML inference: using env ML_INFERENCE_FUNCTION_URL: {function_url}")
                else:
                    # 3) Construct default 1st‑gen CF URL
                    # Prefer env vars first, then config
                    project = os.getenv('GOOGLE_CLOUD_PROJECT') or self.config.get('project', 'id') or self.project_id
                    region = os.getenv('REGION') or self.location or os.getenv('GOOGLE_CLOUD_REGION') or 'us-central1'
                    function_name = (
                        self.config.get('ml', 'inference', 'function_name', default=None)
                        or os.getenv('ML_INFERENCE_FUNCTION_NAME')
                        or 'ml-inference-function'
                    )
                    if project and region and function_name:
                        function_url = f"https://{region}-{project}.cloudfunctions.net/{function_name}"
                        self.logger.info(f"ML inference: constructed Cloud Function URL: {function_url}")
                    else:
                        self.logger.warning("ML inference: unable to construct Cloud Function URL (missing project/region/name)")
            timeout_seconds = self.config.get('ml', 'inference', 'timeout_seconds', default=45)
            if function_url:
                try:
                    self.cf_client = CloudFunctionInferenceClient(function_url, timeout_seconds)
                    self.logger.info(f"ML inference: initialized Cloud Function client (timeout={timeout_seconds}s)")
                except Exception as e:
                    self.logger.warning(f"Failed to initialize Cloud Function client: {e}")
            else:
                self.logger.warning("Cloud Function mode selected but 'function_url' is not configured")
        else:
            # Initialize Vertex AI only when needed
            aiplatform.init(project=project_id, location=self.location)
        
        # Model configuration
        self.current_model = None
        self.endpoint = None
        self.model_version = None
        self.model_resource_name = None
        
        # Feature engineering
        self.feature_engineer = None
        
        # Caching for frequent vendors (TTL: 1 hour)
        self.prediction_cache = cachetools.TTLCache(maxsize=1000, ttl=3600)
        
        # Thread pool for async predictions
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Model name pattern in Vertex AI
        self.model_display_name_prefix = "transaction_model"
        
        # Load current model metadata depending on mode
        if self.inference_mode == 'vertex_ai':
            self._load_current_model()
        else:
            # For cloud_function/local, model_version is determined server-side; we can set from config if present
            self.model_version = None
    
    def _load_current_model(self):
        """Load the current active model from Vertex AI Model Registry"""
        try:
            # List all models, ordered by creation time descending
            self.logger.info("Searching for all models")
            models = aiplatform.Model.list(
                order_by="create_time desc"
            )
            
            self.logger.info(f"Found {len(models)} total models")
            
            # Filter models client-side by display_name prefix
            transaction_models = [
                model for model in models 
                if model.display_name.startswith(self.model_display_name_prefix)
            ]
            
            self.logger.info(f"Found {len(transaction_models)} models matching prefix '{self.model_display_name_prefix}'")
            
            if not transaction_models:
                self.logger.warning("No transaction models found in Vertex AI Model Registry")
                return
            
            # Log all found matching models
            for i, model in enumerate(transaction_models):
                self.logger.info(f"Model {i+1}: {model.display_name} (created: {model.create_time})")
            
            # The first in the list is the most recent (since ordered desc)
            latest_model = transaction_models[0]
            self.current_model = latest_model
            self.model_resource_name = latest_model.resource_name
            self.model_version = latest_model.display_name
            
            self.logger.info(f"Found model: {self.model_version}")
            
            # Find deployed endpoints for this model
            endpoints = latest_model.gca_resource.deployed_models
            self.logger.info(f"Endpoints: {endpoints}")
            if endpoints:
                # Get the endpoint ID from the deployed model
                endpoint_id = endpoints[0].endpoint.split('/')[-1]
                self.logger.info(f"Found deployed endpoint ID: {endpoint_id}")
                self.endpoint = aiplatform.Endpoint(endpoint_id)
                self.logger.info(f"Loaded endpoint: {endpoint_id}")
            else:
                # If not deployed, look for endpoints by name pattern
                endpoint_display_name = f"{self.model_version}_endpoint"
                self.logger.info(f"Looking for endpoint with display name: {endpoint_display_name}")
                
                endpoint_filter = f'display_name="{endpoint_display_name}"'
                self.logger.info(f"Searching for endpoints with filter: {endpoint_filter}")
                
                endpoints = aiplatform.Endpoint.list(
                    filter=endpoint_filter,
                    order_by="create_time desc"
                )
                
                if endpoints:
                    self.endpoint = endpoints[0]
                    self.logger.info(f"Found endpoint: {self.endpoint.resource_name}")
                else:
                    self.logger.warning(f"No deployed endpoint found for model {self.model_version}")
                    return
            
            # Initialize feature engineer with model version
            self.feature_engineer = FeatureEngineer(self.project_id, self.model_version)
            
            # Log model metadata
            if hasattr(latest_model, 'labels') and latest_model.labels:
                self.logger.info(f"Model metadata: {latest_model.labels}")
            
        except Exception as e:
            self.logger.error(f"Error loading current model: {e}")
            self.endpoint = None
    
    def is_available(self) -> bool:
        """Check if ML prediction service is available"""
        if self.inference_mode == 'cloud_function':
            # Do not block on ping; consider available if client is set
            available = bool(self.cf_client)
            self.logger.info(f"ML inference availability (cloud_function): {available}")
            return available
        
        if self.endpoint is None:
            return False
        
        try:
            # Check if endpoint is ready by making a simple test call
            # Use a proper test transaction that goes through feature engineering
            test_transaction = {
                'vendor': 'test_vendor',
                'amount': 10.0,
                'template_used': 'test',
                'account': 'test_account',
                'date': datetime.now()
            }
            
            self.logger.info("Testing endpoint availability...")
            # Use the feature engineering pipeline to prepare the test data
            features = self.feature_engineer.prepare_for_prediction([test_transaction])
            # Convert DataFrame to list of lists for Vertex AI
            instances = features.values.tolist()
            response = self.endpoint.predict(instances=instances)
            self.logger.info("Endpoint is ready and responding")
            return True
            
        except Exception as e:
            self.logger.warning(f"Endpoint not ready: {e}")
            return False
    
    def get_current_model_version(self) -> Optional[str]:
        """Get the current model version"""
        return self.model_version
    
    def predict_category(self, transaction: dict) -> dict:
        """Predict category for a single transaction"""
        predictions = self.predict_categories([transaction])
        return predictions[0] if predictions else self._get_default_prediction()
    
    def predict_categories(self, transactions: list) -> list:
        """Predict categories for multiple transactions"""
        self.logger.info(f"predict_categories called with {len(transactions)} transactions (mode={self.inference_mode})")
        
        # Cloud Function mode
        if self.inference_mode == 'cloud_function':
            if not self.cf_client:
                self.logger.warning("Cloud Function client not initialized, returning defaults")
                return [self._get_default_prediction(source='cloud_function_unavailable') for _ in transactions]
            try:
                self.logger.info(f"Calling ML Cloud Function for {len(transactions)} transactions...")
                preds = self.cf_client.predict(transactions)
                # Ensure shape and fields; add timestamps and defaults
                results = []
                for p in preds:
                    result = {
                        'category': p.get('category', 'Uncategorized'),
                        'subcategory': p.get('subcategory'),
                        'confidence': float(p.get('confidence', 0.0)),
                        'source': p.get('source', 'cloud_function'),
                        'model_version': p.get('model_version', self.model_version),
                        'predicted_at': datetime.utcnow().isoformat()
                    }
                    results.append(result)
                self.logger.info(f"Received {len(results)} predictions from Cloud Function")
                return results
            except Exception as e:
                self.logger.error(f"Cloud Function prediction failed: {e}")
                return [self._get_default_prediction(source='cloud_function_error', error=str(e)) for _ in transactions]
        
        # Vertex AI mode
        if self.endpoint is None:
            self.logger.warning("No endpoint available, returning defaults")
            return [self._get_default_prediction() for _ in transactions]
        
        self.logger.info(f"Using endpoint: {self.endpoint.resource_name if self.endpoint else 'None'}")
        
        try:
            predictions = []
            uncached_transactions = []
            uncached_indices = []
            
            # Check cache first
            for i, transaction in enumerate(transactions):
                cache_key = self._get_cache_key(transaction)
                cached_result = self.prediction_cache.get(cache_key)
                
                if cached_result:
                    predictions.append(cached_result)
                else:
                    predictions.append(None)
                    uncached_transactions.append(transaction)
                    uncached_indices.append(i)
            
            # Predict uncached transactions
            if uncached_transactions:
                # Validate transactions
                valid_transactions = []
                valid_indices = []
                
                for i, transaction in enumerate(uncached_transactions):
                    is_valid, errors = self.feature_engineer.validate_transaction_data(transaction)
                    if is_valid:
                        valid_transactions.append(transaction)
                        valid_indices.append(uncached_indices[i])
                    else:
                        self.logger.warning(f"Invalid transaction data: {errors}")
                        predictions[uncached_indices[i]] = self._get_default_prediction()
                
                if valid_transactions:
                    # Prepare features
                    features = self.feature_engineer.prepare_for_prediction(valid_transactions)
                    
                    # Make predictions
                    batch_predictions = self._predict_batch(features)
                    
                    # Process results
                    for i, (transaction, prediction) in enumerate(zip(valid_transactions, batch_predictions)):
                        # Log prediction format for debugging
                        self.logger.debug(f"Prediction {i}: type={type(prediction)}, value={prediction}")
                        
                        # The prediction should already be a dict from _predict_batch
                        # No need to access it as a dict again, just use it directly
                        result = prediction.copy()  # Copy to avoid modifying original
                        
                        # Ensure all required fields are present
                        result['model_version'] = self.model_version
                        result['predicted_at'] = datetime.utcnow().isoformat()
                        
                        # Set defaults if missing
                        if 'source' not in result:
                            result['source'] = 'vertex_ai'
                        if 'confidence' not in result:
                            result['confidence'] = 0.0
                        
                        # Cache result
                        cache_key = self._get_cache_key(transaction)
                        self.prediction_cache[cache_key] = result
                        
                        # Update predictions list
                        predictions[valid_indices[i]] = result
            
            # Fill any remaining None values with defaults
            for i in range(len(predictions)):
                if predictions[i] is None:
                    predictions[i] = self._get_default_prediction()
            
            return predictions
            
        except Exception as e:
            self.logger.error(f"Error in batch prediction: {e}", exc_info=True)
            return [self._get_default_prediction() for _ in transactions]
    
    def _predict_batch(self, features: pd.DataFrame) -> list:
        """Make batch predictions using Vertex AI endpoint"""
        try:
            print("features: ", features.head(5))
            # Convert DataFrame to list of lists for Vertex AI
            instances = features.values.tolist()
            
            
            # Log detailed information about the request
            self.logger.debug(f"Features DataFrame shape: {features.shape}")
            self.logger.debug(f"Features DataFrame columns: {list(features.columns)}")
            self.logger.debug(f"First row of features: {features.iloc[0].tolist() if len(features) > 0 else 'No data'}")
            self.logger.debug(f"Instances type: {type(instances)}")
            self.logger.debug(f"Instances length: {len(instances)}")
            self.logger.debug(f"First instance type: {type(instances[0]) if instances else 'No instances'}")
            self.logger.debug(f"First instance: {instances[0] if instances else 'No instances'}")
            
            # Make prediction request with timeout
            import time
            start_time = time.time()
            
            # Set a reasonable timeout (15 seconds)
            timeout_seconds = 15
            
            self.logger.info(f"Making prediction request for {len(instances)} instances...")
            self.logger.debug(f"Endpoint details: {self.endpoint.resource_name}")
            self.logger.debug(f"Model version: {self.model_version}")
            
            response = self.endpoint.predict(instances=instances)
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"Prediction completed in {elapsed_time:.2f} seconds")
            
            # Debug logging for response format
            self.logger.debug(f"Response type: {type(response)}")
            self.logger.debug(f"Response.predictions type: {type(response.predictions)}")
            if response.predictions:
                self.logger.debug(f"First prediction type: {type(response.predictions[0])}")
                self.logger.debug(f"First prediction value: {response.predictions[0]}")
            
            # Parse predictions
            predictions = []
            for i, prediction in enumerate(response.predictions):
                self.logger.debug(f"Raw prediction {i}: type={type(prediction)}, value={prediction}")
                
                # Handle multi-output format [category, subcategory]
                if isinstance(prediction, list) and len(prediction) >= 2:
                    category = str(prediction[0])  # Convert to string
                    subcategory = str(prediction[1]) if len(prediction) > 1 and prediction[1] is not None else None
                    self.logger.debug(f"Parsed as list: category='{category}', subcategory='{subcategory}'")
                elif isinstance(prediction, list) and len(prediction) == 1:
                    # Single element list
                    category = str(prediction[0])
                    subcategory = None
                    self.logger.debug(f"Parsed as single-element list: category='{category}'")
                else:
                    # Assume it's a single value (category only)
                    category = str(prediction)
                    subcategory = None
                    self.logger.debug(f"Parsed as single value: category='{category}'")
                
                # Get confidence if available
                confidence = 1.0  # Default confidence
                if hasattr(response, 'deployed_model_id'):
                    # Some models provide confidence scores
                    pass
                
                predictions.append({
                    'category': category,
                    'subcategory': subcategory,
                    'confidence': confidence,
                    'source': 'vertex_ai'
                })
            
            self.logger.info(f"Successfully parsed {len(predictions)} predictions")
            return predictions
            
        except Exception as e:
            self.logger.error(f"Error calling Vertex AI endpoint: {e}")
            self.logger.error(f"Error type: {type(e).__name__}")
            
            # Check if it's a timeout/connection error
            if "timeout" in str(e).lower() or "connection" in str(e).lower():
                self.logger.warning("Connection timeout detected, returning default predictions")
                source = 'vertex_ai_timeout'
            elif "not found" in str(e).lower() or "does not exist" in str(e).lower():
                self.logger.warning("Endpoint not found, may need to redeploy model")
                source = 'vertex_ai_not_found'
            else:
                self.logger.error(f"Unexpected error: {str(e)}")
                source = 'vertex_ai_error'
            
            # Return default predictions for all instances
            self.logger.warning("Returning default predictions due to model error")
            return [{'category': 'Uncategorized', 'subcategory': None, 'confidence': 0.0, 'source': source, 'error': str(e)} 
                   for _ in range(len(features))]
    
    def _get_cache_key(self, transaction: dict) -> str:
        """Generate cache key for transaction"""
        # Use vendor, amount, and template as cache key
        vendor = transaction.get('vendor', transaction.get('description', ''))
        amount = transaction.get('amount', 0)
        template = transaction.get('template_used', '')
        
        return f"{vendor}|{amount}|{template}".lower()
    
    def _get_default_prediction(self, source: str = 'vertex_ai_unavailable', error: Optional[str] = None) -> dict:
        """Get default prediction when ML is unavailable"""
        return {
            'category': 'Uncategorized',
            'subcategory': None,
            'confidence': 0.0,
            'model_version': None,
            'predicted_at': datetime.utcnow().isoformat(),
            'source': source,
            'error': error
        }
    
    async def predict_categories_async(self, transactions: list) -> list:
        """Async version of predict_categories for better performance"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self.executor, self.predict_categories, transactions)
    
    def update_model(self, new_model_display_name: str):
        """Update to a new model version"""
        try:
            # Find the new model in Vertex AI
            models = aiplatform.Model.list(
                filter=f'display_name="{new_model_display_name}"'
            )
            
            if not models:
                self.logger.error(f"Model {new_model_display_name} not found")
                return
            
            # Reload with new model
            self._load_current_model()
            
            # Clear cache when model changes
            self.prediction_cache.clear()
            
            self.logger.info(f"Updated to model {new_model_display_name}")
            
        except Exception as e:
            self.logger.error(f"Error updating model: {e}")
    
    def get_model_metrics(self) -> dict:
        """Get current model performance metrics from Vertex AI"""
        try:
            if not self.current_model:
                return {}
            
            metrics = {}
            
            # Get model evaluation if available
            model_evaluations = self.current_model.list_model_evaluations()
            if model_evaluations:
                latest_eval = model_evaluations[0]
                metrics['evaluation'] = {
                    'metrics': latest_eval.metrics,
                    'create_time': latest_eval.create_time
                }
            
            # Get model metadata
            if hasattr(self.current_model, 'labels'):
                metrics['labels'] = self.current_model.labels
            
            # Get deployment info
            if self.endpoint:
                deployed_models = self.endpoint.list_models()
                if deployed_models:
                    metrics['deployment'] = {
                        'deployed_model_id': deployed_models[0].id,
                        'traffic_percentage': deployed_models[0].traffic_split
                    }
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Error getting model metrics: {e}")
            return {}
    
    def close(self):
        """Clean up resources"""
        self.executor.shutdown(wait=True) 