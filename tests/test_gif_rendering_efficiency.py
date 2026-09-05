"""Structural performance contracts; no timing thresholds or live I/O."""

from __future__ import annotations

from contextlib import ExitStack
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageChops, ImageDraw
from PySide6.QtGui import QImage
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = ROOT / "tests/fixtures/lcd-0x08-reference.jpg"
sys.path.append(str(ROOT / "src"))

import image_pipeline as pipeline
import lcd_refresh
import lcd_transport
import system_sensors
import telemetry
import tuf_aio_gui as gui


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class MemoryController:
    result = None
    is_running = False

    def __init__(self, source):
        self.source = source

    def start(self):
        self.is_running = True

    def request_stop(self):
        self.is_running = False
        self.result = lcd_refresh.RefreshResult(
            lcd_refresh.RefreshStopReason.EXPLICIT_STOP, 0, 0.0, (), ())


def direct_overlay(base, slots, config):
    """Pre-optimization drawing oracle, including independent stroke/fill."""
    rendered = base.copy()
    draw = ImageDraw.Draw(rendered)
    for placement in pipeline.layout_data_overlay.__wrapped__(slots, config):
        for text, center, preferred, minimum, maximum, role in (
            (placement.label, placement.label_center, 25, 8, 110, "label"),
            (placement.value_text, placement.center, 33, 22, 85, "value"),
        ):
            font = pipeline._fit_font(draw, text, preferred_size=preferred,
                minimum_size=minimum, maximum_width=maximum, role=role)
            draw.text(center, text, fill=placement.color, font=font, anchor="mm",
                      stroke_width=1, stroke_fill="#000000")
    return rendered


class GifRenderingEfficiencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self._settings_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._settings_directory.cleanup)

    @staticmethod
    def _settings(path):
        return QSettings(str(path), QSettings.Format.IniFormat)

    @staticmethod
    def _write_gif(path, *, durations):
        frames = [Image.new("RGB", (320, 320), color) for color in ("red", "green", "blue")]
        frames[0].save(path, save_all=True, append_images=frames[1:],
                       duration=list(durations), loop=0)

    @staticmethod
    def _window(**kwargs):
        with mock.patch.object(gui.transport, "discover_lcd_interface", return_value=(None, "offline")):
            return gui.MainWindow(**kwargs, diagnostics_factory=lambda: lcd_refresh.refresh_diagnostics.NULL_DIAGNOSTICS)

    def window_and_gif(self, *, overlay=True):
        directory = Path(self._settings_directory.name)
        path = directory / "animation.gif"
        self._write_gif(path, durations=(60, 60, 60))
        clock = Clock()
        settings = self._settings(directory / "efficiency.ini")
        settings.setValue(gui.OVERLAY_ENABLED_SETTING, overlay)
        reader = mock.Mock(return_value=system_sensors.TemperatureSnapshot(
            cpu_usage=system_sensors.PercentageValue(43, "fixture")))
        window = self._window(settings=settings, animation_clock=clock,
                              sensor_reader=reader, controller_factory=MemoryController)
        self.addCleanup(window.tray_icon.hide)
        self.addCleanup(window.hide)
        self.addCleanup(window._stop_application_timers)
        return window, path, clock, reader

    def test_preview_load_animation_settings_static_switches_never_encode_or_publish(self):
        window, path, clock, reader = self.window_and_gif()
        window.show()
        with (
            mock.patch.object(pipeline, "_encode_jpeg", side_effect=AssertionError("preview encoded")),
            mock.patch.object(lcd_refresh.LatestFrameBuffer, "publish", side_effect=AssertionError("preview published")),
            mock.patch.object(gui.QPixmap, "loadFromData", side_effect=AssertionError("JPEG decoded")),
        ):
            self.assertTrue(window.load_image(path))
            for index in range(300):
                clock.now += 0.031
                window._advance_gif_animation()
                self.assertEqual(window._animation_frame_index, (index + 1) % 3)
            reader.assert_not_called()
            window.refresh_temperatures()
            reader.assert_called_once()
            window._rotate_clockwise()
            window._set_overlay_color("#12ABCD")
            window._overlay_toggled(False)
            self.assertTrue(window.load_image(REFERENCE_PATH))
            self.assertIsNone(window._prepared_animation)
            self.assertTrue(window.load_image(path))
            self.assertIsNotNone(window._final_pixmap)
            self.assertFalse(window._prepared.jpeg_is_prepared)

    def test_lcd_hidden_encodes_once_per_frame_and_does_no_preview_work(self):
        window, path, clock, reader = self.window_and_gif()
        self.assertTrue(window.load_image(path))
        with mock.patch.object(pipeline, "_encode_jpeg", wraps=pipeline._encode_jpeg) as encode:
            window.start_lcd()
            self.assertEqual(encode.call_count, 1)
            source = window._frame_buffer
            first = source.snapshot()
            with ExitStack() as patches:
                for owner, name in ((window, "_load_final_preview"),
                                    (window, "_refresh_preview_if_needed"),
                                    (window, "_show_prepared_image"),
                                    (gui.QPixmap, "fromImage")):
                    patches.enter_context(mock.patch.object(owner, name,
                        side_effect=AssertionError(f"hidden preview: {name}")))
                for index in range(300):
                    clock.now += 0.031
                    source.request_next_frame()
                    self.assertEqual(window._lcd_animation_frame_index, (index + 1) % 3)
                    self.assertEqual(source.snapshot().generation, index + 2)
                    # Accessing validation metadata or the same frame twice cannot encode again.
                    self.assertEqual(window._lcd_prepared.jpeg_info, source.snapshot().jpeg_info)
                    self.assertIs(window._lcd_prepared.jpeg_bytes, source.snapshot().jpeg_bytes)
                    self.assertEqual(encode.call_count, index + 2)
                    self.assertLessEqual(len(window._animation_render_cache), 2)
                before = encode.call_count
                window.refresh_temperatures()
                self.assertEqual(encode.call_count, before)
                reader.assert_called_once()
            self.assertEqual(first.generation, 1)
            self.assertIsInstance(first.jpeg_bytes, bytes)
            self.assertNotEqual(first.generation, source.snapshot().generation)
        window.stop_lcd()
        window._poll_refresh_controller()
        self.assertIs(window._refresh_state, gui.GuiRefreshState.IDLE)

    def test_hidden_stopped_has_no_animation_sensor_encode_or_publish_work(self):
        window, path, clock, reader = self.window_and_gif()
        window.show()
        self.assertTrue(window.load_image(path))
        window.close()  # Tray hide, not application shutdown.
        with (
            mock.patch.object(pipeline, "compose_lcd_frame", side_effect=AssertionError("hidden composition")),
            mock.patch.object(pipeline, "_encode_jpeg", side_effect=AssertionError("hidden JPEG")),
            mock.patch.object(lcd_refresh.LatestFrameBuffer, "publish", side_effect=AssertionError("hidden publish")),
        ):
            for index in range(300):
                clock.now += 0.031
                window._advance_gif_animation()
                window._produce_transport_frame()
                window.refresh_temperatures()
                self.app.processEvents()
            reader.assert_not_called()
            for timer in (window._animation_timer, window._transport_animation_timer,
                          window._temperature_timer, window._refresh_state_timer):
                self.assertFalse(timer.isActive())
        window.tray_open_action.trigger()
        self.assertTrue(window._animation_timer.isActive())

    def test_shared_frame_is_composed_once_and_qt_and_jpeg_use_same_pixels(self):
        window, path, clock, _ = self.window_and_gif()
        window.show()
        self.assertTrue(window.load_image(path))
        window.start_lcd()
        source = window._frame_buffer
        for rotation in (0, 90, 180, 270):
            window._rotation_degrees = rotation
            with (
                mock.patch.object(pipeline, "compose_lcd_frame", wraps=pipeline.compose_lcd_frame) as compose,
                mock.patch.object(pipeline, "_encode_jpeg", wraps=pipeline._encode_jpeg) as encode,
            ):
                clock.now += 0.031
                window._advance_gif_animation()
                rgb = window._prepared.rgb_bytes
                self.assertEqual(encode.call_count, 0)
                source.request_next_frame()
                self.assertIs(window._prepared, window._lcd_prepared)
                self.assertEqual(compose.call_count, 1)
                self.assertEqual(encode.call_count, 1)
                self.assertEqual(encode.call_args.args[0].tobytes(), rgb)
                actual = window._final_pixmap.toImage().convertToFormat(QImage.Format.Format_RGB888)
                self.assertEqual(bytes(actual.constBits()), rgb)
                self.assertEqual(lcd_transport.validate_jpeg(source.snapshot().jpeg_bytes),
                                 window._lcd_prepared.jpeg_info)
        window.stop_lcd()
        window._poll_refresh_controller()

    def test_no_source_decode_resize_font_load_or_layout_during_warmed_cycles(self):
        window, path, clock, _ = self.window_and_gif()
        window.show()
        self.assertTrue(window.load_image(path))
        # Populate glyph/font/layout caches for the unchanged visible snapshot.
        for _ in range(3):
            clock.now += 0.031
            window._advance_gif_animation()
        misses = pipeline.layout_data_overlay.cache_info().misses
        with ExitStack() as patches:
            for owner, name in ((Image, "open"), (pipeline, "prepare_gif"),
                                (pipeline, "_prepare_base"), (Image.Image, "resize"),
                                (pipeline.ImageFont, "truetype"), (ImageDraw.ImageDraw, "text")):
                patches.enter_context(mock.patch.object(owner, name,
                    side_effect=AssertionError(f"uncached work: {name}")))
            for _ in range(300):
                clock.now += 0.031
                window._advance_gif_animation()
        self.assertEqual(pipeline.layout_data_overlay.cache_info().misses, misses)

    def test_hidden_telemetry_change_is_visible_immediately_on_tray_show(self):
        window, path, clock, reader = self.window_and_gif()
        window.show()
        self.assertTrue(window.load_image(path))
        window.start_lcd()
        window.hide()
        window.refresh_temperatures()
        reader.assert_called_once()
        with mock.patch.object(window, "_update_scaled_preview", wraps=window._update_scaled_preview) as update:
            window.tray_open_action.trigger()
            self.assertEqual(update.call_count, 1)
        expected = window._prepare_animation_frame(window._animation_frame_index)
        self.assertIs(window._preview_prepared, expected)
        self.assertIn("43 %", [p.value_text for p in pipeline.layout_data_overlay(
            window._overlay_slots(), window._overlay_config())])
        window.stop_lcd()
        window._poll_refresh_controller()

    def test_cached_masks_match_preoptimization_pixels_and_jpeg_for_all_rotations(self):
        with Image.open(REFERENCE_PATH) as source:
            base = source.convert("RGB")
        metrics = (telemetry.MetricId.CPU_USAGE, telemetry.MetricId.GPU_USAGE,
                   telemetry.MetricId.CPU_PACKAGE, telemetry.MetricId.GPU_TEMPERATURE)
        for value in (None, 73.0, -9.0, 100.0):
            slots = pipeline.OverlaySlots(*(telemetry.MetricValue(
                metric, metric.value, value, telemetry.METRIC_BY_ID[metric].unit)
                for metric in metrics))
            for color in ("#FFFFFF", "#12ABCD", "#000000"):
                config = pipeline.TemperatureOverlayConfig(True,
                    pipeline.TemperatureOverlayColors.uniform(color))
                expected = direct_overlay(base, slots, config)
                for rotation in (0, 90, 180, 270):
                    with self.subTest(value=value, color=color, rotation=rotation):
                        rotated = pipeline.rotate_composition(expected, rotation)
                        actual = pipeline.compose_lcd_frame(base.tobytes(), config,
                            pipeline.TemperatureOverlayValues(), overlay_slots=slots,
                            rotation_degrees=rotation)
                        self.assertIsNone(ImageChops.difference(actual, rotated).getbbox())
                        self.assertEqual(pipeline._encode_jpeg(actual), pipeline._encode_jpeg(rotated))

    def test_gif_disposal_transparency_and_prepared_cache_match_pillow(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "disposal.gif"
            frames = []
            for x, color in ((0, "red"), (40, "blue"), (80, "green")):
                frame = Image.new("RGBA", (160, 100))
                ImageDraw.Draw(frame).rectangle((x, 10, x + 35, 70), fill=color)
                frames.append(frame)
            frames[0].save(path, save_all=True, append_images=frames[1:],
                duration=[40, 80, 120], loop=0, disposal=[1, 2, 3], transparency=0)
            animation = pipeline.prepare_gif(path, mode="fit", encode=False)
            with Image.open(path) as source:
                for index, prepared in enumerate(animation.frames):
                    source.seek(index)
                    rgba = source.convert("RGBA")
                    expected = pipeline._scale_image(pipeline._rgb_on_black(rgba), "fit")
                    self.assertEqual(prepared.base_rgb_bytes, expected.tobytes())
                    self.assertIsNone(prepared.jpeg_bytes)
                    self.assertIsNone(prepared.jpeg_info)
            self.assertEqual(tuple(f.duration_ms for f in animation.frames), (40, 80, 120))

    def test_caches_are_bounded_and_no_caller_image_is_mutated(self):
        base = Image.new("RGB", (320, 320), "#203040")
        original = base.tobytes()
        config = pipeline.TemperatureOverlayConfig(enabled=True)
        for value in range(140):
            slots = pipeline.OverlaySlots(top_left=telemetry.MetricValue(
                telemetry.MetricId.CPU_USAGE, "CPU", value, "%"))
            pipeline.render_data_overlay(base, slots, config)
        self.assertEqual(base.tobytes(), original)
        for cache, limit in ((pipeline._overlay_font, 32),
                             (pipeline._text_masks, 128),
                             (pipeline.layout_data_overlay, 8)):
            self.assertEqual(cache.cache_info().maxsize, limit)
            self.assertLessEqual(cache.cache_info().currsize, limit)

    def test_lazy_jpeg_errors_remain_fail_closed_and_snapshot_is_unchanged(self):
        window, path, clock, _ = self.window_and_gif()
        self.assertTrue(window.load_image(path))
        window.start_lcd()
        source = window._frame_buffer
        previous = source.snapshot()
        with mock.patch.object(pipeline, "_encode_jpeg", return_value=b"invalid"):
            clock.now += 0.031
            source.request_next_frame()
        self.assertIs(source.snapshot(), previous)
        self.assertIn("fehlgeschlagen", window.status_label.text())
        window.stop_lcd()
        window._poll_refresh_controller()

    def test_failed_encoding_during_image_switch_preserves_running_animation(self):
        window, path, clock, _ = self.window_and_gif()
        self.assertTrue(window.load_image(path))
        window.start_lcd()
        previous_animation = window._prepared_animation
        previous_deadline = window._lcd_animation_scheduler.next_deadline
        source = window._frame_buffer
        previous = source.snapshot()
        with mock.patch.object(pipeline, "_encode_jpeg", return_value=b"invalid"):
            self.assertFalse(window.load_image(REFERENCE_PATH))
        self.assertIs(window._prepared_animation, previous_animation)
        self.assertEqual(window._lcd_animation_scheduler.next_deadline, previous_deadline)
        self.assertIs(source.snapshot(), previous)
        clock.now += 0.031
        source.request_next_frame()
        self.assertEqual(source.snapshot().generation, previous.generation + 1)
        window.stop_lcd()
        window._poll_refresh_controller()

    def test_initial_encoding_error_never_starts_controller(self):
        window, path, _, _ = self.window_and_gif()
        self.assertTrue(window.load_image(path))
        factory = mock.Mock(side_effect=AssertionError("invalid JPEG reached controller"))
        window._controller_factory = factory
        with mock.patch.object(pipeline, "_encode_jpeg", return_value=b"invalid"):
            window.start_lcd()
        factory.assert_not_called()
        self.assertIs(window._refresh_state, gui.GuiRefreshState.ERROR)

    def test_offset_timelines_retain_order_without_extra_lcd_encodes(self):
        window, path, clock, _ = self.window_and_gif()
        window.show()
        self.assertTrue(window.load_image(path))
        clock.now += 0.031
        window._advance_gif_animation()
        window.start_lcd()
        with mock.patch.object(pipeline, "_encode_jpeg", wraps=pipeline._encode_jpeg) as encode:
            for index in range(300):
                clock.now += 0.031
                before = encode.call_count
                window._advance_gif_animation()
                self.assertEqual(encode.call_count, before)
                window._frame_buffer.request_next_frame()
                self.assertEqual(window._animation_frame_index, (index + 2) % 3)
                self.assertEqual(window._lcd_animation_frame_index, (index + 1) % 3)
                self.assertLessEqual(encode.call_count - before, 1)
                self.assertLessEqual(len(window._animation_render_cache), 2)
        window.stop_lcd()
        window._poll_refresh_controller()

    def test_qt_pixmap_owns_pixels_after_composition_cache_eviction(self):
        window, path, clock, _ = self.window_and_gif(overlay=False)
        window.show()
        self.assertTrue(window.load_image(path))
        retained_pixmap = window._final_pixmap
        expected = retained_pixmap.toImage().copy()
        for _ in range(12):
            clock.now += 0.031
            window._advance_gif_animation()
        window._animation_render_cache.clear()
        self.assertEqual(retained_pixmap.toImage(), expected)
