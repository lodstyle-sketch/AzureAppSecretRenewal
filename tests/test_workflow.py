from datetime import datetime, timezone
import unittest

from credential_renewal.cosmos_store import InMemoryCaseStore
from credential_renewal.models import AzureApplication, CaseState, CredentialCase, CredentialReference, CredentialType, ResponsibleUser
from credential_renewal.workflow import CaseWorkflow


class FakeGraph:
    def __init__(self) -> None:
        self.removed: list[tuple[str, str]] = []

    def add_password(self, application_object_id: str, display_name: str) -> dict:
        return {
            "keyId": "new-key",
            "displayName": display_name,
            "startDateTime": "2026-07-09T00:00:00Z",
            "endDateTime": "2027-07-09T00:00:00Z",
            "secretText": "super-secret",
        }

    def remove_password(self, application_object_id: str, key_id: str) -> None:
        self.removed.append((application_object_id, key_id))


class FakeBitwarden:
    def __init__(self) -> None:
        self.secrets: list[str] = []

    def create_secret_send(self, name: str, secret_text: str, expires_in, max_access_count: int):
        self.secrets.append(secret_text)
        return type("Send", (), {"send_id": "send-1", "access_url": "https://bitwarden.example/send-1"})()


class WorkflowTests(unittest.TestCase):
    def test_renew_secret_keeps_old_secret_and_does_not_persist_secret_text(self):
        store, graph, bitwarden, case = _workflow_with_case()
        workflow = CaseWorkflow(store, graph, bitwarden)

        updated = workflow.renew_secret(case.case_id, "owner@example.com")
        document = store.documents[case.case_id]

        self.assertEqual(updated.state, CaseState.RENEWED_PENDING_OLD_SECRET_REMOVAL)
        self.assertEqual(graph.removed, [])
        self.assertEqual(bitwarden.secrets, ["super-secret"])
        self.assertNotIn("super-secret", str(document))
        self.assertEqual(document["new_credential"]["keyId"], "new-key")

    def test_delete_old_secret_requires_renewal_and_confirmation(self):
        store, graph, bitwarden, case = _workflow_with_case()
        workflow = CaseWorkflow(store, graph, bitwarden)

        with self.assertRaises(ValueError):
            workflow.delete_old_secret(case.case_id, "owner@example.com", confirmed=True)

        workflow.renew_secret(case.case_id, "owner@example.com")

        with self.assertRaises(ValueError):
            workflow.delete_old_secret(case.case_id, "owner@example.com", confirmed=False)

        updated = workflow.delete_old_secret(case.case_id, "owner@example.com", confirmed=True)
        self.assertEqual(updated.state, CaseState.RENEWED_OLD_SECRET_REMOVED)
        self.assertEqual(graph.removed, [("app-object-id", "old-key")])

    def test_defer_sets_one_month_decision_state(self):
        store, graph, bitwarden, case = _workflow_with_case()
        workflow = CaseWorkflow(store, graph, bitwarden)

        updated = workflow.defer(case.case_id, "owner@example.com")

        self.assertEqual(updated.state, CaseState.DEFERRED)
        self.assertIsNotNone(updated.defer_until)
        self.assertIsNotNone(updated.decision_editable_until)


def _workflow_with_case():
    store = InMemoryCaseStore()
    graph = FakeGraph()
    bitwarden = FakeBitwarden()
    case = CredentialCase(
        case_id="case-1",
        azure_application=AzureApplication(
            object_id="app-object-id",
            app_id="client-id",
            display_name="Payments API",
            service_management_reference="PAY",
        ),
        old_credential=CredentialReference(
            key_id="old-key",
            display_name="old secret",
            credential_type=CredentialType.SECRET,
            end_date_time=datetime(2026, 12, 1, tzinfo=timezone.utc),
        ),
        link_expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        responsible_users=[ResponsibleUser(email="owner@example.com")],
    )
    store.upsert_case(case)
    return store, graph, bitwarden, case


if __name__ == "__main__":
    unittest.main()
