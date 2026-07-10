# credential-renewal Terraform Module

This module creates the Azure resources for the credential renewal workflow:

- Resource Group
- Artifact Storage Account
- Key Vault with link-signing key and optional Cherwell secret
- Cosmos DB SQL account, database, and three containers
- Log Analytics Workspace, Data Collection Endpoint, and Data Collection Rule
- Linux App Service with Entra App Service Authentication
- Automation Account, Python3 package, runbooks, schedules, and variables
- Azure RBAC and optional Microsoft Graph app-role assignments

The Cosmos containers intentionally use partition key `/id` because every Python model writes `id` equal to its logical key.

Set `enable_cherwell=false` for the main-compatible deployment and `enable_cherwell=true` for the Cherwell feature branch.
