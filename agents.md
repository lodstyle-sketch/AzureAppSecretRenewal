# Agent Instructions

This repository contains a Python workflow for Azure App Registration credential renewal. The main branch includes the Azure Automation scan runbook, FastAPI Web App workflow, app overview/archive storage, Log Analytics export, and Grafana dashboards.

## Repository Shape

- `credential_renewal/runbook_scan.py`: Azure Automation scan entry point.
- `credential_renewal/web_app.py`: FastAPI Web App entry point.
- `credential_renewal/workflow.py`: user decision workflow for renew, defer, and old-secret deletion.
- `credential_renewal/archive.py`: archive record helpers.
- `credential_renewal/reporting_export.py`: Log Analytics export entry point.
- `credential_renewal/models.py`: case, credential, owner, and state models.
- `credential_renewal/cosmos_store.py`: Cosmos DB store plus test in-memory store.
- `grafana/`: Grafana dashboard templates for cases, app overview, and archive.
- `terraform/`: Terraform bootstrap, reusable module, dev/prod environments, and Automation runbook wrappers.
- `scripts/build_deployment_artifacts.sh`: builds `dist/webapp.zip` and the Automation wheel consumed by Terraform.
- `tests/`: standard-library `unittest` tests.
- `README.md`: main technical overview.
- `DETAILED_EXPLANATION_AND_DEPLOYMENT.md`: detailed German explanation.
- `DEPLOYMENT.md`: deployment checklist.

## Working Rules

- Keep code comments and identifiers in English.
- Keep German user-facing documentation in German when editing German docs.
- Do not store, log, export, or email secret values. Microsoft Graph `secretText` is returned once and must only be passed to Bitwarden Send.
- Do not remove old secrets immediately after renewal. Old secrets are removed only after explicit user confirmation in the Web App.
- Certificate renewal/removal is not automated in version 1.
- If an App Registration has no `serviceManagementReference`, store it in app overview but do not create a credential case or owner notification.
- Store every App Registration in the app overview, including apps without `serviceManagementReference`.
- Archive secret renewals, old-secret deletions, and deleted App Registrations.
- Cosmos DB containers must use partition key `/id`; the Python documents store logical IDs in the `id` field.
- Terraform must keep `enable_cherwell` and `enable_graph_app_role_assignments` as explicit toggles.
- Keep branch-specific docs aligned with branch behavior. This main branch includes Grafana reporting but does not include Cherwell runtime code.

## Validation

Run these checks before committing code changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile credential_renewal/*.py tests/*.py
terraform fmt -recursive terraform
python3 -m json.tool grafana/credential-renewal-cases-dashboard.json
python3 -m json.tool grafana/app-registration-overview-dashboard.json
python3 -m json.tool grafana/credential-renewal-archive-dashboard.json
rg -n "^(<<<<<<<|=======|>>>>>>>)" README.md DETAILED_EXPLANATION_AND_DEPLOYMENT.md DEPLOYMENT.md DEPLOYMENT_DETAILED.md agents.md terraform grafana/*.json
```

The `rg` command should return no matches. Exit code `1` from `rg` is acceptable when no merge markers are found.

## Git Guidance

- Use feature branches for behavior changes.
- Do not add Cherwell behavior to `main` unless explicitly requested.
- Recommended commit style: concise imperative subject, for example `Add deployment checklist`.
