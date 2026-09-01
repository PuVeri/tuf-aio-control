#!/usr/bin/env python3
"""One-shot, explicitly armed test for the statically analysed command 0x87."""

from __future__ import annotations

import argparse
import os
import select
import stat
import sys
import time
from pathlib import Path

from discover_device import HidrawInterface, discover

TARGET_VID = "0b05"
TARGET_PID = "1c7b"
TARGET_INTERFACE = 0
PRE_WRITE_QUIET_SECONDS = 5.0
RESPONSE_TIMEOUT_SECONDS = 3.0

COMMAND = 0x87
FORBIDDEN_COMMANDS = frozenset({0x08, 0x02, 0x09, 0x1F, 0x45, 0x86, 0x88, 0xFF})

WIRE_REQUEST = bytes((COMMAND, 0x01, 0x00, 0x80)) + bytes(436)
HIDRAW_REQUEST = b"\x00" + WIRE_REQUEST
RESPONSE_HEADER = bytes((COMMAND, 0x01, 0x00, 0x80))
RESPONSE_PADDING = bytes(434)
V51_REFERENCE_RESPONSE = RESPONSE_HEADER + bytes((0x51, 0x00)) + RESPONSE_PADDING

EXIT_SUCCESS = 0
EXIT_DEVICE_SELECTION = 1
EXIT_PERMISSION = 2
EXIT_TIMEOUT = 3
EXIT_UNEXPECTED_RESPONSE = 4
EXIT_IO_ERROR = 5
EXIT_SAFETY_INVARIANT = 6
EXIT_PRE_WRITE_REPORT = 7


class PreWriteReportError(Exception):
    """Carry a pre-write report until after the device has been closed."""

    def __init__(self, response: bytes, phase: str) -> None:
        super().__init__("HID-Report vor dem Write")
        self.response = response
        self.phase = phase


class UnexpectedResponseError(Exception):
    """Carry an unexpected response until after the device has been closed."""

    def __init__(self, response: bytes) -> None:
        super().__init__("unerwartete HID-Antwort")
        self.response = response


def _validate_safety_invariants() -> None:
    """Refuse to run if any fixed protocol or framing invariant has changed."""
    if COMMAND != 0x87 or COMMAND in FORBIDDEN_COMMANDS:
        raise RuntimeError("Nur Befehl 0x87 ist zulässig")
    if PRE_WRITE_QUIET_SECONDS != 5.0:
        raise RuntimeError("Die feste Pre-Write-Ruhephase muss 5 Sekunden dauern")
    if HIDRAW_REQUEST != b"\x00\x87\x01\x00\x80" + bytes(436):
        raise RuntimeError("Der feste 441-Byte-Request ist ungültig")
    if len(HIDRAW_REQUEST) != 441 or len(WIRE_REQUEST) != 440:
        raise RuntimeError("Die feste Request-Länge ist ungültig")
    if RESPONSE_HEADER != b"\x87\x01\x00\x80" or RESPONSE_PADDING != bytes(434):
        raise RuntimeError("Die feste Antwortstruktur ist ungültig")
    if V51_REFERENCE_RESPONSE != b"\x87\x01\x00\x80\x51\x00" + bytes(434):
        raise RuntimeError("Die feste v51-Referenzantwort ist ungültig")
    if len(V51_REFERENCE_RESPONSE) != 440:
        raise RuntimeError("Die feste Antwortlänge ist ungültig")


def _select_target() -> HidrawInterface | None:
    matches = [
        device
        for device in discover(TARGET_VID, TARGET_PID)
        if device.interface_number == TARGET_INTERFACE
    ]
    if len(matches) != 1:
        print(
            "FEHLER: Interface 0 für 0b05:1c7b wurde nicht eindeutig gefunden "
            f"(Treffer: {len(matches)}).",
            file=sys.stderr,
        )
        return None

    device = matches[0]
    if (
        device.vendor_id != TARGET_VID
        or device.product_id != TARGET_PID
        or device.interface_number != TARGET_INTERFACE
        or device.input_report_bytes != 440
        or device.output_report_bytes != 440
        or device.report_ids
    ):
        print(
            "FEHLER: Gerätekennung oder HID-Reportstruktur entspricht nicht "
            "den festen Sicherheitsvorgaben.",
            file=sys.stderr,
        )
        return None

    device_path = Path(device.device_path)
    if (
        not device_path.is_absolute()
        or device_path.parent != Path("/dev")
        or not device_path.name.startswith("hidraw")
    ):
        print("FEHLER: Der dynamisch ermittelte Gerätepfad ist ungültig.", file=sys.stderr)
        return None
    return device


