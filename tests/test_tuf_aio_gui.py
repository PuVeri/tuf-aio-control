from __future__ import annotations

import json
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
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from PIL import Image

import image_pipeline
import gui_refresh_factory
import lcd_refresh
import lcd_runtime_safety
import lcd_transport
import refresh_diagnostics
import system_sensors
import telemetry
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
        diagnostics_factory: tuf_aio_gui.DiagnosticsFactory | None = None,
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
                diagnostics_factory=(
                    diagnostics_factory
                    or (lambda: refresh_diagnostics.NULL_DIAGNOSTICS)
                ),
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

    def test_reference_image_is_compatible_and_prepares_lcd_output(self) -> None:
        window = self._window()
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertFalse(hasattr(window, "hardware_live_checkbox"))
            self.assertEqual(window.original_size_value.text(), "320×320")
            self.assertEqual(window.output_size_value.text(), "320×320")
            self.assertEqual(window.segments_value.text(), "3")
            self.assertIn("ASUS-JPEG-Validator: PASS", window.validation_value.text())
            self.assertIsNotNone(window._final_pixmap)
        finally:
            window.close()

    def test_incompatible_image_disables_lcd_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.png"
            path.write_bytes(b"not an image")

            window = self._window()
            try:
                self.assertFalse(window.load_image(path))
                self.assertFalse(window.start_lcd_button.isEnabled())
                self.assertIn("Nicht sendbar", window.status_label.text())
            finally:
                window.close()

    def test_missing_device_is_shown_as_not_connected(self) -> None:
        window = self._window((None, "Interface 1 nicht eindeutig gefunden (Treffer: 0)"))
        try:
            self.assertEqual(window.device_status_label.text(), "Gerät: nicht verbunden")
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertFalse(window.start_lcd_button.isEnabled())
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
                    overlay_slots=window._overlay_slots(),
                    rotation_degrees=window._rotation_degrees,
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

    def test_rotation_cycles_persists_and_preview_matches_final_jpeg(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            settings = self._settings(path)
            settings.setValue(tuf_aio_gui.OVERLAY_ENABLED_SETTING, True)
            source_path = Path(directory) / "asymmetric.png"
            source = Image.new("RGB", (320, 320), "black")
            source.paste("red", (10, 10, 60, 60))
            source.paste("blue", (260, 260, 310, 310))
            source.save(source_path)
            window = self._window(settings=settings)
            try:
                self.assertTrue(window.load_image(source_path))
                observed = []
                for _ in range(4):
                    window.rotation_button.click()
                    observed.append(window._rotation_degrees)
                    assert window._prepared is not None
                    self.assertEqual(
                        window._prepared.rotation_degrees,
                        window._rotation_degrees,
                    )
                    preview = window._final_pixmap
                    assert preview is not None
                    expected = QImage.fromData(window._prepared.jpeg_bytes, "JPEG")
                    self.assertEqual(preview.toImage(), expected)
                self.assertEqual(observed, [90, 180, 270, 0])
            finally:
                window.close()

            settings = self._settings(path)
            settings.setValue(tuf_aio_gui.ROTATION_SETTING, 270)
            settings.sync()
            restored = self._window(settings=self._settings(path))
            try:
                self.assertEqual(restored._rotation_degrees, 270)
                self.assertIn("270°", restored.rotation_button.text())
            finally:
                restored.close()

    def test_invalid_saved_rotation_falls_back_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            settings = self._settings(path)
            settings.setValue(tuf_aio_gui.ROTATION_SETTING, 45)
            settings.sync()
            window = self._window(settings=self._settings(path))
            try:
                self.assertEqual(window._rotation_degrees, 0)
                self.assertEqual(
                    int(window._settings.value(tuf_aio_gui.ROTATION_SETTING)), 0
                )
            finally:
                window.close()

    def test_slot_defaults_independent_selection_persistence_and_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            window = self._window(settings=self._settings(path))
            try:
                self.assertEqual(window._slot_metric_ids, tuf_aio_gui.SLOT_DEFAULTS)
                choices = {
                    window.slot_combos["top_left"].itemData(index)
                    for index in range(window.slot_combos["top_left"].count())
                }
                self.assertEqual(choices, {metric.value for metric in telemetry.MetricId})
                selections = {
                    "top_left": telemetry.MetricId.CPU_USAGE,
                    "top_right": telemetry.MetricId.GPU_USAGE,
                    "bottom_left": telemetry.MetricId.CPU_CCD,
                    "bottom_right": telemetry.MetricId.OFF,
                }
                for slot, metric_id in selections.items():
                    combo = window.slot_combos[slot]
                    combo.setCurrentIndex(combo.findData(metric_id.value))
                self.assertEqual(window._slot_metric_ids, selections)
            finally:
                window.close()

            restored = self._window(settings=self._settings(path))
            try:
                self.assertEqual(restored._slot_metric_ids, selections)
            finally:
                restored.close()

            settings = self._settings(path)
            settings.setValue(
                f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/top_right", "retired_metric"
            )
            settings.sync()
            fallback = self._window(settings=self._settings(path))
            try:
                self.assertIs(
                    fallback._slot_metric_ids["top_right"],
                    telemetry.MetricId.GPU_USAGE,
                )
            finally:
                fallback.close()

    def test_legacy_three_slot_settings_migrate_without_losing_valid_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.ini"
            settings = self._settings(path)
            settings.setValue(
                f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/top_left",
                telemetry.MetricId.GPU_MEMORY.value,
            )
            settings.setValue(
                f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/top_right",
                telemetry.MetricId.OFF.value,
            )
            settings.setValue(
                f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/bottom_center",
                telemetry.MetricId.CPU_CCD.value,
            )
            settings.sync()

            window = self._window(settings=self._settings(path))
            try:
                self.assertEqual(
                    window._slot_metric_ids,
                    {
                        "top_left": telemetry.MetricId.GPU_MEMORY,
                        "top_right": telemetry.MetricId.OFF,
                        "bottom_left": telemetry.MetricId.CPU_CCD,
                        "bottom_right": telemetry.MetricId.GPU_TEMPERATURE,
                    },
                )
                self.assertEqual(
                    window._settings.value(
                        f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/bottom_left"
                    ),
                    telemetry.MetricId.CPU_CCD.value,
                )
            finally:
                window.close()

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

    def test_selected_usage_change_publishes_once_without_hid_or_restart(self) -> None:
        snapshots = [
            system_sensors.TemperatureSnapshot(
                cpu_usage=system_sensors.PercentageValue(17.0, "/proc/stat")
            ),
            system_sensors.TemperatureSnapshot(
                cpu_usage=system_sensors.PercentageValue(18.0, "/proc/stat")
            ),
            system_sensors.TemperatureSnapshot(
                cpu_usage=system_sensors.PercentageValue(18.0, "/proc/stat")
            ),
        ]
        reader = mock.Mock(side_effect=snapshots)
        sender = FakeSender()
        controllers: list[FakeRefreshController] = []

        def factory(source: lcd_refresh.FrameSource) -> FakeRefreshController:
            controller = FakeRefreshController(source, sender)
            controllers.append(controller)
            return controller

        settings = self._settings(Path(self._settings_directory.name) / "usage.ini")
        settings.setValue(tuf_aio_gui.OVERLAY_ENABLED_SETTING, True)
        settings.setValue(
            f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/top_left",
            telemetry.MetricId.CPU_USAGE.value,
        )
        settings.setValue(
            f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/top_right",
            telemetry.MetricId.OFF.value,
        )
        settings.setValue(
            f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/bottom_left",
            telemetry.MetricId.OFF.value,
        )
        settings.setValue(
            f"{tuf_aio_gui.SLOT_SETTING_PREFIX}/bottom_right",
            telemetry.MetricId.OFF.value,
        )
        window = self._window(
            sensor_reader=reader,
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
                ) as send_once,
            ):
                window.start_lcd_button.click()
                source = window._frame_buffer
                assert source is not None
                controller = controllers[0]
                initial = source.snapshot().generation
                window.refresh_temperatures()
                self.assertEqual(source.snapshot().generation, initial + 1)
                window.refresh_temperatures()
                self.assertEqual(source.snapshot().generation, initial + 1)
                self.assertIs(window._refresh_controller, controller)
                hid_open.assert_not_called()
                send_once.assert_not_called()
        finally:
            if controllers and controllers[0].is_running:
                controllers[0].request_stop()
                controllers[0].join()
                window._poll_refresh_controller()
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
            self.assertTrue(window.start_lcd_button.isEnabled())

            window.start_lcd_button.click()
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.RUNNING)
            self.assertFalse(window.start_lcd_button.isEnabled())
            self.assertTrue(window.stop_lcd_button.isEnabled())
            self.assertTrue(window.select_button.isEnabled())
        finally:
            if controllers and controllers[0].is_running:
                controllers[0].request_stop()
                controllers[0].join()
                window._poll_refresh_controller()
            window.close()

    def test_start_is_explicit_without_redundant_hardware_approval(self) -> None:
        sender = FakeSender()
        controllers: list[FakeRefreshController] = []

        def build_controller(source: lcd_refresh.FrameSource) -> FakeRefreshController:
            controller = FakeRefreshController(source, sender)
            controllers.append(controller)
            return controller

        factory = mock.Mock(side_effect=build_controller)
        window = self._window(controller_factory=factory)
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertFalse(hasattr(window, "hardware_live_checkbox"))
            self.assertFalse(
                any(
                    checkbox.text() == "Hardware-Livebetrieb freigeben"
                    for checkbox in window.findChildren(tuf_aio_gui.QCheckBox)
                )
            )
            self.assertTrue(window.start_lcd_button.isEnabled())
            factory.assert_not_called()
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
            ):
                window.start_lcd()
            factory.assert_called_once()
            device_open.assert_not_called()
            send_once.assert_not_called()
            self.assertEqual(window._refresh_state, tuf_aio_gui.GuiRefreshState.RUNNING)
        finally:
            if controllers and controllers[0].is_running:
                controllers[0].request_stop()
                controllers[0].join()
                window._poll_refresh_controller()
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

    def test_production_runs_past_old_hardcaps_until_explicit_stop(
        self,
    ) -> None:
        class FastClock:
            def __init__(self) -> None:
                self.now = 0.0

            def __call__(self) -> float:
                return self.now

            def wait(self, event: threading.Event, timeout: float) -> bool:
                if event.is_set():
                    return True
                self.now += timeout
                return event.is_set()

        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "gui-refresh.jsonl"
            diagnostics = refresh_diagnostics.JsonlRefreshDiagnostics(log_path)
            clock = FastClock()
            controllers: list[lcd_refresh.RefreshController] = []
            send_calls = 0
            fake_writes = 0
            active_sends = 0
            maximum_active = 0

            def build_controller(
                plan: lcd_refresh.RefreshPlan,
                sender: lcd_refresh.FrameSender,
                *,
                frame_source: lcd_refresh.FrameSource,
            ) -> lcd_refresh.RefreshController:
                controller = lcd_refresh.RefreshController(
                    plan,
                    sender,
                    frame_source=frame_source,
                    clock=clock,
                    wait_function=clock.wait,
                )
                controllers.append(controller)
                return controller

            factory = gui_refresh_factory.ProductionControllerFactory(
                device_discovery=mock.Mock(return_value=(self._device(), "fake")),
                competing_writer_finder=mock.Mock(return_value=()),
                controller_builder=build_controller,
            )

            def fake_send_once(
                device: lcd_transport.HidrawInterface,
                jpeg: bytes,
                **kwargs: object,
            ) -> int:
                nonlocal send_calls, fake_writes, active_sends, maximum_active
                self.assertEqual(device.interface_number, 1)
                observer = kwargs["write_observer"]
                segments = lcd_transport.build_segments(jpeg)
                send_calls += 1
                active_sends += 1
                maximum_active = max(maximum_active, active_sends)
                try:
                    for segment in segments:
                        observer(segment)  # type: ignore[operator]
                        fake_writes += 1
                finally:
                    active_sends -= 1
                if send_calls == 35:
                    controllers[0].request_stop()
                return len(segments)

            window = self._window(
                controller_factory=factory,
                diagnostics_factory=lambda: diagnostics,
            )
            try:
                self.assertTrue(window.load_image(REFERENCE_PATH))
                with (
                    mock.patch.object(
                        lcd_refresh.lcd_transport,
                        "send_frame_once",
                        side_effect=fake_send_once,
                    ),
                    mock.patch.object(
                        lcd_transport.os,
                        "open",
                        side_effect=AssertionError("real hidraw open called"),
                    ) as real_open,
                ):
                    window.start_lcd_button.click()
                    self._wait_until(lambda: bool(controllers[0].result))
                    window._poll_refresh_controller()
                real_open.assert_not_called()

                result = controllers[0].result
                assert result is not None
                self.assertEqual(result.frames_sent, 35)
                self.assertEqual(
                    result.stop_reason, lcd_refresh.RefreshStopReason.EXPLICIT_STOP
                )
                self.assertGreater(result.elapsed_seconds, 30.0)
                self.assertEqual(send_calls, 35)
                self.assertEqual(fake_writes, 105)
                self.assertEqual(maximum_active, 1)

                entries = [
                    json.loads(line)
                    for line in log_path.read_text(encoding="utf-8").splitlines()
                ]
                events = [entry["event"] for entry in entries]
                self.assertIn("start_requested", events)
                self.assertIn("production_factory_created", events)
                self.assertIn("refresh_controller_created", events)
                self.assertIn("worker_started", events)
                self.assertEqual(events.count("frame_snapshot"), 35)
                self.assertEqual(events.count("send_frame_once_called"), 35)
                returned = [
                    entry
                    for entry in entries
                    if entry["event"] == "send_frame_once_returned"
                ]
                self.assertEqual(len(returned), 35)
                self.assertEqual(
                    sum(entry["completed_segments"] for entry in returned), 105
                )
                self.assertEqual(events.count("frame_count_advanced"), 35)
                self.assertIn("handle_closed", events)
                self.assertIn("worker_ended", events)
                terminal = next(
                    entry for entry in entries if entry["event"] == "session_stopped"
                )
                self.assertEqual(terminal["frame_count"], 35)
                self.assertEqual(terminal["stop_reason"], "user")
                timestamps = [entry["monotonic_seconds"] for entry in entries]
                self.assertEqual(timestamps, sorted(timestamps))
                self.assertTrue(
                    all(
                        "jpeg_bytes" not in entry and "payload" not in entry
                        for entry in entries
                    )
                )
            finally:
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
                window.start_lcd_button.click()
                source = window._frame_buffer
                assert source is not None
                controller = controllers[0]

                generation = source.snapshot().generation
                window._set_overlay_color("#12ABCD")
                self.assertEqual(source.snapshot().generation, generation + 1)

                generation = source.snapshot().generation
                window.rotation_button.click()
                self.assertEqual(source.snapshot().generation, generation + 1)
                self.assertIs(window._refresh_controller, controller)

                generation = source.snapshot().generation
                combo = window.slot_combos["top_left"]
                combo.setCurrentIndex(
                    combo.findData(telemetry.MetricId.GPU_MEMORY.value)
                )
                self.assertEqual(source.snapshot().generation, generation + 1)
                self.assertIs(window._refresh_controller, controller)

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
