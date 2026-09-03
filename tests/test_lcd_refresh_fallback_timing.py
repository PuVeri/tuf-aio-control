from __future__ import annotations

import ast
import contextlib
import importlib.util
import io
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

import lcd_refresh
import lcd_transport

from tests.test_lcd_refresh_live import prepared_test

SPEC = importlib.util.spec_from_file_location(
    "lcd_refresh_fallback_tool", SRC_ROOT / "test_lcd_refresh_fallback.py"
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

    def schedule_wait(self, event: threading.Event, timeout: float) -> bool:
        if event.is_set():
            return True
        self.advance(timeout)
        return event.is_set()


class PassiveObservationTests(unittest.TestCase):
    def test_user_event_uses_correct_monotonic_differences(self) -> None:
        clock = FakeClock()
        clock.now = 12.0

        def report(_: float) -> bool:
            clock.advance(2.25)
            return True

        with contextlib.redirect_stdout(io.StringIO()):
            result = TOOL.observe_fallback(
                test_started_at=5.0,
                last_frame_completed_at=12.0,
                clock=clock,
                wait_function=report,
            )

        self.assertTrue(result.reported)
        self.assertAlmostEqual(result.seconds_since_test_start, 9.25)
        self.assertAlmostEqual(result.seconds_since_last_frame, 2.25)

    def test_observation_timeout_is_exactly_twenty_seconds(self) -> None:
        clock = FakeClock()
        observed_timeouts: list[float] = []

        def timeout(seconds: float) -> bool:
            observed_timeouts.append(seconds)
            clock.advance(seconds)
            return False

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = TOOL.observe_fallback(
                test_started_at=0.0,
                last_frame_completed_at=4.1,
                clock=clock,
                wait_function=timeout,
            )

        self.assertFalse(result.reported)
        self.assertEqual(observed_timeouts, [20.0])
        self.assertIn("Kein beobachteter Fallback innerhalb 20 s", output.getvalue())

    def test_observation_function_has_no_hid_usb_or_sysfs_calls(self) -> None:
        clock = FakeClock()
        with (
            mock.patch.object(
                lcd_transport.os,
                "open",
                side_effect=AssertionError("hidraw open called"),
            ),
            mock.patch.object(
                lcd_transport.os,
                "write",
                side_effect=AssertionError("hidraw write called"),
            ),
            mock.patch.object(
                lcd_transport,
                "discover_lcd_interface",
                side_effect=AssertionError("USB discovery called"),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = TOOL.observe_fallback(
                test_started_at=0.0,
                last_frame_completed_at=0.0,
                clock=clock,
                wait_function=lambda _: False,
            )
        self.assertFalse(result.reported)

    def test_observation_source_uses_no_transport_or_device_call(self) -> None:
        tree = ast.parse(
            Path(TOOL.__file__).read_text(encoding="utf-8"),
            filename=TOOL.__file__,
        )
        function = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "observe_fallback"
        )
        called_names = {
            node.func.attr
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        self.assertFalse(
            called_names.intersection(
                {"open", "read", "write", "discover", "discover_lcd_interface"}
            )
        )


class TransportThenObservationTests(unittest.TestCase):
    def test_observation_starts_after_fifth_close_and_no_more_writes_follow(self) -> None:
        prepared = prepared_test()
        clock = FakeClock()
        writes = mock.Mock(return_value=1025)
        closes = mock.Mock()
        observation_calls = 0

        def observe(_: float) -> bool:
            nonlocal observation_calls
            observation_calls += 1
            self.assertEqual(writes.call_count, 15)
            self.assertEqual(closes.call_count, 5)
            return False

        with (
            mock.patch.object(TOOL.os, "access", return_value=True),
            mock.patch.object(
                TOOL.refresh_test, "runtime_device_error", return_value=None
            ),
            mock.patch.object(lcd_transport.os, "open", return_value=123),
            mock.patch.object(lcd_transport.os, "write", writes),
            mock.patch.object(lcd_transport.os, "close", closes),
            mock.patch.object(lcd_transport, "validate_open_target"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = TOOL.run_timing_live(
                prepared,
                clock=clock,
                observation_wait=observe,
                schedule_wait=clock.schedule_wait,
            )

        self.assertEqual(result, TOOL.EXIT_SUCCESS)
        self.assertEqual(observation_calls, 1)
        self.assertEqual(writes.call_count, 15)
        self.assertEqual(closes.call_count, 5)

    def test_transport_profile_remains_exactly_the_first_live_profile(self) -> None:
        prepared = prepared_test()
        self.assertEqual(prepared.plan.transport_interval_seconds, 1.0)
        self.assertEqual(prepared.plan.max_duration_seconds, 6.0)
        self.assertEqual(prepared.plan.max_frames, 5)
        self.assertEqual(len(prepared.frame_reports), 5)
        self.assertEqual(sum(len(frame) for frame in prepared.frame_reports), 15)
        self.assertTrue(
            all(
                segment.control[0] == 0x08
                for frame in prepared.frame_reports
                for segment in frame
            )
        )

    def test_default_preview_never_opens_hidraw(self) -> None:
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
            self.assertEqual(TOOL.main([]), TOOL.EXIT_SUCCESS)


if __name__ == "__main__":
    unittest.main()
