#!/usr/bin/env python3
"""Reusable one-frame ASUS LCD JPEG validation and transport."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from discover_device import HidrawInterface, discover

TARGET_VID = "0b05"
TARGET_PID = "1c7b"
TARGET_INTERFACE = 1
EXPECTED_INPUT_REPORT_BYTES = 16
WIRE_REPORT_BYTES = 1024
HIDRAW_WRITE_BYTES = 1025
CONTROL_BYTES = 4
PAYLOAD_BYTES = 1020
MAX_SEGMENTS = 200
MAX_JPEG_BYTES = MAX_SEGMENTS * PAYLOAD_BYTES
COMMAND = 0x08

SOI = 0xD8
EOI = 0xD9
SOS = 0xDA
SOF0 = 0xC0
SOF2 = 0xC2
APP0 = 0xE0
DQT = 0xDB
DRI = 0xDD
DAC = 0xCC
SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)
STANDARD_HUFFMAN_TABLE_SHA256 = {
    (0, 0): "9fb04cb1a8076318f33f273ffef967a9ea7291ecf3adeca79f643dfd300de425",
    (1, 0): "f27ce9b718f91cd426885e6ce4a37d0ba4900db219f719eef29ecc1f7f4fd5f0",
    (0, 1): "af48d4f608dfb682fd19ee479c66dad5342dfbed5b1d1807b95393162a8715d1",
    (1, 1): "8cf60aa835f8474bb590e73332bee9c246bec9ce1e368aa725674c096f3efd2c",
}

class JpegValidationError(ValueError):
    """The supplied bytes are outside the deliberately narrow JPEG subset."""


class LcdTransportError(RuntimeError):
    """A one-frame transfer failed and no further write was attempted."""


@dataclass(frozen=True)
class JpegComponent:
    identifier: int
    horizontal_sampling: int
    vertical_sampling: int
    quantization_table: int


@dataclass(frozen=True)
class JpegInfo:
    length: int
    width: int
    height: int
    precision: int
    sof_marker: int
    components: tuple[JpegComponent, ...]
    jfif: bool
    segment_count: int
    padding_length: int


@dataclass(frozen=True)
class TransferSegment:
    index: int
    control: bytes
    payload: bytes
    wire_report: bytes
    hidraw_buffer: bytes


def segment_count(jpeg_length: int, *, max_segments: int = MAX_SEGMENTS) -> int:
    """Return the bounded number of 1020-byte transport payloads."""
    if jpeg_length <= 0:
        raise JpegValidationError("Die JPEG-Länge muss größer als null sein")
    count = (jpeg_length + PAYLOAD_BYTES - 1) // PAYLOAD_BYTES
    if not 1 <= max_segments <= MAX_SEGMENTS:
        raise ValueError(f"max_segments muss zwischen 1 und {MAX_SEGMENTS} liegen")
    if not 1 <= count <= max_segments:
        raise JpegValidationError(
            f"N muss zwischen 1 und {max_segments} liegen, ist aber {count}"
        )
    return count


def _next_header_marker(data: bytes, offset: int) -> tuple[int, int]:
    if offset >= len(data) or data[offset] != 0xFF:
        raise JpegValidationError(
            f"JPEG-Marker an Offset 0x{offset:x} erwartet"
        )
    marker_prefixes = 0
    while offset < len(data) and data[offset] == 0xFF:
        marker_prefixes += 1
        offset += 1
    if marker_prefixes != 1:
        raise JpegValidationError("JPEG-Marker enthält unerwartete Fillbytes")
    if offset >= len(data):
        raise JpegValidationError("Abgeschnittener JPEG-Marker")
    marker = data[offset]
    if marker == 0x00:
        raise JpegValidationError("Byte-Stuffing außerhalb der Scandaten")
    return marker, offset + 1


def _read_segment_payload(data: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 2 > len(data):
        raise JpegValidationError("Abgeschnittene JPEG-Segmentlänge")
    declared_length = int.from_bytes(data[offset : offset + 2], "big")
    if declared_length < 2:
        raise JpegValidationError("Ungültige JPEG-Segmentlänge")
    end = offset + declared_length
    if end > len(data):
        raise JpegValidationError("JPEG-Segment reicht über das Dateiende")
    return data[offset + 2 : end], end


def _find_scan_terminator(data: bytes, offset: int) -> tuple[int, int]:
    """Find a real marker in entropy data while respecting FF00 stuffing."""
    while offset < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue

        marker_prefixes = 1
        offset += 1
        while offset < len(data) and data[offset] == 0xFF:
            marker_prefixes += 1
            offset += 1
        if offset >= len(data):
            raise JpegValidationError("Abgeschnittene JPEG-Scandaten")

        marker = data[offset]
        offset += 1
        if marker_prefixes != 1:
            raise JpegValidationError("Fillbytes in den JPEG-Scandaten sind unzulässig")
        if marker == 0x00:
            continue
        if 0xD0 <= marker <= 0xD7:
            raise JpegValidationError("Restartmarker sind für diesen Test unzulässig")
        return marker, offset

    raise JpegValidationError("JPEG-EOI fehlt")


def _parse_sof0(payload: bytes) -> tuple[int, int, int, tuple[JpegComponent, ...]]:
    if len(payload) < 6:
        raise JpegValidationError("Abgeschnittenes SOF0-Segment")
    precision = payload[0]
    height = int.from_bytes(payload[1:3], "big")
    width = int.from_bytes(payload[3:5], "big")
    component_count = payload[5]
    if len(payload) != 6 + 3 * component_count:
        raise JpegValidationError("SOF0-Komponentenlänge ist inkonsistent")

    components: list[JpegComponent] = []
    for index in range(component_count):
        base = 6 + 3 * index
        sampling = payload[base + 1]
        horizontal = sampling >> 4
        vertical = sampling & 0x0F
        if horizontal == 0 or vertical == 0:
            raise JpegValidationError("Null-Samplingfaktor im SOF0-Segment")
        components.append(
            JpegComponent(
                identifier=payload[base],
                horizontal_sampling=horizontal,
                vertical_sampling=vertical,
                quantization_table=payload[base + 2],
            )
        )
    return precision, width, height, tuple(components)


def _validate_scan_header(payload: bytes) -> None:
    if not payload:
        raise JpegValidationError("Leeres SOS-Segment")
    scan_components = payload[0]
    if scan_components != 3 or len(payload) != 1 + 2 * scan_components + 3:
        raise JpegValidationError("Es ist genau ein Drei-Komponenten-Scan erforderlich")

    selectors = tuple(
        (payload[1 + 2 * index], payload[2 + 2 * index])
        for index in range(scan_components)
    )
    if selectors != ((1, 0x00), (2, 0x11), (3, 0x11)):
        raise JpegValidationError(
            "SOS-Komponenten oder Huffman-Tabellenselektoren sind nicht konservativ"
        )
    if payload[-3:] != bytes((0x00, 0x3F, 0x00)):
        raise JpegValidationError("Der SOS-Scan ist nicht Baseline Sequential")


def _validate_jfif(payload: bytes) -> None:
    if len(payload) != 14 or not payload.startswith(b"JFIF\x00"):
        raise JpegValidationError("JFIF-APP0 muss ein vollständiger Header ohne Thumbnail sein")
    if payload[5] != 1:
        raise JpegValidationError("Nur JFIF-Hauptversion 1 ist zulässig")
    if payload[7] not in (0, 1, 2):
        raise JpegValidationError("Ungültige JFIF-Dichteeinheit")
    if int.from_bytes(payload[8:10], "big") == 0:
        raise JpegValidationError("JFIF-X-Dichte darf nicht null sein")
    if int.from_bytes(payload[10:12], "big") == 0:
        raise JpegValidationError("JFIF-Y-Dichte darf nicht null sein")
    if payload[12:] != b"\x00\x00":
        raise JpegValidationError("JFIF-Thumbnails sind unzulässig")


def _parse_quantization_tables(payload: bytes) -> set[int]:
    tables: set[int] = set()
    offset = 0
    while offset < len(payload):
        table_info = payload[offset]
        offset += 1
        precision = table_info >> 4
        table_id = table_info & 0x0F
        if precision != 0 or table_id not in (0, 1):
            raise JpegValidationError("Nur 8-Bit-Quantisierungstabellen 0 und 1 sind zulässig")
        if table_id in tables:
            raise JpegValidationError("Doppelte Quantisierungstabelle im DQT-Segment")
        if offset + 64 > len(payload):
            raise JpegValidationError("Abgeschnittene Quantisierungstabelle")
        values = payload[offset : offset + 64]
        if any(value == 0 for value in values):
            raise JpegValidationError("Quantisierungstabellen dürfen keinen Nullwert enthalten")
        offset += 64
        tables.add(table_id)
    if not tables:
        raise JpegValidationError("Leeres DQT-Segment")
    return tables


def _parse_standard_huffman_tables(payload: bytes) -> set[tuple[int, int]]:
    tables: set[tuple[int, int]] = set()
    offset = 0
    while offset < len(payload):
        start = offset
        table_info = payload[offset]
        offset += 1
        table_class = table_info >> 4
        table_id = table_info & 0x0F
        key = (table_class, table_id)
        if key not in STANDARD_HUFFMAN_TABLE_SHA256:
            raise JpegValidationError("Unerwartete Huffman-Tabellenklasse oder -ID")
        if key in tables:
            raise JpegValidationError("Doppelte Huffman-Tabelle im DHT-Segment")
        if offset + 16 > len(payload):
            raise JpegValidationError("Abgeschnittene Huffman-Codeanzahlen")
        symbol_count = sum(payload[offset : offset + 16])
        offset += 16
        if offset + symbol_count > len(payload):
            raise JpegValidationError("Abgeschnittene Huffman-Symbolliste")
        offset += symbol_count
        table_bytes = payload[start:offset]
        if (
            hashlib.sha256(table_bytes).hexdigest()
            != STANDARD_HUFFMAN_TABLE_SHA256[key]
        ):
            raise JpegValidationError("JPEG verwendet keine Standard-Huffmantabelle")
        tables.add(key)
    if not tables:
        raise JpegValidationError("Leeres DHT-Segment")
    return tables


def validate_jpeg(data: bytes, *, max_segments: int = MAX_SEGMENTS) -> JpegInfo:
    """Validate the exact conservative JPEG subset without decoding pixels."""
    count = segment_count(len(data), max_segments=max_segments)
    if len(data) > max_segments * PAYLOAD_BYTES:
        raise JpegValidationError("JPEG überschreitet die Transportgrenze")
    if not data.startswith(b"\xff\xd8"):
        raise JpegValidationError("JPEG muss mit SOI FF D8 beginnen")

    offset = 2
    jfif = False
    sof: tuple[int, int, int, tuple[JpegComponent, ...]] | None = None
    quantization_tables: set[int] = set()
    huffman_tables: set[tuple[int, int]] = set()
    saw_sos = False

    while offset < len(data):
        marker, offset = _next_header_marker(data, offset)
        if marker == EOI:
            raise JpegValidationError("JPEG-EOI erschien vor den Scandaten")
        if marker == SOI or marker == 0x01 or 0xD0 <= marker <= 0xD7:
            raise JpegValidationError(f"Unerwarteter standalone Marker FF {marker:02X}")

        payload, offset = _read_segment_payload(data, offset)
        if marker == APP0:
            if jfif:
                raise JpegValidationError("Mehrere JFIF-APP0-Segmente sind unzulässig")
            _validate_jfif(payload)
            jfif = True
        elif marker == DQT:
            new_tables = _parse_quantization_tables(payload)
            if quantization_tables.intersection(new_tables):
                raise JpegValidationError("Doppelte Quantisierungstabelle")
            quantization_tables.update(new_tables)
        elif marker in SOF_MARKERS:
            if marker == SOF2:
                raise JpegValidationError("Progressive JPEG / SOF2 ist unzulässig")
            if marker != SOF0:
                raise JpegValidationError(
                    f"Nur Baseline SOF0 ist zulässig, gefunden FF {marker:02X}"
                )
            if sof is not None:
                raise JpegValidationError("Mehrere SOF-Segmente sind unzulässig")
            sof = _parse_sof0(payload)
        elif marker == 0xC4:
            new_tables = _parse_standard_huffman_tables(payload)
            if huffman_tables.intersection(new_tables):
                raise JpegValidationError("Doppelte Huffman-Tabelle")
            huffman_tables.update(new_tables)
        elif marker == DRI:
            raise JpegValidationError("Ein Restartintervall ist unzulässig")
        elif marker == DAC:
            raise JpegValidationError("Arithmetische JPEG-Codierung ist unzulässig")
        elif marker == SOS:
            if sof is None:
                raise JpegValidationError("SOS erschien vor SOF0")
            _validate_scan_header(payload)
            saw_sos = True
            terminator, after_terminator = _find_scan_terminator(data, offset)
            if terminator != EOI:
                raise JpegValidationError(
                    "Nach dem einzigen Scan ist unmittelbar EOI erforderlich"
                )
            if after_terminator != len(data):
                raise JpegValidationError("Bytes nach JPEG-EOI sind unzulässig")
            break
        else:
            raise JpegValidationError(f"Unzulässiger JPEG-Marker FF {marker:02X}")

    if sof is None:
        raise JpegValidationError("SOF0 fehlt")
    if not saw_sos:
        raise JpegValidationError("JPEG-Scan oder EOI fehlt")
    if not jfif:
        raise JpegValidationError("JFIF-APP0-Marker fehlt")
    if quantization_tables != {0, 1}:
        raise JpegValidationError("Quantisierungstabellen 0 und 1 sind erforderlich")
    if huffman_tables != set(STANDARD_HUFFMAN_TABLE_SHA256):
        raise JpegValidationError("Die vier Standard-Huffmantabellen sind erforderlich")

    precision, width, height, components = sof
    if (width, height) != (320, 320):
        raise JpegValidationError(
            f"JPEG-Geometrie muss 320x320 sein, ist aber {width}x{height}"
        )
    if precision != 8:
        raise JpegValidationError(f"JPEG-Präzision muss 8 Bit sein, ist aber {precision}")
    if len(components) != 3:
        raise JpegValidationError(
            f"JPEG muss 3 Komponenten besitzen, hat aber {len(components)}"
        )

    component_shape = tuple(
        (
            component.identifier,
            component.horizontal_sampling,
            component.vertical_sampling,
            component.quantization_table,
        )
        for component in components
    )
    if component_shape != ((1, 2, 2, 0), (2, 1, 1, 1), (3, 1, 1, 1)):
        raise JpegValidationError(
            "Erforderlich ist JFIF-YCbCr 4:2:0 mit Y=2x2 und Cb/Cr=1x1"
        )

    return JpegInfo(
        length=len(data),
        width=width,
        height=height,
        precision=precision,
        sof_marker=SOF0,
        components=components,
        jfif=jfif,
        segment_count=count,
        padding_length=count * PAYLOAD_BYTES - len(data),
    )


def build_segments(
    jpeg: bytes, *, max_segments: int = MAX_SEGMENTS
) -> tuple[TransferSegment, ...]:
    """Build all wire reports and hidraw buffers without device access."""
    count = segment_count(len(jpeg), max_segments=max_segments)
    segments: list[TransferSegment] = []
    for index in range(count):
        control = (
            bytes((COMMAND, count & 0xFF, 0x00, 0x80))
            if index == 0
            else bytes((COMMAND, index & 0xFF, 0x00, 0x00))
        )
        chunk = jpeg[index * PAYLOAD_BYTES : (index + 1) * PAYLOAD_BYTES]
        payload = chunk + bytes(PAYLOAD_BYTES - len(chunk))
        wire_report = control + payload
        hidraw_buffer = b"\x00" + wire_report
        segments.append(
            TransferSegment(
                index=index,
                control=control,
                payload=payload,
                wire_report=wire_report,
                hidraw_buffer=hidraw_buffer,
            )
        )

    result = tuple(segments)
    validate_transfer_invariants(jpeg, result, max_segments=max_segments)
    return result


def validate_transfer_invariants(
    jpeg: bytes,
    segments: Sequence[TransferSegment],
    *,
    max_segments: int = MAX_SEGMENTS,
) -> None:
    if COMMAND != 0x08:
        raise RuntimeError("Nur Command 0x08 ist zulässig")
    if (
        len(segments) != segment_count(len(jpeg), max_segments=max_segments)
        or len(segments) > max_segments
    ):
        raise RuntimeError("Ungültige Segmentanzahl")

    reconstructed = bytearray()
    for expected_index, segment in enumerate(segments):
        expected_control = (
            bytes((0x08, len(segments), 0x00, 0x80))
            if expected_index == 0
            else bytes((0x08, expected_index, 0x00, 0x00))
        )
        if segment.index != expected_index or segment.control != expected_control:
            raise RuntimeError("Ungültige Controlbytes oder Segmentreihenfolge")
        if len(segment.payload) != PAYLOAD_BYTES:
            raise RuntimeError("Ungültige Payloadlänge")
        if len(segment.wire_report) != WIRE_REPORT_BYTES:
            raise RuntimeError("Drahtreport muss exakt 1024 Byte besitzen")
        if len(segment.hidraw_buffer) != HIDRAW_WRITE_BYTES:
            raise RuntimeError("hidraw-Puffer muss exakt 1025 Byte besitzen")
        if segment.hidraw_buffer != b"\x00" + segment.wire_report:
            raise RuntimeError("Ungültiges Linux-hidraw-Framing")
        reconstructed.extend(segment.payload)

    if bytes(reconstructed[: len(jpeg)]) != jpeg:
        raise RuntimeError("JPEG wurde bei der Paketbildung verändert")
    if any(reconstructed[len(jpeg) :]):
        raise RuntimeError("Letzter Payload enthält Nonzero-Padding")


def device_validation_error(device: HidrawInterface) -> str | None:
    if device.vendor_id != TARGET_VID or device.product_id != TARGET_PID:
        return "VID/PID weichen ab"
    if device.interface_number != TARGET_INTERFACE:
        return "es ist nicht USB-Interface 1"
    if device.input_report_bytes != EXPECTED_INPUT_REPORT_BYTES:
        return "Input-Reportgröße ist nicht 16 Byte"
    if device.output_report_bytes != WIRE_REPORT_BYTES:
        return "Output-Reportgröße ist nicht 1024 Drahtbyte"
    if device.report_ids:
        return "der HID-Report ist nicht unnumbered"
    device_path = Path(device.device_path)
    if (
        not device_path.is_absolute()
        or device_path.parent != Path("/dev")
        or not device_path.name.startswith("hidraw")
    ):
        return "der dynamisch ermittelte hidraw-Pfad ist ungültig"
    return None


def discover_lcd_interface() -> tuple[HidrawInterface | None, str]:
    matches = [
        device
        for device in discover(TARGET_VID, TARGET_PID, include_udev=False)
        if device.interface_number == TARGET_INTERFACE
    ]
    if len(matches) != 1:
        return None, f"Interface 1 nicht eindeutig gefunden (Treffer: {len(matches)})"
    error = device_validation_error(matches[0])
    if error is not None:
        return None, error
    return matches[0], "gültig"


def _sysfs_device_number(device: HidrawInterface) -> int:
    major_text, separator, minor_text = (
        Path(device.sysfs_path) / "dev"
    ).read_text(encoding="ascii").strip().partition(":")
    if separator != ":":
        raise ValueError("ungültige sysfs-Gerätenummer")
    return os.makedev(int(major_text), int(minor_text))


def validate_open_target(fd: int, expected: HidrawInterface) -> None:
    """Revalidate identity and framing immediately before every write."""
    expected_error = device_validation_error(expected)
    if expected_error is not None:
        raise RuntimeError(expected_error)

    opened_stat = os.fstat(fd)
    if not stat.S_ISCHR(opened_stat.st_mode):
        raise RuntimeError("geöffnetes Ziel ist kein Zeichengerät")
    if opened_stat.st_rdev != _sysfs_device_number(expected):
        raise RuntimeError("Geräteknoten und sysfs-Eintrag stimmen nicht überein")

    current_matches = [
        device
        for device in discover(TARGET_VID, TARGET_PID, include_udev=False)
        if device.interface_number == TARGET_INTERFACE
        and device.device_path == expected.device_path
        and device.sysfs_path == expected.sysfs_path
        and device_validation_error(device) is None
    ]
    if len(current_matches) != 1:
        raise RuntimeError("Ziel oder HID-Reportstruktur hat sich verändert")


def load_jpeg(path: Path, *, max_segments: int = MAX_SEGMENTS) -> bytes:
    """Read one stable regular file within the configured transport bound."""
    try:
        file_status = path.stat()
    except OSError as error:
        raise JpegValidationError(f"JPEG kann nicht geprüft werden: {error}") from error
    if not stat.S_ISREG(file_status.st_mode):
        raise JpegValidationError("JPEG-Eingabe muss eine reguläre Datei sein")
    file_size = file_status.st_size
    if file_size <= 0:
        raise JpegValidationError("JPEG-Länge muss größer als null sein")
    if file_size > max_segments * PAYLOAD_BYTES:
        count = (file_size + PAYLOAD_BYTES - 1) // PAYLOAD_BYTES
        raise JpegValidationError(
            f"JPEG würde N={count} benötigen; maximal zulässig ist N={max_segments}"
        )
    try:
        data = path.read_bytes()
    except OSError as error:
        raise JpegValidationError(f"JPEG kann nicht gelesen werden: {error}") from error
    if len(data) != file_size:
        raise JpegValidationError("JPEG-Datei änderte sich während des Lesens")
    return data


def send_frame_once(device: HidrawInterface, jpeg: bytes) -> int:
    """Synchronously send exactly one validated frame, without retry or reads.

    Returns the number of successful writes. Any failure raises immediately;
    the descriptor is closed by the function's finally block.
    """
    validate_jpeg(jpeg)
    segments = build_segments(jpeg)
    error = device_validation_error(device)
    if error is not None:
        raise LcdTransportError(error)
    if not os.access(device.device_path, os.W_OK):
        raise PermissionError(
            "Keine Schreibberechtigung; Rechte wurden nicht verändert"
        )

    flags = os.O_WRONLY | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(device.device_path, flags)

    completed = 0
    try:
        for segment in segments:
            validate_open_target(fd, device)
            validate_transfer_invariants(jpeg, segments)
            try:
                written = os.write(fd, segment.hidraw_buffer)
            except PermissionError:
                raise
            except OSError as error:
                raise LcdTransportError(
                    f"Write für Segment {segment.index} fehlgeschlagen: {error}"
                ) from error
            if written != HIDRAW_WRITE_BYTES:
                raise LcdTransportError(
                    f"Short Write bei Segment {segment.index}: "
                    f"{written} statt {HIDRAW_WRITE_BYTES} Byte; kein Nachsenden"
                )
            completed += 1
        return completed
    finally:
        os.close(fd)
