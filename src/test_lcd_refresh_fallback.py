#!/usr/bin/env python3
"""Fixed five-frame refresh followed by passive fallback timing on stdin."""

from __future__ import annotations

import argparse
import os
import select
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Sequence

import lcd_refresh
import lcd_transport
import test_lcd_refresh as refresh_test

OBSERVATION_SECONDS = 20.0

EXIT_SUCCESS = 0
EXIT_PREFLIGHT = 2
EXIT_PERMISSION = 3
EXIT_TRANSFER = 4
EXIT_SAFETY = 5

Clock = Callable[[], float]
ObservationWait = Callable[[float], bool]
ScheduleWait = Callable[[threading.Event, float], bool]


@dataclass(frozen=True)
class FallbackObservation:
    reported: bool
    seconds_since_test_start: float | None
    seconds_since_last_frame: float | None


def wait_for_enter(timeout: float) -> bool:
    """Wait only on terminal input; never access HID, USB or sysfs."""
    readable, _, _ = select.select((sys.stdin,), (), (), timeout)
    if not readable:
        return False
    return sys.stdin.readline() != ""


def observe_fallback(
    *,
    test_started_at: float,
    last_frame_completed_at: float,
    clock: Clock = time.monotonic,
    wait_function: ObservationWait = wait_for_enter,
) -> FallbackObservation:
    """Passively time an Enter report for at most twenty seconds."""
    print(
        "PASSIVE BEOBACHTUNG: Enter drücken, sobald das ASUS-Defaultbild "
        "sichtbar ist. Keine HID-/USB-Zugriffe."
    )
    reported = wait_function(OBSERVATION_SECONDS)
    if not reported:
        print("Kein beobachteter Fallback innerhalb 20 s.")
        return FallbackObservation(False, None, None)

    reported_at = clock()
    since_start = max(0.0, reported_at - test_started_at)
    since_last = max(0.0, reported_at - last_frame_completed_at)
    print(f"Fallback gemeldet: {since_start:.6f} s seit Teststart.")
    print(f"Fallback gemeldet: {since_last:.6f} s seit Abschluss von Frame 5.")
    return FallbackObservation(True, since_start, since_last)


def run_timing_live(
    prepared: refresh_test.PreparedRefreshTest,
    *,
    clock: Clock = time.monotonic,
    observation_wait: ObservationWait = wait_for_enter,
    schedule_wait: ScheduleWait | None = None,
) -> int:
    """Run the unchanged transport, then observe without further writes."""
    if not os.access(prepared.device.device_path, os.W_OK):
        print("FEHLER: Interface 1 ist nicht schreibbar.", file=sys.stderr)
        return EXIT_PERMISSION

    print(
        "Während der 5 Frames beobachten, ob das Defaultbild kurz "
        "dazwischen erscheint. Dieses Ja/Nein wird nicht automatisch erkannt."
    )
    test_started_at = clock()
    sender = refresh_test.LoggedPreparedSender(prepared, clock=clock)
    if schedule_wait is None:
        controller = lcd_refresh.RefreshController(
            prepared.plan,
            sender,
            clock=clock,
        )
    else:
        controller = lcd_refresh.RefreshController(
            prepared.plan,
            sender,
            clock=clock,
            wait_function=schedule_wait,
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
        or sender.last_completed_at is None
    ):
        print(
            f"FEHLER: Refresh abgebrochen: {result.stop_reason.value}, "
            f"Frames={result.frames_sent}, Ursache={result.error}",
            file=sys.stderr,
        )
        return EXIT_TRANSFER

    print("TRANSPORTERFOLG: 5 Frames / 15 vollständige Writes.")
    print(
        "SICHTBARKEIT UND DEFAULT-UNTERDRÜCKUNG WERDEN NICHT AUTOMATISCH "
        "BEHAUPTET."
    )
    observe_fallback(
        test_started_at=test_started_at,
        last_frame_completed_at=sender.last_completed_at,
        clock=clock,
        wait_function=observation_wait,
    )
    return EXIT_SUCCESS


def _preview() -> tuple[bytes, object | None, str]:
    jpeg = lcd_transport.load_jpeg(
        refresh_test.REFERENCE_PATH,
        max_segments=refresh_test.EXPECTED_SEGMENTS,
    )
    lcd_refresh.build_first_refresh_live_test_plan(jpeg)
    reports = tuple(
        lcd_transport.build_segments(jpeg)
        for _ in range(lcd_refresh.FIRST_REFRESH_MAX_FRAMES)
    )
    if sum(len(frame) for frame in reports) != refresh_test.EXPECTED_WRITES:
        raise RuntimeError("Offline-Profil enthält nicht exakt 15 Reports")

    device, discovery_status = lcd_transport.discover_lcd_interface()
    status = discovery_status
    if device is not None:
        error = refresh_test.runtime_device_error(device)
        status = error or "alle read-only Preflight-Gates erfüllt"
    refresh_test._print_preview(jpeg, device, status)
    print("  Danach:         maximal 20 s passive Enter-Zeitmessung")
    return jpeg, device, discovery_status


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        allow_abbrev=False,
        description=(
            "Standardmäßig nur Preview; fester 5-Frame-Transport mit "
            "anschließender rein passiver Fallback-Zeitmessung."
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
        help="den festen Transport plus passive Zeitmessung ausdrücklich starten",
    )
    args = parser.parse_args(argv)
    if args.dry_run and args.i_understand_the_risk:
        parser.error("--dry-run und --i-understand-the-risk schließen sich aus")

    try:
        _, device, discovery_status = _preview()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"FEHLER: Referenz-/Paketprüfung fehlgeschlagen: {error}", file=sys.stderr)
        return EXIT_SAFETY
    if args.dry_run or not args.i_understand_the_risk:
        print("DRY-RUN: Kein hidraw-Open, kein HID-Write, keine Session.")
        return EXIT_SUCCESS
    if device is None:
        print(f"FEHLER: {discovery_status}", file=sys.stderr)
        return EXIT_PREFLIGHT
    try:
        prepared = refresh_test.prepare_test(device)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"FEHLER: Live-Preflight abgebrochen: {error}", file=sys.stderr)
        return EXIT_PREFLIGHT
    print("RISIKO BESTÄTIGT: Festes 5-Frame-Profil mit Zeitmessung beginnt.")
    return run_timing_live(prepared)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nABBRUCH: Kein Retry und keine Recovery.", file=sys.stderr)
        raise SystemExit(EXIT_TRANSFER)
