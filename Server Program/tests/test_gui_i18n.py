"""Tests for GUI localization helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from server_app.core.network import PortCheckResult, PortCheckStatus
from server_app.gui.i18n import (
    format_port_check_message,
    get_gui_preferences_path,
    load_language_preference,
    save_language_preference,
    set_language,
    tr,
)


class GuiI18nTests(unittest.TestCase):
    """Validate language fallback, persistence, and formatted network messages."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        patcher = patch.dict(os.environ, {"ERP_SERVER_CONFIG_DIR": self.temp_dir.name})
        patcher.start()
        self.addCleanup(patcher.stop)
        set_language("en", persist=False)

    def test_language_preference_persists_and_falls_back(self) -> None:
        self.assertEqual(load_language_preference(), "en")

        save_language_preference("ru")

        self.assertTrue(get_gui_preferences_path().exists())
        self.assertEqual(load_language_preference(), "ru")
        self.assertEqual(set_language("missing", persist=False), "en")

    def test_translation_falls_back_to_english_key(self) -> None:
        set_language("tk", persist=False)

        self.assertEqual(tr("common.next"), "Indiki")
        self.assertEqual(tr("missing.key"), "missing.key")

    def test_port_messages_are_localized_from_structured_status(self) -> None:
        result = PortCheckResult(
            host="0.0.0.0",
            port=8123,
            bind_host="",
            status=PortCheckStatus.IN_USE,
            message="English source message should not be used.",
        )

        self.assertIn("already in use", format_port_check_message(result))
        set_language("ru", persist=False)
        self.assertIn("уже используется", format_port_check_message(result))


if __name__ == "__main__":
    unittest.main()
