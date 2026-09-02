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
