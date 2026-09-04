from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import system_sensors
import telemetry


class FakeHwmon:
    def __init__(self, root: Path) -> None:
        self.root = root

    def add(
        self,
        number: int,
        name: str,
        channels: tuple[tuple[int, str | None, str], ...],
        *,
        device_name: str | None = None,
    ) -> Path:
        directory = self.root / f"hwmon{number}"
        directory.mkdir()
        (directory / "name").write_text(f"{name}\n", encoding="ascii")
        for index, label, value in channels:
            (directory / f"temp{index}_input").write_text(value, encoding="ascii")
            if label is not None:
                (directory / f"temp{index}_label").write_text(
                    f"{label}\n", encoding="ascii"
                )
        if device_name is not None:
            device = self.root / "devices" / device_name
            device.mkdir(parents=True, exist_ok=True)
            (directory / "device").symlink_to(device, target_is_directory=True)
        return directory


class SystemSensorsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.hwmon = FakeHwmon(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_cpu_tdie_sensor_is_found(self) -> None:
        self.hwmon.add(7, "k10temp", ((2, "Tdie", "48250\n"),))
        snapshot = system_sensors.read_current_temperatures(self.root)
        self.assertIsNotNone(snapshot.cpu)
        assert snapshot.cpu is not None
        self.assertEqual(snapshot.cpu.sensor.label, "Tdie")
        self.assertEqual(snapshot.cpu.celsius, 48.25)
        self.assertIsNone(snapshot.cpu_package)

    def test_cpu_package_tctl_sensor_is_found_without_duplicate_cpu(self) -> None:
        self.hwmon.add(3, "k10temp", ((1, "Tctl", "51750"),))
        snapshot = system_sensors.read_current_temperatures(self.root)
        self.assertIsNone(snapshot.cpu)
        self.assertIsNotNone(snapshot.cpu_package)
        assert snapshot.cpu_package is not None
        self.assertEqual(snapshot.cpu_package.sensor.label, "Tctl")

    def test_gpu_edge_sensor_is_found(self) -> None:
        self.hwmon.add(12, "amdgpu", ((1, "edge", "43000"),))
        snapshot = system_sensors.read_current_temperatures(self.root)
        self.assertIsNotNone(snapshot.gpu)
        assert snapshot.gpu is not None
        self.assertEqual(snapshot.gpu.sensor.label, "edge")
        self.assertEqual(snapshot.gpu.celsius, 43.0)

    def test_multiple_labels_keep_roles_and_future_gpu_channels(self) -> None:
        self.hwmon.add(
            4,
            "k10temp",
            ((1, "Tctl", "60000"), (2, "Tdie", "57000"), (3, "Tccd1", "53000")),
        )
        self.hwmon.add(
            9,
            "amdgpu",
            ((1, "edge", "42000"), (2, "junction", "65000"), (3, "mem", "58000")),
        )
        discovered = system_sensors.discover_temperature_sensors(self.root)
        snapshot = system_sensors.read_current_temperatures(self.root)
        self.assertEqual([item.label for item in discovered.cpu], ["Tdie"])
        self.assertEqual([item.label for item in discovered.cpu_package], ["Tctl"])
        self.assertEqual(
            [item.label for item in discovered.cpu_channels],
            ["Tctl", "Tdie", "Tccd1"],
        )
        self.assertEqual([item.label for item in discovered.gpu], ["edge", "junction"])
        self.assertEqual(
            [item.label for item in discovered.gpu_channels],
            ["edge", "junction", "mem"],
        )
        assert snapshot.cpu is not None
        assert snapshot.cpu_package is not None
        assert snapshot.gpu is not None
        self.assertEqual(snapshot.cpu.sensor.label, "Tdie")
        self.assertEqual(snapshot.cpu_package.sensor.label, "Tctl")
        self.assertEqual(snapshot.gpu.sensor.label, "edge")

    def test_missing_sensors_are_unavailable(self) -> None:
        self.hwmon.add(0, "acpitz", ((1, "temp", "39000"),))
        self.assertEqual(
            system_sensors.read_current_temperatures(self.root),
            system_sensors.TemperatureSnapshot(),
        )

    def test_malformed_input_is_unavailable(self) -> None:
        self.hwmon.add(2, "k10temp", ((1, "Tctl", "not-a-temperature"),))
        snapshot = system_sensors.read_current_temperatures(self.root)
        self.assertIsNone(snapshot.cpu_package)

    def test_dynamic_hwmon_number_and_millidegree_conversion(self) -> None:
        self.hwmon.add(117, "k10temp", ((6, "Tdie", "42125"),))
        snapshot = system_sensors.read_current_temperatures(self.root)
        assert snapshot.cpu is not None
        self.assertEqual(snapshot.cpu.celsius, 42.125)
        self.assertEqual(snapshot.cpu.sensor.channel, "temp6")
        self.assertIn("hwmon117", str(snapshot.cpu.sensor.input_path))

    def test_multiple_devices_fall_through_unreadable_primary_value(self) -> None:
        self.hwmon.add(1, "amdgpu", ((1, "edge", "malformed"),))
        self.hwmon.add(8, "amdgpu", ((1, "edge", "44500"),))
        snapshot = system_sensors.read_current_temperatures(self.root)
        assert snapshot.gpu is not None
        self.assertEqual(snapshot.gpu.celsius, 44.5)
        self.assertIn("hwmon8", str(snapshot.gpu.sensor.input_path))

    def test_disappearing_input_becomes_unavailable(self) -> None:
        directory = self.hwmon.add(5, "k10temp", ((2, "Tdie", "47500"),))
        discovered = system_sensors.discover_temperature_sensors(self.root)
        self.assertEqual(len(discovered.cpu), 1)
        (directory / "temp2_input").unlink()
        self.assertIsNone(system_sensors.read_temperature(discovered.cpu[0]))
        self.assertIsNone(system_sensors.read_current_temperatures(self.root).cpu)

    def test_rediscovery_accepts_changed_hwmon_number(self) -> None:
        directory = self.hwmon.add(1, "k10temp", ((2, "Tdie", "41000"),))
        first = system_sensors.read_current_temperatures(self.root)
        assert first.cpu is not None
        directory.rename(self.root / "hwmon91")
        second = system_sensors.read_current_temperatures(self.root)
        assert second.cpu is not None
        self.assertEqual(second.cpu.celsius, 41.0)
        self.assertIn("hwmon91", str(second.cpu.sensor.input_path))

    def test_richer_gpu_profile_wins_independent_of_hwmon_number(self) -> None:
        self.hwmon.add(1, "amdgpu", ((1, "edge", "39000"),))
        self.hwmon.add(
            82,
            "amdgpu",
            (
                (1, "edge", "46000"),
                (2, "junction", "61000"),
                (3, "mem", "58000"),
            ),
        )
        snapshot = system_sensors.read_current_temperatures(self.root)
        assert snapshot.gpu is not None
        self.assertEqual(snapshot.gpu.celsius, 46.0)
        self.assertIn("hwmon82", str(snapshot.gpu.sensor.input_path))

    def test_lcd_sources_use_tctl_tccd1_and_configured_primary_gpu(self) -> None:
        self.hwmon.add(
            4,
            "k10temp",
            ((1, "Tctl", "51250"), (3, "Tccd1", "46750")),
        )
        self.hwmon.add(
            2,
            "amdgpu",
            ((1, "edge", "49000"), (2, "junction", "68000")),
            device_name="0000:03:00.0",
        )
        self.hwmon.add(
            3,
            "amdgpu",
            ((1, "edge", "41000"),),
            device_name="0000:0e:00.0",
        )
        snapshot = system_sensors.read_lcd_temperatures(self.root)
        assert snapshot.cpu_package is not None
        assert snapshot.cpu_ccd is not None
        assert snapshot.gpu is not None
        self.assertEqual(snapshot.cpu_package.sensor.label, "Tctl")
        self.assertEqual(snapshot.cpu_ccd.sensor.label, "Tccd1")
        self.assertEqual(snapshot.gpu.celsius, 49.0)
        self.assertEqual(snapshot.gpu.sensor.device_path.name, "0000:03:00.0")

    def test_lcd_source_does_not_fall_back_to_second_gpu(self) -> None:
        self.hwmon.add(
            3,
            "amdgpu",
            ((1, "edge", "41000"),),
            device_name="0000:0e:00.0",
        )
        snapshot = system_sensors.read_lcd_temperatures(self.root)
        self.assertIsNone(snapshot.gpu)

    def test_cpu_usage_uses_consecutive_proc_stat_deltas(self) -> None:
        path = self.root / "proc-stat"
        path.write_text("cpu 100 0 100 800 0 0 0 0\n", encoding="ascii")
        sampler = system_sensors.CpuUsageSampler(path)
        self.assertIsNone(sampler.sample())

        path.write_text("cpu 150 0 150 900 0 0 0 0\n", encoding="ascii")
        sample = sampler.sample()
        assert sample is not None
        self.assertEqual(sample.percent, 50.0)

        path.write_text("cpu 150 0 150 1100 0 0 0 0\n", encoding="ascii")
        idle = sampler.sample()
        assert idle is not None
        self.assertEqual(idle.percent, 0.0)

        path.write_text("cpu 250 0 250 1100 0 0 0 0\n", encoding="ascii")
        busy = sampler.sample()
        assert busy is not None
        self.assertEqual(busy.percent, 100.0)

    def test_cpu_usage_missing_and_malformed_are_unavailable(self) -> None:
        path = self.root / "missing-stat"
        sampler = system_sensors.CpuUsageSampler(path)
        self.assertIsNone(sampler.sample())
        path.write_text("not cpu counters\n", encoding="ascii")
        self.assertIsNone(sampler.sample())
        path.write_text("cpu 1 2 broken 4\n", encoding="ascii")
        self.assertIsNone(sampler.sample())

    def test_primary_gpu_usage_and_extra_temperatures_are_read_dynamically(self) -> None:
        self.hwmon.add(
            9,
            "amdgpu",
            ((1, "edge", "48000"), (2, "junction", "71000"), (3, "mem", "62000")),
            device_name="0000:03:00.0",
        )
        self.hwmon.add(
            2,
            "amdgpu",
            ((1, "edge", "39000"),),
            device_name="0000:0e:00.0",
        )
        (self.root / "devices" / "0000:03:00.0" / "gpu_busy_percent").write_text(
            "82\n", encoding="ascii"
        )
        (self.root / "devices" / "0000:0e:00.0" / "gpu_busy_percent").write_text(
            "17\n", encoding="ascii"
        )
        snapshot = system_sensors.read_lcd_temperatures(self.root)
        assert snapshot.gpu_usage is not None
        assert snapshot.gpu_hotspot is not None
        assert snapshot.gpu_memory is not None
        self.assertEqual(snapshot.gpu_usage.percent, 82.0)
        self.assertEqual(snapshot.gpu_hotspot.celsius, 71.0)
        self.assertEqual(snapshot.gpu_memory.celsius, 62.0)

    def test_gpu_usage_missing_malformed_and_out_of_range_are_unavailable(self) -> None:
        self.hwmon.add(
            4,
            "amdgpu",
            ((1, "edge", "48000"),),
            device_name="0000:03:00.0",
        )
        busy = self.root / "devices" / "0000:03:00.0" / "gpu_busy_percent"
        self.assertIsNone(system_sensors.read_lcd_temperatures(self.root).gpu_usage)
        for invalid in ("busy", "-1", "101"):
            with self.subTest(invalid=invalid):
                busy.write_text(invalid, encoding="ascii")
                self.assertIsNone(
                    system_sensors.read_lcd_temperatures(self.root).gpu_usage
                )

    def test_unreadable_gpu_usage_is_unavailable(self) -> None:
        self.hwmon.add(
            4,
            "amdgpu",
            ((1, "edge", "48000"),),
            device_name="0000:03:00.0",
        )
        busy = self.root / "devices" / "0000:03:00.0" / "gpu_busy_percent"
        busy.write_text("50", encoding="ascii")
        original = system_sensors._read_text

        def unreadable(path: Path) -> str | None:
            return None if path.name == "gpu_busy_percent" else original(path)

        with mock.patch.object(system_sensors, "_read_text", side_effect=unreadable):
            self.assertIsNone(system_sensors.read_lcd_temperatures(self.root).gpu_usage)

    def test_system_reader_skips_hwmon_for_cpu_usage_only(self) -> None:
        reader = system_sensors.SystemTelemetryReader(
            self.root, proc_stat_path=self.root / "proc-stat"
        )
        usage = system_sensors.PercentageValue(25.0, "/proc/stat")
        with (
            mock.patch.object(
                reader._cpu_usage, "sample", return_value=usage
            ) as cpu_sample,
            mock.patch.object(
                system_sensors,
                "read_lcd_metrics",
                side_effect=AssertionError("hwmon metrics read"),
            ) as read_metrics,
        ):
            snapshot = reader.sample(frozenset({telemetry.MetricId.CPU_USAGE}))

        self.assertIs(snapshot.cpu_usage, usage)
        cpu_sample.assert_called_once_with()
        read_metrics.assert_not_called()

    def test_selective_hwmon_read_touches_only_requested_metric_value(self) -> None:
        self.hwmon.add(
            9,
            "amdgpu",
            ((1, "edge", "48000"), (2, "junction", "71000"), (3, "mem", "62000")),
            device_name="0000:03:00.0",
        )
        observed_labels: list[str] = []
        original = system_sensors.read_temperature

        def observe(sensor: system_sensors.TemperatureSensor):
            observed_labels.append(sensor.label)
            return original(sensor)

        with mock.patch.object(
            system_sensors, "read_temperature", side_effect=observe
        ):
            snapshot = system_sensors.read_lcd_metrics(
                self.root, frozenset({telemetry.MetricId.GPU_MEMORY})
            )

        assert snapshot.gpu_memory is not None
        self.assertEqual(snapshot.gpu_memory.celsius, 62.0)
        self.assertEqual(observed_labels, ["mem"])
        self.assertIsNone(snapshot.gpu)
        self.assertIsNone(snapshot.gpu_hotspot)
        self.assertIsNone(snapshot.gpu_usage)


if __name__ == "__main__":
    unittest.main()
