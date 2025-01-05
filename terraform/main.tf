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
    user_managed {
      replicas {
        location = local.region
      }
    }
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

  environment_variables = merge(
    local.processed_env_vars,
    {
      PROJECT_ID = local.project_id
      REGION     = local.region
    }
  )

  depends_on = [
    google_project_service.required_apis
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
    user_managed {
      replicas {
        location = local.region
      }
    }
  }

  depends_on = [
    google_project_service.required_apis
  ]
}

resource "google_secret_manager_secret" "firebase_credentials" {
  count = local.enabled_services.secrets ? 1 : 0
  
  secret_id = local.config_raw.data.credentials.firebase_secret

  replication {
    user_managed {
      replicas {
        location = local.region
      }
    }
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

# Secret for Cloud Build service account
resource "google_secret_manager_secret" "cloud_build_sa_key" {
  count = local.enabled_services.cloud_build ? 1 : 0
  
  secret_id = local.cloud_build.secrets.service_account_key

  replication {
    user_managed {
      replicas {
        location = local.region
      }
    }
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

# Note: Individual Gmail credential secrets will be created dynamically by the application
# using the pattern: gmail-credentials-{user_id}-{email} 