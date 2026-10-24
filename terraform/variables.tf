variable "project_id" {
  type        = string
  description = "The target Google Cloud Project ID"
  default     = "patrice-fde-agent-l200"
}

variable "region" {
  type        = string
  description = "The primary Google Cloud deployment region"
  default     = "us-central1"
}

variable "firestore_region" {
  type        = string
  description = "The location for Cloud Firestore Database"
  default     = "nam5" # US multi-region
}

variable "service_name" {
  type        = string
  description = "The name of the Cloud Run microservice"
  default     = "fde-template-generator"
}

variable "container_image" {
  type        = string
  description = "Container image URL to deploy on Cloud Run"
  default     = "us-central1-docker.pkg.dev/patrice-fde-agent-l200/fde-agents/template-generator:latest"
}

variable "min_instances" {
  type        = number
  description = "Minimum running container instances for Cloud Run (0 for scale-to-zero)"
  default     = 0
}

variable "max_instances" {
  type        = number
  description = "Maximum running container instances for Cloud Run autoscaling"
  default     = 10
}
