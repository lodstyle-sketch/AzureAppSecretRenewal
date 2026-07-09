from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from credential_renewal.models import CredentialCase


@dataclass(frozen=True)
class CherwellChange:
    change_id: str
    change_number: str
    status: str


class CherwellClient:
    def __init__(
        self,
        base_url: str,
        token_url: str,
        client_id: str,
        client_secret: str,
        change_template_id: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.change_template_id = change_template_id
        self.session = session or requests.Session()
        self._access_token: str | None = None

    def create_change(self, case: CredentialCase) -> CherwellChange:
        payload = {
            "templateId": self.change_template_id,
            "summary": f"App Registration credential expiry: {case.azure_application.display_name}",
            "description": self._description(case),
            "externalReference": case.case_id,
            "serviceManagementReference": case.azure_application.service_management_reference,
            "application": {
                "objectId": case.azure_application.object_id,
                "appId": case.azure_application.app_id,
                "displayName": case.azure_application.display_name,
            },
            "credential": {
                "keyId": case.old_credential.key_id,
                "type": case.old_credential.credential_type.value,
                "expiresAt": case.old_credential.end_date_time.isoformat(),
            },
            "owners": [{"email": user.email, "displayName": user.display_name} for user in case.responsible_users],
            "internalMetadata": case.internal_metadata,
        }
        response = self.session.post(f"{self.base_url}/changes", headers=self._headers(), json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        return CherwellChange(
            change_id=str(body.get("id") or body.get("changeId")),
            change_number=str(body.get("number") or body.get("changeNumber")),
            status=str(body.get("status") or "New"),
        )

    def get_change_status(self, change_id: str) -> str:
        response = self.session.get(f"{self.base_url}/changes/{change_id}", headers=self._headers(), timeout=30)
        response.raise_for_status()
        body = response.json()
        return str(body.get("status") or body.get("state") or "")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _token(self) -> str:
        if self._access_token:
            return self._access_token
        response = self.session.post(
            self.token_url,
            data={"grant_type": "client_credentials", "client_id": self.client_id, "client_secret": self.client_secret},
            timeout=30,
        )
        response.raise_for_status()
        self._access_token = response.json()["access_token"]
        return self._access_token

    def _description(self, case: CredentialCase) -> str:
        owners = ", ".join(user.email for user in case.responsible_users) or "No resolved owners"
        return (
            f"Application: {case.azure_application.display_name}\n"
            f"App ID: {case.azure_application.app_id}\n"
            f"Service management reference: {case.azure_application.service_management_reference}\n"
            f"Credential type: {case.old_credential.credential_type.value}\n"
            f"Credential key ID: {case.old_credential.key_id}\n"
            f"Credential expiry: {case.old_credential.end_date_time.astimezone(timezone.utc).isoformat()}\n"
            f"Owners: {owners}\n"
            f"Case ID: {case.case_id}"
        )


def apply_created_change(case: CredentialCase, change: CherwellChange, actor: str = "automation-runbook") -> None:
    now = datetime.now(timezone.utc)
    case.cherwell_change_id = change.change_id
    case.cherwell_change_number = change.change_number
    case.cherwell_status = change.status
    case.cherwell_created_at = now
    case.add_audit_event("cherwell_change_created", actor, {"changeId": change.change_id, "changeNumber": change.change_number, "status": change.status})
