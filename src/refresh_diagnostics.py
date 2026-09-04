#!/usr/bin/env python3
"""Thread-safe JSONL diagnostics for one explicitly started GUI refresh session."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Protocol

DEFAULT_MAX_LOG_BYTES = 2 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 3
DEFAULT_RETAINED_LOG_FILES = 20


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


def default_log_directory() -> Path:
    """Return the XDG user-state directory used for persistent runtime logs."""
    configured = os.environ.get("XDG_STATE_HOME")
    if configured:
        candidate = Path(configured).expanduser()
        if candidate.is_absolute():
            return candidate / "tuf-aio-control"
    return Path.home() / ".local" / "state" / "tuf-aio-control"


class JsonlRefreshDiagnostics:
    """Append and flush one payload-free JSON object per diagnostic event."""

    def __init__(
        self,
        path: Path,
        *,
        clock=time.monotonic,
        session_id: str | None = None,
        max_bytes: int = DEFAULT_MAX_LOG_BYTES,
        backup_count: int = DEFAULT_BACKUP_COUNT,
    ) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes muss positiv sein")
        if backup_count < 1:
            raise ValueError("backup_count muss positiv sein")
        self.path = path
        self._clock = clock
        self._session_id = session_id or uuid.uuid4().hex
        self._max_bytes = max_bytes
        self._backup_count = backup_count
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
            self._rotate_if_needed(len((encoded + "\n").encode("utf-8")))
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded + "\n")
                stream.flush()

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        try:
            current_bytes = self.path.stat().st_size
        except FileNotFoundError:
            return
        if current_bytes == 0 or current_bytes + incoming_bytes <= self._max_bytes:
            return
        oldest = self.path.with_name(f"{self.path.name}.{self._backup_count}")
        oldest.unlink(missing_ok=True)
        for index in range(self._backup_count - 1, 0, -1):
            source = self.path.with_name(f"{self.path.name}.{index}")
            if source.exists():
                source.replace(self.path.with_name(f"{self.path.name}.{index + 1}"))
        self.path.replace(self.path.with_name(f"{self.path.name}.1"))

    def record_exception(self, phase: str, error: BaseException) -> None:
        self.record(
            "exception",
            phase=phase,
            exception_type=type(error).__name__,
            message=str(error)[:500],
        )


def create_gui_session_diagnostics(
    directory: Path | None = None,
) -> JsonlRefreshDiagnostics:
    """Create a unique persistent log only after an explicit GUI start request."""
    filename = (
        f"gui-refresh-{time.strftime('%Y%m%d-%H%M%S')}-"
        f"{uuid.uuid4().hex[:8]}.jsonl"
    )
    log_directory = directory if directory is not None else default_log_directory()
    diagnostics = JsonlRefreshDiagnostics(log_directory / filename)
    _prune_runtime_logs(log_directory)
    return diagnostics


def _prune_runtime_logs(directory: Path) -> None:
    files = sorted(
        directory.glob("gui-refresh-*.jsonl*"),
        key=lambda candidate: candidate.stat().st_mtime_ns,
        reverse=True,
    )
    for stale in files[DEFAULT_RETAINED_LOG_FILES:]:
        stale.unlink(missing_ok=True)


def diagnostics_for(source: object | None) -> RefreshDiagnostics:
    candidate = getattr(source, "diagnostics", None)
    if callable(getattr(candidate, "record", None)) and callable(
        getattr(candidate, "record_exception", None)
    ):
        return candidate
    return NULL_DIAGNOSTICS
