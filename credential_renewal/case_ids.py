from __future__ import annotations

import hashlib

from credential_renewal.models import AzureApplication, CredentialReference


def build_case_id(application: AzureApplication, credential: CredentialReference) -> str:
    raw = f"{application.object_id}:{credential.key_id}:{credential.end_date_time.isoformat()}:{credential.credential_type.value}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
