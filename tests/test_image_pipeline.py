from __future__ import annotations

import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest import mock

from PIL import Image

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
