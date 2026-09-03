#!/usr/bin/env python3
"""Offline image preparation for the validated ASUS LCD JPEG transport."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from io import BytesIO
import math
from pathlib import Path
import re
from typing import Literal

from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

import lcd_transport

OUTPUT_SIZE = (320, 320)
JPEG_QUALITY = 60
JPEG_SUBSAMPLING = 2  # libjpeg/Pillow: YCbCr 4:2:0
MAX_SOURCE_PIXELS = 64_000_000
MAX_ANIMATION_FRAMES = 500
MAX_ANIMATION_SOURCE_PIXELS = 64_000_000
SUPPORTED_FORMATS = frozenset({"JPEG", "PNG", "WEBP", "BMP", "GIF"})
DEFAULT_OVERLAY_COLOR = "#FFFFFF"
OVERLAY_SAFE_BOUNDS = (24, 24, 296, 296)
OVERLAY_ROUND_CENTER = (160, 160)
OVERLAY_ROUND_SAFE_RADIUS = 148
OVERLAY_LABEL_PREFERRED_SIZE = 13
OVERLAY_LABEL_MINIMUM_SIZE = 8
OVERLAY_VALUE_PREFERRED_SIZE = 33
OVERLAY_VALUE_MINIMUM_SIZE = 22
OVERLAY_FONT_CANDIDATES = {
    "label": (
        "NotoSansMono-SemiBold.ttf",
        "/usr/share/fonts/google-noto/NotoSansMono-SemiBold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-SemiBold.ttf",
        "DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
        "LiberationMono-Bold.ttf",
    ),
    "value": (
        "NotoSansMono-Bold.ttf",
        "/usr/share/fonts/google-noto/NotoSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansMono-Bold.ttf",
        "DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf",
        "LiberationMono-Bold.ttf",
    ),
}

ScaleMode = Literal["crop", "fit"]
OverlaySensor = Literal["cpu_package", "gpu", "cpu_ccd"]
OverlayFontRole = Literal["label", "value"]


class ImagePipelineError(ValueError):
    """The source cannot be converted into the validated LCD JPEG subset."""


def normalize_overlay_color(value: object) -> str:
    """Return an uppercase #RRGGBB value or the safe default."""
    if isinstance(value, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", value):
        return value.upper()
    return DEFAULT_OVERLAY_COLOR


@dataclass(frozen=True)
class TemperatureOverlayColors:
    cpu_package: str = DEFAULT_OVERLAY_COLOR
    gpu: str = DEFAULT_OVERLAY_COLOR
    cpu_ccd: str = DEFAULT_OVERLAY_COLOR

    @classmethod
    def uniform(cls, color: object) -> TemperatureOverlayColors:
        normalized = normalize_overlay_color(color)
        return cls(normalized, normalized, normalized)


@dataclass(frozen=True)
class TemperatureOverlayConfig:
    enabled: bool = False
    colors: TemperatureOverlayColors = field(
        default_factory=TemperatureOverlayColors
    )


@dataclass(frozen=True)
class TemperatureOverlayValues:
    cpu_package: float | None = None
    gpu: float | None = None
    cpu_ccd: float | None = None


@dataclass(frozen=True)
class TemperatureOverlayPlacement:
    sensor: OverlaySensor
    label: str
    label_center: tuple[int, int]
    value_text: str
    center: tuple[int, int]
    bounds: tuple[int, int, int, int]
    color: str


@dataclass(frozen=True)
class PreparedImage:
    source_path: Path
    source_format: str
    source_size: tuple[int, int]
    oriented_size: tuple[int, int]
    scale_mode: ScaleMode
    gif_first_frame_only: bool
    base_rgb_bytes: bytes
    jpeg_bytes: bytes
    jpeg_info: lcd_transport.JpegInfo


@dataclass(frozen=True)
class PreparedAnimationFrame:
    source_index: int
    duration_ms: int
    base_rgb_bytes: bytes
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


def _format_temperature(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value:.0f} °C"


def _overlay_font(size: int, role: OverlayFontRole) -> ImageFont.FreeTypeFont:
    """Load a technical semibold/bold mono face with a safe Pillow fallback."""
    for candidate in OVERLAY_FONT_CANDIDATES[role]:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    preferred_size: int,
    minimum_size: int,
    maximum_width: int,
    role: OverlayFontRole,
) -> ImageFont.FreeTypeFont:
    for size in range(preferred_size, minimum_size - 1, -1):
        font = _overlay_font(size, role)
        bounds = draw.textbbox((0, 0), text, font=font, stroke_width=1)
        if bounds[2] - bounds[0] <= maximum_width:
            return font
    raise ImagePipelineError(f"Overlaytext ist zu breit: {text}")


