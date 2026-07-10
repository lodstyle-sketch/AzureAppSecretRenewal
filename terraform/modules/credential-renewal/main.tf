data "azurerm_client_config" "current" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

resource "random_password" "link_signing_key" {
  length  = 48
  special = true
}

resource "time_offset" "package_sas_expiry" {
  offset_years = 5
}

resource "time_static" "package_sas_start" {}

resource "azurerm_resource_group" "main" {
  count    = var.create_resource_group ? 1 : 0
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

data "azurerm_resource_group" "main" {
  count = var.create_resource_group ? 0 : 1
  name  = var.resource_group_name
}

resource "azurerm_storage_account" "artifacts" {
  name                            = substr("${replace(local.name_prefix, "-", "")}art${random_string.suffix.result}", 0, 24)
  resource_group_name             = local.resource_group_name
  location                        = local.resource_group_location
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_storage_container" "automation_packages" {
  name                  = "automation-packages"
  storage_account_id    = azurerm_storage_account.artifacts.id
  container_access_type = "private"
}

resource "azurerm_storage_blob" "automation_wheel" {
  name                   = basename(var.automation_wheel_path)
  storage_account_name   = azurerm_storage_account.artifacts.name
  storage_container_name = azurerm_storage_container.automation_packages.name
  type                   = "Block"
  source                 = var.automation_wheel_path
  content_md5            = filemd5(var.automation_wheel_path)
}

data "azurerm_storage_account_sas" "automation_packages" {
  connection_string = azurerm_storage_account.artifacts.primary_connection_string
  https_only        = true
  start             = time_static.package_sas_start.rfc3339
  expiry            = time_offset.package_sas_expiry.rfc3339

  resource_types {
    service   = false
    container = false
    object    = true
  }

  services {
    blob  = true
    queue = false
    table = false
    file  = false
  }

  permissions {
    read    = true
    list    = false
    add     = false
    create  = false
    write   = false
    delete  = false
    update  = false
    process = false
    tag     = false
    filter  = false
  }
}

resource "azurerm_key_vault" "main" {
  name                       = substr("${local.name_prefix}-kv-${random_string.suffix.result}", 0, 24)
  resource_group_name        = local.resource_group_name
  location                   = local.resource_group_location
  tenant_id                  = var.tenant_id
  sku_name                   = "standard"
  enable_rbac_authorization  = true
  purge_protection_enabled   = true
  soft_delete_retention_days = 30
  tags                       = local.tags
}

resource "azurerm_role_assignment" "current_key_vault_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_key_vault_secret" "link_signing_key" {
  name         = "link-signing-key"
  value        = random_password.link_signing_key.result
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.current_key_vault_secrets_officer]
}

resource "azurerm_key_vault_secret" "cherwell_client_secret" {
  count        = var.enable_cherwell && var.cherwell_client_secret != "" ? 1 : 0
  name         = "cherwell-client-secret"
  value        = var.cherwell_client_secret
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.current_key_vault_secrets_officer]
}

resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.name_prefix}-law-${random_string.suffix.result}"
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  sku                 = "PerGB2018"
  retention_in_days   = var.log_analytics_retention_days
  tags                = local.tags
}

