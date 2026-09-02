from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import io
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = PROJECT_ROOT / "src" / "test_jpeg_0x08.py"
TRANSPORT_SOURCE_PATH = PROJECT_ROOT / "src" / "lcd_transport.py"
REFERENCE_PATH = PROJECT_ROOT / "tests" / "fixtures" / "lcd-0x08-reference.jpg"
REFERENCE_SHA256 = "5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866"
sys.path.insert(0, str(PROJECT_ROOT / "src"))
import lcd_transport as TRANSPORT
import set_lcd_image as SET_IMAGE

SPEC = importlib.util.spec_from_file_location("jpeg_0x08_tool", SOURCE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("test_jpeg_0x08.py konnte nicht geladen werden")
TOOL = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = TOOL
SPEC.loader.exec_module(TOOL)


def _segment(marker: int, payload: bytes) -> bytes:
    length = len(payload) + 2
    return bytes((0xFF, marker)) + length.to_bytes(2, "big") + payload


def _reference_header_segments(wanted_marker: int) -> bytes:
    data = REFERENCE_PATH.read_bytes()
    offset = 2
    result = bytearray()
    while offset < len(data):
        marker_start = offset
        if data[offset] != 0xFF:
            raise RuntimeError("unexpected reference marker")
        marker = data[offset + 1]
        offset += 2
        if marker == 0xDA:
            break
        length = int.from_bytes(data[offset : offset + 2], "big")
        end = offset + length
        if marker == wanted_marker:
            result.extend(data[marker_start:end])
        offset = end
    return bytes(result)


def _jpeg(
    *,
    width: int = 320,
    height: int = 320,
    sof_marker: int = 0xC0,
    component_specs: bytes = bytes((1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1)),
    total_length: int | None = None,
) -> bytes:
    app0 = _segment(
        0xE0,
        b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
    )
    dqt = _reference_header_segments(0xDB)
    dht = _reference_header_segments(0xC4)
    component_count = len(component_specs) // 3
    sof = _segment(
        sof_marker,
        bytes((8,))
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + bytes((component_count,))
        + component_specs,
    )
    sos = _segment(
        0xDA,
        bytes((3, 1, 0x00, 2, 0x11, 3, 0x11, 0x00, 0x3F, 0x00)),
    )
    prefix = b"\xff\xd8" + app0 + dqt + sof + dht + sos
    minimum_length = len(prefix) + 1 + 2
    target = total_length if total_length is not None else minimum_length
    if target < minimum_length:
        raise ValueError("test JPEG target too small")
    entropy = bytes((0x11,)) * (target - len(prefix) - 2)
    return prefix + entropy + b"\xff\xd9"


class PacketBuilderTests(unittest.TestCase):
    def test_segment_counts_n1_n2_n4(self) -> None:
        for length, expected in ((1, 1), (1021, 2), (3061, 4)):
            with self.subTest(length=length):
                segments = TOOL.build_transfer_segments(bytes((0xA5,)) * length)
                self.assertEqual(len(segments), expected)

    def test_padding_is_only_zero(self) -> None:
        jpeg = bytes((0xA5,)) * 1021
        segments = TOOL.build_transfer_segments(jpeg)
        self.assertEqual(segments[1].payload[:1], b"\xA5")
        self.assertEqual(segments[1].payload[1:], bytes(1019))

    def test_controlwords(self) -> None:
        segments = TOOL.build_transfer_segments(bytes((0x5A,)) * 3061)
        self.assertEqual(
            [segment.control for segment in segments],
            [
                b"\x08\x04\x00\x80",
                b"\x08\x01\x00\x00",
                b"\x08\x02\x00\x00",
                b"\x08\x03\x00\x00",
            ],
        )

    def test_every_hidraw_buffer_is_exactly_1025_bytes(self) -> None:
        for length in (1, 1021, 3061):
            with self.subTest(length=length):
                for segment in TOOL.build_transfer_segments(bytes(length)):
                    self.assertEqual(len(segment.wire_report), 1024)
                    self.assertEqual(len(segment.hidraw_buffer), 1025)
                    self.assertEqual(segment.hidraw_buffer[0], 0)
                    self.assertEqual(segment.hidraw_buffer[1], 0x08)

    def test_n_greater_than_four_is_rejected(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "N muss"):
            TOOL.build_transfer_segments(bytes(4081))


class JpegValidatorTests(unittest.TestCase):
    def test_accepts_conservative_sof0_jpeg(self) -> None:
        info = TOOL.validate_jpeg(_jpeg())
        self.assertEqual((info.width, info.height), (320, 320))
        self.assertEqual(info.sof_marker, 0xC0)
        self.assertEqual(info.precision, 8)
        self.assertEqual(len(info.components), 3)

    def test_rejects_invalid_geometry(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "320x320"):
            TOOL.validate_jpeg(_jpeg(width=319))

    def test_rejects_sof2(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "SOF2"):
            TOOL.validate_jpeg(_jpeg(sof_marker=0xC2))

    def test_rejects_sof1(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "Nur Baseline SOF0"):
            TOOL.validate_jpeg(_jpeg(sof_marker=0xC1))

    def test_rejects_other_sof_variant(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "Nur Baseline SOF0"):
            TOOL.validate_jpeg(_jpeg(sof_marker=0xC9))

    def test_rejects_malformed_marker_length(self) -> None:
        jpeg = bytearray(_jpeg())
        jpeg[4:6] = b"\xff\xff"
        with self.assertRaisesRegex(TOOL.JpegValidationError, "Dateiende"):
            TOOL.validate_jpeg(bytes(jpeg))

    def test_rejects_missing_eoi(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "EOI|Scandaten"):
            TOOL.validate_jpeg(_jpeg()[:-2])

    def test_rejects_data_after_eoi(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "nach JPEG-EOI"):
            TOOL.validate_jpeg(_jpeg() + b"\x00")

    def test_rejects_wrong_component_count(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "3 Komponenten"):
            TOOL.validate_jpeg(_jpeg(component_specs=bytes((1, 0x11, 0))))

    def test_rejects_wrong_sampling(self) -> None:
        specs = bytes((1, 0x11, 0, 2, 0x11, 1, 3, 0x11, 1))
        with self.assertRaisesRegex(TOOL.JpegValidationError, "4:2:0"):
            TOOL.validate_jpeg(_jpeg(component_specs=specs))

    def test_rejects_truncated_jfif_header(self) -> None:
        jpeg = _jpeg()
        app0_end = 2 + 2 + 2 + 14
        shortened = b"\xff\xd8" + _segment(0xE0, b"JFIF\x00") + jpeg[app0_end:]
        with self.assertRaisesRegex(TOOL.JpegValidationError, "vollständiger Header"):
            TOOL.validate_jpeg(shortened)

    def test_rejects_missing_quantization_tables(self) -> None:
        jpeg = _jpeg()
        dqt = _reference_header_segments(0xDB)
        without_dqt = jpeg.replace(dqt, b"", 1)
        with self.assertRaisesRegex(TOOL.JpegValidationError, "Quantisierungstabellen"):
            TOOL.validate_jpeg(without_dqt)

    def test_rejects_additional_app_marker(self) -> None:
        jpeg = _jpeg()
        with_app1 = jpeg[:20] + _segment(0xE1, b"Exif\x00\x00") + jpeg[20:]
        with self.assertRaisesRegex(TOOL.JpegValidationError, "Unzulässiger JPEG-Marker"):
            TOOL.validate_jpeg(with_app1)

    def test_rejects_jpeg_requiring_more_than_four_segments(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "N muss"):
            TOOL.validate_jpeg(_jpeg(total_length=4081))

    def test_reference_jpeg_is_frozen_and_valid(self) -> None:
        jpeg = REFERENCE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(jpeg).hexdigest(), REFERENCE_SHA256)
        info = TOOL.validate_jpeg(jpeg)
        self.assertEqual((info.width, info.height), (320, 320))
        self.assertEqual(info.sof_marker, 0xC0)
        self.assertEqual(info.precision, 8)
        self.assertEqual(len(info.components), 3)
        self.assertEqual(info.segment_count, 3)
        self.assertEqual(info.padding_length, 824)