def _print_plan(device: HidrawInterface) -> None:
    print("Geplante einmalige 0x87-Transaktion:")
    print(f"  Ziel:             {device.device_path}")
    print(f"  USB-ID:           {device.vendor_id}:{device.product_id}")
    print(f"  USB-Interface:    {device.interface_number}")
    print("  hidraw-Request:   441 Byte = 00 | 87 01 00 80 | 436 x 00")
    print("  USB-Drahtreport:  440 Byte = 87 01 00 80 | 436 x 00")
    print("  Antwortstruktur:  440 Byte = 87 01 00 80 VV VV | 434 x 00")
    print("  v51-Referenz:     Versionswert 0x0051")
    print("  Ruhephase:        5 Sekunden rein lesend; Abbruch bei jedem Report")
    print("  Antwortdeadline:  maximal 3 Sekunden")
    print("  Schreibversuche:  exakt einer, keine Wiederholung")


def _print_hexdump(response: bytes) -> None:
    """Print all received bytes without persisting them."""
    for offset in range(0, len(response), 16):
        chunk = response[offset : offset + 16]
        print(f"  {offset:04x}: {chunk.hex(' ')}", file=sys.stderr)


def _print_pre_write_report(error: PreWriteReportError) -> None:
    """Print a report that caused a guaranteed pre-write abort."""
    print(
        f"ABBRUCH VOR WRITE: {error.phase}; "
        f"Reportlänge {len(error.response)} Byte.",
        file=sys.stderr,
    )
    print("Vollständiger Hexdump des wartenden Reports:", file=sys.stderr)
    _print_hexdump(error.response)
    print("Es wurde nichts an das HID-Gerät gesendet.", file=sys.stderr)


def _print_unexpected_response(response: bytes) -> None:
    """Print the complete response and every difference without persisting it."""
    print(
        "FEHLER: Strukturell ungültige 0x87-Antwort "
        f"(Länge {len(response)} statt 440, falscher Header oder Nonzero-Padding).",
        file=sys.stderr,
    )
    print("Vollständiger Hexdump der empfangenen Antwort:", file=sys.stderr)
    _print_hexdump(response)

    print("Abweichende Bytepositionen gegenüber der v51-Referenz:", file=sys.stderr)
    for offset in range(max(len(response), len(V51_REFERENCE_RESPONSE))):
        actual = response[offset] if offset < len(response) else None
        expected = (
            V51_REFERENCE_RESPONSE[offset]
            if offset < len(V51_REFERENCE_RESPONSE)
            else None
        )
        if actual == expected:
            continue
        actual_text = f"{actual:02x}" if actual is not None else "<fehlend>"
        expected_text = f"{expected:02x}" if expected is not None else "<nicht erwartet>"
        print(
            f"  Offset 0x{offset:04x}: erwartet={expected_text}, "
            f"empfangen={actual_text}",
            file=sys.stderr,
        )


def _sysfs_device_number(device: HidrawInterface) -> int:
    major_text, separator, minor_text = (
        Path(device.sysfs_path) / "dev"
    ).read_text(encoding="ascii").strip().partition(":")
    if separator != ":":
        raise ValueError("ungültige sysfs-Gerätenummer")
    return os.makedev(int(major_text), int(minor_text))


def _validate_open_target(fd: int, expected: HidrawInterface) -> None:
    """Revalidate the opened character device against sysfs after opening it."""
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
        and device.input_report_bytes == 440
        and device.output_report_bytes == 440
        and not device.report_ids
    ]
    if len(current_matches) != 1:
        raise RuntimeError("Gerät hat sich zwischen Erkennung und Öffnen geändert")


