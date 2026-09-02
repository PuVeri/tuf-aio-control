#!/usr/bin/env python3
"""Offline image preparation for the validated ASUS LCD JPEG transport."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal

from PIL import Image, ImageOps, UnidentifiedImageError

import lcd_transport

OUTPUT_SIZE = (320, 320)
JPEG_QUALITY = 60
JPEG_SUBSAMPLING = 2  # libjpeg/Pillow: YCbCr 4:2:0
MAX_SOURCE_PIXELS = 64_000_000
SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "BMP", "GIF"})

ScaleMode = Literal["crop", "fit"]


class ImagePipelineError(ValueError):
    """The source cannot be converted into the validated LCD JPEG subset."""


@dataclass(frozen=True)
class PreparedImage:
    source_path: Path
    source_format: str
    source_size: tuple[int, int]
    oriented_size: tuple[int, int]
    scale_mode: ScaleMode
    gif_first_frame_only: bool
    jpeg_bytes: bytes
    jpeg_info: lcd_transport.JpegInfo


def _rgb_on_black(image: Image.Image) -> Image.Image:
    """Convert one oriented source frame to RGB with deterministic alpha handling."""
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
        return Image.alpha_composite(background, rgba).convert("RGB")
    return image.convert("RGB")


def _scale_image(image: Image.Image, mode: ScaleMode) -> Image.Image:
    if mode == "crop":
        return ImageOps.fit(
            image,
            OUTPUT_SIZE,
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
    if mode == "fit":
        contained = ImageOps.contain(
            image,
            OUTPUT_SIZE,
            method=Image.Resampling.LANCZOS,
        )
        canvas = Image.new("RGB", OUTPUT_SIZE, (0, 0, 0))
        offset = (
            (OUTPUT_SIZE[0] - contained.width) // 2,
            (OUTPUT_SIZE[1] - contained.height) // 2,
        )
        canvas.paste(contained, offset)
        return canvas
    raise ImagePipelineError(f"Unbekannter Skalierungsmodus: {mode}")


def _encode_jpeg(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(
        output,
        format="JPEG",
        quality=JPEG_QUALITY,
        subsampling=JPEG_SUBSAMPLING,
        progressive=False,
        optimize=False,
    )
    return output.getvalue()


def prepare_image(path: Path, *, mode: ScaleMode = "crop") -> PreparedImage:
    """Prepare only frame 0 of one supported file entirely in memory."""
    if mode not in ("crop", "fit"):
        raise ImagePipelineError(f"Unbekannter Skalierungsmodus: {mode}")

    resolved = path.expanduser().resolve()
    try:
        with Image.open(resolved) as source:
            source_format = (source.format or "").upper()
            if source_format not in SUPPORTED_FORMATS:
                raise ImagePipelineError(
                    f"Nicht unterstütztes Eingabeformat: {source_format or 'unbekannt'}"
                )

            source_size = source.size
            source_pixels = source_size[0] * source_size[1]
            if source_size[0] <= 0 or source_size[1] <= 0:
                raise ImagePipelineError("Das Quellbild besitzt ungültige Abmessungen")
            if source_pixels > MAX_SOURCE_PIXELS:
                raise ImagePipelineError(
                    f"Quellbild überschreitet die Sicherheitsgrenze von "
                    f"{MAX_SOURCE_PIXELS} Pixeln"
                )

            source.seek(0)
            source.load()
            first_frame = source.copy()
    except ImagePipelineError:
        raise
    except (FileNotFoundError, PermissionError, UnidentifiedImageError, OSError) as error:
        raise ImagePipelineError(f"Bild kann nicht gelesen werden: {error}") from error

    oriented = ImageOps.exif_transpose(first_frame)
    oriented_size = oriented.size
    rgb = _rgb_on_black(oriented)
    prepared = _scale_image(rgb, mode)
    if prepared.mode != "RGB" or prepared.size != OUTPUT_SIZE:
        raise ImagePipelineError("Interne Bildvorbereitung verletzte RGB-/Größeninvariante")

    try:
        jpeg_bytes = _encode_jpeg(prepared)
    except OSError as error:
        raise ImagePipelineError(f"JPEG-Encoding fehlgeschlagen: {error}") from error

    try:
        jpeg_info = lcd_transport.validate_jpeg(jpeg_bytes)
    except (lcd_transport.JpegValidationError, RuntimeError, ValueError) as error:
        raise ImagePipelineError(
            f"Erzeugtes JPEG verletzt den ASUS-Transportvertrag: {error}"
        ) from error

    return PreparedImage(
        source_path=resolved,
        source_format=source_format,
        source_size=source_size,
        oriented_size=oriented_size,
        scale_mode=mode,
        gif_first_frame_only=source_format == "GIF",
        jpeg_bytes=jpeg_bytes,
        jpeg_info=jpeg_info,
    )