def layout_temperature_overlay(
    values: TemperatureOverlayValues,
    config: TemperatureOverlayConfig,
) -> tuple[TemperatureOverlayPlacement, ...]:
    """Measure the three sparse text blocks used by preview and LCD output."""
    canvas = Image.new("RGB", OUTPUT_SIZE)
    draw = ImageDraw.Draw(canvas)
    specs: tuple[
        tuple[OverlaySensor, str, tuple[int, int], tuple[int, int], str], ...
    ] = (
        (
            "cpu_package",
            "CPU Package / Tctl",
            (102, 66),
            (102, 100),
            config.colors.cpu_package,
        ),
        ("gpu", "GPU / edge", (218, 66), (218, 100), config.colors.gpu),
        (
            "cpu_ccd",
            "CPU CCD / Tccd1",
            (160, 216),
            (160, 250),
            config.colors.cpu_ccd,
        ),
    )
    placements: list[TemperatureOverlayPlacement] = []
    for sensor, label, label_center, value_center, raw_color in specs:
        value_text = _format_temperature(getattr(values, sensor))
        label_font = _fit_font(
            draw,
            label,
            preferred_size=OVERLAY_LABEL_PREFERRED_SIZE,
            minimum_size=OVERLAY_LABEL_MINIMUM_SIZE,
            maximum_width=106,
            role="label",
        )
        value_font = _fit_font(
            draw,
            value_text,
            preferred_size=OVERLAY_VALUE_PREFERRED_SIZE,
            minimum_size=OVERLAY_VALUE_MINIMUM_SIZE,
            maximum_width=114,
            role="value",
        )
        label_bounds = draw.textbbox(
            label_center,
            label,
            font=label_font,
            anchor="mm",
            stroke_width=1,
        )
        value_bounds = draw.textbbox(
            value_center,
            value_text,
            font=value_font,
            anchor="mm",
            stroke_width=1,
        )
        bounds = (
            min(label_bounds[0], value_bounds[0]),
            min(label_bounds[1], value_bounds[1]),
            max(label_bounds[2], value_bounds[2]),
            max(label_bounds[3], value_bounds[3]),
        )
        left, top, right, bottom = OVERLAY_SAFE_BOUNDS
        if not (
            left <= bounds[0] <= bounds[2] <= right
            and top <= bounds[1] <= bounds[3] <= bottom
        ):
            raise ImagePipelineError(
                f"Overlayblock überschreitet den sicheren Rand: {label}"
            )
        for x in (bounds[0], bounds[2]):
            for y in (bounds[1], bounds[3]):
                distance = math.hypot(
                    x - OVERLAY_ROUND_CENTER[0],
                    y - OVERLAY_ROUND_CENTER[1],
                )
                if distance > OVERLAY_ROUND_SAFE_RADIUS:
                    raise ImagePipelineError(
                        f"Overlayblock verlässt den runden Sichtbereich: {label}"
                    )
        placements.append(
            TemperatureOverlayPlacement(
                sensor=sensor,
                label=label,
                label_center=label_center,
                value_text=value_text,
                center=value_center,
                bounds=bounds,
                color=normalize_overlay_color(raw_color),
            )
        )
    return tuple(placements)


def render_temperature_overlay(
    base_image: Image.Image,
    values: TemperatureOverlayValues,
    config: TemperatureOverlayConfig,
) -> Image.Image:
    """Render the shared preview/LCD overlay without mutating the base image."""
    if base_image.size != OUTPUT_SIZE:
        raise ImagePipelineError("Temperaturoverlay benötigt exakt 320×320 Pixel")
    rendered = base_image.convert("RGB").copy()
    if not config.enabled:
        return rendered

    draw = ImageDraw.Draw(rendered)
    placement_by_sensor = {
        placement.sensor: placement
        for placement in layout_temperature_overlay(values, config)
    }
    for sensor in ("cpu_package", "gpu", "cpu_ccd"):
        placement = placement_by_sensor[sensor]
        label_font = _fit_font(
            draw,
            placement.label,
            preferred_size=OVERLAY_LABEL_PREFERRED_SIZE,
            minimum_size=OVERLAY_LABEL_MINIMUM_SIZE,
            maximum_width=106,
            role="label",
        )
        value_font = _fit_font(
            draw,
            placement.value_text,
            preferred_size=OVERLAY_VALUE_PREFERRED_SIZE,
            minimum_size=OVERLAY_VALUE_MINIMUM_SIZE,
            maximum_width=114,
            role="value",
        )
        draw.text(
            placement.label_center,
            placement.label,
            fill=placement.color,
            font=label_font,
            anchor="mm",
            stroke_width=1,
            stroke_fill="#000000",
        )
        draw.text(
            placement.center,
            placement.value_text,
            fill=placement.color,
            font=value_font,
            anchor="mm",
            stroke_width=1,
            stroke_fill="#000000",
        )
    return rendered


