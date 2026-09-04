#!/usr/bin/env python3
"""Small queue-free sequential scheduler for prepared GIF frames."""

from __future__ import annotations

from dataclasses import dataclass
import math

# Technical non-zero floor only; transport pacing is handled separately.
MINIMUM_EFFECTIVE_FRAME_DURATION_MS = 1


class GifAnimationConfigurationError(ValueError):
    """The prepared animation metadata cannot form a safe timeline."""


@dataclass(frozen=True)
class GifAnimationState:
    frame_index: int
    completed_loops: int
    finished: bool


class GifAnimationScheduler:
    """Track one GIF timeline without decoding, rendering, threads, or queues."""

    def __init__(
        self,
        *,
        minimum_frame_duration_ms: int = MINIMUM_EFFECTIVE_FRAME_DURATION_MS,
    ) -> None:
        if (
            isinstance(minimum_frame_duration_ms, bool)
            or not isinstance(minimum_frame_duration_ms, int)
            or minimum_frame_duration_ms < 1
        ):
            raise GifAnimationConfigurationError(
                "Minimaler GIF-Frameabstand muss positiv sein"
            )
        self.minimum_frame_duration_ms = minimum_frame_duration_ms
        self._source_durations_ms: tuple[int, ...] = ()
        self._durations_ms: tuple[int, ...] = ()
        self._playback_speed = 1.0
        self._total_cycles: int | None = None
        self._frame_started_at = 0.0
        self._next_deadline: float | None = None
        self._state: GifAnimationState | None = None

    @property
    def state(self) -> GifAnimationState | None:
        return self._state

    @property
    def effective_durations_ms(self) -> tuple[int, ...]:
        return self._durations_ms

    @property
    def playback_speed(self) -> float:
        return self._playback_speed

    @property
    def is_running(self) -> bool:
        return self._state is not None and not self._state.finished

    @property
    def next_deadline(self) -> float | None:
        return self._next_deadline

    def start(
        self,
        durations_ms: tuple[int, ...],
        loop_count: int | None,
        *,
        now: float,
        playback_speed: float = 1.0,
    ) -> GifAnimationState:
        if not durations_ms:
            raise GifAnimationConfigurationError("GIF benötigt mindestens einen Frame")
        if not math.isfinite(now):
            raise GifAnimationConfigurationError("Ungültiger GIF-Startzeitpunkt")
        if loop_count is not None and (
            isinstance(loop_count, bool)
            or not isinstance(loop_count, int)
            or loop_count < 0
        ):
            raise GifAnimationConfigurationError("Ungültiger GIF-Loopwert")
        self._validate_playback_speed(playback_speed)
        source_durations: list[int] = []
        for duration in durations_ms:
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int)
                or duration < 0
            ):
                raise GifAnimationConfigurationError("Ungültige GIF-Framedauer")
            source_durations.append(duration)
        self._source_durations_ms = tuple(source_durations)
        self._playback_speed = float(playback_speed)
        self._durations_ms = self._scaled_durations(self._playback_speed)
        # GIF loop=0 means infinite; positive values count repetitions after
        # the initial pass. Missing loop metadata means one pass.
        self._total_cycles = None if loop_count == 0 else 1 + (loop_count or 0)
        self._frame_started_at = now
        self._next_deadline = now + self._durations_ms[0] / 1000.0
        self._state = GifAnimationState(0, 0, False)
        return self._state

    def stop(self) -> None:
        self._next_deadline = None
        self._state = None

    def set_playback_speed(self, playback_speed: float, *, now: float) -> None:
        """Apply a new factor without restarting or skipping the current frame."""
        self._validate_playback_speed(playback_speed)
        if not math.isfinite(now):
            raise GifAnimationConfigurationError("Ungültiger GIF-Zeitpunkt")
        previous_duration = (
            self._durations_ms[self._state.frame_index]
            if self._state is not None and self._durations_ms
            else None
        )
        self._playback_speed = float(playback_speed)
        self._durations_ms = self._scaled_durations(self._playback_speed)
        if self.is_running and previous_duration is not None:
            elapsed_ms = max(0.0, (now - self._frame_started_at) * 1000.0)
            new_duration = self._durations_ms[self._state.frame_index]
            self._next_deadline = now + max(0.0, new_duration - elapsed_ms) / 1000.0

    @staticmethod
    def _validate_playback_speed(playback_speed: float) -> None:
        if (
            isinstance(playback_speed, bool)
            or not isinstance(playback_speed, (int, float))
            or not math.isfinite(playback_speed)
            or playback_speed <= 0
        ):
            raise GifAnimationConfigurationError("Ungültiger GIF-Geschwindigkeitsfaktor")

    def _scaled_durations(self, playback_speed: float) -> tuple[int, ...]:
        return tuple(
            max(
                self.minimum_frame_duration_ms,
                round(duration / playback_speed),
            )
            for duration in self._source_durations_ms
        )

    def milliseconds_until_next(self, *, now: float) -> int | None:
        if not self.is_running or self._next_deadline is None:
            return None
        return max(0, math.ceil((self._next_deadline - now) * 1000.0))

    def advance(self, *, now: float) -> GifAnimationState | None:
        """Advance exactly one frame when due; never skip or queue frames."""
        if not self.is_running or self._next_deadline is None:
            return None
        if now < self._next_deadline:
            return None
        current = self._state
        assert current is not None
        if (
            current.frame_index == len(self._durations_ms) - 1
            and self._total_cycles is not None
            and current.completed_loops + 1 >= self._total_cycles
        ):
            self._state = GifAnimationState(
                len(self._durations_ms) - 1,
                self._total_cycles - 1,
                True,
            )
            self._next_deadline = None
            return self._state

        frame_index = (current.frame_index + 1) % len(self._durations_ms)
        completed_loops = current.completed_loops + (1 if frame_index == 0 else 0)
        # A late caller advances only once and establishes a fresh deadline.
        # This preserves order without building timeline debt to catch up later.
        self._frame_started_at = now
        self._next_deadline = now + self._durations_ms[frame_index] / 1000.0
        self._state = GifAnimationState(frame_index, completed_loops, False)
        return self._state
