#!/usr/bin/env python3
"""Analyze a saved ASUS LCD USBPcap capture without accessing any USB device.

The input must be a classic pcap or pcapng file whose packet link type is
DLT_USBPCAP (249).  This program opens only the capture and optional output
files.  It imports no USB or HID module and has no live-capture mode.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import BinaryIO, Iterable


DLT_USBPCAP = 249
TARGET_VID = 0x0B05
TARGET_PID = 0x1C7B
USBPCAP_HEADER_LEN = 27
TRANSFER_INTERRUPT = 1


class CaptureError(Exception):
    """The file is unsupported, truncated, or inconsistent."""


@dataclass(frozen=True)
class CapturePacket:
    frame: int
    timestamp: Fraction
    link_type: int
    captured_length: int
    original_length: int
    data: bytes


@dataclass(frozen=True)
class UsbEvent:
    frame: int
    timestamp: Fraction
    irp_id: int
    status: int
    function: int
    info: int
    bus: int
    device: int
    endpoint: int
    transfer_type: int
    declared_data_length: int
    payload: bytes
    captured_length: int
    original_length: int
    header_length: int
    control_stage: int | None

    @property
    def is_completion(self) -> bool:
        return bool(self.info & 1)

    @property
    def phase(self) -> str:
        return "complete" if self.is_completion else "submit"


@dataclass
class LogicalUrb:
    irp_id: int
    bus: int
    device: int
    endpoint: int
    transfer_type: int
    events: list[UsbEvent] = field(default_factory=list)

    @property
    def submit(self) -> UsbEvent | None:
        return next((event for event in self.events if not event.is_completion), None)

    @property
    def completion(self) -> UsbEvent | None:
        return next((event for event in reversed(self.events) if event.is_completion), None)

    @property
    def data_event(self) -> UsbEvent | None:
        # USBPcap attaches OUT data to FDO->PDO (submit) and IN data to
        # PDO->FDO (completion).  Pick the longest matching payload so a
        # duplicate metadata event cannot hide the actual transfer buffer.
        want_completion = bool(self.endpoint & 0x80)
        candidates = [
            event
            for event in self.events
            if event.is_completion == want_completion and event.payload
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda event: len(event.payload))

    @property
    def event_time(self) -> Fraction:
        data = self.data_event
        if data is not None:
            return data.timestamp
        if self.completion is not None:
            return self.completion.timestamp
        return self.events[0].timestamp


@dataclass(frozen=True)
class SegmentReport:
    urb: LogicalUrb
    report: bytes
    controlword: int
    command: int
    first: bool
    field23: int


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    data = handle.read(length)
    if len(data) != length:
        raise CaptureError("unerwartetes Dateiende")
    return data


def read_capture(path: Path) -> tuple[list[CapturePacket], list[str]]:
    with path.open("rb") as handle:
        magic = _read_exact(handle, 4)
        handle.seek(0)
        if magic == b"\x0a\x0d\x0d\x0a":
            return _read_pcapng(handle)
        return _read_pcap(handle)


def _read_pcap(handle: BinaryIO) -> tuple[list[CapturePacket], list[str]]:
    header = _read_exact(handle, 24)
    magic = header[:4]
    variants = {
        b"\xd4\xc3\xb2\xa1": ("<", 1_000_000),
        b"\xa1\xb2\xc3\xd4": (">", 1_000_000),
        b"\x4d\x3c\xb2\xa1": ("<", 1_000_000_000),
        b"\xa1\xb2\x3c\x4d": (">", 1_000_000_000),
    }
    if magic not in variants:
        raise CaptureError("weder pcap noch pcapng")
    endian, resolution = variants[magic]
    _, _, _, _, _, link_type = struct.unpack(endian + "HHiIII", header[4:])
    if link_type != DLT_USBPCAP:
        raise CaptureError(f"pcap-Linktyp {link_type}, erwartet {DLT_USBPCAP}")

    packets: list[CapturePacket] = []
    frame = 0
    while True:
        record_header = handle.read(16)
        if not record_header:
            break
        if len(record_header) != 16:
            raise CaptureError("gekürzter pcap-Recordheader")
        seconds, fraction, captured, original = struct.unpack(
            endian + "IIII", record_header
        )
        frame += 1
        packets.append(
            CapturePacket(
                frame=frame,
                timestamp=Fraction(seconds, 1) + Fraction(fraction, resolution),
                link_type=link_type,
                captured_length=captured,
                original_length=original,
                data=_read_exact(handle, captured),
            )
        )
    return packets, []


def _pcapng_options(data: bytes, endian: str) -> dict[int, list[bytes]]:
    options: dict[int, list[bytes]] = {}
    offset = 0
    while offset + 4 <= len(data):
        code, length = struct.unpack_from(endian + "HH", data, offset)
        offset += 4
        if code == 0:
            break
        if offset + length > len(data):
            raise CaptureError("gekürzte pcapng-Option")
        options.setdefault(code, []).append(data[offset : offset + length])
        offset += (length + 3) & ~3
    return options


def _read_pcapng(handle: BinaryIO) -> tuple[list[CapturePacket], list[str]]:
    packets: list[CapturePacket] = []
    warnings: list[str] = []
    interfaces: list[tuple[int, int]] = []  # (link type, timestamp denominator)
    endian: str | None = None
    frame = 0

    while True:
        prefix = handle.read(12)
        if not prefix:
            break
        if len(prefix) != 12:
            raise CaptureError("gekürzter pcapng-Blockheader")
        raw_type = prefix[:4]

        if raw_type == b"\x0a\x0d\x0d\x0a":
            bom = prefix[8:12]
            if bom == b"\x4d\x3c\x2b\x1a":
                endian = "<"
            elif bom == b"\x1a\x2b\x3c\x4d":
                endian = ">"
            else:
                raise CaptureError("ungültige pcapng-Byteorder-Magic")
            block_length = struct.unpack(endian + "I", prefix[4:8])[0]
            interfaces = []
        else:
            if endian is None:
                raise CaptureError("pcapng beginnt nicht mit Section Header Block")
            block_length = struct.unpack(endian + "I", prefix[4:8])[0]

        if block_length < 12 or block_length % 4:
            raise CaptureError(f"ungültige pcapng-Blocklänge {block_length}")
        remainder = _read_exact(handle, block_length - 12)
        trailer = struct.unpack(endian + "I", remainder[-4:])[0]
        if trailer != block_length:
            raise CaptureError("pcapng-Blocklängen stimmen nicht überein")
        body = prefix[8:] + remainder[:-4]
        block_type = struct.unpack(endian + "I", raw_type)[0]

        if block_type == 0x0A0D0D0A:
            continue
        if block_type == 1:  # Interface Description Block
            if len(body) < 8:
                raise CaptureError("gekürzter Interface Description Block")
            link_type = struct.unpack_from(endian + "H", body, 0)[0]
            options = _pcapng_options(body[8:], endian)
            denominator = 1_000_000
            if 9 in options and options[9] and options[9][0]:
                value = options[9][0][0]
                denominator = (
                    2 ** (value & 0x7F) if value & 0x80 else 10 ** value
                )
            interfaces.append((link_type, denominator))
            continue
        if block_type == 6:  # Enhanced Packet Block
            if len(body) < 20:
                raise CaptureError("gekürzter Enhanced Packet Block")
            interface_id, ts_hi, ts_lo, captured, original = struct.unpack_from(
                endian + "IIIII", body, 0
            )
            if interface_id >= len(interfaces):
                raise CaptureError("pcapng verweist auf unbekanntes Interface")
            if 20 + captured > len(body):
                raise CaptureError("gekürzte EPB-Paketdaten")
            link_type, denominator = interfaces[interface_id]
            frame += 1
            packets.append(
                CapturePacket(
                    frame=frame,
                    timestamp=Fraction((ts_hi << 32) | ts_lo, denominator),
                    link_type=link_type,
                    captured_length=captured,
                    original_length=original,
                    data=body[20 : 20 + captured],
                )
            )
            continue
        if block_type == 2:  # Obsolete Packet Block
            if len(body) < 20:
                raise CaptureError("gekürzter Packet Block")
            interface_id, _drops, ts_hi, ts_lo, captured, original = struct.unpack_from(
                endian + "HHIIII", body, 0
            )
            if interface_id >= len(interfaces):
                raise CaptureError("pcapng verweist auf unbekanntes Interface")
            link_type, denominator = interfaces[interface_id]
            frame += 1
            packets.append(
                CapturePacket(
                    frame=frame,
                    timestamp=Fraction((ts_hi << 32) | ts_lo, denominator),
                    link_type=link_type,
                    captured_length=captured,
                    original_length=original,
                    data=body[20 : 20 + captured],
                )
            )
            continue
        if block_type == 3:
            warnings.append("Simple Packet Block ohne Zeitstempel wurde ignoriert")

    if not packets:
        raise CaptureError("Capture enthält keine auswertbaren Paketblöcke")
    wrong = sorted({packet.link_type for packet in packets if packet.link_type != DLT_USBPCAP})
    if wrong:
        warnings.append(
            "Nicht-USBPcap-Linktypen wurden ignoriert: " + ", ".join(map(str, wrong))
        )
    return [packet for packet in packets if packet.link_type == DLT_USBPCAP], warnings


def decode_usbpcap(packet: CapturePacket) -> UsbEvent:
    if len(packet.data) < USBPCAP_HEADER_LEN:
        raise CaptureError(f"Frame {packet.frame}: gekürzter USBPcap-Header")
    (
        header_length,
        irp_id,
        status,
        function,
        info,
        bus,
        device,
        endpoint,
        transfer_type,
        data_length,
    ) = struct.unpack_from("<HQIHBHHBBI", packet.data, 0)
    if header_length < USBPCAP_HEADER_LEN or header_length > len(packet.data):
        raise CaptureError(
            f"Frame {packet.frame}: ungültige USBPcap-Headerlänge {header_length}"
        )
    control_stage = packet.data[27] if transfer_type == 2 and header_length >= 28 else None
    return UsbEvent(
        frame=packet.frame,
        timestamp=packet.timestamp,
        irp_id=irp_id,
        status=status,
        function=function,
        info=info,
        bus=bus,
        device=device,
        endpoint=endpoint,
        transfer_type=transfer_type,
        declared_data_length=data_length,
        payload=packet.data[header_length:],
        captured_length=packet.captured_length,
        original_length=packet.original_length,
        header_length=header_length,
        control_stage=control_stage,
    )


def discover_target_instances(events: Iterable[UsbEvent]) -> dict[tuple[int, int], dict]:
    found: dict[tuple[int, int], dict] = {}
    for event in events:
        if event.endpoint != 0 or event.transfer_type != 2:
            continue
        payload = event.payload
        for offset in range(max(0, len(payload) - 17)):
            candidate = payload[offset : offset + 18]
            if len(candidate) < 18 or candidate[0:2] != b"\x12\x01":
                continue
            vid = int.from_bytes(candidate[8:10], "little")
            pid = int.from_bytes(candidate[10:12], "little")
            if (vid, pid) != (TARGET_VID, TARGET_PID):
                continue
            found[(event.bus, event.device)] = {
                "vid": f"{vid:04x}",
                "pid": f"{pid:04x}",
                "bcd_device": f"{int.from_bytes(candidate[12:14], 'little'):04x}",
                "descriptor_frame": event.frame,
            }
    return found


def parse_device(value: str) -> tuple[int, int]:
    try:
        bus_text, address_text = value.split(":", 1)
        return int(bus_text, 0), int(address_text, 0)
    except (ValueError, TypeError) as error:
        raise argparse.ArgumentTypeError("Gerät muss BUS:ADDRESS sein") from error


def pair_urbs(events: Iterable[UsbEvent]) -> list[LogicalUrb]:
    urbs: dict[tuple[int, int, int, int], LogicalUrb] = {}
    for event in events:
        key = (event.bus, event.device, event.endpoint, event.irp_id)
        urb = urbs.setdefault(
            key,
            LogicalUrb(
                irp_id=event.irp_id,
                bus=event.bus,
                device=event.device,
                endpoint=event.endpoint,
                transfer_type=event.transfer_type,
            ),
        )
        urb.events.append(event)
    for urb in urbs.values():
        urb.events.sort(key=lambda event: (event.timestamp, event.frame))
    return sorted(urbs.values(), key=lambda urb: (urb.event_time, urb.irp_id))


def segment_reports(
    urbs: Iterable[LogicalUrb], endpoint: int, report_size: int
) -> tuple[list[SegmentReport], list[str]]:
    reports: list[SegmentReport] = []
    warnings: list[str] = []
    for urb in urbs:
        if urb.endpoint != endpoint or urb.transfer_type != TRANSFER_INTERRUPT:
            continue
        event = urb.data_event
        if event is None:
            continue
        report = event.payload
        if len(report) != report_size:
            warnings.append(
                f"Frame {event.frame}: EP 0x{endpoint:02x} hat {len(report)} statt "
                f"{report_size} erfasste Datenbyte (deklariert {event.declared_data_length})"
            )
            continue
        controlword = int.from_bytes(report[:4], "little")
        reports.append(
            SegmentReport(
                urb=urb,
                report=report,
                controlword=controlword,
                command=controlword & 0xFF,
                first=bool(controlword & 0x80000000),
                field23=(controlword >> 8) & 0x7FFFFF,
            )
        )
    return reports, warnings


def group_segmented_transfers(
    reports: Iterable[SegmentReport], payload_size: int
) -> tuple[list[dict], list[str]]:
    completed: list[dict] = []
    warnings: list[str] = []
    active: dict | None = None

    for report in reports:
        if report.first:
            if active is not None:
                warnings.append(
                    f"neues Erstsegment vor Abschluss von Command 0x{active['command']:02x}"
                )
            active = {
                "command": report.command,
                "n": report.field23,
                "reports": [report],
                "accepted": {0: report.report[4:]},
                "expected": 1,
                "sequence_errors": [],
                "duplicates": [],
            }
            if report.field23 == 0:
                active["sequence_errors"].append("N=0")
                completed.append(active)
                active = None
            elif report.field23 == 1:
                completed.append(active)
                active = None
            continue

        if active is None:
            warnings.append(
                f"Frame {report.urb.data_event.frame if report.urb.data_event else '?'}: "
                "Folgesegment ohne aktives Erstsegment"
            )
            continue
        active["reports"].append(report)
        if report.command != active["command"]:
            active["sequence_errors"].append(
                f"Command wechselte zu 0x{report.command:02x}"
            )
        index = report.field23
        if index == active["expected"]:
            active["accepted"][index] = report.report[4:]
            active["expected"] += 1
        elif index == active["expected"] - 1:
            active["duplicates"].append(index)
            active["accepted"][index] = report.report[4:]
        else:
            active["sequence_errors"].append(
                f"Index {index}, erwartet {active['expected']}"
            )

        if active["expected"] == active["n"]:
            completed.append(active)
            active = None

    if active is not None:
        active["sequence_errors"].append(
            f"unvollständig: erwartet {active['n']}, erreicht {active['expected']}"
        )
        completed.append(active)
    for transfer in completed:
        transfer["assembled"] = b"".join(
            transfer["accepted"].get(index, b"") for index in range(transfer["n"])
        )
        expected_length = transfer["n"] * payload_size
        if len(transfer["assembled"]) != expected_length:
            transfer["sequence_errors"].append(
                f"Assemblierung {len(transfer['assembled'])} statt {expected_length} Byte"
            )
    return completed, warnings


def analyze_jpeg(data: bytes) -> dict:
    soi = data.find(b"\xff\xd8")
    result: dict = {
        "soi_offset": soi if soi >= 0 else None,
        "eoi_offset": None,
        "jpeg_length": None,
        "markers": [],
        "sof": None,
        "error": None,
    }
    if soi < 0:
        result["error"] = "SOI nicht gefunden"
        return result

    pos = soi + 2
    in_scan = False
    while pos < len(data):
        marker_offset: int | None = None
        marker: int | None = None
        if in_scan:
            cursor = pos
            while cursor < len(data):
                ff = data.find(b"\xff", cursor)
                if ff < 0 or ff + 1 >= len(data):
                    result["error"] = "EOI vor Datenende nicht gefunden"
                    return result
                next_pos = ff + 1
                while next_pos < len(data) and data[next_pos] == 0xFF:
                    next_pos += 1
                if next_pos >= len(data):
                    result["error"] = "abgeschnittene Markersequenz"
                    return result
                code = data[next_pos]
                if code == 0x00 or 0xD0 <= code <= 0xD7:
                    cursor = next_pos + 1
                    continue
                marker_offset, marker = ff, code
                break
            in_scan = False
        else:
            ff = data.find(b"\xff", pos)
            if ff < 0 or ff + 1 >= len(data):
                result["error"] = "JPEG-Markersequenz endet ohne EOI"
                return result
            next_pos = ff + 1
            while next_pos < len(data) and data[next_pos] == 0xFF:
                next_pos += 1
            if next_pos >= len(data):
                result["error"] = "abgeschnittene Markersequenz"
                return result
            marker_offset, marker = ff, data[next_pos]

        assert marker_offset is not None and marker is not None
        result["markers"].append({"offset": marker_offset, "marker": f"ff{marker:02x}"})
        if marker == 0xD9:
            result["eoi_offset"] = marker_offset
            result["jpeg_length"] = marker_offset + 2 - soi
            return result
        if marker in {0x01, 0xD8} or 0xD0 <= marker <= 0xD7:
            pos = marker_offset + 2
            continue
        if marker_offset + 4 > len(data):
            result["error"] = f"Marker ff{marker:02x} ohne vollständige Länge"
            return result
        segment_length = int.from_bytes(data[marker_offset + 2 : marker_offset + 4], "big")
        if segment_length < 2:
            result["error"] = f"Marker ff{marker:02x} mit ungültiger Länge"
            return result
        segment_end = marker_offset + 2 + segment_length
        if segment_end > len(data):
            result["error"] = f"Marker ff{marker:02x} reicht über Datenende"
            return result
        result["markers"][-1]["length"] = segment_length
        if marker in {0xC0, 0xC1, 0xC2} and segment_length >= 8:
            payload = data[marker_offset + 4 : segment_end]
            component_count = payload[5] if len(payload) >= 6 else None
            components = []
            if component_count is not None and len(payload) >= 6 + 3 * component_count:
                for index in range(component_count):
                    base = 6 + 3 * index
                    sampling = payload[base + 1]
                    components.append(
                        {
                            "id": payload[base],
                            "h": sampling >> 4,
                            "v": sampling & 0x0F,
                            "quant_table": payload[base + 2],
                        }
                    )
            result["sof"] = {
                "marker": f"SOF{marker - 0xC0}",
                "precision": payload[0] if payload else None,
                "height": int.from_bytes(payload[1:3], "big") if len(payload) >= 3 else None,
                "width": int.from_bytes(payload[3:5], "big") if len(payload) >= 5 else None,
                "component_count": component_count,
                "components": components,
            }
        if marker == 0xDA:
            in_scan = True
        pos = segment_end

    result["error"] = "Datenende ohne EOI"
    return result


def _time_text(timestamp: Fraction | None) -> str | None:
    if timestamp is None:
        return None
    return f"{float(timestamp):.9f}"


def _iso_time(timestamp: Fraction | None) -> str | None:
    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(float(timestamp), UTC).isoformat(timespec="microseconds")
    except (OverflowError, OSError, ValueError):
        return None


def _delta_ms(later: Fraction | None, earlier: Fraction | None) -> float | None:
    if later is None or earlier is None:
        return None
    return round(float((later - earlier) * 1000), 6)


def _urb_times(urb: LogicalUrb) -> dict:
    return {
        "submit_epoch": _time_text(urb.submit.timestamp if urb.submit else None),
        "complete_epoch": _time_text(urb.completion.timestamp if urb.completion else None),
        "submit_frame": urb.submit.frame if urb.submit else None,
        "complete_frame": urb.completion.frame if urb.completion else None,
        "status": f"0x{urb.completion.status:08x}" if urb.completion else None,
    }


def _segment_json(report: SegmentReport, include_report: bool = False) -> dict:
    event = report.urb.data_event
    value = {
        "frame": event.frame if event else None,
        "irp_id": f"0x{report.urb.irp_id:016x}",
        "controlword_bytes": report.report[:4].hex(" "),
        "controlword_le": f"0x{report.controlword:08x}",
        "command": f"0x{report.command:02x}",
        "first": report.first,
        "field23": report.field23,
        "payload_sha256": hashlib.sha256(report.report[4:]).hexdigest(),
        **_urb_times(report.urb),
    }
    if include_report:
        value["full_report_hex"] = report.report.hex(" ")
    return value


def build_analysis(
    capture_path: Path,
    packets: list[CapturePacket],
    initial_warnings: list[str],
    explicit_devices: set[tuple[int, int]],
    out_dir: Path | None,
) -> dict:
    events = [decode_usbpcap(packet) for packet in packets]
    discovered = discover_target_instances(events)
    targets = explicit_devices or set(discovered)
    if not targets:
        raise CaptureError(
            "0b05:1c7b nicht aus injiziertem Device Descriptor erkannt; "
            "--device BUS:ADDRESS angeben"
        )

    warnings = list(initial_warnings)
    if explicit_devices:
        unverified = sorted(explicit_devices - set(discovered))
        if unverified:
            warnings.append(
                "Explizit gewählte Geräteadressen ohne passenden Descriptor im Capture: "
                + ", ".join(f"{bus}:{device}" for bus, device in unverified)
            )
    target_events = [event for event in events if (event.bus, event.device) in targets]
    urbs = pair_urbs(target_events)

    incomplete_urbs = [
        urb
        for urb in urbs
        if urb.transfer_type == TRANSFER_INTERRUPT
        and (urb.submit is None or urb.completion is None)
    ]
    truncated_frames = [
        event.frame
        for event in target_events
        if event.captured_length < event.original_length
        or (
            event.payload
            and len(event.payload) < event.declared_data_length
            and ((event.endpoint & 0x80) != 0) == event.is_completion
        )
    ]
    if incomplete_urbs:
        warnings.append(f"{len(incomplete_urbs)} Interrupt-URBs ohne Submit/Completion-Paar")
    if truncated_frames:
        warnings.append("möglicherweise gekürzte Payloadframes: " + ", ".join(map(str, truncated_frames)))

    if1_out, local = segment_reports(urbs, 0x03, 1024)
    warnings.extend(local)
    if0_out, local = segment_reports(urbs, 0x01, 440)
    warnings.extend(local)
    if0_in, local = segment_reports(urbs, 0x82, 440)
    warnings.extend(local)
    if1_transfers, local = group_segmented_transfers(if1_out, 1020)
    warnings.extend(local)
    if0_transfers, local = group_segmented_transfers(if0_out, 436)
    warnings.extend(local)
    if0_in_transfers, local = group_segmented_transfers(if0_in, 436)
    warnings.extend(local)

    in_reports: list[dict] = []
    for urb in urbs:
        if urb.endpoint != 0x84 or urb.transfer_type != TRANSFER_INTERRUPT:
            continue
        event = urb.data_event
        if event is None:
            continue
        if len(event.payload) != 16:
            warnings.append(
                f"Frame {event.frame}: EP 0x84 hat {len(event.payload)} statt 16 erfasste Datenbyte"
            )
        in_reports.append(
            {
                "frame": event.frame,
                "irp_id": f"0x{urb.irp_id:016x}",
                "length": len(event.payload),
                "report_hex": event.payload.hex(" "),
                "is_08_81": len(event.payload) >= 2 and event.payload[:2] == b"\x08\x81",
                "epoch": _time_text(event.timestamp),
                "iso_utc": _iso_time(event.timestamp),
                **_urb_times(urb),
            }
        )

    jpeg_results: list[dict] = []
    cmd08_index = 0
    for transfer in if1_transfers:
        if transfer["command"] != 0x08:
            continue
        cmd08_index += 1
        assembled: bytes = transfer["assembled"]
        jpeg = analyze_jpeg(assembled)
        soi = jpeg["soi_offset"]
        eoi = jpeg["eoi_offset"]
        suffix = assembled[eoi + 2 :] if eoi is not None else b""
        reports: list[SegmentReport] = transfer["reports"]
        last_urb = reports[-1].urb
        last_out_time = (
            last_urb.completion.timestamp
            if last_urb.completion is not None
            else last_urb.event_time
        )
        related_in = []
        for report in in_reports:
            report_time = Fraction(report["epoch"])
            if report_time >= last_out_time:
                related_in.append(
                    {
                        "frame": report["frame"],
                        "epoch": report["epoch"],
                        "report_hex": report["report_hex"],
                        "is_08_81": report["is_08_81"],
                        "delta_from_last_out_complete_ms": _delta_ms(report_time, last_out_time),
                    }
                )
        first_08_81_time = next(
            (
                Fraction(report["epoch"])
                for report in in_reports
                if report["is_08_81"] and Fraction(report["epoch"]) >= last_out_time
            ),
            None,
        )
        for report in related_in:
            report["delta_from_08_81_ms"] = _delta_ms(
                Fraction(report["epoch"]),
                first_08_81_time,
            )
        result = {
            "index": cmd08_index,
            "segment_count_n": transfer["n"],
            "physical_report_count": len(reports),
            "assembled_length": len(assembled),
            "sequence_errors": transfer["sequence_errors"],
            "duplicate_indices": transfer["duplicates"],
            "controlwords": [_segment_json(report) for report in reports],
            "first_report": _segment_json(reports[0], include_report=True) if reports else None,
            "last_report": _segment_json(reports[-1], include_report=True) if reports else None,
            "assembled_sha256": hashlib.sha256(assembled).hexdigest(),
            "jpeg": jpeg,
            "jpeg_prefix_sha256": (
                hashlib.sha256(assembled[soi : eoi + 2]).hexdigest()
                if soi is not None and eoi is not None
                else None
            ),
            "suffix_length": len(suffix) if eoi is not None else None,
            "suffix_sha256": hashlib.sha256(suffix).hexdigest() if eoi is not None else None,
            "suffix_hex": suffix.hex(" ") if eoi is not None else None,
            "suffix_byte_counts": (
                {f"{byte:02x}": suffix.count(byte) for byte in sorted(set(suffix))}
                if eoi is not None
                else None
            ),
            "last_out_complete_epoch": _time_text(last_out_time),
            "last_out_complete_iso_utc": _iso_time(last_out_time),
            "following_interface1_in": related_in,
        }
        jpeg_results.append(result)
        if out_dir is not None:
            stem = f"if1-cmd08-{cmd08_index:03d}"
            (out_dir / f"{stem}.assembled.bin").write_bytes(assembled)
            if soi is not None and eoi is not None:
                (out_dir / f"{stem}.jpeg").write_bytes(assembled[soi : eoi + 2])
                (out_dir / f"{stem}.suffix.bin").write_bytes(suffix)

    interface0_results = []
    dangerous_commands = {0x02, 0x0A, 0x0B, 0x0C, 0x0D, 0x1B, 0x1C, 0x1F, 0x45, 0x86, 0x88, 0xFE, 0xFF}
    for index, transfer in enumerate(if0_transfers, start=1):
        assembled: bytes = transfer["assembled"]
        command = transfer["command"]
        interface0_results.append(
            {
                "index": index,
                "command": f"0x{command:02x}",
                "segment_count_n": transfer["n"],
                "physical_report_count": len(transfer["reports"]),
                "sequence_errors": transfer["sequence_errors"],
                "duplicate_indices": transfer["duplicates"],
                "controlwords": [_segment_json(report) for report in transfer["reports"]],
                "assembled_length": len(assembled),
                "assembled_sha256": hashlib.sha256(assembled).hexdigest(),
                "payload_first_32_hex": assembled[:32].hex(" "),
                "payload_last_32_hex": assembled[-32:].hex(" "),
                "config_0x108_candidate": (
                    int.from_bytes(assembled[:4], "little")
                    if command == 0x19 and len(assembled) >= 4
                    else None
                ),
                "safety_alert": command in dangerous_commands,
            }
        )

    interface0_in_results = []
    for index, transfer in enumerate(if0_in_transfers, start=1):
        assembled: bytes = transfer["assembled"]
        interface0_in_results.append(
            {
                "index": index,
                "command": f"0x{transfer['command']:02x}",
                "segment_count_n": transfer["n"],
                "physical_report_count": len(transfer["reports"]),
                "sequence_errors": transfer["sequence_errors"],
                "duplicate_indices": transfer["duplicates"],
                "controlwords": [_segment_json(report) for report in transfer["reports"]],
                "assembled_length": len(assembled),
                "assembled_sha256": hashlib.sha256(assembled).hexdigest(),
                "payload_first_32_hex": assembled[:32].hex(" "),
                "payload_last_32_hex": assembled[-32:].hex(" "),
            }
        )

    endpoint_counts: dict[str, int] = {}
    for urb in urbs:
        endpoint_counts[f"0x{urb.endpoint:02x}"] = endpoint_counts.get(f"0x{urb.endpoint:02x}", 0) + 1

    single_jpeg = jpeg_results[0] if len(jpeg_results) == 1 else None
    single_sof = single_jpeg["jpeg"]["sof"] if single_jpeg is not None else None
    relevant_urbs = [
        report.urb for report in if1_out
    ] + [
        urb
        for urb in urbs
        if urb.endpoint in {0x01, 0x82, 0x84} and urb.data_event is not None
    ]

    analysis = {
        "analyzer": "analyze_lcd_reference_capture.py",
        "capture": str(capture_path),
        "capture_sha256": hashlib.sha256(capture_path.read_bytes()).hexdigest(),
        "target": "0b05:1c7b",
        "target_instances": [
            {
                "bus": bus,
                "device_address": device,
                "descriptor": discovered.get((bus, device)),
            }
            for bus, device in sorted(targets)
        ],
        "record_counts": {
            "usbpcap_packets": len(packets),
            "target_events": len(target_events),
            "target_urbs": len(urbs),
            "endpoint_urbs": endpoint_counts,
            "incomplete_interrupt_urbs": len(incomplete_urbs),
        },
        "warnings": warnings,
        "interface1": {
            "out_reports_ep03": len(if1_out),
            "cmd08_transfers": jpeg_results,
            "all_in_reports_ep84": in_reports,
        },
        "interface0": {
            "out_reports_ep01": len(if0_out),
            "out_segmented_transfers": interface0_results,
            "in_reports_ep82": len(if0_in),
            "in_segmented_transfers": interface0_in_results,
        },
        "control_endpoint_events": [
            {
                "frame": event.frame,
                "epoch": _time_text(event.timestamp),
                "irp_id": f"0x{event.irp_id:016x}",
                "phase": event.phase,
                "stage": event.control_stage,
                "declared_data_length": event.declared_data_length,
                "captured_payload_length": len(event.payload),
                "payload_hex": event.payload.hex(" "),
            }
            for event in target_events
            if event.endpoint == 0 and event.transfer_type == 2
        ],
        "acceptance": {
            "exactly_one_complete_cmd08": (
                len(jpeg_results) == 1
                and not jpeg_results[0]["sequence_errors"]
                and jpeg_results[0]["physical_report_count"] == jpeg_results[0]["segment_count_n"]
            ),
            "target_descriptor_is_v49": bool(discovered)
            and all(
                discovered.get(target, {}).get("bcd_device") == "0049"
                for target in targets
            ),
            "no_truncated_frames": not truncated_frames,
            "all_payload_urbs_successful": all(
                urb.completion is not None and urb.completion.status == 0
                for urb in relevant_urbs
            ),
            "all_interface1_reports_full_size": not any(
                "EP 0x03" in warning for warning in warnings
            ),
            "all_interface1_in_reports_full_size": not any(
                "EP 0x84" in warning for warning in warnings
            ),
            "syntactic_jpeg_with_eoi": (
                single_jpeg is not None
                and single_jpeg["jpeg"]["soi_offset"] == 0
                and single_jpeg["jpeg"]["eoi_offset"] is not None
                and single_jpeg["jpeg"]["error"] is None
            ),
            "sof0_8bit_320x320": (
                single_sof is not None
                and single_sof["marker"] == "SOF0"
                and single_sof["precision"] == 8
                and single_sof["width"] == 320
                and single_sof["height"] == 320
            ),
            "segment_count_in_safe_range": (
                single_jpeg is not None
                and 2 <= single_jpeg["segment_count_n"] <= 200
            ),
            "suffix_present": (
                single_jpeg is not None
                and single_jpeg["suffix_length"] is not None
                and single_jpeg["suffix_length"] > 0
            ),
            "exactly_one_08_81": sum(report["is_08_81"] for report in in_reports) == 1,
            "no_interface0_safety_alert": not any(
                transfer["safety_alert"] for transfer in interface0_results
            ),
        },
    }
    return analysis


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline-Auswertung eines gespeicherten ASUS-LCD-USBPcap-Captures"
    )
    parser.add_argument("capture", type=Path, help="USBPcap-pcap oder -pcapng")
    parser.add_argument(
        "--device",
        action="append",
        type=parse_device,
        default=[],
        metavar="BUS:ADDRESS",
        help="Zieladresse, falls kein injizierter 0b05:1c7b-Descriptor vorliegt; wiederholbar",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="optional: Analyse-JSON sowie rekonstruierte JPEG-/Suffixdateien schreiben",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        packets, warnings = read_capture(args.capture)
        if args.out_dir is not None:
            args.out_dir.mkdir(parents=True, exist_ok=False)
        analysis = build_analysis(
            args.capture,
            packets,
            warnings,
            set(args.device),
            args.out_dir,
        )
        rendered = json.dumps(analysis, indent=2, ensure_ascii=False) + "\n"
        if args.out_dir is not None:
            (args.out_dir / "analysis.json").write_text(rendered, encoding="utf-8")
        else:
            sys.stdout.write(rendered)
        return 0
    except (CaptureError, OSError, ValueError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
