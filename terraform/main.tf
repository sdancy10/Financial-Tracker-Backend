provider "google" {
  project = local.project_id
  region  = local.region
  credentials = "${path.module}/../credentials/service-account-key.json"
}

# Get project data
data "google_project" "project" {}

# Gmail OAuth credentials secrets - one for each account
resource "google_secret_manager_secret" "gmail_oauth" {
  for_each = local.enabled_services.secrets ? local.config_raw.auth.gmail.accounts : {}
  
  secret_id = format("gmail-credentials-%s-%s",
    lower(each.value.user_id),
    replace(
      replace(
        base64encode(
          [for email, account in local.config_raw.auth.gmail.email_to_account : email if account == each.key][0]
        ),
        "-", "_"
      ),
      "=", ""
    )
  )

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Gmail OAuth credentials versions - one for each account
resource "google_secret_manager_secret_version" "gmail_oauth" {
  for_each = local.enabled_services.secrets ? local.config_raw.auth.gmail.accounts : {}
  
  secret = google_secret_manager_secret.gmail_oauth[each.key].id
  secret_data = jsonencode({
    client_id     = local.gmail_user_credentials[each.key].client_id
    client_secret = local.gmail_user_credentials[each.key].client_secret
    refresh_token = local.gmail_user_credentials[each.key].refresh_token
    token_uri     = local.config_raw.auth.gmail.token_uri
    scopes        = local.config_raw.auth.gmail.scopes
    email         = [for email, account in local.config_raw.auth.gmail.email_to_account : email if account == each.key][0]
    user_id       = each.value.user_id
  })
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = local.enabled_apis
  
  service = each.key
  disable_on_destroy = false
}

# Storage buckets
resource "google_storage_bucket" "ml_artifacts_bucket" {
  count = local.enabled_services.storage ? 1 : 0
  
  name     = local.storage.buckets.ml_artifacts
  location = local.resource_config.storage.location
  uniform_bucket_level_access = true
  
}

resource "google_storage_bucket" "functions_bucket" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name     = local.storage.buckets.functions
  location = local.resource_config.storage.location
  uniform_bucket_level_access = true
}
# IAM for user to view/download objects in ML artifacts bucket
resource "google_storage_bucket_iam_member" "ml_artifacts_user_viewer" {
  count = local.enabled_services.storage ? 1 : 0  # Only create if storage is enabled
  
  bucket = google_storage_bucket.ml_artifacts_bucket[0].name
  role   = "roles/storage.objectViewer"  # Grants storage.objects.get (download/read access)
  member = "user:sdancy.10@gmail.com"    # Your personal account
}

# ML Data Storage Bucket for Parquet files
resource "google_storage_bucket" "ml_data_bucket" {
  count = local.enabled_services.storage ? 1 : 0
  
  name     = "${local.project_id}-ml-data"
  location = local.resource_config.storage.location
  uniform_bucket_level_access = true
  force_destroy = true
  
  lifecycle_rule {
    condition {
      age = 90  # Delete files older than 90 days
    }
    action {
      type = "Delete"
    }
  }
}

# BigQuery Dataset for ML Training Data
resource "google_bigquery_dataset" "transactions" {
  count = try(local.enabled_services.bigquery, true) ? 1 : 0
  
  dataset_id = "${replace(local.project_id, "-", "_")}_transactions"
  location   = "US"
  description = "Transaction data for ML training"

  delete_contents_on_destroy = true
}

# BigQuery Table for ML Feedback
resource "google_bigquery_table" "ml_feedback" {
  count = local.enabled_services.bigquery ? 1 : 0
  
  dataset_id = google_bigquery_dataset.transactions[0].dataset_id
  table_id   = "ml_feedback"
  
  schema = jsonencode([
    {
      name = "feedback_id"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "transaction_id"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "user_id"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "original_category"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "original_subcategory"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "user_category"
      type = "STRING"
      mode = "REQUIRED"
    },
    {
      name = "user_subcategory"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "prediction_confidence"
      type = "FLOAT64"
      mode = "NULLABLE"
    },
    {
      name = "model_version"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "vendor"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "vendor_cleaned"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "amount"
      type = "FLOAT64"
      mode = "NULLABLE"
    },
    {
      name = "template_used"
      type = "STRING"
      mode = "NULLABLE"
    },
    {
      name = "feedback_timestamp"
      type = "TIMESTAMP"
      mode = "REQUIRED"
    },
    {
      name = "transaction_date"
      type = "TIMESTAMP"
      mode = "NULLABLE"
    }
  ])
}

