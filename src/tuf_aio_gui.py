#!/usr/bin/env python3
"""PySide6 UI for one explicitly requested, prepared ASUS LCD image."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from PySide6.QtCore import QSettings, QSocketNotifier, QTimer, Qt, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QCloseEvent,
    QHideEvent,
    QPixmap,
    QResizeEvent,
    QShowEvent,
)
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
    QMenu,
    QPushButton,
    QSizePolicy,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

import image_pipeline
import gif_animation
import gui_refresh_factory
import lcd_refresh
import lcd_transport as transport
import refresh_diagnostics
import system_sensors
import telemetry

TemperatureReader = Callable[[], system_sensors.TemperatureSnapshot]
DiagnosticsFactory = Callable[[], refresh_diagnostics.RefreshDiagnostics]
AnimationClock = Callable[[], float]


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
ROTATION_SETTING = "lcd_output/rotation_degrees"
SCALE_MODE_SETTING = "lcd_output/scale_mode"
LAST_IMAGE_SETTING = "lcd_output/last_image"
LCD_AUTOSTART_SETTING = "lcd_runtime/autostart"
GIF_PLAYBACK_SPEED_SETTING = "lcd_output/gif_playback_speed"
GIF_PLAYBACK_SPEED_DEFAULT = 2.0
GIF_PLAYBACK_SPEEDS = (1.0, 1.5, 2.0, 3.0)
SLOT_SETTING_PREFIX = "lcd_data_slots"
SLOT_DEFAULTS = {
    "top_left": telemetry.MetricId.CPU_USAGE,
    "top_right": telemetry.MetricId.GPU_USAGE,
    "bottom_left": telemetry.MetricId.CPU_PACKAGE,
    "bottom_right": telemetry.MetricId.GPU_TEMPERATURE,
}
STATIC_TRANSPORT_INTERVAL_SECONDS = 1.0
GIF_NOMINAL_SENDER_INTERVAL_SECONDS = 0.012


class GuiRefreshState(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


class QtSignalShutdownBridge:
    """Route terminal signals into the Qt event loop without KeyboardInterrupt."""

    def __init__(self, request_shutdown: Callable[[], None]) -> None:
        self._request_shutdown = request_shutdown
        self._read_fd: int | None = None
        self._write_fd: int | None = None
        self._notifier: QSocketNotifier | None = None
        self._previous_wakeup_fd: int | None = None
        self._previous_handlers: dict[int, object] = {}
        self._signal_pending = False
        self._shutdown_dispatched = False

    def install(self) -> None:
        """Install only from the Python main thread after QApplication exists."""
        if self._read_fd is not None:
            raise RuntimeError("Signal-Bridge wurde bereits installiert")
        read_fd, write_fd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        previous_wakeup_fd: int | None = None
        previous_handlers: dict[int, object] = {}
        try:
            previous_wakeup_fd = signal.set_wakeup_fd(write_fd)
            previous_handlers = {
                signum: signal.getsignal(signum)
                for signum in (signal.SIGINT, signal.SIGTERM)
            }
            for signum in previous_handlers:
                signal.signal(signum, self._handle_signal)
            notifier = QSocketNotifier(read_fd, QSocketNotifier.Type.Read)
            notifier.activated.connect(self._dispatch_pending_signal)
        except BaseException:
            if previous_wakeup_fd is not None:
                signal.set_wakeup_fd(previous_wakeup_fd)
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)  # type: ignore[arg-type]
            os.close(read_fd)
            os.close(write_fd)
            raise

        self._read_fd = read_fd
        self._write_fd = write_fd
        self._previous_wakeup_fd = previous_wakeup_fd
        self._previous_handlers = previous_handlers
        self._notifier = notifier

    def close(self) -> None:
        """Restore the process signal state after the Qt event loop has ended."""
        notifier = self._notifier
        if notifier is not None:
            notifier.setEnabled(False)
            notifier.deleteLater()
            self._notifier = None
        if self._read_fd is None or self._write_fd is None:
            return
        if self._previous_wakeup_fd is not None:
            signal.set_wakeup_fd(self._previous_wakeup_fd)
        for signum, handler in self._previous_handlers.items():
            signal.signal(signum, handler)  # type: ignore[arg-type]
        os.close(self._read_fd)
        os.close(self._write_fd)
        self._read_fd = None
        self._write_fd = None
        self._previous_wakeup_fd = None
        self._previous_handlers = {}

    def _handle_signal(self, _signum: int, _frame: object) -> None:
        """Keep the Python signal handler minimal and exception-free."""
        self._signal_pending = True

    def _dispatch_pending_signal(self, *_: object) -> None:
        read_fd = self._read_fd
        if read_fd is None:
            return
        while True:
            try:
                if not os.read(read_fd, 4096):
                    break
            except BlockingIOError:
                break
        if not self._signal_pending or self._shutdown_dispatched:
            return
        self._signal_pending = False
        self._shutdown_dispatched = True
        self._request_shutdown()


class MainWindow(QMainWindow):
    """Single-image UI; conversion and transport stay in separate modules."""

    transport_frame_requested = Signal()
    refresh_worker_finished = Signal()

    def __init__(
        self,
        *,
        sensor_reader: TemperatureReader | None = None,
        settings: QSettings | None = None,
        controller_factory: ControllerFactory | None = None,
        diagnostics_factory: DiagnosticsFactory = (
            refresh_diagnostics.create_gui_session_diagnostics
        ),
        animation_clock: AnimationClock = time.monotonic,
    ) -> None:
        super().__init__()
        self._sensor_reader = sensor_reader or system_sensors.SystemTelemetryReader()
        self._controller_factory = controller_factory
        self._diagnostics_factory = diagnostics_factory
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
        self._rotation_degrees = image_pipeline.normalize_rotation(
            self._settings.value(ROTATION_SETTING, 0)
        )
        self._settings.setValue(ROTATION_SETTING, self._rotation_degrees)
        self._slot_metric_ids = self._read_slot_settings()
        self._gif_playback_speed = self._read_gif_playback_speed()
        for slot, metric_id in self._slot_metric_ids.items():
            self._settings.setValue(f"{SLOT_SETTING_PREFIX}/{slot}", metric_id.value)
        self._settings.sync()
        self._latest_temperature_snapshot = system_sensors.TemperatureSnapshot()
        self._selected_path: Path | None = None
        self._prepared: image_pipeline.PreparedImage | None = None
        self._prepared_animation: image_pipeline.PreparedAnimation | None = None
        self._animation_frame_index = 0
        self._animation_clock = animation_clock
        self._animation_scheduler = gif_animation.GifAnimationScheduler()
        self._lcd_animation_scheduler = gif_animation.GifAnimationScheduler()
        self._lcd_animation_frame_index = 0
        self._lcd_prepared: image_pipeline.PreparedImage | None = None
        self._transport_frame_request_lock = threading.Lock()
        self._transport_frame_request_pending = False
        self._device_ready = False
        self._final_pixmap: QPixmap | None = None
        self._refresh_state = GuiRefreshState.IDLE
        self._frame_buffer: lcd_refresh.LatestFrameBuffer | None = None
        self._refresh_controller: RefreshControllerLike | None = None
        self._last_refresh_result: lcd_refresh.RefreshResult | None = None
        self._refresh_diagnostics: refresh_diagnostics.RefreshDiagnostics = (
            refresh_diagnostics.NULL_DIAGNOSTICS
        )
        self._preview_jpeg: bytes | None = None
        self._preview_dirty = False
        self._quit_when_stopped = False
        self._quit_requested = False
        self._quit_finished = False
        self._worker_completion_notifier_installed = False

        self.setWindowTitle("TUF AIO Control")
        self.resize(920, 900)
        self._build_ui()
        self._build_tray()
        self._apply_style()
        self.refresh_device_status()
        self._temperature_timer = QTimer(self)
        self._temperature_timer.setInterval(1000)
        self._temperature_timer.timeout.connect(self.refresh_temperatures)
        self._refresh_state_timer = QTimer(self)
        self._refresh_state_timer.setInterval(250)
        self._refresh_state_timer.timeout.connect(self._poll_refresh_controller)
        self._animation_timer = QTimer(self)
        self._animation_timer.setSingleShot(True)
        self._animation_timer.timeout.connect(self._advance_gif_animation)
        self._transport_animation_timer = QTimer(self)
        self._transport_animation_timer.setSingleShot(True)
        self._transport_animation_timer.timeout.connect(self._produce_transport_frame)
        self.transport_frame_requested.connect(self._produce_transport_frame)
        self.refresh_worker_finished.connect(self._poll_refresh_controller)
        self._apply_refresh_state()
        self._restore_last_image()
        QTimer.singleShot(0, self._maybe_autostart_lcd)

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
        preview_grid.addWidget(self._preview_title("LCD-Ausgabe 320×320"), 0, 0)
        self.final_preview = self._preview_label("Noch keine Ausgabe erzeugt")
        preview_grid.addWidget(self.final_preview, 1, 0)
        preview_grid.setColumnStretch(0, 1)
        outer.addWidget(previews, 1)

        options = QFrame()
        options.setObjectName("card")
        options_layout = QHBoxLayout(options)
        options_layout.addWidget(QLabel("Skalierung:"))
        self.scale_mode = QComboBox()
        self.scale_mode.addItem("Zuschneiden", "crop")
        self.scale_mode.addItem("Einpassen", "fit")
        saved_scale_mode = self._settings.value(SCALE_MODE_SETTING, "crop")
        saved_scale_index = self.scale_mode.findData(saved_scale_mode)
        self.scale_mode.setCurrentIndex(max(0, saved_scale_index))
        self.scale_mode.currentIndexChanged.connect(self._scale_mode_changed)
        options_layout.addWidget(self.scale_mode)
        self.gif_speed_label = QLabel("GIF-Geschwindigkeit:")
        options_layout.addWidget(self.gif_speed_label)
        self.gif_speed_combo = QComboBox()
        for speed, label in ((1.0, "1×"), (1.5, "1.5×"), (2.0, "2×"), (3.0, "3×")):
            self.gif_speed_combo.addItem(label, speed)
        self.gif_speed_combo.setCurrentIndex(
            self.gif_speed_combo.findData(self._gif_playback_speed)
        )
        self.gif_speed_combo.currentIndexChanged.connect(
            self._gif_playback_speed_changed
        )
        options_layout.addWidget(self.gif_speed_combo)
        self.overlay_checkbox = QCheckBox("Datenoverlay auf LCD anzeigen")
        self.overlay_checkbox.setChecked(self._overlay_enabled)
        self.overlay_checkbox.toggled.connect(self._overlay_toggled)
        options_layout.addWidget(self.overlay_checkbox)
        self.overlay_color_button = QPushButton()
        self.overlay_color_button.clicked.connect(self._choose_overlay_color)
        self._update_overlay_color_button()
        options_layout.addWidget(self.overlay_color_button)
        self.rotation_button = QPushButton()
        self.rotation_button.clicked.connect(self._rotate_clockwise)
        self._update_rotation_button()
        options_layout.addWidget(self.rotation_button)
        self.lcd_autostart_checkbox = QCheckBox(
            "LCD beim Programmstart automatisch starten"
        )
        self.lcd_autostart_checkbox.setChecked(
            self._read_bool_setting(LCD_AUTOSTART_SETTING)
        )
        self.lcd_autostart_checkbox.toggled.connect(
            lambda enabled: self._store_bool_setting(
                LCD_AUTOSTART_SETTING, enabled
            )
        )
        options_layout.addWidget(self.lcd_autostart_checkbox)
        options_layout.addStretch(1)
        outer.addWidget(options)

        slots_card = QFrame()
        slots_card.setObjectName("card")
        slots_layout = QGridLayout(slots_card)
        slots_title = QLabel("LCD-Datenpositionen")
        slots_title.setObjectName("sectionTitle")
        slots_layout.addWidget(slots_title, 0, 0, 1, 3)
        self.slot_combos: dict[str, QComboBox] = {}
        slot_labels = {
            "top_left": "Oben links",
            "top_right": "Oben rechts",
            "bottom_left": "Unten links",
            "bottom_right": "Unten rechts",
        }
        for column, (slot, label) in enumerate(slot_labels.items()):
            row = 1 + (column // 2) * 2
            grid_column = column % 2
            slots_layout.addWidget(QLabel(label), row, grid_column)
            combo = QComboBox()
            for definition in telemetry.METRIC_DEFINITIONS:
                combo.addItem(definition.display_label, definition.metric_id.value)
            selected = combo.findData(self._slot_metric_ids[slot].value)
            combo.setCurrentIndex(selected)
            combo.currentIndexChanged.connect(
                lambda _index, selected_slot=slot: self._slot_selection_changed(
                    selected_slot
                )
            )
            slots_layout.addWidget(combo, row + 1, grid_column)
            slots_layout.setColumnStretch(grid_column, 1)
            self.slot_combos[slot] = combo
        outer.addWidget(slots_card)

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
        self.start_lcd_button = QPushButton("LCD starten")
        self.start_lcd_button.setObjectName("primaryButton")
        self.start_lcd_button.clicked.connect(self.start_lcd)
        self.stop_lcd_button = QPushButton("LCD stoppen")
        self.stop_lcd_button.clicked.connect(self.stop_lcd)
        self.acknowledge_error_button = QPushButton("Fehler bestätigen")
        self.acknowledge_error_button.clicked.connect(self.acknowledge_refresh_error)
        buttons.addWidget(self.select_button)
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

    def _store_bool_setting(self, key: str, enabled: bool) -> None:
        self._settings.setValue(key, enabled)
        self._settings.sync()

    def _read_gif_playback_speed(self) -> float:
        raw = self._settings.value(
            GIF_PLAYBACK_SPEED_SETTING,
            GIF_PLAYBACK_SPEED_DEFAULT,
        )
        try:
            speed = float(raw)
        except (TypeError, ValueError):
            speed = GIF_PLAYBACK_SPEED_DEFAULT
        if speed not in GIF_PLAYBACK_SPEEDS:
            speed = GIF_PLAYBACK_SPEED_DEFAULT
        self._settings.setValue(GIF_PLAYBACK_SPEED_SETTING, speed)
        return speed

    def _build_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        icon = self.windowIcon()
        if icon.isNull():
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("TUF AIO Control")
        self.tray_menu = QMenu(self)
        self.tray_open_action = QAction("Öffnen", self)
        self.tray_start_action = QAction("LCD starten", self)
        self.tray_stop_action = QAction("LCD stoppen", self)
        self.tray_quit_action = QAction("Beenden", self)
        self.tray_open_action.triggered.connect(self.open_window)
        self.tray_start_action.triggered.connect(self.start_lcd)
        self.tray_stop_action.triggered.connect(self.stop_lcd)
        self.tray_quit_action.triggered.connect(self.quit_application)
        self.tray_menu.addAction(self.tray_open_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_start_action)
        self.tray_menu.addAction(self.tray_stop_action)
        self.tray_menu.addSeparator()
        self.tray_menu.addAction(self.tray_quit_action)
        self.tray_icon.setContextMenu(self.tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        self.tray_icon.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.open_window()

    def open_window(self) -> None:
        """Show and raise this existing window without creating another instance."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._refresh_preview_if_needed()
        if self._prepared is not None:
            self._show_prepared_image(self._prepared)
        self._update_sensor_polling()

    def _restore_last_image(self) -> None:
        raw_path = self._settings.value(LAST_IMAGE_SETTING)
        if isinstance(raw_path, str) and raw_path:
            self.load_image(Path(raw_path), persist=False)

    def _maybe_autostart_lcd(self) -> None:
        if not self._read_bool_setting(LCD_AUTOSTART_SETTING):
            return
        if self._prepared is None:
            self.status_label.setText(
                "Status: LCD-Autostart benötigt ein weiterhin verfügbares Bild"
            )
            return
        self.start_lcd()

    def _read_slot_settings(self) -> dict[str, telemetry.MetricId]:
        values: dict[str, telemetry.MetricId] = {}
        for slot, default in SLOT_DEFAULTS.items():
            key = f"{SLOT_SETTING_PREFIX}/{slot}"
            if slot == "bottom_left" and not self._settings.contains(key):
                legacy_key = f"{SLOT_SETTING_PREFIX}/bottom_center"
                raw = (
                    self._settings.value(legacy_key)
                    if self._settings.contains(legacy_key)
                    else default.value
                )
            else:
                raw = self._settings.value(key, default.value)
            values[slot] = telemetry.parse_metric_id(raw, default)
        return values

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

    def _overlay_slots(
        self,
        snapshot: system_sensors.TemperatureSnapshot | None = None,
    ) -> image_pipeline.OverlaySlots:
        metrics = system_sensors.metric_values(
            snapshot or self._latest_temperature_snapshot
        )

        def selected(slot: str) -> telemetry.MetricValue | None:
            metric_id = self._slot_metric_ids[slot]
            return None if metric_id is telemetry.MetricId.OFF else metrics[metric_id]

        return image_pipeline.OverlaySlots(
            top_left=selected("top_left"),
            top_right=selected("top_right"),
            bottom_left=selected("bottom_left"),
            bottom_right=selected("bottom_right"),
        )

    def _visible_metric_signature(
        self, snapshot: system_sensors.TemperatureSnapshot
    ) -> tuple[tuple[str, str] | None, ...]:
        slots = self._overlay_slots(snapshot)
        return tuple(
            None if metric is None else (metric.metric_id.value, metric.display_value)
            for metric in (
                slots.top_left,
                slots.top_right,
                slots.bottom_left,
                slots.bottom_right,
            )
        )

    def _slot_selection_changed(self, slot: str) -> None:
        if self._refresh_state in {
            GuiRefreshState.STARTING,
            GuiRefreshState.STOPPING,
            GuiRefreshState.ERROR,
        }:
            return
        combo = self.slot_combos[slot]
        metric_id = telemetry.parse_metric_id(combo.currentData(), SLOT_DEFAULTS[slot])
        self._slot_metric_ids[slot] = metric_id
        self._settings.setValue(f"{SLOT_SETTING_PREFIX}/{slot}", metric_id.value)
        self._settings.sync()
        self._rerender_temperature_overlay()
        self._update_sensor_polling()

    def _rotate_clockwise(self) -> None:
        if self._refresh_state in {
            GuiRefreshState.STARTING,
            GuiRefreshState.STOPPING,
            GuiRefreshState.ERROR,
        }:
            return
        self._rotation_degrees = (self._rotation_degrees + 90) % 360
        self._settings.setValue(ROTATION_SETTING, self._rotation_degrees)
        self._settings.sync()
        self._update_rotation_button()
        self._rerender_temperature_overlay()

    def _update_rotation_button(self) -> None:
        self.rotation_button.setText(f"LCD drehen: {self._rotation_degrees}°")

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
        self._update_sensor_polling()

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

    def _selected_dynamic_metrics(self) -> frozenset[telemetry.MetricId]:
        if not self._overlay_enabled:
            return frozenset()
        return frozenset(
            metric_id
            for metric_id in self._slot_metric_ids.values()
            if metric_id is not telemetry.MetricId.OFF
        )

    def _sensor_polling_needed(self) -> bool:
        if self._prepared is None or not self._selected_dynamic_metrics():
            return False
        return self._refresh_state is GuiRefreshState.RUNNING or self.isVisible()

    def _update_sensor_polling(self) -> None:
        if self._sensor_polling_needed():
            if not self._temperature_timer.isActive():
                self._temperature_timer.start()
        else:
            self._temperature_timer.stop()

    def _content_transport_interval(self) -> float:
        return (
            GIF_NOMINAL_SENDER_INTERVAL_SECONDS
            if self._prepared_animation is not None
            and len(self._prepared_animation.frames) > 1
            and self._lcd_animation_scheduler.is_running
            else STATIC_TRANSPORT_INTERVAL_SECONDS
        )

    def _update_frame_buffer_cadence(self) -> None:
        if self._frame_buffer is not None:
            self._frame_buffer.set_transport_interval_seconds(
                self._content_transport_interval()
            )
            self._frame_buffer.set_transport_driven(
                self._prepared_animation is not None
                and len(self._prepared_animation.frames) > 1
                and self._lcd_animation_scheduler.is_running
            )

    def _replace_animation(
        self, prepared: image_pipeline.PreparedAnimation | None
    ) -> None:
        self._animation_timer.stop()
        self._transport_animation_timer.stop()
        self._animation_scheduler.stop()
        self._lcd_animation_scheduler.stop()
        self._prepared_animation = prepared
        self._animation_frame_index = 0
        self._lcd_animation_frame_index = 0
        self._lcd_prepared = None
        if prepared is not None and len(prepared.frames) > 1:
            durations = tuple(frame.duration_ms for frame in prepared.frames)
            now = self._animation_clock()
            self._animation_scheduler.start(
                durations,
                prepared.loop_count,
                now=now,
                playback_speed=self._gif_playback_speed,
            )
            self._lcd_animation_scheduler.start(
                durations,
                prepared.loop_count,
                now=now,
                playback_speed=self._gif_playback_speed,
            )
        self._update_frame_buffer_cadence()
        self._update_animation_scheduling()
        self._apply_refresh_state()

    def _animation_scheduling_needed(self) -> bool:
        return (
            self._prepared_animation is not None
            and self._animation_scheduler.is_running
            and self._refresh_state in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}
            and self.isVisible()
        )

    def _update_animation_scheduling(self) -> None:
        self._animation_timer.stop()
        if not self._animation_scheduling_needed():
            return
        delay_ms = self._animation_scheduler.milliseconds_until_next(
            now=self._animation_clock()
        )
        if delay_ms is not None:
            self._animation_timer.start(max(1, delay_ms))

    def _prepare_animation_frame(self, frame_index: int) -> image_pipeline.PreparedImage:
        animation = self._prepared_animation
        if animation is None:
            raise RuntimeError("Kein GIF für die Frame-Erzeugung geladen")
        return image_pipeline.render_prepared_animation_frame(
            animation,
            frame_index,
            overlay_config=self._overlay_config(),
            temperatures=self._overlay_values(self._latest_temperature_snapshot),
            overlay_slots=self._overlay_slots(),
            rotation_degrees=self._rotation_degrees,
        )

    def _render_preview_animation_frame(
        self, frame_index: int, *, update_widgets: bool
    ) -> None:
        prepared = self._prepare_animation_frame(frame_index)
        self._animation_frame_index = frame_index
        self._prepared = prepared
        self._load_final_preview(prepared.jpeg_bytes)
        if update_widgets:
            self._show_prepared_image(prepared)

    def _advance_preview_animation(self, *, update_widgets: bool) -> bool:
        state = self._animation_scheduler.advance(now=self._animation_clock())
        rendered = False
        if state is not None and state.frame_index != self._animation_frame_index:
            self._render_preview_animation_frame(
                state.frame_index,
                update_widgets=update_widgets,
            )
            rendered = True
        return rendered

    def _advance_gif_animation(self) -> None:
        if not self._animation_scheduling_needed():
            self._animation_timer.stop()
            return
        try:
            self._advance_preview_animation(update_widgets=True)
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            self._show_render_error(error)
        self._update_animation_scheduling()

    def _request_transport_frame(self) -> None:
        """Coalesce sender completion notices into one GUI-producer request."""
        if (
            self._refresh_state
            not in {GuiRefreshState.STARTING, GuiRefreshState.RUNNING}
            or self._prepared_animation is None
            or not self._lcd_animation_scheduler.is_running
        ):
            return
        with self._transport_frame_request_lock:
            if self._transport_frame_request_pending:
                return
            self._transport_frame_request_pending = True
        self.transport_frame_requested.emit()

    def _produce_transport_frame(self) -> None:
        """Publish exactly the next sequential frame after transport completion."""
        keep_pending = False
        try:
            if (
                self._refresh_state is GuiRefreshState.RUNNING
                and self._prepared_animation is not None
                and self._lcd_animation_scheduler.is_running
            ):
                delay_ms = self._lcd_animation_scheduler.milliseconds_until_next(
                    now=self._animation_clock()
                )
                if delay_ms is not None and delay_ms > 0:
                    self._transport_animation_timer.start(max(1, delay_ms))
                    keep_pending = True
                    return
                state = self._lcd_animation_scheduler.advance(
                    now=self._animation_clock()
                )
                if state is not None and state.frame_index != self._lcd_animation_frame_index:
                    prepared = self._prepare_animation_frame(state.frame_index)
                    self._lcd_animation_frame_index = state.frame_index
                    self._lcd_prepared = prepared
                    self._publish_running_frame(prepared.jpeg_bytes)
                elif self._frame_buffer is not None and self._lcd_prepared is not None:
                    # The finite final frame is held while the sender returns to
                    # static cadence; publishing also releases its generation wait.
                    self._frame_buffer.publish(self._lcd_prepared.jpeg_bytes)
                if state is not None and state.finished:
                    self._update_frame_buffer_cadence()
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            self._show_render_error(error)
        finally:
            if not keep_pending:
                with self._transport_frame_request_lock:
                    self._transport_frame_request_pending = False
        self._update_animation_scheduling()

    def refresh_temperatures(self) -> system_sensors.TemperatureSnapshot:
        """Sample local telemetry once without involving any HID path."""
        if not self._sensor_polling_needed():
            return self._latest_temperature_snapshot
        previous_values = self._visible_metric_signature(
            self._latest_temperature_snapshot
        )
        try:
            selected_metrics = self._selected_dynamic_metrics()
            selective_reader = getattr(type(self._sensor_reader), "sample", None)
            snapshot = (
                selective_reader(self._sensor_reader, selected_metrics)
                if callable(selective_reader)
                else self._sensor_reader()
            )
        except (OSError, RuntimeError, ValueError):
            snapshot = system_sensors.TemperatureSnapshot()
        self._latest_temperature_snapshot = snapshot
        if (
            self._overlay_enabled
            and self._prepared is not None
            and self._refresh_state in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}
            and self._visible_metric_signature(snapshot) != previous_values
        ):
            self._rerender_temperature_overlay(update_widgets=self.isVisible())
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
        self._settings.setValue(SCALE_MODE_SETTING, self.scale_mode.currentData())
        self._settings.sync()
        if (
            self._selected_path is not None
            and self._refresh_state in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}
        ):
            self.load_image(self._selected_path)

    def _gif_playback_speed_changed(self) -> None:
        speed = float(self.gif_speed_combo.currentData())
        if speed == self._gif_playback_speed:
            return
        self._gif_playback_speed = speed
        self._settings.setValue(GIF_PLAYBACK_SPEED_SETTING, speed)
        self._settings.sync()
        now = self._animation_clock()
        self._animation_scheduler.set_playback_speed(speed, now=now)
        self._lcd_animation_scheduler.set_playback_speed(speed, now=now)
        self._update_animation_scheduling()
        if self._transport_frame_request_pending:
            self._transport_animation_timer.stop()
            self._produce_transport_frame()

    def load_image(self, path: Path, *, persist: bool = True) -> bool:
        """Prepare one static source or one cached GIF animation."""
        if self._refresh_state not in {GuiRefreshState.IDLE, GuiRefreshState.RUNNING}:
            return False
        resolved = path.expanduser().resolve()
        self.path_value.setText(str(resolved))
        self.original_size_value.setText("wird ermittelt …")
        previous_prepared = self._prepared
        previous_animation = self._prepared_animation
        if self._refresh_state is GuiRefreshState.IDLE:
            self._prepared = None
            self._final_pixmap = None
            self.final_preview.setPixmap(QPixmap())
            self.final_preview.setText("Ausgabe wird vorbereitet …")
            self._update_send_enabled()

        mode = self.scale_mode.currentData()
        try:
            animation: image_pipeline.PreparedAnimation | None = None
            if resolved.suffix.casefold() == ".gif":
                animation = image_pipeline.prepare_gif(
                    resolved,
                    mode=mode,
                    overlay_config=self._overlay_config(),
                    temperatures=self._overlay_values(
                        self._latest_temperature_snapshot
                    ),
                    overlay_slots=self._overlay_slots(),
                    rotation_degrees=self._rotation_degrees,
                )
                prepared = image_pipeline.render_prepared_animation_frame(
                    animation,
                    0,
                    overlay_config=self._overlay_config(),
                    temperatures=self._overlay_values(
                        self._latest_temperature_snapshot
                    ),
                    overlay_slots=self._overlay_slots(),
                    rotation_degrees=self._rotation_degrees,
                )
            else:
                prepared = image_pipeline.prepare_image(
                    resolved,
                    mode=mode,
                    overlay_config=self._overlay_config(),
                    temperatures=self._overlay_values(
                        self._latest_temperature_snapshot
                    ),
                    overlay_slots=self._overlay_slots(),
                    rotation_degrees=self._rotation_degrees,
                )
            self._replace_animation(animation)
            self._lcd_prepared = prepared
            self._load_final_preview(prepared.jpeg_bytes)
            self._publish_running_frame(prepared.jpeg_bytes)
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            if self._refresh_state is GuiRefreshState.RUNNING:
                self._prepared = previous_prepared
                self._prepared_animation = previous_animation
                self._show_render_error(error)
            else:
                self._prepared = None
                self._replace_animation(None)
                self._final_pixmap = None
                self.final_preview.setPixmap(QPixmap())
                self.final_preview.setText("Keine kompatible LCD-Ausgabe")
                self._set_invalid_image(str(error))
            return False

        self._selected_path = resolved
        if persist:
            self._settings.setValue(LAST_IMAGE_SETTING, str(resolved))
            self._settings.sync()
        self._show_prepared_image(prepared)
        self._update_sensor_polling()
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
        if self._prepared_animation is not None:
            input_text = f"GIF · Animation · {len(self._prepared_animation.frames)} Frames"
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
            self.status_label.setText("Status: Bild vorbereitet – LCD-Start bereit")
        self._update_send_enabled()

    def _rerender_temperature_overlay(self, *, update_widgets: bool = True) -> None:
        if self._prepared is None:
            return
        try:
            if self._prepared_animation is not None:
                prepared = self._prepare_animation_frame(self._animation_frame_index)
                if (
                    self._refresh_state is GuiRefreshState.RUNNING
                    and not self._lcd_animation_scheduler.is_running
                ):
                    lcd_prepared = self._prepare_animation_frame(
                        self._lcd_animation_frame_index
                    )
                    self._lcd_prepared = lcd_prepared
                    self._publish_running_frame(lcd_prepared.jpeg_bytes)
            else:
                prepared = image_pipeline.rerender_prepared_image(
                    self._prepared,
                    overlay_config=self._overlay_config(),
                    temperatures=self._overlay_values(
                        self._latest_temperature_snapshot
                    ),
                    overlay_slots=self._overlay_slots(),
                    rotation_degrees=self._rotation_degrees,
                )
            self._load_final_preview(prepared.jpeg_bytes)
            if self._prepared_animation is None:
                self._publish_running_frame(prepared.jpeg_bytes)
        except (image_pipeline.ImagePipelineError, OSError, RuntimeError, ValueError) as error:
            self._show_render_error(error)
            return
        if update_widgets:
            self._show_prepared_image(prepared)
        else:
            self._prepared = prepared

    def _publish_running_frame(self, jpeg_bytes: bytes) -> None:
        if self._refresh_state is not GuiRefreshState.RUNNING:
            return
        if self._frame_buffer is None:
            raise RuntimeError("Laufende LCD-Session besitzt keinen Framepuffer")
        self._frame_buffer.publish(jpeg_bytes)

    def _show_render_error(self, error: BaseException) -> None:
        self._refresh_diagnostics.record("render_error", stop_reason="render error")
        self._refresh_diagnostics.record_exception("frame_render", error)
        self.status_label.setText(
            "Status: Frame-Aktualisierung fehlgeschlagen – letzter gültiger "
            f"Frame bleibt aktiv: {error}"
        )

    def _load_final_preview(self, jpeg: bytes) -> None:
        self._preview_jpeg = jpeg
        self._preview_dirty = True
        if not self.isVisible():
            return
        self._refresh_preview_if_needed()

    def _refresh_preview_if_needed(self) -> None:
        if not self._preview_dirty or self._preview_jpeg is None:
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(self._preview_jpeg, "JPEG"):
            raise image_pipeline.ImagePipelineError(
                "Das validierte JPEG konnte nicht als Vorschau geladen werden"
            )
        self._final_pixmap = pixmap
        self._preview_dirty = False
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
        gif_controls_enabled = editable and self._prepared_animation is not None
        self.gif_speed_label.setEnabled(gif_controls_enabled)
        self.gif_speed_combo.setEnabled(gif_controls_enabled)
        self.overlay_checkbox.setEnabled(editable)
        self.overlay_color_button.setEnabled(editable)
        self.rotation_button.setEnabled(editable)
        for combo in self.slot_combos.values():
            combo.setEnabled(editable)
        self.refresh_button.setEnabled(editable)
        start_enabled = (
            self._refresh_state is GuiRefreshState.IDLE
            and self._prepared is not None
            and self._device_ready
            and self._controller_factory is not None
        )
        self.start_lcd_button.setEnabled(start_enabled)
        self.stop_lcd_button.setEnabled(
            self._refresh_state is GuiRefreshState.RUNNING
        )
        self.acknowledge_error_button.setVisible(
            self._refresh_state is GuiRefreshState.ERROR
        )
        self.acknowledge_error_button.setEnabled(
            self._refresh_state is GuiRefreshState.ERROR
        )
        self.tray_start_action.setEnabled(start_enabled)
        self.tray_stop_action.setEnabled(
            self._refresh_state is GuiRefreshState.RUNNING
        )
        if self._controller_factory is None:
            self.start_lcd_button.setToolTip(
                "Noch keine Produktions-Hardwareverdrahtung konfiguriert"
            )
        else:
            self.start_lcd_button.setToolTip("")

    def _set_refresh_state(self, state: GuiRefreshState) -> None:
        self._refresh_state = state
        if state in {GuiRefreshState.RUNNING, GuiRefreshState.STOPPING}:
            self._refresh_state_timer.start()
        else:
            self._refresh_state_timer.stop()
        self._apply_refresh_state()
        self._update_sensor_polling()
        self._update_animation_scheduling()

    def start_lcd(self) -> None:
        """Start exactly one explicitly injected refresh session."""
        if self._refresh_state is not GuiRefreshState.IDLE:
            return
        if self._prepared is None:
            self.status_label.setText("Status: LCD-Start benötigt einen gültigen Frame")
            self._apply_refresh_state()
            return
        if self._controller_factory is None:
            self.status_label.setText(
                "Status: LCD-Livebetrieb ist noch nicht mit Hardware verdrahtet"
            )
            self._apply_refresh_state()
            return

        initial_prepared = self._prepared
        if self._prepared_animation is not None and len(self._prepared_animation.frames) > 1:
            self._lcd_animation_scheduler.stop()
            self._lcd_animation_scheduler.start(
                tuple(frame.duration_ms for frame in self._prepared_animation.frames),
                self._prepared_animation.loop_count,
                now=self._animation_clock(),
                playback_speed=self._gif_playback_speed,
            )
            self._lcd_animation_frame_index = 0
            initial_prepared = self._prepare_animation_frame(0)
            self._lcd_prepared = initial_prepared

        self._set_refresh_state(GuiRefreshState.STARTING)
        self.status_label.setText("Status: LCD-Session wird gestartet …")
        controller: RefreshControllerLike | None = None
        self._worker_completion_notifier_installed = False
        try:
            diagnostics = self._diagnostics_factory()
            self._refresh_diagnostics = diagnostics
            diagnostics.record("start_requested")
            frame_buffer = lcd_refresh.LatestFrameBuffer(
                initial_prepared.jpeg_bytes,
                diagnostics=diagnostics,
                transport_interval_seconds=self._content_transport_interval(),
                next_frame_callback=self._request_transport_frame,
                transport_driven=(
                    self._prepared_animation is not None
                    and len(self._prepared_animation.frames) > 1
                    and self._lcd_animation_scheduler.is_running
                ),
            )
            diagnostics.record(
                "initial_frame_snapshot",
                generation=frame_buffer.snapshot().generation,
            )
            controller = self._controller_factory(frame_buffer)
            self._frame_buffer = frame_buffer
            self._refresh_controller = controller
            set_completion_callback = getattr(controller, "set_completion_callback", None)
            if callable(set_completion_callback):
                set_completion_callback(self.refresh_worker_finished.emit)
                self._worker_completion_notifier_installed = True
            controller.start()
        except Exception as error:
            self._refresh_diagnostics.record_exception("gui_session_start", error)
            if controller is not None:
                controller.request_stop()
            self._enter_refresh_error(f"LCD-Start fehlgeschlagen: {error}")
            return

        self._set_refresh_state(GuiRefreshState.RUNNING)
        self.status_label.setText("Status: LCD-Session läuft · Framegeneration 1")

    def stop_lcd(self) -> None:
        """Request stop without blocking the Qt event loop."""
        if self._refresh_state not in {
            GuiRefreshState.STARTING,
            GuiRefreshState.RUNNING,
        }:
            return
        controller = self._refresh_controller
        if controller is None:
            self._enter_refresh_error("Laufende LCD-Session besitzt keinen Controller")
            return
        try:
            controller.request_stop()
        except Exception as error:
            self._refresh_diagnostics.record_exception("gui_stop_request", error)
            self.status_label.setText(f"Status: Stopanforderung fehlgeschlagen: {error}")
            return
        self._transport_animation_timer.stop()
        self._lcd_animation_scheduler.stop()
        with self._transport_frame_request_lock:
            self._transport_frame_request_pending = False
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
        self._worker_completion_notifier_installed = False
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
        if self._quit_when_stopped:
            self._quit_when_stopped = False
            QTimer.singleShot(0, self._finish_quit)

    def _enter_refresh_error(self, message: str) -> None:
        self._refresh_diagnostics.record(
            "gui_error_state",
            message=message[:500],
        )
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

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        if self.isVisible():
            self._update_scaled_preview(self.final_preview, self._final_pixmap)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 - Qt API
        super().showEvent(event)
        self._refresh_preview_if_needed()
        self._update_sensor_polling()
        self._update_animation_scheduling()

    def hideEvent(self, event: QHideEvent) -> None:  # noqa: N802 - Qt API
        super().hideEvent(event)
        self._update_sensor_polling()
        self._update_animation_scheduling()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self._quit_requested:
            event.accept()
            return
        event.ignore()
        self.hide()

    def quit_application(self) -> None:
        """Use one idempotent lifecycle for tray and terminal shutdown."""
        if self._quit_requested:
            return
        self._quit_requested = True
        self.hide()
        self._stop_application_timers()
        if self._refresh_state in {
            GuiRefreshState.STARTING,
            GuiRefreshState.RUNNING,
        }:
            self._quit_when_stopped = True
            self.stop_lcd()
            if self._worker_completion_notifier_installed:
                self._refresh_state_timer.stop()
            return
        if self._refresh_state is GuiRefreshState.STOPPING:
            self._quit_when_stopped = True
            if not self._worker_completion_notifier_installed:
                # Compatibility for a non-production injected controller that
                # has no completion callback to wake the Qt event loop.
                self._refresh_state_timer.start()
            return
        self._finish_quit()

    def _stop_application_timers(self) -> None:
        """Stop all GUI-owned timers before waiting for the worker to exit."""
        self._temperature_timer.stop()
        self._refresh_state_timer.stop()
        self._animation_timer.stop()
        self._transport_animation_timer.stop()
        self._animation_scheduler.stop()
        self._lcd_animation_scheduler.stop()
        with self._transport_frame_request_lock:
            self._transport_frame_request_pending = False

    def _finish_quit(self) -> None:
        if self._quit_finished:
            return
        self._quit_finished = True
        self._stop_application_timers()
        self.tray_icon.hide()
        application = QApplication.instance()
        if application is not None:
            application.quit()


def main() -> int:
    background = "--background" in sys.argv[1:]
    qt_arguments = [argument for argument in sys.argv if argument != "--background"]
    app = QApplication(qt_arguments)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(
        controller_factory=gui_refresh_factory.ProductionControllerFactory()
    )
    signal_bridge = QtSignalShutdownBridge(window.quit_application)
    signal_bridge.install()
    if not background:
        window.show()
    try:
        return app.exec()
    finally:
        signal_bridge.close()


if __name__ == "__main__":
    raise SystemExit(main())
