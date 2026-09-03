from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import image_pipeline
import lcd_refresh
import lcd_transport

REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"


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


def _jpeg(color: str) -> bytes:
    return image_pipeline._encode_jpeg(
        Image.new("RGB", image_pipeline.OUTPUT_SIZE, color)
    )


def _plan(
    frames: tuple[lcd_refresh.RefreshFrame, ...],
    *,
    interval: float = 0.01,
    max_duration: float = 1.0,
    max_frames: int = 10,
) -> lcd_refresh.RefreshPlan:
    return lcd_refresh.RefreshPlan(
        frames=frames,
        transport_interval_seconds=interval,
        max_duration_seconds=max_duration,
        max_frames=max_frames,
    )


class RefreshControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.jpeg = REFERENCE_PATH.read_bytes()
        cls.segment_count = lcd_transport.validate_jpeg(cls.jpeg).segment_count

    def test_explicit_start_and_stop_interrupt_wait(self) -> None:
        first_send = threading.Event()

        def sender(jpeg: bytes) -> int:
            self.assertIs(jpeg, self.jpeg)
            first_send.set()
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            _plan(
                (lcd_refresh.RefreshFrame(self.jpeg),),
                interval=30.0,
                max_duration=60.0,
                max_frames=100,
            ),
            sender,
        )
        self.assertFalse(controller.is_running)
        controller.start()
        self.assertTrue(first_send.wait(1.0))
        result = controller.stop(timeout=1.0)

        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP)
        self.assertEqual(result.frames_sent, 1)
        self.assertFalse(controller.is_running)

    def test_second_parallel_refresh_session_is_rejected(self) -> None:
        first_send = threading.Event()

        def sender(_: bytes) -> int:
            first_send.set()
            return self.segment_count

        first = lcd_refresh.RefreshController(
            _plan(
                (lcd_refresh.RefreshFrame(self.jpeg),),
                interval=30.0,
                max_duration=60.0,
                max_frames=100,
            ),
            sender,
        )
        second = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),)), sender
        )
        first.start()
        try:
            self.assertTrue(first_send.wait(1.0))
            with self.assertRaisesRegex(lcd_refresh.RefreshStateError, "bereits aktiv"):
                second.start()
        finally:
            first.stop(timeout=1.0)

    def test_transport_rejects_parallel_frame_sender_before_device_open(self) -> None:
        with (
            lcd_transport._FRAME_SEND_LOCK,  # process-wide transport invariant
            mock.patch.object(
                lcd_transport.os,
                "open",
                side_effect=AssertionError("device opened"),
            ),
        ):
            with self.assertRaisesRegex(lcd_transport.LcdTransportError, "bereits aktiv"):
                lcd_transport.send_frame_once(
                    mock.sentinel.device, self.jpeg  # type: ignore[arg-type]
                )

    def test_first_send_error_stops_without_retry(self) -> None:
        clock = FakeClock()
        calls = 0

        def sender(_: bytes) -> int:
            nonlocal calls
            calls += 1
            raise lcd_transport.LcdTransportError("offline write failure")

        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),)),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.SEND_ERROR)
        self.assertEqual(result.frames_sent, 0)
        self.assertEqual(calls, 1)
        self.assertIsInstance(result.error, lcd_transport.LcdTransportError)

    def test_error_after_one_frame_stops_at_first_failure(self) -> None:
        clock = FakeClock()
        calls = 0

        def sender(_: bytes) -> int:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second-frame failure")
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),)),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.SEND_ERROR)
        self.assertEqual(result.frames_sent, 1)
        self.assertEqual(calls, 2)

    def test_incomplete_frame_result_stops_without_retry(self) -> None:
        clock = FakeClock()
        sender = mock.Mock(return_value=self.segment_count - 1)
        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),)),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.SEND_ERROR)
        self.assertEqual(result.frames_sent, 0)
        sender.assert_called_once_with(self.jpeg)

    def test_maximum_frame_count_is_exact(self) -> None:
        clock = FakeClock()
        calls = 0

        def sender(_: bytes) -> int:
            nonlocal calls
            calls += 1
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),), max_frames=4),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.MAX_FRAMES)
        self.assertEqual(result.frames_sent, 4)
        self.assertEqual(calls, 4)

    def test_maximum_runtime_prevents_next_frame(self) -> None:
        clock = FakeClock()
        starts: list[float] = []

        def sender(_: bytes) -> int:
            starts.append(clock())
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            _plan(
                (lcd_refresh.RefreshFrame(self.jpeg),),
                interval=0.01,
                max_duration=0.025,
                max_frames=100,
            ),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.MAX_DURATION)
        self.assertEqual(starts, [0.0, 0.01, 0.02])

    def test_slow_transfer_never_overlaps_and_has_no_catch_up_burst(self) -> None:
        clock = FakeClock()
        starts: list[float] = []
        active = 0
        maximum_active = 0
        durations = iter((0.025, 0.0, 0.0))

        def sender(_: bytes) -> int:
            nonlocal active, maximum_active
            starts.append(clock())
            active += 1
            maximum_active = max(maximum_active, active)
            clock.advance(next(durations))
            active -= 1
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            _plan(
                (lcd_refresh.RefreshFrame(self.jpeg),),
                interval=0.01,
                max_frames=3,
            ),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(maximum_active, 1)
        self.assertEqual(starts, [0.0, 0.025, 0.035])
        self.assertEqual(result.transfer_durations, (0.025, 0.0, 0.0))

    def test_static_frame_bytes_are_reused(self) -> None:
        clock = FakeClock()
        observed: list[bytes] = []

        def sender(jpeg: bytes) -> int:
            observed.append(jpeg)
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),), max_frames=3),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(len(observed), 3)
        self.assertTrue(all(item is self.jpeg for item in observed))
        self.assertEqual(result.frame_indices, (0, 0, 0))

    def test_animated_frames_rotate_in_order_without_skipping(self) -> None:
        clock = FakeClock()
        jpegs = (_jpeg("red"), _jpeg("green"), _jpeg("blue"))
        by_identity = {id(jpeg): index for index, jpeg in enumerate(jpegs)}
        observed: list[int] = []
        frames = tuple(
            lcd_refresh.RefreshFrame(jpeg, duration_seconds=0.009)
            for jpeg in jpegs
        )

        def sender(jpeg: bytes) -> int:
            observed.append(by_identity[id(jpeg)])
            return lcd_transport.validate_jpeg(jpeg).segment_count

        controller = lcd_refresh.RefreshController(
            _plan(frames, interval=0.01, max_frames=5),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(observed, [0, 1, 2, 0, 1])
        self.assertEqual(result.frame_indices, (0, 1, 2, 0, 1))

    def test_device_adapter_is_fully_mockable(self) -> None:
        clock = FakeClock()
        device = mock.sentinel.device
        send_once = mock.Mock(return_value=self.segment_count)
        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),), max_frames=1),
            lcd_refresh.HidrawFrameSender(device),  # type: ignore[arg-type]
            clock=clock,
            wait_function=clock.wait,
        )

        with mock.patch.object(lcd_refresh.lcd_transport, "send_frame_once", send_once):
            controller.start()
            result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.MAX_FRAMES)
        send_once.assert_called_once_with(device, self.jpeg)

    def test_plan_requires_explicit_bounded_limits_and_frame_durations(self) -> None:
        frame = lcd_refresh.RefreshFrame(self.jpeg)
        with self.assertRaises(lcd_refresh.RefreshConfigurationError):
            _plan((frame,), max_duration=lcd_refresh.MAX_REFRESH_DURATION_SECONDS + 1)
        with self.assertRaises(lcd_refresh.RefreshConfigurationError):
            _plan((frame,), max_frames=lcd_refresh.MAX_REFRESH_FRAME_COUNT + 1)
        with self.assertRaisesRegex(
            lcd_refresh.RefreshConfigurationError, "explizites Frameintervall"
        ):
            _plan((frame, frame))


if __name__ == "__main__":
    unittest.main()