def _encode_and_validate_frame(
    base_rgb_bytes: bytes,
    overlay_config: TemperatureOverlayConfig,
    temperatures: TemperatureOverlayValues,
) -> tuple[bytes, lcd_transport.JpegInfo]:
    expected_length = OUTPUT_SIZE[0] * OUTPUT_SIZE[1] * 3
    if len(base_rgb_bytes) != expected_length:
        raise ImagePipelineError("Ungültiger interner 320×320-RGB-Basispuffer")
    base_image = Image.frombytes("RGB", OUTPUT_SIZE, base_rgb_bytes)
    final_image = render_temperature_overlay(base_image, temperatures, overlay_config)
    try:
        jpeg_bytes = _encode_jpeg(final_image)
    except OSError as error:
        raise ImagePipelineError(f"JPEG-Encoding fehlgeschlagen: {error}") from error

    try:
        jpeg_info = lcd_transport.validate_jpeg(jpeg_bytes)
    except (lcd_transport.JpegValidationError, RuntimeError, ValueError) as error:
        raise ImagePipelineError(
            f"Erzeugtes JPEG verletzt den ASUS-Transportvertrag: {error}"
        ) from error
    return jpeg_bytes, jpeg_info


def _prepare_frame(
    source_frame: Image.Image,
    mode: ScaleMode,
    overlay_config: TemperatureOverlayConfig,
    temperatures: TemperatureOverlayValues,
) -> tuple[tuple[int, int], bytes, bytes, lcd_transport.JpegInfo]:
    oriented = ImageOps.exif_transpose(source_frame)
    oriented_size = oriented.size
    rgb = _rgb_on_black(oriented)
    prepared = _scale_image(rgb, mode)
    if prepared.mode != "RGB" or prepared.size != OUTPUT_SIZE:
        raise ImagePipelineError("Interne Bildvorbereitung verletzte RGB-/Größeninvariante")

    base_rgb_bytes = prepared.tobytes()
    jpeg_bytes, jpeg_info = _encode_and_validate_frame(
        base_rgb_bytes,
        overlay_config,
        temperatures,
    )
    return oriented_size, base_rgb_bytes, jpeg_bytes, jpeg_info


def prepare_image(
    path: Path,
    *,
    mode: ScaleMode = "crop",
    overlay_config: TemperatureOverlayConfig = TemperatureOverlayConfig(),
    temperatures: TemperatureOverlayValues = TemperatureOverlayValues(),
) -> PreparedImage:
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

    oriented_size, base_rgb_bytes, jpeg_bytes, jpeg_info = _prepare_frame(
        first_frame,
        mode,
        overlay_config,
        temperatures,
    )

    return PreparedImage(
        source_path=resolved,
        source_format=source_format,
        source_size=source_size,
        oriented_size=oriented_size,
        scale_mode=mode,
        gif_first_frame_only=source_format == "GIF",
        base_rgb_bytes=base_rgb_bytes,
        jpeg_bytes=jpeg_bytes,
        jpeg_info=jpeg_info,
    )


def rerender_prepared_image(
    prepared: PreparedImage,
    *,
    overlay_config: TemperatureOverlayConfig,
    temperatures: TemperatureOverlayValues,
) -> PreparedImage:
    """Rebuild JPEG bytes from the cached base without reading sensors or source."""
    jpeg_bytes, jpeg_info = _encode_and_validate_frame(
        prepared.base_rgb_bytes,
        overlay_config,
        temperatures,
    )
    return replace(prepared, jpeg_bytes=jpeg_bytes, jpeg_info=jpeg_info)


def rerender_prepared_animation(
    prepared: PreparedAnimation,
    *,
    overlay_config: TemperatureOverlayConfig,
    temperatures: TemperatureOverlayValues,
) -> PreparedAnimation:
    """Rebuild cached GIF frames while preserving their order and timing."""
    frames: list[PreparedAnimationFrame] = []
    for frame in prepared.frames:
        jpeg_bytes, jpeg_info = _encode_and_validate_frame(
            frame.base_rgb_bytes,
            overlay_config,
            temperatures,
        )
        frames.append(replace(frame, jpeg_bytes=jpeg_bytes, jpeg_info=jpeg_info))
    return replace(prepared, frames=tuple(frames))


def prepare_gif(
    path: Path,
    *,
    mode: ScaleMode = "crop",
    overlay_config: TemperatureOverlayConfig = TemperatureOverlayConfig(),
    temperatures: TemperatureOverlayValues = TemperatureOverlayValues(),
) -> PreparedAnimation:
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
                _, base_rgb_bytes, jpeg_bytes, jpeg_info = _prepare_frame(
                    frame,
                    mode,
                    overlay_config,
                    temperatures,
                )
                frames.append(
                    PreparedAnimationFrame(
                        source_index=index,
                        duration_ms=duration_ms,
                        base_rgb_bytes=base_rgb_bytes,
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