resource "azurerm_monitor_data_collection_endpoint" "main" {
  name                = "${local.name_prefix}-dce-${random_string.suffix.result}"
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  kind                = "Linux"
  tags                = local.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "azurerm_monitor_data_collection_rule" "main" {
  name                        = "${local.name_prefix}-dcr-${random_string.suffix.result}"
  resource_group_name         = local.resource_group_name
  location                    = local.resource_group_location
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.main.id
  tags                        = local.tags

  destinations {
    log_analytics {
      workspace_resource_id = azurerm_log_analytics_workspace.main.id
      name                  = "credential-renewal-log-analytics"
    }
  }

  data_flow {
    streams       = [local.cases_stream_name]
    destinations  = ["credential-renewal-log-analytics"]
    output_stream = local.cases_stream_name
    transform_kql = local.cases_transform
  }

  data_flow {
    streams       = [local.overview_stream_name]
    destinations  = ["credential-renewal-log-analytics"]
    output_stream = local.overview_stream_name
    transform_kql = local.overview_transform
  }

  data_flow {
    streams       = [local.archive_stream_name]
    destinations  = ["credential-renewal-log-analytics"]
    output_stream = local.archive_stream_name
    transform_kql = local.archive_transform
  }

  stream_declaration {
    stream_name = local.cases_stream_name

    dynamic "column" {
      for_each = local.cases_stream_columns
      content {
        name = column.key
        type = column.value
      }
    }
  }

  stream_declaration {
    stream_name = local.overview_stream_name

    dynamic "column" {
      for_each = local.overview_stream_columns
      content {
        name = column.key
        type = column.value
      }
    }
  }

  stream_declaration {
    stream_name = local.archive_stream_name

    dynamic "column" {
      for_each = local.archive_stream_columns
      content {
        name = column.key
        type = column.value
      }
    }
  }
}

resource "azurerm_cosmosdb_account" "main" {
  name                = substr("${local.name_prefix}-cosmos-${random_string.suffix.result}", 0, 44)
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"
  tags                = local.tags

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = local.resource_group_location
    failover_priority = 0
  }
}

resource "azurerm_cosmosdb_sql_database" "main" {
  name                = var.cosmos_database_name
  resource_group_name = local.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
}

resource "azurerm_cosmosdb_sql_container" "cases" {
  name                = var.cosmos_cases_container_name
  resource_group_name = local.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = local.cosmos_partition_key_paths
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "overview" {
  name                = var.cosmos_overview_container_name
  resource_group_name = local.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = local.cosmos_partition_key_paths
  throughput          = 400
}

resource "azurerm_cosmosdb_sql_container" "archive" {
  name                = var.cosmos_archive_container_name
  resource_group_name = local.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.main.name
  partition_key_paths = local.cosmos_partition_key_paths
  throughput          = 400
}

resource "azurerm_service_plan" "web" {
  name                = "${local.name_prefix}-asp-${random_string.suffix.result}"
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  os_type             = "Linux"
  sku_name            = var.app_service_plan_sku
  tags                = local.tags
}

resource "azuread_application" "web_auth" {
  display_name     = "${local.name_prefix}-web-auth"
  sign_in_audience = "AzureADMyOrg"

  web {
    redirect_uris = ["${trim(var.webapp_public_base_url, "/")}/.auth/login/aad/callback"]
  }
}

resource "azuread_service_principal" "web_auth" {
  client_id = azuread_application.web_auth.client_id
}

resource "azuread_application_password" "web_auth" {
  application_id = azuread_application.web_auth.id
  display_name   = "app-service-auth"
  end_date_relative = "8760h"
}

resource "azurerm_linux_web_app" "web" {
  name                = "${local.name_prefix}-web-${random_string.suffix.result}"
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  service_plan_id     = azurerm_service_plan.web.id
  https_only          = true
  zip_deploy_file     = var.webapp_zip_path
  app_settings        = local.web_app_settings
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }

  site_config {
    always_on           = true
    minimum_tls_version = "1.2"

    application_stack {
      python_version = "3.11"
    }
  }

  auth_settings_v2 {
    auth_enabled           = true
    require_authentication = true
    unauthenticated_action = "RedirectToLoginPage"
    default_provider       = "azureactivedirectory"
    require_https          = true

    active_directory_v2 {
      client_id                  = azuread_application.web_auth.client_id
      tenant_auth_endpoint       = "https://login.microsoftonline.com/${var.tenant_id}/v2.0/"
      client_secret_setting_name = "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET"
    }

    login {
      token_store_enabled = false
    }
  }
}

resource "azurerm_automation_account" "main" {
  name                = "${local.name_prefix}-aa-${random_string.suffix.result}"
  resource_group_name = local.resource_group_name
  location            = local.resource_group_location
  sku_name            = "Basic"
  tags                = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_automation_python3_package" "application" {
  name                    = "azure-app-credential-renewal"
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  content_uri             = "${azurerm_storage_blob.automation_wheel.url}${data.azurerm_storage_account_sas.automation_packages.sas}"
  content_version         = var.application_package_version
}

