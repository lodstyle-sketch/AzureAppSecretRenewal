from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from credential_renewal.models import CredentialReference, CredentialType, parse_datetime


def expiring_credentials(application: dict, now: datetime, window_days: int) -> list[CredentialReference]:
    window_end = now.astimezone(timezone.utc) + timedelta(days=window_days)
    credentials: list[CredentialReference] = []
    credentials.extend(
        _from_graph_credentials(
            application.get("passwordCredentials", []),
            CredentialType.SECRET,
            window_end,
            now,
        )
    )
    credentials.extend(
        _from_graph_credentials(
            application.get("keyCredentials", []),
            CredentialType.CERTIFICATE,
            window_end,
            now,
        )
    )
    return credentials


def _from_graph_credentials(
    graph_credentials: Iterable[dict],
    credential_type: CredentialType,
    window_end: datetime,
    now: datetime,
) -> list[CredentialReference]:
    result: list[CredentialReference] = []
    for credential in graph_credentials:
        end_date = credential.get("endDateTime")
        key_id = credential.get("keyId")
        if not end_date or not key_id:
            continue
        end_date_time = parse_datetime(end_date)
        if now.astimezone(timezone.utc) <= end_date_time <= window_end:
            result.append(
                CredentialReference(
                    key_id=key_id,
                    display_name=credential.get("displayName"),
                    credential_type=credential_type,
                    end_date_time=end_date_time,
                )
            )
    return result
