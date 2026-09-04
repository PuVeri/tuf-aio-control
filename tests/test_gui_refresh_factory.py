from __future__ import annotations

import sys
import threading
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

import gui_refresh_factory
import lcd_refresh
import lcd_runtime_safety
import lcd_transport
from discover_device import HidrawInterface

REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"


def valid_device() -> HidrawInterface:
    return HidrawInterface(
        device_path="/dev/hidraw-dynamic-test",
        sysfs_path="/sys/class/hidraw/hidraw-dynamic-test",
        interface_number=1,
        manufacturer="ASUS Tek",
        product="TUF GAMING LC III 360 ARGB LCD",
        serial="offline-test",
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


def frame_source() -> lcd_refresh.LatestFrameBuffer:
    return lcd_refresh.LatestFrameBuffer(REFERENCE_PATH.read_bytes())


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def wait(self, event: threading.Event, timeout: float) -> bool:
        if event.is_set():
            return True
        self.now += timeout
        return event.is_set()


class ProductionControllerFactoryTests(unittest.TestCase):
    def _factory(self, device: HidrawInterface, **changes: object) -> object:
        defaults = {
            "device_discovery": mock.Mock(return_value=(device, "offline fake")),
            "competing_writer_finder": mock.Mock(return_value=()),
        }
        defaults.update(changes)
        return gui_refresh_factory.ProductionControllerFactory(**defaults)

    def test_factory_builds_existing_sender_controller_and_dynamic_source(self) -> None:
        device = valid_device()
        source = frame_source()
        with mock.patch.object(
            lcd_transport.os,
            "open",
            side_effect=AssertionError("hidraw open called"),
        ) as device_open:
            controller = self._factory(device)(source)

        self.assertIsInstance(controller, lcd_refresh.RefreshController)
        self.assertIs(controller._frame_source, source)
        self.assertIsInstance(controller._sender, lcd_refresh.HidrawFrameSender)
        self.assertIs(controller._sender.device, device)
        self.assertIs(
            controller._sender.extra_validator,
            lcd_runtime_safety.runtime_device_error,
        )
        device_open.assert_not_called()

    def test_production_policy_is_one_hz_and_has_no_automatic_limit(self) -> None:
        clock = FakeClock()
        calls = 0

        def sender(jpeg: bytes) -> int:
            nonlocal calls
            calls += 1
            if calls == 35:
                controller.request_stop()
            return lcd_transport.validate_jpeg(jpeg).segment_count

        def build_controller(
            plan: lcd_refresh.RefreshPlan,
            frame_sender: lcd_refresh.FrameSender,
            *,
            frame_source: lcd_refresh.FrameSource,
        ) -> lcd_refresh.RefreshController:
            return lcd_refresh.RefreshController(
                plan,
                frame_sender,
                frame_source=frame_source,
                clock=clock,
                wait_function=clock.wait,
            )

        controller = self._factory(
            valid_device(),
            sender_factory=mock.Mock(return_value=sender),
            controller_builder=build_controller,
        )(frame_source())
        self.assertEqual(controller._plan.transport_interval_seconds, 1.0)
        self.assertIsNone(controller._plan.max_duration_seconds)
        self.assertIsNone(controller._plan.max_frames)

        controller.start()
        result = controller.wait(1.0)
        assert result is not None
        self.assertEqual(
            result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP
        )
        self.assertEqual(result.frames_sent, 35)
        self.assertGreater(result.elapsed_seconds, 30.0)
        self.assertEqual(calls, 35)

    def test_bounded_development_policy_remains_available(self) -> None:
        plan = gui_refresh_factory.build_gui_development_plan(
            REFERENCE_PATH.read_bytes()
        )
        self.assertEqual(plan.transport_interval_seconds, 1.0)
        self.assertEqual(plan.max_duration_seconds, 30.0)
        self.assertEqual(plan.max_frames, 30)

    def test_stop_is_nonblocking_at_factory_controller_boundary(self) -> None:
        first_send = threading.Event()

        def sender(jpeg: bytes) -> int:
            first_send.set()
            return lcd_transport.validate_jpeg(jpeg).segment_count

        controller = self._factory(
            valid_device(),
            sender_factory=mock.Mock(return_value=sender),
        )(frame_source())
        controller.start()
        self.assertTrue(first_send.wait(1.0))
        controller.request_stop()
        result = controller.wait(1.0)
        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP)
        self.assertEqual(result.frames_sent, 1)

    def test_first_transport_error_stops_without_retry(self) -> None:
        calls = 0

        def sender(_: bytes) -> int:
            nonlocal calls
            calls += 1
            raise lcd_transport.LcdTransportError("injected offline failure")

        controller = self._factory(
            valid_device(),
            sender_factory=mock.Mock(return_value=sender),
        )(frame_source())
        controller.start()
        result = controller.wait(1.0)
        assert result is not None
        self.assertEqual(result.stop_reason, lcd_refresh.RefreshStopReason.SEND_ERROR)
        self.assertEqual(result.frames_sent, 0)
        self.assertEqual(calls, 1)

    def test_every_identity_and_report_gate_rejects_before_sender_creation(self) -> None:
        wrong_endpoints = lcd_runtime_safety.EXPECTED_ENDPOINTS[:1]
        changes = (
            {"vendor_id": "ffff"},
            {"product_id": "19af"},
            {"interface_number": 0},
            {"manufacturer": "Other"},
            {"product": "Other LCD"},
            {"bcd_device": "0051"},
            {"bcd_device": None},
            {"usage_page": 0x0001},
            {"usage": 0x02},
            {"input_report_bytes": 15},
            {"output_report_bytes": 440},
            {"feature_report_bytes": 8},
            {"report_ids": (1,)},
            {"device_path": "/dev/not-the-dynamic-hidraw-node"},
            {"alternate_setting": 1},
            {"interface_class": 0xFF},
            {"interface_subclass": 1},
            {"interface_protocol": 1},
            {"endpoint_count": 1},
            {"endpoints": wrong_endpoints},
        )
        for change in changes:
            with self.subTest(change=change):
                sender_factory = mock.Mock(
                    side_effect=AssertionError("sender constructed")
                )
                device = replace(valid_device(), **change)
                with (
                    mock.patch.object(
                        lcd_transport.os,
                        "open",
                        side_effect=AssertionError("hidraw open called"),
                    ) as device_open,
                    self.assertRaisesRegex(
                        gui_refresh_factory.ProductionControllerFactoryError,
                        "Safety-Gate",
                    ),
                ):
                    self._factory(
                        device,
                        sender_factory=sender_factory,
                    )(frame_source())
                sender_factory.assert_not_called()
                device_open.assert_not_called()

    def test_missing_or_ambiguous_interface_fails_without_sender(self) -> None:
        sender_factory = mock.Mock(side_effect=AssertionError("sender constructed"))
        factory = gui_refresh_factory.ProductionControllerFactory(
            device_discovery=mock.Mock(return_value=(None, "Treffer: 0")),
            competing_writer_finder=mock.Mock(return_value=()),
            sender_factory=sender_factory,
        )
        with self.assertRaisesRegex(
            gui_refresh_factory.ProductionControllerFactoryError,
            "Kein eindeutiges LCD-Interface 1",
        ):
            factory(frame_source())
        sender_factory.assert_not_called()

    def test_competing_writer_fails_before_sender_or_open(self) -> None:
        sender_factory = mock.Mock(side_effect=AssertionError("sender constructed"))
        factory = self._factory(
            valid_device(),
            competing_writer_finder=mock.Mock(
                return_value=("PID 42 (other-writer), FD 7",)
            ),
            sender_factory=sender_factory,
        )
        with (
            mock.patch.object(
                lcd_transport.os,
                "open",
                side_effect=AssertionError("hidraw open called"),
            ) as device_open,
            self.assertRaisesRegex(
                gui_refresh_factory.ProductionControllerFactoryError,
                "Konkurrierender Writer",
            ),
        ):
            factory(frame_source())
        sender_factory.assert_not_called()
        device_open.assert_not_called()

    def test_default_discovery_is_scoped_to_0b05_1c7b_only(self) -> None:
        with mock.patch.object(
            gui_refresh_factory.lcd_transport,
            "discover",
            return_value=[],
        ) as discover:
            with self.assertRaises(
                gui_refresh_factory.ProductionControllerFactoryError
            ):
                gui_refresh_factory.ProductionControllerFactory()(frame_source())
        discover.assert_called_once_with("0b05", "1c7b", include_udev=False)

    def test_missing_product_name_is_accepted_when_other_gates_match(self) -> None:
        controller = self._factory(replace(valid_device(), product=None))(frame_source())
        self.assertIsInstance(controller, lcd_refresh.RefreshController)


if __name__ == "__main__":
    unittest.main()
