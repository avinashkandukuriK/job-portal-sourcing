"""Adapter on/off state — persisted across restarts.

Two layers:
- `is_configured()` (in `base.py`) — code-level readiness: env vars present,
  not deprecated. Read-only from the adapter's perspective.
- `ToggleState` (this file) — runtime override that an admin sets via the API
  or CLI. Disabled / paused state always overrides "configured" — even if an
  adapter has all its env vars, a paused adapter won't run.

The orchestrator calls `is_active()` (in `base.py`) which combines both.

Toggle states:
    ENABLED       — default; runs normally
    DISABLED      — admin disabled; only an explicit enable() re-activates
    PAUSED        — temporary off; auto-resumes after `paused_until`
    AUTO_DISABLED — circuit-breaker tripped (too many failures); recoverable
"""
from __future__ import annotations

import abc
import json
import logging
import threading
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ToggleState(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"
    AUTO_DISABLED = "auto_disabled"


class AdapterToggle(BaseModel):
    """Persisted toggle record for one adapter."""

    name: str
    state: ToggleState = ToggleState.ENABLED
    reason: Optional[str] = None        # human note for the admin UI
    set_by: Optional[str] = None        # user id / email when auth is added
    set_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    paused_until: Optional[datetime] = None  # auto-resume timestamp

    # Circuit-breaker counters (optional, used when consecutive failures detected)
    consecutive_failures: int = 0
    last_failure_at: Optional[datetime] = None

    def is_currently_active(self) -> bool:
        """Resolve transient states (PAUSED past expiry → ENABLED)."""
        if self.state == ToggleState.PAUSED and self.paused_until:
            if datetime.now(timezone.utc) >= self.paused_until:
                return True
        return self.state == ToggleState.ENABLED


# ----------------------- abstract store -----------------------

class ToggleStore(abc.ABC):
    """Pluggable persistence for adapter toggles."""

    @abc.abstractmethod
    def get(self, name: str) -> AdapterToggle: ...

    @abc.abstractmethod
    def set(self, toggle: AdapterToggle) -> None: ...

    @abc.abstractmethod
    def all(self) -> dict[str, AdapterToggle]: ...

    # ---- convenience helpers shared by all backends ----

    def enable(self, name: str, *, set_by: Optional[str] = None, reason: Optional[str] = None) -> AdapterToggle:
        t = AdapterToggle(name=name, state=ToggleState.ENABLED, set_by=set_by, reason=reason)
        self.set(t)
        return t

    def disable(self, name: str, *, set_by: Optional[str] = None, reason: Optional[str] = None) -> AdapterToggle:
        t = AdapterToggle(name=name, state=ToggleState.DISABLED, set_by=set_by, reason=reason)
        self.set(t)
        return t

    def pause(
        self,
        name: str,
        *,
        until: datetime,
        set_by: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> AdapterToggle:
        t = AdapterToggle(
            name=name,
            state=ToggleState.PAUSED,
            paused_until=until,
            set_by=set_by,
            reason=reason,
        )
        self.set(t)
        return t

    def record_failure(self, name: str, *, threshold: int = 5, cooldown_minutes: int = 30) -> AdapterToggle:
        """Optional circuit breaker: auto-disable after N consecutive failures."""
        from datetime import timedelta
        cur = self.get(name)
        cur.consecutive_failures += 1
        cur.last_failure_at = datetime.now(timezone.utc)
        if cur.consecutive_failures >= threshold and cur.state == ToggleState.ENABLED:
            cur.state = ToggleState.AUTO_DISABLED
            cur.paused_until = datetime.now(timezone.utc) + timedelta(minutes=cooldown_minutes)
            cur.reason = f"Auto-disabled after {threshold} consecutive failures"
        self.set(cur)
        return cur

    def record_success(self, name: str) -> None:
        cur = self.get(name)
        if cur.consecutive_failures or cur.state == ToggleState.AUTO_DISABLED:
            cur.consecutive_failures = 0
            if cur.state == ToggleState.AUTO_DISABLED:
                cur.state = ToggleState.ENABLED
                cur.reason = None
            self.set(cur)


# ----------------------- JSON file store (dev) -----------------------

class JSONFileToggleStore(ToggleStore):
    """Simple file-backed store. Suitable for local dev and small single-node deploys."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("{}", encoding="utf-8")

    def _read(self) -> dict[str, AdapterToggle]:
        with self.path.open("r", encoding="utf-8") as f:
            raw = json.load(f) or {}
        out: dict[str, AdapterToggle] = {}
        for name, data in raw.items():
            try:
                out[name] = AdapterToggle.model_validate(data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bad toggle record for %s: %s", name, exc)
        return out

    def _write(self, data: dict[str, AdapterToggle]) -> None:
        serializable = {n: t.model_dump(mode="json") for n, t in data.items()}
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, default=str)
        tmp.replace(self.path)

    def get(self, name: str) -> AdapterToggle:
        with self._lock:
            data = self._read()
            return data.get(name) or AdapterToggle(name=name)

    def set(self, toggle: AdapterToggle) -> None:
        with self._lock:
            data = self._read()
            data[toggle.name] = toggle
            self._write(data)

    def all(self) -> dict[str, AdapterToggle]:
        with self._lock:
            return self._read()


# ----------------------- Supabase store (prod) -----------------------

class SupabaseToggleStore(ToggleStore):
    """Supabase-backed store.

    Schema (see migrations/002_adapter_toggles.sql):
        create table adapter_toggles (
            name text primary key,
            state text not null default 'enabled',
            reason text,
            set_by text,
            set_at timestamptz not null default now(),
            paused_until timestamptz,
            consecutive_failures int not null default 0,
            last_failure_at timestamptz
        );
    """

    TABLE = "adapter_toggles"

    def __init__(self, client) -> None:
        self._client = client

    def get(self, name: str) -> AdapterToggle:
        res = self._client.table(self.TABLE).select("*").eq("name", name).limit(1).execute()
        rows = res.data or []
        return AdapterToggle.model_validate(rows[0]) if rows else AdapterToggle(name=name)

    def set(self, toggle: AdapterToggle) -> None:
        self._client.table(self.TABLE).upsert(toggle.model_dump(mode="json")).execute()

    def all(self) -> dict[str, AdapterToggle]:
        res = self._client.table(self.TABLE).select("*").execute()
        out: dict[str, AdapterToggle] = {}
        for row in res.data or []:
            try:
                t = AdapterToggle.model_validate(row)
                out[t.name] = t
            except Exception as exc:  # noqa: BLE001
                logger.warning("Bad toggle row: %s", exc)
        return out


# ----------------------- factory -----------------------

_INSTANCE: Optional[ToggleStore] = None


def get_toggle_store() -> ToggleStore:
    """Return the singleton store. Uses Supabase if configured, else JSON file."""
    global _INSTANCE
    if _INSTANCE is not None:
        return _INSTANCE

    from app.config import get_settings
    settings = get_settings()
    if settings.has_supabase:
        try:
            from supabase import create_client
            key = getattr(settings, "supabase_service_key", None) or settings.supabase_key
            client = create_client(settings.supabase_url, key)
            _INSTANCE = SupabaseToggleStore(client)
            logger.info("Toggle store: Supabase")
            return _INSTANCE
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falling back to JSON store — Supabase init failed: %s", exc)

    fallback = Path("data/adapter_toggles.json")
    _INSTANCE = JSONFileToggleStore(fallback)
    logger.info("Toggle store: JSON file at %s", fallback)
    return _INSTANCE


def reset_toggle_store() -> None:
    """Test helper — discard the singleton."""
    global _INSTANCE
    _INSTANCE = None
