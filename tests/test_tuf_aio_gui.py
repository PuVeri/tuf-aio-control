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

from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

import lcd_transport
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
    ) -> tuf_aio_gui.MainWindow:
        result = discovery if discovery is not None else (self._device(), "gültig")
        with mock.patch.object(
            tuf_aio_gui.transport, "discover_lcd_interface", return_value=result
        ):
            return tuf_aio_gui.MainWindow()

    def test_reference_image_is_compatible_and_enables_send(self) -> None:
        window = self._window()
        try:
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertTrue(window.send_button.isEnabled())
            self.assertEqual(window.resolution_value.text(), "320×320")
            self.assertEqual(window.segments_value.text(), "3")
            self.assertIn("824", window.padding_value.text())
            self.assertEqual(window.validation_value.text(), "kompatibel")
        finally:
            window.close()

    def test_incompatible_previewable_image_disables_send(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "preview-only.png"
            image = QImage(320, 320, QImage.Format.Format_RGB32)
            image.fill(QColor("white"))
            self.assertTrue(image.save(str(path), "PNG"))

            window = self._window()
            try:
                self.assertFalse(window.load_image(path))
                self.assertFalse(window.send_button.isEnabled())
                self.assertIsNotNone(window._preview_pixmap)
                self.assertFalse(window._preview_pixmap.isNull())
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


if __name__ == "__main__":
    unittest.main()
