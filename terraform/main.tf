provider "google" {
  project = "shanedancy-9f2a3"
  region  = "us-central1"
  credentials = "${path.module}/../credentials/service-account-key.json"
}

locals {
  use_free_tier = try(local.config.project.use_free_tier, false)
  
  # Get enabled services from config
  enabled_services = try(local.config.features.enabled_services, {
    cloud_api: false,
    cloud_functions: true,
    storage: true,
    pubsub: true,
    scheduler: true,
    firestore: true,
    secrets: true
  })

  # Map of APIs to their feature flags
  api_service_map = {
    "cloudrun.googleapis.com": local.enabled_services.cloud_api,
    "cloudfunctions.googleapis.com": local.enabled_services.cloud_functions,
    "storage.googleapis.com": local.enabled_services.storage,
    "containerregistry.googleapis.com": local.enabled_services.cloud_api || local.enabled_services.cloud_functions,
    "cloudbuild.googleapis.com": local.enabled_services.cloud_api || local.enabled_services.cloud_functions,
    "pubsub.googleapis.com": local.enabled_services.pubsub,
    "firestore.googleapis.com": local.enabled_services.firestore,
    "secretmanager.googleapis.com": local.enabled_services.secrets,
    "cloudscheduler.googleapis.com": local.enabled_services.scheduler,
    "aiplatform.googleapis.com": true  # Always enabled for future ML features
  }

  # Filter to only enabled APIs
  enabled_apis = {
    for api, enabled in local.api_service_map:
    api => enabled if enabled
  }
  
  # Resource configurations based on tier
  resource_config = {
    cloud_function = local.use_free_tier ? {
      memory    = 128  # 128MB is in free tier
      timeout   = 60   # 60 seconds
      schedule  = "0 */12 * * *"  # Every 12 hours for free tier
      retries   = 1
    } : {
      memory    = 256
      timeout   = local.config.cloud_function.timeout
      schedule  = local.config.scheduler.transaction_sync.schedule
      retries   = local.config.scheduler.transaction_sync.retry_count
    }
    cloud_run = local.use_free_tier ? {
      memory        = "128Mi"  # 128MB
      cpu          = "0.1"    # 0.1 vCPU
      min_instances = 0       # Scale to zero
      max_instances = 1       # Max 1 instance
    } : {
      memory        = "256Mi"
      cpu          = "1000m"
      min_instances = local.config.cloud_run.min_instances
      max_instances = local.config.cloud_run.max_instances
    }
    storage = local.use_free_tier ? {
      location = "US"  # Multi-region US for free tier
      lifecycle_age = 30  # Auto-delete after 30 days
    } : {
      location = local.config.project.region
      lifecycle_age = null  # No auto-deletion
    }
  }
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
  
  name     = local.config.storage.buckets.ml_artifacts
  location = local.resource_config.storage.location
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "functions_bucket" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name     = local.config.storage.buckets.functions
  location = local.resource_config.storage.location
  uniform_bucket_level_access = true
}

# Pub/Sub topic for transaction processing
resource "google_pubsub_topic" "transaction_topic" {
  count = local.enabled_services.pubsub ? 1 : 0
  
  name = "scheduled-transactions"
}

# Cloud Function
resource "google_cloudfunctions_function" "transaction_processor" {
  count = local.enabled_services.cloud_functions ? 1 : 0
  
  name        = local.config.cloud_function.name
  description = "Processes financial transactions"
  runtime     = local.config.cloud_function.runtime

  available_memory_mb   = local.resource_config.cloud_function.memory
  source_archive_bucket = google_storage_bucket.functions_bucket[0].name
  source_archive_object = "function-source.zip"
  entry_point          = local.config.cloud_function.entry_point
  timeout             = local.resource_config.cloud_function.timeout

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.transaction_topic[0].name
  }

  environment_variables = {
    for key, value in local.config.cloud_function.environment_variables:
    key => replace(replace(value, "${project.id}", local.config.project.id), "${project.use_free_tier ? \"free_tier\" : \"standard\"}", local.use_free_tier ? "free_tier" : "standard")
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

# Cloud Scheduler job
resource "google_cloud_scheduler_job" "transaction_scheduler" {
  count = local.enabled_services.scheduler ? 1 : 0
  
  name             = "process-scheduled-transactions"
  description      = "Triggers transaction processing on a schedule"
  schedule         = local.resource_config.cloud_function.schedule
  time_zone        = local.config.scheduler.transaction_sync.timezone
  attempt_deadline = "${local.resource_config.cloud_function.timeout}s"

  retry_config {
    retry_count = local.resource_config.cloud_function.retries
    min_backoff_duration = "${local.config.scheduler.transaction_sync.retry_interval}s"
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
  
  name     = local.config.cloud_run.service_name
  location = local.config.project.region

  template {
    spec {
      containers {
        image = local.config.cloud_run.container_image
        resources {
          limits = {
            cpu    = local.resource_config.cloud_run.cpu
            memory = local.resource_config.cloud_run.memory
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
  location = google_cloud_run_service.transaction_api[0].location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Secret Manager secrets
resource "google_secret_manager_secret" "default_credentials" {
  count = local.enabled_services.secrets ? 1 : 0
  
  secret_id = local.config.data.credentials.default_secret

  replication {
    user_managed {
      replicas {
        location = local.config.project.region
      }
    }
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

resource "google_secret_manager_secret" "firebase_credentials" {
  count = local.enabled_services.secrets ? 1 : 0
  
  secret_id = local.config.data.credentials.firebase_secret

  replication {
    user_managed {
      replicas {
        location = local.config.project.region
      }
    }
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