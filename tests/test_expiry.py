from datetime import datetime, timezone
import unittest

from credential_renewal.expiry import expiring_credentials
from credential_renewal.models import CredentialType


class ExpiryTests(unittest.TestCase):
    def test_expiring_credentials_returns_secrets_and_certificates_inside_window(self):
        application = {
            "passwordCredentials": [{"keyId": "secret-1", "displayName": "old", "endDateTime": "2026-07-20T00:00:00Z"}],
            "keyCredentials": [{"keyId": "cert-1", "displayName": "cert", "endDateTime": "2026-07-25T00:00:00Z"}],
        }

        result = expiring_credentials(application, now=datetime(2026, 7, 9, tzinfo=timezone.utc), window_days=30)

        self.assertEqual([credential.key_id for credential in result], ["secret-1", "cert-1"])
        self.assertEqual(result[0].credential_type, CredentialType.SECRET)
        self.assertEqual(result[1].credential_type, CredentialType.CERTIFICATE)

    def test_expiring_credentials_ignores_expired_and_later_credentials(self):
        application = {
            "passwordCredentials": [
                {"keyId": "expired", "endDateTime": "2026-07-01T00:00:00Z"},
                {"keyId": "later", "endDateTime": "2026-09-01T00:00:00Z"},
            ],
            "keyCredentials": [],
        }

        result = expiring_credentials(application, now=datetime(2026, 7, 9, tzinfo=timezone.utc), window_days=30)

        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
