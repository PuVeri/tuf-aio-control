#!/usr/bin/env python3
"""Preview or explicitly run the fixed five-frame ASUS LCD refresh test."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

import lcd_refresh
import lcd_transport
from discover_device import HidrawInterface, UsbEndpoint

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"

EXPECTED_BCD_DEVICE = 0x0049
EXPECTED_BCD_DEVICE_DISPLAY = "0.49"
EXPECTED_MANUFACTURER = "ASUS Tek"
EXPECTED_PRODUCT = "TUF GAMING LC III 360 ARGB LCD"
EXPECTED_USAGE_PAGE = 0xFF06
EXPECTED_USAGE = 0x01
EXPECTED_SEGMENTS = 3
EXPECTED_WRITES = 15
EXPECTED_ENDPOINTS = (
    UsbEndpoint(address=0x03, attributes=0x03, max_packet_size=1024, interval=1),
    UsbEndpoint(address=0x84, attributes=0x03, max_packet_size=16, interval=1),
)

EXIT_SUCCESS = 0
EXIT_PREFLIGHT = 2
EXIT_PERMISSION = 3
EXIT_TRANSFER = 4
EXIT_SAFETY = 5


@dataclass(frozen=True)
class PreparedRefreshTest:
    device: HidrawInterface
    jpeg: bytes
    plan: lcd_refresh.RefreshPlan
    frame_reports: tuple[tuple[lcd_transport.TransferSegment, ...], ...]


def parse_bcd_device(value: str | None) -> int | None:
    """Normalize sysfs raw and human-readable BCD representations."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized.startswith("0x"):
        normalized = normalized[2:]
    if len(normalized) == 4 and all(
        character in "0123456789" for character in normalized
    ):
        return int(normalized, 16)
    major, separator, minor = normalized.partition(".")
    if (
        separator == "."
        and 1 <= len(major) <= 2
        and len(minor) == 2
        and all(character in "0123456789" for character in major)
        and all(character in "0123456789" for character in minor)
    ):
        return (int(major, 16) << 8) | int(minor, 16)
    return None


def strict_device_error(device: HidrawInterface) -> str | None:
    """Validate every known read-only identity, HID and USB-interface field."""
    error = lcd_transport.device_validation_error(device)
    if error is not None:
        return error
    if (
        device.manufacturer is not None
        and device.manufacturer != EXPECTED_MANUFACTURER
    ):
        return f"Hersteller weicht ab: {device.manufacturer!r}"
    if device.product is not None and device.product != EXPECTED_PRODUCT:
        return f"Produkt weicht ab: {device.product!r}"
    bcd_device = parse_bcd_device(device.bcd_device)
    if bcd_device is None:
        return f"bcdDevice ist ungültig formatiert: {device.bcd_device!r}"
    if bcd_device != EXPECTED_BCD_DEVICE:
        return (
            f"bcdDevice muss 0x{EXPECTED_BCD_DEVICE:04x} "
            f"({EXPECTED_BCD_DEVICE_DISPLAY}) sein, ist 0x{bcd_device:04x}"
        )
    if device.usage_page != EXPECTED_USAGE_PAGE or device.usage != EXPECTED_USAGE:
        return (
            "HID Usage Page/Usage müssen "
            f"0x{EXPECTED_USAGE_PAGE:04x}/0x{EXPECTED_USAGE:02x} sein"
        )
    if device.alternate_setting != 0:
        return "bAlternateSetting muss 0 sein"
    if (
        device.interface_class,
        device.interface_subclass,
        device.interface_protocol,
    ) != (3, 0, 0):
        return "USB-Interfaceklasse muss HID 03/00/00 sein"
    if device.endpoint_count != 2:
        return "Interface 1 muss genau zwei Endpoints besitzen"
    endpoint_signature = tuple(
        sorted(
            (
                endpoint.address,
                endpoint.attributes,
                endpoint.max_packet_size,
            )
            for endpoint in device.endpoints
        )
    )
    expected_signature = tuple(
        sorted(
            (
                endpoint.address,
                endpoint.attributes,
                endpoint.max_packet_size,
            )
            for endpoint in EXPECTED_ENDPOINTS
        )
    )
    if endpoint_signature != expected_signature:
        return "Endpointprofil muss 03 OUT/1024 und 84 IN/16, Interrupt sein"
    if any(endpoint.interval <= 0 for endpoint in device.endpoints):
        return "Endpointintervall muss in sysfs positiv ausgewiesen sein"
    return None


