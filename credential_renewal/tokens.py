from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

from credential_renewal.models import parse_datetime


class TokenError(ValueError):
    pass


def create_case_token(case_id: str, expires_at: datetime, signing_key: str) -> str:
    payload = {
        "case_id": case_id,
        "expires_at": expires_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _sign(body, signing_key)
    return f"{body}.{signature}"


def validate_case_token(token: str, expected_case_id: str, signing_key: str, now: datetime | None = None) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise TokenError("Token is malformed.") from exc

    expected_signature = _sign(body, signing_key)
    if not hmac.compare_digest(signature, expected_signature):
        raise TokenError("Token signature is invalid.")

    payload = json.loads(_b64decode(body))
    if payload.get("case_id") != expected_case_id:
        raise TokenError("Token was issued for a different case.")

    expires_at = parse_datetime(payload["expires_at"])
    current_time = now or datetime.now(timezone.utc)
    if current_time.astimezone(timezone.utc) > expires_at:
        raise TokenError("Token has expired.")

    return payload


def _sign(body: str, signing_key: str) -> str:
    digest = hmac.new(signing_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
