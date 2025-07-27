locals {
  # Base config from YAML
  config_raw = yamldecode(file("${path.module}/../config.yaml"))

  # Gmail credentials from individual user credential files
  gmail_user_credentials = {
    for account_key, account in local.config_raw.auth.gmail.accounts : account_key => jsondecode(file("${path.module}/../${account.credentials_file}"))
  }

  # Direct access to common config sections
  gcp = local.config_raw.gcp
  project_id = local.gcp.project_id
  region = local.gcp.region
  
  # Features and services
  features = local.config_raw.features
  enabled_services = local.features.enabled_services
  use_free_tier = try(local.features.use_free_tier, false)
  tier_string = local.use_free_tier ? "free_tier" : "standard"

  # Storage configuration with replacements
  storage = {
    location = local.config_raw.storage.location
    buckets = {
      data = replace(local.config_raw.storage.buckets.data, "%PROJECT_ID%", local.project_id)
      ml_artifacts = replace(local.config_raw.storage.buckets.ml_artifacts, "%PROJECT_ID%", local.project_id)
      functions = replace(local.config_raw.storage.buckets.functions, "%PROJECT_ID%", local.project_id)
    }
  }

  # Cloud Function configuration with replacements
  cloud_function = merge(local.config_raw.cloud_function, {
    source_path = replace(local.config_raw.cloud_function.source_path, "%PROJECT_ID%", local.project_id)
  })
  
  # Cloud Run configuration with replacements
  cloud_run = merge(local.config_raw.cloud_run, {
    container_image = replace(local.config_raw.cloud_run.container_image, "%PROJECT_ID%", local.project_id)
  })

  # Pub/Sub configuration
  pubsub = local.config_raw.pubsub

  # Scheduler configuration
  scheduler = merge(local.config_raw.scheduler, {
    jobs = local.config_raw.scheduler.jobs
  })

  # Cloud Build configuration
  cloud_build = local.config_raw.cloud_build

  # Service accounts (keeping existing logic)
  service_accounts = {
    cloud_build = "${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
    app_engine = "${local.project_id}@appspot.gserviceaccount.com"
    python_etl = "python-etl@${local.project_id}.iam.gserviceaccount.com"
  }

  # API mappings (keeping existing logic)
  api_service_map = {
    "cloudrun.googleapis.com": local.enabled_services.cloud_api,
    "cloudfunctions.googleapis.com": local.enabled_services.cloud_functions,
    "storage.googleapis.com": local.enabled_services.storage,
    "containerregistry.googleapis.com": local.enabled_services.cloud_api || local.enabled_services.cloud_functions,
    "cloudbuild.googleapis.com": local.enabled_services.cloud_api || local.enabled_services.cloud_functions || local.enabled_services.cloud_build,
    "pubsub.googleapis.com": local.enabled_services.pubsub,
    "firestore.googleapis.com": local.enabled_services.firestore,
    "secretmanager.googleapis.com": local.enabled_services.secrets,
    "cloudscheduler.googleapis.com": local.enabled_services.scheduler,
    "aiplatform.googleapis.com": true,
    "bigquery.googleapis.com": true,
    "monitoring.googleapis.com": true
  }

  # Filter to only enabled APIs (keeping existing logic)
  enabled_apis = {
    for api, enabled in local.api_service_map:
    api => enabled if enabled
  }

  # Resource configurations based on tier (keeping existing logic)
  resource_config = {
    cloud_function = local.use_free_tier ? {
      memory    = 128
      timeout   = 60
      schedule  = "0 */12 * * *"
      retries   = 1
    } : {
      memory    = try(local.cloud_function.memory, 256)  # Use config.yaml memory or default to 256
      timeout   = local.cloud_function.timeout
      schedule  = local.scheduler.transaction_sync.schedule
      retries   = local.scheduler.transaction_sync.retry_count
    }
    cloud_run = local.use_free_tier ? {
      memory        = "128Mi"
      cpu          = "0.1"
      min_instances = 0
      max_instances = 1
    } : {
      memory        = "256Mi"
      cpu          = "1000m"
      min_instances = local.cloud_run.min_instances
      max_instances = local.cloud_run.max_instances
    }
    storage = local.use_free_tier ? {
      location = "US"
      lifecycle_age = 30
    } : {
      location = local.region
      lifecycle_age = null
    }
  }

  # Environment variables with replacements
  processed_env_vars = {
    for key, value in local.cloud_function.environment_variables :
    key => replace(
      replace(
        replace(
          value,
          "%PROJECT_ID%",
          local.project_id
        ),
        "%PROJECT_TIER%",
        local.tier_string
      ),
      "%REGION%",
      local.region
    )
  }
}

