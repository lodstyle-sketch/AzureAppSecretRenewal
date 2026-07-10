variable "location" {
  description = "Azure region for the Terraform state resources."
  type        = string
}

variable "resource_group_name" {
  description = "Resource group that stores the Terraform state backend."
  type        = string
}

variable "storage_account_name" {
  description = "Globally unique Storage Account name for Terraform state."
  type        = string
}

variable "container_name" {
  description = "Blob container name for Terraform state files."
  type        = string
  default     = "tfstate"
}

variable "tags" {
  description = "Tags applied to Terraform state resources."
  type        = map(string)
  default     = {}
}
