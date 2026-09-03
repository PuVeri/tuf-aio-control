#!/usr/bin/env python3
"""Stable, extensible metric identities shared by sensors, GUI and overlay."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class MetricId(str, Enum):
    CPU_USAGE = "cpu_usage"
    GPU_USAGE = "gpu_usage"
    CPU_PACKAGE = "cpu_package"
    CPU_CCD = "cpu_ccd"
    GPU_TEMPERATURE = "gpu_temperature"
    GPU_HOTSPOT = "gpu_hotspot"
    GPU_MEMORY = "gpu_memory"
    OFF = "off"


@dataclass(frozen=True)
class MetricDefinition:
    metric_id: MetricId
    display_label: str
    unit: str


METRIC_DEFINITIONS = (
    MetricDefinition(MetricId.CPU_USAGE, "CPU", "%"),
    MetricDefinition(MetricId.GPU_USAGE, "GPU", "%"),
    MetricDefinition(MetricId.CPU_PACKAGE, "CPU Package", "°C"),
    MetricDefinition(MetricId.CPU_CCD, "CPU CCD", "°C"),
    MetricDefinition(MetricId.GPU_TEMPERATURE, "GPU Temperatur", "°C"),
    MetricDefinition(MetricId.GPU_HOTSPOT, "GPU Hotspot", "°C"),
    MetricDefinition(MetricId.GPU_MEMORY, "GPU Memory", "°C"),
    MetricDefinition(MetricId.OFF, "Aus", ""),
)
METRIC_BY_ID = {definition.metric_id: definition for definition in METRIC_DEFINITIONS}


@dataclass(frozen=True)
class MetricValue:
    metric_id: MetricId
    display_label: str
    value: float | None
    unit: str
    source_label: str | None = None

    @property
    def available(self) -> bool:
        return self.value is not None and math.isfinite(self.value)

    @property
    def display_value(self) -> str:
        if not self.available:
            return "—"
        return f"{self.value:.0f} {self.unit}"


def unavailable(metric_id: MetricId) -> MetricValue:
    definition = METRIC_BY_ID[metric_id]
    return MetricValue(metric_id, definition.display_label, None, definition.unit)


def parse_metric_id(value: object, fallback: MetricId) -> MetricId:
    try:
        return MetricId(value)
    except (TypeError, ValueError):
        return fallback
