output "backend_resource_group_name" {
  value = azurerm_resource_group.state.name
}

output "backend_storage_account_name" {
  value = azurerm_storage_account.state.name
}

output "backend_container_name" {
  value = azurerm_storage_container.state.name
}
