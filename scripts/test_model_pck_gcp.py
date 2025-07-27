import joblib
from google.cloud import storage
import tempfile

# Specify project ID as in TransactionModelTrainer
project_id = 'shanedancy-9f2a3'

# Initialize GCS client with explicit project ID for proper authentication
client = storage.Client(project=project_id)

# Specify bucket and blob path from context
bucket_name = 'shanedancy-9f2a3-ml-artifacts'
blob_path = 'models/transaction_model_v20250727/model.joblib'  # Using 'model.joblib' as per training script upload

# Download to temporary file
bucket = client.bucket(bucket_name)
blob = bucket.blob(blob_path)

with tempfile.NamedTemporaryFile(delete=False) as temp_file:
    blob.download_to_filename(temp_file.name)
    loaded = joblib.load(temp_file.name)

# Clean up temp file (optional, but good practice)
import os
os.unlink(temp_file.name)

print(type(loaded))