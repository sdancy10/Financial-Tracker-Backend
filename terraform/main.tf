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
    "firestore.googleapis.com"
  ])
  
  service = each.key
  disable_on_destroy = false
}

# Cloud Storage bucket for ML artifacts
resource "google_storage_bucket" "ml_artifacts" {
  name     = "${local.config.project.id}-${local.config.project.bucket_name}"
  location = local.config.project.region
}

# Create Pub/Sub topic
resource "google_pubsub_topic" "email_notifications" {
  name = "email-notifications"
}

# Create Pub/Sub subscription
resource "google_pubsub_subscription" "email_processing" {
  name  = "email-processing"
  topic = google_pubsub_topic.email_notifications.name
}

# Cloud Run service
resource "google_cloud_run_service" "transaction_api" {
  name     = local.config.cloud_run.service_name
  location = local.config.project.region

  template {
    spec {
      containers {
        image = local.config.cloud_run.container_image
      }
    }
  }
} 