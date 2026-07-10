output "web_app_url" {
  value = "https://${azurerm_linux_web_app.web.default_hostname}"
}

output "configured_public_base_url" {
  value = var.webapp_public_base_url
}

output "cosmos_account_url" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "cosmos_database" {
  value = azurerm_cosmosdb_sql_database.main.name
}

output "cosmos_containers" {
  value = {
    cases    = azurerm_cosmosdb_sql_container.cases.name
    overview = azurerm_cosmosdb_sql_container.overview.name
    archive  = azurerm_cosmosdb_sql_container.archive.name
  }
}

output "cosmos_partition_key_paths" {
  value = local.cosmos_partition_key_paths
}

output "key_vault_uri" {
  value = azurerm_key_vault.main.vault_uri
}

output "automation_account_name" {
  value = azurerm_automation_account.main.name
}

output "runbook_names" {
  value = {
    scan            = azurerm_automation_runbook.scan.name
    reporting_export = azurerm_automation_runbook.reporting_export.name
    cherwell_status  = var.enable_cherwell ? azurerm_automation_runbook.cherwell_status[0].name : null
  }
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.main.workspace_id
}

output "log_analytics_workspace_resource_id" {
  value = azurerm_log_analytics_workspace.main.id
}

output "data_collection_endpoint_url" {
  value = azurerm_monitor_data_collection_endpoint.main.logs_ingestion_endpoint
}

output "data_collection_rule_immutable_id" {
  value = azurerm_monitor_data_collection_rule.main.immutable_id
}

output "managed_identity_principal_ids" {
  value = {
    web_app    = azurerm_linux_web_app.web.identity[0].principal_id
    automation = azurerm_automation_account.main.identity[0].principal_id
  }
}
