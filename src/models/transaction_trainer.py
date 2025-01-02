import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import FunctionTransformer
from sklearn.metrics import accuracy_score, classification_report
from sklearn.model_selection import GridSearchCV
from sklearn.multioutput import MultiOutputClassifier
from google.cloud import aiplatform
from google.cloud import storage
import os
import json
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import pickle
from src.utils.data_sync import DataSync

    
class TransactionModelTrainer:
    def __init__(self, project_id: str, region: str = "us-central1"):
        self.project_id = project_id
        self.region = region
        self.bucket_name = f"{project_id}-ml-artifacts"
        self.training_data_path = 'data/training/transaction_categorizations.xlsx'
        aiplatform.init(project=project_id, location=region)
        
        # Initialize data sync
        self.data_sync = DataSync(project_id)

    def extract_features(self, df):
        if isinstance(df, pd.Series):
            df = df.to_frame()

        if 'vendor' not in df.columns:
            raise ValueError("The DataFrame does not contain the column 'vendor'")

        df['vendor'] = df['vendor'].str.lower()
        
        vendor_list = [
            ('amz', 'amazon'),
            ('a.mazon', 'amazon'),
            ('amazon', 'amazon'),
            ('aramark', 'aramark'),
            ('jpmc', 'aramark'),
            ('great clips', 'great_clips'),
            ('osu', 'ohio_state'),
            ('ohio state', 'ohio_state'),
            ('firstma', 'student_loan'),
            ('mohela', 'student_loan'),
            ('spirits', 'bar'),
            ('brewery', 'bar'),
            ('tavern', 'bar'),
            ('bar', 'bar'),
            ('supplement', 'supplements'),
            ('best buy', 'best_buy'),
            ('lending', 'loan')
        ]

        for _, vendor_name in vendor_list:
            df[vendor_name] = 0
        for vendor_code, vendor_name in vendor_list:
            df[vendor_name] = df['vendor'].apply(lambda x: vendor_code in x).astype(int) + df[vendor_name]
        return df

    def create_pipeline(self):
        text_columns = ['vendor_cleaned', 'vendor', 'cleaned_metaphone',
                       'template_used', 'account', 'day', 'month', 'year', 'day_name']

        feature_extraction_transformer = FunctionTransformer(self.extract_features, validate=False)
        text_transformers = [(f'tfidf_{col}', TfidfVectorizer(min_df=0.001, max_df=0.99, ngram_range=(1, 2)), col) 
                            for col in text_columns]

        column_transformer = ColumnTransformer(
            text_transformers,
            remainder='passthrough'
        )

        multi_target_classifier = MultiOutputClassifier(
            RandomForestClassifier(n_estimators=100, min_samples_split=2, min_samples_leaf=1, random_state=42)
        )

        return Pipeline([
            ('feature_extraction', feature_extraction_transformer),
            ('column_transformer', column_transformer),
            ('multi_target_classifier', multi_target_classifier)
        ])

    def train_and_deploy_model(self, model_display_name: str):
        """Train and deploy model using Vertex AI custom training"""
        # Ensure training data is up to date
        self.data_sync.sync_training_data()
        
        # Load and prepare data
        df = pd.read_excel(self.training_data_path, sheet_name='raw_data')
        df.dropna(inplace=True)

        # Upload training data to GCS
        training_data_uri = self._upload_training_data(df)

        # Create custom training job specification
        job_spec = {
            "pythonPackageSpec": {
                "executorImageUri": "us-docker.pkg.dev/vertex-ai/training/scikit-learn-cpu.0-23:latest",
                "packageUris": [f"gs://{self.bucket_name}/trainer.tar.gz"],
                "pythonModule": "trainer.task",
                "args": [
                    f"--training_data_uri={training_data_uri}",
                    f"--model_dir=gs://{self.bucket_name}/models/{model_display_name}"
                ]
            }
        }

        # Create and run custom training job
        custom_job = aiplatform.CustomJob(
            display_name=f"train_{model_display_name}",
            worker_pool_specs=[job_spec],
            base_output_dir=f"gs://{self.bucket_name}/training_output"
        )
        custom_job.run(sync=True)

        # Create model in Vertex AI Model Registry
        model = aiplatform.Model.upload(
            display_name=model_display_name,
            artifact_uri=f"gs://{self.bucket_name}/models/{model_display_name}",
            serving_container_image_uri="us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.0-23:latest",
            serving_container_environment_variables={
                "SKLEARN_ALLOW_DEPRECATED_SKLEARN_PACKAGE": "True"
            }
        )

        # Deploy model to endpoint
        endpoint = model.deploy(
            machine_type="n1-standard-2",
            min_replica_count=1,
            max_replica_count=2,
            accelerator_type=None,
            accelerator_count=None
        )

        return model, endpoint

    def _upload_training_data(self, df: pd.DataFrame) -> str:
        """Upload training data to Cloud Storage"""
        data_path = f"data/training_data_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
        blob = self.bucket.blob(data_path)
        blob.upload_from_string(df.to_csv(index=False))
        return f"gs://{self.bucket_name}/{data_path}"

    def _create_trainer_package(self):
        """Create and upload trainer package"""
        trainer_code = """
import argparse
import os
import pickle
import pandas as pd
from google.cloud import storage
from sklearn.model_selection import train_test_split

def train_model(args):
    # Download training data from GCS
    storage_client = storage.Client()
    df = pd.read_csv(args.training_data_uri.replace('gs://', ''))
    
    # Create and train model pipeline
    pipeline = create_pipeline()
    X = df[text_columns]
    Y = df[['category', 'sub_category']].astype('string')
    pipeline.fit(X, Y)
    
    # Save model to GCS
    model_path = os.path.join(args.model_dir, 'model.pkl')
    with open('/tmp/model.pkl', 'wb') as f:
        pickle.dump(pipeline, f)
    
    bucket = storage_client.bucket(args.model_dir.split('/')[2])
    blob = bucket.blob('model.pkl')
    blob.upload_from_filename('/tmp/model.pkl')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--training_data_uri', type=str)
    parser.add_argument('--model_dir', type=str)
    args = parser.parse_args()
    train_model(args)
"""
        # Create trainer package
        os.makedirs('trainer', exist_ok=True)
        with open('trainer/task.py', 'w') as f:
            f.write(trainer_code)
        
        # Upload trainer package to GCS
        os.system('tar -czf trainer.tar.gz trainer/')
        blob = self.bucket.blob('trainer.tar.gz')
        blob.upload_from_filename('trainer.tar.gz')