from __future__ import annotations


class ManagedIdentityTokenProvider:
    def __init__(self, scope: str = "https://graph.microsoft.com/.default") -> None:
        from azure.identity import DefaultAzureCredential

        self._credential = DefaultAzureCredential()
        self._scope = scope

    def get_token(self) -> str:
        return self._credential.get_token(self._scope).token
