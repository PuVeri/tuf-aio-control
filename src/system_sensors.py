#!/usr/bin/env python3
"""Read-only discovery and sampling of local Linux hwmon temperatures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_HWMON_ROOT = Path("/sys/class/hwmon")
DEFAULT_PRIMARY_GPU_PCI_ADDRESS = "0000:03:00.0"


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
class TemperatureSnapshot:
    cpu: TemperatureValue | None = None
    cpu_package: TemperatureValue | None = None
    cpu_ccd: TemperatureValue | None = None
    gpu: TemperatureValue | None = None


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
            discovered.gpu_channels,
            label="edge",
            device_name=primary_gpu_pci_address,
        ),
    )
