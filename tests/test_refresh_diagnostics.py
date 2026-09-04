from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import gui_refresh_factory
import lcd_refresh
import lcd_runtime_safety
import lcd_transport
import refresh_diagnostics
from discover_device import HidrawInterface

REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"


def valid_device() -> HidrawInterface:
    return HidrawInterface(
        device_path="/dev/hidraw-offline-diagnostic",
        sysfs_path="/sys/class/hidraw/hidraw-offline-diagnostic",
        interface_number=1,
        manufacturer="ASUS Tek",
        product="TUF GAMING LC III 360 ARGB LCD",
        serial=None,
        vendor_id="0b05",
        product_id="1c7b",
        input_report_bytes=16,
        output_report_bytes=1024,
        feature_report_bytes=None,
        report_ids=(),
        readable=False,
        udev_properties={},
        usage_page=0xFF06,
        usage=0x01,
        bcd_device="0049",
        alternate_setting=0,
        interface_class=3,
        interface_subclass=0,
        interface_protocol=0,
        endpoint_count=2,
        endpoints=lcd_runtime_safety.EXPECTED_ENDPOINTS,
    )


def read_entries(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


class RefreshDiagnosticsTests(unittest.TestCase):
    def test_default_log_directory_uses_absolute_xdg_state_home(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_home = Path(directory) / "state"
            with mock.patch.dict(
                os.environ, {"XDG_STATE_HOME": str(state_home)}, clear=False
            ):
                self.assertEqual(
                    refresh_diagnostics.default_log_directory(),
                    state_home / "tuf-aio-control",
                )

    def test_default_log_directory_falls_back_to_local_user_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory) / "home"
            with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(
                refresh_diagnostics.Path, "home", return_value=home
            ):
                self.assertEqual(
                    refresh_diagnostics.default_log_directory(),
                    home / ".local" / "state" / "tuf-aio-control",
                )

    def test_factory_writes_only_to_injected_log_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            diagnostics = refresh_diagnostics.create_gui_session_diagnostics(root)
            self.assertEqual(diagnostics.path.parent, root)
            self.assertTrue(diagnostics.path.is_file())

    def test_jsonl_rotates_by_size_and_limits_backups(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gui-refresh-test.jsonl"
            diagnostics = refresh_diagnostics.JsonlRefreshDiagnostics(
                path,
                session_id="offline-session",
                max_bytes=300,
                backup_count=2,
            )
            for index in range(20):
                diagnostics.record("frame_transfer_succeeded", frame_number=index)

            files = sorted(path.parent.glob(f"{path.name}*"))
            self.assertEqual(
                [candidate.name for candidate in files],
                [path.name, f"{path.name}.1", f"{path.name}.2"],
            )
            entries = [
                json.loads(line)
                for candidate in files
                for line in candidate.read_text(encoding="utf-8").splitlines()
            ]
            self.assertTrue(entries)
            self.assertTrue(
                all(entry["session_id"] == "offline-session" for entry in entries)
            )
            self.assertTrue(
                all(
                    "jpeg_bytes" not in entry and "payload" not in entry
                    for entry in entries
                )
            )

    def test_runtime_log_retention_removes_oldest_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / f"gui-refresh-{index:02d}.jsonl" for index in range(5)]
            for index, path in enumerate(paths):
                path.write_text("{}\n", encoding="utf-8")
                path.touch()
                path.chmod(0o600)
                os.utime(path, (index + 1, index + 1))

            with mock.patch.object(
                refresh_diagnostics, "DEFAULT_RETAINED_LOG_FILES", 3
            ):
                refresh_diagnostics._prune_runtime_logs(root)

            self.assertEqual(
                sorted(path.name for path in root.glob("gui-refresh-*.jsonl")),
                [path.name for path in paths[-3:]],
            )

    def test_factory_gate_exception_is_persisted_with_phase_and_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "factory.jsonl"
            diagnostics = refresh_diagnostics.JsonlRefreshDiagnostics(path)
            source = lcd_refresh.LatestFrameBuffer(
                REFERENCE_PATH.read_bytes(), diagnostics=diagnostics
            )
            factory = gui_refresh_factory.ProductionControllerFactory(
                device_discovery=mock.Mock(
                    side_effect=OSError("injected discovery failure")
                )
            )
            with self.assertRaises(
                gui_refresh_factory.ProductionControllerFactoryError
            ):
                factory(source)

            entries = read_entries(path)
            failure = next(
                entry
                for entry in entries
                if entry["event"] == "exception"
                and entry["phase"] == "device_discovery"
            )
            self.assertEqual(failure["exception_type"], "OSError")
            self.assertIn("injected discovery failure", failure["message"])
            self.assertIn(
                "safety_gates_failed", [entry["event"] for entry in entries]
            )

    def test_sender_and_worker_failures_are_persisted_without_retry(self) -> None:
        class Clock:
            def __init__(self) -> None:
                self.now = 0.0

            def __call__(self) -> float:
                return self.now

            def wait(self, event: threading.Event, timeout: float) -> bool:
                self.now += timeout
                return event.is_set()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sender.jsonl"
            diagnostics = refresh_diagnostics.JsonlRefreshDiagnostics(path)
            source = lcd_refresh.LatestFrameBuffer(
                REFERENCE_PATH.read_bytes(), diagnostics=diagnostics
            )
            clock = Clock()
            sender = lcd_refresh.HidrawFrameSender(
                valid_device(), diagnostics=diagnostics, clock=clock
            )
            plan = gui_refresh_factory.build_gui_development_plan(
                source.snapshot().jpeg_bytes
            )
            controller = lcd_refresh.RefreshController(
                plan,
                sender,
                frame_source=source,
                clock=clock,
                wait_function=clock.wait,
            )
            send_once = mock.Mock(
                side_effect=lcd_transport.LcdTransportError(
                    "injected transport failure"
                )
            )
            with mock.patch.object(
                lcd_refresh.lcd_transport, "send_frame_once", send_once
            ):
                controller.start()
                result = controller.wait(1.0)

            assert result is not None
            self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.SEND_ERROR)
            self.assertEqual(result.frames_sent, 0)
            send_once.assert_called_once()
            entries = read_entries(path)
            exceptions = {
                entry["phase"]: entry["exception_type"]
                for entry in entries
                if entry["event"] == "exception"
            }
            self.assertEqual(exceptions["send_frame_once"], "LcdTransportError")
            self.assertEqual(exceptions["refresh_result"], "LcdTransportError")
            terminal = next(
                entry for entry in entries if entry["event"] == "session_stopped"
            )
            self.assertEqual(terminal["stop_reason"], "transport error")
            self.assertEqual(
                [entry["event"] for entry in entries].count(
                    "send_frame_once_called"
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
