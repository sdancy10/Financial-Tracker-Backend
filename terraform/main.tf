locals {
  config = yamldecode(file("${path.module}/../config.yaml"))
}

provider "google" {
  project = local.config.project.id
  region  = local.config.project.region
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
    "containerregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudrun.googleapis.com",
    "pubsub.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudscheduler.googleapis.com"
  ])
  
  service = each.key
  disable_on_destroy = false
}

# Storage buckets
resource "google_storage_bucket" "data_bucket" {
  name     = local.config.storage.buckets.data
  location = local.config.project.region
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "ml_artifacts_bucket" {
  name     = local.config.storage.buckets.ml_artifacts
  location = local.config.project.region
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "functions_bucket" {
  name     = local.config.storage.buckets.functions
  location = local.config.project.region
  uniform_bucket_level_access = true
}

# Pub/Sub topic for transaction processing
resource "google_pubsub_topic" "transaction_topic" {
  name = "scheduled-transactions"
}

# Cloud Function
resource "google_cloudfunctions_function" "transaction_processor" {
  name        = local.config.cloud_function.name
  description = "Processes financial transactions"
  runtime     = local.config.cloud_function.runtime

  available_memory_mb   = 256
  source_archive_bucket = google_storage_bucket.functions_bucket.name
  source_archive_object = "function-source.zip"
  entry_point          = local.config.cloud_function.entry_point
  timeout             = local.config.cloud_function.timeout

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.transaction_topic.name
  }

  environment_variables = {
    GOOGLE_CLOUD_PROJECT = local.config.project.id
    CONFIG_PATH         = "config.yaml"
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Cloud Scheduler job
resource "google_cloud_scheduler_job" "transaction_scheduler" {
  name             = "process-scheduled-transactions"
  description      = "Triggers transaction processing on a schedule"
  schedule         = local.config.scheduler.transaction_sync.schedule
  time_zone        = local.config.scheduler.transaction_sync.timezone
  attempt_deadline = "${local.config.scheduler.transaction_sync.timeout}s"

  retry_config {
    retry_count = local.config.scheduler.transaction_sync.retry_count
    min_backoff_duration = "${local.config.scheduler.transaction_sync.retry_interval}s"
  }

  pubsub_target {
    topic_name = google_pubsub_topic.transaction_topic.id
    data       = base64encode("{}")
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Cloud Run service
resource "google_cloud_run_service" "transaction_api" {
  name     = local.config.cloud_run.service_name
  location = local.config.project.region

  template {
    spec {
      containers {
        image = local.config.cloud_run.container_image
        resources {
          limits = {
            cpu    = "1000m"
            memory = "256Mi"
          }
        }
        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = local.config.project.id
        }
        env {
          name  = "CONFIG_PATH"
          value = "config.yaml"
        }
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
  service  = google_cloud_run_service.transaction_api.name
  location = google_cloud_run_service.transaction_api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "default_credentials" {
  secret_id = local.config.data.credentials.default_secret

  replication {
    automatic = true
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

resource "google_secret_manager_secret" "firebase_credentials" {
  secret_id = local.config.data.credentials.firebase_secret

  replication {
    automatic = true
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Output values
output "function_url" {
  value = google_cloudfunctions_function.transaction_processor.https_trigger_url
  description = "URL of the deployed Cloud Function"
}

output "cloud_run_url" {
  value = google_cloud_run_service.transaction_api.status[0].url
  description = "URL of the deployed Cloud Run service"
}

output "data_bucket" {
  value = google_storage_bucket.data_bucket.name
  description = "Name of the data storage bucket"
}

output "ml_artifacts_bucket" {
  value = google_storage_bucket.ml_artifacts_bucket.name
  description = "Name of the ML artifacts bucket"
}

output "functions_bucket" {
  value = google_storage_bucket.functions_bucket.name
  description = "Name of the functions storage bucket"
} 