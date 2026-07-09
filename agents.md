# Agent Instructions

This repository contains a Python workflow for Azure App Registration credential renewal. It has an Azure Automation scan runbook, a FastAPI Web App, Cherwell Change automation, Log Analytics export, and a Grafana dashboard template.

## Repository Shape

- `credential_renewal/runbook_scan.py`: main Azure Automation scan entry point.
- `credential_renewal/web_app.py`: FastAPI Web App entry point.
- `credential_renewal/workflow.py`: user decision workflow for renew, defer, and old-secret deletion.
- `credential_renewal/cherwell_client.py`: Cherwell REST adapter.
- `credential_renewal/cherwell_status_scan.py`: Cherwell status polling entry point.
- `credential_renewal/archive.py`: archive record helpers.
- `credential_renewal/reporting_export.py`: Log Analytics reporting export entry point for cases, overview, and archive.
- `credential_renewal/models.py`: case, credential, owner, and state models.
- `credential_renewal/cosmos_store.py`: Cosmos DB store plus test in-memory store.
- `grafana/`: Grafana dashboard templates for cases, app overview, and archive.
- `tests/`: standard-library `unittest` tests.
- `README.md`: main technical overview.
- `DETAILED_EXPLANATION_AND_DEPLOYMENT.md`: detailed German explanation.
- `DEPLOYMENT.md`: deployment checklist.

## Working Rules

- Keep code comments and identifiers in English.
- Keep German user-facing documentation in German when editing German docs.
- Do not store, log, export, or email secret values. Microsoft Graph `secretText` is returned once and must only be passed to Bitwarden Send.
- Do not remove old secrets immediately after renewal. Old client secrets are removed only by explicit Web App action or by completed Cherwell Change processing.
- Certificate renewal/removal is not automated in version 1. Mark certificate cleanup as manual when Cherwell completes.
- If an App Registration has no `serviceManagementReference`, do not create a Cosmos case, Cherwell Change, or email notification.
- Store every App Registration in the app overview, including apps without `serviceManagementReference`.
- Archive secret renewals, old-secret deletions, Cherwell-triggered deletions, and deleted App Registrations.
- Keep branch-specific docs aligned with branch behavior. This feature branch includes Cherwell and Grafana reporting.

## Validation

Run these checks before committing code changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile credential_renewal/*.py tests/*.py
python3 -m json.tool grafana/credential-renewal-cases-dashboard.json
python3 -m json.tool grafana/app-registration-overview-dashboard.json
python3 -m json.tool grafana/credential-renewal-archive-dashboard.json
rg -n "^(<<<<<<<|=======|>>>>>>>)" README.md DETAILED_EXPLANATION_AND_DEPLOYMENT.md DEPLOYMENT.md DEPLOYMENT_DETAILED.md agents.md grafana/*.json
```

The `rg` command should return no matches. Exit code `1` from `rg` is acceptable when no merge markers are found.

## Git Guidance

- Use feature branches for behavior changes.
- Do not merge this branch into `main` unless explicitly requested.
- Recommended commit style: concise imperative subject, for example `Add Cherwell change workflow and Grafana reporting`.
