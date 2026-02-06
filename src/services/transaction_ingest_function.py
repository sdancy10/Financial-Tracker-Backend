"""
Cloud Function: transaction-ingest-function (HTTP)

Accepts transactions from external sources (e.g. Coinbase loader),
runs ML category prediction, and writes to Firestore via TransactionDAO.

Request:  POST {"user_id": "...", "transactions": [{id, vendor, amount, date, account, template_used}, ...]}
Response: {"status": "success", "total": N, "stored": true, "predictions_applied": N}
"""

import json
import logging
import os
from typing import Any, Dict, List

import joblib
from google.cloud import storage
import nltk

from src.services.feature_engineering import FeatureEngineer
from src.utils.transaction_dao import TransactionDAO

# Global caches for warm Cloud Function instances
_MODEL = None
_MODEL_VERSION = None
_FEATURE_ENGINEER = None
_TRANSACTION_DAO = None


def _get_project_id() -> str:
    return os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")


def _resolve_latest_model_path(bucket_name: str) -> str:
    client = storage.Client(project=_get_project_id())
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix="models/"))
    candidates = [b.name for b in blobs if b.name.endswith("/model.joblib")]
    if not candidates:
        raise FileNotFoundError("No model.joblib found in models/ directory")
    candidates.sort(reverse=True)
    return candidates[0]


def _load_model_if_needed(model_version: str | None = None):
    global _MODEL, _MODEL_VERSION, _FEATURE_ENGINEER
    if _MODEL is not None and (model_version is None or model_version == _MODEL_VERSION):
        return

    logger = logging.getLogger(__name__)
    logger.info("[Ingest CF] Loading ML model...")
    project_id = _get_project_id()
    if not project_id:
        raise RuntimeError("PROJECT_ID not set")

    bucket_name = f"{project_id}-ml-artifacts"
    client = storage.Client(project=project_id)
    bucket = client.bucket(bucket_name)

    if model_version:
        blob_path = f"models/{model_version}/model.joblib"
    else:
        blob_path = _resolve_latest_model_path(bucket_name)
        try:
            parts = blob_path.split("/")
            model_version = parts[1]
        except Exception:
            model_version = None

    blob = bucket.blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError(f"Model blob not found: gs://{bucket_name}/{blob_path}")

    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        logger.info(f"[Ingest CF] Downloading model from gs://{bucket_name}/{blob_path}")
        blob.download_to_filename(tmp.name)
        _MODEL = joblib.load(tmp.name)

    _MODEL_VERSION = model_version
    _FEATURE_ENGINEER = FeatureEngineer(project_id, model_version)
    logger.info(f"[Ingest CF] Model loaded. version={_MODEL_VERSION}")

    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        try:
            nltk.download('punkt', quiet=True)
        except Exception:
            pass
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        try:
            nltk.download('stopwords', quiet=True)
        except Exception:
            pass


def _get_transaction_dao() -> TransactionDAO:
    global _TRANSACTION_DAO
    if _TRANSACTION_DAO is None:
        project_id = _get_project_id()
        if not project_id:
            raise RuntimeError("PROJECT_ID not set")
        _TRANSACTION_DAO = TransactionDAO(project_id)
    return _TRANSACTION_DAO


def _make_response(status_code: int, body: Dict[str, Any]):
    return (json.dumps(body), status_code, {"Content-Type": "application/json"})


def ingest_transactions_http(request):
    """HTTP entry point for Cloud Functions.

    Accepts JSON:
    {
        "user_id": "firestore_user_id",
        "transactions": [
            {"id": "...", "vendor": "...", "amount": 10.0,
             "date": "2026-02-04T00:00:00+00:00", "account": "CB_0000",
             "template_used": "Coinbase One Credit Card"}
        ]
    }

    Returns JSON:
    {
        "status": "success",
        "total": N,
        "stored": true,
        "predictions_applied": N
    }
    """
    logger = logging.getLogger(__name__)
    try:
        if request.method == 'OPTIONS':
            return ('', 204, {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type',
            })

        data = request.get_json(silent=True) or {}
        user_id = data.get("user_id")
        transactions = data.get("transactions", [])

        if not user_id:
            return _make_response(400, {"error": "Missing required field: user_id"})

        if not isinstance(transactions, list) or not transactions:
            return _make_response(400, {"error": "transactions must be a non-empty list"})

        required = ['id', 'vendor', 'amount', 'date', 'account', 'template_used']
        for i, txn in enumerate(transactions):
            missing = [f for f in required if f not in txn]
            if missing:
                return _make_response(400, {
                    "error": f"Transaction at index {i} missing fields: {', '.join(missing)}"
                })

        logger.info(f"[Ingest CF] Received {len(transactions)} transactions for user {user_id}")

        # ML prediction
        _load_model_if_needed()
        features = _FEATURE_ENGINEER.prepare_for_prediction(transactions)
        preds = _MODEL.predict(features)

        for txn, row in zip(transactions, preds):
            txn['predicted_category'] = str(row[0]) if len(row) > 0 else "Uncategorized"
            txn['predicted_subcategory'] = str(row[1]) if len(row) > 1 and row[1] is not None else "Uncategorized"

        logger.info(f"[Ingest CF] Predictions complete. Storing to Firestore...")

        # Firestore writes
        dao = _get_transaction_dao()
        stored = dao.store_transactions_batch(transactions, user_id)

        logger.info(f"[Ingest CF] Done. stored={stored}")
        return _make_response(200, {
            "status": "success",
            "total": len(transactions),
            "stored": stored,
            "predictions_applied": len(preds)
        })

    except Exception as e:
        logger.error(f"[Ingest CF] Error: {e}", exc_info=True)
        return _make_response(500, {"error": "Ingest failed", "message": str(e)})
