#!/usr/bin/env python3
"""Production wiring for the explicitly enabled, bounded GUI refresh path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import lcd_refresh
import lcd_runtime_safety
import lcd_transport
from discover_device import HidrawInterface

# Temporary development policy for the first GUI live path. Replace this
# isolated profile with an explicitly reviewed production session policy later.
GUI_DEVELOPMENT_INTERVAL_SECONDS = 1.0
GUI_DEVELOPMENT_MAX_DURATION_SECONDS = 30.0
GUI_DEVELOPMENT_MAX_FRAMES = 30


class ProductionControllerFactoryError(RuntimeError):
    """Read-only discovery or a mandatory runtime safety gate failed."""


DeviceDiscovery = Callable[[], tuple[HidrawInterface | None, str]]
SenderFactory = Callable[[HidrawInterface], lcd_refresh.FrameSender]


class ControllerBuilder(Protocol):
    def __call__(
        self,
        plan: lcd_refresh.RefreshPlan,
        sender: lcd_refresh.FrameSender,
        *,
        frame_source: lcd_refresh.FrameSource,
    ) -> lcd_refresh.RefreshController: ...


def build_gui_development_plan(jpeg_bytes: bytes) -> lcd_refresh.RefreshPlan:
    """Build the fixed temporary 1 Hz, 30-second/30-frame GUI profile."""
    return lcd_refresh.RefreshPlan(
        frames=(lcd_refresh.RefreshFrame(jpeg_bytes),),
        transport_interval_seconds=GUI_DEVELOPMENT_INTERVAL_SECONDS,
        max_duration_seconds=GUI_DEVELOPMENT_MAX_DURATION_SECONDS,
        max_frames=GUI_DEVELOPMENT_MAX_FRAMES,
    )


def _production_sender(device: HidrawInterface) -> lcd_refresh.HidrawFrameSender:
    return lcd_refresh.HidrawFrameSender(
        device,
        extra_validator=lcd_runtime_safety.runtime_device_error,
    )


@dataclass(frozen=True)
class ProductionControllerFactory:
    """Discover and gate exactly one confirmed Interface-1 refresh session."""

    device_discovery: DeviceDiscovery = lcd_transport.discover_lcd_interface
    competing_writer_finder: lcd_runtime_safety.CompetingWriterFinder = (
        lcd_runtime_safety.find_competing_writers
    )
    sender_factory: SenderFactory = _production_sender
    controller_builder: ControllerBuilder = lcd_refresh.RefreshController

    def __call__(
        self, frame_source: lcd_refresh.FrameSource
    ) -> lcd_refresh.RefreshController:
        try:
            device, discovery_detail = self.device_discovery()
        except (OSError, RuntimeError, ValueError) as error:
            raise ProductionControllerFactoryError(
                f"LCD-Gerätesuche fehlgeschlagen: {error}"
            ) from error
        if device is None:
            raise ProductionControllerFactoryError(
                f"Kein eindeutiges LCD-Interface 1: {discovery_detail}"
            )

        gate_error = lcd_runtime_safety.runtime_device_error(
            device,
            competing_writer_finder=self.competing_writer_finder,
        )
        if gate_error is not None:
            raise ProductionControllerFactoryError(
                f"LCD-Safety-Gate fehlgeschlagen: {gate_error}"
            )

        snapshot = frame_source.snapshot()
        plan = build_gui_development_plan(snapshot.jpeg_bytes)
        sender = self.sender_factory(device)
        return self.controller_builder(
            plan,
            sender,
            frame_source=frame_source,
        )
