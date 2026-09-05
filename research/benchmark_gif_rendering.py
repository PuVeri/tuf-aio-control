#!/usr/bin/env python3
"""Offline render benchmark. No discovery, sensors, device handles or live sender.

Run from any directory with the existing Python/Pillow/PySide6 environment.
Wall times are measured without instrumentation; component timings and cProfile
come from separate passes. Simulated time drives the real GUI callbacks, not a
real-time FPS limit. The fake sender validates and builds reports in memory.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import ExitStack
import cProfile
import functools
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import statistics
import sys
import tempfile
import time
from unittest import mock

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path(os.environ.get("TUF_BENCH_SOURCE_ROOT", ROOT))
sys.path.insert(0, str(SOURCE_ROOT / "src"))

import PIL
from PIL import Image, ImageChops, ImageDraw
import PySide6
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import image_pipeline as pipeline
import lcd_refresh
import lcd_transport
import refresh_diagnostics
import system_sensors
import tuf_aio_gui as gui


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class MemoryController:
    """Synchronous transfer completion under benchmark control; no worker/I/O."""

    result = None
    is_running = False

    def __init__(self, source):
        self.source = source
        self.frames = 0

    def start(self):
        self.is_running = True

    def request_stop(self):
        self.is_running = False

    def send(self):
        jpeg = self.source.snapshot().jpeg_bytes
        info = lcd_transport.validate_jpeg(jpeg)
        reports = lcd_transport.build_segments(jpeg)
        assert len(reports) == info.segment_count
        self.frames += 1


class Components:
    """Nested exclusive timings: parent time excludes measured children."""

    def __init__(self):
        self.ns = defaultdict(int)
        self.calls = defaultdict(int)
        self.stack = []

    def wrap(self, name, function):
        @functools.wraps(function)
        def measured(*args, **kwargs):
            entry = [time.perf_counter_ns(), 0]
            self.stack.append(entry)
            try:
                return function(*args, **kwargs)
            finally:
                elapsed = time.perf_counter_ns() - entry[0]
                self.stack.pop()
                self.ns[name] += elapsed - entry[1]
                self.calls[name] += 1
                if self.stack:
                    self.stack[-1][1] += elapsed
        return measured

    def install(self, patches):
        targets = {
            "lookup/composition Python": [(pipeline, "compose_lcd_frame"),
                (pipeline, "render_prepared_animation_frame"),
                (gui.MainWindow, "_prepare_animation_frame")],
            "GIF decode": [(pipeline, "prepare_gif")],
            "image copy/convert/bytes": [(Image.Image, "copy"),
                (Image.Image, "convert"), (Image, "frombytes"),
                (Image.Image, "tobytes")],
            "resize": [(pipeline, "_scale_image"), (Image.Image, "resize")],
            "telemetry composition": [(pipeline, "render_data_overlay"),
                (pipeline, "render_temperature_overlay")],
            "font load/layout/draw": [(pipeline, "_overlay_font"),
                (pipeline, "_fit_font"), (pipeline, "layout_data_overlay"),
                (ImageDraw.ImageDraw, "text")],
            "rotation": [(pipeline, "rotate_composition")],
            "JPEG encode": [(pipeline, "_encode_jpeg")],
            "JPEG validation": [(lcd_transport, "validate_jpeg")],
            "Qt image/pixmap (+JPEG decode in baseline)": [
                (gui.MainWindow, "_refresh_preview_if_needed")],
            "Qt scaling/widget": [(gui.MainWindow, "_update_scaled_preview")],
            "metadata widgets": [(gui.MainWindow, "_show_prepared_image")],
            "buffer publish": [(lcd_refresh.LatestFrameBuffer, "publish")],
            "sensor snapshot/slots": [(gui.MainWindow, "_overlay_slots"),
                (gui.MainWindow, "refresh_temperatures")],
            "memory sender/reports": [(MemoryController, "send")],
        }
        if hasattr(pipeline, "_draw_data_overlay"):
            targets["telemetry composition"].append((pipeline, "_draw_data_overlay"))
            targets["font load/layout/draw"].append((pipeline, "_text_masks"))
        for name, items in targets.items():
            for owner, attr in items:
                replacement = self.wrap(name, getattr(owner, attr))
                if owner is gui.MainWindow and attr == "_update_scaled_preview":
                    replacement = staticmethod(replacement)
                patches.enter_context(mock.patch.object(owner, attr, replacement))


def fixture(path):
    # Existing JPEG fixture, translated into 12 distinct GIF frames. Preparation
    # and fixture generation are excluded from steady-state measurements.
    with Image.open(ROOT / "tests/fixtures/lcd-0x08-reference.jpg") as source:
        rgb = source.convert("RGB")
    frames = [ImageChops.offset(rgb, index * 13, index * 7) for index in range(12)]
    frames[0].save(path, format="GIF", save_all=True, append_images=frames[1:],
                   duration=[60] * 12, loop=0, disposal=2)


def run(directory, path, scenario, frames, overlay, preview_offset=0, *, components=None, profile=None):
    clock = Clock()
    settings = QSettings(str(directory / "settings.ini"), QSettings.Format.IniFormat)
    settings.clear()
    settings.setValue(gui.OVERLAY_ENABLED_SETTING, overlay)
    settings.setValue(gui.ROTATION_SETTING, 90)
    settings.setValue(gui.GIF_PLAYBACK_SPEED_SETTING, 2.0)
    sensor = system_sensors.TemperatureSensor("fixture", "fixture", Path("/offline"), "1")

    def sample():
        value = 40 + int(clock.now) % 20
        return system_sensors.TemperatureSnapshot(
            cpu_usage=system_sensors.PercentageValue(value, "fixture"),
            gpu_usage=system_sensors.PercentageValue(value + 10, "fixture"),
            cpu_package=system_sensors.TemperatureValue(value + 15, sensor),
            gpu=system_sensors.TemperatureValue(value + 5, sensor))

    with mock.patch.object(gui.transport, "discover_lcd_interface", return_value=(None, "offline")):
        window = gui.MainWindow(settings=settings, sensor_reader=sample,
            controller_factory=MemoryController, animation_clock=clock,
            diagnostics_factory=lambda: refresh_diagnostics.NULL_DIAGNOSTICS)
    try:
        if scenario != "lcd":
            window.show()
        started = time.perf_counter_ns()
        assert window.load_image(path)
        load_ms = (time.perf_counter_ns() - started) / 1e6
        if scenario == "combined":
            for _ in range(preview_offset):
                clock.now += 0.031
                window._advance_gif_animation()
        if scenario in {"lcd", "combined", "static"}:
            window.start_lcd()
            assert window._refresh_state is gui.GuiRefreshState.RUNNING
        # Drain initial layout/paint/autostart events before deterministic timing.
        QApplication.processEvents()
        for timer in (window._temperature_timer, window._animation_timer,
                      window._transport_animation_timer, window._refresh_state_timer):
            timer.stop()

        def tick(index):
            # GIF: one 30-FPS scheduling opportunity; static: one 1-Hz
            # opportunity, so the control also measures hundreds of updates.
            clock.now += (1.0 if scenario == "static" else 1.0 / 30) + 0.000001
            if scenario == "static" or index % 30 == 0:
                window.refresh_temperatures()
            if scenario in {"preview", "combined"}:
                window._advance_gif_animation()
            if scenario in {"lcd", "combined"}:
                window._frame_buffer.request_next_frame()
                window._refresh_controller.send()
            elif scenario == "static":
                window._refresh_controller.send()

        for index in range(60):
            tick(index)
        with ExitStack() as patches:
            if components is not None:
                components.install(patches)
            if profile is not None:
                profile.enable()
            started = time.perf_counter_ns()
            for index in range(frames):
                tick(index)
            elapsed = time.perf_counter_ns() - started
            if profile is not None:
                profile.disable()
        return {"total_ms": elapsed / 1e6, "ms_per_tick": elapsed / frames / 1e6,
                "processing_ticks_per_second": frames * 1e9 / elapsed,
                "load_ms": load_ms}
    finally:
        window._stop_application_timers()
        if window._refresh_controller is not None:
            window._refresh_controller.request_stop()
        window.hide()
        window.tray_icon.hide()
        window.deleteLater()
        QApplication.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--overlay", choices=("on", "off"), default="on")
    parser.add_argument("--scenarios", nargs="+", choices=("preview", "lcd", "combined", "static"),
                        default=("preview", "lcd", "combined", "static"))
    parser.add_argument("--preview-offset", type=int, choices=range(4), default=0)
    args = parser.parse_args()
    if args.frames < 300 or args.repeats < 1:
        parser.error("use at least 300 frames and one repeat")
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    result = {"python": platform.python_version(), "platform": platform.platform(),
              "pillow": PIL.__version__, "pyside": PySide6.__version__,
              "frames": args.frames, "repeats": args.repeats, "overlay": args.overlay,
              "rotation": 90, "preview_offset": args.preview_offset, "scenarios": {},
              "source_sha256": {name: hashlib.sha256((SOURCE_ROOT / "src" / name).read_bytes()).hexdigest()
                  for name in ("image_pipeline.py", "tuf_aio_gui.py", "gif_animation.py", "lcd_refresh.py", "lcd_transport.py")}}
    with tempfile.TemporaryDirectory(prefix="tuf-render-bench-") as temporary:
        directory = Path(temporary)
        gif = directory / "reference-animation.gif"
        fixture(gif)
        result["gif_sha256"] = hashlib.sha256(gif.read_bytes()).hexdigest()
        for scenario in args.scenarios:
            path = ROOT / "tests/fixtures/lcd-0x08-reference.jpg" if scenario == "static" else gif
            options = (directory, path, scenario, args.frames, args.overlay == "on", args.preview_offset)
            runs = [run(*options) for _ in range(args.repeats)]
            components = Components()
            instrumented = run(*options, components=components)
            profile = cProfile.Profile()
            run(*options, profile=profile)
            stats = pstats.Stats(profile)
            top = sorted(stats.stats.items(), key=lambda item: item[1][3], reverse=True)[:25]
            result["scenarios"][scenario] = {
                "runs": runs, "median_ms_per_tick": statistics.median(r["ms_per_tick"] for r in runs),
                "components_separate_pass": {name: {"calls": components.calls[name],
                    "exclusive_ms": ns / 1e6, "ms_per_tick": ns / args.frames / 1e6,
                    "percent_instrumented_total": ns / (instrumented["total_ms"] * 1e6) * 100}
                    for name, ns in sorted(components.ns.items(), key=lambda item: -item[1])},
                "instrumented_total_ms": instrumented["total_ms"],
                "cprofile_top_cumulative": [{"site": f"{Path(key[0]).name}:{key[1]}:{key[2]}",
                    "calls": value[1], "self_seconds": value[2], "cumulative_seconds": value[3]}
                    for key, value in top]}
            print(scenario, result["scenarios"][scenario]["median_ms_per_tick"], "ms/tick", flush=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