resource "azurerm_automation_python3_package" "dependencies" {
  for_each                = var.automation_dependency_packages
  name                    = each.key
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  content_uri             = each.value.content_uri
  content_version         = each.value.content_version
  hash_algorithm          = each.value.hash_algorithm
  hash_value              = each.value.hash_value
}

resource "azurerm_automation_variable_string" "settings" {
  for_each                = local.automation_variables
  name                    = each.key
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  value                   = each.value
  encrypted               = false
}

resource "azurerm_automation_runbook" "scan" {
  name                    = "Scan-App-Registration-Credentials"
  location                = local.resource_group_location
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  log_verbose             = true
  log_progress            = true
  description             = "Scans App Registration credentials and creates renewal cases."
  runbook_type            = "Python3"
  content                 = file("${path.module}/../../runbooks/scan.py")
  tags                    = local.tags

  depends_on = [azurerm_automation_python3_package.application]
}

resource "azurerm_automation_runbook" "reporting_export" {
  name                    = "Export-Credential-Renewal-Reporting"
  location                = local.resource_group_location
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  log_verbose             = true
  log_progress            = true
  description             = "Exports Cosmos case, overview, and archive data to Log Analytics."
  runbook_type            = "Python3"
  content                 = file("${path.module}/../../runbooks/reporting_export.py")
  tags                    = local.tags

  depends_on = [azurerm_automation_python3_package.application]
}

resource "azurerm_automation_runbook" "cherwell_status" {
  count                   = var.enable_cherwell ? 1 : 0
  name                    = "Poll-Cherwell-Credential-Changes"
  location                = local.resource_group_location
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  log_verbose             = true
  log_progress            = true
  description             = "Polls Cherwell Changes and removes old secrets after Change completion."
  runbook_type            = "Python3"
  content                 = file("${path.module}/../../runbooks/cherwell_status.py")
  tags                    = local.tags

  depends_on = [azurerm_automation_python3_package.application]
}

resource "azurerm_automation_schedule" "scan" {
  name                    = "scan-app-registration-credentials"
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  frequency               = var.scan_schedule.frequency
  interval                = var.scan_schedule.interval
  timezone                = var.scan_schedule.timezone
  start_time              = try(var.scan_schedule.start_time, null)
}

resource "azurerm_automation_schedule" "reporting_export" {
  name                    = "export-credential-renewal-reporting"
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  frequency               = var.reporting_export_schedule.frequency
  interval                = var.reporting_export_schedule.interval
  timezone                = var.reporting_export_schedule.timezone
  start_time              = try(var.reporting_export_schedule.start_time, null)
}

resource "azurerm_automation_schedule" "cherwell_status" {
  count                   = var.enable_cherwell ? 1 : 0
  name                    = "poll-cherwell-credential-changes"
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  frequency               = var.cherwell_status_schedule.frequency
  interval                = var.cherwell_status_schedule.interval
  timezone                = var.cherwell_status_schedule.timezone
  start_time              = try(var.cherwell_status_schedule.start_time, null)
}

resource "azurerm_automation_job_schedule" "scan" {
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  schedule_name           = azurerm_automation_schedule.scan.name
  runbook_name            = azurerm_automation_runbook.scan.name
}

resource "azurerm_automation_job_schedule" "reporting_export" {
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  schedule_name           = azurerm_automation_schedule.reporting_export.name
  runbook_name            = azurerm_automation_runbook.reporting_export.name
}

resource "azurerm_automation_job_schedule" "cherwell_status" {
  count                   = var.enable_cherwell ? 1 : 0
  resource_group_name     = local.resource_group_name
  automation_account_name = azurerm_automation_account.main.name
  schedule_name           = azurerm_automation_schedule.cherwell_status[0].name
  runbook_name            = azurerm_automation_runbook.cherwell_status[0].name
}
