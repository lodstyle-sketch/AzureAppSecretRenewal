# Azure App Credential Renewal Workflow

This repository contains a Python implementation for detecting expiring Entra ID App Registration credentials and driving an owner decision workflow.

The solution has two runtime entry points:

- **Azure Automation runbook**: scans App Registrations, enriches findings with an internal application system, writes Cosmos DB cases, and sends notification emails.
- **Azure Web App**: shows each case to authorized responsible users and lets them renew a secret, defer renewal, or delete the old secret after a new one was created.

Version 1 renews **client secrets** automatically. Certificates are detected and shown, but certificate renewal is intentionally out of scope because private-key generation and delivery require a separate security design.

## Architecture

The workflow uses Microsoft Graph as the source of App Registration credentials. The runbook reads each application with `serviceManagementReference`, `passwordCredentials`, and `keyCredentials`. If a credential expires within the configured window, the runbook calls the internal REST API with the service management reference and resolves the returned responsible users in Entra ID.

Each expiring credential becomes one Cosmos DB case. Notification emails contain a reusable Web App link:

```text
https://credential-renewal.example.com/cases/{caseId}?token={signedToken}
```

The link is not single-use. It can be opened multiple times until the original old credential expires. The Web App still requires Entra ID login and only allows users stored as responsible people on the case.

When a user renews a secret, Microsoft Graph creates a new password credential and returns `secretText` once. The Web App immediately creates a Bitwarden Send link and stores only metadata in Cosmos DB. The old secret is not deleted automatically. A separate **Delete old secret** button appears after renewal and asks for explicit confirmation before Graph `removePassword` is called.

## Required Azure Resources

- Azure Automation Account with a system-assigned or user-assigned managed identity.
- Azure Web App for the FastAPI application.
- Managed identity for the Web App.
- Cosmos DB account, database, and container.
- Key Vault for production secrets such as the link signing key and internal API credentials.
- Shared Exchange Online mailbox for notifications.
- Microsoft Graph application permissions granted to the managed identities.
- Bitwarden Enterprise setup that allows automated Bitwarden Send creation from the Web App runtime.

Recommended Cosmos DB container:

```text
Database: credential-renewal
Container: credential-renewal-cases
Partition key: /caseId
```

## Microsoft Graph Permissions

Grant and admin-consent the minimum permissions required for your tenant model:

- `Application.Read.All` for scanning applications.
- `Application.ReadWrite.All` for creating and removing application passwords, unless you implement a narrower owner-based permission model.
- `User.Read.All` for resolving responsible users.
- `Mail.Send` for shared-mailbox notification delivery.

Use separate managed identities for the Automation Account and Web App if you want tighter privilege separation. The runbook needs read and mail permissions; the Web App needs secret creation/removal permissions.

## Configuration

The application reads configuration from environment variables:

```bash
TENANT_ID="00000000-0000-0000-0000-000000000000"
EXPIRY_WINDOW_DAYS="30"
GRAPH_BASE_URL="https://graph.microsoft.com/v1.0"
INTERNAL_API_BASE_URL="https://internal-api.example.com"
COSMOS_ACCOUNT_URL="https://cosmos-account.documents.azure.com:443/"
COSMOS_DATABASE="credential-renewal"
COSMOS_CONTAINER="credential-renewal-cases"
WEBAPP_PUBLIC_BASE_URL="https://credential-renewal.example.com"
MAIL_SHARED_MAILBOX="credential-renewal@example.com"
BITWARDEN_MODE="send"
LINK_SIGNING_KEY="replace-with-key-vault-in-production"
# Or use Key Vault:
KEY_VAULT_URL="https://your-vault.vault.azure.net/"
LINK_SIGNING_KEY_SECRET_NAME="credential-renewal-link-signing-key"
```

For local development, `LINK_SIGNING_KEY` is the simplest option. In production, prefer `KEY_VAULT_URL` plus `LINK_SIGNING_KEY_SECRET_NAME`; the managed identity must have permission to read that secret.

## Internal REST API Contract

The runbook calls:

```http
GET /applications/{serviceManagementReference}/responsibles
Accept: application/json
```

Example response:

```json
{
  "applicationCode": "PAY",
  "businessService": "Payments",
  "environment": "Production",
  "criticality": "High",
  "responsibles": [
    {
      "email": "owner.one@example.com",
      "role": "Application Owner"
    },
    {
      "upn": "owner.two@example.com",
      "role": "Technical Owner"
    }
  ]
}
```

The `responsibles` array must contain email or UPN values. Display names are not used as identifiers because they are not unique.

## Cosmos DB Case Schema

Each case stores:

- `case_id` and `id`.
- Azure application metadata: object ID, app ID, display name, and service management reference.
- Old credential metadata: key ID, display name, type, and expiry.
- Internal application metadata, excluding the raw `responsibles` block.
- Resolved responsible users with email, display name, and Entra object ID.
- Link expiry, which equals the old credential expiry.
- Decision state and decision edit window.
- New credential metadata after renewal, excluding the secret value.
- Bitwarden Send metadata.
- Audit events.

Supported states:

- `open`
- `renewed_pending_old_secret_removal`
- `renewed_old_secret_removed`
- `deferred`
- `error`
- `expired`

Secret values must never be stored in Cosmos DB, logs, emails, or audit events.

## Runbook Deployment

