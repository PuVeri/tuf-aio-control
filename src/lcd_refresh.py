#!/usr/bin/env python3
"""Explicit and offline-testable scheduling for LCD frame refreshes."""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Protocol

import lcd_transport
import refresh_diagnostics

MAX_REFRESH_DURATION_SECONDS = 60.0
MAX_REFRESH_FRAME_COUNT = 500
MAX_RESULT_HISTORY_FRAMES = 1024

# Offline safety profile for the separately authorized first live refresh test.
# Constructing this plan performs no device access and starts no worker.
FIRST_REFRESH_REFERENCE_SHA256 = (
    "5a1ca416974481eda228e5d69bc044c3556fd1325f0de1b12ed3ff458b584866"
)
FIRST_REFRESH_INTERVAL_SECONDS = 1.0
FIRST_REFRESH_MAX_DURATION_SECONDS = 6.0
FIRST_REFRESH_MAX_FRAMES = 5


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
NextFrameCallback = Callable[[], None]


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
class FrameSnapshot:
    """One immutable, validated JPEG version published for refresh use."""

    jpeg_bytes: bytes
    generation: int
    jpeg_info: lcd_transport.JpegInfo = field(repr=False, compare=False)


class FrameSource(Protocol):
    def snapshot(self) -> FrameSnapshot:
        """Return one atomic immutable view of the currently published frame."""


class LatestFrameBuffer:
    """Publish validated latest-frame snapshots without maintaining a queue."""

    def __init__(
        self,
        initial_jpeg: bytes | None = None,
        *,
        diagnostics: refresh_diagnostics.RefreshDiagnostics | None = None,
        transport_interval_seconds: float | None = None,
        next_frame_callback: NextFrameCallback | None = None,
        transport_driven: bool = False,
    ) -> None:
        if transport_interval_seconds is not None:
            _require_positive_finite(transport_interval_seconds, "Transportintervall")
        if next_frame_callback is not None and not callable(next_frame_callback):
            raise TypeError("next_frame_callback muss aufrufbar sein")
        if not isinstance(transport_driven, bool):
            raise TypeError("transport_driven muss boolesch sein")
        self._condition = threading.Condition()
        self._current: FrameSnapshot | None = None
        self._transport_interval_seconds = transport_interval_seconds
        self._next_frame_callback = next_frame_callback
        self._transport_driven = transport_driven
        self.diagnostics = diagnostics or refresh_diagnostics.NULL_DIAGNOSTICS
        if initial_jpeg is not None:
            self.publish(initial_jpeg)

    def publish(self, jpeg_bytes: bytes) -> FrameSnapshot:
        """Validate before locking, then atomically replace the current frame."""
        validated = RefreshFrame(jpeg_bytes)
        with self._condition:
            generation = (
                1 if self._current is None else self._current.generation + 1
            )
            snapshot = FrameSnapshot(
                jpeg_bytes=validated.jpeg_bytes,
                generation=generation,
                jpeg_info=validated.jpeg_info,
            )
            self.diagnostics.record(
                "frame_published",
                generation=generation,
                jpeg_length=validated.jpeg_info.length,
                planned_segments=validated.jpeg_info.segment_count,
            )
            self._current = snapshot
            self._condition.notify_all()
            return snapshot

    def snapshot(self) -> FrameSnapshot:
        """Return the current immutable snapshot under only a short read lock."""
        with self._condition:
            if self._current is None:
                raise RefreshStateError("Noch kein Refresh-Frame publiziert")
            return self._current

    @property
    def transport_interval_seconds(self) -> float | None:
        with self._condition:
            return self._transport_interval_seconds

    def set_transport_interval_seconds(self, interval_seconds: float) -> None:
        """Atomically select static or animated cadence without a new session."""
        _require_positive_finite(interval_seconds, "Transportintervall")
        with self._condition:
            self._transport_interval_seconds = interval_seconds

    @property
    def transport_driven(self) -> bool:
        with self._condition:
            return self._transport_driven

    def set_transport_driven(self, enabled: bool) -> None:
        if not isinstance(enabled, bool):
            raise TypeError("transport_driven muss boolesch sein")
        with self._condition:
            self._transport_driven = enabled
            self._condition.notify_all()

    def request_next_frame(self) -> None:
        """Request one coalescible producer update after a completed transfer."""
        callback = self._next_frame_callback
        if callback is not None:
            callback()

    def wait_for_generation_after(
        self, generation: int, stop_event: threading.Event
    ) -> bool:
        """Wait for one newer latest frame; return false when stopping."""
        with self._condition:
            while (
                not stop_event.is_set()
                and self._transport_driven
                and self._current is not None
                and self._current.generation <= generation
            ):
                self._condition.wait()
            return not stop_event.is_set()

    def cancel_waiters(self) -> None:
        with self._condition:
            self._condition.notify_all()


