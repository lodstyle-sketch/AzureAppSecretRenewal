from __future__ import annotations

import base64
import json


def principal_from_easy_auth_header(header_value: str | None) -> str | None:
    if not header_value:
        return None
    try:
        payload = json.loads(base64.b64decode(header_value))
    except (ValueError, json.JSONDecodeError):
        return None

    for claim in payload.get("claims", []):
        claim_type = claim.get("typ", "")
        if claim_type.endswith("/claims/emailaddress") or claim_type in {"preferred_username", "upn"}:
            return claim.get("val")
    return payload.get("userDetails")


def is_authorized_responsible(principal_email: str, responsible_emails: list[str]) -> bool:
    normalized = principal_email.strip().lower()
    return normalized in {email.strip().lower() for email in responsible_emails}
