"""Abstract source adapter — the contract every portal/source implements.

Design goal: adding a new adapter in the future requires *only* dropping a
single Python file (in-tree) or installing a third-party Python package
exposing an entry-point. No changes to orchestrator, API, or UI code.

A new adapter must:
1. Subclass `SourceAdapter`.
2. Define a class-level `metadata: AdapterMetadata`.
3. Implement `search(jd, limit) -> list[Candidate]`.
4. Apply `@register_adapter` (or expose via `entry_points` for plugins).

Everything else — UI tabs, cost estimation, health checks, rate limits,
on/off toggles — is read from `metadata`.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from app.models import Candidate, ParsedJD

from .capabilities import AdapterMetadata, AdapterStatus
from .toggle_store import AdapterToggle, ToggleState, get_toggle_store

logger = logging.getLogger(__name__)


class AdapterDisabled(Exception):
    """Raised when a disabled adapter is asked to run."""


class AdapterRateLimited(Exception):
    """Raised when an adapter has hit its rate limit; orchestrator can skip + retry later."""


class SourceAdapter(ABC):
    """Base class for every portal/source.

    Subclasses MUST override `metadata` with a fully populated `AdapterMetadata`
    instance. Subclasses MUST implement `search`. Everything else is optional.
    """

    #: Single source of truth — UI, orchestrator, registry all read this.
    metadata: ClassVar[AdapterMetadata]

    # -------------------- lifecycle --------------------

    async def setup(self) -> None:
        """Optional one-time init (open httpx client, load model, etc.)."""
        return None

    async def aclose(self) -> None:
        """Optional cleanup (close client, browser, files)."""
        return None

    # -------------------- core contract --------------------

    @abstractmethod
    async def search(
        self,
        jd: ParsedJD,
        limit: int = 25,
    ) -> list[Candidate]:
        """Run a candidate search and return normalized `Candidate` records."""

    async def enrich(self, candidate: Candidate) -> Candidate:
        """Optional: enrich an existing candidate with more data (email/phone/etc.).
        Default = identity (no-op). Override if `metadata.capabilities` includes ENRICH.
        """
        return candidate

    async def post_job(self, parsed_jd: ParsedJD, *, dry_run: bool = False) -> dict:
        """Optional: post a job to this source. Override if capabilities include POST_JOB.
        Returns a dict with at least `posting_url` and `external_id`.
        """
        raise NotImplementedError(f"{self.metadata.name} does not support post_job")

    # -------------------- health / readiness --------------------

    async def is_configured(self) -> bool:
        """Code-level readiness — env vars present, not deprecated.

        Renamed from `is_enabled()` to make the layered check explicit:
        `is_configured()` (CAN it run) vs `is_active()` (SHOULD it run).
        """
        if self.metadata.deprecated:
            return False
        from app.config import get_settings
        settings = get_settings()
        for var in self.metadata.required_env_vars:
            if not getattr(settings, var.lower(), None):
                return False
        return True

    # Back-compat alias — legacy callers used `is_enabled`
    async def is_enabled(self) -> bool:
        return await self.is_configured()

    def get_toggle(self) -> AdapterToggle:
        """Read this adapter's runtime on/off record from the persistent store."""
        return get_toggle_store().get(self.metadata.name)

    async def is_active(self) -> bool:
        """The single check the orchestrator uses: configured AND toggled on."""
        if not await self.is_configured():
            return False
        return self.get_toggle().is_currently_active()

    async def status(self) -> AdapterStatus:
        """Resolved status combining code-level config and runtime toggle.

        Precedence: deprecated → experimental → not configured → toggle state.
        """
        if self.metadata.deprecated:
            return AdapterStatus.DOWN
        if self.metadata.is_experimental:
            return AdapterStatus.EXPERIMENTAL
        if not await self.is_configured():
            return AdapterStatus.DISABLED_NO_CONFIG

        toggle = self.get_toggle()
        if toggle.state == ToggleState.DISABLED:
            return AdapterStatus.DISABLED_USER
        if toggle.state in (ToggleState.PAUSED, ToggleState.AUTO_DISABLED) and not toggle.is_currently_active():
            return AdapterStatus.DEGRADED
        return AdapterStatus.READY

    def disabled_reason(self) -> Optional[str]:
        """User-facing string explaining why the adapter is off (UI tooltip)."""
        if self.metadata.deprecated:
            return self.metadata.deprecation_message or "Deprecated"

        from app.config import get_settings
        settings = get_settings()
        missing = [v for v in self.metadata.required_env_vars
                   if not getattr(settings, v.lower(), None)]
        if missing:
            return f"Missing config: {', '.join(missing)}"

        toggle = self.get_toggle()
        if toggle.state == ToggleState.DISABLED:
            return f"Disabled by admin{f': {toggle.reason}' if toggle.reason else ''}"
        if toggle.state == ToggleState.PAUSED and toggle.paused_until:
            return f"Paused until {toggle.paused_until.isoformat()}{f' — {toggle.reason}' if toggle.reason else ''}"
        if toggle.state == ToggleState.AUTO_DISABLED:
            return f"Auto-disabled{f' — {toggle.reason}' if toggle.reason else ''}"
        return None

    # -------------------- convenience --------------------

    @property
    def name(self) -> str:
        return self.metadata.name

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.metadata.name} tier={self.metadata.tier}>"
