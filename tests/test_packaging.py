from __future__ import annotations

import ast
import configparser
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGING_ROOT = PROJECT_ROOT / "packaging"
INSTALLER = PACKAGING_ROOT / "manage-user-installation.sh"


class PackagingOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.data_home = self.root / "xdg-data"
        self.config_home = self.root / "xdg-config"
        self.state_home = self.root / "xdg-state"
        self.home.mkdir()
        self.environment = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data_home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "XDG_STATE_HOME": str(self.state_home),
        }
        self.app_directory = self.data_home / "tuf-aio-control"
        self.launcher = self.home / ".local/bin/tuf-aio-control"
        self.desktop = self.data_home / "applications/tuf-aio-control.desktop"
        self.autostart = self.config_home / "autostart/tuf-aio-control.desktop"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_installer(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(INSTALLER), *arguments],
            env=self.environment,
            text=True,
            capture_output=True,
            check=check,
        )

    @staticmethod
    def read_desktop(path: Path) -> configparser.SectionProxy:
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_string(path.read_text(encoding="utf-8"))
        return parser["Desktop Entry"]

    def test_install_layout_is_copied_and_has_no_repository_dependency(self) -> None:
        self.run_installer("install", "--autostart")

        manifest = {
            Path(line).name
            for line in (PACKAGING_ROOT / "runtime-files.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line and not line.startswith("#")
        }
        installed = {path.name for path in (self.app_directory / "app").iterdir()}
        self.assertEqual(installed, manifest)
        self.assertTrue(self.launcher.is_file())
        self.assertTrue(os.access(self.launcher, os.X_OK))
        self.assertFalse(
            any(path.is_symlink() for path in self.app_directory.rglob("*"))
        )

        installed_artifacts = [
            *self.app_directory.rglob("*"),
            self.launcher,
            self.desktop,
            self.autostart,
        ]
        repository_path = str(PROJECT_ROOT).encode()
        for artifact in installed_artifacts:
            if artifact.is_file():
                self.assertNotIn(repository_path, artifact.read_bytes())

        launcher_text = self.launcher.read_text(encoding="utf-8")
        self.assertIn(
            '$data_home/tuf-aio-control/app/tuf_aio_gui.py', launcher_text
        )
        self.assertIn('"$@"', launcher_text)
        self.assertNotIn("HeartdriveLAB", launcher_text)

        desktop = self.read_desktop(self.desktop)
        autostart = self.read_desktop(self.autostart)
        self.assertEqual(desktop["Exec"], f'"{self.launcher}"')
        self.assertEqual(desktop["TryExec"], str(self.launcher))
        self.assertEqual(autostart["Type"], "Application")
        self.assertEqual(autostart["Name"], "TUF AIO Control")
        self.assertEqual(autostart["Exec"], f'"{self.launcher}" --background')
        self.assertEqual(autostart["TryExec"], str(self.launcher))
        self.assertEqual(autostart["Terminal"], "false")
        self.assertNotIn("sudo", autostart["Exec"])
        self.assertNotIn("src/", autostart["Exec"])

    def test_runtime_manifest_is_import_complete_and_dependencies_are_exact(self) -> None:
        relative_files = [
            line
            for line in (PACKAGING_ROOT / "runtime-files.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line and not line.startswith("#")
        ]
        installed_modules = {Path(relative).stem for relative in relative_files}
        all_source_modules = {path.stem for path in (PROJECT_ROOT / "src").glob("*.py")}
        external_modules: set[str] = set()

        for relative in relative_files:
            tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name.partition(".")[0] for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module.partition(".")[0]]
                else:
                    continue
                for name in names:
                    if name in all_source_modules:
                        self.assertIn(name, installed_modules)
                    elif name not in sys.stdlib_module_names:
                        external_modules.add(name)

        self.assertEqual(external_modules, {"PIL", "PySide6"})
        self.assertTrue(all(not Path(path).name.startswith("test_") for path in relative_files))

    def test_install_update_and_uninstall_preserve_settings_and_logs(self) -> None:
        self.run_installer("install", "--autostart")
        settings = self.config_home / "HeartDriveLab/tuf-aio-control.conf"
        log = self.state_home / "tuf-aio-control/gui-refresh-test.jsonl"
        settings.parent.mkdir(parents=True)
        log.parent.mkdir(parents=True)
        settings.write_text("persistent-setting\n", encoding="utf-8")
        log.write_text("persistent-log\n", encoding="utf-8")

        repeated_install = self.run_installer("install", check=False)
        self.assertNotEqual(repeated_install.returncode, 0)
        installed_gui = self.app_directory / "app/tuf_aio_gui.py"
        installed_gui.write_text("stale copy\n", encoding="utf-8")

        self.run_installer("update")
        self.assertEqual(
            installed_gui.read_bytes(),
            (PROJECT_ROOT / "src/tuf_aio_gui.py").read_bytes(),
        )
        self.assertTrue(self.autostart.is_file(), "update must preserve autostart")
        self.run_installer("update")
        self.assertEqual(settings.read_text(encoding="utf-8"), "persistent-setting\n")
        self.assertEqual(log.read_text(encoding="utf-8"), "persistent-log\n")

        self.run_installer("uninstall")
        self.assertFalse(self.app_directory.exists())
        self.assertFalse(self.launcher.exists())
        self.assertFalse(self.desktop.exists())
        self.assertFalse(self.autostart.exists())
        self.assertTrue(settings.is_file())
        self.assertTrue(log.is_file())

    def test_autostart_can_be_enabled_and_disabled_explicitly(self) -> None:
        self.run_installer("install")
        self.assertFalse(self.autostart.exists())
        self.assertEqual(
            self.run_installer("autostart-status").stdout.strip(), "disabled"
        )
        self.run_installer("enable-autostart")
        self.assertTrue(self.autostart.is_file())
        expected = (PACKAGING_ROOT / "tuf-aio-control-autostart.desktop").read_text(
            encoding="utf-8"
        ).replace("@LAUNCHER@", str(self.launcher))
        self.assertEqual(self.autostart.read_text(encoding="utf-8"), expected)
        first_content = self.autostart.read_bytes()
        self.run_installer("enable-autostart")
        self.assertEqual(self.autostart.read_bytes(), first_content)
        self.assertEqual(
            self.run_installer("autostart-status").stdout.strip(), "enabled"
        )
        self.run_installer("disable-autostart")
        self.assertFalse(self.autostart.exists())
        self.run_installer("disable-autostart")
        self.assertFalse(self.autostart.exists())

    def test_update_preserves_disabled_autostart_and_install_does_not_enable(self) -> None:
        self.run_installer("install")
        self.assertFalse(self.autostart.exists())
        self.run_installer("update")
        self.assertFalse(self.autostart.exists())

    def test_xdg_config_home_and_home_fallback_are_respected(self) -> None:
        self.run_installer("install")
        self.run_installer("enable-autostart")
        self.assertTrue(self.autostart.is_file())
        self.run_installer("uninstall")

        self.environment.pop("XDG_CONFIG_HOME")
        fallback = self.home / ".config/autostart/tuf-aio-control.desktop"
        self.run_installer("install")
        self.run_installer("enable-autostart")
        self.assertTrue(fallback.is_file())

    def test_disable_and_uninstall_preserve_unmanaged_desktop_files(self) -> None:
        self.run_installer("install", "--autostart")
        foreign = self.config_home / "autostart/foreign.desktop"
        foreign.write_text("[Desktop Entry]\nType=Application\n", encoding="utf-8")
        self.run_installer("disable-autostart")
        self.assertTrue(foreign.is_file())
        self.run_installer("enable-autostart")
        self.run_installer("uninstall")
        self.assertTrue(foreign.is_file())

    def test_unmanaged_autostart_target_is_never_removed(self) -> None:
        self.run_installer("install", "--autostart")
        self.autostart.write_text(
            "[Desktop Entry]\nType=Application\nName=Foreign\n",
            encoding="utf-8",
        )
        disabled = self.run_installer("disable-autostart", check=False)
        self.assertNotEqual(disabled.returncode, 0)
        self.assertTrue(self.autostart.is_file())
        uninstalled = self.run_installer("uninstall", check=False)
        self.assertNotEqual(uninstalled.returncode, 0)
        self.assertTrue(self.autostart.is_file())

    def test_generated_desktop_files_pass_available_validator(self) -> None:
        validator = shutil.which("desktop-file-validate")
        if validator is None:
            self.skipTest("desktop-file-validate is not installed")
        self.run_installer("install", "--autostart")
        subprocess.run([validator, str(self.desktop)], check=True, capture_output=True)
        subprocess.run([validator, str(self.autostart)], check=True, capture_output=True)

    def test_user_installer_has_no_privilege_escalation_or_install_side_effect(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertNotIn("sudo", text)
        self.assertNotIn("udevadm", text)
        self.assertFalse((self.home / ".local").exists())

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
