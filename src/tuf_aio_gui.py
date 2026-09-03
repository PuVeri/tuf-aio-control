#!/usr/bin/env python3
"""PySide6 UI for one explicitly requested, prepared ASUS LCD image."""

from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from PySide6.QtCore import QSettings, QTimer, Qt
from PySide6.QtGui import QColor, QCloseEvent, QImageReader, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
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
import gui_refresh_factory
import lcd_refresh
import lcd_transport as transport
import system_sensors

TemperatureReader = Callable[[], system_sensors.TemperatureSnapshot]


class RefreshControllerLike(Protocol):
    @property
    def is_running(self) -> bool: ...

    @property
    def result(self) -> lcd_refresh.RefreshResult | None: ...

    def start(self) -> None: ...

    def request_stop(self) -> None: ...


ControllerFactory = Callable[[lcd_refresh.FrameSource], RefreshControllerLike]
SETTINGS_ORGANIZATION = "HeartDriveLab"
SETTINGS_APPLICATION = "tuf-aio-control"
OVERLAY_ENABLED_SETTING = "lcd_temperature_overlay/enabled"
OVERLAY_COLOR_SETTING = "lcd_temperature_overlay/color"


class GuiRefreshState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class MainWindow(QMainWindow):
    """Single-image UI; conversion and transport stay in separate modules."""

    def __init__(
        self,
        *,
        sensor_reader: TemperatureReader | None = None,
        settings: QSettings | None = None,
        controller_factory: ControllerFactory | None = None,
    ) -> None:
        super().__init__()
        self._sensor_reader = sensor_reader or system_sensors.read_lcd_temperatures
        self._controller_factory = controller_factory
        self._settings = (
            settings
            if settings is not None
            else QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
        )
        self._overlay_enabled = self._read_bool_setting(OVERLAY_ENABLED_SETTING)
        raw_color = self._settings.value(
            OVERLAY_COLOR_SETTING,
            image_pipeline.DEFAULT_OVERLAY_COLOR,
        )
        self._overlay_color = image_pipeline.normalize_overlay_color(raw_color)
        if raw_color != self._overlay_color:
            self._settings.setValue(OVERLAY_COLOR_SETTING, self._overlay_color)
            self._settings.sync()
        self._latest_temperature_snapshot = system_sensors.TemperatureSnapshot()
        self._selected_path: Path | None = None
        self._prepared: image_pipeline.PreparedImage | None = None
        self._device_ready = False
        self._original_pixmap: QPixmap | None = None
        self._final_pixmap: QPixmap | None = None
        self._refresh_state = GuiRefreshState.IDLE
        self._frame_buffer: lcd_refresh.LatestFrameBuffer | None = None
        self._refresh_controller: RefreshControllerLike | None = None
        self._last_refresh_result: lcd_refresh.RefreshResult | None = None
        self._close_when_stopped = False

        self.setWindowTitle("TUF AIO Control")
        self.resize(920, 900)
        self._build_ui()
        self._apply_style()
        self.refresh_device_status()
        self.refresh_temperatures()
        self._temperature_timer = QTimer(self)
        self._temperature_timer.setInterval(1000)
        self._temperature_timer.timeout.connect(self.refresh_temperatures)
        self._temperature_timer.start()
        self._refresh_state_timer = QTimer(self)
        self._refresh_state_timer.setInterval(25)
        self._refresh_state_timer.timeout.connect(self._poll_refresh_controller)
        self._refresh_state_timer.start()
        self._apply_refresh_state()

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
        self.hardware_live_checkbox = QCheckBox("Hardware-Livebetrieb freigeben")
        self.hardware_live_checkbox.setChecked(False)
        self.hardware_live_checkbox.setToolTip(
            "Entwicklungsfreigabe für reale HID-Writes; standardmäßig aus"
        )
        self.hardware_live_checkbox.toggled.connect(self._apply_refresh_state)
        device_layout.addWidget(self.device_dot)
        device_layout.addLayout(device_text, 1)
        device_layout.addWidget(self.hardware_live_checkbox)
        device_layout.addWidget(self.refresh_button)
        outer.addWidget(device_card)

        temperature_card = QFrame()
        temperature_card.setObjectName("card")
        temperature_layout = QGridLayout(temperature_card)
        temperature_layout.setHorizontalSpacing(24)
        temperature_layout.setVerticalSpacing(4)
        temperature_title = QLabel("Lokale Temperaturen")
        temperature_title.setObjectName("sectionTitle")
        temperature_layout.addWidget(temperature_title, 0, 0, 1, 3)
        (
            self.cpu_temperature_value,
            self.cpu_temperature_source,
        ) = self._add_temperature_column(temperature_layout, 1, 0, "CPU")
        (
            self.cpu_package_temperature_value,
            self.cpu_package_temperature_source,
        ) = self._add_temperature_column(
            temperature_layout, 1, 1, "CPU Package"
        )
        (
            self.gpu_temperature_value,
            self.gpu_temperature_source,
        ) = self._add_temperature_column(temperature_layout, 1, 2, "GPU")
        for column in range(3):
            temperature_layout.setColumnStretch(column, 1)
        outer.addWidget(temperature_card)

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
        self.overlay_checkbox = QCheckBox("Temperaturen auf LCD anzeigen")
        self.overlay_checkbox.setChecked(self._overlay_enabled)
        self.overlay_checkbox.toggled.connect(self._overlay_toggled)
        options_layout.addWidget(self.overlay_checkbox)
        self.overlay_color_button = QPushButton()
        self.overlay_color_button.clicked.connect(self._choose_overlay_color)
        self._update_overlay_color_button()
        options_layout.addWidget(self.overlay_color_button)
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
        self.start_lcd_button = QPushButton("LCD starten")
        self.start_lcd_button.clicked.connect(self.start_lcd)
        self.stop_lcd_button = QPushButton("LCD stoppen")
        self.stop_lcd_button.clicked.connect(self.stop_lcd)
        self.acknowledge_error_button = QPushButton("Fehler bestätigen")
        self.acknowledge_error_button.clicked.connect(self.acknowledge_refresh_error)
        buttons.addWidget(self.select_button)
        buttons.addWidget(self.send_button)
        buttons.addWidget(self.start_lcd_button)
        buttons.addWidget(self.stop_lcd_button)
        buttons.addWidget(self.acknowledge_error_button)
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

    @staticmethod
    def _add_temperature_column(
        layout: QGridLayout, row: int, column: int, name: str
    ) -> tuple[QLabel, QLabel]:
        key = QLabel(name)
        key.setObjectName("temperatureKey")
        value = QLabel("N/A")
        value.setObjectName("temperatureValue")
        source = QLabel("nicht verfügbar")
        source.setObjectName("muted")
        layout.addWidget(key, row, column)
        layout.addWidget(value, row + 1, column)
        layout.addWidget(source, row + 2, column)
        return value, source

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
            QLabel#deviceStatus, QLabel#previewTitle, QLabel#sectionTitle {
                font-weight: 600; font-size: 15px;
            }
            QLabel#muted, QLabel#infoKey { color: #9ca5b1; }
            QLabel#temperatureKey { color: #9ca5b1; font-weight: 600; }
            QLabel#temperatureValue { font-size: 22px; font-weight: 700; color: #f4f5f7; }
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

    def _read_bool_setting(self, key: str) -> bool:
        value = self._settings.value(key, False)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.casefold() in {"1", "true", "yes", "on"}
        return False

    def _overlay_config(self) -> image_pipeline.TemperatureOverlayConfig:
        return image_pipeline.TemperatureOverlayConfig(
            enabled=self._overlay_enabled,
            colors=image_pipeline.TemperatureOverlayColors.uniform(
                self._overlay_color
            ),
        )

    @staticmethod
    def _overlay_values(
        snapshot: system_sensors.TemperatureSnapshot,
    ) -> image_pipeline.TemperatureOverlayValues:
        return image_pipeline.TemperatureOverlayValues(
            cpu_package=(
                snapshot.cpu_package.celsius
                if snapshot.cpu_package is not None
                else None
            ),
            gpu=snapshot.gpu.celsius if snapshot.gpu is not None else None,
            cpu_ccd=(
                snapshot.cpu_ccd.celsius if snapshot.cpu_ccd is not None else None
            ),
        )

    def _overlay_toggled(self, enabled: bool) -> None:
        if self._refresh_state in {
            GuiRefreshState.STARTING,
            GuiRefreshState.STOPPING,
            GuiRefreshState.ERROR,
        }:
            return
        self._overlay_enabled = enabled
        self._settings.setValue(OVERLAY_ENABLED_SETTING, enabled)
        self._settings.sync()
        self._rerender_temperature_overlay()

    def _choose_overlay_color(self) -> None:
        selected = QColorDialog.getColor(
            QColor(self._overlay_color),
            self,
            "Farbe der LCD-Temperaturanzeige",
        )
        if selected.isValid():
            self._set_overlay_color(selected.name(QColor.NameFormat.HexRgb))

    def _set_overlay_color(self, color: object) -> None:
        if self._refresh_state in {
            GuiRefreshState.STARTING,
            GuiRefreshState.STOPPING,
            GuiRefreshState.ERROR,
        }:
            return
        self._overlay_color = image_pipeline.normalize_overlay_color(color)
        self._settings.setValue(OVERLAY_COLOR_SETTING, self._overlay_color)
        self._settings.sync()
        self._update_overlay_color_button()
        self._rerender_temperature_overlay()

    def _update_overlay_color_button(self) -> None:
        self.overlay_color_button.setText(f"Overlayfarbe: {self._overlay_color}")
        foreground = "#111111" if QColor(self._overlay_color).lightness() > 160 else "#FFFFFF"
        self.overlay_color_button.setStyleSheet(
            f"background: {self._overlay_color}; color: {foreground};"
        )

    @staticmethod
    def _show_temperature(
        value_label: QLabel,
        source_label: QLabel,
        reading: system_sensors.TemperatureValue | None,
    ) -> None:
        if reading is None:
            value_label.setText("N/A")
            source_label.setText("nicht verfügbar")
            value_label.setToolTip("Keine passende lokale hwmon-Quelle verfügbar")
            return
        value_label.setText(f"{reading.celsius:.1f} °C")
        source = f"{reading.sensor.hwmon_name} · {reading.sensor.label}"
        source_label.setText(source)
        value_label.setToolTip(f"Quelle: {source} · {reading.sensor.channel}")

    def refresh_temperatures(self) -> system_sensors.TemperatureSnapshot:
        """Sample local hwmon sources once without involving any HID path."""
        previous_values = self._overlay_values(self._latest_temperature_snapshot)
        try:
            snapshot = self._sensor_reader()
        except (OSError, RuntimeError, ValueError):
            snapshot = system_sensors.TemperatureSnapshot()
        self._show_temperature(
            self.cpu_temperature_value,
            self.cpu_temperature_source,
            snapshot.cpu,
        )
        self._show_temperature(
            self.cpu_package_temperature_value,
            self.cpu_package_temperature_source,
            snapshot.cpu_package,
        )
        self._show_temperature(
            self.gpu_temperature_value,
            self.gpu_temperature_source,
            snapshot.gpu,
        )
        self._latest_temperature_snapshot = snapshot
        if (
            self._overlay_enabled
            and self._prepared is not None
            and self._refresh_state in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}
            and self._overlay_values(snapshot) != previous_values
        ):
            self._rerender_temperature_overlay()
        return snapshot

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
        if (
            self._selected_path is not None
            and self._refresh_state in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}
        ):
            self.load_image(self._selected_path)

    def load_image(self, path: Path) -> bool:
        """Show frame 0 of the source and prepare one validated output JPEG."""
        if self._refresh_state not in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}:
            return False
        resolved = path.expanduser().resolve()
        self.path_value.setText(str(resolved))
        preview_size = self._load_original_preview(resolved)
        self.original_size_value.setText(
            f"{preview_size[0]}×{preview_size[1]}" if preview_size else "unbekannt"
        )
        previous_prepared = self._prepared
        if self._refresh_state is GuiRefreshState.IDLE:
            self._prepared = None
            self._final_pixmap = None
            self.final_preview.setPixmap(QPixmap())
            self.final_preview.setText("Ausgabe wird vorbereitet …")
            self._update_send_enabled()

        mode = self.scale_mode.currentData()
        try:
            prepared = image_pipeline.prepare_image(
                resolved,
                mode=mode,
                overlay_config=self._overlay_config(),
                temperatures=self._overlay_values(
                    self._latest_temperature_snapshot
                ),
            )
            self._load_final_preview(prepared.jpeg_bytes)
            self._publish_running_frame(prepared.jpeg_bytes)
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            if self._refresh_state is GuiRefreshState.RUNNING:
                self._prepared = previous_prepared
                self._show_render_error(str(error))
            else:
                self._prepared = None
                self._final_pixmap = None
                self.final_preview.setPixmap(QPixmap())
                self.final_preview.setText("Keine kompatible LCD-Ausgabe")
                self._set_invalid_image(str(error))
            return False

        self._selected_path = resolved
        self._show_prepared_image(prepared)
        return True

    def _show_prepared_image(self, prepared: image_pipeline.PreparedImage) -> None:
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
        if self._refresh_state is GuiRefreshState.RUNNING:
            generation = self._frame_buffer.snapshot().generation if self._frame_buffer else 0
            self.status_label.setText(
                f"Status: LCD läuft · Framegeneration {generation} veröffentlicht"
            )
        else:
            self.status_label.setText("Status: Bild vorbereitet – Senden nur nach Klick")
        self._update_send_enabled()

    def _rerender_temperature_overlay(self) -> None:
        if self._prepared is None:
            return
        try:
            prepared = image_pipeline.rerender_prepared_image(
                self._prepared,
                overlay_config=self._overlay_config(),
                temperatures=self._overlay_values(
                    self._latest_temperature_snapshot
                ),
            )
            self._load_final_preview(prepared.jpeg_bytes)
            self._publish_running_frame(prepared.jpeg_bytes)
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            self._show_render_error(str(error))
            return
        self._show_prepared_image(prepared)

    def _publish_running_frame(self, jpeg_bytes: bytes) -> None:
        if self._refresh_state is not GuiRefreshState.RUNNING:
            return
        if self._frame_buffer is None:
            raise RuntimeError("Laufende LCD-Session besitzt keinen Framepuffer")
        self._frame_buffer.publish(jpeg_bytes)

    def _show_render_error(self, reason: str) -> None:
        self.status_label.setText(
            f"Status: Frame-Aktualisierung fehlgeschlagen – letzter gültiger Frame bleibt aktiv: {reason}"
        )

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
        self._apply_refresh_state()

    def _apply_refresh_state(self) -> None:
        editable = self._refresh_state in {
            GuiRefreshState.IDLE,
            GuiRefreshState.RUNNING,
        }
        self.select_button.setEnabled(editable)
        self.scale_mode.setEnabled(editable)
        self.overlay_checkbox.setEnabled(editable)
        self.overlay_color_button.setEnabled(editable)
        self.refresh_button.setEnabled(editable)
        self.hardware_live_checkbox.setEnabled(
            self._refresh_state is GuiRefreshState.IDLE
        )
        self.send_button.setEnabled(
            self._refresh_state is GuiRefreshState.IDLE
            and self._prepared is not None
            and self._device_ready
            and self.hardware_live_checkbox.isChecked()
        )
        self.start_lcd_button.setEnabled(
            self._refresh_state is GuiRefreshState.IDLE
            and self._prepared is not None
            and self._device_ready
            and self._controller_factory is not None
            and self.hardware_live_checkbox.isChecked()
        )
        self.stop_lcd_button.setEnabled(
            self._refresh_state is GuiRefreshState.RUNNING
        )
        self.acknowledge_error_button.setVisible(
            self._refresh_state is GuiRefreshState.ERROR
        )
        self.acknowledge_error_button.setEnabled(
            self._refresh_state is GuiRefreshState.ERROR
        )
        if self._controller_factory is None:
            self.start_lcd_button.setToolTip(
                "Noch keine Produktions-Hardwareverdrahtung konfiguriert"
            )
        else:
            self.start_lcd_button.setToolTip("")

    def _set_refresh_state(self, state: GuiRefreshState) -> None:
        self._refresh_state = state
        self._apply_refresh_state()

    def start_lcd(self) -> None:
        """Start exactly one explicitly injected refresh session."""
        if self._refresh_state is not GuiRefreshState.IDLE:
            return
        if self._prepared is None:
            self.status_label.setText("Status: LCD-Start benötigt einen gültigen Frame")
            self._apply_refresh_state()
            return
        if not self.hardware_live_checkbox.isChecked():
            self.status_label.setText(
                "Status: Hardware-Livebetrieb muss ausdrücklich freigegeben werden"
            )
            self._apply_refresh_state()
            return
        if self._controller_factory is None:
            self.status_label.setText(
                "Status: LCD-Livebetrieb ist noch nicht mit Hardware verdrahtet"
            )
            self._apply_refresh_state()
            return

        self._set_refresh_state(GuiRefreshState.STARTING)
        self.status_label.setText("Status: LCD-Session wird gestartet …")
        controller: RefreshControllerLike | None = None
        try:
            frame_buffer = lcd_refresh.LatestFrameBuffer(self._prepared.jpeg_bytes)
            controller = self._controller_factory(frame_buffer)
            self._frame_buffer = frame_buffer
            self._refresh_controller = controller
            controller.start()
        except Exception as error:
            if controller is not None:
                controller.request_stop()
            self._enter_refresh_error(f"LCD-Start fehlgeschlagen: {error}")
            return

        self._set_refresh_state(GuiRefreshState.RUNNING)
        self.status_label.setText("Status: LCD-Session läuft · Framegeneration 1")

    def stop_lcd(self) -> None:
        """Request stop without blocking the Qt event loop."""
        if self._refresh_state is not GuiRefreshState.RUNNING:
            return
        controller = self._refresh_controller
        if controller is None:
            self._enter_refresh_error("Laufende LCD-Session besitzt keinen Controller")
            return
        try:
            controller.request_stop()
        except Exception as error:
            self.status_label.setText(f"Status: Stopanforderung fehlgeschlagen: {error}")
            return
        self._set_refresh_state(GuiRefreshState.STOPPING)
        self.status_label.setText("Status: LCD-Session wird sauber beendet …")

    def _poll_refresh_controller(self) -> None:
        if self._refresh_state not in {
            GuiRefreshState.RUNNING,
            GuiRefreshState.STOPPING,
        }:
            return
        controller = self._refresh_controller
        if controller is None:
            self._enter_refresh_error("LCD-Session endete ohne Controller")
            return
        if controller.is_running:
            return

        result = controller.result
        self._last_refresh_result = result
        self._refresh_controller = None
        if result is None:
            self._enter_refresh_error("LCD-Refreshworker endete ohne Ergebnis")
        elif result.stop_reason in {
            lcd_refresh.RefreshStopReason.SEND_ERROR,
            lcd_refresh.RefreshStopReason.INTERNAL_ERROR,
        }:
            detail = f": {result.error}" if result.error is not None else ""
            self._enter_refresh_error(
                f"LCD-Session wegen {result.stop_reason.value} beendet{detail}"
            )
        else:
            self._frame_buffer = None
            self._set_refresh_state(GuiRefreshState.IDLE)
            self.status_label.setText(
                f"Status: LCD-Session beendet ({result.stop_reason.value}, "
                f"{result.frames_sent} Frames)"
            )
        if self._close_when_stopped:
            self._close_when_stopped = False
            QTimer.singleShot(0, self.close)

    def _enter_refresh_error(self, message: str) -> None:
        self._refresh_controller = None
        self._set_refresh_state(GuiRefreshState.ERROR)
        self.status_label.setText(f"Status: Fehler – {message} · kein Retry")

    def acknowledge_refresh_error(self) -> None:
        """Require one explicit user action before another session may start."""
        if self._refresh_state is not GuiRefreshState.ERROR:
            return
        self._frame_buffer = None
        self._set_refresh_state(GuiRefreshState.IDLE)
        self.status_label.setText("Status: Fehler bestätigt – LCD-Session ist bereit")

    def send_selected_image(self) -> None:
        """Revalidate the prepared JPEG and request exactly one existing transfer."""
        if not self.hardware_live_checkbox.isChecked():
            self._show_send_error(
                "Hardware-Livebetrieb muss ausdrücklich freigegeben werden."
            )
            return
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

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._refresh_state is GuiRefreshState.RUNNING:
            self._close_when_stopped = True
            self.stop_lcd()
            event.ignore()
            return
        if self._refresh_state is GuiRefreshState.STOPPING:
            self._close_when_stopped = True
            event.ignore()
            return
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow(
        controller_factory=gui_refresh_factory.ProductionControllerFactory()
    )
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
