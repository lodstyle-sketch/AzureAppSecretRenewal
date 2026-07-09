from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    tenant_id: str
    graph_base_url: str
    expiry_window_days: int
    internal_api_base_url: str
    cosmos_account_url: str
    cosmos_database: str
    cosmos_container: str
    cosmos_app_overview_container: str
    cosmos_archive_container: str
    webapp_public_base_url: str
    mail_shared_mailbox: str
    department_summary_mailbox: str
    bitwarden_mode: str
    link_signing_key: str
    log_analytics_dce_url: str | None
    log_analytics_dcr_immutable_id: str | None
    log_analytics_cases_stream_name: str
    log_analytics_overview_stream_name: str
    log_analytics_archive_stream_name: str

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            tenant_id=_required("TENANT_ID"),
            graph_base_url=os.getenv("GRAPH_BASE_URL", "https://graph.microsoft.com/v1.0").rstrip("/"),
            expiry_window_days=int(os.getenv("EXPIRY_WINDOW_DAYS", "30")),
            internal_api_base_url=_required("INTERNAL_API_BASE_URL").rstrip("/"),
            cosmos_account_url=_required("COSMOS_ACCOUNT_URL"),
            cosmos_database=_required("COSMOS_DATABASE"),
            cosmos_container=_required("COSMOS_CONTAINER"),
            cosmos_app_overview_container=os.getenv("COSMOS_APP_OVERVIEW_CONTAINER", "credential-renewal-app-overview"),
            cosmos_archive_container=os.getenv("COSMOS_ARCHIVE_CONTAINER", "credential-renewal-archive"),
            webapp_public_base_url=_required("WEBAPP_PUBLIC_BASE_URL").rstrip("/"),
            mail_shared_mailbox=_required("MAIL_SHARED_MAILBOX"),
            department_summary_mailbox=_required("DEPARTMENT_SUMMARY_MAILBOX"),
            bitwarden_mode=os.getenv("BITWARDEN_MODE", "send"),
            link_signing_key=_link_signing_key(),
            log_analytics_dce_url=os.getenv("LOG_ANALYTICS_DCE_URL", "").rstrip("/") or None,
            log_analytics_dcr_immutable_id=os.getenv("LOG_ANALYTICS_DCR_IMMUTABLE_ID"),
            log_analytics_cases_stream_name=os.getenv("LOG_ANALYTICS_CASES_STREAM_NAME", "Custom-CredentialRenewalCases_CL"),
            log_analytics_overview_stream_name=os.getenv("LOG_ANALYTICS_OVERVIEW_STREAM_NAME", "Custom-CredentialRenewalAppOverview_CL"),
            log_analytics_archive_stream_name=os.getenv("LOG_ANALYTICS_ARCHIVE_STREAM_NAME", "Custom-CredentialRenewalArchive_CL"),
        )


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _link_signing_key() -> str:
    value = os.getenv("LINK_SIGNING_KEY")
    if value:
        return value
    secret_name = os.getenv("LINK_SIGNING_KEY_SECRET_NAME")
    key_vault_url = os.getenv("KEY_VAULT_URL")
    if secret_name and key_vault_url:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        client = SecretClient(vault_url=key_vault_url, credential=DefaultAzureCredential())
        secret = client.get_secret(secret_name)
        if secret.value:
            return secret.value
    raise RuntimeError("Missing LINK_SIGNING_KEY or KEY_VAULT_URL plus LINK_SIGNING_KEY_SECRET_NAME.")
