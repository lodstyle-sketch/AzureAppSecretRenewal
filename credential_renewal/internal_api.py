from __future__ import annotations

import requests


class InternalApplicationApi:
    def __init__(self, base_url: str, bearer_token: str | None = None, session: requests.Session | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token
        self.session = session or requests.Session()

    def get_application_details(self, service_management_reference: str) -> dict:
        headers = {"Accept": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        response = self.session.get(
            f"{self.base_url}/applications/{service_management_reference}/responsibles",
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        responsibles = payload.get("responsibles", [])
        if not isinstance(responsibles, list):
            raise ValueError("Internal API response must contain a responsibles list.")
        return payload
