# Deployment Checklist

This checklist deploys the feature branch with Azure Automation, FastAPI Web App, Cherwell Change automation, Log Analytics export, and Grafana reporting. Terraform is the recommended deployment path.

## 0. Terraform Deployment

- [ ] Build deployment artifacts:

```bash
./scripts/build_deployment_artifacts.sh
```

- [ ] Bootstrap remote state:

```bash
cd terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

- [ ] Configure the target environment:

```bash
cd ../envs/dev
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

- [ ] Use `enable_cherwell=false` for the main-compatible deployment.
- [ ] Use `enable_cherwell=true` for the Cherwell feature branch.
- [ ] Keep `enable_graph_app_role_assignments=false` unless the Terraform identity has the required Entra permissions.
- [ ] Provide Azure Automation dependency package URLs through `automation_dependency_packages`.
- [ ] Import Grafana JSON files manually; Terraform does not create Grafana.

## 1. Azure Resources

- [ ] Create or select the target Resource Group.
- [ ] Create an Azure Automation Account.
- [ ] Create an Azure App Service Plan.
- [ ] Create an Azure Linux Web App with Python 3.11 or newer.
- [ ] Create a Cosmos DB account.
- [ ] Create Cosmos DB database `credential-renewal`.
- [ ] Create Cosmos DB container `credential-renewal-cases` with partition key `/id`.
- [ ] Create Cosmos DB container `credential-renewal-app-overview` with partition key `/id`.
- [ ] Create Cosmos DB container `credential-renewal-archive` with partition key `/id`.
- [ ] Create or select an Azure Key Vault.
- [ ] Create or select the shared mailbox used for notifications.
- [ ] Create or select Log Analytics Workspace.
- [ ] Create Log Analytics Data Collection Endpoint.
- [ ] Create Data Collection Rule for custom table `CredentialRenewalCases_CL`.
- [ ] Prepare Grafana with the Azure Monitor datasource.

## 2. Managed Identities

- [ ] Enable managed identity on the Automation Account.
- [ ] Enable managed identity on the Web App.
- [ ] Grant both identities required Cosmos DB data-plane access.
- [ ] Grant both identities Key Vault secret read access.
- [ ] Grant the reporting identity permission to send data through the Logs Ingestion API.

## 3. Microsoft Graph Permissions

- [ ] Grant `Application.Read.All` for scanning App Registrations.
- [ ] Grant `User.Read.All` for responsible-user lookup.
- [ ] Grant `Mail.Send` for shared-mailbox notifications.
- [ ] Grant `Application.ReadWrite.OwnedBy` where possible, or `Application.ReadWrite.All` if required for secret create/remove.
- [ ] Complete tenant admin consent.
- [ ] Verify the Web App identity can call `addPassword` and `removePassword` for target App Registrations.

## 4. Key Vault Secrets

- [ ] Add `link-signing-key`.
- [ ] Add `cherwell-client-secret`.
- [ ] Grant read permission to the Automation Account identity.
- [ ] Grant read permission to the Web App identity.

## 5. App Settings And Environment Variables

Set these for the Web App and relevant Automation jobs:

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
- [ ] `KEY_VAULT_URL`
- [ ] `LINK_SIGNING_KEY_SECRET_NAME=link-signing-key`
- [ ] `CHERWELL_BASE_URL`
- [ ] `CHERWELL_TOKEN_URL`
- [ ] `CHERWELL_CLIENT_ID`
- [ ] `CHERWELL_AUTH_SECRET_NAME=cherwell-client-secret`
- [ ] `CHERWELL_CHANGE_TEMPLATE_ID`
- [ ] `CHERWELL_COMPLETED_STATUSES=Closed,Completed,Resolved`
- [ ] `LOG_ANALYTICS_DCE_URL`
- [ ] `LOG_ANALYTICS_DCR_IMMUTABLE_ID`
- [ ] `LOG_ANALYTICS_CASES_STREAM_NAME=Custom-CredentialRenewalCases_CL`
- [ ] `LOG_ANALYTICS_OVERVIEW_STREAM_NAME=Custom-CredentialRenewalAppOverview_CL`
- [ ] `LOG_ANALYTICS_ARCHIVE_STREAM_NAME=Custom-CredentialRenewalArchive_CL`

## 6. Web App Deployment

