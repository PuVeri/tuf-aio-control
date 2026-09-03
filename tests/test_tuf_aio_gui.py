from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from PIL import Image

import image_pipeline
import gui_refresh_factory
import lcd_refresh
import lcd_runtime_safety
import lcd_transport
import system_sensors
import tuf_aio_gui


class FakeSender:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.frames: list[bytes] = []
        self.maximum_active = 0
        self._active = 0
        self._lock = threading.Lock()

    def __call__(self, jpeg: bytes) -> int:
        with self._lock:
            self._active += 1
            self.maximum_active = max(self.maximum_active, self._active)
        try:
            self.frames.append(jpeg)
            if self.error is not None:
                raise self.error
            return lcd_transport.validate_jpeg(jpeg).segment_count
        finally:
            with self._lock:
                self._active -= 1


class FakeRefreshController:
    """Controllable offline worker that consumes only injected snapshots."""

    def __init__(
        self,
        source: lcd_refresh.FrameSource,
        sender: FakeSender,
        *,
        block_sender: threading.Event | None = None,
    ) -> None:
        self.source = source
        self.sender = sender
        self.block_sender = block_sender
        self.result: lcd_refresh.RefreshResult | None = None
        self.request_stop_calls = 0
        self._running = False
        self._stop = threading.Event()
        self._transfer = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        self._running = True
        self._transfer.set()
        self._thread = threading.Thread(target=self._run, daemon=False)
        self._thread.start()

    def request_transfer(self) -> None:
        self._transfer.set()

    def request_stop(self) -> None:
        self.request_stop_calls += 1
        self._stop.set()
        self._transfer.set()

    def join(self) -> None:
        if self._thread is not None:
            self._thread.join(1.0)

    def _run(self) -> None:
        frames_sent = 0
        try:
            while not self._stop.is_set():
                self._transfer.wait()
                self._transfer.clear()
                if self._stop.is_set():
                    break
                snapshot = self.source.snapshot()
                if self.block_sender is not None:
                    self.block_sender.wait(1.0)
                self.sender(snapshot.jpeg_bytes)
                frames_sent += 1
        except Exception as error:
            self.result = lcd_refresh.RefreshResult(
                lcd_refresh.RefreshStopReason.SEND_ERROR,
                frames_sent,
                0.0,
                (),
                (),
                error,
            )
        else:
            self.result = lcd_refresh.RefreshResult(
                lcd_refresh.RefreshStopReason.EXPLICIT_STOP,
                frames_sent,
                0.0,
                (),
                (),
            )
        finally:
            self._running = False


class TufAioGuiOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._settings_directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self._settings_directory.cleanup()

    @staticmethod
    def _device() -> lcd_transport.HidrawInterface:
        return lcd_transport.HidrawInterface(
            device_path="/dev/hidraw-never-opened",
            sysfs_path="/sys/class/hidraw/hidraw-never-opened",
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

    def _window(
        self,
        discovery: tuple[lcd_transport.HidrawInterface | None, str] | None = None,
        sensor_reader: tuf_aio_gui.TemperatureReader | None = None,
        settings: QSettings | None = None,
        controller_factory: tuf_aio_gui.ControllerFactory | None = None,
    ) -> tuf_aio_gui.MainWindow:
        result = discovery if discovery is not None else (self._device(), "gültig")
        reader = sensor_reader or system_sensors.TemperatureSnapshot
        if settings is None:
            settings = self._settings(
                Path(self._settings_directory.name) / "default-settings.ini"
            )
        with mock.patch.object(
            tuf_aio_gui.transport, "discover_lcd_interface", return_value=result
        ):
            return tuf_aio_gui.MainWindow(
                sensor_reader=reader,
                settings=settings,
                controller_factory=controller_factory,
            )

    @staticmethod
    def _settings(path: Path) -> QSettings:
        return QSettings(str(path), QSettings.Format.IniFormat)

    @staticmethod
    def _wait_until(predicate: object, timeout: float = 1.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():  # type: ignore[operator]
                return
            QApplication.processEvents()
            time.sleep(0.005)
        raise AssertionError("Bedingung wurde nicht rechtzeitig erfüllt")

    def test_missing_temperatures_are_shown_as_na(self) -> None:
        window = self._window()
        try:
            self.assertEqual(window.cpu_temperature_value.text(), "N/A")
            self.assertEqual(window.cpu_package_temperature_value.text(), "N/A")
            self.assertEqual(window.gpu_temperature_value.text(), "N/A")
            self.assertEqual(window._temperature_timer.interval(), 1000)
            self.assertTrue(window._temperature_timer.isActive())
        finally:
            window.close()

    def test_temperatures_show_values_and_become_unavailable_cleanly(self) -> None:
        def value(
            label: str, channel: str, celsius: float
        ) -> system_sensors.TemperatureValue:
            sensor = system_sensors.TemperatureSensor(
                "k10temp" if label != "edge" else "amdgpu",
                label,
                Path(f"/fake/{channel}_input"),
                channel,
            )
            return system_sensors.TemperatureValue(celsius, sensor)

        present = system_sensors.TemperatureSnapshot(
            cpu=value("Tdie", "temp2", 47.25),
            cpu_package=value("Tctl", "temp1", 50.0),
            gpu=value("edge", "temp1", 43.5),
        )
        reader = mock.Mock(
            side_effect=[present, system_sensors.TemperatureSnapshot()]
        )
        window = self._window(sensor_reader=reader)
        try:
            self.assertEqual(window.cpu_temperature_value.text(), "47.2 °C")
            self.assertEqual(window.cpu_package_temperature_value.text(), "50.0 °C")
            self.assertEqual(window.gpu_temperature_value.text(), "43.5 °C")
            window.refresh_temperatures()
            self.assertEqual(window.cpu_temperature_value.text(), "N/A")
            self.assertEqual(window.cpu_package_temperature_value.text(), "N/A")
            self.assertEqual(window.gpu_temperature_value.text(), "N/A")
        finally:
            window.close()

    def test_reference_image_is_compatible_and_enables_send(self) -> None:
        window = self._window()
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertFalse(window.hardware_live_checkbox.isChecked())
            self.assertFalse(window.send_button.isEnabled())
            window.hardware_live_checkbox.setChecked(True)
            self.assertTrue(window.send_button.isEnabled())
            self.assertEqual(window.original_size_value.text(), "320×320")
            self.assertEqual(window.output_size_value.text(), "320×320")
            self.assertEqual(window.segments_value.text(), "3")
            self.assertIn("ASUS-JPEG-Validator: PASS", window.validation_value.text())
            self.assertIsNotNone(window._original_pixmap)
            self.assertIsNotNone(window._final_pixmap)
        finally:
            window.close()

    def test_incompatible_image_disables_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.png"
            path.write_bytes(b"not an image")

            window = self._window()
            try:
                self.assertFalse(window.load_image(path))
                self.assertFalse(window.send_button.isEnabled())
                self.assertIn("Nicht sendbar", window.status_label.text())
            finally:
                window.close()

    def test_missing_device_is_shown_as_not_connected(self) -> None:
        window = self._window((None, "Interface 1 nicht eindeutig gefunden (Treffer: 0)"))
        try:
            self.assertEqual(window.device_status_label.text(), "Gerät: nicht verbunden")
            self.assertTrue(window.load_image(REFERENCE_PATH))
            window.hardware_live_checkbox.setChecked(True)
            send_mock = mock.Mock(side_effect=AssertionError("send called"))
            with (
                mock.patch.object(window, "refresh_device_status", return_value=None),
                mock.patch.object(tuf_aio_gui.transport, "send_frame_once", send_mock),
                mock.patch.object(tuf_aio_gui.QMessageBox, "critical"),
            ):
                window.send_button.click()
            send_mock.assert_not_called()
        finally:
            window.close()

    def test_transport_error_is_reported_without_retry(self) -> None:
        window = self._window()
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            window.hardware_live_checkbox.setChecked(True)
            send_mock = mock.Mock(side_effect=lcd_transport.LcdTransportError("offline"))
            with (
                mock.patch.object(window, "refresh_device_status", return_value=self._device()),
                mock.patch.object(tuf_aio_gui.transport, "send_frame_once", send_mock),
                mock.patch.object(tuf_aio_gui.QMessageBox, "critical"),
            ):
                window.send_button.click()
            send_mock.assert_called_once()
            self.assertIn("Transfer abgebrochen", window.status_label.text())
        finally:
            window.close()

    def test_one_click_calls_send_frame_once_exactly_once(self) -> None:
        window = self._window()
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            window.hardware_live_checkbox.setChecked(True)
            send_mock = mock.Mock(return_value=3)
            with (
                mock.patch.object(window, "refresh_device_status", return_value=self._device()),
                mock.patch.object(tuf_aio_gui.transport, "send_frame_once", send_mock),
            ):
                window.send_button.click()
            send_mock.assert_called_once()
            self.assertIn("Ein Frame erfolgreich", window.status_label.text())
        finally:
            window.close()

    def test_overlay_color_defaults_to_white(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = self._settings(Path(directory) / "settings.ini")
            window = self._window(settings=settings)
            try:
                self.assertEqual(window._overlay_color, "#FFFFFF")
                self.assertEqual(
                    window._overlay_config().colors,
                    tuf_aio_gui.image_pipeline.TemperatureOverlayColors.uniform(
                        "#FFFFFF"
                    ),
                )
            finally:
                window.close()

    def test_custom_color_is_saved_restored_and_rerenders_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            settings = self._settings(path)
            settings.setValue(tuf_aio_gui.OVERLAY_ENABLED_SETTING, True)
            window = self._window(settings=settings)
            try:
                self.assertTrue(window.load_image(REFERENCE_PATH))
                before = window._prepared
                assert before is not None
                window._set_overlay_color("#12abCd")
                after = window._prepared
                assert after is not None
                self.assertEqual(window._overlay_color, "#12ABCD")
                self.assertNotEqual(after.jpeg_bytes, before.jpeg_bytes)
                expected = tuf_aio_gui.image_pipeline.rerender_prepared_image(
                    before,
                    overlay_config=window._overlay_config(),
                    temperatures=window._overlay_values(
                        window._latest_temperature_snapshot
                    ),
                )
                self.assertEqual(after.jpeg_bytes, expected.jpeg_bytes)
            finally:
                window.close()

            restored = self._window(settings=self._settings(path))
            try:
                self.assertEqual(restored._overlay_color, "#12ABCD")
                self.assertEqual(
                    restored._settings.value(tuf_aio_gui.OVERLAY_COLOR_SETTING),
                    "#12ABCD",
                )
            finally:
                restored.close()

    def test_invalid_saved_color_falls_back_to_persisted_white(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            settings = self._settings(path)
            settings.setValue(tuf_aio_gui.OVERLAY_COLOR_SETTING, "not-a-color")
            settings.sync()
            window = self._window(settings=self._settings(path))
            try:
                self.assertEqual(window._overlay_color, "#FFFFFF")
                self.assertEqual(
                    window._settings.value(tuf_aio_gui.OVERLAY_COLOR_SETTING),
                    "#FFFFFF",
                )
            finally:
                window.close()

    def test_sensor_poll_rerenders_without_usb_refresh_or_send(self) -> None:
        sensor = system_sensors.TemperatureSensor(
            "k10temp",
            "Tctl",
            Path("/fake/temp1_input"),
            "temp1",
        )
        reader = mock.Mock(
            side_effect=[
                system_sensors.TemperatureSnapshot(),
                system_sensors.TemperatureSnapshot(
                    cpu_package=system_sensors.TemperatureValue(51.0, sensor)
                ),
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            settings = self._settings(Path(directory) / "settings.ini")
            settings.setValue(tuf_aio_gui.OVERLAY_ENABLED_SETTING, True)
            window = self._window(sensor_reader=reader, settings=settings)
            try:
                self.assertTrue(window.load_image(REFERENCE_PATH))
                rerender = mock.Mock(wraps=window._rerender_temperature_overlay)
                with (
                    mock.patch.object(window, "_rerender_temperature_overlay", rerender),
                    mock.patch.object(
                        tuf_aio_gui.transport,
                        "discover_lcd_interface",
                        side_effect=AssertionError("USB discovery called"),
                    ),
                    mock.patch.object(
                        tuf_aio_gui.transport,
                        "send_frame_once",
                        side_effect=AssertionError("HID send called"),
                    ),
                ):
                    window.refresh_temperatures()
                rerender.assert_called_once_with()
                self.assertEqual(reader.call_count, 2)
            finally:
                window.close()

    def test_live_controls_require_injected_factory_and_valid_frame(self) -> None:
        sender = FakeSender()
        controllers: list[FakeRefreshController] = []

        def factory(source: lcd_refresh.FrameSource) -> FakeRefreshController:
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.STARTING)
            self.assertFalse(window.select_button.isEnabled())
            controller = FakeRefreshController(source, sender)
            controllers.append(controller)
            return controller

        window = self._window(controller_factory=factory)
        try:
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.IDLE)
            self.assertFalse(window.start_lcd_button.isEnabled())
            self.assertFalse(window.stop_lcd_button.isEnabled())
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertFalse(window.start_lcd_button.isEnabled())
            window.hardware_live_checkbox.setChecked(True)
            self.assertTrue(window.start_lcd_button.isEnabled())

            window.start_lcd_button.click()
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.RUNNING)
            self.assertFalse(window.start_lcd_button.isEnabled())
            self.assertTrue(window.stop_lcd_button.isEnabled())
            self.assertFalse(window.send_button.isEnabled())
            self.assertTrue(window.select_button.isEnabled())
        finally:
            if controllers and controllers[0].is_running:
                controllers[0].request_stop()
                controllers[0].join()
                window._poll_refresh_controller()
            window.close()

    def test_hardware_live_approval_defaults_off_and_blocks_all_writes(self) -> None:
        factory = mock.Mock(side_effect=AssertionError("controller factory called"))
        window = self._window(controller_factory=factory)
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertFalse(window.hardware_live_checkbox.isChecked())
            with (
                mock.patch.object(
                    tuf_aio_gui.transport.os,
                    "open",
                    side_effect=AssertionError("hidraw open called"),
                ) as device_open,
                mock.patch.object(
                    tuf_aio_gui.transport,
                    "send_frame_once",
                    side_effect=AssertionError("HID write path called"),
                ) as send_once,
                mock.patch.object(tuf_aio_gui.QMessageBox, "critical"),
            ):
                window.start_lcd()
                window.send_selected_image()
            factory.assert_not_called()
            device_open.assert_not_called()
            send_once.assert_not_called()
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.IDLE)
        finally:
            window.close()

    def test_production_gate_failure_enters_error_before_device_open(self) -> None:
        wrong_version = replace(self._device(), bcd_device="0051")
        factory = gui_refresh_factory.ProductionControllerFactory(
            device_discovery=mock.Mock(return_value=(wrong_version, "offline fake")),
            competing_writer_finder=mock.Mock(return_value=()),
        )
        window = self._window(controller_factory=factory)
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            window.hardware_live_checkbox.setChecked(True)
            with mock.patch.object(
                tuf_aio_gui.transport.os,
                "open",
                side_effect=AssertionError("hidraw open called"),
            ) as device_open:
                window.start_lcd_button.click()
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.ERROR)
            self.assertIn("bcdDevice", window.status_label.text())
            self.assertIn("kein Retry", window.status_label.text())
            device_open.assert_not_called()
        finally:
            window.close()

    def test_fake_end_to_end_publishes_changed_sensor_once_and_stops(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "hwmon"
            cpu = root / "hwmon7"
            cpu.mkdir(parents=True)
            (cpu / "name").write_text("k10temp\n", encoding="ascii")
            (cpu / "temp1_label").write_text("Tctl\n", encoding="ascii")
            sensor_input = cpu / "temp1_input"
            sensor_input.write_text("50000\n", encoding="ascii")
            settings = self._settings(Path(directory) / "settings.ini")
            settings.setValue(tuf_aio_gui.OVERLAY_ENABLED_SETTING, True)
            sender = FakeSender()
            controllers: list[FakeRefreshController] = []

            def factory(source: lcd_refresh.FrameSource) -> FakeRefreshController:
                controller = FakeRefreshController(source, sender)
                controllers.append(controller)
                return controller

            window = self._window(
                sensor_reader=lambda: system_sensors.read_lcd_temperatures(root),
                settings=settings,
                controller_factory=factory,
            )
            try:
                self.assertTrue(window.load_image(REFERENCE_PATH))
                with (
                    mock.patch.object(
                        tuf_aio_gui.transport.os,
                        "open",
                        side_effect=AssertionError("HID opened"),
                    ) as hid_open,
                    mock.patch.object(
                        tuf_aio_gui.transport,
                        "send_frame_once",
                        side_effect=AssertionError("USB sender called"),
                    ) as real_sender,
                ):
                    window.hardware_live_checkbox.setChecked(True)
                    window.start_lcd_button.click()
                    controller = controllers[0]
                    self._wait_until(lambda: len(sender.frames) == 1)
                    source = window._frame_buffer
                    assert source is not None
                    initial = source.snapshot()
                    self.assertEqual(initial.generation, 1)
                    self.assertIs(sender.frames[0], initial.jpeg_bytes)

                    sensor_input.write_text("51000\n", encoding="ascii")
                    window.refresh_temperatures()
                    changed = source.snapshot()
                    self.assertEqual(changed.generation, 2)
                    window.refresh_temperatures()
                    self.assertEqual(source.snapshot().generation, 2)

                    controller.request_transfer()
                    self._wait_until(lambda: len(sender.frames) == 2)
                    self.assertIs(sender.frames[1], changed.jpeg_bytes)
                    self.assertEqual(sender.maximum_active, 1)

                    window.stop_lcd_button.click()
                    self.assertEqual(
                        window._refresh_state, tuf_aio_gui.GuiRefreshState.STOPPING
                    )
                    controller.join()
                    window._poll_refresh_controller()
                    self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.IDLE)
                    self.assertEqual(controller.request_stop_calls, 1)
                    hid_open.assert_not_called()
                    real_sender.assert_not_called()
            finally:
                if controllers and controllers[0].is_running:
                    controllers[0].request_stop()
                    controllers[0].join()
                    window._poll_refresh_controller()
                window.close()

    def test_running_changes_publish_and_render_error_keeps_last_frame(self) -> None:
        sender = FakeSender()
        controllers: list[FakeRefreshController] = []

        def factory(source: lcd_refresh.FrameSource) -> FakeRefreshController:
            controller = FakeRefreshController(source, sender)
            controllers.append(controller)
            return controller

        with tempfile.TemporaryDirectory() as directory:
            settings = self._settings(Path(directory) / "settings.ini")
            settings.setValue(tuf_aio_gui.OVERLAY_ENABLED_SETTING, True)
            alternate = Path(directory) / "alternate.png"
            Image.new("RGB", (480, 240), "navy").save(alternate)
            window = self._window(settings=settings, controller_factory=factory)
            try:
                self.assertTrue(window.load_image(REFERENCE_PATH))
                window.hardware_live_checkbox.setChecked(True)
                window.start_lcd_button.click()
                source = window._frame_buffer
                assert source is not None

                generation = source.snapshot().generation
                window._set_overlay_color("#12ABCD")
                self.assertEqual(source.snapshot().generation, generation + 1)

                generation = source.snapshot().generation
                window._overlay_toggled(False)
                self.assertEqual(source.snapshot().generation, generation + 1)

                generation = source.snapshot().generation
                self.assertTrue(window.load_image(alternate))
                self.assertEqual(source.snapshot().generation, generation + 1)

                generation = source.snapshot().generation
                window.scale_mode.setCurrentIndex(1)
                self.assertEqual(source.snapshot().generation, generation + 1)

                before = source.snapshot()
                prepared_before = window._prepared
                with mock.patch.object(
                    image_pipeline,
                    "rerender_prepared_image",
                    side_effect=image_pipeline.ImagePipelineError("injected render error"),
                ):
                    window._overlay_toggled(True)
                self.assertIs(source.snapshot(), before)
                self.assertIs(window._prepared, prepared_before)
                self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.RUNNING)
                self.assertIn("letzter gültiger Frame", window.status_label.text())

                color_before_stop = window._overlay_color
                window.stop_lcd_button.click()
                stopping_snapshot = source.snapshot()
                window._set_overlay_color("#654321")
                self.assertEqual(window._overlay_color, color_before_stop)
                self.assertIs(source.snapshot(), stopping_snapshot)
            finally:
                if controllers and controllers[0].is_running:
                    controllers[0].request_stop()
                    controllers[0].join()
                    window._poll_refresh_controller()
                window.close()

    def test_transport_error_enters_error_without_retry_until_acknowledged(self) -> None:
        sender = FakeSender(error=lcd_transport.LcdTransportError("injected"))
        controllers: list[FakeRefreshController] = []

        def factory(source: lcd_refresh.FrameSource) -> FakeRefreshController:
            controller = FakeRefreshController(source, sender)
            controllers.append(controller)
            return controller

        window = self._window(controller_factory=factory)
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            window.hardware_live_checkbox.setChecked(True)
            window.start_lcd_button.click()
            controller = controllers[0]
            controller.join()
            window._poll_refresh_controller()

            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.ERROR)
            self.assertEqual(len(sender.frames), 1)
            self.assertFalse(window.start_lcd_button.isEnabled())
            self.assertFalse(window.acknowledge_error_button.isHidden())
            self.assertIn("kein Retry", window.status_label.text())

            window.acknowledge_error_button.click()
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.IDLE)
            self.assertTrue(window.start_lcd_button.isEnabled())
        finally:
            window.close()

    def test_close_requests_nonblocking_stop_before_accepting_close(self) -> None:
        release_sender = threading.Event()
        sender = FakeSender()
        controllers: list[FakeRefreshController] = []

        def factory(source: lcd_refresh.FrameSource) -> FakeRefreshController:
            controller = FakeRefreshController(
                source,
                sender,
                block_sender=release_sender,
            )
            controllers.append(controller)
            return controller

        window = self._window(controller_factory=factory)
        self.assertTrue(window.load_image(REFERENCE_PATH))
        window.hardware_live_checkbox.setChecked(True)
        window.show()
        window.start_lcd_button.click()
        controller = controllers[0]
        started = time.monotonic()
        window.close()
        elapsed = time.monotonic() - started
        self.assertLess(elapsed, 0.1)
        self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.STOPPING)
        self.assertEqual(controller.request_stop_calls, 1)
        self.assertTrue(window.isVisible())

        release_sender.set()
        controller.join()
        window._poll_refresh_controller()
        QApplication.processEvents()
        self.assertFalse(window.isVisible())


if __name__ == "__main__":
    unittest.main()
