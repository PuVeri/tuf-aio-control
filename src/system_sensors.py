#!/usr/bin/env python3
"""Read-only discovery and nonblocking sampling of local Linux telemetry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import telemetry

DEFAULT_HWMON_ROOT = Path("/sys/class/hwmon")
DEFAULT_PRIMARY_GPU_PCI_ADDRESS = "0000:03:00.0"
DEFAULT_PROC_STAT_PATH = Path("/proc/stat")


@dataclass(frozen=True)
class TemperatureSensor:
    hwmon_name: str
    label: str
    input_path: Path
    channel: str
    device_path: Path | None = None


@dataclass(frozen=True)
class DiscoveredTemperatureSensors:
    cpu: tuple[TemperatureSensor, ...] = ()
    cpu_package: tuple[TemperatureSensor, ...] = ()
    cpu_channels: tuple[TemperatureSensor, ...] = ()
    gpu: tuple[TemperatureSensor, ...] = ()
    gpu_channels: tuple[TemperatureSensor, ...] = ()


@dataclass(frozen=True)
class TemperatureValue:
    celsius: float
    sensor: TemperatureSensor


@dataclass(frozen=True)
class PercentageValue:
    percent: float
    source_label: str


@dataclass(frozen=True)
class TemperatureSnapshot:
    cpu: TemperatureValue | None = None
    cpu_package: TemperatureValue | None = None
    cpu_ccd: TemperatureValue | None = None
    gpu: TemperatureValue | None = None
    gpu_hotspot: TemperatureValue | None = None
    gpu_memory: TemperatureValue | None = None
    cpu_usage: PercentageValue | None = None
    gpu_usage: PercentageValue | None = None


@dataclass(frozen=True)
class CpuTimes:
    total: int
    idle: int


def parse_cpu_times(text: str) -> CpuTimes | None:
    """Parse aggregate /proc/stat CPU counters without treating them as percent."""
    lines = text.splitlines()
    first_line = lines[0] if lines else ""
    fields = first_line.split()
    if len(fields) < 5 or fields[0] != "cpu":
        return None
    try:
        counters = [int(value, 10) for value in fields[1:9]]
    except ValueError:
        return None
    if len(counters) < 4 or any(value < 0 for value in counters):
        return None
    idle = counters[3] + (counters[4] if len(counters) > 4 else 0)
    return CpuTimes(total=sum(counters), idle=idle)


class CpuUsageSampler:
    """Calculate total CPU usage from consecutive nonblocking /proc/stat samples."""

    def __init__(self, path: Path = DEFAULT_PROC_STAT_PATH) -> None:
        self.path = path
        self._previous: CpuTimes | None = None

    def sample(self) -> PercentageValue | None:
        raw = _read_text(self.path)
        if raw is None:
            return None
        current = parse_cpu_times(raw)
        if current is None:
            return None
        previous = self._previous
        self._previous = current
        if previous is None:
            return None
        total_delta = current.total - previous.total
        idle_delta = current.idle - previous.idle
        if total_delta <= 0 or idle_delta < 0:
            return None
        percent = 100.0 * (total_delta - min(idle_delta, total_delta)) / total_delta
        return PercentageValue(max(0.0, min(100.0, percent)), str(self.path))


def _read_text(path: Path) -> str | None:
    try:
        value = path.read_text(encoding="ascii", errors="strict").strip()
    except (OSError, UnicodeError):
        return None
    return value or None


def _channel_number(path: Path) -> int:
    name = path.name
    digits = name.removeprefix("temp").removesuffix("_input")
    try:
        return int(digits)
    except ValueError:
        return 1 << 30


def _label_key(label: str) -> str:
    return " ".join(label.casefold().replace("_", " ").split())


def _device_path(directory: Path) -> Path | None:
    try:
        return (directory / "device").resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def _discover_hwmon_channels(
    directory: Path, hwmon_name: str
) -> tuple[TemperatureSensor, ...]:
    sensors: list[TemperatureSensor] = []
    try:
        inputs = sorted(
            directory.glob("temp*_input"),
            key=lambda path: (_channel_number(path), path.name),
        )
    except OSError:
        return ()
    device_path = _device_path(directory)
    for input_path in inputs:
        channel = input_path.name.removesuffix("_input")
        label = _read_text(directory / f"{channel}_label") or channel
        sensors.append(
            TemperatureSensor(hwmon_name, label, input_path, channel, device_path)
        )
    return tuple(sensors)


def _cpu_role(label: str) -> tuple[str, int] | None:
    key = _label_key(label)
    cpu_priorities = {
        "tdie": 0,
        "cpu": 1,
        "cpu temp": 2,
        "cpu temperature": 3,
    }
    package_priorities = {
        "tctl": 0,
        "tctl/tdie": 1,
        "cpu package": 2,
        "package": 3,
        "package id 0": 4,
    }
    if key in cpu_priorities:
        return "cpu", cpu_priorities[key]
    if key in package_priorities or key.startswith("package id "):
        return "cpu_package", package_priorities.get(key, 5)
    return None


def _gpu_priority(label: str) -> int | None:
    key = _label_key(label)
    priorities = {
        "edge": 0,
        "gpu": 1,
        "gpu temp": 2,
        "gpu temperature": 3,
        "junction": 4,
        "hotspot": 5,
    }
    return priorities.get(key)


def discover_temperature_sensors(
    hwmon_root: Path = DEFAULT_HWMON_ROOT,
) -> DiscoveredTemperatureSensors:
    """Rediscover supported temperature channels without fixed hwmon numbers."""
    cpu: list[tuple[int, int, str, int, TemperatureSensor]] = []
    cpu_package: list[tuple[int, int, str, int, TemperatureSensor]] = []
    cpu_channels: list[tuple[str, TemperatureSensor]] = []
    gpu: list[tuple[int, int, str, int, TemperatureSensor]] = []
    gpu_channels: list[tuple[str, TemperatureSensor]] = []

    try:
        directories = sorted(hwmon_root.glob("hwmon*"), key=lambda path: path.name)
    except OSError:
        directories = []

    for directory in directories:
        hwmon_name = _read_text(directory / "name")
        if hwmon_name not in {"k10temp", "amdgpu"}:
            continue
        channels = _discover_hwmon_channels(directory, hwmon_name)
        device_key = (
            str(channels[0].device_path or directory) if channels else str(directory)
        )
        for sensor in channels:
            if hwmon_name == "k10temp":
                cpu_channels.append((device_key, sensor))
                role = _cpu_role(sensor.label)
                if role is None:
                    continue
                target, priority = role
                candidate = (
                    priority,
                    0,
                    device_key,
                    _channel_number(sensor.input_path),
                    sensor,
                )
                if target == "cpu":
                    cpu.append(candidate)
                else:
                    cpu_package.append(candidate)
            else:
                gpu_channels.append((device_key, sensor))
                priority = _gpu_priority(sensor.label)
                if priority is not None:
                    gpu.append(
                        (
                            priority,
                            -len(channels),
                            device_key,
                            _channel_number(sensor.input_path),
                            sensor,
                        )
                    )

    def ordered(
        candidates: list[tuple[int, int, str, int, TemperatureSensor]],
    ) -> tuple[TemperatureSensor, ...]:
        return tuple(
            item[4] for item in sorted(candidates, key=lambda item: item[:4])
        )

    def all_channels(
        candidates: list[tuple[str, TemperatureSensor]],
    ) -> tuple[TemperatureSensor, ...]:
        return tuple(
            sensor
            for _, sensor in sorted(
                candidates,
                key=lambda item: (
                    item[0],
                    _channel_number(item[1].input_path),
                    item[1].channel,
                ),
            )
        )

    return DiscoveredTemperatureSensors(
        cpu=ordered(cpu),
        cpu_package=ordered(cpu_package),
        cpu_channels=all_channels(cpu_channels),
        gpu=ordered(gpu),
        gpu_channels=all_channels(gpu_channels),
    )


def read_temperature(sensor: TemperatureSensor) -> TemperatureValue | None:
    """Read one millidegree-Celsius sysfs value, returning unavailable on error."""
    raw = _read_text(sensor.input_path)
    if raw is None:
        return None
    try:
        millidegrees = int(raw, 10)
    except ValueError:
        return None
    if not -273_150 <= millidegrees <= 300_000:
        return None
    return TemperatureValue(millidegrees / 1000.0, sensor)


def _first_available(
    candidates: tuple[TemperatureSensor, ...],
) -> TemperatureValue | None:
    for sensor in candidates:
        value = read_temperature(sensor)
        if value is not None:
            return value
    return None


def _read_matching_channel(
    channels: tuple[TemperatureSensor, ...],
    *,
    label: str,
    device_name: str | None = None,
) -> TemperatureValue | None:
    wanted_label = _label_key(label)
    for sensor in channels:
        if _label_key(sensor.label) != wanted_label:
            continue
        if device_name is not None and (
            sensor.device_path is None or sensor.device_path.name != device_name
        ):
            continue
        value = read_temperature(sensor)
        if value is not None:
            return value
    return None


def read_current_temperatures(
    hwmon_root: Path = DEFAULT_HWMON_ROOT,
) -> TemperatureSnapshot:
    """Rediscover on every sample so renumbering and disappearing sensors are safe."""
    discovered = discover_temperature_sensors(hwmon_root)
    cpu = _first_available(discovered.cpu)
    cpu_package = _first_available(discovered.cpu_package)
    if (
        cpu is not None
        and cpu_package is not None
        and cpu.sensor.input_path == cpu_package.sensor.input_path
    ):
        cpu_package = None
    return TemperatureSnapshot(
        cpu=cpu,
        cpu_package=cpu_package,
        gpu=_first_available(discovered.gpu),
    )


def read_lcd_temperatures(
    hwmon_root: Path = DEFAULT_HWMON_ROOT,
    *,
    primary_gpu_pci_address: str = DEFAULT_PRIMARY_GPU_PCI_ADDRESS,
) -> TemperatureSnapshot:
    """Read the explicit default sources used by the LCD temperature overlay."""
    discovered = discover_temperature_sensors(hwmon_root)
    primary_gpu_channels = tuple(
        sensor
        for sensor in discovered.gpu_channels
        if sensor.device_path is not None
        and sensor.device_path.name == primary_gpu_pci_address
    )
    return TemperatureSnapshot(
        cpu=_first_available(discovered.cpu),
        cpu_package=_read_matching_channel(
            discovered.cpu_channels,
            label="Tctl",
        ),
        cpu_ccd=_read_matching_channel(
            discovered.cpu_channels,
            label="Tccd1",
        ),
        gpu=_read_matching_channel(
            primary_gpu_channels,
            label="edge",
        ),
        gpu_hotspot=_read_matching_channel(primary_gpu_channels, label="junction")
        or _read_matching_channel(primary_gpu_channels, label="hotspot"),
        gpu_memory=_read_matching_channel(primary_gpu_channels, label="mem"),
        gpu_usage=_read_gpu_usage(primary_gpu_channels),
    )


def _read_gpu_usage(
    primary_gpu_channels: tuple[TemperatureSensor, ...],
) -> PercentageValue | None:
    device_paths = sorted(
        {
            sensor.device_path
            for sensor in primary_gpu_channels
            if sensor.device_path is not None
        },
        key=str,
    )
    if not device_paths:
        return None
    path = device_paths[0] / "gpu_busy_percent"
    raw = _read_text(path)
    if raw is None:
        return None
    try:
        percent = int(raw, 10)
    except ValueError:
        return None
    if not 0 <= percent <= 100:
        return None
    return PercentageValue(float(percent), str(path))


class SystemTelemetryReader:
    """Stateful callable combining hwmon with consecutive CPU counter samples."""

    def __init__(
        self,
        hwmon_root: Path = DEFAULT_HWMON_ROOT,
        *,
        proc_stat_path: Path = DEFAULT_PROC_STAT_PATH,
        primary_gpu_pci_address: str = DEFAULT_PRIMARY_GPU_PCI_ADDRESS,
    ) -> None:
        self._hwmon_root = hwmon_root
        self._primary_gpu_pci_address = primary_gpu_pci_address
        self._cpu_usage = CpuUsageSampler(proc_stat_path)

    def __call__(self) -> TemperatureSnapshot:
        temperatures = read_lcd_temperatures(
            self._hwmon_root,
            primary_gpu_pci_address=self._primary_gpu_pci_address,
        )
        return TemperatureSnapshot(
            cpu=temperatures.cpu,
            cpu_package=temperatures.cpu_package,
            cpu_ccd=temperatures.cpu_ccd,
            gpu=temperatures.gpu,
            gpu_hotspot=temperatures.gpu_hotspot,
            gpu_memory=temperatures.gpu_memory,
            cpu_usage=self._cpu_usage.sample(),
            gpu_usage=temperatures.gpu_usage,
        )

    def sample(
        self, metric_ids: frozenset[telemetry.MetricId]
    ) -> TemperatureSnapshot:
        """Read only the sensor values required by the selected LCD metrics."""
        temperature_ids = {
            telemetry.MetricId.CPU_PACKAGE,
            telemetry.MetricId.CPU_CCD,
            telemetry.MetricId.GPU_TEMPERATURE,
            telemetry.MetricId.GPU_HOTSPOT,
            telemetry.MetricId.GPU_MEMORY,
            telemetry.MetricId.GPU_USAGE,
        }
        needed_temperatures = metric_ids & temperature_ids
        temperatures = (
            read_lcd_metrics(
                self._hwmon_root,
                needed_temperatures,
                primary_gpu_pci_address=self._primary_gpu_pci_address,
            )
            if needed_temperatures
            else TemperatureSnapshot()
        )
        return TemperatureSnapshot(
            cpu_package=temperatures.cpu_package,
            cpu_ccd=temperatures.cpu_ccd,
            gpu=temperatures.gpu,
            gpu_hotspot=temperatures.gpu_hotspot,
            gpu_memory=temperatures.gpu_memory,
            cpu_usage=(
                self._cpu_usage.sample()
                if telemetry.MetricId.CPU_USAGE in metric_ids
                else None
            ),
            gpu_usage=temperatures.gpu_usage,
        )


def read_lcd_metrics(
    hwmon_root: Path,
    metric_ids: frozenset[telemetry.MetricId],
    *,
    primary_gpu_pci_address: str = DEFAULT_PRIMARY_GPU_PCI_ADDRESS,
) -> TemperatureSnapshot:
    """Read only requested LCD metrics after one shared hwmon discovery."""
    discovered = discover_temperature_sensors(hwmon_root)
    primary_gpu_channels = tuple(
        sensor
        for sensor in discovered.gpu_channels
        if sensor.device_path is not None
        and sensor.device_path.name == primary_gpu_pci_address
    )
    return TemperatureSnapshot(
        cpu_package=(
            _read_matching_channel(discovered.cpu_channels, label="Tctl")
            if telemetry.MetricId.CPU_PACKAGE in metric_ids
            else None
        ),
        cpu_ccd=(
            _read_matching_channel(discovered.cpu_channels, label="Tccd1")
            if telemetry.MetricId.CPU_CCD in metric_ids
            else None
        ),
        gpu=(
            _read_matching_channel(primary_gpu_channels, label="edge")
            if telemetry.MetricId.GPU_TEMPERATURE in metric_ids
            else None
        ),
        gpu_hotspot=(
            _read_matching_channel(primary_gpu_channels, label="junction")
            or _read_matching_channel(primary_gpu_channels, label="hotspot")
            if telemetry.MetricId.GPU_HOTSPOT in metric_ids
            else None
        ),
        gpu_memory=(
            _read_matching_channel(primary_gpu_channels, label="mem")
            if telemetry.MetricId.GPU_MEMORY in metric_ids
            else None
        ),
        gpu_usage=(
            _read_gpu_usage(primary_gpu_channels)
            if telemetry.MetricId.GPU_USAGE in metric_ids
            else None
        ),
    )


def metric_values(
    snapshot: TemperatureSnapshot,
) -> dict[telemetry.MetricId, telemetry.MetricValue]:
    """Adapt sensor-specific readings to stable, renderer-independent metrics."""
    values: dict[telemetry.MetricId, telemetry.MetricValue] = {}

    def temperature_metric(
        metric_id: telemetry.MetricId,
        reading: TemperatureValue | None,
    ) -> None:
        definition = telemetry.METRIC_BY_ID[metric_id]
        source = None
        value = None
        if reading is not None:
            value = reading.celsius
            source = f"{reading.sensor.hwmon_name} · {reading.sensor.label}"
        values[metric_id] = telemetry.MetricValue(
            metric_id, definition.display_label, value, definition.unit, source
        )

    def percentage_metric(
        metric_id: telemetry.MetricId,
        reading: PercentageValue | None,
    ) -> None:
        definition = telemetry.METRIC_BY_ID[metric_id]
        values[metric_id] = telemetry.MetricValue(
            metric_id,
            definition.display_label,
            reading.percent if reading is not None else None,
            definition.unit,
            reading.source_label if reading is not None else None,
        )

    percentage_metric(telemetry.MetricId.CPU_USAGE, snapshot.cpu_usage)
    percentage_metric(telemetry.MetricId.GPU_USAGE, snapshot.gpu_usage)
    temperature_metric(telemetry.MetricId.CPU_PACKAGE, snapshot.cpu_package)
    temperature_metric(telemetry.MetricId.CPU_CCD, snapshot.cpu_ccd)
    temperature_metric(telemetry.MetricId.GPU_TEMPERATURE, snapshot.gpu)
    temperature_metric(telemetry.MetricId.GPU_HOTSPOT, snapshot.gpu_hotspot)
    temperature_metric(telemetry.MetricId.GPU_MEMORY, snapshot.gpu_memory)
    values[telemetry.MetricId.OFF] = telemetry.unavailable(telemetry.MetricId.OFF)
    return values
