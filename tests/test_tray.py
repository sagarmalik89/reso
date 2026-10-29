"""
tests/test_tray.py
------------------
Unit tests for the Windows System Tray application & packaging helpers.
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from printer_agent.tray_app import (
    DEFAULT_CONFIG,
    PrinterAgentTrayApp,
    create_tray_icon_image,
    load_config,
    save_config,
)


class TestTrayApp(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dynamic_icon_generation(self):
        """Verify dynamic tray icon generates valid RGBA image."""
        img_online = create_tray_icon_image(online=True)
        img_offline = create_tray_icon_image(online=False)

        if img_online is not None:
            self.assertEqual(img_online.size, (64, 64))
            self.assertEqual(img_online.mode, "RGBA")
        if img_offline is not None:
            self.assertEqual(img_offline.size, (64, 64))
            self.assertEqual(img_offline.mode, "RGBA")

    @patch("printer_agent.tray_app.CONFIG_FILE")
    def test_config_load_and_save(self, mock_config_path):
        cfg_file = self.temp_path / "test_shop_config.json"
        mock_config_path.exists.side_effect = cfg_file.exists
        mock_config_path.__str__.return_value = str(cfg_file)

        # Test defaults generated
        with patch("builtins.open", side_effect=open):
            # Patch CONFIG_FILE directly
            import printer_agent.tray_app as tray_mod
            tray_mod.CONFIG_FILE = cfg_file

            cfg = load_config()
            self.assertEqual(cfg["shop_id"], "counter-1")
            self.assertTrue(cfg_file.exists())

            # Update and save
            cfg["shop_id"] = "test-custom-shop"
            save_config(cfg)

            reloaded = load_config()
            self.assertEqual(reloaded["shop_id"], "test-custom-shop")

    @patch("printer_agent.tray_app.ShopPrinterClient")
    def test_tray_app_initialization(self, mock_client_cls):
        mock_instance = MagicMock()
        mock_client_cls.return_value = mock_instance

        app = PrinterAgentTrayApp()
        self.assertIsNotNone(app.client)
        self.assertFalse(app.is_connected)
        self.assertEqual(app.total_printed, 0)

        # Heartbeat callback
        app._on_heartbeat(True)
        self.assertTrue(app.is_connected)

        app._on_heartbeat(False)
        self.assertFalse(app.is_connected)


if __name__ == "__main__":
    unittest.main()
