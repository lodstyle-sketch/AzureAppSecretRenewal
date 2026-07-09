from __future__ import annotations

from datetime import datetime, timedelta, timezone

from credential_renewal.models import CaseState, CredentialCase, CredentialType


class CaseWorkflow:
    def __init__(self, store, graph_client, bitwarden_client) -> None:
        self.store = store
        self.graph_client = graph_client
        self.bitwarden_client = bitwarden_client

    def renew_secret(self, case_id: str, actor: str) -> CredentialCase:
        case = self._load_editable_case(case_id)
        if case.old_credential.credential_type != CredentialType.SECRET:
            raise ValueError("Only client secrets can be renewed automatically in version 1.")

        new_secret = self.graph_client.add_password(
            case.azure_application.object_id,
            display_name=f"Renewed by credential workflow for case {case.case_id}",
        )
        secret_text = new_secret.get("secretText")
        if not secret_text:
            raise ValueError("Graph did not return a secretText for the newly created password.")

        send = self.bitwarden_client.create_secret_send(
            name=f"{case.azure_application.display_name} renewed secret",
            secret_text=secret_text,
            expires_in=timedelta(days=7),
            max_access_count=1,
        )

        # Graph returns secretText only once. Store metadata only, never the secret value itself.
        case.new_credential = {
            "keyId": new_secret.get("keyId"),
            "displayName": new_secret.get("displayName"),
            "startDateTime": new_secret.get("startDateTime"),
            "endDateTime": new_secret.get("endDateTime"),
        }
        case.bitwarden_send = {"sendId": send.send_id, "accessUrl": send.access_url}
        self._mark_decision_window(case)
        case.state = CaseState.RENEWED_PENDING_OLD_SECRET_REMOVAL
        case.add_audit_event("renew_secret", actor, {"newCredentialKeyId": new_secret.get("keyId"), "bitwardenSendId": send.send_id})
        self.store.upsert_case(case)
        return case

    def defer(self, case_id: str, actor: str) -> CredentialCase:
        case = self._load_editable_case(case_id)
        now = datetime.now(timezone.utc)
        case.defer_until = now + timedelta(days=30)
        self._mark_decision_window(case, now)
        case.state = CaseState.DEFERRED
        case.add_audit_event("defer", actor, {"deferUntil": case.defer_until.isoformat()})
        self.store.upsert_case(case)
        return case

    def delete_old_secret(self, case_id: str, actor: str, confirmed: bool) -> CredentialCase:
        if not confirmed:
            raise ValueError("Old secret deletion requires explicit confirmation.")
        case = self._load_editable_case(case_id)
        if case.state != CaseState.RENEWED_PENDING_OLD_SECRET_REMOVAL:
            raise ValueError("The old secret can only be deleted after a new secret was created.")
        if case.old_credential.credential_type != CredentialType.SECRET:
            raise ValueError("Only old client secrets can be removed by this workflow.")

        self.graph_client.remove_password(case.azure_application.object_id, case.old_credential.key_id)
        case.old_secret_removed_at = datetime.now(timezone.utc)
        case.state = CaseState.RENEWED_OLD_SECRET_REMOVED
        case.add_audit_event("delete_old_secret", actor, {"oldCredentialKeyId": case.old_credential.key_id})
        self.store.upsert_case(case)
        return case

    def _load_editable_case(self, case_id: str) -> CredentialCase:
        case = self.store.get_case(case_id)
        if not case:
            raise KeyError(f"Case not found: {case_id}")
        now = datetime.now(timezone.utc)
        if now > case.link_expires_at:
            case.state = CaseState.EXPIRED
            self.store.upsert_case(case)
            raise ValueError("The original credential has expired; this case is no longer editable.")
        if case.decision_editable_until and now > case.decision_editable_until:
            raise ValueError("The decision change window has expired.")
        return case

    def _mark_decision_window(self, case: CredentialCase, now: datetime | None = None) -> None:
        decision_time = now or datetime.now(timezone.utc)
        if not case.first_decision_at:
            case.first_decision_at = decision_time
            case.decision_editable_until = decision_time + timedelta(days=30)
