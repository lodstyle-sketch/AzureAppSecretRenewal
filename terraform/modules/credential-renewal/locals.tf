locals {
  name_prefix = lower(replace("${var.resource_prefix}-${var.environment}", "_", "-"))
  tags        = merge(var.tags, { environment = var.environment, workload = "credential-renewal" })

  resource_group_name     = var.create_resource_group ? azurerm_resource_group.main[0].name : data.azurerm_resource_group.main[0].name
  resource_group_location = var.create_resource_group ? azurerm_resource_group.main[0].location : data.azurerm_resource_group.main[0].location

  graph_base_url = "https://graph.microsoft.com/v1.0"

  cosmos_partition_key_paths = ["/id"]

  cases_stream_name    = "Custom-CredentialRenewalCases_CL"
  overview_stream_name = "Custom-CredentialRenewalAppOverview_CL"
  archive_stream_name  = "Custom-CredentialRenewalArchive_CL"

  base_app_settings = {
    TENANT_ID                            = var.tenant_id
    EXPIRY_WINDOW_DAYS                   = tostring(var.expiry_window_days)
    GRAPH_BASE_URL                       = local.graph_base_url
    INTERNAL_API_BASE_URL                = var.internal_api_base_url
    COSMOS_ACCOUNT_URL                   = azurerm_cosmosdb_account.main.endpoint
    COSMOS_DATABASE                      = azurerm_cosmosdb_sql_database.main.name
    COSMOS_CONTAINER                     = azurerm_cosmosdb_sql_container.cases.name
    COSMOS_APP_OVERVIEW_CONTAINER        = azurerm_cosmosdb_sql_container.overview.name
    COSMOS_ARCHIVE_CONTAINER             = azurerm_cosmosdb_sql_container.archive.name
    WEBAPP_PUBLIC_BASE_URL               = var.webapp_public_base_url
    MAIL_SHARED_MAILBOX                  = var.mail_shared_mailbox
    DEPARTMENT_SUMMARY_MAILBOX           = var.department_summary_mailbox
    BITWARDEN_MODE                       = "send"
    KEY_VAULT_URL                        = azurerm_key_vault.main.vault_uri
    LINK_SIGNING_KEY_SECRET_NAME         = azurerm_key_vault_secret.link_signing_key.name
    LOG_ANALYTICS_DCE_URL                = azurerm_monitor_data_collection_endpoint.main.logs_ingestion_endpoint
    LOG_ANALYTICS_DCR_IMMUTABLE_ID       = azurerm_monitor_data_collection_rule.main.immutable_id
    LOG_ANALYTICS_CASES_STREAM_NAME      = local.cases_stream_name
    LOG_ANALYTICS_OVERVIEW_STREAM_NAME   = local.overview_stream_name
    LOG_ANALYTICS_ARCHIVE_STREAM_NAME    = local.archive_stream_name
    SCM_DO_BUILD_DURING_DEPLOYMENT       = "true"
    ENABLE_ORYX_BUILD                    = "true"
    MICROSOFT_PROVIDER_AUTHENTICATION_SECRET = azuread_application_password.web_auth.value
  }

  cherwell_app_settings = var.enable_cherwell ? {
    CHERWELL_BASE_URL            = var.cherwell_base_url
    CHERWELL_TOKEN_URL           = var.cherwell_token_url
    CHERWELL_CLIENT_ID           = var.cherwell_client_id
    CHERWELL_AUTH_SECRET_NAME    = try(azurerm_key_vault_secret.cherwell_client_secret[0].name, "cherwell-client-secret")
    CHERWELL_CHANGE_TEMPLATE_ID  = var.cherwell_change_template_id
    CHERWELL_COMPLETED_STATUSES  = var.cherwell_completed_statuses
  } : {}

  automation_variables = merge(
    { for key, value in local.base_app_settings : key => value if key != "SCM_DO_BUILD_DURING_DEPLOYMENT" && key != "ENABLE_ORYX_BUILD" && key != "MICROSOFT_PROVIDER_AUTHENTICATION_SECRET" },
    local.cherwell_app_settings
  )

  web_app_settings = merge(local.base_app_settings, local.cherwell_app_settings)

  automation_graph_roles = var.enable_cherwell ? setunion(var.automation_graph_app_roles, ["Application.ReadWrite.All"]) : var.automation_graph_app_roles

  cases_transform = <<-KQL
    source
    | project TimeGenerated=todatetime(TimeGenerated), CaseId_s=tostring(CaseId), AzureAppName_s=tostring(AzureAppName), AzureAppId_s=tostring(AzureAppId), AzureAppObjectId_s=tostring(AzureAppObjectId), ServiceManagementReference_s=tostring(ServiceManagementReference), CredentialType_s=tostring(CredentialType), CredentialKeyId_s=tostring(CredentialKeyId), CredentialExpiresAt_t=todatetime(CredentialExpiresAt), OwnersText_s=tostring(OwnersText), OwnerEmails_s=tostring(OwnerEmails), CherwellId_s=tostring(CherwellId), CherwellNumber_s=tostring(CherwellNumber), CherwellStatus_s=tostring(CherwellStatus), CaseState_s=tostring(CaseState), FirstDecisionAt_t=todatetime(FirstDecisionAt), DecisionEditableUntil_t=todatetime(DecisionEditableUntil), DeferUntil_t=todatetime(DeferUntil), OldSecretRemovedAt_t=todatetime(OldSecretRemovedAt), CherwellCreatedAt_t=todatetime(CherwellCreatedAt), CherwellCompletedAt_t=todatetime(CherwellCompletedAt), UpdatedAt_t=todatetime(UpdatedAt)
  KQL

  overview_transform = <<-KQL
    source
    | project TimeGenerated=todatetime(TimeGenerated), AzureAppName_s=tostring(AzureAppName), AzureAppId_s=tostring(AzureAppId), AzureAppObjectId_s=tostring(AzureAppObjectId), ServiceManagementReference_s=tostring(ServiceManagementReference), HasInternalCode_bool=tobool(HasInternalCode), Status_s=tostring(Status), SecretCount_d=todouble(SecretCount), CertificateCount_d=todouble(CertificateCount), NextSecretExpiry_t=todatetime(NextSecretExpiry), NextCertificateExpiry_t=todatetime(NextCertificateExpiry), OwnersText_s=tostring(OwnersText), OwnerEmails_s=tostring(OwnerEmails), LastSeenAt_t=todatetime(LastSeenAt), DeletedAt_t=todatetime(DeletedAt), UpdatedAt_t=todatetime(UpdatedAt)
  KQL

  archive_transform = <<-KQL
    source
    | project TimeGenerated=todatetime(TimeGenerated), ArchiveId_s=tostring(ArchiveId), Action_s=tostring(Action), Status_s=tostring(Status), Source_s=tostring(Source), Actor_s=tostring(Actor), CaseId_s=tostring(CaseId), AzureAppName_s=tostring(AzureAppName), AzureAppId_s=tostring(AzureAppId), AzureAppObjectId_s=tostring(AzureAppObjectId), ServiceManagementReference_s=tostring(ServiceManagementReference), CredentialType_s=tostring(CredentialType), CredentialKeyId_s=tostring(CredentialKeyId), CredentialExpiresAt_t=todatetime(CredentialExpiresAt), CherwellId_s=tostring(CherwellId), CherwellNumber_s=tostring(CherwellNumber), Details_s=tostring(Details)
  KQL

  cases_stream_columns = {
    TimeGenerated          = "datetime"
    CaseId                 = "string"
    AzureAppName           = "string"
    AzureAppId             = "string"
    AzureAppObjectId       = "string"
    ServiceManagementReference = "string"
    CredentialType         = "string"
    CredentialKeyId        = "string"
    CredentialExpiresAt    = "datetime"
    OwnersText             = "string"
    OwnerEmails            = "string"
    CherwellId             = "string"
    CherwellNumber         = "string"
    CherwellStatus         = "string"
    CaseState              = "string"
    FirstDecisionAt        = "datetime"
    DecisionEditableUntil  = "datetime"
    DeferUntil             = "datetime"
    OldSecretRemovedAt     = "datetime"
    CherwellCreatedAt      = "datetime"
    CherwellCompletedAt    = "datetime"
    UpdatedAt              = "datetime"
  }

  overview_stream_columns = {
    TimeGenerated          = "datetime"
    AzureAppName           = "string"
    AzureAppId             = "string"
    AzureAppObjectId       = "string"
    ServiceManagementReference = "string"
    HasInternalCode        = "boolean"
    Status                 = "string"
    SecretCount            = "real"
    CertificateCount       = "real"
    NextSecretExpiry       = "datetime"
    NextCertificateExpiry  = "datetime"
    OwnersText             = "string"
    OwnerEmails            = "string"
    LastSeenAt             = "datetime"
    DeletedAt              = "datetime"
    UpdatedAt              = "datetime"
  }

  archive_stream_columns = {
    TimeGenerated          = "datetime"
    ArchiveId              = "string"
    Action                 = "string"
    Status                 = "string"
    Source                 = "string"
    Actor                  = "string"
    CaseId                 = "string"
    AzureAppName           = "string"
    AzureAppId             = "string"
    AzureAppObjectId       = "string"
    ServiceManagementReference = "string"
    CredentialType         = "string"
    CredentialKeyId        = "string"
    CredentialExpiresAt    = "datetime"
    CherwellId             = "string"
    CherwellNumber         = "string"
    Details                = "string"
  }
}
