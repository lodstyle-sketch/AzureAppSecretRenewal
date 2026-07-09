from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from credential_renewal.models import ArchiveAction, ArchiveEntry, AzureApplication, CredentialCase, CredentialReference


def archive_id(action: ArchiveAction, source_id: str, timestamp: datetime | None = None) -> str:
    moment = (timestamp or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    raw = f"{action.value}:{source_id}:{moment}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def case_archive_entry(
    action: ArchiveAction,
    status: str,
    source: str,
    case: CredentialCase,
    actor: str | None = None,
    details: dict[str, Any] | None = None,
) -> ArchiveEntry:
    timestamp = datetime.now(timezone.utc)
    return ArchiveEntry(
        archive_id=archive_id(action, f"{case.case_id}:{case.old_credential.key_id}", timestamp),
        action=action,
        status=status,
        source=source,
        timestamp=timestamp,
        azure_application=case.azure_application,
        credential=case.old_credential,
        case_id=case.case_id,
        actor=actor,
        details=details or {},
    )


def app_deleted_archive_entry(application: AzureApplication, details: dict[str, Any] | None = None) -> ArchiveEntry:
    timestamp = datetime.now(timezone.utc)
    return ArchiveEntry(
        archive_id=archive_id(ArchiveAction.APP_DELETED, application.object_id, timestamp),
        action=ArchiveAction.APP_DELETED,
        status="deleted",
        source="automation-runbook",
        timestamp=timestamp,
        azure_application=application,
        credential=None,
        details=details or {},
    )
