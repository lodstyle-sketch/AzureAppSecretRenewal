from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from credential_renewal.azure_identity import ManagedIdentityTokenProvider
from credential_renewal.config import Settings
from credential_renewal.cosmos_store import CosmosAppOverviewStore, CosmosArchiveStore, CosmosCaseStore
from credential_renewal.models import AppOverview, ArchiveEntry, CredentialCase

logger = logging.getLogger(__name__)


def flatten_case_for_log_analytics(case: CredentialCase) -> dict[str, Any]:
    owner_emails = [user.email for user in case.responsible_users]
    owner_names = [user.display_name for user in case.responsible_users if user.display_name]
    return {
        "TimeGenerated": _now(),
        "CaseId": case.case_id,
        "AzureAppName": case.azure_application.display_name,
        "AzureAppId": case.azure_application.app_id,
        "AzureAppObjectId": case.azure_application.object_id,
        "ServiceManagementReference": case.azure_application.service_management_reference,
        "CredentialType": case.old_credential.credential_type.value,
        "CredentialKeyId": case.old_credential.key_id,
        "CredentialExpiresAt": _datetime(case.old_credential.end_date_time),
        "OwnersText": " ".join(owner_emails + owner_names),
        "OwnerEmails": ",".join(owner_emails),
        "CaseState": case.state.value,
        "FirstDecisionAt": _datetime(case.first_decision_at),
        "DecisionEditableUntil": _datetime(case.decision_editable_until),
        "DeferUntil": _datetime(case.defer_until),
        "OldSecretRemovedAt": _datetime(case.old_secret_removed_at),
        "UpdatedAt": _datetime(case.updated_at),
    }


def flatten_overview_for_log_analytics(overview: AppOverview) -> dict[str, Any]:
    owner_emails = [user.email for user in overview.owners]
    owner_names = [user.display_name for user in overview.owners if user.display_name]
    return {
        "TimeGenerated": _now(),
        "AzureAppName": overview.display_name,
        "AzureAppId": overview.app_id,
        "AzureAppObjectId": overview.app_object_id,
        "ServiceManagementReference": overview.service_management_reference,
        "HasInternalCode": bool(overview.service_management_reference),
        "Status": overview.status.value,
        "SecretCount": overview.secret_count,
        "CertificateCount": overview.certificate_count,
        "NextSecretExpiry": _datetime(overview.next_secret_expiry),
        "NextCertificateExpiry": _datetime(overview.next_certificate_expiry),
        "OwnersText": " ".join(owner_emails + owner_names),
        "OwnerEmails": ",".join(owner_emails),
        "LastSeenAt": _datetime(overview.last_seen_at),
        "DeletedAt": _datetime(overview.deleted_at),
        "UpdatedAt": _datetime(overview.updated_at),
    }


def flatten_archive_for_log_analytics(entry: ArchiveEntry) -> dict[str, Any]:
    return {
        "TimeGenerated": _datetime(entry.timestamp),
        "ArchiveId": entry.archive_id,
        "Action": entry.action.value,
        "Status": entry.status,
        "Source": entry.source,
        "Actor": entry.actor,
        "CaseId": entry.case_id,
        "AzureAppName": entry.azure_application.display_name,
        "AzureAppId": entry.azure_application.app_id,
        "AzureAppObjectId": entry.azure_application.object_id,
        "ServiceManagementReference": entry.azure_application.service_management_reference,
        "CredentialType": entry.credential.credential_type.value if entry.credential else None,
        "CredentialKeyId": entry.credential.key_id if entry.credential else None,
        "CredentialExpiresAt": _datetime(entry.credential.end_date_time) if entry.credential else None,
        "Details": str(entry.details),
    }


class LogAnalyticsExporter:
    def __init__(self, dce_url: str, dcr_immutable_id: str, token_provider=None, session: requests.Session | None = None) -> None:
        self.dce_url = dce_url.rstrip("/")
        self.dcr_immutable_id = dcr_immutable_id
        self.token_provider = token_provider or ManagedIdentityTokenProvider("https://monitor.azure.com/.default")
        self.session = session or requests.Session()

    def export_rows(self, stream_name: str, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        url = f"{self.dce_url}/dataCollectionRules/{self.dcr_immutable_id}/streams/{stream_name}?api-version=2023-01-01"
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.token_provider.get_token()}", "Content-Type": "application/json"},
            json=rows,
            timeout=60,
        )
        response.raise_for_status()
        return len(rows)


def run_export(settings: Settings, case_store, overview_store, archive_store, exporter: LogAnalyticsExporter) -> dict[str, int]:
    cases = case_store.list_cases()
    overviews = overview_store.list_apps()
    archive_entries = archive_store.list_archive_entries()
    return {
        "case_rows_exported": exporter.export_rows(settings.log_analytics_cases_stream_name, [flatten_case_for_log_analytics(case) for case in cases]),
        "overview_rows_exported": exporter.export_rows(
            settings.log_analytics_overview_stream_name,
            [flatten_overview_for_log_analytics(overview) for overview in overviews],
        ),
        "archive_rows_exported": exporter.export_rows(
            settings.log_analytics_archive_stream_name,
            [flatten_archive_for_log_analytics(entry) for entry in archive_entries],
        ),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_environment()
    if not settings.log_analytics_dce_url or not settings.log_analytics_dcr_immutable_id:
        raise RuntimeError("Missing Log Analytics export configuration.")
    case_store = CosmosCaseStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_container)
    overview_store = CosmosAppOverviewStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_app_overview_container)
    archive_store = CosmosArchiveStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_archive_container)
    exporter = LogAnalyticsExporter(settings.log_analytics_dce_url, settings.log_analytics_dcr_immutable_id)
    counters = run_export(settings, case_store, overview_store, archive_store, exporter)
    logger.info("Credential renewal reporting export completed", extra=counters)


def _now() -> str:
    return _datetime(datetime.now(timezone.utc)) or ""


def _datetime(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


if __name__ == "__main__":
    main()
