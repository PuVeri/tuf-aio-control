#!/usr/bin/env python3
"""Conservative preview or one explicitly armed ASUS LCD JPEG safety test."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Sequence

import lcd_transport as transport

os = transport.os

HidrawInterface = transport.HidrawInterface
JpegValidationError = transport.JpegValidationError
JpegInfo = transport.JpegInfo
TransferSegment = transport.TransferSegment

PAYLOAD_BYTES = transport.PAYLOAD_BYTES
HIDRAW_WRITE_BYTES = transport.HIDRAW_WRITE_BYTES
MAX_SEGMENTS = 4
MAX_JPEG_BYTES = MAX_SEGMENTS * PAYLOAD_BYTES

EXIT_SUCCESS = 0
EXIT_INPUT = 1
EXIT_DEVICE_SELECTION = 2
EXIT_PERMISSION = 3
EXIT_IO_ERROR = 4
EXIT_SAFETY_INVARIANT = 5


def segment_count(jpeg_length: int) -> int:
    return transport.segment_count(jpeg_length, max_segments=MAX_SEGMENTS)


def validate_jpeg(data: bytes) -> JpegInfo:
    return transport.validate_jpeg(data, max_segments=MAX_SEGMENTS)


def build_transfer_segments(jpeg: bytes) -> tuple[TransferSegment, ...]:
    return transport.build_segments(jpeg, max_segments=MAX_SEGMENTS)


def _validate_transfer_invariants(
    jpeg: bytes, segments: Sequence[TransferSegment]
) -> None:
    transport.validate_transfer_invariants(
        jpeg, segments, max_segments=MAX_SEGMENTS
    )


def _device_validation_error(device: HidrawInterface) -> str | None:
    return transport.device_validation_error(device)


def _select_target() -> tuple[HidrawInterface | None, str]:
    return transport.discover_lcd_interface()


def _print_preview(
    jpeg_path: Path,
    digest: str,
    info: JpegInfo,
    segments: Sequence[TransferSegment],
    device: HidrawInterface | None,
    device_status: str,
) -> None:
    print("Preview des einmaligen 0x08-JPEG-Transfers:")
    print(f"  JPEG-Pfad:             {jpeg_path}")
    print(f"  SHA-256:               {digest}")
    print(f"  JPEG-Länge:            {info.length} Byte")
    print(f"  Geometrie:             {info.width}x{info.height}")
    print(f"  SOF-Typ:               SOF0 / FF C0, {info.precision} Bit")
    print(f"  Komponenten:           {len(info.components)} (JFIF-YCbCr 4:2:0)")
    print(f"  N:                     {info.segment_count}")
    print(f"  Paddinglänge:          {info.padding_length} Byte, ausschließlich 00")
    for segment in segments:
        print(f"  Segment {segment.index} Control: {segment.control.hex(' ')}")
    if device is None:
        print(f"  Zielgerät:             nicht verwendbar ({device_status})")
    else:
        print(f"  Zielgerät:             {device.device_path}")
        print(f"  USB-ID/Interface:      {device.vendor_id}:{device.product_id} / 1")
        print("  HID-Report:            unnumbered, 1024 Byte OUT auf dem Draht")
        print("  Linux-hidraw-Framing:  00 || 1024 Byte = 1025 Byte")
    print(f"  Geplante Writes:       {len(segments)}, kein Retry")


def _run_once(
    device: HidrawInterface,
    jpeg: bytes,
    segments: Sequence[TransferSegment],
) -> int:
    try:
        validate_jpeg(jpeg)
        _validate_transfer_invariants(jpeg, segments)
        written = transport.send_frame_once(device, jpeg)
    except PermissionError as error:
        print(f"FEHLER: Schreibberechtigung verweigert: {error}", file=sys.stderr)
        return EXIT_PERMISSION
    except transport.LcdTransportError as error:
        print(f"FEHLER: Transfer abgebrochen: {error}", file=sys.stderr)
        return EXIT_IO_ERROR
    except (OSError, ValueError, RuntimeError) as error:
        print(f"FEHLER: Sicherheitsprüfung fehlgeschlagen: {error}", file=sys.stderr)
        return EXIT_SAFETY_INVARIANT

    print(
        f"ERFOLG: Genau {written} Segmente einmalig geschrieben; "
        "kein Read, Retry oder Folgekommando."
    )
    print("Gerätedeskriptor geschlossen; kein zweiter Frame.")
    return EXIT_SUCCESS


def _load_jpeg(path: Path) -> bytes:
    return transport.load_jpeg(path, max_segments=MAX_SEGMENTS)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Standardmäßig rein offline/vorschauend: validiert genau ein JPEG "
            "und baut den auf N<=4 begrenzten ASUS-0x08-Safety-Test."
        ),
    )
    parser.add_argument("jpeg", type=Path, help="explizit zu prüfende JPEG-Datei")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="nur Preview; das hidraw-Gerät niemals öffnen",
    )
    parser.add_argument(
        "--i-understand-the-risk",
        action="store_true",
        help="den konservativen Einmaltransfer ausdrücklich starten",
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.i_understand_the_risk:
        parser.error("--dry-run und --i-understand-the-risk schließen sich aus")

    jpeg_path = args.jpeg.expanduser().resolve()
    try:
        jpeg = _load_jpeg(jpeg_path)
        info = validate_jpeg(jpeg)
        segments = build_transfer_segments(jpeg)
    except (JpegValidationError, RuntimeError) as error:
        print(f"FEHLER: JPEG-/Paketprüfung fehlgeschlagen: {error}", file=sys.stderr)
        return EXIT_INPUT

    device, device_status = _select_target()
    _print_preview(
        jpeg_path,
        hashlib.sha256(jpeg).hexdigest(),
        info,
        segments,
        device,
        device_status,
    )

    if args.dry_run or not args.i_understand_the_risk:
        print("DRY-RUN: Das hidraw-Gerät wurde nicht geöffnet; es wurde nichts gesendet.")
        return EXIT_SUCCESS
    if device is None:
        print(f"FEHLER: Zielgerät nicht sicher auswählbar: {device_status}", file=sys.stderr)
        return EXIT_DEVICE_SELECTION

    print("RISIKO BESTÄTIGT: Der einmalige 0x08-Transfer beginnt jetzt.")
    return _run_once(device, jpeg, segments)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nABBRUCH: Kein Retry und keine automatische Recovery.", file=sys.stderr)
        raise SystemExit(EXIT_IO_ERROR)
