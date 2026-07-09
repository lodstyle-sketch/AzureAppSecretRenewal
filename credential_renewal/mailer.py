from __future__ import annotations

from credential_renewal.models import CredentialCase, ResponsibleUser


class Mailer:
    def __init__(self, graph_client, shared_mailbox: str) -> None:
        self.graph_client = graph_client
        self.shared_mailbox = shared_mailbox

    def send_case_notification(self, case: CredentialCase, recipient: ResponsibleUser, case_url: str) -> None:
        subject = f"Action required: credential expiry for {case.azure_application.display_name}"
        body = (
            f"<p>Hello {recipient.display_name or recipient.email},</p>"
            f"<p>An App Registration credential is expiring and needs a decision.</p>"
            f"<ul>"
            f"<li>Application: {case.azure_application.display_name}</li>"
            f"<li>App ID: {case.azure_application.app_id}</li>"
            f"<li>Credential type: {case.old_credential.credential_type.value}</li>"
            f"<li>Credential expiry: {case.old_credential.end_date_time.isoformat()}</li>"
            f"</ul>"
            f"<p><a href=\"{case_url}\">Open the credential renewal case</a></p>"
        )
        message = {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body},
            "toRecipients": [{"emailAddress": {"address": recipient.email}}],
        }
        self.graph_client.send_mail(self.shared_mailbox, message)
