from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import os
import sys
import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import discover_device
import lcd_refresh
import lcd_transport

SPEC = importlib.util.spec_from_file_location(
    "lcd_refresh_live_tool", SRC_ROOT / "test_lcd_refresh.py"
)
assert SPEC is not None and SPEC.loader is not None
TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOOL
SPEC.loader.exec_module(TOOL)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds

    def wait(self, event: threading.Event, timeout: float) -> bool:
        if event.is_set():
            return True
        self.advance(timeout)
        return event.is_set()


def valid_device() -> discover_device.HidrawInterface:
    return discover_device.HidrawInterface(
        device_path="/dev/hidraw-dynamic",
        sysfs_path="/sys/class/hidraw/hidraw-dynamic",
        interface_number=1,
        manufacturer="ASUS Tek",
        product="TUF GAMING LC III 360 ARGB LCD",
        serial="test-serial",
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
        bcd_device="0.49",
        alternate_setting=0,
        interface_class=3,
        interface_subclass=0,
        interface_protocol=0,
        endpoint_count=2,
        endpoints=TOOL.EXPECTED_ENDPOINTS,
    )


def prepared_test() -> object:
    jpeg = TOOL.REFERENCE_PATH.read_bytes()
    plan = lcd_refresh.build_first_refresh_live_test_plan(jpeg)
    reports = tuple(
        lcd_transport.build_segments(jpeg) for _ in range(plan.max_frames)
    )
    return TOOL.PreparedRefreshTest(valid_device(), jpeg, plan, reports)


