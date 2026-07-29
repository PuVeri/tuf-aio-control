#!/usr/bin/env python3
"""Read-only discovery for the ASUS TUF AIO LCD HID interfaces."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

TARGET_VID = "0b05"
TARGET_PID = "1c7b"
HIDRAW_CLASS = Path("/sys/class/hidraw")


@dataclass(frozen=True)
class HidrawInterface:
    device_path: str
    sysfs_path: str
    interface_number: int | None
    manufacturer: str | None
    product: str | None
    serial: str | None
    vendor_id: str
    product_id: str
    input_report_bytes: int | None
    output_report_bytes: int | None
    feature_report_bytes: int | None
    report_ids: tuple[int, ...]
    readable: bool
    udev_properties: dict[str, str]


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="ascii", errors="replace").strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _ancestors(start: Path) -> Iterator[Path]:
    current = start.resolve()
    yield current
    yield from current.parents


def _find_usb_device(start: Path) -> Path | None:
    for candidate in _ancestors(start):
        vid = _read_text(candidate / "idVendor")
        pid = _read_text(candidate / "idProduct")
        if vid is not None and pid is not None:
            return candidate
    return None


def _find_interface_number(start: Path, usb_device: Path) -> int | None:
    for candidate in _ancestors(start):
        if candidate == usb_device:
            break
        value = _read_text(candidate / "bInterfaceNumber")
        if value is not None:
            try:
                return int(value, 16)
            except ValueError:
                return None
    return None


def _udev_properties(sysfs_class_entry: Path) -> dict[str, str]:
    """Return udev properties without treating udev as an identification authority."""
    try:
        result = subprocess.run(
            [
                "udevadm",
                "info",
                "--query=property",
                f"--path={sysfs_class_entry.resolve()}",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return {}

    properties: dict[str, str] = {}
    if result.returncode == 0:
        for line in result.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                properties[key] = value
    return properties


def parse_report_descriptor(data: bytes) -> dict[str, object]:
    """Compute maximum byte lengths per report type from a HID descriptor.

    Long items are skipped. For each report ID and report type, Report Size *
    Report Count is accumulated. Returned byte lengths include a report-ID byte
    only when report IDs are declared.
    """
    report_size = 0
    report_count = 0
    report_id = 0
    declared_ids: set[int] = set()
    bits: dict[str, dict[int, int]] = {
        "input": {},
        "output": {},
        "feature": {},
    }
    index = 0

    while index < len(data):
        prefix = data[index]
        index += 1
        if prefix == 0xFE:
            if index + 2 > len(data):
                break
            size = data[index]
            index += 2 + size
            continue

        size_code = prefix & 0x03
        size = 4 if size_code == 3 else size_code
        if index + size > len(data):
            break
        raw_value = data[index : index + size]
        value = int.from_bytes(raw_value, "little", signed=False)
        index += size

        item_type = (prefix >> 2) & 0x03
        tag = (prefix >> 4) & 0x0F
        if item_type == 1:  # Global item
            if tag == 7:
                report_size = value
            elif tag == 8:
                report_id = value
                declared_ids.add(value)
            elif tag == 9:
                report_count = value
        elif item_type == 0:  # Main item
            kind = {8: "input", 9: "output", 11: "feature"}.get(tag)
            if kind is not None:
                current = bits[kind].get(report_id, 0)
                bits[kind][report_id] = current + report_size * report_count

    has_report_ids = bool(declared_ids)

    def maximum_bytes(kind: str) -> int | None:
        if not bits[kind]:
            return None
        return max(
            (bit_count + 7) // 8 + (1 if has_report_ids else 0)
            for bit_count in bits[kind].values()
        )

    return {
        "input_report_bytes": maximum_bytes("input"),
        "output_report_bytes": maximum_bytes("output"),
        "feature_report_bytes": maximum_bytes("feature"),
        "report_ids": tuple(sorted(declared_ids)),
    }


def discover(
    vendor_id: str = TARGET_VID,
    product_id: str = TARGET_PID,
    *,
    include_udev: bool = True,
) -> list[HidrawInterface]:
    vendor_id = vendor_id.lower().removeprefix("0x").zfill(4)
    product_id = product_id.lower().removeprefix("0x").zfill(4)
    found: list[HidrawInterface] = []

    try:
        entries = sorted(HIDRAW_CLASS.glob("hidraw*"))
    except OSError:
        return found

    for entry in entries:
        hid_device = entry / "device"
        usb_device = _find_usb_device(hid_device)
        if usb_device is None:
            continue
        actual_vid = (_read_text(usb_device / "idVendor") or "").lower()
        actual_pid = (_read_text(usb_device / "idProduct") or "").lower()
        if (actual_vid, actual_pid) != (vendor_id, product_id):
            continue

        descriptor_info: dict[str, object] = {
            "input_report_bytes": None,
            "output_report_bytes": None,
            "feature_report_bytes": None,
            "report_ids": (),
        }
        try:
            descriptor_info = parse_report_descriptor(
                (hid_device / "report_descriptor").read_bytes()
            )
        except (FileNotFoundError, PermissionError, OSError):
            pass

        device_path = Path("/dev") / entry.name
        found.append(
            HidrawInterface(
                device_path=str(device_path),
                sysfs_path=str(entry.resolve()),
                interface_number=_find_interface_number(hid_device, usb_device),
                manufacturer=_read_text(usb_device / "manufacturer"),
                product=_read_text(usb_device / "product"),
                serial=_read_text(usb_device / "serial"),
                vendor_id=actual_vid,
                product_id=actual_pid,
                input_report_bytes=descriptor_info["input_report_bytes"],  # type: ignore[arg-type]
                output_report_bytes=descriptor_info["output_report_bytes"],  # type: ignore[arg-type]
                feature_report_bytes=descriptor_info["feature_report_bytes"],  # type: ignore[arg-type]
                report_ids=descriptor_info["report_ids"],  # type: ignore[arg-type]
                readable=os.access(device_path, os.R_OK),
                udev_properties=_udev_properties(entry) if include_udev else {},
            )
        )

    return sorted(
        found,
        key=lambda item: (
            item.interface_number is None,
            item.interface_number if item.interface_number is not None else 999,
            item.device_path,
        ),
    )


def _print_human(devices: list[HidrawInterface]) -> None:
    if not devices:
        print(f"Kein HID-Gerät mit USB-ID {TARGET_VID}:{TARGET_PID} gefunden.")
        return
    print(f"Gefunden: {len(devices)} HID-Interface(s) für {TARGET_VID}:{TARGET_PID}")
    for device in devices:
        interface = (
            str(device.interface_number)
            if device.interface_number is not None
            else "unbekannt"
        )
        print(f"\nInterface {interface}: {device.device_path}")
        print(f"  sysfs:       {device.sysfs_path}")
        print(f"  Hersteller:  {device.manufacturer or 'unbekannt'}")
        print(f"  Produkt:     {device.product or 'unbekannt'}")
        print(f"  Seriennr.:   {device.serial or 'unbekannt'}")
        print(f"  Input:       {device.input_report_bytes or 'unbekannt'} Byte")
        print(f"  Output:      {device.output_report_bytes or 'unbekannt'} Byte")
        feature = (
            f"{device.feature_report_bytes} Byte"
            if device.feature_report_bytes is not None
            else "nicht deklariert/unbekannt"
        )
        print(f"  Feature:     {feature}")
        ids = ", ".join(map(str, device.report_ids)) or "keine deklariert"
        print(f"  Report-IDs:  {ids}")
        print(f"  lesbar:      {'ja' if device.readable else 'nein'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ASUS-AIO-LCD über sysfs und udev rein lesend erkennen."
    )
    parser.add_argument("--json", action="store_true", help="JSON ausgeben")
    parser.add_argument(
        "--no-udev",
        action="store_true",
        help="udevadm-Abfrage überspringen; sysfs bleibt aktiv",
    )
    args = parser.parse_args()

    devices = discover(include_udev=not args.no_udev)
    if args.json:
        json.dump([asdict(device) for device in devices], sys.stdout, indent=2)
        print()
    else:
        _print_human(devices)
    return 0 if devices else 1


if __name__ == "__main__":
    raise SystemExit(main())

