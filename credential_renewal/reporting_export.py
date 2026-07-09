from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from credential_renewal.azure_identity import ManagedIdentityTokenProvider
from credential_renewal.config import Settings
from credential_renewal.cosmos_store import CosmosCaseStore
from credential_renewal.models import CredentialCase

logger = logging.getLogger(__name__)


def flatten_case_for_log_analytics(case: CredentialCase) -> dict[str, Any]:
    owner_emails = [user.email for user in case.responsible_users]
    owner_names = [user.display_name for user in case.responsible_users if user.display_name]
    return {
        "TimeGenerated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "CaseId": case.case_id,
        "AzureAppName": case.azure_application.display_name,
        "AzureAppId": case.azure_application.app_id,
        "AzureAppObjectId": case.azure_application.object_id,
        "ServiceManagementReference": case.azure_application.service_management_reference,
        "CredentialType": case.old_credential.credential_type.value,
        "CredentialKeyId": case.old_credential.key_id,
        "CredentialExpiresAt": case.old_credential.end_date_time.isoformat().replace("+00:00", "Z"),
        "OwnersText": " ".join(owner_emails + owner_names),
        "OwnerEmails": ",".join(owner_emails),
        "CherwellId": case.cherwell_change_id,
        "CherwellNumber": case.cherwell_change_number,
        "CherwellStatus": case.cherwell_status,
        "CaseState": case.state.value,
        "FirstDecisionAt": _optional_datetime(case.first_decision_at),
        "DecisionEditableUntil": _optional_datetime(case.decision_editable_until),
        "DeferUntil": _optional_datetime(case.defer_until),
        "OldSecretRemovedAt": _optional_datetime(case.old_secret_removed_at),
        "CherwellCreatedAt": _optional_datetime(case.cherwell_created_at),
        "CherwellCompletedAt": _optional_datetime(case.cherwell_completed_at),
        "UpdatedAt": _optional_datetime(case.updated_at),
    }


class LogAnalyticsExporter:
    def __init__(self, dce_url: str, dcr_immutable_id: str, stream_name: str, token_provider=None, session: requests.Session | None = None) -> None:
        self.dce_url = dce_url.rstrip("/")
        self.dcr_immutable_id = dcr_immutable_id
        self.stream_name = stream_name
        self.token_provider = token_provider or ManagedIdentityTokenProvider("https://monitor.azure.com/.default")
        self.session = session or requests.Session()

    def export_cases(self, cases: list[CredentialCase]) -> int:
        rows = [flatten_case_for_log_analytics(case) for case in cases]
        if not rows:
            return 0
        url = (
            f"{self.dce_url}/dataCollectionRules/{self.dcr_immutable_id}"
            f"/streams/{self.stream_name}?api-version=2023-01-01"
        )
        response = self.session.post(
            url,
            headers={"Authorization": f"Bearer {self.token_provider.get_token()}", "Content-Type": "application/json"},
            json=rows,
            timeout=60,
        )
        response.raise_for_status()
        return len(rows)


def run_export(settings: Settings, store, exporter: LogAnalyticsExporter) -> dict[str, int]:
    cases = store.list_cases()
    exported = exporter.export_cases(cases)
    return {"cases_read": len(cases), "rows_exported": exported}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_environment()
    if not settings.log_analytics_dce_url or not settings.log_analytics_dcr_immutable_id or not settings.log_analytics_stream_name:
        raise RuntimeError("Missing Log Analytics export configuration.")
    store = CosmosCaseStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_container)
    exporter = LogAnalyticsExporter(
        settings.log_analytics_dce_url,
        settings.log_analytics_dcr_immutable_id,
        settings.log_analytics_stream_name,
    )
    counters = run_export(settings, store, exporter)
    logger.info("Credential renewal reporting export completed", extra=counters)


def _optional_datetime(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None


if __name__ == "__main__":
    main()
