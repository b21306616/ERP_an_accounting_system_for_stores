"""Tests for password hashing and token helpers."""

from __future__ import annotations

import unittest

from server_app.core.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class SecurityTests(unittest.TestCase):
    """Validate authentication primitives."""

    def test_password_hash_roundtrip(self) -> None:
        """A password hash should verify only the original password."""

        password_hash = hash_password("correct-password")

        self.assertTrue(verify_password("correct-password", password_hash))
        self.assertFalse(verify_password("wrong-password", password_hash))

    def test_access_token_roundtrip(self) -> None:
        """A token should decode with the same secret used to create it."""

        token = create_access_token("owner", "secret", "Owner")
        payload = decode_access_token(token, "secret")

        self.assertEqual(payload["sub"], "owner")
        self.assertEqual(payload["role"], "Owner")

    def test_access_token_rejects_wrong_secret(self) -> None:
        """A changed signing secret should invalidate the token signature."""

        token = create_access_token("owner", "secret", "Owner")

        with self.assertRaises(TokenError):
            decode_access_token(token, "other-secret")

    def test_access_token_expiration(self) -> None:
        """Already expired tokens should be rejected."""

        token = create_access_token("owner", "secret", "Owner", expires_minutes=-1)

        with self.assertRaises(TokenError):
            decode_access_token(token, "secret")


if __name__ == "__main__":
    unittest.main()
