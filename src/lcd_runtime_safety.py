#!/usr/bin/env python3
"""Strict read-only runtime gates for the confirmed v49 LCD interface."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Callable

import lcd_transport
from discover_device import HidrawInterface, UsbEndpoint

EXPECTED_BCD_DEVICE = 0x0049
EXPECTED_BCD_DEVICE_DISPLAY = "0.49"
EXPECTED_MANUFACTURER = "ASUS Tek"
EXPECTED_PRODUCT = "TUF GAMING LC III 360 ARGB LCD"
EXPECTED_USAGE_PAGE = 0xFF06
EXPECTED_USAGE = 0x01
EXPECTED_ENDPOINTS = (
    UsbEndpoint(address=0x03, attributes=0x03, max_packet_size=1024, interval=1),
    UsbEndpoint(address=0x84, attributes=0x03, max_packet_size=16, interval=1),
)

CompetingWriterFinder = Callable[[HidrawInterface], tuple[str, ...]]


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
    """Validate every known identity, HID and USB-interface field."""
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
    if device.feature_report_bytes is not None:
        return "Interface 1 darf keine Feature-Reports deklarieren"
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
        try:
            descriptors = tuple((process / "fd").iterdir())
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


def runtime_device_error(
    device: HidrawInterface,
    *,
    competing_writer_finder: CompetingWriterFinder = find_competing_writers,
) -> str | None:
    """Apply strict metadata and best-effort local competing-writer gates."""
    error = strict_device_error(device)
    if error is not None:
        return error
    try:
        competitors = competing_writer_finder(device)
    except RuntimeError as error:
        return str(error)
    if competitors:
        return "Konkurrierender Writer erkannt: " + "; ".join(competitors)
    return None
