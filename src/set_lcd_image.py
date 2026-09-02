#!/usr/bin/env python3
"""Preview or apply one already compatible JPEG to the ASUS AIO LCD."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Sequence

import lcd_transport as transport

EXIT_SUCCESS = 0
EXIT_INPUT = 1
EXIT_DEVICE_SELECTION = 2
EXIT_PERMISSION = 3
EXIT_IO_ERROR = 4


def _print_preview(
    path: Path,
    digest: str,
    info: transport.JpegInfo,
    device: transport.HidrawInterface | None,
    device_status: str,
) -> None:
    print("Preview des einzelnen LCD-Bildtransfers:")
    print(f"  Datei:                 {path}")
    print(f"  SHA-256:               {digest}")
    print(f"  JPEG-Länge:            {info.length} Byte")
    print(f"  Geometrie:             {info.width}x{info.height}")
    print(f"  JPEG-Profil:           SOF0/Baseline, {info.precision} Bit")
    print("  Farbdarstellung:       JFIF-YCbCr 4:2:0")
    print(f"  Segmentzahl:           {info.segment_count}")
    print(f"  Padding:               {info.padding_length} Byte, ausschließlich 00")
    if device is None:
        print(f"  Zielgerät:             nicht verwendbar ({device_status})")
    else:
        print(f"  Zielgerät:             {device.device_path}")
        print(
            f"  USB-ID/Interface:      {device.vendor_id}:{device.product_id} / "
            f"{device.interface_number}"
        )
    print(f"  Geplante Writes:       {info.segment_count}, kein Retry")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Validiert und zeigt standardmäßig nur die Vorschau genau eines "
            "bereits passenden 320x320-JPEGs."
        ),
    )
    parser.add_argument("jpeg", type=Path, help="explizite JPEG-Datei")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="genau dieses eine validierte Bild einmalig übertragen",
    )
    args = parser.parse_args(argv)

    path = args.jpeg.expanduser().resolve()
    try:
        jpeg = transport.load_jpeg(path)
        info = transport.validate_jpeg(jpeg)
        transport.build_segments(jpeg)
    except (transport.JpegValidationError, RuntimeError, ValueError) as error:
        print(f"FEHLER: JPEG-/Paketprüfung fehlgeschlagen: {error}", file=sys.stderr)
        return EXIT_INPUT

    device, device_status = transport.discover_lcd_interface()
    _print_preview(
        path,
        hashlib.sha256(jpeg).hexdigest(),
        info,
        device,
        device_status,
    )

    if not args.apply:
        print("PREVIEW: Das hidraw-Gerät wurde nicht geöffnet; es wurde nichts gesendet.")
        return EXIT_SUCCESS
    if device is None:
        print(f"FEHLER: Zielgerät nicht sicher auswählbar: {device_status}", file=sys.stderr)
        return EXIT_DEVICE_SELECTION

    try:
        written = transport.send_frame_once(device, jpeg)
    except PermissionError as error:
        print(f"FEHLER: Schreibberechtigung verweigert: {error}", file=sys.stderr)
        return EXIT_PERMISSION
    except (transport.LcdTransportError, OSError, RuntimeError) as error:
        print(f"FEHLER: Einmaltransfer abgebrochen: {error}", file=sys.stderr)
        return EXIT_IO_ERROR

    print(
        f"ERFOLG: Ein Frame mit genau {written} Writes übertragen; "
        "kein Read, Retry oder zweiter Frame."
    )
    return EXIT_SUCCESS


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nABBRUCH: Kein Retry und keine automatische Recovery.", file=sys.stderr)
        raise SystemExit(EXIT_IO_ERROR)
