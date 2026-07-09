from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from credential_renewal.cherwell_status_scan import run_status_scan
from credential_renewal.cosmos_store import InMemoryCaseStore
from credential_renewal.models import AzureApplication, CaseState, CredentialCase, CredentialReference, CredentialType, ResponsibleUser
from credential_renewal.reporting_export import flatten_case_for_log_analytics
from credential_renewal.runbook_scan import run_scan


class FakeScanGraph:
    def __init__(self, applications):
        self.applications = applications

    def list_applications(self):
        return self.applications

    def resolve_user(self, email_or_upn: str):
        return {"id": f"id-{email_or_upn}", "mail": email_or_upn, "displayName": email_or_upn.split("@")[0]}


class FakeInternalApi:
    def get_application_details(self, service_management_reference: str):
        return {
            "applicationCode": service_management_reference,
            "businessService": "Payments",
            "responsibles": [{"email": "owner.one@example.com"}, {"email": "owner.two@example.com"}],
        }


class FakeMailer:
    def __init__(self):
        self.sent = []

    def send_case_notification(self, case, recipient, case_url):
        self.sent.append((case.case_id, recipient.email, case_url))


class FakeCherwell:
    def __init__(self, status="Closed"):
        self.created = []
        self.status = status

    def create_change(self, case):
        self.created.append(case.case_id)
        return SimpleNamespace(change_id="chg-id-1", change_number="CHG0001", status="New")

    def get_change_status(self, change_id: str):
        return self.status


class FakeRemovalGraph:
    def __init__(self):
        self.removed = []

    def remove_password(self, application_object_id: str, key_id: str):
        self.removed.append((application_object_id, key_id))


class CherwellReportingTests(unittest.TestCase):
    def test_scan_skips_missing_service_management_reference_without_case_change_or_mail(self):
        store = InMemoryCaseStore()
        mailer = FakeMailer()
        cherwell = FakeCherwell()

        counters = run_scan(
            _settings(),
            FakeScanGraph([_graph_application(service_management_reference=None)]),
            FakeInternalApi(),
            store,
            mailer,
            cherwell,
        )

        self.assertEqual(counters["missing_internal_reference"], 1)
        self.assertEqual(store.list_cases(), [])
        self.assertEqual(mailer.sent, [])
        self.assertEqual(cherwell.created, [])

    def test_scan_creates_cherwell_change_once_for_valid_case(self):
        store = InMemoryCaseStore()
        mailer = FakeMailer()
        cherwell = FakeCherwell()
        graph = FakeScanGraph([_graph_application(service_management_reference="PAY")])

        first = run_scan(_settings(), graph, FakeInternalApi(), store, mailer, cherwell)
        second = run_scan(_settings(), graph, FakeInternalApi(), store, mailer, cherwell)
        case = store.list_cases()[0]

        self.assertEqual(first["cherwell_changes_created"], 1)
        self.assertEqual(second["cherwell_changes_created"], 0)
        self.assertEqual(cherwell.created, [case.case_id])
        self.assertEqual(case.cherwell_change_number, "CHG0001")
        self.assertEqual(case.state, CaseState.CHERWELL_PENDING)
        self.assertEqual(len(mailer.sent), 2)

    def test_completed_cherwell_change_deletes_old_secret_once_even_after_defer(self):
        store = InMemoryCaseStore()
        case = _case(CredentialType.SECRET)
        case.state = CaseState.DEFERRED
        case.cherwell_change_id = "chg-id-1"
        store.upsert_case(case)
        graph = FakeRemovalGraph()

        first = run_status_scan(_settings(), store, graph, FakeCherwell(status="Closed"))
        second = run_status_scan(_settings(), store, graph, FakeCherwell(status="Closed"))
        updated = store.get_case(case.case_id)

        self.assertEqual(first["old_secrets_removed"], 1)
        self.assertEqual(second["old_secrets_removed"], 0)
        self.assertEqual(graph.removed, [("app-object-id", "old-key")])
        self.assertEqual(updated.state, CaseState.CHERWELL_COMPLETED_OLD_SECRET_REMOVED)
        self.assertIsNotNone(updated.old_secret_removed_at)

    def test_completed_cherwell_change_for_certificate_requires_manual_removal(self):
        store = InMemoryCaseStore()
        case = _case(CredentialType.CERTIFICATE)
        case.cherwell_change_id = "chg-id-1"
        store.upsert_case(case)
        graph = FakeRemovalGraph()

        counters = run_status_scan(_settings(), store, graph, FakeCherwell(status="Closed"))
        updated = store.get_case(case.case_id)

        self.assertEqual(counters["manual_certificate_removals"], 1)
        self.assertEqual(graph.removed, [])
        self.assertEqual(updated.state, CaseState.MANUAL_CERTIFICATE_REMOVAL_REQUIRED)

    def test_reporting_export_flattens_multiple_owners_for_search(self):
        case = _case(CredentialType.SECRET)
        case.responsible_users = [
            ResponsibleUser(email="owner.one@example.com", display_name="Owner One"),
            ResponsibleUser(email="owner.two@example.com", display_name="Owner Two"),
        ]
        case.cherwell_change_id = "chg-id-1"
        case.cherwell_change_number = "CHG0001"

        row = flatten_case_for_log_analytics(case)

        self.assertIn("owner.one@example.com", row["OwnersText"])
        self.assertIn("Owner Two", row["OwnersText"])
        self.assertEqual(row["CherwellNumber"], "CHG0001")


def _settings():
    return SimpleNamespace(
        expiry_window_days=30,
        link_signing_key="test-signing-key",
        webapp_public_base_url="https://credential-renewal.example.com",
        cherwell_completed_statuses={"closed", "completed", "resolved"},
    )


def _graph_application(service_management_reference: str | None):
    return {
        "id": "app-object-id",
        "appId": "client-id",
        "displayName": "Payments API",
        "serviceManagementReference": service_management_reference,
        "passwordCredentials": [{"keyId": "old-key", "displayName": "old", "endDateTime": "2026-08-01T00:00:00Z"}],
        "keyCredentials": [],
    }


def _case(credential_type: CredentialType):
    return CredentialCase(
        case_id="case-1",
        azure_application=AzureApplication(
            object_id="app-object-id",
            app_id="client-id",
            display_name="Payments API",
            service_management_reference="PAY",
        ),
        old_credential=CredentialReference(
            key_id="old-key",
            display_name="old credential",
            credential_type=credential_type,
            end_date_time=datetime(2026, 12, 1, tzinfo=timezone.utc),
        ),
        link_expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        responsible_users=[ResponsibleUser(email="owner@example.com")],
    )


if __name__ == "__main__":
    unittest.main()
