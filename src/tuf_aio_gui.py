#!/usr/bin/env python3
"""PySide6 desktop UI for one explicitly requested ASUS LCD image transfer."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import lcd_transport as transport


class MainWindow(QMainWindow):
    """Single-image UI; all protocol and device work stays in lcd_transport."""

    def __init__(self) -> None:
        super().__init__()
        self._selected_path: Path | None = None
        self._preview_pixmap: QPixmap | None = None

        self.setWindowTitle("TUF AIO Control")
        self.resize(720, 780)
        self._build_ui()
        self._apply_style()
        self.refresh_device_status()

    def _build_ui(self) -> None:
        central = QWidget(self)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(28, 24, 28, 24)
        outer.setSpacing(18)

        title = QLabel("TUF AIO Control")
        title.setObjectName("title")
        outer.addWidget(title)

        device_card = QFrame()
        device_card.setObjectName("card")
        device_layout = QHBoxLayout(device_card)
        self.device_dot = QLabel("●")
        self.device_dot.setObjectName("deviceDot")
        self.device_status_label = QLabel("Gerät wird geprüft …")
        self.device_status_label.setObjectName("deviceStatus")
        self.device_detail_label = QLabel("")
        self.device_detail_label.setObjectName("muted")
        device_text = QVBoxLayout()
        device_text.addWidget(self.device_status_label)
        device_text.addWidget(self.device_detail_label)
        device_layout.addWidget(self.device_dot)
        device_layout.addLayout(device_text, 1)
        outer.addWidget(device_card)

        preview_card = QFrame()
        preview_card.setObjectName("previewCard")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        self.preview_label = QLabel("Noch kein Bild ausgewählt")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(320, 320)
        self.preview_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.preview_label.setObjectName("preview")
        preview_layout.addWidget(self.preview_label, 1)
        outer.addWidget(preview_card, 1)

        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QGridLayout(info_card)
        info_layout.setHorizontalSpacing(18)
        info_layout.setVerticalSpacing(8)

        self.path_value = self._add_info_row(info_layout, 0, "Datei")
        self.resolution_value = self._add_info_row(info_layout, 1, "Auflösung")
        self.profile_value = self._add_info_row(info_layout, 2, "JPEG-Profil")
        self.size_value = self._add_info_row(info_layout, 3, "Dateigröße")
        self.segments_value = self._add_info_row(info_layout, 4, "Segmentzahl")
        self.padding_value = self._add_info_row(info_layout, 5, "Padding")
        self.validation_value = self._add_info_row(info_layout, 6, "Validierung")
        self.path_value.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.path_value.setWordWrap(True)
        outer.addWidget(info_card)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)
        self.select_button = QPushButton("Bild auswählen")
        self.select_button.clicked.connect(self.choose_image)
        self.send_button = QPushButton("Auf Display senden")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_selected_image)
        button_layout.addWidget(self.select_button)
        button_layout.addWidget(self.send_button)
        outer.addLayout(button_layout)

        self.status_label = QLabel("Status: Bitte ein kompatibles JPEG auswählen")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)

        self.setCentralWidget(central)

    @staticmethod
    def _add_info_row(layout: QGridLayout, row: int, name: str) -> QLabel:
        key = QLabel(f"{name}:")
        key.setObjectName("infoKey")
        value = QLabel("—")
        value.setObjectName("infoValue")
        layout.addWidget(key, row, 0, Qt.AlignmentFlag.AlignTop)
        layout.addWidget(value, row, 1)
        layout.setColumnStretch(1, 1)
        return value

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #111419;
                color: #e7e9ed;
                font-family: "Noto Sans", "DejaVu Sans", sans-serif;
                font-size: 14px;
            }
            QLabel#title {
                font-size: 26px;
                font-weight: 700;
                color: #f4f5f7;
            }
            QFrame#card, QFrame#previewCard {
                background: #1a1f26;
                border: 1px solid #2b323d;
                border-radius: 10px;
            }
            QLabel#deviceDot {
                color: #7f8996;
                font-size: 20px;
            }
            QLabel#deviceStatus {
                font-weight: 600;
                font-size: 15px;
            }
            QLabel#muted, QLabel#infoKey {
                color: #9ca5b1;
            }
            QLabel#preview {
                background: #0d1014;
                border: 1px dashed #343c48;
                border-radius: 7px;
                color: #747f8c;
            }
            QPushButton {
                min-height: 42px;
                padding: 0 18px;
                border-radius: 7px;
                border: 1px solid #3a424e;
                background: #252b34;
                color: #edf0f4;
                font-weight: 600;
            }
            QPushButton:hover { background: #303844; }
            QPushButton:pressed { background: #20262e; }
            QPushButton#primaryButton {
                background: #c53b3f;
                border-color: #d44a4e;
            }
            QPushButton#primaryButton:hover { background: #d2464a; }
            QPushButton:disabled {
                background: #20242a;
                border-color: #2c323a;
                color: #68717d;
            }
            QLabel#status {
                padding: 10px 12px;
                background: #171b21;
                border-radius: 6px;
                color: #bdc4cd;
            }
            """
        )

    def refresh_device_status(self) -> transport.HidrawInterface | None:
        """Perform one read-only discovery and update the visible status."""
        try:
            device, detail = transport.discover_lcd_interface()
        except (OSError, RuntimeError, ValueError) as error:
            self._show_device_problem(f"Geräteprüfung fehlgeschlagen: {error}")
            return None

        if device is not None:
            self.device_dot.setStyleSheet("color: #55c987;")
            self.device_status_label.setText("Gerät: verbunden")
            self.device_detail_label.setText(
                f"{device.vendor_id}:{device.product_id} · Interface 1 · "
                f"{device.device_path}"
            )
            return device

        if "Treffer: 0" in detail:
            self.device_dot.setStyleSheet("color: #7f8996;")
            self.device_status_label.setText("Gerät: nicht verbunden")
            self.device_detail_label.setText("0b05:1c7b / Interface 1 nicht gefunden")
        else:
            self._show_device_problem(detail)
        return None

    def _show_device_problem(self, detail: str) -> None:
        self.device_dot.setStyleSheet("color: #e5a64b;")
        self.device_status_label.setText("Gerät: unerwartete Reportstruktur")
        self.device_detail_label.setText(detail)

    def choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "JPEG für das AIO-LCD auswählen",
            "",
            "JPEG-Bilder (*.jpg *.jpeg);;Alle Dateien (*)",
        )
        if filename:
            self.load_image(Path(filename))

    def load_image(self, path: Path) -> bool:
        """Load a preview and validate sendability without opening a device."""
        resolved = path.expanduser().resolve()
        self._selected_path = resolved
        self.path_value.setText(str(resolved))
        self._load_preview(resolved)

        try:
            size = resolved.stat().st_size
        except OSError:
            size = None
        self.size_value.setText(f"{size} Byte" if size is not None else "unbekannt")

        try:
            jpeg = transport.load_jpeg(resolved)
            info = transport.validate_jpeg(jpeg)
        except (transport.JpegValidationError, OSError, RuntimeError, ValueError) as error:
            self._set_invalid_image(str(error))
            return False

        self.resolution_value.setText(f"{info.width}×{info.height}")
        self.profile_value.setText("SOF0 / Baseline · 8 Bit · JFIF-YCbCr 4:2:0")
        self.segments_value.setText(str(info.segment_count))
        self.padding_value.setText(f"{info.padding_length} Byte · ausschließlich 00")
        self.validation_value.setText("kompatibel")
        self.validation_value.setStyleSheet("color: #55c987;")
        self.send_button.setEnabled(True)
        self.status_label.setText("Status: Bereit – Senden erfolgt nur nach Klick")
        return True

    def _load_preview(self, path: Path) -> None:
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._preview_pixmap = None
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("Für diese Datei ist keine Vorschau verfügbar")
            self.resolution_value.setText("unbekannt")
            return

        self._preview_pixmap = pixmap
        self.resolution_value.setText(f"{pixmap.width()}×{pixmap.height()}")
        self._update_scaled_preview()

    def _update_scaled_preview(self) -> None:
        if self._preview_pixmap is None:
            return
        scaled = self._preview_pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setText("")
        self.preview_label.setPixmap(scaled)

    def _set_invalid_image(self, reason: str) -> None:
        self.profile_value.setText("nicht kompatibel")
        self.segments_value.setText("—")
        self.padding_value.setText("—")
        self.validation_value.setText(reason)
        self.validation_value.setStyleSheet("color: #e5a64b;")
        self.validation_value.setWordWrap(True)
        self.send_button.setEnabled(False)
        self.status_label.setText(f"Status: Nicht sendbar – {reason}")

    def send_selected_image(self) -> None:
        """Revalidate everything and request exactly one synchronous frame."""
        if self._selected_path is None:
            self._show_send_error("Kein Bild ausgewählt.")
            return

        try:
            jpeg = transport.load_jpeg(self._selected_path)
            info = transport.validate_jpeg(jpeg)
        except (transport.JpegValidationError, OSError, RuntimeError, ValueError) as error:
            self._set_invalid_image(str(error))
            self._show_send_error(f"JPEG ist nicht mehr sendbar: {error}")
            return

        device = self.refresh_device_status()
        if device is None:
            self._show_send_error("Kein sicher verwendbares LCD-Gerät gefunden.")
            return

        self.status_label.setText(
            f"Status: Sende genau einen Frame mit {info.segment_count} Segmenten …"
        )
        try:
            written = transport.send_frame_once(device, jpeg)
        except PermissionError as error:
            self._show_send_error(f"Schreibberechtigung fehlt: {error}")
            return
        except (transport.LcdTransportError, OSError, RuntimeError) as error:
            self._show_send_error(f"Transfer abgebrochen: {error}")
            return

        self.status_label.setText(
            f"Status: Ein Frame erfolgreich gesendet ({written} Writes, kein Retry)"
        )

    def _show_send_error(self, message: str) -> None:
        self.status_label.setText(f"Status: Fehler – {message}")
        QMessageBox.critical(self, "TUF AIO Control", message)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._update_scaled_preview()


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