def _read_report_if_ready(fd: int, timeout: float) -> bytes | None:
    """Wait read-only for one input report and never write to the descriptor."""
    readable, _, exceptional = select.select([fd], [], [fd], timeout)
    if exceptional:
        raise OSError("das HID-Gerät meldete einen Ausnahmezustand")
    if not readable:
        return None

    response = os.read(fd, len(V51_REFERENCE_RESPONSE))
    if not response:
        raise OSError("Gerät getrennt oder Eingabestrom beendet")
    return response


def _response_version_value(response: bytes) -> int | None:
    """Return the little-endian version value for a structurally valid reply."""
    if len(response) != len(V51_REFERENCE_RESPONSE):
        return None
    if response[:4] != RESPONSE_HEADER or response[6:] != RESPONSE_PADDING:
        return None
    return int.from_bytes(response[4:6], "little")


def _run_once(device: HidrawInterface) -> int:
    if not os.access(device.device_path, os.R_OK | os.W_OK):
        print(
            "FEHLER: Keine Lese- und Schreibberechtigung; Rechte wurden nicht verändert.",
            file=sys.stderr,
        )
        return EXIT_PERMISSION

    flags = os.O_RDWR | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)

    print(f"Schritt 1/5: Öffne {device.device_path} mit O_RDWR | O_NONBLOCK.")
    try:
        fd = os.open(device.device_path, flags)
    except PermissionError as error:
        print(f"FEHLER: Berechtigung verweigert: {error}", file=sys.stderr)
        return EXIT_PERMISSION
    except OSError as error:
        print(f"FEHLER: Gerät konnte nicht geöffnet werden: {error}", file=sys.stderr)
        return EXIT_IO_ERROR

    try:
        print("Schritt 2/5: Prüfe Identität, Interface und Reportgrößen erneut.")
        try:
            _validate_open_target(fd, device)
        except (OSError, ValueError, RuntimeError) as error:
            print(f"FEHLER: Sicherheitsprüfung fehlgeschlagen: {error}", file=sys.stderr)
            return EXIT_SAFETY_INVARIANT

        print("Schritt 3/5: Beobachte die Inputqueue 5 Sekunden rein lesend.")
        try:
            pre_write_report = _read_report_if_ready(fd, PRE_WRITE_QUIET_SECONDS)
        except (OSError, ValueError) as error:
            print(f"FEHLER: Rein lesende Ruhephase fehlgeschlagen: {error}", file=sys.stderr)
            return EXIT_IO_ERROR
        if pre_write_report is not None:
            raise PreWriteReportError(
                pre_write_report,
                "Report während der fünfsekündigen Ruhephase empfangen",
            )

        print(
            "Schritt 4/5: Prüfe die Inputqueue unmittelbar; "
            "nur bei leerer Queue folgt der einmalige Write."
        )
        try:
            pre_write_report = _read_report_if_ready(fd, 0.0)
        except (OSError, ValueError) as error:
            print(f"FEHLER: Unmittelbare Queueprüfung fehlgeschlagen: {error}", file=sys.stderr)
            return EXIT_IO_ERROR
        if pre_write_report is not None:
            raise PreWriteReportError(
                pre_write_report,
                "Report bei der unmittelbaren Pre-Write-Prüfung empfangen",
            )

        try:
            written = os.write(fd, HIDRAW_REQUEST)
        except PermissionError as error:
            print(f"FEHLER: Schreibberechtigung verweigert: {error}", file=sys.stderr)
            return EXIT_PERMISSION
        except OSError as error:
            print(f"FEHLER: Einmaliger Write fehlgeschlagen: {error}", file=sys.stderr)
            return EXIT_IO_ERROR
        if written != len(HIDRAW_REQUEST):
            print(
                f"FEHLER: Partieller Write ({written} von 441 Byte); kein Nachsenden.",
                file=sys.stderr,
            )
            return EXIT_IO_ERROR

        response_deadline = time.monotonic() + RESPONSE_TIMEOUT_SECONDS
        print("Schritt 5/5: Warte maximal 3 Sekunden auf genau eine Antwort.")
        try:
            remaining = max(0.0, response_deadline - time.monotonic())
            readable, _, exceptional = select.select(
                [fd], [], [fd], remaining
            )
        except (OSError, ValueError) as error:
            print(f"FEHLER: Warten auf Antwort fehlgeschlagen: {error}", file=sys.stderr)
            return EXIT_IO_ERROR
        if exceptional:
            print("FEHLER: Das HID-Gerät meldete einen Ausnahmezustand.", file=sys.stderr)
            return EXIT_IO_ERROR
        if not readable:
            print("FEHLER: Timeout nach maximal 3 Sekunden.", file=sys.stderr)
            return EXIT_TIMEOUT

        try:
            response = os.read(fd, len(V51_REFERENCE_RESPONSE))
        except PermissionError as error:
            print(f"FEHLER: Leseberechtigung verweigert: {error}", file=sys.stderr)
            return EXIT_PERMISSION
        except OSError as error:
            print(f"FEHLER: Antwort konnte nicht gelesen werden: {error}", file=sys.stderr)
            return EXIT_IO_ERROR

        if not response:
            print("FEHLER: Gerät getrennt oder Eingabestrom beendet.", file=sys.stderr)
            return EXIT_IO_ERROR
        version_value = _response_version_value(response)
        if version_value is None:
            raise UnexpectedResponseError(response)

        print(
            "ERFOLG: Strukturell korrekte 440-Byte-0x87-Antwort empfangen; "
            f"Versionswert=0x{version_value:04x}."
        )
        return EXIT_SUCCESS
    finally:
        try:
            os.close(fd)
        except OSError as error:
            print(f"WARNUNG: Fehler beim Schließen des Deskriptors: {error}", file=sys.stderr)
            print("Keine weiteren Befehle werden gesendet.")
        else:
            print("Gerätedeskriptor geschlossen; keine weiteren Befehle gesendet.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Stark abgesicherter Einmaltest für Befehl 0x87. Ohne explizite "
            "Risikobestätigung wird kein HID-Gerät geöffnet."
        )
    )
    parser.add_argument(
        "--i-understand-the-risk",
        action="store_true",
        help="den einmaligen echten HID-Test ausdrücklich freigeben",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ziel und Paket anzeigen, das HID-Gerät aber nicht öffnen",
    )
    args = parser.parse_args()

    try:
        _validate_safety_invariants()
    except RuntimeError as error:
        print(f"FEHLER: Interne Sicherheitsinvariante verletzt: {error}", file=sys.stderr)
        return EXIT_SAFETY_INVARIANT

    print("Schritt 0/5: Suche 0b05:1c7b dynamisch und verlange USB-Interface 0.")
    device = _select_target()
    if device is None:
        return EXIT_DEVICE_SELECTION
    _print_plan(device)

    if args.dry_run:
        print("DRY-RUN: Das HID-Gerät wurde nicht geöffnet; es wurde nichts gesendet.")
        return EXIT_SUCCESS
    if not args.i_understand_the_risk:
        print(
            "NICHT AUSGEFÜHRT: Für den echten Test ist "
            "--i-understand-the-risk erforderlich."
        )
        print("Das HID-Gerät wurde nicht geöffnet; es wurde nichts gesendet.")
        return EXIT_SUCCESS

    print("RISIKO BESTÄTIGT: Der einmalige echte HID-Test beginnt jetzt.")
    try:
        return _run_once(device)
    except PreWriteReportError as error:
        _print_pre_write_report(error)
        return EXIT_PRE_WRITE_REPORT
    except UnexpectedResponseError as error:
        _print_unexpected_response(error.response)
        return EXIT_UNEXPECTED_RESPONSE


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nABBRUCH: Benutzerabbruch; keine automatische Recovery.", file=sys.stderr)
        raise SystemExit(EXIT_IO_ERROR)