def _fd_open_mode(fdinfo: Path) -> int | None:
    try:
        lines = fdinfo.read_text(encoding="ascii", errors="replace").splitlines()
    except (FileNotFoundError, PermissionError, OSError):
        return None
    for line in lines:
        key, separator, value = line.partition(":")
        if key == "flags" and separator:
            try:
                return int(value.strip(), 8) & os.O_ACCMODE
            except ValueError:
                return None
    return None


def find_competing_writers(device: HidrawInterface) -> tuple[str, ...]:
    """Best-effort local /proc check scoped to this exact character device."""
    try:
        target = os.stat(device.device_path)
    except OSError as error:
        raise RuntimeError(f"Zielknoten kann nicht geprüft werden: {error}") from error
    if not stat.S_ISCHR(target.st_mode):
        raise RuntimeError("Zielknoten ist kein Zeichengerät")

    competitors: list[str] = []
    own_pid = os.getpid()
    try:
        processes = tuple(Path("/proc").iterdir())
    except OSError as error:
        raise RuntimeError(f"/proc kann nicht geprüft werden: {error}") from error
    for process in processes:
        if not process.name.isdecimal() or int(process.name) == own_pid:
            continue
        fd_root = process / "fd"
        try:
            descriptors = tuple(fd_root.iterdir())
        except (FileNotFoundError, PermissionError, OSError):
            continue
        for descriptor in descriptors:
            try:
                opened = os.stat(descriptor)
            except (FileNotFoundError, PermissionError, OSError):
                continue
            if not stat.S_ISCHR(opened.st_mode) or opened.st_rdev != target.st_rdev:
                continue
            mode = _fd_open_mode(process / "fdinfo" / descriptor.name)
            if mode == os.O_RDONLY:
                continue
            try:
                command = (process / "comm").read_text(
                    encoding="utf-8", errors="replace"
                ).strip()
            except (FileNotFoundError, PermissionError, OSError):
                command = "unbekannt"
            competitors.append(f"PID {process.name} ({command}), FD {descriptor.name}")
    return tuple(sorted(competitors))


def runtime_device_error(device: HidrawInterface) -> str | None:
    error = strict_device_error(device)
    if error is not None:
        return error
    try:
        competitors = find_competing_writers(device)
    except RuntimeError as error:
        return str(error)
    if competitors:
        return "Konkurrierender Writer erkannt: " + "; ".join(competitors)
    return None


def prepare_test(device: HidrawInterface) -> PreparedRefreshTest:
    """Finish all immutable JPEG/report/device gates before session start."""
    error = runtime_device_error(device)
    if error is not None:
        raise RuntimeError(error)
    jpeg = lcd_transport.load_jpeg(REFERENCE_PATH, max_segments=EXPECTED_SEGMENTS)
    plan = lcd_refresh.build_first_refresh_live_test_plan(jpeg)
    frame_reports = tuple(
        lcd_transport.build_segments(jpeg) for _ in range(plan.max_frames)
    )
    prepared = PreparedRefreshTest(device, jpeg, plan, frame_reports)
    validate_prepared_profile(prepared)
    return prepared


