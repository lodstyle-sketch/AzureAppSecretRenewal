variable "environment" {
  type    = string
  default = "prod"
}

variable "location" {
  type    = string
  default = "westeurope"
}

variable "resource_prefix" {
  type    = string
  default = "credrenew"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "create_resource_group" {
  type    = bool
  default = true
}

variable "resource_group_name" {
  type    = string
  default = "rg-credential-renewal-prod"
}

variable "internal_api_base_url" {
  type = string
}

variable "mail_shared_mailbox" {
  type = string
}

variable "department_summary_mailbox" {
  type = string
}

variable "webapp_public_base_url" {
  type = string
}

variable "webapp_zip_path" {
  type    = string
  default = "../../../dist/webapp.zip"
}

variable "automation_wheel_path" {
  type    = string
  default = "../../../dist/azure_app_credential_renewal-0.1.0-py3-none-any.whl"
}

variable "application_package_version" {
  type    = string
  default = "0.1.0"
}

variable "automation_dependency_packages" {
  type = map(object({
    content_uri     = string
    content_version = optional(string)
    hash_algorithm  = optional(string)
    hash_value      = optional(string)
  }))
  default = {}
}

variable "enable_cherwell" {
  type    = bool
  default = true
}

variable "enable_graph_app_role_assignments" {
  type    = bool
  default = false
}

variable "cherwell_base_url" {
  type    = string
  default = ""
}

variable "cherwell_token_url" {
  type    = string
  default = ""
}

variable "cherwell_client_id" {
  type    = string
  default = ""
}

variable "cherwell_client_secret" {
  type      = string
  default   = ""
  sensitive = true
}

variable "cherwell_change_template_id" {
  type    = string
  default = ""
}

variable "cherwell_completed_statuses" {
  type    = string
  default = "Closed,Completed,Resolved"
}

variable "scan_schedule" {
  type = object({
    frequency  = string
    interval   = number
    timezone   = string
    start_time = optional(string)
  })
  default = {
    frequency = "Day"
    interval  = 1
    timezone  = "Etc/UTC"
  }
}

variable "cherwell_status_schedule" {
  type = object({
    frequency  = string
    interval   = number
    timezone   = string
    start_time = optional(string)
  })
  default = {
    frequency = "Hour"
    interval  = 1
    timezone  = "Etc/UTC"
  }
}

variable "reporting_export_schedule" {
  type = object({
    frequency  = string
    interval   = number
    timezone   = string
    start_time = optional(string)
  })
  default = {
    frequency = "Hour"
    interval  = 1
    timezone  = "Etc/UTC"
  }
}
