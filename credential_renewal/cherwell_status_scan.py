from __future__ import annotations

import logging
from datetime import datetime, timezone

from credential_renewal.azure_identity import ManagedIdentityTokenProvider
from credential_renewal.cherwell_client import CherwellClient
from credential_renewal.config import Settings
from credential_renewal.cosmos_store import CosmosCaseStore
from credential_renewal.graph_client import GraphClient
from credential_renewal.models import CaseState, CredentialType

logger = logging.getLogger(__name__)


def run_status_scan(settings: Settings, store, graph_client: GraphClient, cherwell_client: CherwellClient) -> dict[str, int]:
    counters = {"cases_checked": 0, "statuses_updated": 0, "old_secrets_removed": 0, "manual_certificate_removals": 0, "errors": 0}
    for case in store.list_cases():
        if not case.cherwell_change_id or case.cherwell_completed_at:
            continue
        counters["cases_checked"] += 1
        try:
            status = cherwell_client.get_change_status(case.cherwell_change_id)
            now = datetime.now(timezone.utc)
            case.cherwell_status = status
            case.cherwell_last_checked_at = now
            case.add_audit_event("cherwell_status_checked", "cherwell-status-runbook", {"status": status})
            counters["statuses_updated"] += 1

            if status.strip().lower() in settings.cherwell_completed_statuses:
                case.cherwell_completed_at = now
                if case.old_credential.credential_type == CredentialType.CERTIFICATE:
                    case.state = CaseState.MANUAL_CERTIFICATE_REMOVAL_REQUIRED
                    case.add_audit_event("cherwell_completed_certificate_manual_removal_required", "cherwell-status-runbook")
                    counters["manual_certificate_removals"] += 1
                elif case.old_secret_removed_at:
                    case.state = CaseState.CHERWELL_COMPLETED_OLD_SECRET_REMOVED
                    case.add_audit_event("cherwell_completed_old_secret_already_removed", "cherwell-status-runbook")
                else:
                    graph_client.remove_password(case.azure_application.object_id, case.old_credential.key_id)
                    case.old_secret_removed_at = now
                    case.state = CaseState.CHERWELL_COMPLETED_OLD_SECRET_REMOVED
                    case.add_audit_event(
                        "cherwell_completed_old_secret_deleted",
                        "cherwell-status-runbook",
                        {"oldCredentialKeyId": case.old_credential.key_id, "cherwellStatus": status},
                    )
                    counters["old_secrets_removed"] += 1
            store.upsert_case(case)
        except Exception:
            counters["errors"] += 1
            logger.exception("Failed to process Cherwell status", extra={"caseId": case.case_id, "cherwellChangeId": case.cherwell_change_id})
    return counters


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_environment()
    graph_client = GraphClient(settings.graph_base_url, ManagedIdentityTokenProvider())
    store = CosmosCaseStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_container)
    cherwell_client = _build_cherwell_client(settings)
    counters = run_status_scan(settings, store, graph_client, cherwell_client)
    logger.info("Cherwell status scan completed", extra=counters)


def _build_cherwell_client(settings: Settings) -> CherwellClient:
    required = {
        "CHERWELL_BASE_URL": settings.cherwell_base_url,
        "CHERWELL_TOKEN_URL": settings.cherwell_token_url,
        "CHERWELL_CLIENT_ID": settings.cherwell_client_id,
        "CHERWELL_CLIENT_SECRET": settings.cherwell_client_secret,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required Cherwell configuration: {', '.join(missing)}")
    return CherwellClient(
        base_url=settings.cherwell_base_url or "",
        token_url=settings.cherwell_token_url or "",
        client_id=settings.cherwell_client_id or "",
        client_secret=settings.cherwell_client_secret or "",
        change_template_id=settings.cherwell_change_template_id,
    )


if __name__ == "__main__":
    main()