def validate_prepared_profile(prepared: PreparedRefreshTest) -> None:
    """Revalidate the complete immutable 5x3 transfer plan."""
    digest = hashlib.sha256(prepared.jpeg).hexdigest()
    if digest != lcd_refresh.FIRST_REFRESH_REFERENCE_SHA256:
        raise RuntimeError("Referenz-JPEG-Hash hat sich verändert")
    info = lcd_transport.validate_jpeg(
        prepared.jpeg, max_segments=EXPECTED_SEGMENTS
    )
    if info.segment_count != EXPECTED_SEGMENTS:
        raise RuntimeError(f"Referenzprofil muss N={EXPECTED_SEGMENTS} besitzen")
    if (
        prepared.plan.frames != (prepared.plan.frames[0],)
        or prepared.plan.frames[0].jpeg_bytes is not prepared.jpeg
        or prepared.plan.transport_interval_seconds
        != lcd_refresh.FIRST_REFRESH_INTERVAL_SECONDS
        or prepared.plan.max_duration_seconds
        != lcd_refresh.FIRST_REFRESH_MAX_DURATION_SECONDS
        or prepared.plan.max_frames != lcd_refresh.FIRST_REFRESH_MAX_FRAMES
    ):
        raise RuntimeError("Refreshplan weicht vom fixierten Ersttestprofil ab")
    if len(prepared.frame_reports) != lcd_refresh.FIRST_REFRESH_MAX_FRAMES:
        raise RuntimeError("Ersttest muss exakt fünf vorbereitete Frames besitzen")
    if sum(len(reports) for reports in prepared.frame_reports) != EXPECTED_WRITES:
        raise RuntimeError("Ersttest muss exakt 15 vorbereitete Reports besitzen")
    for reports in prepared.frame_reports:
        lcd_transport.validate_transfer_invariants(prepared.jpeg, reports)
        if len(reports) != EXPECTED_SEGMENTS:
            raise RuntimeError("Jeder Ersttestframe muss exakt N=3 besitzen")
        if any(report.control[0] != lcd_transport.COMMAND for report in reports):
            raise RuntimeError("Nur Opcode 0x08 ist zulässig")


