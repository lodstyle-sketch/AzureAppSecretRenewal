# Agent Instructions

This repository contains a Python workflow for Azure App Registration credential renewal. The main branch includes the base Azure Automation scan runbook and FastAPI Web App workflow.

## Repository Shape

- `credential_renewal/runbook_scan.py`: Azure Automation scan entry point.
- `credential_renewal/web_app.py`: FastAPI Web App entry point.
- `credential_renewal/workflow.py`: user decision workflow for renew, defer, and old-secret deletion.
- `credential_renewal/models.py`: case, credential, owner, and state models.
- `credential_renewal/cosmos_store.py`: Cosmos DB store plus test in-memory store.
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
- If an App Registration has no `serviceManagementReference`, the base workflow cannot map it to the internal system and should not proceed with owner notification.
- Keep branch-specific docs aligned with branch behavior. This main branch does not include Cherwell or Grafana reporting.

## Validation

Run these checks before committing code changes:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile credential_renewal/*.py tests/*.py
rg -n "^(<<<<<<<|=======|>>>>>>>)" README.md DETAILED_EXPLANATION_AND_DEPLOYMENT.md DEPLOYMENT.md agents.md
```

The `rg` command should return no matches. Exit code `1` from `rg` is acceptable when no merge markers are found.

## Git Guidance

- Use feature branches for behavior changes.
- Do not add Cherwell/Grafana behavior to `main` unless explicitly requested.
- Recommended commit style: concise imperative subject, for example `Add deployment checklist`.
