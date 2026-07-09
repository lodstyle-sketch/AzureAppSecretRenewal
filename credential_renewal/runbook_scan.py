from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import Any

from credential_renewal.archive import app_deleted_archive_entry
from credential_renewal.azure_identity import ManagedIdentityTokenProvider
from credential_renewal.case_ids import build_case_id
from credential_renewal.cherwell_client import CherwellClient, apply_created_change
from credential_renewal.config import Settings
from credential_renewal.cosmos_store import CosmosAppOverviewStore, CosmosArchiveStore, CosmosCaseStore
from credential_renewal.expiry import expiring_credentials
from credential_renewal.graph_client import GraphClient
from credential_renewal.internal_api import InternalApplicationApi
from credential_renewal.mailer import Mailer
from credential_renewal.models import AppOverview, AppOverviewStatus, AzureApplication, CaseState, CredentialCase, CredentialReference, ResponsibleUser
from credential_renewal.models import parse_datetime
from credential_renewal.tokens import create_case_token

logger = logging.getLogger(__name__)


def run_scan(
    settings: Settings,
    graph_client: GraphClient,
    internal_api: InternalApplicationApi,
    store,
    mailer: Mailer,
    overview_store=None,
    archive_store=None,
    cherwell_client=None,
) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    scan_id = now.isoformat()
    seen_app_object_ids: set[str] = set()
    summary_items: list[dict[str, Any]] = []
    counters = {
        "applications": 0,
        "expiring_credentials": 0,
        "missing_internal_reference": 0,
        "overview_upserted": 0,
        "deleted_apps_archived": 0,
        "cherwell_changes_created": 0,
        "cases_upserted": 0,
        "emails_sent": 0,
        "summary_emails_sent": 0,
        "errors": 0,
    }

    for graph_application in graph_client.list_applications():
        counters["applications"] += 1
        application = AzureApplication(
            object_id=graph_application["id"],
            app_id=graph_application["appId"],
            display_name=graph_application.get("displayName") or graph_application["appId"],
            service_management_reference=graph_application.get("serviceManagementReference"),
        )
        seen_app_object_ids.add(application.object_id)
        if overview_store:
            overview_store.upsert_app(_build_overview(application, graph_application, now))
            counters["overview_upserted"] += 1

        credentials = expiring_credentials(graph_application, now=now, window_days=settings.expiry_window_days)
        counters["expiring_credentials"] += len(credentials)
        for credential in credentials:
            summary_item = _summary_item(application, credential)
            try:
                if not application.service_management_reference:
                    counters["missing_internal_reference"] += 1
                    summary_item["missing_reference"] = True
                    summary_items.append(summary_item)
                    logger.warning(
                        "Skipping credential workflow because application has no serviceManagementReference",
                        extra={"applicationId": application.app_id, "credentialKeyId": credential.key_id},
                    )
                    continue

                internal_details = internal_api.get_application_details(application.service_management_reference)
                responsible_users = _resolve_responsibles(graph_client, internal_details)
                _update_overview_owners(overview_store, application.object_id, responsible_users)
                summary_item["owners"] = ", ".join(user.email for user in responsible_users)
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
                if cherwell_client and not case.cherwell_change_id:
                    change = cherwell_client.create_change(case)
                    apply_created_change(case, change)
                    case.state = CaseState.CHERWELL_PENDING
                    counters["cherwell_changes_created"] += 1
                store.upsert_case(case)
                summary_item["case_state"] = case.state.value
                summary_item["cherwell_number"] = case.cherwell_change_number or ""
                counters["cases_upserted"] += 1
                if not case.email_sent_at:
                    counters["emails_sent"] += _send_notifications(settings, mailer, case, responsible_users, store)
                summary_items.append(summary_item)
            except Exception:
                counters["errors"] += 1
                summary_item["error"] = "processing_failed"
                summary_items.append(summary_item)
                logger.exception("Failed to process expiring credential", extra={"applicationId": application.app_id, "credentialKeyId": credential.key_id})

    if overview_store and archive_store:
        counters["deleted_apps_archived"] = _mark_deleted_apps(overview_store, archive_store, seen_app_object_ids, now, scan_id)
    try:
        _send_department_summary(settings, mailer, counters, summary_items, now)
        counters["summary_emails_sent"] = 1
    except Exception:
        counters["errors"] += 1
        logger.exception("Failed to send department summary email")
    return counters


def _build_overview(application: AzureApplication, graph_application: dict[str, Any], now: datetime) -> AppOverview:
    password_credentials = graph_application.get("passwordCredentials", [])
    key_credentials = graph_application.get("keyCredentials", [])
    return AppOverview(
        app_object_id=application.object_id,
        app_id=application.app_id,
        display_name=application.display_name,
        service_management_reference=application.service_management_reference,
        status=AppOverviewStatus.ACTIVE,
        secret_count=len(password_credentials),
        certificate_count=len(key_credentials),
        next_secret_expiry=_next_expiry(password_credentials),
        next_certificate_expiry=_next_expiry(key_credentials),
        last_seen_at=now,
        deleted_at=None,
        updated_at=now,
    )