# Cloud Function for Model Retraining
resource "google_cloudfunctions_function" "model_retraining" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = "model-retraining-function"
  runtime     = "python310"
  region      = local.region
  
  source_archive_bucket = google_storage_bucket.functions_bucket[0].name
  source_archive_object = "model-retraining-function.zip"
  
  depends_on = [google_storage_bucket.functions_bucket]
  
  entry_point = "trigger_model_retraining"
  timeout     = 540
  available_memory_mb = 2048
  
  event_trigger {
    event_type = "providers/cloud.pubsub/eventTypes/topic.publish"
    resource   = google_pubsub_topic.model_retraining[0].name
  }
  
  environment_variables = {
    PROJECT_ID = local.project_id
    GOOGLE_CLOUD_PROJECT = local.project_id
    LOG_LEVEL = "INFO"
  }
  
  service_account_email = local.service_accounts.app_engine
}

# Pub/Sub Topic for Model Retraining
resource "google_pubsub_topic" "model_retraining" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  name = "model-retraining-trigger"
}

# Cloud Scheduler for Model Retraining
resource "google_cloud_scheduler_job" "model_retraining_scheduler" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = "model-retraining-weekly"
  region      = local.region
  schedule    = "0 2 * * 0"  # Weekly at 2 AM on Sundays
  time_zone   = "America/New_York"
  
  pubsub_target {
    topic_name = google_pubsub_topic.model_retraining[0].id
    data = base64encode(jsonencode({
      min_feedback_count = 100
      days_lookback = 7
    }))
  }
}

# Cloud Function for Model Performance Monitoring
resource "google_cloudfunctions_function" "model_performance_checker" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = "model-performance-checker"
  runtime     = "python310"
  region      = local.region
  
  source_archive_bucket = google_storage_bucket.functions_bucket[0].name
  source_archive_object = "model-performance-checker.zip"
  
  depends_on = [google_storage_bucket.functions_bucket]
  
  entry_point = "check_model_performance"
  timeout     = 60
  available_memory_mb = 512
  
  trigger_http = true
  
  environment_variables = {
    PROJECT_ID = local.project_id
    GOOGLE_CLOUD_PROJECT = local.project_id
    LOG_LEVEL = "INFO"
  }
  
  service_account_email = local.service_accounts.app_engine
}

# Cloud Scheduler for Performance Monitoring
resource "google_cloud_scheduler_job" "performance_monitor_scheduler" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = "model-performance-monitor"
  region      = local.region
  schedule    = "0 */6 * * *"  # Every 6 hours
  time_zone   = "America/New_York"
  
  http_target {
    uri = google_cloudfunctions_function.model_performance_checker[0].https_trigger_url
    http_method = "GET"
    oidc_token {
      service_account_email = local.service_accounts.app_engine
    }
  }
}

# Pub/Sub topic for transaction processing
resource "google_pubsub_topic" "transaction_topic" {
  count = local.enabled_services.pubsub ? 1 : 0
  name = local.pubsub.topics.transactions
}

# Cloud Function
resource "google_cloudfunctions_function" "transaction_processor" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = local.cloud_function.name
  description = "Processes financial transactions"
  runtime     = local.cloud_function.runtime

  available_memory_mb   = local.resource_config.cloud_function.memory
  source_archive_bucket = google_storage_bucket.functions_bucket[0].name
  source_archive_object = "function-source.zip"
  entry_point          = local.cloud_function.entry_point
  timeout             = local.resource_config.cloud_function.timeout

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.transaction_topic[0].name
  }

  environment_variables = {
    "CONFIG_PATH"          = "config.yaml"
    "GOOGLE_CLOUD_PROJECT" = local.project_id
    "PROJECT_ID"           = local.project_id
    "REGION"               = local.region
    "LOG_LEVEL"            = "INFO"  # Set to DEBUG for verbose logging
  }

  service_account_email = local.service_accounts.app_engine

  depends_on = [
    google_project_service.required_apis
  ]
}

