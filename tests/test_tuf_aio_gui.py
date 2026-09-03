from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import lcd_transport
import system_sensors
import tuf_aio_gui


class TufAioGuiOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _device() -> lcd_transport.HidrawInterface:
        return lcd_transport.HidrawInterface(
            device_path="/dev/hidraw-never-opened",
            sysfs_path="/sys/class/hidraw/hidraw-never-opened",
            interface_number=1,
            manufacturer="ASUS",
            product="TUF AIO",
            serial=None,
            vendor_id="0b05",
            product_id="1c7b",
            input_report_bytes=16,
            output_report_bytes=1024,
            feature_report_bytes=None,
            report_ids=(),
            readable=False,
            udev_properties={},
        )

    def _window(
        self,
        discovery: tuple[lcd_transport.HidrawInterface | None, str] | None = None,
        sensor_reader: tuf_aio_gui.TemperatureReader | None = None,
        settings: QSettings | None = None,
    ) -> tuf_aio_gui.MainWindow:
        result = discovery if discovery is not None else (self._device(), "gültig")
        reader = sensor_reader or system_sensors.TemperatureSnapshot
        with mock.patch.object(
            tuf_aio_gui.transport, "discover_lcd_interface", return_value=result
        ):
            return tuf_aio_gui.MainWindow(sensor_reader=reader, settings=settings)

    @staticmethod
    def _settings(path: Path) -> QSettings:
        return QSettings(str(path), QSettings.Format.IniFormat)

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


if __name__ == "__main__":
    unittest.main()