def _next_expiry(credentials: list[dict[str, Any]]) -> datetime | None:
    expiries = [parse_datetime(credential["endDateTime"]) for credential in credentials if credential.get("endDateTime")]
    return min(expiries) if expiries else None


def _update_overview_owners(overview_store, app_object_id: str, responsible_users: list[ResponsibleUser]) -> None:
    if not overview_store:
        return
    overview = overview_store.get_app(app_object_id)
    if overview:
        overview.owners = responsible_users
        overview.updated_at = datetime.now(timezone.utc)
        overview_store.upsert_app(overview)


def _summary_item(application: AzureApplication, credential: CredentialReference) -> dict[str, Any]:
    return {
        "app_name": application.display_name,
        "app_id": application.app_id,
        "service_management_reference": application.service_management_reference or "missing",
        "credential_type": credential.credential_type.value,
        "credential_name": credential.display_name or credential.key_id,
        "credential_key_id": credential.key_id,
        "expiry": credential.end_date_time.isoformat(),
        "owners": "",
        "case_state": "",
        "cherwell_number": "",
        "missing_reference": False,
        "error": "",
    }


def _mark_deleted_apps(overview_store, archive_store, seen_app_object_ids: set[str], now: datetime, scan_id: str) -> int:
    archived = 0
    for overview in overview_store.list_apps():
        if overview.app_object_id in seen_app_object_ids or overview.status == AppOverviewStatus.DELETED:
            continue
        overview.status = AppOverviewStatus.DELETED
        overview.deleted_at = now
        overview.updated_at = now
        overview_store.upsert_app(overview)
        application = AzureApplication(
            object_id=overview.app_object_id,
            app_id=overview.app_id,
            display_name=overview.display_name,
            service_management_reference=overview.service_management_reference,
        )
        archive_store.upsert_archive_entry(app_deleted_archive_entry(application, {"scanId": scan_id}))
        archived += 1
    return archived


def _send_department_summary(settings: Settings, mailer: Mailer, counters: dict[str, int], summary_items: list[dict[str, Any]], now: datetime) -> None:
    rows = "".join(_summary_row(item) for item in summary_items)
    if not rows:
        rows = "<tr><td colspan=\"10\">No credentials expire inside the configured window.</td></tr>"
    body = (
        f"<h2>App Registration credential expiry summary</h2>"
        f"<p>Scan completed at {escape(now.isoformat())}.</p>"
        f"<p>Applications scanned: {counters['applications']} | Expiring credentials: {counters['expiring_credentials']} | "
        f"Missing internal references: {counters['missing_internal_reference']} | Cherwell changes: {counters['cherwell_changes_created']} | "
        f"Errors: {counters['errors']}</p>"
        "<table border=\"1\" cellpadding=\"4\" cellspacing=\"0\">"
        "<thead><tr><th>Azure App Name</th><th>App ID</th><th>Internal Code</th><th>Credential Type</th>"
        "<th>Credential</th><th>Key ID</th><th>Expiry</th><th>Owners</th><th>Cherwell</th><th>Case State / Notes</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>"
    )
    mailer.send_department_summary(settings.department_summary_mailbox, "App Registration credential expiry summary", body)


def _summary_row(item: dict[str, Any]) -> str:
    notes = item.get("case_state") or ""
    if item.get("missing_reference"):
        notes = "missing serviceManagementReference"
    if item.get("error"):
        notes = item["error"]
    values = [
        item.get("app_name", ""),
        item.get("app_id", ""),
        item.get("service_management_reference", ""),
        item.get("credential_type", ""),
        item.get("credential_name", ""),
        item.get("credential_key_id", ""),
        item.get("expiry", ""),
        item.get("owners", ""),
        item.get("cherwell_number", ""),
        notes,
    ]
    return "<tr>" + "".join(f"<td>{escape(str(value))}</td>" for value in values) + "</tr>"


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
    overview_store = CosmosAppOverviewStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_app_overview_container)
    archive_store = CosmosArchiveStore(settings.cosmos_account_url, settings.cosmos_database, settings.cosmos_archive_container)
    mailer = Mailer(graph_client, settings.mail_shared_mailbox)
    cherwell_client = _build_cherwell_client(settings)
    counters = run_scan(settings, graph_client, internal_api, store, mailer, overview_store, archive_store, cherwell_client)
    logger.info("Credential scan completed", extra=counters)


def _build_cherwell_client(settings: Settings) -> CherwellClient | None:
    required = [
        settings.cherwell_base_url,
        settings.cherwell_token_url,
        settings.cherwell_client_id,
        settings.cherwell_client_secret,
    ]
    if not all(required):
        logger.warning("Cherwell integration is not fully configured; changes will not be created.")
        return None
    return CherwellClient(
        base_url=settings.cherwell_base_url or "",
        token_url=settings.cherwell_token_url or "",
        client_id=settings.cherwell_client_id or "",
        client_secret=settings.cherwell_client_secret or "",
        change_template_id=settings.cherwell_change_template_id,
    )


if __name__ == "__main__":
    main()
