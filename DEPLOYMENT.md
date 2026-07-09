# Deployment Checklist

This checklist deploys the main branch with the base Azure Automation scan runbook and FastAPI Web App workflow.

## 1. Azure Resources

- [ ] Create or select the target Resource Group.
- [ ] Create an Azure Automation Account.
- [ ] Create an Azure App Service Plan.
- [ ] Create an Azure Linux Web App with Python 3.11 or newer.
- [ ] Create a Cosmos DB account.
- [ ] Create Cosmos DB database `credential-renewal`.
- [ ] Create Cosmos DB container `credential-renewal-cases` with partition key `/caseId`.
- [ ] Create Cosmos DB container `credential-renewal-app-overview` with partition key `/appObjectId`.
- [ ] Create Cosmos DB container `credential-renewal-archive` with partition key `/archiveId`.
- [ ] Create or select an Azure Key Vault.
- [ ] Create or select the shared mailbox used for notifications.
- [ ] Create or select Log Analytics Workspace.
- [ ] Create Data Collection Endpoint and Data Collection Rule for reporting export.
- [ ] Prepare Grafana with Azure Monitor datasource.

## 2. Managed Identities

- [ ] Enable managed identity on the Automation Account.
- [ ] Enable managed identity on the Web App.
- [ ] Grant both identities required Cosmos DB data-plane access.
- [ ] Grant both identities Key Vault secret read access.

## 3. Microsoft Graph Permissions

- [ ] Grant `Application.Read.All` for scanning App Registrations.
- [ ] Grant `User.Read.All` for responsible-user lookup.
- [ ] Grant `Mail.Send` for shared-mailbox notifications.
- [ ] Grant `Application.ReadWrite.OwnedBy` where possible, or `Application.ReadWrite.All` if required for secret create/remove.
- [ ] Complete tenant admin consent.
- [ ] Verify the Web App identity can call `addPassword` and `removePassword` for target App Registrations.

## 4. Key Vault Secrets

- [ ] Add `credential-renewal-link-signing-key`.
- [ ] Grant read permission to the Automation Account identity.
- [ ] Grant read permission to the Web App identity.

## 5. App Settings And Environment Variables

Set these for the Web App and Automation job:

- [ ] `TENANT_ID`
- [ ] `EXPIRY_WINDOW_DAYS=30`
- [ ] `GRAPH_BASE_URL=https://graph.microsoft.com/v1.0`
- [ ] `INTERNAL_API_BASE_URL`
- [ ] `COSMOS_ACCOUNT_URL`
- [ ] `COSMOS_DATABASE=credential-renewal`
- [ ] `COSMOS_CONTAINER=credential-renewal-cases`
- [ ] `COSMOS_APP_OVERVIEW_CONTAINER=credential-renewal-app-overview`
- [ ] `COSMOS_ARCHIVE_CONTAINER=credential-renewal-archive`
- [ ] `WEBAPP_PUBLIC_BASE_URL`
- [ ] `MAIL_SHARED_MAILBOX`
- [ ] `DEPARTMENT_SUMMARY_MAILBOX`
- [ ] `BITWARDEN_MODE=send`
- [ ] `LOG_ANALYTICS_DCE_URL`
- [ ] `LOG_ANALYTICS_DCR_IMMUTABLE_ID`
- [ ] `LOG_ANALYTICS_CASES_STREAM_NAME=Custom-CredentialRenewalCases_CL`
- [ ] `LOG_ANALYTICS_OVERVIEW_STREAM_NAME=Custom-CredentialRenewalAppOverview_CL`
- [ ] `LOG_ANALYTICS_ARCHIVE_STREAM_NAME=Custom-CredentialRenewalArchive_CL`
- [ ] `KEY_VAULT_URL`
- [ ] `LINK_SIGNING_KEY_SECRET_NAME=credential-renewal-link-signing-key`

## 6. Web App Deployment

- [ ] Deploy the repository branch `main` to the Web App.
- [ ] Ensure dependencies from `requirements.txt` are installed.
- [ ] Configure startup command:

```bash
python -m uvicorn credential_renewal.web_app:app --host 0.0.0.0 --port 8000
```

- [ ] Enable App Service Authentication.
- [ ] Add Microsoft Entra ID as the identity provider.
- [ ] Require authentication for unauthenticated requests.
- [ ] Verify `/healthz` returns `{"status":"ok"}`.

