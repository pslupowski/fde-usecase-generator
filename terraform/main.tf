terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ---------------------------------------------------------------------------
# 1. Enable Required Google Cloud APIs
# ---------------------------------------------------------------------------
locals {
  services = [
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "firestore.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudtrace.googleapis.com",
    "logging.googleapis.com",
    "dlp.googleapis.com",
  ]
}

resource "google_project_service" "enabled_apis" {
  for_each           = toset(locals.services)
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# 2. Service Account with Principle of Least Privilege
# ---------------------------------------------------------------------------
resource "google_service_account" "fde_agent_sa" {
  project      = var.project_id
  account_id   = "fde-agent-sa"
  display_name = "Forward Deployed AI Engineer Agent Service Account"
  description  = "Dedicated identity for FDE Multi-Agent system executing on Cloud Run"
  depends_on   = [google_project_service.enabled_apis]
}

locals {
  sa_roles = [
    "roles/secretmanager.secretAccessor",
    "roles/datastore.user",              # Firestore Native access
    "roles/logging.logWriter",           # Structured JSON logging
    "roles/cloudtrace.agent",            # OpenTelemetry distributed tracing
    "roles/aiplatform.user",             # Vertex AI Gemini 2.5 access
  ]
}

resource "google_project_iam_member" "sa_role_bindings" {
  for_each = toset(locals.sa_roles)
  project  = var.project_id
  role     = each.key
  member   = "serviceAccount:${google_service_account.fde_agent_sa.email}"
}

# ---------------------------------------------------------------------------
# 3. Google Cloud Secret Manager for GEMINI_API_KEY
# ---------------------------------------------------------------------------
resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = "GEMINI_API_KEY"

  replication {
    auto {}
  }

  labels = {
    managed-by = "terraform"
    workload   = "fde-agent-system"
  }

  depends_on = [google_project_service.enabled_apis]
}

# ---------------------------------------------------------------------------
# 4. Google Cloud Firestore Database (Native Mode)
# ---------------------------------------------------------------------------
resource "google_firestore_database" "fde_database" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.firestore_region
  type        = "FIRESTORE_NATIVE"

  concurrency_mode                = "OPTIMISTIC"
  app_engine_integration_mode     = "DISABLED"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED"
  delete_protection_state         = "DELETE_PROTECTION_ENABLED"
  deletion_policy                 = "ABANDON"

  depends_on = [google_project_service.enabled_apis]
}

# ---------------------------------------------------------------------------
# 5. Google Cloud Run Service (Serverless Agent Engine)
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "fde_service" {
  project  = var.project_id
  name     = var.service_name
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.fde_agent_sa.email

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }

      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "ENVIRONMENT"
        value = "production"
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      # Mount GEMINI_API_KEY directly from Secret Manager securely
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      startup_probe {
        timeout_seconds   = 240
        period_seconds    = 10
        failure_threshold = 3
        tcp_socket {
          port = 8080
        }
      }

      liveness_probe {
        period_seconds = 30
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.enabled_apis,
    google_project_iam_member.sa_role_bindings,
    google_secret_manager_secret.gemini_api_key,
    google_firestore_database.fde_database,
  ]
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------
output "cloud_run_service_uri" {
  description = "The deployed Cloud Run service URL"
  value       = google_cloud_run_v2_service.fde_service.uri
}

output "service_account_email" {
  description = "The dedicated service account email for the agent"
  value       = google_service_account.fde_agent_sa.email
}

output "firestore_database_name" {
  description = "The Firestore database name"
  value       = google_firestore_database.fde_database.name
}

output "secret_manager_name" {
  description = "The secret ID created in Secret Manager"
  value       = google_secret_manager_secret.gemini_api_key.secret_id
}
