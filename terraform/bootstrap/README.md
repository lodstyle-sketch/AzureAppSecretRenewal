# Terraform Backend Bootstrap

This folder creates the Storage Account and Blob container used by the remote Terraform backend.

```bash
cd terraform/bootstrap
cp terraform.tfvars.example terraform.tfvars
terraform init
terraform apply
```

Use the output values in `terraform/envs/dev/backend.hcl` and `terraform/envs/prod/backend.hcl`.
