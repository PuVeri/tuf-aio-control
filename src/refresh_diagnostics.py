#!/usr/bin/env python3
"""Thread-safe JSONL diagnostics for one explicitly started GUI refresh session."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIRECTORY = PROJECT_ROOT / "logs"


class RefreshDiagnostics(Protocol):
    def record(self, event: str, **fields: object) -> None: ...

    def record_exception(self, phase: str, error: BaseException) -> None: ...


class NullRefreshDiagnostics:
    """No-op sink used by non-GUI and legacy offline controller callers."""

    def record(self, event: str, **fields: object) -> None:
        del event, fields

    def record_exception(self, phase: str, error: BaseException) -> None:
        del phase, error


NULL_DIAGNOSTICS = NullRefreshDiagnostics()


class JsonlRefreshDiagnostics:
    """Append and flush one payload-free JSON object per diagnostic event."""

    def __init__(
        self,
        path: Path,
        *,
        clock=time.monotonic,
        session_id: str | None = None,
    ) -> None:
        self.path = path
        self._clock = clock
        self._session_id = session_id or uuid.uuid4().hex
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.record("diagnostics_created", log_path=str(path))

    def record(self, event: str, **fields: object) -> None:
        with self._lock:
            entry = {
                "monotonic_seconds": self._clock(),
                "session_id": self._session_id,
                "event": event,
                **fields,
            }
            encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
                stream.flush()

    def record_exception(self, phase: str, error: BaseException) -> None:
        self.record(
            "exception",
            phase=phase,
            exception_type=type(error).__name__,
            message=str(error)[:500],
        )


def create_gui_session_diagnostics() -> JsonlRefreshDiagnostics:
    """Create a unique persistent log only after an explicit GUI start request."""
    filename = (
        f"gui-refresh-{time.strftime('%Y%m%d-%H%M%S')}-"
        f"{uuid.uuid4().hex[:8]}.jsonl"
    )
    return JsonlRefreshDiagnostics(DEFAULT_LOG_DIRECTORY / filename)


def diagnostics_for(source: object | None) -> RefreshDiagnostics:
    candidate = getattr(source, "diagnostics", None)
    if callable(getattr(candidate, "record", None)) and callable(
        getattr(candidate, "record_exception", None)
    ):
        return candidate
    return NULL_DIAGNOSTICS
