# Terraform Deployment

This Terraform deployment provisions Azure infrastructure for both the base branch and the Cherwell/Grafana feature branch.

## Layout

- `bootstrap/`: creates the remote state Storage Account and Blob container.
- `modules/credential-renewal/`: reusable Azure infrastructure module.
- `envs/dev/`: development environment entry point.
- `envs/prod/`: production environment entry point.
- `runbooks/`: small Azure Automation Python wrappers that load Automation Variables and call the package entry points.

## Build Artifacts

Create the Web App ZIP and Automation wheel before running Terraform:

```bash
./scripts/build_deployment_artifacts.sh
```

The default environment examples expect:

- `dist/webapp.zip`
- `dist/azure_app_credential_renewal-0.1.0-py3-none-any.whl`

## Remote State Bootstrap

```bash
cd terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Copy the outputs into `terraform/envs/dev/backend.hcl` and `terraform/envs/prod/backend.hcl`.

## Environment Deployment

```bash
cd terraform/envs/dev
cp backend.hcl.example backend.hcl
cp terraform.tfvars.example terraform.tfvars
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

For production, repeat the same flow in `terraform/envs/prod`.

## Important Defaults

- Cosmos DB containers use partition key `/id`, matching the Python document model.
- `enable_cherwell=false` deploys the main-compatible workflow.
- `enable_cherwell=true` adds Cherwell variables, Change status runbook, and the Cherwell schedule.
- `enable_graph_app_role_assignments=false` by default, because enabling it requires elevated Entra permissions.
- Grafana infrastructure is not created. Import the JSON dashboards from `grafana/` into your existing Grafana instance.

## Azure Automation Dependencies

Terraform uploads this project as a Python3 package. Azure Automation does not reliably resolve Python package dependencies from the wheel metadata, so provide enterprise-approved package URLs through `automation_dependency_packages` for packages from `requirements.txt`.