class CliSafetyTests(unittest.TestCase):
    def _preview(self, arguments: list[str]) -> int:
        with (
            mock.patch.object(
                TOOL.lcd_transport,
                "discover_lcd_interface",
                return_value=(None, "offline"),
            ),
            mock.patch.object(
                TOOL.lcd_transport.os,
                "open",
                side_effect=AssertionError("hidraw open called"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return TOOL.main(arguments)

    def test_standard_invocation_never_opens_hidraw(self) -> None:
        self.assertEqual(self._preview([]), TOOL.EXIT_SUCCESS)

    def test_explicit_dry_run_never_opens_hidraw(self) -> None:
        self.assertEqual(self._preview(["--dry-run"]), TOOL.EXIT_SUCCESS)

    def test_missing_confirmation_never_enters_live_path(self) -> None:
        with (
            mock.patch.object(
                TOOL.lcd_transport,
                "discover_lcd_interface",
                return_value=(valid_device(), "gültig"),
            ),
            mock.patch.object(TOOL, "runtime_device_error", return_value=None),
            mock.patch.object(
                TOOL,
                "run_live",
                side_effect=AssertionError("live path called"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(TOOL.main([]), TOOL.EXIT_SUCCESS)

    def test_risk_switch_cannot_be_abbreviated(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                TOOL.main(["--i-understand"])
        self.assertEqual(raised.exception.code, 2)

    def test_wrong_reference_hash_stops_before_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            wrong = Path(directory) / "wrong.jpg"
            data = bytearray(TOOL.REFERENCE_PATH.read_bytes())
            data[-3] ^= 1
            wrong.write_bytes(data)
            with (
                mock.patch.object(TOOL, "REFERENCE_PATH", wrong),
                mock.patch.object(
                    TOOL.lcd_transport,
                    "discover_lcd_interface",
                    side_effect=AssertionError("discovery called"),
                ),
                mock.patch.object(
                    TOOL.lcd_transport.os,
                    "open",
                    side_effect=AssertionError("hidraw open called"),
                ),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(
                    TOOL.main(["--i-understand-the-risk"]), TOOL.EXIT_SAFETY
                )

    def test_wrong_n_stops_before_discovery(self) -> None:
        with (
            mock.patch.object(TOOL, "EXPECTED_SEGMENTS", 2),
            mock.patch.object(
                TOOL.lcd_transport,
                "discover_lcd_interface",
                side_effect=AssertionError("discovery called"),
            ),
            mock.patch.object(
                TOOL.lcd_transport.os,
                "open",
                side_effect=AssertionError("hidraw open called"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                TOOL.main(["--i-understand-the-risk"]), TOOL.EXIT_SAFETY
            )


class StrictMetadataTests(unittest.TestCase):
    def test_valid_metadata_is_accepted(self) -> None:
        self.assertIsNone(TOOL.strict_device_error(valid_device()))

    def test_wrong_vid_pid_is_rejected(self) -> None:
        for change in ({"vendor_id": "ffff"}, {"product_id": "ffff"}):
            with self.subTest(change=change):
                self.assertIsNotNone(
                    TOOL.strict_device_error(replace(valid_device(), **change))
                )

    def test_wrong_interface_is_rejected(self) -> None:
        self.assertIsNotNone(
            TOOL.strict_device_error(replace(valid_device(), interface_number=0))
        )

    def test_raw_bcd_device_0049_is_accepted(self) -> None:
        self.assertEqual(TOOL.parse_bcd_device("0049"), 0x0049)
        self.assertIsNone(
            TOOL.strict_device_error(replace(valid_device(), bcd_device="0049"))
        )

    def test_normalized_bcd_device_0_49_is_accepted(self) -> None:
        for representation in ("0.49", "0x0049"):
            with self.subTest(representation=representation):
                self.assertEqual(TOOL.parse_bcd_device(representation), 0x0049)
                self.assertIsNone(
                    TOOL.strict_device_error(
                        replace(valid_device(), bcd_device=representation)
                    )
                )

    def test_raw_bcd_device_0051_is_rejected(self) -> None:
        self.assertEqual(TOOL.parse_bcd_device("0051"), 0x0051)
        self.assertIsNotNone(
            TOOL.strict_device_error(replace(valid_device(), bcd_device="0051"))
        )

    def test_malformed_bcd_device_is_rejected(self) -> None:
        self.assertIsNone(TOOL.parse_bcd_device("firmware-0049"))
        self.assertIsNotNone(
            TOOL.strict_device_error(
                replace(valid_device(), bcd_device="firmware-0049")
            )
        )

    def test_rejected_bcd_preflight_cannot_reach_write(self) -> None:
        device = replace(valid_device(), bcd_device="0051")
        with (
            mock.patch.object(
                TOOL.lcd_transport,
                "discover_lcd_interface",
                return_value=(device, "gefunden"),
            ),
            mock.patch.object(TOOL, "find_competing_writers", return_value=()),
            mock.patch.object(
                TOOL,
                "run_live",
                side_effect=AssertionError("live path called"),
            ),
            mock.patch.object(
                TOOL.lcd_transport.os,
                "write",
                side_effect=AssertionError("write called"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(
                TOOL.main(["--i-understand-the-risk"]), TOOL.EXIT_PREFLIGHT
            )

    def test_wrong_report_size_is_rejected(self) -> None:
        self.assertIsNotNone(
            TOOL.strict_device_error(
                replace(valid_device(), output_report_bytes=440)
            )
        )

    def test_wrong_usage_is_rejected(self) -> None:
        self.assertIsNotNone(
            TOOL.strict_device_error(replace(valid_device(), usage=2))
        )

    def test_wrong_endpoint_profile_is_rejected(self) -> None:
        self.assertIsNotNone(
            TOOL.strict_device_error(replace(valid_device(), endpoints=()))
        )

    def test_descriptor_parser_extracts_known_usage(self) -> None:
        descriptor = bytes.fromhex(
            "06 06 ff 09 01 a1 01 15 00 26 ff 00 75 08 "
            "96 10 00 09 01 81 02 96 00 04 09 01 91 02 c0"
        )
        parsed = discover_device.parse_report_descriptor(descriptor)
        self.assertEqual(parsed["usage_page"], 0xFF06)
        self.assertEqual(parsed["usage"], 0x01)
        self.assertEqual(parsed["input_report_bytes"], 16)
        self.assertEqual(parsed["output_report_bytes"], 1024)

    def test_sysfs_endpoint_reader_extracts_known_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            interface = Path(directory)
            values = (
                ("ep_03", "03", "03", "0400", "125us"),
                ("ep_84", "84", "03", "0010", "125us"),
            )
            for name, address, attributes, packet_size, interval in values:
                endpoint = interface / name
                endpoint.mkdir()
                (endpoint / "bEndpointAddress").write_text(address, encoding="ascii")
                (endpoint / "bmAttributes").write_text(attributes, encoding="ascii")
                (endpoint / "wMaxPacketSize").write_text(packet_size, encoding="ascii")
                (endpoint / "interval").write_text(interval, encoding="ascii")

            endpoints = discover_device._read_endpoints(interface)

        self.assertEqual(
            endpoints,
            (
                discover_device.UsbEndpoint(0x03, 0x03, 1024, 125),
                discover_device.UsbEndpoint(0x84, 0x03, 16, 125),
            ),
        )

    def test_competing_writer_aborts_preflight(self) -> None:
        with mock.patch.object(
            TOOL,
            "find_competing_writers",
            return_value=("PID 123 (other), FD 4",),
        ):
            with self.assertRaisesRegex(RuntimeError, "Konkurrierender Writer"):
                TOOL.prepare_test(valid_device())


class FixedRuntimeTests(unittest.TestCase):
    def test_fixed_profile_has_five_frames_fifteen_reports_and_only_0x08(self) -> None:
        prepared = prepared_test()
        self.assertEqual(prepared.plan.max_frames, 5)
        self.assertEqual(len(prepared.frame_reports), 5)
        self.assertEqual(sum(map(len, prepared.frame_reports)), 15)
        self.assertTrue(
            all(
                report.control[0] == 0x08
                for frame in prepared.frame_reports
                for report in frame
            )
        )

    def test_five_frame_starts_are_one_second_apart(self) -> None:
        prepared = prepared_test()
        clock = FakeClock()
        starts: list[float] = []

        def sender(_: bytes) -> int:
            starts.append(clock())
            return 3

        controller = lcd_refresh.RefreshController(
            prepared.plan, sender, clock=clock, wait_function=clock.wait
        )
        controller.start()
        result = controller.wait(timeout=1)
        assert result is not None
        self.assertEqual(starts, [0.0, 1.0, 2.0, 3.0, 4.0])
        self.assertEqual(result.frames_sent, 5)

    def test_slow_transfer_has_no_overlap_or_catch_up(self) -> None:
        prepared = prepared_test()
        clock = FakeClock()
        starts: list[float] = []
        calls = 0

        def sender(_: bytes) -> int:
            nonlocal calls
            starts.append(clock())
            if calls == 0:
                clock.advance(1.5)
            calls += 1
            return 3

        controller = lcd_refresh.RefreshController(
            prepared.plan, sender, clock=clock, wait_function=clock.wait
        )
        controller.start()
        result = controller.wait(timeout=1)
        assert result is not None
        self.assertEqual(starts, [0.0, 1.5, 2.5, 3.5, 4.5])
        self.assertEqual(result.frames_sent, 5)

    def test_success_uses_exactly_fifteen_writes_and_closes_every_frame(self) -> None:
        prepared = prepared_test()
        sender = TOOL.LoggedPreparedSender(prepared, clock=FakeClock())
        write = mock.Mock(return_value=1025)
        close = mock.Mock()
        with (
            mock.patch.object(TOOL, "runtime_device_error", return_value=None),
            mock.patch.object(lcd_transport.os, "access", return_value=True),
            mock.patch.object(lcd_transport.os, "open", return_value=123),
            mock.patch.object(lcd_transport.os, "write", write),
            mock.patch.object(lcd_transport.os, "close", close),
            mock.patch.object(lcd_transport, "validate_open_target"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            for _ in range(5):
                self.assertEqual(sender(prepared.jpeg), 3)
        self.assertEqual(write.call_count, 15)
        self.assertEqual(close.call_count, 5)

    def test_first_write_error_stops_without_retry_and_closes(self) -> None:
        prepared = prepared_test()
        clock = FakeClock()
        write = mock.Mock(side_effect=OSError("injected"))
        close = mock.Mock()
        sender = TOOL.LoggedPreparedSender(prepared, clock=clock)
        controller = lcd_refresh.RefreshController(
            prepared.plan, sender, clock=clock, wait_function=clock.wait
        )
        with (
            mock.patch.object(TOOL, "runtime_device_error", return_value=None),
            mock.patch.object(lcd_transport.os, "access", return_value=True),
            mock.patch.object(lcd_transport.os, "open", return_value=123),
            mock.patch.object(lcd_transport.os, "write", write),
            mock.patch.object(lcd_transport.os, "close", close),
            mock.patch.object(lcd_transport, "validate_open_target"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            controller.start()
            result = controller.wait(timeout=1)
        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.SEND_ERROR)
        self.assertEqual(result.frames_sent, 0)
        self.assertEqual(write.call_count, 1)
        self.assertEqual(close.call_count, 1)

    def test_extra_gate_is_called_before_open_and_each_write(self) -> None:
        prepared = prepared_test()
        validator = mock.Mock(return_value=None)
        transfer_validator = mock.Mock(return_value=None)

        def validate_open(
            _: int,
            device: discover_device.HidrawInterface,
            *,
            extra_validator: object = None,
        ) -> None:
            self.assertIs(extra_validator, validator)
            assert callable(extra_validator)
            self.assertIsNone(extra_validator(device))

        with (
            mock.patch.object(lcd_transport.os, "access", return_value=True),
            mock.patch.object(lcd_transport.os, "open", return_value=123),
            mock.patch.object(lcd_transport.os, "write", return_value=1025),
            mock.patch.object(lcd_transport.os, "close"),
            mock.patch.object(lcd_transport, "validate_open_target", side_effect=validate_open),
        ):
            self.assertEqual(
                lcd_transport.send_frame_once(
                    prepared.device,
                    prepared.jpeg,
                    prepared_segments=prepared.frame_reports[0],
                    extra_validator=validator,
                    extra_transfer_validator=transfer_validator,
                ),
                3,
            )
        self.assertEqual(validator.call_count, 4)
        self.assertEqual(transfer_validator.call_count, 4)

    def test_source_has_one_os_write_and_no_os_read_callsite(self) -> None:
        write_sites: list[Path] = []
        read_sites: list[Path] = []
        refresh_path = {
            SRC_ROOT / "lcd_transport.py",
            SRC_ROOT / "lcd_refresh.py",
            SRC_ROOT / "test_lcd_refresh.py",
        }
        for path in sorted(refresh_path):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if not isinstance(node.func.value, ast.Name) or node.func.value.id != "os":
                    continue
                if node.func.attr == "write":
                    write_sites.append(path)
                elif node.func.attr == "read":
                    read_sites.append(path)
        self.assertEqual(write_sites, [SRC_ROOT / "lcd_transport.py"])
        self.assertEqual(read_sites, [])


if __name__ == "__main__":
    unittest.main()
