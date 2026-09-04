from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import system_sensors
import telemetry


class TelemetryModelTests(unittest.TestCase):
    def test_all_required_metric_ids_are_stable_and_unique(self) -> None:
        self.assertEqual(
            {definition.metric_id for definition in telemetry.METRIC_DEFINITIONS},
            set(telemetry.MetricId),
        )
        self.assertEqual(
            len({item.metric_id.value for item in telemetry.METRIC_DEFINITIONS}),
            len(telemetry.METRIC_DEFINITIONS),
        )
        self.assertEqual(
            [definition.lcd_label for definition in telemetry.METRIC_DEFINITIONS[:-1]],
            ["CPU", "GPU", "CPU PKG", "CPU CCD", "GPU TEMP", "GPU HOT", "GPU MEM"],
        )
        self.assertEqual(
            [definition.display_label for definition in telemetry.METRIC_DEFINITIONS[:-1]],
            [
                "CPU",
                "GPU",
                "CPU Package",
                "CPU CCD",
                "GPU Temperatur",
                "GPU Hotspot",
                "GPU Memory",
            ],
        )

    def test_units_availability_and_display_values(self) -> None:
        snapshot = system_sensors.TemperatureSnapshot(
            cpu_usage=system_sensors.PercentageValue(17.0, "/proc/stat")
        )
        metrics = system_sensors.metric_values(snapshot)
        self.assertEqual(metrics[telemetry.MetricId.CPU_USAGE].display_value, "17 %")
        self.assertEqual(metrics[telemetry.MetricId.CPU_PACKAGE].display_value, "—")
        self.assertFalse(metrics[telemetry.MetricId.CPU_PACKAGE].available)
        self.assertFalse(
            telemetry.MetricValue(
                telemetry.MetricId.GPU_USAGE, "GPU", math.nan, "%"
            ).available
        )

    def test_sensor_adapter_exposes_every_selectable_metric(self) -> None:
        cpu_sensor = system_sensors.TemperatureSensor(
            "k10temp", "Tctl", Path("/fake/cpu"), "temp1"
        )
        gpu_edge = system_sensors.TemperatureSensor(
            "amdgpu", "edge", Path("/fake/edge"), "temp1"
        )
        gpu_hotspot = system_sensors.TemperatureSensor(
            "amdgpu", "junction", Path("/fake/junction"), "temp2"
        )
        gpu_memory = system_sensors.TemperatureSensor(
            "amdgpu", "mem", Path("/fake/mem"), "temp3"
        )
        snapshot = system_sensors.TemperatureSnapshot(
            cpu_package=system_sensors.TemperatureValue(47.0, cpu_sensor),
            cpu_ccd=system_sensors.TemperatureValue(44.0, cpu_sensor),
            gpu=system_sensors.TemperatureValue(52.0, gpu_edge),
            gpu_hotspot=system_sensors.TemperatureValue(70.0, gpu_hotspot),
            gpu_memory=system_sensors.TemperatureValue(62.0, gpu_memory),
            cpu_usage=system_sensors.PercentageValue(17.0, "/proc/stat"),
            gpu_usage=system_sensors.PercentageValue(82.0, "gpu_busy_percent"),
        )
        metrics = system_sensors.metric_values(snapshot)
        self.assertEqual(set(metrics), set(telemetry.MetricId))
        self.assertEqual(
            {
                metrics[item].unit
                for item in telemetry.MetricId
                if item is not telemetry.MetricId.OFF
            },
            {"%", "°C"},
        )
        self.assertTrue(
            all(
                metrics[item].available
                for item in telemetry.MetricId
                if item is not telemetry.MetricId.OFF
            )
        )

    def test_invalid_metric_id_uses_explicit_fallback(self) -> None:
        self.assertIs(
            telemetry.parse_metric_id("obsolete", telemetry.MetricId.CPU_CCD),
            telemetry.MetricId.CPU_CCD,
        )


if __name__ == "__main__":
    unittest.main()
