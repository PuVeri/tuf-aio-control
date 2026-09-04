from __future__ import annotations

import sys
import threading
import time
import unittest
from dataclasses import FrozenInstanceError
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


class LatestFrameBufferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.first = REFERENCE_PATH.read_bytes()
        cls.second = _jpeg("blue")
        cls.third = _jpeg("green")

    def test_first_publish_creates_generation_one(self) -> None:
        source = lcd_refresh.LatestFrameBuffer()
        with self.assertRaises(lcd_refresh.RefreshStateError):
            source.snapshot()
        published = source.publish(self.first)

        self.assertEqual(published.generation, 1)
        self.assertIs(published.jpeg_bytes, self.first)
        self.assertIs(source.snapshot(), published)

    def test_generation_increases_only_after_successful_publish(self) -> None:
        source = lcd_refresh.LatestFrameBuffer(self.first)
        before = source.snapshot()

        with self.assertRaises(lcd_refresh.RefreshConfigurationError):
            source.publish(b"not a jpeg")

        self.assertIs(source.snapshot(), before)
        published = source.publish(self.second)
        self.assertEqual(published.generation, before.generation + 1)
        self.assertIs(published.jpeg_bytes, self.second)

    def test_snapshot_is_frozen_and_contains_immutable_bytes(self) -> None:
        snapshot = lcd_refresh.LatestFrameBuffer(self.first).snapshot()
        self.assertIsInstance(snapshot.jpeg_bytes, bytes)
        with self.assertRaises(FrozenInstanceError):
            snapshot.generation = 2  # type: ignore[misc]

    def test_validation_occurs_without_holding_snapshot_lock(self) -> None:
        source = lcd_refresh.LatestFrameBuffer(self.first)
        validation_started = threading.Event()
        allow_validation = threading.Event()
        original_validate = lcd_refresh.lcd_transport.validate_jpeg

        def blocking_validate(jpeg: bytes) -> lcd_transport.JpegInfo:
            validation_started.set()
            self.assertTrue(allow_validation.wait(1.0))
            return original_validate(jpeg)

        with mock.patch.object(
            lcd_refresh.lcd_transport,
            "validate_jpeg",
            side_effect=blocking_validate,
        ):
            publisher = threading.Thread(target=source.publish, args=(self.second,))
            publisher.start()
            self.assertTrue(validation_started.wait(1.0))
            observed: list[lcd_refresh.FrameSnapshot] = []
            snapshot_finished = threading.Event()
            reader = threading.Thread(
                target=lambda: (
                    observed.append(source.snapshot()),
                    snapshot_finished.set(),
                )
            )
            reader.start()
            try:
                self.assertTrue(snapshot_finished.wait(0.1))
            finally:
                allow_validation.set()
            publisher.join(1.0)
            reader.join(1.0)

        self.assertFalse(publisher.is_alive())
        self.assertFalse(reader.is_alive())
        self.assertEqual(observed[0].generation, 1)
        self.assertEqual(source.snapshot().generation, 2)

    def test_concurrent_snapshot_and_publish_never_exposes_partial_state(self) -> None:
        source = lcd_refresh.LatestFrameBuffer(self.first)
        start = threading.Barrier(2)
        finished = threading.Event()
        observed: list[lcd_refresh.FrameSnapshot] = []

        def publish_many() -> None:
            start.wait()
            for index in range(100):
                source.publish(self.second if index % 2 else self.third)
            finished.set()

        publisher = threading.Thread(target=publish_many)
        publisher.start()
        start.wait()
        while not finished.is_set():
            observed.append(source.snapshot())
        observed.append(source.snapshot())
        publisher.join(1.0)

        self.assertFalse(publisher.is_alive())
        self.assertTrue(observed)
        self.assertEqual(
            [item.generation for item in observed],
            sorted(item.generation for item in observed),
        )
        self.assertTrue(
            all(
                item.jpeg_bytes in {self.first, self.second, self.third}
                for item in observed
            )
        )
        self.assertEqual(source.snapshot().generation, 101)

    def test_rapid_publishes_retain_only_latest_frame(self) -> None:
        source = lcd_refresh.LatestFrameBuffer()
        source.publish(self.first)
        source.publish(self.second)
        latest = source.publish(self.third)

        self.assertIs(source.snapshot(), latest)
        self.assertEqual(latest.generation, 3)
        self.assertIs(latest.jpeg_bytes, self.third)
        self.assertFalse(hasattr(source, "_queue"))


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

        self.assertEqual(
            result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP
        )
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

    def test_unbounded_plan_runs_past_old_limits_until_explicit_stop(self) -> None:
        clock = FakeClock()
        starts: list[float] = []
        controller: lcd_refresh.RefreshController

        def sender(_: bytes) -> int:
            starts.append(clock())
            if len(starts) == 35:
                controller.request_stop()
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            lcd_refresh.RefreshPlan(
                frames=(lcd_refresh.RefreshFrame(self.jpeg),),
                transport_interval_seconds=1.0,
                max_duration_seconds=None,
                max_frames=None,
            ),
            sender,
            clock=clock,
            wait_function=clock.wait,
        )
        controller.start()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(
            result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP
        )
        self.assertEqual(result.frames_sent, 35)
        self.assertEqual(starts, [float(index) for index in range(35)])
        self.assertGreater(result.elapsed_seconds, 30.0)

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

    def test_publish_during_transfer_changes_only_the_next_transfer(self) -> None:
        next_jpeg = _jpeg("blue")
        source = lcd_refresh.LatestFrameBuffer(self.jpeg)
        first_started = threading.Event()
        release_first = threading.Event()
        observed: list[bytes] = []

        def sender(jpeg: bytes) -> int:
            observed.append(jpeg)
            if len(observed) == 1:
                first_started.set()
                self.assertTrue(release_first.wait(1.0))
            return lcd_transport.validate_jpeg(jpeg).segment_count

        controller = lcd_refresh.RefreshController(
            _plan((lcd_refresh.RefreshFrame(self.jpeg),), max_frames=2),
            sender,
            frame_source=source,
        )
        controller.start()
        self.assertTrue(first_started.wait(1.0))

        published = source.publish(next_jpeg)
        self.assertEqual(published.generation, 2)
        self.assertEqual(observed, [self.jpeg])
        release_first.set()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.MAX_FRAMES)
        self.assertEqual(observed, [self.jpeg, next_jpeg])

    def test_dynamic_source_is_rejected_for_animation_plan(self) -> None:
        source = lcd_refresh.LatestFrameBuffer(self.jpeg)
        frame = lcd_refresh.RefreshFrame(self.jpeg, duration_seconds=0.1)
        with self.assertRaisesRegex(
            lcd_refresh.RefreshConfigurationError,
            "nur für Einframepläne",
        ):
            lcd_refresh.RefreshController(
                _plan((frame, frame)),
                mock.Mock(),
                frame_source=source,
            )

    def test_request_stop_is_nonblocking_and_performs_no_device_access(self) -> None:
        first_send = threading.Event()
        sender = mock.Mock(
            side_effect=lambda _: (first_send.set(), self.segment_count)[1]
        )
        controller = lcd_refresh.RefreshController(
            _plan(
                (lcd_refresh.RefreshFrame(self.jpeg),),
                interval=30.0,
                max_duration=60.0,
                max_frames=100,
            ),
            sender,
        )

        with mock.patch.object(
            lcd_refresh.lcd_transport.os,
            "open",
            side_effect=AssertionError("device opened"),
        ) as device_open:
            controller.start()
            self.assertTrue(first_send.wait(1.0))
            returned = threading.Event()
            requester = threading.Thread(
                target=lambda: (controller.request_stop(), returned.set())
            )
            requester.start()
            self.assertTrue(returned.wait(0.1))
            requester.join(1.0)
            result = controller.wait(timeout=1.0)

        self.assertFalse(requester.is_alive())
        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP)
        device_open.assert_not_called()

    def test_stop_during_frame_finishes_it_without_starting_another(self) -> None:
        transfer_started = threading.Event()
        release_transfer = threading.Event()
        calls = 0

        def sender(_: bytes) -> int:
            nonlocal calls
            calls += 1
            transfer_started.set()
            self.assertTrue(release_transfer.wait(1.0))
            return self.segment_count

        controller = lcd_refresh.RefreshController(
            lcd_refresh.RefreshPlan(
                frames=(lcd_refresh.RefreshFrame(self.jpeg),),
                transport_interval_seconds=1.0,
                max_duration_seconds=None,
                max_frames=None,
            ),
            sender,
        )
        controller.start()
        self.assertTrue(transfer_started.wait(1.0))

        requested = time.monotonic()
        controller.request_stop()
        self.assertLess(time.monotonic() - requested, 0.1)
        release_transfer.set()
        result = controller.wait(timeout=1.0)

        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP)
        self.assertEqual(result.frames_sent, 1)
        self.assertEqual(calls, 1)

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

    def test_plan_validates_optional_limits_and_frame_durations(self) -> None:
        frame = lcd_refresh.RefreshFrame(self.jpeg)
        with self.assertRaises(lcd_refresh.RefreshConfigurationError):
            _plan((frame,), max_duration=lcd_refresh.MAX_REFRESH_DURATION_SECONDS + 1)
        with self.assertRaises(lcd_refresh.RefreshConfigurationError):
            _plan((frame,), max_frames=lcd_refresh.MAX_REFRESH_FRAME_COUNT + 1)
        with self.assertRaisesRegex(
            lcd_refresh.RefreshConfigurationError, "explizites Frameintervall"
        ):
            _plan((frame, frame))

        unbounded = lcd_refresh.RefreshPlan(
            frames=(frame,),
            transport_interval_seconds=1.0,
            max_duration_seconds=None,
            max_frames=None,
        )
        self.assertIsNone(unbounded.max_duration_seconds)
        self.assertIsNone(unbounded.max_frames)

    def test_first_live_profile_is_fixed_to_reference_and_conservative_limits(self) -> None:
        plan = lcd_refresh.build_first_refresh_live_test_plan(self.jpeg)

        self.assertEqual(len(plan.frames), 1)
        self.assertIs(plan.frames[0].jpeg_bytes, self.jpeg)
        self.assertIsNone(plan.frames[0].duration_seconds)
        self.assertEqual(
            plan.transport_interval_seconds,
            lcd_refresh.FIRST_REFRESH_INTERVAL_SECONDS,
        )
        self.assertEqual(
            plan.max_duration_seconds,
            lcd_refresh.FIRST_REFRESH_MAX_DURATION_SECONDS,
        )
        self.assertEqual(plan.max_frames, lcd_refresh.FIRST_REFRESH_MAX_FRAMES)
        self.assertEqual(plan.transport_interval_seconds, 1.0)
        self.assertEqual(plan.max_duration_seconds, 6.0)
        self.assertEqual(plan.max_frames, 5)

    def test_first_live_profile_rejects_other_valid_jpeg(self) -> None:
        with self.assertRaisesRegex(
            lcd_refresh.RefreshConfigurationError,
            "nur das empirisch bestätigte Referenz-JPEG",
        ):
            lcd_refresh.build_first_refresh_live_test_plan(_jpeg("black"))


if __name__ == "__main__":
    unittest.main()
