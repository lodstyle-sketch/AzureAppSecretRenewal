from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class CredentialType(StrEnum):
    SECRET = "secret"
    CERTIFICATE = "certificate"


class CaseState(StrEnum):
    OPEN = "open"
    CHERWELL_PENDING = "cherwell_pending"
    RENEWED_PENDING_OLD_SECRET_REMOVAL = "renewed_pending_old_secret_removal"
    RENEWED_OLD_SECRET_REMOVED = "renewed_old_secret_removed"
    CHERWELL_COMPLETED_OLD_SECRET_REMOVED = "cherwell_completed_old_secret_removed"
    MANUAL_CERTIFICATE_REMOVAL_REQUIRED = "manual_certificate_removal_required"
    DEFERRED = "deferred"
    ERROR = "error"
    EXPIRED = "expired"


class AppOverviewStatus(StrEnum):
    ACTIVE = "active"
    DELETED = "deleted"


class ArchiveAction(StrEnum):
    SECRET_RENEWED = "secret_renewed"
    OLD_SECRET_DELETED = "old_secret_deleted"
    APP_DELETED = "app_deleted"


@dataclass(frozen=True)
class ResponsibleUser:
    email: str
    display_name: str | None = None
    entra_id: str | None = None


@dataclass(frozen=True)
class AzureApplication:
    object_id: str
    app_id: str
    display_name: str
    service_management_reference: str | None


@dataclass(frozen=True)
class CredentialReference:
    key_id: str
    display_name: str | None
    credential_type: CredentialType
    end_date_time: datetime


@dataclass
class AuditEvent:
    action: str
    actor: str
    timestamp: datetime
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class AppOverview:
    app_object_id: str
    app_id: str
    display_name: str
    service_management_reference: str | None
    status: AppOverviewStatus
    secret_count: int
    certificate_count: int
    next_secret_expiry: datetime | None = None
    next_certificate_expiry: datetime | None = None
    owners: list[ResponsibleUser] = field(default_factory=list)
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    deleted_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_document(self) -> dict[str, Any]:
        document = asdict(self)
        document["id"] = self.app_object_id
        return _encode_datetimes(document)

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "AppOverview":
        return cls(
            app_object_id=document["app_object_id"],
            app_id=document["app_id"],
            display_name=document["display_name"],
            service_management_reference=document.get("service_management_reference"),
            status=AppOverviewStatus(document.get("status", AppOverviewStatus.ACTIVE)),
            secret_count=int(document.get("secret_count", 0)),
            certificate_count=int(document.get("certificate_count", 0)),
            next_secret_expiry=parse_optional_datetime(document.get("next_secret_expiry")),
            next_certificate_expiry=parse_optional_datetime(document.get("next_certificate_expiry")),
            owners=[ResponsibleUser(**owner) for owner in document.get("owners", [])],
            last_seen_at=parse_datetime(document["last_seen_at"]) if document.get("last_seen_at") else datetime.now(timezone.utc),
            deleted_at=parse_optional_datetime(document.get("deleted_at")),
            updated_at=parse_datetime(document["updated_at"]) if document.get("updated_at") else datetime.now(timezone.utc),
        )


@dataclass
class ArchiveEntry:
    archive_id: str
    action: ArchiveAction
    status: str
    source: str
    timestamp: datetime
    azure_application: AzureApplication
    credential: CredentialReference | None = None
    case_id: str | None = None
    actor: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        document = asdict(self)
        document["id"] = self.archive_id
        return _encode_datetimes(document)

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "ArchiveEntry":
        app = document["azure_application"]
        credential = document.get("credential")
        return cls(
            archive_id=document["archive_id"],
            action=ArchiveAction(document["action"]),
            status=document["status"],
            source=document["source"],
            timestamp=parse_datetime(document["timestamp"]),
            azure_application=AzureApplication(**app),
            credential=(
                CredentialReference(
                    key_id=credential["key_id"],
                    display_name=credential.get("display_name"),
                    credential_type=CredentialType(credential["credential_type"]),
                    end_date_time=parse_datetime(credential["end_date_time"]),
                )
                if credential
                else None
            ),
            case_id=document.get("case_id"),
            actor=document.get("actor"),
            details=document.get("details", {}),
        )