@dataclass(frozen=True)
class RefreshPlan:
    """Immutable frames plus transport timing and optional session limits."""

    frames: tuple[RefreshFrame, ...]
    transport_interval_seconds: float
    max_duration_seconds: float | None
    max_frames: int | None

    def __post_init__(self) -> None:
        if not isinstance(self.frames, tuple) or not self.frames:
            raise RefreshConfigurationError(
                "Mindestens ein unveränderlicher Refresh-Frame ist nötig"
            )
        if any(not isinstance(frame, RefreshFrame) for frame in self.frames):
            raise RefreshConfigurationError("RefreshPlan akzeptiert nur RefreshFrame-Einträge")
        _require_positive_finite(self.transport_interval_seconds, "Transportintervall")
        if self.max_duration_seconds is not None:
            _require_positive_finite(self.max_duration_seconds, "Maximale Laufzeit")
        if (
            self.max_duration_seconds is not None
            and self.max_duration_seconds > MAX_REFRESH_DURATION_SECONDS
        ):
            raise RefreshConfigurationError(
                f"Maximale Laufzeit darf {MAX_REFRESH_DURATION_SECONDS:g} s nicht überschreiten"
            )
        if self.max_frames is not None and (
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


def build_first_refresh_live_test_plan(jpeg_bytes: bytes) -> RefreshPlan:
    """Build, but never start, the fixed first-live-refresh safety profile."""
    frame = RefreshFrame(jpeg_bytes)
    digest = hashlib.sha256(jpeg_bytes).hexdigest()
    if digest != FIRST_REFRESH_REFERENCE_SHA256:
        raise RefreshConfigurationError(
            "Erster Live-Refresh akzeptiert nur das empirisch bestätigte "
            f"Referenz-JPEG (SHA-256 {FIRST_REFRESH_REFERENCE_SHA256}); "
            f"erhalten: {digest}"
        )
    return RefreshPlan(
        frames=(frame,),
        transport_interval_seconds=FIRST_REFRESH_INTERVAL_SECONDS,
        max_duration_seconds=FIRST_REFRESH_MAX_DURATION_SECONDS,
        max_frames=FIRST_REFRESH_MAX_FRAMES,
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
    """Device adapter; each call retains send_frame_once's finally-close."""

    device: lcd_transport.HidrawInterface
    extra_validator: lcd_transport.DeviceValidator | None = None
    diagnostics: refresh_diagnostics.RefreshDiagnostics = (
        refresh_diagnostics.NULL_DIAGNOSTICS
    )
    clock: Callable[[], float] = time.monotonic

    def __call__(self, jpeg: bytes) -> int:
        if self.diagnostics is refresh_diagnostics.NULL_DIAGNOSTICS:
            if self.extra_validator is None:
                return lcd_transport.send_frame_once(self.device, jpeg)
            return lcd_transport.send_frame_once(
                self.device,
                jpeg,
                extra_validator=self.extra_validator,
            )
        info = lcd_transport.validate_jpeg(jpeg)
        started_at = self.clock()
        completed_segments = 0

        def observe_write(_: lcd_transport.TransferSegment) -> None:
            nonlocal completed_segments
            completed_segments += 1

        self.diagnostics.record(
            "send_frame_once_called",
            planned_segments=info.segment_count,
        )
        try:
            written = lcd_transport.send_frame_once(
                self.device,
                jpeg,
                extra_validator=self.extra_validator,
                write_observer=observe_write,
            )
        except Exception as error:
            self.diagnostics.record(
                "send_frame_once_failed",
                planned_segments=info.segment_count,
                completed_segments=completed_segments,
                transfer_duration_seconds=max(0.0, self.clock() - started_at),
            )
            self.diagnostics.record_exception("send_frame_once", error)
            if completed_segments:
                self.diagnostics.record(
                    "handle_closed",
                    confirmed=True,
                    basis="send_frame_once finally after observed write",
                )
            else:
                self.diagnostics.record(
                    "handle_close_status",
                    confirmed=False,
                    basis="failure may have preceded hidraw open",
                )
            raise
        self.diagnostics.record(
            "send_frame_once_returned",
            planned_segments=info.segment_count,
            completed_segments=completed_segments,
            transfer_duration_seconds=max(0.0, self.clock() - started_at),
        )
        self.diagnostics.record(
            "handle_closed",
            confirmed=True,
            basis="send_frame_once returned after its finally-close",
        )
        return written


class PersistentHidrawFrameSender:
    """Diagnostic adapter for one production-owned persistent hidraw handle."""

    def __init__(
        self,
        device: lcd_transport.HidrawInterface,
        *,
        extra_validator: lcd_transport.DeviceValidator | None = None,
        diagnostics: refresh_diagnostics.RefreshDiagnostics = (
            refresh_diagnostics.NULL_DIAGNOSTICS
        ),
        clock: Callable[[], float] = time.monotonic,
        session: lcd_transport.PersistentHidrawSession | None = None,
    ) -> None:
        self.device = device
        self.extra_validator = extra_validator
        self.diagnostics = diagnostics
        self.clock = clock
        self.session = session or lcd_transport.PersistentHidrawSession(
            device,
            extra_validator=extra_validator,
            clock=clock,
        )

    def open(self) -> None:
        self.diagnostics.record("persistent_session_open_called")
        started_at = self.clock()
        try:
            self.session.open()
        except Exception as error:
            self.diagnostics.record(
                "persistent_session_open_failed",
                session_open_duration_seconds=max(0.0, self.clock() - started_at),
            )
            self.diagnostics.record_exception("persistent_session_open", error)
            raise
        self.diagnostics.record(
            "persistent_session_opened",
            session_open_duration_seconds=max(0.0, self.clock() - started_at),
            open_duration_seconds=self.session.open_duration_seconds,
        )

    def __call__(self, jpeg: bytes) -> int:
        info = lcd_transport.validate_jpeg(jpeg)
        segment_indices: list[int] = []
        segment_durations: list[float] = []

        def observe_write(
            segment: lcd_transport.TransferSegment,
            duration_seconds: float,
        ) -> None:
            segment_indices.append(segment.index)
            segment_durations.append(duration_seconds)

        self.diagnostics.record(
            "persistent_frame_send_called",
            planned_segments=info.segment_count,
        )
        started_at = self.clock()
        try:
            written = self.session.send_frame(jpeg, write_observer=observe_write)
        except Exception as error:
            self.diagnostics.record(
                "persistent_frame_send_failed",
                planned_segments=info.segment_count,
                completed_segments=max(0, len(segment_durations) - 1),
                segment_write_indices=segment_indices,
                segment_write_durations_seconds=segment_durations,
                write_total_duration_seconds=sum(segment_durations),
                send_frame_duration_seconds=max(0.0, self.clock() - started_at),
            )
            self.diagnostics.record_exception("persistent_frame_send", error)
            raise
        self.diagnostics.record(
            "persistent_frame_send_returned",
            planned_segments=info.segment_count,
            completed_segments=written,
            segment_write_indices=segment_indices,
            segment_write_durations_seconds=segment_durations,
            write_total_duration_seconds=sum(segment_durations),
            send_frame_duration_seconds=max(0.0, self.clock() - started_at),
        )
        return written

    def close(self) -> None:
        if not self.session.is_open:
            return
        started_at = self.clock()
        try:
            self.session.close()
        except Exception as error:
            self.diagnostics.record(
                "persistent_session_close_failed",
                session_close_duration_seconds=max(0.0, self.clock() - started_at),
                close_duration_seconds=self.session.close_duration_seconds,
            )
            self.diagnostics.record_exception("persistent_session_close", error)
            raise
        self.diagnostics.record(
            "persistent_session_closed",
            session_close_duration_seconds=max(0.0, self.clock() - started_at),
            close_duration_seconds=self.session.close_duration_seconds,
        )


_ACTIVE_REFRESH_LOCK = threading.Lock()


def _require_positive_finite(value: float, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RefreshConfigurationError(f"{label} muss eine Zahl sein")
    if not math.isfinite(value) or value <= 0:
        raise RefreshConfigurationError(f"{label} muss endlich und größer als null sein")


def _event_wait(event: threading.Event, timeout: float) -> bool:
    return event.wait(timeout)


class RefreshController:
    """Run one explicit refresh session on one non-daemon worker thread.

    The sender is synchronous. The controller never queues frames, never starts
    a second transfer while one is active and never retries a failed call.
    """

    def __init__(
        self,
        plan: RefreshPlan,
        sender: FrameSender,
        *,
        frame_source: FrameSource | None = None,
        clock: Callable[[], float] = time.monotonic,
        wait_function: WaitFunction = _event_wait,
    ) -> None:
        if not callable(sender):
            raise TypeError("sender muss aufrufbar sein")
        if not callable(clock) or not callable(wait_function):
            raise TypeError("clock und wait_function müssen aufrufbar sein")
        if frame_source is not None:
            if not callable(getattr(frame_source, "snapshot", None)):
                raise TypeError("frame_source muss snapshot() bereitstellen")
            if len(plan.frames) != 1:
                raise RefreshConfigurationError(
                    "Eine dynamische FrameSource ist nur für Einframepläne zulässig"
                )
        self._plan = plan
        self._sender = sender
        self._frame_source = frame_source
        self._diagnostics = refresh_diagnostics.diagnostics_for(frame_source)
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
        self.request_stop()
        thread.join(timeout)
        if thread.is_alive():
            raise TimeoutError("Refreshworker konnte innerhalb des Timeouts nicht stoppen")
        result = self.result
        if result is None:
            raise RefreshStateError("Refreshworker endete ohne Ergebnis")
        return result

    def request_stop(self) -> None:
        """Request a stop without waiting or performing any device operation."""
        if not self._stop_event.is_set():
            self._diagnostics.record("stop_requested", requested_reason="user")
        self._stop_event.set()
        cancel_waiters = getattr(self._frame_source, "cancel_waiters", None)
        if callable(cancel_waiters):
            cancel_waiters()

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
        sender_opened = False
        self._diagnostics.record("worker_started")
        try:
            open_sender = getattr(self._sender, "open", None)
            if callable(open_sender):
                open_sender()
                sender_opened = True
            result = self._run_loop()
        except Exception as error:
            self._diagnostics.record_exception("refresh_worker", error)
            result = RefreshResult(
                stop_reason=RefreshStopReason.INTERNAL_ERROR,
                frames_sent=0,
                elapsed_seconds=0.0,
                transfer_durations=(),
                frame_indices=(),
                error=error,
            )
        finally:
            close_sender = getattr(self._sender, "close", None)
            if sender_opened and callable(close_sender):
                try:
                    close_sender()
                except Exception as error:
                    self._diagnostics.record_exception("refresh_sender_close", error)
                    if result is None or result.error is None:
                        result = RefreshResult(
                            stop_reason=RefreshStopReason.INTERNAL_ERROR,
                            frames_sent=(0 if result is None else result.frames_sent),
                            elapsed_seconds=(
                                0.0 if result is None else result.elapsed_seconds
                            ),
                            transfer_durations=(
                                () if result is None else result.transfer_durations
                            ),
                            frame_indices=(
                                () if result is None else result.frame_indices
                            ),
                            error=error,
                        )
            if result is not None:
                self._diagnostics.record(
                    "session_stopped",
                    stop_reason=_diagnostic_stop_reason(result.stop_reason),
                    controller_stop_reason=result.stop_reason.value,
                    frame_count=result.frames_sent,
                    elapsed_seconds=result.elapsed_seconds,
                )
                if result.error is not None:
                    self._diagnostics.record_exception(
                        "refresh_result", result.error
                    )
            self._diagnostics.record("worker_ended")
            with self._state_lock:
                self._result = result
            _ACTIVE_REFRESH_LOCK.release()

    def _run_loop(self) -> RefreshResult:
        started_at = self._clock()
        deadline = (
            None
            if self._plan.max_duration_seconds is None
            else started_at + self._plan.max_duration_seconds
        )
        sent = 0
        frame_index = 0
        visible_since: float | None = None
        transfer_durations: deque[float] = deque(maxlen=MAX_RESULT_HISTORY_FRAMES)
        frame_indices: deque[int] = deque(maxlen=MAX_RESULT_HISTORY_FRAMES)

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
            if deadline is not None and now >= deadline:
                return self._result_for(
                    RefreshStopReason.MAX_DURATION,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )
            if (
                self._plan.max_frames is not None
                and sent >= self._plan.max_frames
            ):
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

            if self._frame_source is None:
                frame = self._plan.frames[frame_index]
                jpeg_bytes = frame.jpeg_bytes
                jpeg_info = frame.jpeg_info
            else:
                snapshot = self._frame_source.snapshot()
                self._diagnostics.record(
                    "frame_snapshot",
                    generation=snapshot.generation,
                    refresh_number=sent + 1,
                )
                jpeg_bytes = snapshot.jpeg_bytes
                jpeg_info = snapshot.jpeg_info
            if self._stop_event.is_set():
                return self._result_for(
                    RefreshStopReason.EXPLICIT_STOP,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )
            transfer_started = self._clock()
            self._diagnostics.record(
                "frame_transfer_begun",
                frame_number=sent + 1,
                snapshot_generation=(
                    snapshot.generation if self._frame_source is not None else None
                ),
                planned_segments=jpeg_info.segment_count,
            )
            try:
                completed_writes = self._sender(jpeg_bytes)
                if (
                    isinstance(completed_writes, bool)
                    or not isinstance(completed_writes, int)
                    or completed_writes != jpeg_info.segment_count
                ):
                    raise lcd_transport.LcdTransportError(
                        f"Frame meldete {completed_writes} statt "
                        f"{jpeg_info.segment_count} vollständigen Writes"
                    )
            except Exception as error:
                self._diagnostics.record(
                    "frame_transfer_failed",
                    frame_number=sent + 1,
                    planned_segments=jpeg_info.segment_count,
                    transfer_duration_seconds=max(
                        0.0, self._clock() - transfer_started
                    ),
                )
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
            self._diagnostics.record(
                "frame_transfer_succeeded",
                frame_number=sent,
                planned_segments=jpeg_info.segment_count,
                completed_segments=completed_writes,
                transfer_duration_seconds=transfer_durations[-1],
            )
            self._diagnostics.record(
                "frame_count_advanced",
                frame_count=sent,
                transfer_duration_seconds=transfer_durations[-1],
            )
            if frame_changed:
                visible_since = transfer_finished

            if deadline is not None and transfer_finished >= deadline:
                return self._result_for(
                    RefreshStopReason.MAX_DURATION,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )
            if (
                self._plan.max_frames is not None
                and sent >= self._plan.max_frames
            ):
                return self._result_for(
                    RefreshStopReason.MAX_FRAMES,
                    started_at,
                    sent,
                    transfer_durations,
                    frame_indices,
                )

            if self._frame_source is not None and bool(
                getattr(self._frame_source, "transport_driven", False)
            ):
                request_next_frame = getattr(
                    self._frame_source, "request_next_frame", None
                )
                if callable(request_next_frame):
                    try:
                        request_next_frame()
                    except Exception as error:
                        return self._result_for(
                            RefreshStopReason.INTERNAL_ERROR,
                            started_at,
                            sent,
                            transfer_durations,
                            frame_indices,
                            error=error,
                        )
                wait_for_generation = getattr(
                    self._frame_source, "wait_for_generation_after", None
                )
                if callable(wait_for_generation) and not wait_for_generation(
                    snapshot.generation, self._stop_event
                ):
                    return self._result_for(
                        RefreshStopReason.EXPLICIT_STOP,
                        started_at,
                        sent,
                        transfer_durations,
                        frame_indices,
                    )

            transport_interval = self._plan.transport_interval_seconds
            if self._frame_source is not None:
                dynamic_interval = getattr(
                    self._frame_source, "transport_interval_seconds", None
                )
                if dynamic_interval is not None:
                    _require_positive_finite(dynamic_interval, "Transportintervall")
                    transport_interval = dynamic_interval
            next_start = transfer_started + transport_interval
            next_wakeup = (
                next_start if deadline is None else min(next_start, deadline)
            )
            wait_seconds = max(0.0, next_wakeup - transfer_finished)
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
        transfer_durations: deque[float],
        frame_indices: deque[int],
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


def _diagnostic_stop_reason(reason: RefreshStopReason) -> str:
    return {
        RefreshStopReason.EXPLICIT_STOP: "user",
        RefreshStopReason.MAX_DURATION: "30 s",
        RefreshStopReason.MAX_FRAMES: "30 Frames",
        RefreshStopReason.SEND_ERROR: "transport error",
        RefreshStopReason.INTERNAL_ERROR: "sonstiger Fehler",
    }[reason]