# Data Export Function for ML Pipeline
resource "google_cloudfunctions_function" "data_export_function" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = "data-export-function"
  description = "Exports transaction data to BigQuery and Parquet for ML training"
  runtime     = "python310"
  region      = local.region

  available_memory_mb   = 512
  source_archive_bucket = google_storage_bucket.functions_bucket[0].name
  source_archive_object = "data-export-function.zip"
  entry_point          = "export_training_data_http"
  timeout             = 540

  trigger_http = true
  https_trigger_security_level = "SECURE_ALWAYS"

  environment_variables = {
    "PROJECT_ID"           = local.project_id
    "GOOGLE_CLOUD_PROJECT" = local.project_id
    "LOG_LEVEL"            = "INFO"
  }

  service_account_email = local.service_accounts.app_engine

  depends_on = [
    google_storage_bucket.functions_bucket,
    google_project_service.required_apis,
    google_bigquery_dataset.transactions,
    google_storage_bucket.ml_data_bucket
  ]
}

# Cloud Scheduler job for data export
resource "google_cloud_scheduler_job" "data_export_scheduler" {
  count = local.enabled_services.scheduler ? 1 : 0
  
  name             = "data-export-scheduler"
  description      = "Triggers weekly data export for ML training"
  schedule         = "0 2 * * 0"  # Weekly on Sunday at 2 AM
  time_zone        = "America/New_York"

  retry_config {
    retry_count = 3
    min_backoff_duration = "60s"
  }

  http_target {
    uri = google_cloudfunctions_function.data_export_function[0].https_trigger_url
    http_method = "POST"
    headers = {
      "Content-Type" = "application/json"
    }
    body = base64encode(jsonencode({
      action = "export_all"
    }))
  }

  depends_on = [
    google_cloudfunctions_function.data_export_function
  ]
}

