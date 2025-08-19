import json
import logging
import os
from typing import Any, Dict, List

import joblib
from google.cloud import storage
import nltk

# Import using project-relative path; deploy script will rewrite to plain imports for Cloud Functions
from src.services.feature_engineering import FeatureEngineer


# Global model cache for warm instances
_MODEL = None
_MODEL_VERSION = None
_FEATURE_ENGINEER = None


def _get_project_id() -> str:
    return os.environ.get("PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")


def _resolve_latest_model_path(bucket_name: str) -> str:
    """Find the most recent model artifact path in the artifacts bucket."""
    client = storage.Client(project=_get_project_id())
    bucket = client.bucket(bucket_name)
    blobs = list(bucket.list_blobs(prefix="models/"))
    # Prefer model.joblib under models/<version>/
    candidates = [b.name for b in blobs if b.name.endswith("/model.joblib")]
    if not candidates:
        raise FileNotFoundError("No model.joblib found in models/ directory")
    candidates.sort(reverse=True)
    return candidates[0]


def _load_model_if_needed(model_version: str | None = None):
    global _MODEL, _MODEL_VERSION, _FEATURE_ENGINEER
    if _MODEL is not None and (model_version is None or model_version == _MODEL_VERSION):
        return

    logging.getLogger(__name__).info("[ML CF] Loading ML model for inference function...")
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
        # Parse version from path models/<version>/model.joblib
        try:
            parts = blob_path.split("/")
            model_version = parts[1]
        except Exception:
            model_version = None

    blob = bucket.blob(blob_path)
    if not blob.exists():
        raise FileNotFoundError(f"Model blob not found: gs://{bucket_name}/{blob_path}")

    # Download to temp and load
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        logging.getLogger(__name__).info(f"[ML CF] Downloading model from gs://{bucket_name}/{blob_path}")
        blob.download_to_filename(tmp.name)
        _MODEL = joblib.load(tmp.name)

    _MODEL_VERSION = model_version
    _FEATURE_ENGINEER = FeatureEngineer(project_id, model_version)
    logging.getLogger(__name__).info(f"[ML CF] Model loaded. version={_MODEL_VERSION}")

    # Ensure required NLTK resources are available (best-effort)
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


def _make_response(status_code: int, body: Dict[str, Any]):
    return (json.dumps(body), status_code, {"Content-Type": "application/json"})


def predict_categories_http(request):
    """HTTP entry point for Cloud Functions.

    Expects JSON: {"transactions": [...], "model_version": "optional"}
    """
    logger = logging.getLogger(__name__)
    try:
        if request.method == 'OPTIONS':
            # CORS preflight support (optional)
            return ('', 204, {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
            })

        data = request.get_json(silent=True) or {}
        transactions = data.get("transactions", [])
        model_version = data.get("model_version")
        logger.info(f"[ML CF] Received request: count={len(transactions)}, override_model={bool(model_version)}")

        if not isinstance(transactions, list) or not transactions:
            return _make_response(400, {"error": "Missing or invalid 'transactions' list"})

        _load_model_if_needed(model_version)
        # Prepare features
        features = _FEATURE_ENGINEER.prepare_for_prediction(transactions)

        # Run predictions: model is a MultiOutput pipeline → returns array shape (n, 2)
        logger.info("[ML CF] Running predictions...")
        preds = _MODEL.predict(features)

        results: List[Dict[str, Any]] = []
        for row in preds:
            category = str(row[0]) if len(row) > 0 else "Uncategorized"
            subcategory = str(row[1]) if len(row) > 1 and row[1] is not None else None
            results.append({
                "category": category,
                "subcategory": subcategory,
                "confidence": 1.0,
                "source": "cloud_function"
            })

        logger.info(f"[ML CF] Returning {len(results)} predictions (model={_MODEL_VERSION})")
        return _make_response(200, {
            "predictions": results,
            "model_version": _MODEL_VERSION
        })
    except Exception as e:
        logger.error(f"[ML CF] Inference function error: {e}")
        return _make_response(500, {"error": "Prediction failed", "message": str(e)})


