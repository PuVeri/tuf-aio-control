#!/usr/bin/env python3
"""Bounded, explicit and offline-testable scheduling for LCD frame refreshes."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

import lcd_transport

MAX_REFRESH_DURATION_SECONDS = 60.0
MAX_REFRESH_FRAME_COUNT = 500


class RefreshConfigurationError(ValueError):
    """A refresh plan violates a mandatory local safety bound."""


class RefreshStateError(RuntimeError):
    """A refresh controller was started or stopped in an invalid state."""


class RefreshStopReason(str, Enum):
    EXPLICIT_STOP = "explicit-stop"
    MAX_DURATION = "max-duration"
    MAX_FRAMES = "max-frames"
    SEND_ERROR = "send-error"
    INTERNAL_ERROR = "internal-error"


class FrameSender(Protocol):
    def __call__(self, jpeg: bytes) -> int:
        """Send exactly one complete frame and return its successful write count."""


WaitFunction = Callable[[threading.Event, float], bool]


@dataclass(frozen=True)
class RefreshFrame:
    """One fully prepared JPEG and its optional desired visible duration."""

    jpeg_bytes: bytes
    duration_seconds: float | None = None
    jpeg_info: lcd_transport.JpegInfo = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.jpeg_bytes, bytes):
            raise RefreshConfigurationError(
                "Refresh-JPEG muss als unveränderliche Bytes vorliegen"
            )
        try:
            info = lcd_transport.validate_jpeg(self.jpeg_bytes)
        except (lcd_transport.JpegValidationError, RuntimeError, ValueError) as error:
            raise RefreshConfigurationError(f"Ungültiger Refresh-Frame: {error}") from error
        if self.duration_seconds is not None:
            _require_positive_finite(self.duration_seconds, "Frameintervall")
        object.__setattr__(self, "jpeg_info", info)


@dataclass(frozen=True)
class RefreshPlan:
    """Immutable frames plus explicit transport and session limits."""

    frames: tuple[RefreshFrame, ...]
    transport_interval_seconds: float
    max_duration_seconds: float
    max_frames: int

    def __post_init__(self) -> None:
        if not isinstance(self.frames, tuple) or not self.frames:
            raise RefreshConfigurationError(
                "Mindestens ein unveränderlicher Refresh-Frame ist nötig"
            )
        if any(not isinstance(frame, RefreshFrame) for frame in self.frames):
            raise RefreshConfigurationError("RefreshPlan akzeptiert nur RefreshFrame-Einträge")
        _require_positive_finite(self.transport_interval_seconds, "Transportintervall")
        _require_positive_finite(self.max_duration_seconds, "Maximale Laufzeit")
        if self.max_duration_seconds > MAX_REFRESH_DURATION_SECONDS:
            raise RefreshConfigurationError(
                f"Maximale Laufzeit darf {MAX_REFRESH_DURATION_SECONDS:g} s nicht überschreiten"
            )
        if (
            isinstance(self.max_frames, bool)
            or not isinstance(self.max_frames, int)
            or not 1 <= self.max_frames <= MAX_REFRESH_FRAME_COUNT
        ):
            raise RefreshConfigurationError(
                f"Maximale Frameanzahl muss zwischen 1 und "
                f"{MAX_REFRESH_FRAME_COUNT} liegen"
            )
        if len(self.frames) > 1 and any(
            frame.duration_seconds is None for frame in self.frames
        ):
            raise RefreshConfigurationError(
                "Jeder Frame einer Animation benötigt ein explizites Frameintervall"
            )


@dataclass(frozen=True)
class RefreshResult:
    stop_reason: RefreshStopReason
    frames_sent: int
    elapsed_seconds: float
    transfer_durations: tuple[float, ...]
    frame_indices: tuple[int, ...]
    error: Exception | None = None


@dataclass(frozen=True)
class HidrawFrameSender:
    """Future device adapter; each call retains send_frame_once's finally-close."""

    device: lcd_transport.HidrawInterface

    def __call__(self, jpeg: bytes) -> int:
        return lcd_transport.send_frame_once(self.device, jpeg)


_ACTIVE_REFRESH_LOCK = threading.Lock()


def _require_positive_finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefreshConfigurationError(f"{label} muss eine Zahl sein")
    if not math.isfinite(value) or value <= 0:
        raise RefreshConfigurationError(f"{label} muss endlich und größer als null sein")


def _event_wait(event: threading.Event, timeout: float) -> bool:
    return event.wait(timeout)