## 7. Bitwarden

- [ ] Install or package the Bitwarden CLI in the Web App runtime.
- [ ] Configure enterprise-approved Bitwarden authentication.
- [ ] Confirm `bw send create` can create short-lived sends.
- [ ] Confirm Bitwarden Send policy supports limited access count.
- [ ] Verify no secret value is written to logs during a test renewal.

## 8. Azure Automation Runbook

- [ ] Deploy the Python package files to the Automation Account.
- [ ] Make dependencies from `requirements.txt` available to the Python runtime.
- [ ] Create scan runbook entry point:

```text
credential_renewal.runbook_scan.main
```

- [ ] Schedule the scan runbook daily.
- [ ] Create reporting export runbook entry point:

```text
credential_renewal.reporting_export.main
```

- [ ] Schedule the reporting export runbook.
- [ ] Confirm the runbook uses managed identity.
- [ ] Confirm the runbook can call Microsoft Graph.
- [ ] Confirm the runbook can call the internal REST API.
- [ ] Confirm the runbook can write to Cosmos DB.
- [ ] Confirm the runbook can send mail through the shared mailbox.
- [ ] Confirm the runbook sends the department summary mail after completion.
- [ ] Confirm the reporting runbook can write to Log Analytics.

## 9. Grafana

- [ ] Import `grafana/credential-renewal-cases-dashboard.json`.
- [ ] Import `grafana/app-registration-overview-dashboard.json`.
- [ ] Import `grafana/credential-renewal-archive-dashboard.json`.
- [ ] Select the Azure Monitor datasource.
- [ ] Confirm app overview filter defaults to missing internal app code.
- [ ] Confirm archive report shows renewal, deletion, and deleted-app entries.

## 10. Internal REST API

- [ ] Verify `INTERNAL_API_BASE_URL`.
- [ ] Confirm endpoint shape:

```http
GET /applications/{serviceManagementReference}/responsibles
```

- [ ] Confirm responses include app metadata.
- [ ] Confirm responses include responsible users with `email` or `upn`.
- [ ] Confirm display names are not used as identifiers.

## 11. Smoke Test

- [ ] Create a test App Registration.
- [ ] Add a client secret expiring inside the configured window.
- [ ] Set `serviceManagementReference` to a valid internal app code.
- [ ] Ensure the internal API returns at least one responsible user.
- [ ] Run the scan runbook manually.
- [ ] Confirm Cosmos DB case creation.
- [ ] Confirm app overview document creation.
- [ ] Confirm department summary email delivery.
- [ ] Confirm notification email delivery.
- [ ] Open the Web App link and verify Entra ID login.
- [ ] Click `Renew secret`.
- [ ] Confirm the new secret is delivered through Bitwarden Send.
- [ ] Confirm the old secret still exists.
- [ ] Click `Delete old secret`.
- [ ] Confirm the browser confirmation appears.
- [ ] Confirm the old secret is removed only after confirmation.

## 12. Missing Internal App Code Test

- [ ] Create or use an App Registration with an expiring credential and no `serviceManagementReference`.
- [ ] Run the scan runbook.
- [ ] Confirm app appears in the overview container.
- [ ] Confirm no case is created.
- [ ] Confirm the department summary marks the missing internal app code.
- [ ] Add the internal app code to `serviceManagementReference`.
- [ ] Run the scan runbook again.
- [ ] Confirm the normal workflow starts.

## 13. Operational Checks

- [ ] Monitor Automation job failures.
- [ ] Monitor Graph 401, 403, 429, and 5xx responses.
- [ ] Monitor Cosmos DB throttling and write failures.
- [ ] Monitor internal API failures.
- [ ] Monitor Bitwarden Send failures.
- [ ] Monitor Log Analytics ingestion failures.
- [ ] Monitor Web App 401, 403, and 500 rates.
- [ ] Confirm old-secret deletion requires explicit Web App confirmation.
- [ ] Confirm certificate cases are not automatically renewed.

## 14. Security Checks

- [ ] Confirm `secretText` is never stored in Cosmos DB.
- [ ] Confirm `secretText` is never logged.
- [ ] Confirm `secretText` is never sent by email.
- [ ] Confirm `secretText` is never exported to Log Analytics.
- [ ] Confirm Web App links are signed and expire with the old credential.
- [ ] Confirm Entra ID login is required.
- [ ] Confirm only responsible users can open a case.
