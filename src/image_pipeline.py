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
MAX_ANIMATION_FRAMES = 500
MAX_ANIMATION_SOURCE_PIXELS = 64_000_000
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


@dataclass(frozen=True)
class PreparedAnimationFrame:
    source_index: int
    duration_ms: int
    jpeg_bytes: bytes
    jpeg_info: lcd_transport.JpegInfo


@dataclass(frozen=True)
class PreparedAnimation:
    source_path: Path
    source_size: tuple[int, int]
    scale_mode: ScaleMode
    loop_count: int | None
    frames: tuple[PreparedAnimationFrame, ...]


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


def _prepare_frame(
    source_frame: Image.Image, mode: ScaleMode
) -> tuple[tuple[int, int], bytes, lcd_transport.JpegInfo]:
    oriented = ImageOps.exif_transpose(source_frame)
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
    return oriented_size, jpeg_bytes, jpeg_info


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

    oriented_size, jpeg_bytes, jpeg_info = _prepare_frame(first_frame, mode)

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


def prepare_gif(path: Path, *, mode: ScaleMode = "crop") -> PreparedAnimation:
    """Decode and JPEG-prepare every GIF frame without enabling live animation."""
    if mode not in ("crop", "fit"):
        raise ImagePipelineError(f"Unbekannter Skalierungsmodus: {mode}")

    resolved = path.expanduser().resolve()
    try:
        with Image.open(resolved) as source:
            source_format = (source.format or "").upper()
            if source_format != "GIF":
                raise ImagePipelineError("Animationsvorbereitung akzeptiert ausschließlich GIF")

            source_size = source.size
            frame_count = int(getattr(source, "n_frames", 1))
            if source_size[0] <= 0 or source_size[1] <= 0:
                raise ImagePipelineError("Das GIF besitzt ungültige Abmessungen")
            if not 1 <= frame_count <= MAX_ANIMATION_FRAMES:
                raise ImagePipelineError(
                    f"GIF-Frameanzahl muss zwischen 1 und {MAX_ANIMATION_FRAMES} liegen"
                )
            total_pixels = source_size[0] * source_size[1] * frame_count
            if total_pixels > MAX_ANIMATION_SOURCE_PIXELS:
                raise ImagePipelineError(
                    "GIF überschreitet die Gesamtpixelgrenze von "
                    f"{MAX_ANIMATION_SOURCE_PIXELS}"
                )

            raw_loop = source.info.get("loop")
            loop_count = int(raw_loop) if raw_loop is not None else None
            if loop_count is not None and loop_count < 0:
                raise ImagePipelineError("GIF-Loopwert darf nicht negativ sein")

            frames: list[PreparedAnimationFrame] = []
            for index in range(frame_count):
                source.seek(index)
                source.load()
                raw_duration = source.info.get("duration", 0)
                duration_ms = int(raw_duration)
                if duration_ms < 0:
                    raise ImagePipelineError("GIF-Framedauer darf nicht negativ sein")
                frame = source.convert("RGBA").copy()
                _, jpeg_bytes, jpeg_info = _prepare_frame(frame, mode)
                frames.append(
                    PreparedAnimationFrame(
                        source_index=index,
                        duration_ms=duration_ms,
                        jpeg_bytes=jpeg_bytes,
                        jpeg_info=jpeg_info,
                    )
                )
    except ImagePipelineError:
        raise
    except (FileNotFoundError, PermissionError, UnidentifiedImageError, OSError) as error:
        raise ImagePipelineError(f"GIF kann nicht gelesen werden: {error}") from error

    return PreparedAnimation(
        source_path=resolved,
        source_size=source_size,
        scale_mode=mode,
        loop_count=loop_count,
        frames=tuple(frames),
    )
