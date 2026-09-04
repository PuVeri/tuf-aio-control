from __future__ import annotations

import configparser
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGING_ROOT = PROJECT_ROOT / "packaging"


class PackagingOfflineTests(unittest.TestCase):
    def test_xdg_autostart_template_is_background_only_and_not_installed(self) -> None:
        template = PACKAGING_ROOT / "tuf-aio-control-autostart.desktop"
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(template.read_text(encoding="utf-8"))
        entry = parser["Desktop Entry"]

        self.assertEqual(entry["Type"], "Application")
        self.assertEqual(entry["Terminal"], "false")
        self.assertIn("@PROJECT_ROOT@/src/tuf_aio_gui.py", entry["Exec"])
        self.assertIn("--background", entry["Exec"])
        self.assertNotIn("LCD", entry["Exec"].replace("tuf_aio", ""))
        self.assertIn("tuf-aio-control.desktop", (
            PACKAGING_ROOT / "manage-user-autostart.sh"
        ).read_text(encoding="utf-8"))

    def test_udev_rule_grants_write_only_to_confirmed_interface_one(self) -> None:
        text = (PACKAGING_ROOT / "99-tuf-aio-control.rules").read_text(
            encoding="utf-8"
        )
        rules = [
            line for line in text.splitlines() if line and not line.startswith("#")
        ]
        writable = [line for line in rules if 'MODE:="0660"' in line]

        self.assertEqual(len(writable), 1)
        self.assertIn('ATTRS{idVendor}=="0b05"', writable[0])
        self.assertIn('ATTRS{idProduct}=="1c7b"', writable[0])
        self.assertIn('ENV{ID_USB_INTERFACE_NUM}=="01"', writable[0])
        self.assertIn('GROUP:="input"', writable[0])
        self.assertNotIn('ID_USB_INTERFACE_NUM}=="00"', writable[0])
        self.assertNotIn("19af", text.casefold())
        self.assertIsNone(re.search(r'MODE:?="0666"', text))


if __name__ == "__main__":
    unittest.main()
