#!/usr/bin/env python3
"""Production wiring for the explicitly started GUI refresh path."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import lcd_refresh
import lcd_runtime_safety
import lcd_transport
import refresh_diagnostics
from discover_device import HidrawInterface

# The bounded development profile remains available to offline tests and tools.
GUI_DEVELOPMENT_INTERVAL_SECONDS = 1.0
GUI_DEVELOPMENT_MAX_DURATION_SECONDS = 30.0
GUI_DEVELOPMENT_MAX_FRAMES = 30
GUI_PRODUCTION_INTERVAL_SECONDS = 1.0


class ProductionControllerFactoryError(RuntimeError):
    """Read-only discovery or a mandatory runtime safety gate failed."""


DeviceDiscovery = Callable[[], tuple[HidrawInterface | None, str]]
SenderFactory = Callable[
    [HidrawInterface, refresh_diagnostics.RefreshDiagnostics],
    lcd_refresh.FrameSender,
]


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


def build_gui_production_plan(
    jpeg_bytes: bytes,
    *,
    transport_interval_seconds: float = GUI_PRODUCTION_INTERVAL_SECONDS,
) -> lcd_refresh.RefreshPlan:
    """Build an unlimited GUI plan with the selected safe content cadence."""
    return lcd_refresh.RefreshPlan(
        frames=(lcd_refresh.RefreshFrame(jpeg_bytes),),
        transport_interval_seconds=transport_interval_seconds,
        max_duration_seconds=None,
        max_frames=None,
    )


def _production_sender(
    device: HidrawInterface,
    diagnostics: refresh_diagnostics.RefreshDiagnostics,
) -> lcd_refresh.PersistentHidrawFrameSender:
    return lcd_refresh.PersistentHidrawFrameSender(
        device,
        # Repeat the complete gate immediately around the one session open;
        # unlike the legacy path it is never rerun between segment writes.
        extra_validator=lcd_runtime_safety.runtime_device_error,
        diagnostics=diagnostics,
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
        diagnostics = refresh_diagnostics.diagnostics_for(frame_source)
        diagnostics.record("production_factory_entered")
        try:
            device, discovery_detail = self.device_discovery()
        except Exception as error:
            diagnostics.record("safety_gates_failed", phase="device_discovery")
            diagnostics.record_exception("device_discovery", error)
            wrapped = ProductionControllerFactoryError(
                f"LCD-Gerätesuche fehlgeschlagen: {error}"
            )
            raise wrapped from error
        if device is None:
            error = ProductionControllerFactoryError(
                f"Kein eindeutiges LCD-Interface 1: {discovery_detail}"
            )
            diagnostics.record("safety_gates_failed", phase="device_discovery")
            diagnostics.record_exception("device_discovery", error)
            raise error

        diagnostics.record(
            "hidraw_path_selected",
            device_path=device.device_path,
            vendor_id=device.vendor_id,
            product_id=device.product_id,
            interface_number=device.interface_number,
        )

        try:
            gate_error = lcd_runtime_safety.runtime_device_error(
                device,
                competing_writer_finder=self.competing_writer_finder,
            )
        except Exception as error:
            diagnostics.record("safety_gates_failed", phase="runtime_safety")
            diagnostics.record_exception("runtime_safety", error)
            raise ProductionControllerFactoryError(
                f"LCD-Safety-Gate konnte nicht geprüft werden: {error}"
            ) from error
        if gate_error is not None:
            error = ProductionControllerFactoryError(
                f"LCD-Safety-Gate fehlgeschlagen: {gate_error}"
            )
            diagnostics.record("safety_gates_failed", phase="runtime_safety")
            diagnostics.record_exception("runtime_safety", error)
            raise error
        diagnostics.record("safety_gates_passed")

        try:
            snapshot = frame_source.snapshot()
            diagnostics.record(
                "factory_initial_snapshot",
                generation=snapshot.generation,
            )
            source_interval = getattr(
                frame_source,
                "transport_interval_seconds",
                None,
            )
            plan = build_gui_production_plan(
                snapshot.jpeg_bytes,
                transport_interval_seconds=(
                    GUI_PRODUCTION_INTERVAL_SECONDS
                    if source_interval is None
                    else source_interval
                ),
            )
            diagnostics.record(
                "refresh_plan_created",
                interval_seconds=plan.transport_interval_seconds,
                max_duration_seconds=plan.max_duration_seconds,
                max_frames=plan.max_frames,
            )
            sender = self.sender_factory(device, diagnostics)
            diagnostics.record("production_factory_created")
            controller = self.controller_builder(
                plan,
                sender,
                frame_source=frame_source,
            )
            diagnostics.record("refresh_controller_created")
            return controller
        except Exception as error:
            diagnostics.record_exception("controller_creation", error)
            raise