- [ ] Deploy the repository branch `feature/cherwell-change-grafana-report` to the Web App.
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

## 8. Azure Automation Runbooks

- [ ] Deploy the Python package files to the Automation Account.
- [ ] Make dependencies from `requirements.txt` available to the Python runtime.
- [ ] Create scan runbook entry point:

```text
credential_renewal.runbook_scan.main
```

- [ ] Schedule the scan runbook daily.
- [ ] Create Cherwell status runbook entry point:

```text
credential_renewal.cherwell_status_scan.main
```

- [ ] Schedule the Cherwell status runbook every 15 to 60 minutes.
- [ ] Create reporting export runbook entry point:

```text
credential_renewal.reporting_export.main
```

- [ ] Schedule the reporting export runbook at the desired dashboard refresh cadence.

## 9. Cherwell

- [ ] Verify Cherwell REST API base URL.
- [ ] Verify token endpoint and client credentials.
- [ ] Verify Change template ID.
- [ ] Confirm Change payload fields map correctly in the target Cherwell instance.
- [ ] Confirm completed status names match `CHERWELL_COMPLETED_STATUSES`.
- [ ] Test Change creation with a non-production App Registration.
- [ ] Test status polling with a manually completed Change.

## 10. Grafana

- [ ] Import `grafana/credential-renewal-cases-dashboard.json`.
- [ ] Import `grafana/app-registration-overview-dashboard.json`.
- [ ] Import `grafana/credential-renewal-archive-dashboard.json`.
- [ ] Select the Azure Monitor datasource.
- [ ] Confirm table `CredentialRenewalCases_CL` receives rows.
- [ ] Test filter `Azure App Name`.
- [ ] Test filter `Owner`; it should search across all owner names and emails.
- [ ] Test filter `Cherwell ID`; it should match Change ID or Change number.

## 11. Smoke Test

- [ ] Create a test App Registration.
- [ ] Add a client secret expiring inside the configured window.
- [ ] Set `serviceManagementReference` to a valid internal app code.
- [ ] Ensure the internal API returns at least one responsible user.
- [ ] Run the scan runbook manually.
- [ ] Confirm Cosmos DB case creation.
- [ ] Confirm app overview document creation.
- [ ] Confirm department summary email delivery.
- [ ] Confirm Cherwell Change creation.
- [ ] Confirm notification email delivery.
- [ ] Open the Web App link and verify Entra ID login.
- [ ] Click `Renew secret`.
- [ ] Confirm the new secret is delivered through Bitwarden Send.
- [ ] Confirm the old secret still exists.
- [ ] Complete the Cherwell Change.
- [ ] Run the Cherwell status runbook.
- [ ] Confirm the old secret is removed.
- [ ] Run the reporting export runbook.
- [ ] Confirm the case appears in Grafana.

## 12. Missing Internal App Code Test

- [ ] Create or use an App Registration with an expiring credential and no `serviceManagementReference`.
- [ ] Run the scan runbook.
- [ ] Confirm no Cosmos case is created.
- [ ] Confirm no Cherwell Change is created.
- [ ] Confirm no notification email is sent.
- [ ] Confirm the app is visible in the overview dashboard as missing internal app code.
- [ ] Confirm the department summary marks the missing internal app code.
- [ ] Add the internal app code to `serviceManagementReference`.
- [ ] Run the scan runbook again.
- [ ] Confirm the normal workflow starts.

## 13. Operational Checks

- [ ] Monitor Automation job failures.
- [ ] Monitor Graph 401, 403, 429, and 5xx responses.
- [ ] Monitor Cosmos DB throttling and write failures.
- [ ] Monitor Cherwell API failures.
- [ ] Monitor Bitwarden Send failures.
- [ ] Monitor Log Analytics ingestion failures.
- [ ] Confirm old-secret deletion is idempotent if the Cherwell status runbook runs repeatedly.
- [ ] Confirm certificate cases move to manual removal instead of automated deletion.

## 14. Security Checks

- [ ] Confirm `secretText` is never stored in Cosmos DB.
- [ ] Confirm `secretText` is never logged.
- [ ] Confirm `secretText` is never sent by email.
- [ ] Confirm `secretText` is never exported to Log Analytics.
- [ ] Confirm Web App links are signed and expire with the old credential.
- [ ] Confirm Entra ID login is required.
- [ ] Confirm only responsible users can open a case.
