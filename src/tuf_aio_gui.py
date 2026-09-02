#!/usr/bin/env python3
"""PySide6 UI for one explicitly requested, prepared ASUS LCD image."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
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

import image_pipeline
import lcd_transport as transport


class MainWindow(QMainWindow):
    """Single-image UI; conversion and transport stay in separate modules."""

    def __init__(self) -> None:
        super().__init__()
        self._selected_path: Path | None = None
        self._prepared: image_pipeline.PreparedImage | None = None
        self._device_ready = False
        self._original_pixmap: QPixmap | None = None
        self._final_pixmap: QPixmap | None = None

        self.setWindowTitle("TUF AIO Control")
        self.resize(920, 820)
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
        self.refresh_button = QPushButton("Gerät aktualisieren")
        self.refresh_button.clicked.connect(self.refresh_device_status)
        device_layout.addWidget(self.device_dot)
        device_layout.addLayout(device_text, 1)
        device_layout.addWidget(self.refresh_button)
        outer.addWidget(device_card)

        previews = QFrame()
        previews.setObjectName("previewCard")
        preview_grid = QGridLayout(previews)
        preview_grid.setContentsMargins(18, 18, 18, 18)
        preview_grid.setHorizontalSpacing(18)
        preview_grid.addWidget(self._preview_title("Original"), 0, 0)
        preview_grid.addWidget(self._preview_title("LCD-Ausgabe 320×320"), 0, 1)
        self.original_preview = self._preview_label("Noch kein Bild ausgewählt")
        self.final_preview = self._preview_label("Noch keine Ausgabe erzeugt")
        preview_grid.addWidget(self.original_preview, 1, 0)
        preview_grid.addWidget(self.final_preview, 1, 1)
        preview_grid.setColumnStretch(0, 1)
        preview_grid.setColumnStretch(1, 1)
        outer.addWidget(previews, 1)

        options = QFrame()
        options.setObjectName("card")
        options_layout = QHBoxLayout(options)
        options_layout.addWidget(QLabel("Skalierung:"))
        self.scale_mode = QComboBox()
        self.scale_mode.addItem("Zuschneiden", "crop")
        self.scale_mode.addItem("Einpassen", "fit")
        self.scale_mode.currentIndexChanged.connect(self._scale_mode_changed)
        options_layout.addWidget(self.scale_mode)
        options_layout.addStretch(1)
        outer.addWidget(options)

        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QGridLayout(info_card)
        info_layout.setHorizontalSpacing(18)
        info_layout.setVerticalSpacing(8)
        self.path_value = self._add_info_row(info_layout, 0, "Datei")
        self.original_size_value = self._add_info_row(info_layout, 1, "Originalauflösung")
        self.input_format_value = self._add_info_row(info_layout, 2, "Eingabeformat")
        self.output_size_value = self._add_info_row(info_layout, 3, "Ausgabeauflösung")
        self.profile_value = self._add_info_row(info_layout, 4, "JPEG-Ausgabe")
        self.jpeg_size_value = self._add_info_row(info_layout, 5, "JPEG-Größe")
        self.segments_value = self._add_info_row(info_layout, 6, "Segmentzahl")
        self.padding_value = self._add_info_row(info_layout, 7, "Padding")
        self.validation_value = self._add_info_row(info_layout, 8, "Validierung")
        self.path_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_value.setWordWrap(True)
        outer.addWidget(info_card)

        buttons = QHBoxLayout()
        buttons.setSpacing(12)
        self.select_button = QPushButton("Bild auswählen")
        self.select_button.clicked.connect(self.choose_image)
        self.send_button = QPushButton("Auf Display senden")
        self.send_button.setObjectName("primaryButton")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send_selected_image)
        buttons.addWidget(self.select_button)
        buttons.addWidget(self.send_button)
        outer.addLayout(buttons)

        self.status_label = QLabel("Status: Bitte ein Bild auswählen")
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        outer.addWidget(self.status_label)
        self.setCentralWidget(central)

    @staticmethod
    def _preview_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("previewTitle")
        return label

    @staticmethod
    def _preview_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumSize(300, 300)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        label.setObjectName("preview")
        return label

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
                background: #111419; color: #e7e9ed;
                font-family: "Noto Sans", "DejaVu Sans", sans-serif; font-size: 14px;
            }
            QLabel#title { font-size: 26px; font-weight: 700; color: #f4f5f7; }
            QFrame#card, QFrame#previewCard {
                background: #1a1f26; border: 1px solid #2b323d; border-radius: 10px;
            }
            QLabel#deviceDot { color: #7f8996; font-size: 20px; }
            QLabel#deviceStatus, QLabel#previewTitle { font-weight: 600; font-size: 15px; }
            QLabel#muted, QLabel#infoKey { color: #9ca5b1; }
            QLabel#preview {
                background: #0d1014; border: 1px dashed #343c48;
                border-radius: 7px; color: #747f8c;
            }
            QPushButton, QComboBox {
                min-height: 42px; padding: 0 18px; border-radius: 7px;
                border: 1px solid #3a424e; background: #252b34;
                color: #edf0f4; font-weight: 600;
            }
            QPushButton:hover, QComboBox:hover { background: #303844; }
            QPushButton:pressed { background: #20262e; }
            QPushButton#primaryButton { background: #c53b3f; border-color: #d44a4e; }
            QPushButton#primaryButton:hover { background: #d2464a; }
            QPushButton:disabled {
                background: #20242a; border-color: #2c323a; color: #68717d;
            }
            QLabel#status {
                padding: 10px 12px; background: #171b21;
                border-radius: 6px; color: #bdc4cd;
            }
            """
        )

    def refresh_device_status(self) -> transport.HidrawInterface | None:
        """Perform one read-only discovery and update the visible status."""
        try:
            device, detail = transport.discover_lcd_interface()
        except (OSError, RuntimeError, ValueError) as error:
            self._device_ready = False
            self._show_device_problem(f"Geräteprüfung fehlgeschlagen: {error}")
            self._update_send_enabled()
            return None

        self._device_ready = device is not None
        if device is not None:
            self.device_dot.setStyleSheet("color: #55c987;")
            self.device_status_label.setText("Gerät: verbunden")
            self.device_detail_label.setText(
                f"{device.vendor_id}:{device.product_id} · Interface 1 · {device.device_path}"
            )
        elif "Treffer: 0" in detail:
            self.device_dot.setStyleSheet("color: #7f8996;")
            self.device_status_label.setText("Gerät: nicht verbunden")
            self.device_detail_label.setText("0b05:1c7b / Interface 1 nicht gefunden")
        else:
            self._show_device_problem(detail)
        self._update_send_enabled()
        return device

    def _show_device_problem(self, detail: str) -> None:
        self.device_dot.setStyleSheet("color: #e5a64b;")
        self.device_status_label.setText("Gerät: unerwartete Reportstruktur")
        self.device_detail_label.setText(detail)

    def choose_image(self) -> None:
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Bild für das AIO-LCD auswählen",
            "",
            "Unterstützte Bilder (*.jpg *.jpeg *.png *.webp *.bmp *.gif);;Alle Dateien (*)",
        )
        if filename:
            self.load_image(Path(filename))

    def _scale_mode_changed(self) -> None:
        if self._selected_path is not None:
            self.load_image(self._selected_path)

    def load_image(self, path: Path) -> bool:
        """Show frame 0 of the source and prepare one validated output JPEG."""
        resolved = path.expanduser().resolve()
        self._selected_path = resolved
        self.path_value.setText(str(resolved))
        preview_size = self._load_original_preview(resolved)
        self.original_size_value.setText(
            f"{preview_size[0]}×{preview_size[1]}" if preview_size else "unbekannt"
        )
        self._prepared = None
        self._final_pixmap = None
        self.final_preview.setPixmap(QPixmap())
        self.final_preview.setText("Ausgabe wird vorbereitet …")
        self._update_send_enabled()

        mode = self.scale_mode.currentData()
        try:
            prepared = image_pipeline.prepare_image(resolved, mode=mode)
            self._load_final_preview(prepared.jpeg_bytes)
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            self._prepared = None
            self._final_pixmap = None
            self.final_preview.setPixmap(QPixmap())
            self.final_preview.setText("Keine kompatible LCD-Ausgabe")
            self._set_invalid_image(str(error))
            return False

        self._prepared = prepared
        oriented_text = f"{prepared.oriented_size[0]}×{prepared.oriented_size[1]}"
        if prepared.source_size != prepared.oriented_size:
            oriented_text += (
                f" · EXIF-ausgerichtet (Datei {prepared.source_size[0]}×"
                f"{prepared.source_size[1]})"
            )
        self.original_size_value.setText(oriented_text)
        input_text = prepared.source_format
        if prepared.gif_first_frame_only:
            input_text = "GIF · erstes Bild als Standbild"
        self.input_format_value.setText(input_text)
        self.output_size_value.setText("320×320")
        self.profile_value.setText("SOF0 · 8 Bit · JFIF-YCbCr 4:2:0 · Qualität 60")
        self.jpeg_size_value.setText(f"{len(prepared.jpeg_bytes)} Byte")
        self.segments_value.setText(str(prepared.jpeg_info.segment_count))
        self.padding_value.setText(
            f"{prepared.jpeg_info.padding_length} Byte · ausschließlich 00"
        )
        self.validation_value.setText("ASUS-JPEG-Validator: PASS")
        self.validation_value.setStyleSheet("color: #55c987;")
        self.status_label.setText("Status: Bild vorbereitet – Senden nur nach Klick")
        self._update_send_enabled()
        return True

    def _load_original_preview(self, path: Path) -> tuple[int, int] | None:
        reader = QImageReader(str(path))
        reader.setAutoTransform(True)
        image = reader.read()  # For GIF this reads only frame 0; no QMovie is used.
        if image.isNull():
            self._original_pixmap = None
            self.original_preview.setPixmap(QPixmap())
            self.original_preview.setText("Keine Originalvorschau verfügbar")
            return None
        self._original_pixmap = QPixmap.fromImage(image)
        self._update_scaled_preview(self.original_preview, self._original_pixmap)
        return image.width(), image.height()

    def _load_final_preview(self, jpeg: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(jpeg, "JPEG"):
            raise image_pipeline.ImagePipelineError(
                "Das validierte JPEG konnte nicht als Vorschau geladen werden"
            )
        self._final_pixmap = pixmap
        self._update_scaled_preview(self.final_preview, pixmap)

    @staticmethod
    def _update_scaled_preview(label: QLabel, pixmap: QPixmap | None) -> None:
        if pixmap is None:
            return
        scaled = pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label.setText("")
        label.setPixmap(scaled)

    def _set_invalid_image(self, reason: str) -> None:
        self.input_format_value.setText("nicht sendbar")
        self.output_size_value.setText("—")
        self.profile_value.setText("—")
        self.jpeg_size_value.setText("—")
        self.segments_value.setText("—")
        self.padding_value.setText("—")
        self.validation_value.setText(reason)
        self.validation_value.setStyleSheet("color: #e5a64b;")
        self.validation_value.setWordWrap(True)
        self.status_label.setText(f"Status: Nicht sendbar – {reason}")
        self._update_send_enabled()

    def _update_send_enabled(self) -> None:
        self.send_button.setEnabled(self._prepared is not None and self._device_ready)

    def send_selected_image(self) -> None:
        """Revalidate the prepared JPEG and request exactly one existing transfer."""
        if self._prepared is None:
            self._show_send_error("Kein validiertes Ausgabebild vorhanden.")
            return

        jpeg = self._prepared.jpeg_bytes
        try:
            transport.validate_jpeg(jpeg)
        except (transport.JpegValidationError, RuntimeError, ValueError) as error:
            self._prepared = None
            self._set_invalid_image(str(error))
            self._show_send_error(f"Ausgabe-JPEG ist nicht mehr sendbar: {error}")
            return

        device = self.refresh_device_status()
        if device is None:
            self._show_send_error("Kein sicher verwendbares LCD-Gerät gefunden.")
            return

        self.status_label.setText(
            f"Status: Sende genau einen Frame mit "
            f"{self._prepared.jpeg_info.segment_count} Segmenten …"
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
        self._update_scaled_preview(self.original_preview, self._original_pixmap)
        self._update_scaled_preview(self.final_preview, self._final_pixmap)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
