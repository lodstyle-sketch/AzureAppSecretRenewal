from datetime import datetime, timezone
import unittest

from credential_renewal.tokens import TokenError, create_case_token, validate_case_token


class TokenTests(unittest.TestCase):
    def test_case_token_can_be_reused_until_expiry(self):
        expires_at = datetime(2026, 7, 20, tzinfo=timezone.utc)
        token = create_case_token("case-1", expires_at, "secret-key")

        first = validate_case_token(token, "case-1", "secret-key", now=datetime(2026, 7, 10, tzinfo=timezone.utc))
        second = validate_case_token(token, "case-1", "secret-key", now=datetime(2026, 7, 19, tzinfo=timezone.utc))

        self.assertEqual(first["case_id"], "case-1")
        self.assertEqual(second["case_id"], "case-1")

    def test_case_token_is_rejected_after_expiry(self):
        token = create_case_token("case-1", datetime(2026, 7, 20, tzinfo=timezone.utc), "secret-key")

        with self.assertRaises(TokenError):
            validate_case_token(token, "case-1", "secret-key", now=datetime(2026, 7, 21, tzinfo=timezone.utc))

    def test_case_token_is_bound_to_case_id(self):
        token = create_case_token("case-1", datetime(2026, 7, 20, tzinfo=timezone.utc), "secret-key")

        with self.assertRaises(TokenError):
            validate_case_token(token, "case-2", "secret-key", now=datetime(2026, 7, 10, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
