from __future__ import annotations

from credential_renewal.models import AppOverview, ArchiveEntry, CredentialCase


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

    def list_cases(self) -> list[CredentialCase]:
        documents = self.container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True)
        return [CredentialCase.from_document(document) for document in documents]


class InMemoryCaseStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def get_case(self, case_id: str) -> CredentialCase | None:
        document = self.documents.get(case_id)
        return CredentialCase.from_document(document) if document else None

    def upsert_case(self, case: CredentialCase) -> None:
        self.documents[case.case_id] = case.to_document()

    def list_cases(self) -> list[CredentialCase]:
        return [CredentialCase.from_document(document) for document in self.documents.values()]


class CosmosAppOverviewStore:
    def __init__(self, account_url: str, database_name: str, container_name: str) -> None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        client = CosmosClient(account_url, credential=DefaultAzureCredential())
        self.container = client.get_database_client(database_name).get_container_client(container_name)

    def get_app(self, app_object_id: str) -> AppOverview | None:
        try:
            document = self.container.read_item(item=app_object_id, partition_key=app_object_id)
        except Exception as exc:
            if getattr(exc, "status_code", None) == 404:
                return None
            raise
        return AppOverview.from_document(document)

    def upsert_app(self, overview: AppOverview) -> None:
        self.container.upsert_item(overview.to_document())

    def list_apps(self) -> list[AppOverview]:
        documents = self.container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True)
        return [AppOverview.from_document(document) for document in documents]


class CosmosArchiveStore:
    def __init__(self, account_url: str, database_name: str, container_name: str) -> None:
        from azure.cosmos import CosmosClient
        from azure.identity import DefaultAzureCredential

        client = CosmosClient(account_url, credential=DefaultAzureCredential())
        self.container = client.get_database_client(database_name).get_container_client(container_name)

    def upsert_archive_entry(self, entry: ArchiveEntry) -> None:
        self.container.upsert_item(entry.to_document())

    def list_archive_entries(self) -> list[ArchiveEntry]:
        documents = self.container.query_items(query="SELECT * FROM c", enable_cross_partition_query=True)
        return [ArchiveEntry.from_document(document) for document in documents]


class InMemoryAppOverviewStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def get_app(self, app_object_id: str) -> AppOverview | None:
        document = self.documents.get(app_object_id)
        return AppOverview.from_document(document) if document else None

    def upsert_app(self, overview: AppOverview) -> None:
        self.documents[overview.app_object_id] = overview.to_document()

    def list_apps(self) -> list[AppOverview]:
        return [AppOverview.from_document(document) for document in self.documents.values()]


class InMemoryArchiveStore:
    def __init__(self) -> None:
        self.documents: dict[str, dict] = {}

    def upsert_archive_entry(self, entry: ArchiveEntry) -> None:
        self.documents[entry.archive_id] = entry.to_document()

    def list_archive_entries(self) -> list[ArchiveEntry]:
        return [ArchiveEntry.from_document(document) for document in self.documents.values()]