1. Create or select an Azure Automation Account.
2. Enable managed identity.
3. Grant Microsoft Graph permissions and admin consent.
4. Configure required environment variables as Automation variables or process environment variables.
5. Deploy the package files to the Automation Python runtime.
6. Use `credential_renewal.runbook_scan:main` as the runbook entry point.
7. Schedule the runbook daily.

For local validation:

```bash
python -m credential_renewal.runbook_scan
```

The runbook is idempotent by case ID. Repeated scans update the same case instead of creating duplicates. Emails are sent only once per case unless you clear `email_sent_at`.

## Web App Deployment

1. Create an Azure Web App with Python 3.11 or newer.
2. Enable managed identity.
3. Enable App Service Authentication with Microsoft Entra ID.
4. Configure all required environment variables.
5. Deploy the repository.
6. Start the app with:

```bash
uvicorn credential_renewal.web_app:app --host 0.0.0.0 --port 8000
```

Health check endpoint:

```text
/healthz
```

The app reads the authenticated user from App Service Easy Auth headers. For local testing only, `X-User-Principal-Name` can be supplied as a fallback header.

## Web App Decision Rules

- The signed case link is reusable until the original old credential expires.
- The user must be authenticated with Entra ID.
- The signed-in user must match one of the responsible user emails on the case.
- **Renew secret** is available only for client secrets.
- Renewing creates a new secret and a Bitwarden Send link, but does not delete the old secret.
- **Delete old secret** appears only after a new secret has been created.
- Deleting the old secret requires a browser confirmation dialog.
- **Do not renew** sets a one-month deferral.
- Decisions can be changed for one month from the first decision, as long as the original old credential has not expired.

## Bitwarden Send Handling

The Web App calls the Bitwarden CLI through `BitwardenSendClient`. The new secret value is passed directly to Bitwarden and is never logged or persisted by this application.

The Bitwarden Send link is separate from the reusable Web App case link. Configure Bitwarden policy so the Send link has a short lifetime and limited access count.

In production, ensure the Web App runtime has:

- Bitwarden CLI installed.
- A secure enterprise-approved login method.
- Access policies that allow Send creation.
- Monitoring for failed Send creation.

## Example Notification Email

Subject:

```text
Action required: credential expiry for Payments API
```

Body summary:

```text
Hello Owner,

An App Registration credential is expiring and needs a decision.

Application: Payments API
App ID: 11111111-2222-3333-4444-555555555555
Credential type: secret
Credential expiry: 2026-08-01T00:00:00+00:00

Open the credential renewal case: https://credential-renewal.example.com/cases/...
```

## Local Development

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[test]"
```

Run tests without external test tooling:

```bash
python -m unittest discover -s tests
```

Or run them with pytest when the optional test dependency is installed:

```bash
pytest
```

Run the Web App locally:

```bash
uvicorn credential_renewal.web_app:app --reload
```

Local Web App calls require a valid token and a user header:

```bash
curl -H "X-User-Principal-Name: owner@example.com" "http://127.0.0.1:8000/cases/{caseId}?token={token}"
```

## Operational Runbook

Monitor:

- Azure Automation job status and exception logs.
- Cosmos DB request failures and throttling.
- Graph permission failures.
- Internal REST API failures.
- Mail send failures.
- Bitwarden Send creation failures.
- Web App HTTP 401/403/500 rates.

Common failures:

- Missing `serviceManagementReference`: the credential cannot be mapped to the internal system.
- Responsible user not found in Entra ID: the internal system must be corrected.
- Graph `addPassword` failure: verify Web App managed identity permissions.
- Graph `removePassword` failure: verify the old credential still exists and permissions are granted.
- Bitwarden Send failure: do not retry with email or logs containing the secret; retry the renewal action after fixing Bitwarden.

Safe recovery:

- Re-run the Automation job; case creation is idempotent.
- If email delivery fails before `email_sent_at` is set, re-running sends the notification.
- If renewal succeeds but Bitwarden Send fails, treat the case as failed and manually rotate the secret because Graph returns the secret text only once.
- If old-secret deletion fails, the case remains in `renewed_pending_old_secret_removal` and the user can retry.

## Security Notes

- Do not store secret values in Cosmos DB.
- Do not write secret values to logs.
- Keep Web App case links signed and time-limited to the old credential expiry.
- Require Entra ID login in addition to the signed link.
- Keep Bitwarden Send links short-lived and limited-access.
- Preserve audit events for renew, defer, notification, and old-secret deletion actions.
- Separate runbook and Web App identities if your security model requires least privilege.

## Project Layout

```text
credential_renewal/
  auth.py             # Web App identity helpers.
  azure_identity.py   # Managed identity token provider.
  bitwarden.py        # Bitwarden Send adapter.
  case_ids.py         # Stable idempotent case IDs.
  config.py           # Environment-based settings.
  cosmos_store.py     # Cosmos DB and in-memory stores.
  expiry.py           # Credential expiry detection.
  graph_client.py     # Microsoft Graph adapter.
  internal_api.py     # Internal REST API adapter.
  mailer.py           # Shared-mailbox email delivery.
  models.py           # Case and credential models.
  runbook_scan.py     # Azure Automation entry point.
  tokens.py           # Reusable signed case links.
  web_app.py          # FastAPI Web App.
  workflow.py         # Renew, defer, and old-secret deletion logic.
tests/
  test_expiry.py
  test_tokens.py
  test_workflow.py
```
