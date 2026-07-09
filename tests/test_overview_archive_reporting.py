from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from credential_renewal.archive import case_archive_entry
from credential_renewal.cosmos_store import InMemoryAppOverviewStore, InMemoryArchiveStore, InMemoryCaseStore
from credential_renewal.models import ArchiveAction, AzureApplication, CredentialCase, CredentialReference, CredentialType, ResponsibleUser
from credential_renewal.reporting_export import flatten_archive_for_log_analytics, flatten_overview_for_log_analytics
from credential_renewal.runbook_scan import run_scan
from credential_renewal.workflow import CaseWorkflow


class FakeGraph:
    def __init__(self, applications):
        self.applications = applications
        self.removed = []

    def list_applications(self):
        return self.applications

    def resolve_user(self, email_or_upn: str):
        return {"id": f"id-{email_or_upn}", "mail": email_or_upn, "displayName": email_or_upn.split("@")[0]}

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


class FakeInternalApi:
    def get_application_details(self, service_management_reference: str):
        return {"applicationCode": service_management_reference, "responsibles": [{"email": "owner@example.com"}]}


class FakeMailer:
    def __init__(self):
        self.case_notifications = []
        self.summaries = []

    def send_case_notification(self, case, recipient, case_url):
        self.case_notifications.append((case.case_id, recipient.email, case_url))

    def send_department_summary(self, recipient_mailbox: str, subject: str, html_body: str):
        self.summaries.append((recipient_mailbox, subject, html_body))


class FakeBitwarden:
    def create_secret_send(self, name: str, secret_text: str, expires_in, max_access_count: int):
        return SimpleNamespace(send_id="send-1", access_url="https://bitwarden.example/send-1")


class OverviewArchiveReportingTests(unittest.TestCase):
    def test_scan_writes_overview_for_every_app_and_skips_missing_reference_cases(self):
        case_store = InMemoryCaseStore()
        overview_store = InMemoryAppOverviewStore()
        archive_store = InMemoryArchiveStore()
        mailer = FakeMailer()
        graph = FakeGraph([_graph_app("app-1", "App With Code", "PAY"), _graph_app("app-2", "App Missing Code", None)])

        counters = run_scan(_settings(), graph, FakeInternalApi(), case_store, mailer, overview_store, archive_store)

        self.assertEqual(counters["overview_upserted"], 2)
        self.assertEqual(counters["missing_internal_reference"], 1)
        self.assertEqual(len(overview_store.list_apps()), 2)
        self.assertEqual(len(case_store.list_cases()), 1)
        self.assertEqual(len(mailer.case_notifications), 1)
        self.assertEqual(len(mailer.summaries), 1)
        self.assertIn("App Missing Code", mailer.summaries[0][2])
        self.assertIn("missing serviceManagementReference", mailer.summaries[0][2])

    def test_scan_sends_empty_department_summary_when_nothing_expires(self):
        mailer = FakeMailer()
        graph = FakeGraph([_graph_app("app-1", "Long Lived App", "PAY", end_date="2027-12-01T00:00:00Z")])

        run_scan(_settings(), graph, FakeInternalApi(), InMemoryCaseStore(), mailer, InMemoryAppOverviewStore(), InMemoryArchiveStore())

        self.assertEqual(len(mailer.summaries), 1)
        self.assertIn("No credentials expire", mailer.summaries[0][2])

    def test_deleted_app_is_marked_and_archived(self):
        overview_store = InMemoryAppOverviewStore()
        archive_store = InMemoryArchiveStore()
        mailer = FakeMailer()
        run_scan(_settings(), FakeGraph([_graph_app("old-app", "Deleted Later", "OLD")]), FakeInternalApi(), InMemoryCaseStore(), mailer, overview_store, archive_store)

        run_scan(_settings(), FakeGraph([]), FakeInternalApi(), InMemoryCaseStore(), mailer, overview_store, archive_store)

        overview = overview_store.get_app("old-app")
        archives = archive_store.list_archive_entries()
        self.assertEqual(overview.status.value, "deleted")
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].status, "deleted")
        self.assertEqual(archives[0].action, ArchiveAction.APP_DELETED)

    def test_workflow_archives_renewal_and_old_secret_deletion(self):
        case_store = InMemoryCaseStore()
        archive_store = InMemoryArchiveStore()
        graph = FakeGraph([])
        case = _case()
        case_store.upsert_case(case)
        workflow = CaseWorkflow(case_store, graph, FakeBitwarden(), archive_store)

        workflow.renew_secret(case.case_id, "owner@example.com")
        workflow.delete_old_secret(case.case_id, "owner@example.com", confirmed=True)

        actions = [entry.action for entry in archive_store.list_archive_entries()]
        self.assertEqual(actions, [ArchiveAction.SECRET_RENEWED, ArchiveAction.OLD_SECRET_DELETED])
        self.assertNotIn("super-secret", str(archive_store.documents))

    def test_reporting_flattens_overview_and_archive(self):
        overview_store = InMemoryAppOverviewStore()
        archive_store = InMemoryArchiveStore()
        run_scan(_settings(), FakeGraph([_graph_app("app-1", "Payments API", "PAY")]), FakeInternalApi(), InMemoryCaseStore(), FakeMailer(), overview_store, archive_store)
        overview = overview_store.list_apps()[0]
        archive = case_archive_entry(ArchiveAction.OLD_SECRET_DELETED, "deleted", "test", _case(), "owner@example.com")

        overview_row = flatten_overview_for_log_analytics(overview)
        archive_row = flatten_archive_for_log_analytics(archive)

        self.assertEqual(overview_row["AzureAppName"], "Payments API")
        self.assertTrue(overview_row["HasInternalCode"])
        self.assertEqual(archive_row["Action"], "old_secret_deleted")


def _settings():
    return SimpleNamespace(
        expiry_window_days=30,
        link_signing_key="test-signing-key",
        webapp_public_base_url="https://credential-renewal.example.com",
        department_summary_mailbox="department@example.com",
    )


def _graph_app(object_id: str, display_name: str, service_management_reference: str | None, end_date: str = "2026-08-01T00:00:00Z"):
    return {
        "id": object_id,
        "appId": f"client-{object_id}",
        "displayName": display_name,
        "serviceManagementReference": service_management_reference,
        "passwordCredentials": [{"keyId": f"key-{object_id}", "displayName": "client secret", "endDateTime": end_date}],
        "keyCredentials": [],
    }


def _case():
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
            display_name="old secret",
            credential_type=CredentialType.SECRET,
            end_date_time=datetime(2026, 12, 1, tzinfo=timezone.utc),
        ),
        link_expires_at=datetime(2026, 12, 1, tzinfo=timezone.utc),
        responsible_users=[ResponsibleUser(email="owner@example.com")],
    )


if __name__ == "__main__":
    unittest.main()
