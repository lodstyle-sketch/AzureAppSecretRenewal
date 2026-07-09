from __future__ import annotations

from credential_renewal.models import CredentialCase


class CosmosCaseStore:
    def __init__(self, account_url: str, database_name: str, container_name: str) -> None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        client = CosmosClient(account_url, credential=DefaultAzureCredential())
        self.container = client.get_database_client(database_name).get_container_client(container_name)

    def get_case(self, case_id: str) -> CredentialCase | None:
        try:
            document = self.container.read_item(item=case_id, partition_key=case_id)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise
        return CredentialCase.from_document(document)

    def upsert_case(self, case: CredentialCase) -> None:
        self.container.upsert_item(case.to_document())


class InMemoryCaseStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def get_case(self, case_id: str) -> CredentialCase | None:
        document = self.documents.get(case_id)
        return CredentialCase.from_document(document) if document else None

    def upsert_case(self, case: CredentialCase) -> None:
        self.documents[case.case_id] = case.to_document()
