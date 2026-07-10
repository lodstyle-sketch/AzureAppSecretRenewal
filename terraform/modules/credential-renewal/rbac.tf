locals {
  cosmos_sql_data_contributor_role_definition_id = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
}

resource "azurerm_cosmosdb_sql_role_assignment" "web_data_contributor" {
  resource_group_name = local.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = local.cosmos_sql_data_contributor_role_definition_id
  principal_id        = azurerm_linux_web_app.web.identity[0].principal_id
  scope               = azurerm_cosmosdb_account.main.id
}

resource "azurerm_cosmosdb_sql_role_assignment" "automation_data_contributor" {
  resource_group_name = local.resource_group_name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = local.cosmos_sql_data_contributor_role_definition_id
  principal_id        = azurerm_automation_account.main.identity[0].principal_id
  scope               = azurerm_cosmosdb_account.main.id
}

resource "azurerm_role_assignment" "web_key_vault_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_linux_web_app.web.identity[0].principal_id
}

resource "azurerm_role_assignment" "automation_key_vault_secrets_user" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_automation_account.main.identity[0].principal_id
}

resource "azurerm_role_assignment" "automation_monitoring_metrics_publisher" {
  scope                = azurerm_monitor_data_collection_rule.main.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = azurerm_automation_account.main.identity[0].principal_id
}

resource "azurerm_role_assignment" "automation_log_analytics_contributor" {
  scope                = azurerm_log_analytics_workspace.main.id
  role_definition_name = "Log Analytics Contributor"
  principal_id         = azurerm_automation_account.main.identity[0].principal_id
}

data "azuread_application_published_app_ids" "well_known" {
  count = var.enable_graph_app_role_assignments ? 1 : 0
}

resource "azuread_service_principal" "microsoft_graph" {
  count        = var.enable_graph_app_role_assignments ? 1 : 0
  client_id    = data.azuread_application_published_app_ids.well_known[0].result.MicrosoftGraph
  use_existing = true
}

resource "azuread_app_role_assignment" "automation_graph_roles" {
  for_each            = var.enable_graph_app_role_assignments ? local.automation_graph_roles : toset([])
  app_role_id         = azuread_service_principal.microsoft_graph[0].app_role_ids[each.key]
  principal_object_id = azurerm_automation_account.main.identity[0].principal_id
  resource_object_id  = azuread_service_principal.microsoft_graph[0].object_id
}

resource "azuread_app_role_assignment" "web_graph_roles" {
  for_each            = var.enable_graph_app_role_assignments ? var.webapp_graph_app_roles : toset([])
  app_role_id         = azuread_service_principal.microsoft_graph[0].app_role_ids[each.key]
  principal_object_id = azurerm_linux_web_app.web.identity[0].principal_id
  resource_object_id  = azuread_service_principal.microsoft_graph[0].object_id
}
