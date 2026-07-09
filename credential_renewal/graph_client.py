from __future__ import annotations

import logging
from typing import Protocol

import requests


class TokenProvider(Protocol):
    def get_token(self) -> str:
        ...


class GraphClient:
    def __init__(self, base_url: str, token_provider: TokenProvider, session: requests.Session | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token_provider = token_provider
        self.session = session or requests.Session()
        self.logger = logging.getLogger(__name__)

    def list_applications(self) -> list[dict]:
        select = "id,appId,displayName,serviceManagementReference,passwordCredentials,keyCredentials"
        url = f"{self.base_url}/applications?$select={select}"
        applications: list[dict] = []
        while url:
            response = self.session.get(url, headers=self._headers(), timeout=60)
            response.raise_for_status()
            payload = response.json()
            applications.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink")
        return applications

    def resolve_user(self, email_or_upn: str) -> dict | None:
        escaped = email_or_upn.replace("'", "''")
        url = (
            f"{self.base_url}/users?"
            f"$select=id,displayName,mail,userPrincipalName&"
            f"$filter=mail eq '{escaped}' or userPrincipalName eq '{escaped}'"
        )
        response = self.session.get(url, headers=self._headers(), timeout=30)
        response.raise_for_status()
        matches = response.json().get("value", [])
        if len(matches) != 1:
            self.logger.warning("User lookup returned %s matches", len(matches), extra={"email_or_upn": email_or_upn})
            return None
        return matches[0]

    def add_password(self, application_object_id: str, display_name: str) -> dict:
        url = f"{self.base_url}/applications/{application_object_id}/addPassword"
        response = self.session.post(url, headers=self._headers(), json={"passwordCredential": {"displayName": display_name}}, timeout=30)
        response.raise_for_status()
        return response.json()

    def remove_password(self, application_object_id: str, key_id: str) -> None:
        url = f"{self.base_url}/applications/{application_object_id}/removePassword"
        response = self.session.post(url, headers=self._headers(), json={"keyId": key_id}, timeout=30)
        response.raise_for_status()

    def send_mail(self, mailbox: str, message: dict) -> None:
        url = f"{self.base_url}/users/{mailbox}/sendMail"
        response = self.session.post(url, headers=self._headers(), json={"message": message, "saveToSentItems": "true"}, timeout=30)
        response.raise_for_status()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token_provider.get_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