class LoggedPreparedSender:
    def __init__(
        self,
        prepared: PreparedRefreshTest,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._prepared = prepared
        self._clock = clock
        self._epoch = clock()
        self._next_frame = 0
        self._last_completed_at: float | None = None

    @property
    def last_completed_at(self) -> float | None:
        return self._last_completed_at

    def __call__(self, jpeg: bytes) -> int:
        if jpeg is not self._prepared.jpeg:
            raise RuntimeError("Refreshcontroller lieferte nicht die Referenzbytes")
        if self._next_frame >= len(self._prepared.frame_reports):
            raise RuntimeError("Mehr als fünf Frameaufrufe verhindert")
        frame_number = self._next_frame + 1
        reports = self._prepared.frame_reports[self._next_frame]
        self._next_frame += 1
        started = self._clock()
        completed_writes = 0

        def observe_write(_: lcd_transport.TransferSegment) -> None:
            nonlocal completed_writes
            completed_writes += 1

        print(f"Frame {frame_number}: Start +{started - self._epoch:.6f} s")
        try:
            writes = lcd_transport.send_frame_once(
                self._prepared.device,
                jpeg,
                prepared_segments=reports,
                extra_validator=runtime_device_error,
                extra_transfer_validator=lambda: validate_prepared_profile(
                    self._prepared
                ),
                write_observer=observe_write,
            )
        except Exception as error:
            duration = max(0.0, self._clock() - started)
            print(
                f"Frame {frame_number}: FEHLER nach {duration:.6f} s, "
                f"Writes {completed_writes}/{EXPECTED_SEGMENTS}: {error}",
                file=sys.stderr,
            )
            raise
        completed_at = self._clock()
        duration = max(0.0, completed_at - started)
        self._last_completed_at = completed_at
        print(
            f"Frame {frame_number}: Dauer {duration:.6f} s, "
            f"Writes {writes}/{EXPECTED_SEGMENTS}, Ergebnis vollständig"
        )
        return writes


def _print_preview(
    jpeg: bytes,
    device: HidrawInterface | None,
    device_status: str,
) -> None:
    info = lcd_transport.validate_jpeg(jpeg, max_segments=EXPECTED_SEGMENTS)
    print("Preview des fest begrenzten ersten LCD-Refresh-Tests:")
    print(f"  Referenz:       {REFERENCE_PATH}")
    print(f"  SHA-256:        {lcd_refresh.FIRST_REFRESH_REFERENCE_SHA256}")
    print(f"  JPEG/N:         {info.length} Byte / {info.segment_count}")
    print("  Frames/Writes:  5 / 15")
    print("  Startintervall: 1,0 s; kein Catch-up")
    print("  Maximallaufzeit: 6,0 s")
    if device is None:
        print(f"  Zielgerät:      nicht live-freigegeben ({device_status})")
    else:
        print(f"  Zielgerät:      {device.device_path} ({device_status})")
    print("  Sichtbarkeit:   ausschließlich vom Benutzer zu beobachten")


def run_live(prepared: PreparedRefreshTest) -> int:
    if not os.access(prepared.device.device_path, os.W_OK):
        print("FEHLER: Interface 1 ist nicht schreibbar.", file=sys.stderr)
        return EXIT_PERMISSION
    controller = lcd_refresh.RefreshController(
        prepared.plan,
        LoggedPreparedSender(prepared),
    )
    controller.start()
    result = controller.wait()
    if result is None:
        print("FEHLER: Refreshworker lieferte kein Ergebnis.", file=sys.stderr)
        return EXIT_TRANSFER
    if (
        result.stop_reason != lcd_refresh.RefreshStopReason.MAX_FRAMES
        or result.frames_sent != lcd_refresh.FIRST_REFRESH_MAX_FRAMES
        or len(result.transfer_durations) != lcd_refresh.FIRST_REFRESH_MAX_FRAMES
    ):
        print(
            f"FEHLER: Refresh abgebrochen: {result.stop_reason.value}, "
            f"Frames={result.frames_sent}, Ursache={result.error}",
            file=sys.stderr,
        )
        return EXIT_TRANSFER
    print("TRANSPORTERFOLG: 5 Frames / 15 vollständige Writes.")
    print(
        "SICHTBARER ERFOLG WIRD NICHT AUTOMATISCH BEHAUPTET: "
        "Referenzbild und ausbleibendes Defaultbild müssen beobachtet werden."
    )
    return EXIT_SUCCESS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Standardmäßig nur Preview; echter Lauf ausschließlich für das "
            "fest verdrahtete 5-Frame-Referenzprofil."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="nur Preview; keinen hidraw-Knoten öffnen",
    )
    parser.add_argument(
        "--i-understand-the-risk",
        action="store_true",
        help="das fest verdrahtete Ersttestprofil ausdrücklich starten",
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.i_understand_the_risk:
        parser.error("--dry-run und --i-understand-the-risk schließen sich aus")

    try:
        jpeg = lcd_transport.load_jpeg(REFERENCE_PATH, max_segments=EXPECTED_SEGMENTS)
        lcd_refresh.build_first_refresh_live_test_plan(jpeg)
        reports = tuple(
            lcd_transport.build_segments(jpeg)
            for _ in range(lcd_refresh.FIRST_REFRESH_MAX_FRAMES)
        )
        if sum(len(frame) for frame in reports) != EXPECTED_WRITES:
            raise RuntimeError("Offline-Profil enthält nicht exakt 15 Reports")
    except (OSError, ValueError, RuntimeError) as error:
        print(f"FEHLER: Referenz-/Paketprüfung fehlgeschlagen: {error}", file=sys.stderr)
        return EXIT_SAFETY

    device, discovery_status = lcd_transport.discover_lcd_interface()
    status = discovery_status
    if device is not None:
        error = runtime_device_error(device)
        status = error or "alle read-only Preflight-Gates erfüllt"
    _print_preview(jpeg, device, status)

    if args.dry_run or not args.i_understand_the_risk:
        print("DRY-RUN: Kein hidraw-Open, kein HID-Write, keine Session.")
        return EXIT_SUCCESS
    if device is None:
        print(f"FEHLER: {discovery_status}", file=sys.stderr)
        return EXIT_PREFLIGHT
    try:
        prepared = prepare_test(device)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"FEHLER: Live-Preflight abgebrochen: {error}", file=sys.stderr)
        return EXIT_PREFLIGHT
    print("RISIKO BESTÄTIGT: Festes 5-Frame-Profil beginnt.")
    return run_live(prepared)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nABBRUCH: Kein Retry und keine Recovery.", file=sys.stderr)
        raise SystemExit(EXIT_TRANSFER)