class StaticSafetyTests(unittest.TestCase):
    def test_jpeg_sender_has_exactly_one_os_write_callsite(self) -> None:
        calls = []
        for path in (SOURCE_PATH, TRANSPORT_SOURCE_PATH, PROJECT_ROOT / "src" / "set_lcd_image.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            calls.extend(
                node
                for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "os"
                and node.func.attr == "write"
            )
        self.assertEqual(len(calls), 1)

    def test_default_preview_never_opens_hidraw(self) -> None:
        jpeg = _jpeg()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "explicit.jpg"
            path.write_bytes(jpeg)
            with (
                mock.patch.object(TOOL, "_select_target", return_value=(None, "offline")),
                mock.patch.object(TOOL.os, "open", side_effect=AssertionError("os.open called")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(TOOL.main([str(path)]), TOOL.EXIT_SUCCESS)

    def test_explicit_dry_run_never_opens_hidraw(self) -> None:
        jpeg = _jpeg()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "explicit.jpg"
            path.write_bytes(jpeg)
            with (
                mock.patch.object(TOOL, "_select_target", return_value=(None, "offline")),
                mock.patch.object(TOOL.os, "open", side_effect=AssertionError("os.open called")),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    TOOL.main(["--dry-run", str(path)]),
                    TOOL.EXIT_SUCCESS,
                )

    def test_help_never_opens_hidraw(self) -> None:
        with (
            mock.patch.object(TOOL.os, "open", side_effect=AssertionError("os.open called")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                TOOL.main(["--help"])
        self.assertEqual(raised.exception.code, 0)

    def test_dry_run_cannot_be_combined_with_risk_switch(self) -> None:
        with (
            mock.patch.object(TOOL.os, "open", side_effect=AssertionError("os.open called")),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                TOOL.main(["--dry-run", "--i-understand-the-risk", "unused.jpg"])
        self.assertEqual(raised.exception.code, 2)

    def test_risk_switch_cannot_be_abbreviated(self) -> None:
        with (
            mock.patch.object(TOOL.os, "open", side_effect=AssertionError("os.open called")),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                TOOL.main(["--i-understand", "unused.jpg"])
        self.assertEqual(raised.exception.code, 2)

    def test_non_regular_jpeg_input_is_rejected_before_device_selection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                mock.patch.object(
                    TOOL,
                    "_select_target",
                    side_effect=AssertionError("device selection called"),
                ),
                mock.patch.object(
                    TOOL.os,
                    "open",
                    side_effect=AssertionError("os.open called"),
                ),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(TOOL.main([directory]), TOOL.EXIT_INPUT)


class DeviceMetadataTests(unittest.TestCase):
    @staticmethod
    def _valid_device() -> object:
        return TOOL.HidrawInterface(
            device_path="/dev/hidraw-dynamic",
            sysfs_path="/sys/class/hidraw/hidraw-dynamic",
            interface_number=1,
            manufacturer="ASUS",
            product="TUF AIO",
            serial=None,
            vendor_id="0b05",
            product_id="1c7b",
            input_report_bytes=16,
            output_report_bytes=1024,
            feature_report_bytes=None,
            report_ids=(),
            readable=False,
            udev_properties={},
        )

    def test_accepts_only_exact_vid_and_pid(self) -> None:
        valid = self._valid_device()
        self.assertIsNone(TOOL._device_validation_error(valid))
        for changes in ({"vendor_id": "ffff"}, {"product_id": "ffff"}):
            with self.subTest(changes=changes):
                self.assertIsNotNone(
                    TOOL._device_validation_error(replace(valid, **changes))
                )

    def test_rejects_interface_other_than_one(self) -> None:
        device = replace(self._valid_device(), interface_number=0)
        self.assertIsNotNone(TOOL._device_validation_error(device))

    def test_rejects_wrong_report_sizes(self) -> None:
        valid = self._valid_device()
        for changes in (
            {"input_report_bytes": 440},
            {"output_report_bytes": 440},
        ):
            with self.subTest(changes=changes):
                self.assertIsNotNone(
                    TOOL._device_validation_error(replace(valid, **changes))
                )

    def test_rejects_numbered_report(self) -> None:
        device = replace(self._valid_device(), report_ids=(1,))
        self.assertIsNotNone(TOOL._device_validation_error(device))


class OfflineWriteControlFlowTests(unittest.TestCase):
    @staticmethod
    def _device() -> object:
        return TOOL.HidrawInterface(
            device_path="/dev/hidraw-never-opened",
            sysfs_path="/sys/class/hidraw/hidraw-never-opened",
            interface_number=1,
            manufacturer="ASUS",
            product="TUF AIO",
            serial=None,
            vendor_id="0b05",
            product_id="1c7b",
            input_report_bytes=16,
            output_report_bytes=1024,
            feature_report_bytes=None,
            report_ids=(),
            readable=False,
            udev_properties={},
        )

    def _run_with_write_mock(
        self, write_side_effect: object
    ) -> tuple[int, mock.Mock, mock.Mock]:
        jpeg = _jpeg(total_length=2041)
        segments = TOOL.build_transfer_segments(jpeg)
        write_mock = mock.Mock(side_effect=write_side_effect)
        close_mock = mock.Mock()
        with (
            mock.patch.object(TOOL.os, "access", return_value=True),
            mock.patch.object(TOOL.os, "open", return_value=123),
            mock.patch.object(TOOL.os, "write", write_mock),
            mock.patch.object(TOOL.os, "close", close_mock),
            mock.patch.object(TRANSPORT, "validate_open_target"),
            contextlib.redirect_stdout(io.StringIO()),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            result = TOOL._run_once(self._device(), jpeg, segments)
        return result, write_mock, close_mock

    def test_success_path_calls_write_exactly_n_times(self) -> None:
        result, write_mock, close_mock = self._run_with_write_mock(
            [1025, 1025, 1025]
        )
        self.assertEqual(result, TOOL.EXIT_SUCCESS)
        self.assertEqual(write_mock.call_count, 3)
        close_mock.assert_called_once_with(123)

    def test_short_write_stops_without_retry_or_following_segment(self) -> None:
        result, write_mock, close_mock = self._run_with_write_mock([1000, 1025, 1025])
        self.assertEqual(result, TOOL.EXIT_IO_ERROR)
        self.assertEqual(write_mock.call_count, 1)
        close_mock.assert_called_once_with(123)

    def test_write_exception_stops_without_retry(self) -> None:
        result, write_mock, close_mock = self._run_with_write_mock(
            OSError("offline injected write failure")
        )
        self.assertEqual(result, TOOL.EXIT_IO_ERROR)
        self.assertEqual(write_mock.call_count, 1)
        close_mock.assert_called_once_with(123)

    def test_error_after_one_success_stops_before_remaining_segments(self) -> None:
        result, write_mock, close_mock = self._run_with_write_mock(
            [1025, OSError("offline injected second-segment failure"), 1025]
        )
        self.assertEqual(result, TOOL.EXIT_IO_ERROR)
        self.assertEqual(write_mock.call_count, 2)
        close_mock.assert_called_once_with(123)

    def test_n_zero_is_rejected(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "größer als null"):
            TOOL.segment_count(0)

    def test_n_five_is_rejected(self) -> None:
        with self.assertRaisesRegex(TOOL.JpegValidationError, "N muss"):
            TOOL.segment_count(4081)


class ReusableTransportTests(unittest.TestCase):
    def test_reference_transfer_matches_successful_live_test_byte_for_byte(self) -> None:
        jpeg = REFERENCE_PATH.read_bytes()
        self.assertEqual(hashlib.sha256(jpeg).hexdigest(), REFERENCE_SHA256)

        segments = TRANSPORT.build_segments(jpeg)
        self.assertEqual(len(segments), 3)
        self.assertEqual(
            [segment.control for segment in segments],
            [
                b"\x08\x03\x00\x80",
                b"\x08\x01\x00\x00",
                b"\x08\x02\x00\x00",
            ],
        )
        self.assertTrue(all(len(segment.hidraw_buffer) == 1025 for segment in segments))
        self.assertEqual(segments[0].hidraw_buffer[:5], b"\x00\x08\x03\x00\x80")
        self.assertEqual(segments[1].hidraw_buffer[:5], b"\x00\x08\x01\x00\x00")
        self.assertEqual(segments[2].hidraw_buffer[:5], b"\x00\x08\x02\x00\x00")
        self.assertEqual(segments[0].payload, jpeg[:1020])
        self.assertEqual(segments[1].payload, jpeg[1020:2040])
        self.assertEqual(segments[2].payload[:196], jpeg[2040:])
        self.assertEqual(segments[2].payload[196:], bytes(824))

        reconstructed = b"".join(segment.payload for segment in segments)
        self.assertEqual(reconstructed[: len(jpeg)], jpeg)
        self.assertEqual(reconstructed[len(jpeg) :], bytes(824))

    def test_general_builder_covers_n1_n2_n3_n4(self) -> None:
        for length, expected in ((1, 1), (1021, 2), (2041, 3), (3061, 4)):
            with self.subTest(length=length):
                segments = TRANSPORT.build_segments(bytes((0xA5,)) * length)
                self.assertEqual(len(segments), expected)
                self.assertTrue(all(len(item.hidraw_buffer) == 1025 for item in segments))

    def test_general_builder_accepts_larger_bounded_segment_counts(self) -> None:
        for count in (5, 17, 200):
            with self.subTest(count=count):
                length = (count - 1) * TRANSPORT.PAYLOAD_BYTES + 1
                segments = TRANSPORT.build_segments(bytes((0x33,)) * length)
                self.assertEqual(len(segments), count)
                self.assertEqual(segments[0].control, bytes((0x08, count, 0, 0x80)))
                self.assertEqual(segments[-1].control, bytes((0x08, count - 1, 0, 0)))

    def test_general_builder_rejects_n201(self) -> None:
        with self.assertRaisesRegex(TRANSPORT.JpegValidationError, "N muss"):
            TRANSPORT.build_segments(bytes(200 * TRANSPORT.PAYLOAD_BYTES + 1))

    def test_general_builder_zero_pads_only_the_last_payload(self) -> None:
        jpeg = bytes((0x7E,)) * 2041
        segments = TRANSPORT.build_segments(jpeg)
        self.assertEqual(segments[0].payload, jpeg[:1020])
        self.assertEqual(segments[1].payload, jpeg[1020:2040])
        self.assertEqual(segments[2].payload[:1], b"\x7e")
        self.assertEqual(segments[2].payload[1:], bytes(1019))

    def test_general_validator_accepts_reference_fixture(self) -> None:
        info = TRANSPORT.validate_jpeg(REFERENCE_PATH.read_bytes())
        self.assertEqual(info.segment_count, 3)
        self.assertEqual(info.padding_length, 824)

    def test_general_validator_accepts_valid_large_jpeg(self) -> None:
        for count in (17, 200):
            with self.subTest(count=count):
                info = TRANSPORT.validate_jpeg(
                    _jpeg(total_length=(count - 1) * 1020 + 1)
                )
                self.assertEqual(info.segment_count, count)


class SingleImageCliTests(unittest.TestCase):
    @staticmethod
    def _device() -> object:
        return TRANSPORT.HidrawInterface(
            device_path="/dev/hidraw-never-opened",
            sysfs_path="/sys/class/hidraw/hidraw-never-opened",
            interface_number=1,
            manufacturer="ASUS",
            product="TUF AIO",
            serial=None,
            vendor_id="0b05",
            product_id="1c7b",
            input_report_bytes=16,
            output_report_bytes=1024,
            feature_report_bytes=None,
            report_ids=(),
            readable=False,
            udev_properties={},
        )

    def test_default_preview_never_opens_or_sends(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "single.jpg"
            path.write_bytes(_jpeg())
            with (
                mock.patch.object(
                    SET_IMAGE.transport,
                    "discover_lcd_interface",
                    return_value=(None, "offline"),
                ),
                mock.patch.object(
                    SET_IMAGE.transport.os,
                    "open",
                    side_effect=AssertionError("os.open called"),
                ),
                mock.patch.object(
                    SET_IMAGE.transport,
                    "send_frame_once",
                    side_effect=AssertionError("send_frame_once called"),
                ),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(SET_IMAGE.main([str(path)]), SET_IMAGE.EXIT_SUCCESS)

    def test_apply_requests_exactly_one_frame(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "single.jpg"
            path.write_bytes(_jpeg(total_length=2041))
            send_mock = mock.Mock(return_value=3)
            with (
                mock.patch.object(
                    SET_IMAGE.transport,
                    "discover_lcd_interface",
                    return_value=(self._device(), "gültig"),
                ),
                mock.patch.object(SET_IMAGE.transport, "send_frame_once", send_mock),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(
                    SET_IMAGE.main(["--apply", str(path)]),
                    SET_IMAGE.EXIT_SUCCESS,
                )
            send_mock.assert_called_once()

    def test_apply_switch_cannot_be_abbreviated(self) -> None:
        with (
            mock.patch.object(
                SET_IMAGE.transport.os,
                "open",
                side_effect=AssertionError("os.open called"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            with self.assertRaises(SystemExit) as raised:
                SET_IMAGE.main(["--app", "unused.jpg"])
        self.assertEqual(raised.exception.code, 2)

    def test_invalid_jpeg_stops_before_discovery_or_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.jpg"
            path.write_bytes(b"not a jpeg")
            with (
                mock.patch.object(
                    SET_IMAGE.transport,
                    "discover_lcd_interface",
                    side_effect=AssertionError("discovery called"),
                ),
                mock.patch.object(
                    SET_IMAGE.transport.os,
                    "open",
                    side_effect=AssertionError("os.open called"),
                ),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(SET_IMAGE.main([str(path)]), SET_IMAGE.EXIT_INPUT)


if __name__ == "__main__":
    unittest.main()
