"""In-memory, browser-session-scoped SQL authentication for the hosted demo."""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class SqlCredential:
    provider: str
    model: str
    api_key: str = field(repr=False)
    validated_at: float = 0.0


@dataclass(slots=True)
class _SessionEntry:
    credential: SqlCredential
    last_access: float


class SessionCredentialRegistry:
    def __init__(
        self,
        *,
        max_sessions: int = 128,
        idle_timeout: float = 1800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_sessions < 1:
            raise ValueError("max_sessions must be positive")
        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be positive")
        self.max_sessions = max_sessions
        self.idle_timeout = idle_timeout
        self._clock = clock
        self._entries: OrderedDict[str, _SessionEntry] = OrderedDict()
        self._lock = threading.RLock()

    def put(self, session_id: str, credential: SqlCredential) -> None:
        if not session_id:
            raise ValueError("session_id is required")
        now = self._clock()
        with self._lock:
            self._cleanup_locked(now)
            self._entries.pop(session_id, None)
            self._entries[session_id] = _SessionEntry(credential=credential, last_access=now)
            while len(self._entries) > self.max_sessions:
                self._entries.popitem(last=False)

    def get(self, session_id: str) -> SqlCredential | None:
        if not session_id:
            return None
        now = self._clock()
        with self._lock:
            self._cleanup_locked(now)
            entry = self._entries.get(session_id)
            if entry is None:
                return None
            entry.last_access = now
            self._entries.move_to_end(session_id)
            return entry.credential

    def status(self, session_id: str) -> dict[str, object]:
        credential = self.get(session_id)
        if credential is None:
            return {"configured": False}
        return {
            "configured": True,
            "provider": credential.provider,
            "model": credential.model,
            "validated_at": credential.validated_at,
        }

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._entries.pop(session_id, None) is not None

    def cleanup(self) -> int:
        with self._lock:
            return self._cleanup_locked(self._clock())

    def _cleanup_locked(self, now: float) -> int:
        expired = [
            session_id
            for session_id, entry in self._entries.items()
            if now - entry.last_access > self.idle_timeout
        ]
        for session_id in expired:
            self._entries.pop(session_id, None)
        return len(expired)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def session_log_id(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
