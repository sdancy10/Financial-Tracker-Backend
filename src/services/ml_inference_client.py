import json
import logging
from typing import List, Dict, Any, Optional

import requests
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


class CloudFunctionInferenceClient:
    """Client to call the ML inference Cloud Function with ID token auth."""

    def __init__(self, function_url: str, timeout_seconds: int = 15):
        if not function_url:
            raise ValueError("function_url is required for Cloud Function inference")

        self.function_url = function_url
        self.timeout_seconds = timeout_seconds
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        self._google_request = google_requests.Request()

    def _get_id_token(self) -> str:
        """Fetch an ID token for the Cloud Function URL."""
        self.logger.info(f"Fetching ID token for ML Cloud Function URL: {self.function_url}")
        return id_token.fetch_id_token(self._google_request, self.function_url)

    def predict(self, transactions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Send transactions to the Cloud Function and return predictions."""
        try:
            token = self._get_id_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            payload = {"transactions": transactions}

            self.logger.info("Posting transactions to ML Cloud Function...")
            response = self.session.post(
                self.function_url,
                data=json.dumps(payload),
                headers=headers,
                timeout=self.timeout_seconds
            )
            self.logger.info(f"ML Cloud Function response status: {response.status_code}")
            response.raise_for_status()

            data = response.json()
            self.logger.info(f"ML Cloud Function returned model_version: {data.get('model_version')}")
            predictions = data.get("predictions", [])
            model_version = data.get("model_version")
            if not isinstance(predictions, list):
                raise ValueError("Invalid response format: 'predictions' must be a list")
            # Attach model_version to each prediction if present
            if model_version:
                for p in predictions:
                    if isinstance(p, dict) and 'model_version' not in p:
                        p['model_version'] = model_version
            return predictions
        except Exception as e:
            self.logger.error(f"Cloud Function inference failed: {e}")
            raise

    def ping(self) -> bool:
        """Lightweight availability check."""
        try:
            sample_tx = [{
                'vendor': 'test_vendor',
                'amount': 1.0,
                'template_used': 'test',
                'account': 'test',
                'date': '2024-01-01T00:00:00Z'
            }]
            _ = self.predict(sample_tx)
            return True
        except Exception:
            return False


