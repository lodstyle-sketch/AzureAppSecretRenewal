from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from credential_renewal.azure_identity import ManagedIdentityTokenProvider
from credential_renewal.case_ids import build_case_id
from credential_renewal.config import Settings
from credential_renewal.cosmos_store import CosmosCaseStore
from credential_renewal.expiry import expiring_credentials
from credential_renewal.graph_client import GraphClient
from credential_renewal.internal_api import InternalApplicationApi
from credential_renewal.mailer import Mailer
from credential_renewal.models import AzureApplication, CaseState, CredentialCase, ResponsibleUser
from credential_renewal.tokens import create_case_token

logger = logging.getLogger(__name__)


def run_scan(settings: Settings, graph_client: GraphClient, internal_api: InternalApplicationApi, store, mailer: Mailer) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    counters = {"applications": 0, "expiring_credentials": 0, "cases_upserted": 0, "emails_sent": 0, "errors": 0}

    for graph_application in graph_client.list_applications():
        counters["applications"] += 1
        application = AzureApplication(
            object_id=graph_application["id"],
            app_id=graph_application["appId"],
            display_name=graph_application.get("displayName") or graph_application["appId"],
            service_management_reference=graph_application.get("serviceManagementReference"),
        )
        credentials = expiring_credentials(graph_application, now=now, window_days=settings.expiry_window_days)
        counters["expiring_credentials"] += len(credentials)
        for credential in credentials:
            try:
                if not application.service_management_reference:
                    raise ValueError("Application has no serviceManagementReference.")
                internal_details = internal_api.get_application_details(application.service_management_reference)
                responsible_users = _resolve_responsibles(graph_client, internal_details)
                case_id = build_case_id(application, credential)
                existing_case = store.get_case(case_id)
                case = existing_case or CredentialCase(
                    case_id=case_id,
                    azure_application=application,
                    old_credential=credential,
                    link_expires_at=credential.end_date_time,
                )
                case.internal_metadata = _without_responsibles(internal_details)
                case.responsible_users = responsible_users
                case.add_audit_event("scan_detected_expiring_credential", "automation-runbook")
                store.upsert_case(case)
                counters["cases_upserted"] += 1
                if not case.email_sent_at:
                    counters["emails_sent"] += _send_notifications(settings, mailer, case, responsible_users, store)
            except Exception:
                counters["errors"] += 1
                logger.exception("Failed to process expiring credential", extra={"applicationId": application.app_id, "credentialKeyId": credential.key_id})
    return counters


def _resolve_responsibles(graph_client: GraphClient, internal_details: dict[str, Any]) -> list[ResponsibleUser]:
    users: list[ResponsibleUser] = []
    for responsible in internal_details.get("responsibles", []):
        email = responsible.get("email") or responsible.get("upn")
        if not email:
            continue
        resolved = graph_client.resolve_user(email)
        if resolved:
            users.append(
                ResponsibleUser(
                    email=resolved.get("mail") or resolved.get("userPrincipalName") or email,
                    display_name=resolved.get("displayName"),
                    entra_id=resolved.get("id"),
                )
            )
    return users


def _without_responsibles(internal_details: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in internal_details.items() if key != "responsibles"}


def _send_notifications(settings: Settings, mailer: Mailer, case: CredentialCase, users: list[ResponsibleUser], store) -> int:
    token = create_case_token(case.case_id, case.link_expires_at, settings.link_signing_key)
    case_url = f"{settings.webapp_public_base_url}/cases/{case.case_id}?token={token}"
    sent = 0
    for user in users:
        mailer.send_case_notification(case, user, case_url)
        sent += 1
    case.email_sent_at = datetime.now(timezone.utc)
    case.add_audit_event("notification_sent", "automation-runbook", {"recipientCount": sent})
    store.upsert_case(case)
    return sent


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_environment()
    token_provider = ManagedIdentityTokenProvider()
    graph_client = GraphClient(settings.graph_base_url, token_provider)
    internal_api = InternalApplicationApi(settings.internal_api_base_url)
    store = CosmosCaseStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_container)
    mailer = Mailer(graph_client, settings.mail_shared_mailbox)
    counters = run_scan(settings, graph_client, internal_api, store, mailer)
    logger.info("Credential scan completed", extra=counters)


if __name__ == "__main__":
    main()