class RefreshController:
    """Run one bounded refresh session on one non-daemon worker thread.

    The sender is synchronous. The controller never queues frames, never starts
    a second transfer while one is active and never retries a failed call.
    """

    def __init__(
        self,
        plan: RefreshPlan,
        sender: FrameSender,
        *,
        clock: Callable[[], float] = time.monotonic,
        wait_function: WaitFunction = _event_wait,
    ) -> None:
        if not callable(sender):
            raise TypeError("sender muss aufrufbar sein")
        if not callable(clock) or not callable(wait_function):
            raise TypeError("clock und wait_function müssen aufrufbar sein")
        self._plan = plan
        self._sender = sender
        self._clock = clock
        self._wait_function = wait_function
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._started = False
        self._result: RefreshResult | None = None

    @property
    def is_running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive()

    @property
    def result(self) -> RefreshResult | None:
        with self._state_lock:
            return self._result

    def start(self) -> None:
        """Explicitly start this controller exactly once."""
        with self._state_lock:
            if self._started:
                raise RefreshStateError("Diese Refreshsession wurde bereits gestartet")
            if not _ACTIVE_REFRESH_LOCK.acquire(blocking=False):
                raise RefreshStateError("Eine andere Refreshsession ist bereits aktiv")
            self._started = True
            thread = threading.Thread(
                target=self._thread_main,
                name="tuf-aio-lcd-refresh",
                daemon=False,
            )
            self._thread = thread
            try:
                thread.start()
            except BaseException:
                self._thread = None
                self._started = False
                _ACTIVE_REFRESH_LOCK.release()
                raise

    def stop(self, timeout: float | None = None) -> RefreshResult:
        """Explicitly request stop and join the worker."""
        with self._state_lock:
            if not self._started or self._thread is None:
                raise RefreshStateError("Refreshsession wurde nicht gestartet")
            thread = self._thread
        self._stop_event.set()
        thread.join(timeout)
        if thread.is_alive():
            raise TimeoutError("Refreshworker konnte innerhalb des Timeouts nicht stoppen")
        result = self.result
        if result is None:
            raise RefreshStateError("Refreshworker endete ohne Ergebnis")
        return result

    def wait(self, timeout: float | None = None) -> RefreshResult | None:
        """Join without requesting stop; return None only when timeout expires."""
        with self._state_lock:
            if not self._started or self._thread is None:
                raise RefreshStateError("Refreshsession wurde nicht gestartet")
            thread = self._thread
        thread.join(timeout)
        if thread.is_alive():
            return None
        return self.result

    def _thread_main(self) -> None:
        result: RefreshResult | None = None
        try:
            result = self._run_loop()
        except Exception as error:
            result = RefreshResult(
                stop_reason=RefreshStopReason.INTERNAL_ERROR,
                frames_sent=0,
                elapsed_seconds=0.0,
                transfer_durations=(),
                frame_indices=(),
                error=error,
            )
        finally:
            with self._state_lock:
                self._result = result
            _ACTIVE_REFRESH_LOCK.release()

    def _run_loop(self) -> RefreshResult:
        started_at = self._clock()
        deadline = started_at + self._plan.max_duration_seconds
        sent = 0
        frame_index = 0
        visible_since: float | None = None
        transfer_durations: list[float] = []
        frame_indices: list[int] = []

        while True:
            now = self._clock()
            if self._stop_event.is_set():
                return self._result_for(
                    RefreshStopReason.EXPLICIT_STOP,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )
            if now >= deadline:
                return self._result_for(
                    RefreshStopReason.MAX_DURATION,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )
            if sent >= self._plan.max_frames:
                return self._result_for(
                    RefreshStopReason.MAX_FRAMES,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )

            frame_changed = visible_since is None
            if visible_since is not None and len(self._plan.frames) > 1:
                duration = self._plan.frames[frame_index].duration_seconds
                if duration is None:
                    raise AssertionError("Animierter Frame ohne Dauer")
                if now - visible_since >= duration:
                    frame_index = (frame_index + 1) % len(self._plan.frames)
                    frame_changed = True

            frame = self._plan.frames[frame_index]
            transfer_started = self._clock()
            try:
                completed_writes = self._sender(frame.jpeg_bytes)
                if (
                    isinstance(completed_writes, bool)
                    or not isinstance(completed_writes, int)
                    or completed_writes != frame.jpeg_info.segment_count
                ):
                    raise lcd_transport.LcdTransportError(
                        f"Frame meldete {completed_writes} statt "
                        f"{frame.jpeg_info.segment_count} vollständigen Writes"
                    )
            except Exception as error:
                return self._result_for(
                    RefreshStopReason.SEND_ERROR,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                    error=error,
                )

            transfer_finished = self._clock()
            transfer_durations.append(max(0.0, transfer_finished - transfer_started))
            frame_indices.append(frame_index)
            sent += 1
            if frame_changed:
                visible_since = transfer_finished

            if transfer_finished >= deadline:
                return self._result_for(
                    RefreshStopReason.MAX_DURATION,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )
            if sent >= self._plan.max_frames:
                return self._result_for(
                    RefreshStopReason.MAX_FRAMES,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )

            next_start = transfer_started + self._plan.transport_interval_seconds
            wait_seconds = max(0.0, min(next_start, deadline) - transfer_finished)
            if wait_seconds > 0 and self._wait_function(self._stop_event, wait_seconds):
                return self._result_for(
                    RefreshStopReason.EXPLICIT_STOP,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )

    def _result_for(
        self,
        reason: RefreshStopReason,
        started_at: float,
        sent: int,
        transfer_durations: list[float],
        frame_indices: list[int],
        *,
        error: Exception | None = None,
    ) -> RefreshResult:
        return RefreshResult(
            stop_reason=reason,
            frames_sent=sent,
            elapsed_seconds=max(0.0, self._clock() - started_at),
            transfer_durations=tuple(transfer_durations),
            frame_indices=tuple(frame_indices),
            error=error,
        )
