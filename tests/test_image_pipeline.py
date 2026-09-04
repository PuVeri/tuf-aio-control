from __future__ import annotations

import math
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(PROJECT_ROOT / "src"))

import image_pipeline
import lcd_transport


class ImagePipelineOfflineTests(unittest.TestCase):
    def _prepare(
        self,
        image: Image.Image,
        *,
        suffix: str,
        image_format: str,
        mode: image_pipeline.ScaleMode = "crop",
        **save_options: object,
    ) -> image_pipeline.PreparedImage:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"source{suffix}"
            image.save(path, format=image_format, **save_options)
            return image_pipeline.prepare_image(path, mode=mode)

    def _assert_valid_output(self, result: image_pipeline.PreparedImage) -> Image.Image:
        info = lcd_transport.validate_jpeg(result.jpeg_bytes)
        self.assertEqual((info.width, info.height), (320, 320))
        self.assertEqual(info.sof_marker, 0xC0)
        self.assertEqual(info.precision, 8)
        self.assertEqual(
            [
                (item.horizontal_sampling, item.vertical_sampling)
                for item in info.components
            ],
            [(2, 2), (1, 1), (1, 1)],
        )
        self.assertLessEqual(len(result.jpeg_bytes), lcd_transport.MAX_JPEG_BYTES)
        decoded = Image.open(BytesIO(result.jpeg_bytes))
        decoded.load()
        self.assertEqual(decoded.size, (320, 320))
        return decoded.convert("RGB")

    def test_landscape_crop_fills_canvas_without_distortion(self) -> None:
        result = self._prepare(
            Image.new("RGB", (640, 320), "white"),
            suffix=".png",
            image_format="PNG",
            mode="crop",
        )
        decoded = self._assert_valid_output(result)
        self.assertGreater(min(decoded.getpixel((4, 4))), 235)

    def test_portrait_crop_fills_canvas_without_distortion(self) -> None:
        result = self._prepare(
            Image.new("RGB", (320, 640), "white"),
            suffix=".png",
            image_format="PNG",
            mode="crop",
        )
        decoded = self._assert_valid_output(result)
        self.assertGreater(min(decoded.getpixel((4, 4))), 235)

    def test_landscape_fit_adds_black_bars(self) -> None:
        result = self._prepare(
            Image.new("RGB", (640, 320), "white"),
            suffix=".png",
            image_format="PNG",
            mode="fit",
        )
        decoded = self._assert_valid_output(result)
        self.assertLess(max(decoded.getpixel((160, 10))), 20)
        self.assertGreater(min(decoded.getpixel((160, 160))), 235)

    def test_portrait_fit_adds_black_bars(self) -> None:
        result = self._prepare(
            Image.new("RGB", (320, 640), "white"),
            suffix=".png",
            image_format="PNG",
            mode="fit",
        )
        decoded = self._assert_valid_output(result)
        self.assertLess(max(decoded.getpixel((10, 160))), 20)
        self.assertGreater(min(decoded.getpixel((160, 160))), 235)

    def test_square_remains_square_in_both_modes(self) -> None:
        for mode in ("crop", "fit"):
            with self.subTest(mode=mode):
                result = self._prepare(
                    Image.new("RGB", (500, 500), "green"),
                    suffix=".png",
                    image_format="PNG",
                    mode=mode,
                )
                self._assert_valid_output(result)
                self.assertEqual(result.oriented_size, (500, 500))

    def test_png_alpha_is_composited_on_black(self) -> None:
        source = Image.new("RGBA", (320, 320), (255, 0, 0, 0))
        for x in range(120, 200):
            for y in range(120, 200):
                source.putpixel((x, y), (255, 255, 255, 255))
        result = self._prepare(
            source,
            suffix=".png",
            image_format="PNG",
        )
        decoded = self._assert_valid_output(result)
        self.assertLess(max(decoded.getpixel((10, 10))), 20)
        self.assertGreater(min(decoded.getpixel((160, 160))), 235)

    def test_jpeg_png_webp_and_bmp_inputs(self) -> None:
        cases = (
            ("JPEG", ".jpg", {}),
            ("PNG", ".png", {}),
            ("WEBP", ".webp", {"lossless": True}),
            ("BMP", ".bmp", {}),
        )
        for image_format, suffix, options in cases:
            with self.subTest(image_format=image_format):
                result = self._prepare(
                    Image.new("RGB", (480, 270), "#4090d0"),
                    suffix=suffix,
                    image_format=image_format,
                    **options,
                )
                self.assertEqual(result.source_format, image_format)
                self._assert_valid_output(result)

    def test_animated_gif_uses_only_red_frame_zero(self) -> None:
        first = Image.new("RGB", (320, 320), "red")
        second = Image.new("RGB", (320, 320), "blue")
        result = self._prepare(
            first,
            suffix=".gif",
            image_format="GIF",
            save_all=True,
            append_images=[second],
            duration=50,
            loop=0,
        )
        decoded = self._assert_valid_output(result)
        red, _, blue = decoded.getpixel((160, 160))
        self.assertTrue(result.gif_first_frame_only)
        self.assertGreater(red, 220)
        self.assertLess(blue, 30)

    def test_gif_preparation_preserves_frames_durations_and_loop_value(self) -> None:
        images = (
            Image.new("RGB", (320, 320), "red"),
            Image.new("RGB", (320, 320), "green"),
            Image.new("RGB", (320, 320), "blue"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            images[0].save(
                path,
                format="GIF",
                save_all=True,
                append_images=list(images[1:]),
                duration=[40, 90, 120],
                loop=2,
            )
            prepared = image_pipeline.prepare_gif(path, mode="fit")

        self.assertEqual(prepared.source_size, (320, 320))
        self.assertEqual(prepared.scale_mode, "fit")
        self.assertEqual(prepared.loop_count, 2)
        self.assertEqual(
            [frame.source_index for frame in prepared.frames],
            [0, 1, 2],
        )
        self.assertEqual(
            [frame.duration_ms for frame in prepared.frames],
            [40, 90, 120],
        )
        self.assertEqual(len({frame.jpeg_bytes for frame in prepared.frames}), 3)
        for frame in prepared.frames:
            self.assertEqual(frame.jpeg_info, lcd_transport.validate_jpeg(frame.jpeg_bytes))

    def test_overlay_layout_is_triangular_and_inside_round_safe_area(self) -> None:
        placements = image_pipeline.layout_temperature_overlay(
            image_pipeline.TemperatureOverlayValues(51.25, 43.5, 46.75),
            image_pipeline.TemperatureOverlayConfig(enabled=True),
        )
        self.assertEqual(
            [placement.sensor for placement in placements],
            ["cpu_package", "gpu", "cpu_ccd"],
        )
        self.assertLess(placements[0].center[0], 160)
        self.assertGreater(placements[1].center[0], 160)
        self.assertGreater(placements[2].center[1], placements[0].center[1])
        self.assertEqual(
            [placement.label for placement in placements],
            ["CPU Package / Tctl", "GPU / edge", "CPU CCD / Tccd1"],
        )
        self.assertLess(
            image_pipeline.OVERLAY_LABEL_PREFERRED_SIZE,
            image_pipeline.OVERLAY_VALUE_MINIMUM_SIZE,
        )
        self.assertEqual(image_pipeline.OVERLAY_LABEL_PREFERRED_SIZE, 13)
        self.assertEqual(image_pipeline.OVERLAY_VALUE_PREFERRED_SIZE, 33)
        for placement in placements:
            left, top, right, bottom = placement.bounds
            self.assertGreaterEqual(left, image_pipeline.OVERLAY_SAFE_BOUNDS[0])
            self.assertGreaterEqual(top, image_pipeline.OVERLAY_SAFE_BOUNDS[1])
            self.assertLessEqual(right, image_pipeline.OVERLAY_SAFE_BOUNDS[2])
            self.assertLessEqual(bottom, image_pipeline.OVERLAY_SAFE_BOUNDS[3])
            for x in (left, right):
                for y in (top, bottom):
                    distance = ((x - 160) ** 2 + (y - 160) ** 2) ** 0.5
                    self.assertLessEqual(
                        distance,
                        image_pipeline.OVERLAY_ROUND_SAFE_RADIUS,
                    )

    def test_overlay_font_strategy_prefers_weighted_monospace_with_fallback(self) -> None:
        self.assertEqual(
            image_pipeline.OVERLAY_FONT_CANDIDATES["label"][0],
            "NotoSansMono-SemiBold.ttf",
        )
        self.assertEqual(
            image_pipeline.OVERLAY_FONT_CANDIDATES["value"][0],
            "NotoSansMono-Bold.ttf",
        )
        fallback_font = ImageFont.load_default(size=13)
        with (
            mock.patch.object(
                image_pipeline.ImageFont,
                "truetype",
                side_effect=OSError("font unavailable"),
            ),
            mock.patch.object(
                image_pipeline.ImageFont,
                "load_default",
                return_value=fallback_font,
            ) as fallback,
        ):
            font = image_pipeline._overlay_font(13, "label")
        fallback.assert_called_once_with(size=13)
        self.assertIsNotNone(font)

    def test_overlay_uses_distinct_label_and_value_font_roles(self) -> None:
        with mock.patch.object(
            image_pipeline,
            "_overlay_font",
            wraps=image_pipeline._overlay_font,
        ) as load_font:
            image_pipeline.layout_temperature_overlay(
                image_pipeline.TemperatureOverlayValues(51.25, 43.5, 46.75),
                image_pipeline.TemperatureOverlayConfig(enabled=True),
            )
        roles = {call.args[1] for call in load_font.call_args_list}
        self.assertEqual(roles, {"label", "value"})

    def test_missing_overlay_values_use_em_dash_and_default_white(self) -> None:
        placements = image_pipeline.layout_temperature_overlay(
            image_pipeline.TemperatureOverlayValues(),
            image_pipeline.TemperatureOverlayConfig(enabled=True),
        )
        self.assertEqual([item.value_text for item in placements], ["—", "—", "—"])
        self.assertEqual([item.color for item in placements], ["#FFFFFF"] * 3)

    def test_disabled_overlay_preserves_base_pixels_and_jpeg_bytes(self) -> None:
        result = self._prepare(
            Image.new("RGB", (320, 320), "#204060"),
            suffix=".png",
            image_format="PNG",
        )
        rerendered = image_pipeline.rerender_prepared_image(
            result,
            overlay_config=image_pipeline.TemperatureOverlayConfig(enabled=False),
            temperatures=image_pipeline.TemperatureOverlayValues(50.0, 40.0, 45.0),
        )
        self.assertEqual(rerendered.base_rgb_bytes, result.base_rgb_bytes)
        self.assertEqual(rerendered.jpeg_bytes, result.jpeg_bytes)

    def test_custom_overlay_color_is_used_for_all_three_sensors(self) -> None:
        config = image_pipeline.TemperatureOverlayConfig(
            enabled=True,
            colors=image_pipeline.TemperatureOverlayColors.uniform("#12aBcD"),
        )
        placements = image_pipeline.layout_temperature_overlay(
            image_pipeline.TemperatureOverlayValues(50.0, 40.0, 45.0),
            config,
        )
        self.assertEqual([item.color for item in placements], ["#12ABCD"] * 3)
        base = Image.new("RGB", (320, 320), "black")
        rendered = image_pipeline.render_temperature_overlay(
            base,
            image_pipeline.TemperatureOverlayValues(50.0, 40.0, 45.0),
            config,
        )
        self.assertNotEqual(rendered.tobytes(), base.tobytes())
        self.assertEqual(rendered.getpixel((160, 160)), base.getpixel((160, 160)))

    def test_overlay_is_supported_for_png_jpeg_and_gif_frame(self) -> None:
        config = image_pipeline.TemperatureOverlayConfig(enabled=True)
        values = image_pipeline.TemperatureOverlayValues(50.0, 40.0, 45.0)
        cases = (("PNG", ".png"), ("JPEG", ".jpg"), ("GIF", ".gif"))
        for image_format, suffix in cases:
            with self.subTest(image_format=image_format):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / f"source{suffix}"
                    Image.new("RGB", (320, 320), "#204060").save(
                        path,
                        format=image_format,
                    )
                    without_overlay = image_pipeline.prepare_image(path)
                    prepared = image_pipeline.prepare_image(
                        path,
                        overlay_config=config,
                        temperatures=values,
                    )
                self._assert_valid_output(prepared)
                self.assertEqual(prepared.base_rgb_bytes, without_overlay.base_rgb_bytes)
                self.assertNotEqual(prepared.jpeg_bytes, without_overlay.jpeg_bytes)

    def test_gif_overlay_rerender_preserves_order_timing_and_base_frames(self) -> None:
        images = (
            Image.new("RGB", (320, 320), "red"),
            Image.new("RGB", (320, 320), "blue"),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "animated.gif"
            images[0].save(
                path,
                format="GIF",
                save_all=True,
                append_images=[images[1]],
                duration=[40, 90],
                loop=2,
            )
            prepared = image_pipeline.prepare_gif(path)
        rerendered = image_pipeline.rerender_prepared_animation(
            prepared,
            overlay_config=image_pipeline.TemperatureOverlayConfig(enabled=True),
            temperatures=image_pipeline.TemperatureOverlayValues(50.0, 40.0, 45.0),
        )
        self.assertEqual(
            [(frame.source_index, frame.duration_ms) for frame in rerendered.frames],
            [(0, 40), (1, 90)],
        )
        self.assertEqual(
            [frame.base_rgb_bytes for frame in rerendered.frames],
            [frame.base_rgb_bytes for frame in prepared.frames],
        )
        self.assertNotEqual(
            [frame.jpeg_bytes for frame in rerendered.frames],
            [frame.jpeg_bytes for frame in prepared.frames],
        )

    def test_complete_composition_rotates_clockwise_in_all_four_steps(self) -> None:
        base = Image.new("RGB", (320, 320), "black")
        base.paste("red", (0, 0, 80, 80))
        base.paste("green", (240, 0, 320, 80))
        base.paste("blue", (0, 240, 80, 320))
        base.paste("white", (240, 240, 320, 320))
        expected_corners = {
            0: ("red", "green", "blue", "white"),
            90: ("blue", "red", "white", "green"),
            180: ("white", "blue", "green", "red"),
            270: ("green", "white", "red", "blue"),
        }
        rgb = {
            "red": (255, 0, 0),
            "green": (0, 128, 0),
            "blue": (0, 0, 255),
            "white": (255, 255, 255),
        }
        for rotation, names in expected_corners.items():
            with self.subTest(rotation=rotation):
                result = image_pipeline.rotate_composition(base, rotation)
                corners = (
                    result.getpixel((20, 20)),
                    result.getpixel((300, 20)),
                    result.getpixel((20, 300)),
                    result.getpixel((300, 300)),
                )
                self.assertEqual(corners, tuple(rgb[name] for name in names))

    def test_arbitrary_metrics_off_and_missing_value_render_in_fixed_slots(self) -> None:
        import telemetry

        slots = image_pipeline.OverlaySlots(
            top_left=telemetry.MetricValue(
                telemetry.MetricId.CPU_USAGE, "CPU", 17.0, "%"
            ),
            top_right=telemetry.MetricValue(
                telemetry.MetricId.GPU_USAGE, "GPU", 82.0, "%"
            ),
            bottom_left=None,
            bottom_right=telemetry.MetricValue(
                telemetry.MetricId.GPU_TEMPERATURE,
                "GPU Temperatur",
                52.0,
                "°C",
            ),
        )
        placements = image_pipeline.layout_data_overlay(
            slots, image_pipeline.TemperatureOverlayConfig(enabled=True)
        )
        self.assertEqual(
            [item.sensor for item in placements],
            ["top_left", "top_right", "bottom_right"],
        )
        self.assertEqual(
            [item.value_text for item in placements], ["17 %", "82 %", "52 °C"]
        )

        missing = image_pipeline.layout_data_overlay(
            image_pipeline.OverlaySlots(
                top_left=telemetry.MetricValue(
                    telemetry.MetricId.CPU_PACKAGE, "CPU Package", None, "°C"
                )
            ),
            image_pipeline.TemperatureOverlayConfig(enabled=True),
        )
        self.assertEqual(missing[0].value_text, "—")

    def test_four_slot_grid_is_symmetric_nonoverlapping_and_round_safe(self) -> None:
        import telemetry

        metrics = tuple(
            telemetry.MetricValue(metric_id, label, value, unit)
            for metric_id, label, value, unit in (
                (telemetry.MetricId.CPU_USAGE, "CPU", 17.0, "%"),
                (telemetry.MetricId.GPU_USAGE, "GPU", 82.0, "%"),
                (telemetry.MetricId.CPU_PACKAGE, "CPU Package", 47.0, "°C"),
                (
                    telemetry.MetricId.GPU_TEMPERATURE,
                    "GPU Temperatur",
                    52.0,
                    "°C",
                ),
            )
        )
        placements = image_pipeline.layout_data_overlay(
            image_pipeline.OverlaySlots(*metrics),
            image_pipeline.TemperatureOverlayConfig(enabled=True),
        )
        self.assertEqual(
            [item.sensor for item in placements],
            ["top_left", "top_right", "bottom_left", "bottom_right"],
        )
        self.assertEqual(
            [item.center for item in placements],
            [(102, 105), (218, 105), (102, 247), (218, 247)],
        )
        self.assertGreater(218 - 102, 212 - 108)
        self.assertGreater(247 - 105, 242 - 110)
        for index, first in enumerate(placements):
            for second in placements[index + 1 :]:
                horizontal_gap = max(
                    first.bounds[0], second.bounds[0]
                ) - min(first.bounds[2], second.bounds[2])
                vertical_gap = max(
                    first.bounds[1], second.bounds[1]
                ) - min(first.bounds[3], second.bounds[3])
                self.assertTrue(horizontal_gap >= 0 or vertical_gap >= 0)
            for x in (first.bounds[0], first.bounds[2]):
                for y in (first.bounds[1], first.bounds[3]):
                    self.assertLessEqual(
                        math.hypot(x - 160, y - 160),
                        image_pipeline.OVERLAY_ROUND_SAFE_RADIUS,
                    )
        slot_names = ("top_left", "top_right", "bottom_left", "bottom_right")
        for disabled in slot_names:
            with self.subTest(disabled=disabled):
                slot_values = dict(zip(slot_names, metrics, strict=True))
                slot_values[disabled] = None
                visible = image_pipeline.layout_data_overlay(
                    image_pipeline.OverlaySlots(**slot_values),
                    image_pipeline.TemperatureOverlayConfig(enabled=True),
                )
                self.assertEqual(len(visible), 3)
                self.assertNotIn(disabled, {item.sensor for item in visible})

    def test_every_metric_fits_every_outward_slot_at_extreme_values(self) -> None:
        import telemetry

        slot_names = ("top_left", "top_right", "bottom_left", "bottom_right")
        config = image_pipeline.TemperatureOverlayConfig(enabled=True)
        for definition in telemetry.METRIC_DEFINITIONS:
            if definition.metric_id is telemetry.MetricId.OFF:
                continue
            for value in (None, 0.0, 100.0):
                metric = telemetry.MetricValue(
                    definition.metric_id,
                    definition.display_label,
                    value,
                    definition.unit,
                )
                for slot_name in slot_names:
                    with self.subTest(
                        metric=definition.metric_id,
                        value=value,
                        slot=slot_name,
                    ):
                        slots = image_pipeline.OverlaySlots(**{slot_name: metric})
                        placement = image_pipeline.layout_data_overlay(
                            slots, config
                        )[0]
                        left, top, right, bottom = placement.bounds
                        safe_left, safe_top, safe_right, safe_bottom = (
                            image_pipeline.OVERLAY_SAFE_BOUNDS
                        )
                        self.assertGreaterEqual(left, safe_left)
                        self.assertGreaterEqual(top, safe_top)
                        self.assertLessEqual(right, safe_right)
                        self.assertLessEqual(bottom, safe_bottom)
                        for x in (left, right):
                            for y in (top, bottom):
                                self.assertLessEqual(
                                    math.hypot(x - 160, y - 160),
                                    image_pipeline.OVERLAY_ROUND_SAFE_RADIUS,
                                )

    def test_overlay_is_composed_before_rotation_and_jpeg_validation(self) -> None:
        import telemetry

        base = Image.new("RGB", (320, 320), "black")
        slots = image_pipeline.OverlaySlots(
            top_left=telemetry.MetricValue(
                telemetry.MetricId.CPU_USAGE, "CPU", 17.0, "%"
            )
        )
        config = image_pipeline.TemperatureOverlayConfig(enabled=True)
        composed = image_pipeline.render_data_overlay(base, slots, config)
        rotated = image_pipeline.rotate_composition(composed, 90)
        jpeg, info = image_pipeline._encode_and_validate_frame(
            base.tobytes(),
            config,
            image_pipeline.TemperatureOverlayValues(),
            overlay_slots=slots,
            rotation_degrees=90,
        )
        self.assertEqual(info, image_pipeline.lcd_transport.validate_jpeg(jpeg))
        self.assertEqual(jpeg, image_pipeline._encode_jpeg(rotated))

    def test_asymmetric_base_and_all_four_overlays_rotate_once_together(self) -> None:
        import telemetry

        base = Image.new("RGB", (320, 320), "black")
        draw = image_pipeline.ImageDraw.Draw(base)
        draw.rectangle((12, 12, 52, 52), fill="#ff0000")
        draw.rectangle((268, 268, 308, 308), fill="#0000ff")
        slots = image_pipeline.OverlaySlots(
            *(
                telemetry.MetricValue(metric_id, label, value, unit)
                for metric_id, label, value, unit in (
                    (telemetry.MetricId.CPU_USAGE, "CPU", 11.0, "%"),
                    (telemetry.MetricId.GPU_USAGE, "GPU", 22.0, "%"),
                    (telemetry.MetricId.CPU_PACKAGE, "CPU Package", 33.0, "°C"),
                    (
                        telemetry.MetricId.GPU_TEMPERATURE,
                        "GPU Temperatur",
                        44.0,
                        "°C",
                    ),
                )
            )
        )
        config = image_pipeline.TemperatureOverlayConfig(enabled=True)
        unrotated = image_pipeline.render_data_overlay(base, slots, config)
        operations = {
            0: None,
            90: Image.Transpose.ROTATE_270,
            180: Image.Transpose.ROTATE_180,
            270: Image.Transpose.ROTATE_90,
        }
        for rotation, operation in operations.items():
            with self.subTest(rotation=rotation):
                expected = (
                    unrotated.copy()
                    if operation is None
                    else unrotated.transpose(operation)
                )
                final = image_pipeline.compose_lcd_frame(
                    base.tobytes(),
                    config,
                    image_pipeline.TemperatureOverlayValues(),
                    overlay_slots=slots,
                    rotation_degrees=rotation,
                )
                self.assertEqual(final.tobytes(), expected.tobytes())
                self.assertEqual(final.size, (320, 320))
                self.assertEqual(
                    image_pipeline._encode_jpeg(final),
                    image_pipeline._encode_jpeg(expected),
                )

    def test_exif_orientation_is_applied_before_scaling(self) -> None:
        exif = Image.Exif()
        exif[274] = 6
        result = self._prepare(
            Image.new("RGB", (40, 80), "white"),
            suffix=".jpg",
            image_format="JPEG",
            exif=exif,
        )
        self.assertEqual(result.source_size, (40, 80))
        self.assertEqual(result.oriented_size, (80, 40))
        self._assert_valid_output(result)

    def test_very_small_image_is_safely_upscaled(self) -> None:
        result = self._prepare(
            Image.new("RGB", (1, 1), "white"),
            suffix=".png",
            image_format="PNG",
        )
        self._assert_valid_output(result)

    def test_large_image_is_safely_downscaled(self) -> None:
        result = self._prepare(
            Image.new("RGB", (4000, 3000), "white"),
            suffix=".jpg",
            image_format="JPEG",
            quality=75,
        )
        self._assert_valid_output(result)

    def test_invalid_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.png"
            path.write_bytes(b"not an image")
            with self.assertRaisesRegex(image_pipeline.ImagePipelineError, "nicht gelesen"):
                image_pipeline.prepare_image(path)

    def test_encoder_contract_is_explicit_and_validator_enforced(self) -> None:
        self.assertEqual(image_pipeline.JPEG_QUALITY, 60)
        self.assertEqual(image_pipeline.JPEG_SUBSAMPLING, 2)
        observed: dict[str, object] = {}
        original_save = Image.Image.save

        def save_spy(
            image: Image.Image,
            output: object,
            format: str | None = None,
            **options: object,
        ) -> None:
            observed.update(options)
            observed["format"] = format
            original_save(image, output, format=format, **options)

        with mock.patch.object(Image.Image, "save", new=save_spy):
            encoded = image_pipeline._encode_jpeg(
                Image.new("RGB", (320, 320), "white")
            )
        self.assertEqual(observed["format"], "JPEG")
        self.assertEqual(observed["quality"], 60)
        self.assertEqual(observed["subsampling"], 2)
        self.assertIs(observed["progressive"], False)
        self.assertIs(observed["optimize"], False)
        lcd_transport.validate_jpeg(encoded)

        result = self._prepare(
            Image.new("RGB", (320, 320), "white"),
            suffix=".png",
            image_format="PNG",
        )
        info = lcd_transport.validate_jpeg(result.jpeg_bytes)
        self.assertEqual(info.sof_marker, 0xC0)
        self.assertLessEqual(len(result.jpeg_bytes), 204000)


if __name__ == "__main__":
    unittest.main()
