"""Tests for role helper behavior."""

from __future__ import annotations

import unittest

from server_app.db.models import Role, User
from server_app.services.auth import role_name_for_user, user_has_role


class AuthServiceTests(unittest.TestCase):
    """Validate lightweight role helper functions."""

    def test_role_name_for_user(self) -> None:
        """Role helper should expose the related role name."""

        user = User(username="owner", full_name="Owner", password_hash="hash", role=Role(name="Owner"))

        self.assertEqual(role_name_for_user(user), "Owner")

    def test_user_has_role(self) -> None:
        """Role membership helper should check allowed role names."""

        user = User(username="cashier", full_name="Cashier", password_hash="hash", role=Role(name="Cashier"))

        self.assertTrue(user_has_role(user, {"Cashier", "Owner"}))
        self.assertFalse(user_has_role(user, {"Owner"}))


if __name__ == "__main__":
    unittest.main()
