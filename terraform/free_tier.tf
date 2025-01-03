# Free tier configuration - uses same config.yaml but with resource constraints
locals {
  config = yamldecode(file("${path.module}/../config.yaml"))
}

# Enable required APIs (same as main.tf as API enablement is free)
resource "google_project_service" "free_tier_apis" {
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

# Storage buckets with free tier constraints
resource "google_storage_bucket" "free_tier_buckets" {
  for_each = {
    data = "${local.config.storage.buckets.data}-free"
    ml_artifacts = "${local.config.storage.buckets.ml_artifacts}-free"
    functions = "${local.config.storage.buckets.functions}-free"
  }

  name     = each.value
  location = local.config.project.region
  
  # Enable uniform bucket-level access
  uniform_bucket_level_access = true
  
  # Force deletion of bucket contents on destroy
  force_destroy = true
  
  # Lifecycle rules to manage storage costs
  lifecycle_rule {
    condition {
      age = 1  # Delete files after 1 day
    }
    action {
      type = "Delete"
    }
  }

  # Storage quota to stay within free tier (5GB total across all buckets)
  quota {
    metric = "STORAGE_BYTES"
    limit  = "1073741824"  # 1GB per bucket
  }
}

# Pub/Sub topic with minimal configuration
resource "google_pubsub_topic" "free_tier_topic" {
  name = "scheduled-transactions-free"
}

# Cloud Function with free tier constraints
resource "google_cloudfunctions_function" "free_tier_function" {
  name        = "${local.config.cloud_function.name}-free"
  description = "Free tier version of transaction processor"
  runtime     = local.config.cloud_function.runtime

  # Minimal memory allocation
  available_memory_mb   = 128
  source_archive_bucket = google_storage_bucket.free_tier_buckets["functions"].name
  source_archive_object = "function-source.zip"
  entry_point          = local.config.cloud_function.entry_point
  
  # Reduced timeout to minimize resource usage
  timeout             = 60  # 1 minute timeout

  event_trigger {
    event_type = "google.pubsub.topic.publish"
    resource   = google_pubsub_topic.free_tier_topic.name
  }

  environment_variables = {
    GOOGLE_CLOUD_PROJECT = local.config.project.id
    CONFIG_PATH         = "config.yaml"
    ENVIRONMENT         = "free_tier"
  }

  depends_on = [
    google_project_service.free_tier_apis
  ]
}

# Cloud Scheduler with reduced frequency
resource "google_cloud_scheduler_job" "free_tier_scheduler" {
  name             = "process-scheduled-transactions-free"
  description      = "Free tier version of transaction scheduler"
  schedule         = "0 */12 * * *"  # Run every 12 hours instead of every 10 minutes
  time_zone        = local.config.scheduler.transaction_sync.timezone
  attempt_deadline = "60s"  # Match function timeout

  retry_config {
    retry_count = 1
    min_backoff_duration = "10s"
  }

  pubsub_target {
    topic_name = google_pubsub_topic.free_tier_topic.id
    data       = base64encode("{}")
  }

  depends_on = [
    google_project_service.free_tier_apis
  ]
}

# Cloud Run service with free tier constraints
resource "google_cloud_run_service" "free_tier_api" {
  name     = "${local.config.cloud_run.service_name}-free"
  location = local.config.project.region

  template {
    spec {
      containers {
        image = local.config.cloud_run.container_image
        
        # Minimal resource allocation
        resources {
          limits = {
            cpu    = "1000m"
            memory = "128Mi"
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
          value = "free_tier"
        }
      }
    }
  }

  # Allow scale to zero
  metadata {
    annotations = {
      "autoscaling.knative.dev/maxScale" = "1"
      "autoscaling.knative.dev/minScale" = "0"
    }
  }

  depends_on = [
    google_project_service.free_tier_apis
  ]
}

# IAM for Cloud Run (minimal public access)
resource "google_cloud_run_service_iam_member" "free_tier_public_access" {
  service  = google_cloud_run_service.free_tier_api.name
  location = google_cloud_run_service.free_tier_api.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Secret Manager secrets (minimal set)
resource "google_secret_manager_secret" "free_tier_credentials" {
  secret_id = "${local.config.data.credentials.default_secret}-free"

  replication {
    automatic = true
  }

  depends_on = [
    google_project_service.free_tier_apis
  ]
}

# Budget alert to prevent exceeding free tier
resource "google_billing_budget" "free_tier_budget" {
  billing_account = "000000-000000-000000"  # Replace with your billing account ID
  display_name    = "Free Tier Budget"
  
  amount {
    specified_amount {
      currency_code = "USD"
      units        = "1"  # $1 maximum budget
    }
  }

  threshold_rules {
    threshold_percent = 0.5  # Alert at 50 cents
  }
  threshold_rules {
    threshold_percent = 0.9  # Alert at 90 cents
  }

  all_updates_rule {
    monitoring_notification_channels = []
    disable_default_iam_recipients = true
  }
}

# Outputs
output "free_tier_function_url" {
  value = google_cloudfunctions_function.free_tier_function.https_trigger_url
  description = "URL of the free tier Cloud Function"
}

output "free_tier_cloud_run_url" {
  value = google_cloud_run_service.free_tier_api.status[0].url
  description = "URL of the free tier Cloud Run service"
}

output "free_tier_buckets" {
  value = {
    for k, v in google_storage_bucket.free_tier_buckets : k => v.name
  }
  description = "Names of the free tier storage buckets"
} 