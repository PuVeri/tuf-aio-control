#!/usr/bin/env python3
"""Time-limited, read-only hidraw observer for the ASUS TUF AIO LCD."""

from __future__ import annotations

import argparse
import os
import select
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from discover_device import HidrawInterface, discover

DEFAULT_DURATION = 3.0


def _select_interface(
    devices: list[HidrawInterface], interface_number: int
) -> HidrawInterface | None:
    matches = [
        device for device in devices if device.interface_number == interface_number
    ]
    if len(matches) != 1:
        return None
    return matches[0]


def _capture_path(value: str | None, interface_number: int) -> Path | None:
    if value is None:
        return None
    if value != "AUTO":
        candidate = Path(value)
        if candidate.parent != Path("captures") or candidate.name != value.removeprefix(
            "captures/"
        ):
            raise ValueError("Capture-Pfad muss eine direkte Datei unter captures/ sein")
        return candidate
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%z")
    return Path("captures") / f"hid-input-if{interface_number}-{timestamp}.bin"


def observe(
    device: HidrawInterface,
    duration: float,
    capture_path: Path | None,
) -> tuple[int, Path | None]:
    if not device.readable:
        raise PermissionError(
            f"Keine Leseberechtigung für {device.device_path}; "
            "Rechte wurden nicht verändert."
        )

    capture_fd: int | None = None
    if capture_path is not None:
        capture_path.parent.mkdir(parents=False, exist_ok=True)
        capture_fd = os.open(
            capture_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )

    device_fd: int | None = None
    report_count = 0
    try:
        # O_RDONLY is an explicit safety invariant. This program contains no
        # write/ioctl operation directed at the hidraw file descriptor.
        device_fd = os.open(device.device_path, os.O_RDONLY | os.O_NONBLOCK)
        deadline = time.monotonic() + duration
        read_size = device.input_report_bytes or 4096

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            readable, _, _ = select.select([device_fd], [], [], remaining)
            if not readable:
                break
            try:
                data = os.read(device_fd, read_size)
            except BlockingIOError:
                continue
            if not data:
                break

            report_count += 1
            timestamp = datetime.now(timezone.utc).astimezone().isoformat(
                timespec="milliseconds"
            )
            print(
                f"{timestamp} interface={device.interface_number} "
                f"bytes={len(data)} data={data.hex(' ')}"
            )
            if capture_fd is not None:
                os.write(capture_fd, data)
    finally:
        if device_fd is not None:
            os.close(device_fd)
        if capture_fd is not None:
            os.close(capture_fd)

    return report_count, capture_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Eingehende hidraw-Daten zeitbegrenzt und ausschließlich lesend beobachten."
    )
    parser.add_argument(
        "--interface",
        type=int,
        required=True,
        choices=(0, 1),
        help="USB-Interface-Nummer, nicht hidraw-Nummer",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=DEFAULT_DURATION,
        help=f"Laufzeit in Sekunden (Standard: {DEFAULT_DURATION:g})",
    )
    parser.add_argument(
        "--capture",
        nargs="?",
        const="AUTO",
        metavar="captures/DATEI.bin",
        help="Rohbytes exklusiv in einer neuen Datei unter captures/ sichern",
    )
    args = parser.parse_args()

    if not 0 < args.duration <= 300:
        parser.error("--duration muss größer 0 und höchstens 300 Sekunden sein")

    device = _select_interface(discover(), args.interface)
    if device is None:
        print(
            f"Interface {args.interface} wurde nicht eindeutig für "
            "0b05:1c7b gefunden.",
            file=sys.stderr,
        )
        return 2
    if not device.readable:
        print(
            f"Keine Leseberechtigung für {device.device_path}. "
            "Es wurde kein Lesezugriff versucht und keine Berechtigung verändert.",
            file=sys.stderr,
        )
        return 3

    try:
        capture_path = _capture_path(args.capture, args.interface)
        count, saved_path = observe(device, args.duration, capture_path)
    except (PermissionError, FileExistsError, OSError, ValueError) as error:
        print(f"Lesebeobachtung nicht gestartet/abgebrochen: {error}", file=sys.stderr)
        return 4

    print(
        f"Beobachtung beendet: interface={args.interface}, "
        f"reports={count}, duration={args.duration:g}s"
    )
    if saved_path is not None:
        print(f"Rohbytes: {saved_path} (neu angelegt, nicht überschrieben)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