# Cloud Scheduler job
resource "google_cloud_scheduler_job" "transaction_scheduler" {
  count = local.enabled_services.scheduler ? 1 : 0
  
  name             = local.scheduler.jobs.transaction_processor.name
  description      = local.scheduler.jobs.transaction_processor.description
  schedule         = local.resource_config.cloud_function.schedule
  time_zone        = local.scheduler.transaction_sync.timezone

  retry_config {
    retry_count = local.resource_config.cloud_function.retries
    min_backoff_duration = "${local.scheduler.transaction_sync.retry_interval}s"
  }

  pubsub_target {
    topic_name = google_pubsub_topic.transaction_topic[0].id
    data       = base64encode("{}")
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Cloud Run service
resource "google_cloud_run_service" "transaction_api" {
  count = local.enabled_services.cloud_api ? 1 : 0
  
  name     = local.cloud_run.service_name
  location = local.region

  template {
    spec {
      containers {
        image = local.cloud_run.container_image
        resources {
          limits = {
            cpu    = local.resource_config.cloud_run.cpu
            memory = local.resource_config.cloud_run.memory
          }
        }
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = local.project_id
        }
        env {
          name  = "CONFIG_PATH"
          value = "config.yaml"
        }
        env {
          name  = "ENVIRONMENT"
          value = local.use_free_tier ? "free_tier" : "standard"
        }
      }
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = tostring(local.resource_config.cloud_run.min_instances)
        "autoscaling.knative.dev/maxScale" = tostring(local.resource_config.cloud_run.max_instances)
      }
    }
  }

  autogenerate_revision_name = true

  traffic {
    percent         = 100
    latest_revision = true
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# IAM for Cloud Run
resource "google_cloud_run_service_iam_member" "public_access" {
  count = local.enabled_services.cloud_api ? 1 : 0
  
  service  = google_cloud_run_service.transaction_api[0].name
  location = local.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "default_credentials" {
  count = local.enabled_services.secrets ? 1 : 0
  
  secret_id = local.config_raw.data.credentials.default_secret

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

resource "google_secret_manager_secret" "firebase_credentials" {
  count = local.enabled_services.secrets ? 1 : 0
  
  secret_id = local.config_raw.data.credentials.firebase_secret

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Cloud Build Trigger
resource "google_cloudbuild_trigger" "auto_deploy" {
  count = local.enabled_services.cloud_build ? 1 : 0  # Only create if cloud_build is enabled
  
  name        = local.cloud_build.triggers.auto_deploy.name
  description = local.cloud_build.triggers.auto_deploy.description
  
  github {
    owner = local.cloud_build.triggers.auto_deploy.github.owner
    name  = local.cloud_build.triggers.auto_deploy.github.repository
    push {
      branch = local.cloud_build.triggers.auto_deploy.github.branch
    }
  }

  filename = "cloudbuild.yaml"
  
  substitutions = {
    _PROJECT_ID = local.project_id
    _REGION     = local.region
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Output values
output "function_url" {
  value = local.enabled_services.cloud_functions ? google_cloudfunctions_function.transaction_processor[0].https_trigger_url : null
  description = "URL of the deployed Cloud Function"
}

output "cloud_run_url" {
  value = local.enabled_services.cloud_api ? google_cloud_run_service.transaction_api[0].status[0].url : null
  description = "URL of the deployed Cloud Run service"
}

output "ml_artifacts_bucket" {
  value = local.enabled_services.storage ? google_storage_bucket.ml_artifacts_bucket[0].name : null
  description = "Name of the ML artifacts bucket"
}

output "functions_bucket" {
  value = local.enabled_services.cloud_functions ? google_storage_bucket.functions_bucket[0].name : null
  description = "Name of the functions storage bucket"
}

output "data_export_function_url" {
  value = local.enabled_services.cloud_functions ? google_cloudfunctions_function.data_export_function[0].https_trigger_url : null
  description = "URL of the data export function"
}

output "ml_data_bucket" {
  value = local.enabled_services.storage ? google_storage_bucket.ml_data_bucket[0].name : null
  description = "Name of the ML data bucket for Parquet files"
}

output "bigquery_dataset" {
  value = local.enabled_services.bigquery ? google_bigquery_dataset.transactions[0].dataset_id : null
  description = "BigQuery dataset ID for transactions"
}

output "model_retraining_function" {
  value = local.enabled_services.cloud_functions ? google_cloudfunctions_function.model_retraining[0].name : null
  description = "Model retraining Cloud Function name"
}

output "model_performance_checker_url" {
  value = local.enabled_services.cloud_functions ? google_cloudfunctions_function.model_performance_checker[0].https_trigger_url : null
  description = "Model performance checker HTTP endpoint"
}

output "ml_feedback_table" {
  value = local.enabled_services.bigquery ? google_bigquery_table.ml_feedback[0].table_id : null
  description = "BigQuery table for ML feedback data"
}

# Secret for Cloud Build service account
resource "google_secret_manager_secret" "cloud_build_sa_key" {
  count = local.enabled_services.cloud_build ? 1 : 0
  
  secret_id = local.cloud_build.secrets.service_account_key

  replication {
    auto {}
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Add service account key as a secret version
resource "google_secret_manager_secret_version" "cloud_build_sa_key" {
  count = local.enabled_services.cloud_build ? 1 : 0
  
  secret = google_secret_manager_secret.cloud_build_sa_key[0].id
  secret_data = file("${path.module}/../credentials/service-account-key.json")

  depends_on = [
    google_secret_manager_secret.cloud_build_sa_key
  ]
}

# IAM for Cloud Build
resource "google_project_iam_member" "cloud_build_sa" {
  count = local.enabled_services.cloud_build ? 1 : 0
  
  project = local.project_id
  role    = "roles/cloudbuild.builds.builder"
  member  = "serviceAccount:${local.service_accounts.cloud_build}"

  depends_on = [
    google_project_service.required_apis["cloudbuild.googleapis.com"]
  ]
}

resource "google_project_iam_member" "cloud_build_terraform" {
  count   = local.enabled_services.cloud_build ? 1 : 0
  project = local.project_id
  role    = "roles/editor"
  member  = "serviceAccount:${local.service_accounts.cloud_build}"
}

# Add Secret Manager access for Cloud Build
resource "google_project_iam_member" "cloud_build_secret_accessor" {
  count   = local.enabled_services.cloud_build ? 1 : 0
  project = local.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.service_accounts.cloud_build}"
}

# IAM for Cloud Run service
resource "google_cloud_run_service_iam_member" "cloud_build_invoker" {
  count = local.enabled_services.cloud_api ? 1 : 0
  
  service  = google_cloud_run_service.transaction_api[0].name
  location = local.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.service_accounts.cloud_build}"
  project   = local.project_id
}

# IAM for Cloud Function to access and create secrets
resource "google_project_iam_member" "function_secret_admin" {
  count   = local.enabled_services.cloud_functions && local.enabled_services.secrets ? 1 : 0
  project = local.project_id
  role    = "roles/secretmanager.admin"  # This allows creating secrets and managing their versions
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# Remove all other Secret Manager IAM bindings for the Cloud Function service account
# The admin role above provides all necessary permissions

# Secret Manager IAM for Cloud Build
resource "google_secret_manager_secret_iam_member" "cloud_build_secret_access" {
  count = local.enabled_services.secrets ? 1 : 0
  
  secret_id = google_secret_manager_secret.default_credentials[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${local.service_accounts.cloud_build}"
  project   = local.project_id
}

# IAM binding for Cloud Function to access secrets
resource "google_project_iam_member" "function_secretmanager" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  project = local.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for python-etl service account to access secrets
resource "google_project_iam_member" "python_etl_secretmanager" {
  count = local.enabled_services.secrets ? 1 : 0
  
  project = local.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${local.service_accounts.python_etl}"
}

# IAM binding for Cloud Function to access Firestore/Datastore
resource "google_project_iam_member" "function_datastore" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  project = local.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to publish to Pub/Sub
resource "google_project_iam_member" "function_pubsub_publisher" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  project = local.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to access Vertex AI (for ML predictions)
resource "google_project_iam_member" "function_aiplatform_user" {
  count = local.enabled_services.cloud_functions && local.enabled_services.aiplatform ? 1 : 0
  
  project = local.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to access Vertex AI Model Registry
resource "google_project_iam_member" "function_aiplatform_model_user" {
  count = local.enabled_services.cloud_functions && local.enabled_services.aiplatform ? 1 : 0
  
  project = local.project_id
  role    = "roles/aiplatform.modelUser"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to access Vertex AI Endpoints
resource "google_project_iam_member" "function_aiplatform_endpoint_user" {
  count = local.enabled_services.cloud_functions && local.enabled_services.aiplatform ? 1 : 0
  
  project = local.project_id
  role    = "roles/aiplatform.endpointUser"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to access BigQuery (for ML data operations)
resource "google_project_iam_member" "function_bigquery_user" {
  count = local.enabled_services.cloud_functions && local.enabled_services.bigquery ? 1 : 0
  
  project = local.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to access BigQuery Data Editor (for writing feedback)
resource "google_project_iam_member" "function_bigquery_data_editor" {
  count = local.enabled_services.cloud_functions && local.enabled_services.bigquery ? 1 : 0
  
  project = local.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to access Cloud Storage (for ML artifacts)
resource "google_project_iam_member" "function_storage_object_viewer" {
  count = local.enabled_services.cloud_functions && local.enabled_services.storage ? 1 : 0
  
  project = local.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# IAM binding for Cloud Function to write to Cloud Storage (for ML artifacts)
resource "google_project_iam_member" "function_storage_object_creator" {
  count = local.enabled_services.cloud_functions && local.enabled_services.storage ? 1 : 0
  
  project = local.project_id
  role    = "roles/storage.objectCreator"
  member  = "serviceAccount:${local.project_id}@appspot.gserviceaccount.com"
}

# Note: Individual Gmail credential secrets will be created dynamically by the application
# using the pattern: gmail-credentials-{user_id}-{email} 