@dataclass
class CredentialCase:
    case_id: str
    azure_application: AzureApplication
    old_credential: CredentialReference
    link_expires_at: datetime
    state: CaseState = CaseState.OPEN
    internal_metadata: dict[str, Any] = field(default_factory=dict)
    responsible_users: list[ResponsibleUser] = field(default_factory=list)
    new_credential: dict[str, Any] | None = None
    bitwarden_send: dict[str, Any] | None = None
    cherwell_change_id: str | None = None
    cherwell_change_number: str | None = None
    cherwell_status: str | None = None
    cherwell_created_at: datetime | None = None
    cherwell_last_checked_at: datetime | None = None
    cherwell_completed_at: datetime | None = None
    defer_until: datetime | None = None
    first_decision_at: datetime | None = None
    decision_editable_until: datetime | None = None
    old_secret_removed_at: datetime | None = None
    audit_events: list[AuditEvent] = field(default_factory=list)
    email_sent_at: datetime | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_audit_event(self, action: str, actor: str, details: dict[str, Any] | None = None) -> None:
        self.audit_events.append(
            AuditEvent(
                action=action,
                actor=actor,
                timestamp=datetime.now(timezone.utc),
                details=details or {},
            )
        )
        self.updated_at = datetime.now(timezone.utc)

    def to_document(self) -> dict[str, Any]:
        document = asdict(self)
        document["id"] = self.case_id
        return _encode_datetimes(document)

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "CredentialCase":
        app = document["azure_application"]
        old = document["old_credential"]
        return cls(
            case_id=document["case_id"],
            azure_application=AzureApplication(**app),
            old_credential=CredentialReference(
                key_id=old["key_id"],
                display_name=old.get("display_name"),
                credential_type=CredentialType(old["credential_type"]),
                end_date_time=parse_datetime(old["end_date_time"]),
            ),
            link_expires_at=parse_datetime(document["link_expires_at"]),
            state=CaseState(document.get("state", CaseState.OPEN)),
            internal_metadata=document.get("internal_metadata", {}),
            responsible_users=[ResponsibleUser(**user) for user in document.get("responsible_users", [])],
            new_credential=document.get("new_credential"),
            bitwarden_send=document.get("bitwarden_send"),
            cherwell_change_id=document.get("cherwell_change_id"),
            cherwell_change_number=document.get("cherwell_change_number"),
            cherwell_status=document.get("cherwell_status"),
            cherwell_created_at=parse_optional_datetime(document.get("cherwell_created_at")),
            cherwell_last_checked_at=parse_optional_datetime(document.get("cherwell_last_checked_at")),
            cherwell_completed_at=parse_optional_datetime(document.get("cherwell_completed_at")),
            defer_until=parse_optional_datetime(document.get("defer_until")),
            first_decision_at=parse_optional_datetime(document.get("first_decision_at")),
            decision_editable_until=parse_optional_datetime(document.get("decision_editable_until")),
            old_secret_removed_at=parse_optional_datetime(document.get("old_secret_removed_at")),
            audit_events=[
                AuditEvent(
                    action=event["action"],
                    actor=event["actor"],
                    timestamp=parse_datetime(event["timestamp"]),
                    details=event.get("details", {}),
                )
                for event in document.get("audit_events", [])
            ],
            email_sent_at=parse_optional_datetime(document.get("email_sent_at")),
            updated_at=parse_datetime(document["updated_at"]) if document.get("updated_at") else datetime.now(timezone.utc),
        )


def parse_optional_datetime(value: str | None) -> datetime | None:
    return parse_datetime(value) if value else None


def parse_datetime(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _encode_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, list):
        return [_encode_datetimes(item) for item in value]
    if isinstance(value, dict):
        return {key: _encode_datetimes(item) for key, item in value.items()}
    if isinstance(value, StrEnum):
        return value.value
    return value
