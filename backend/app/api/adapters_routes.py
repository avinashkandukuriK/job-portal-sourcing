"""Adapter management endpoints — list, inspect, toggle on/off.

GET    /api/adapters                        List with metadata + status + toggle
GET    /api/adapters/{name}                 One adapter detail
POST   /api/adapters/{name}/enable          Turn ON
POST   /api/adapters/{name}/disable         Turn OFF (admin override; persists)
POST   /api/adapters/{name}/pause           Temporary off until {paused_until}
POST   /api/adapters/{name}/resume          Resume from PAUSED / AUTO_DISABLED
POST   /api/adapters/bulk/enable            Turn ON multiple at once
POST   /api/adapters/bulk/disable           Turn OFF multiple at once

The orchestrator and source-picker UI both consult these. A disabled adapter
is silently skipped during search runs and shown grayed-out in the picker
with the `reason` and `paused_until` exposed as a tooltip.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from app.adapters import (
    get_adapter_class,
    health_check_all,
)
from app.adapters.toggle_store import (
    AdapterToggle,
    get_toggle_store,
)

router = APIRouter(prefix="/api/adapters", tags=["adapters"])


# ----------------------- request schemas -----------------------

class ToggleRequest(BaseModel):
    reason: Optional[str] = None
    set_by: Optional[str] = None  # set automatically once auth is wired


class PauseRequest(ToggleRequest):
    minutes: int = Field(60, ge=1, le=60 * 24 * 30, description="Pause duration in minutes")


class BulkToggleRequest(ToggleRequest):
    names: list[str] = Field(..., min_length=1)


# ----------------------- read endpoints -----------------------

@router.get("")
async def list_adapters() -> list[dict]:
    """Returns every registered adapter with metadata, resolved status,
    raw toggle record, and a short disabled_reason string.

    Frontend source picker groups by `metadata.tier` for the
    Premium / Non-Premium / Internal tabs and reads `toggle.state` to render
    the on/off switch.
    """
    return await health_check_all()


@router.get("/{name}")
async def get_adapter_detail(name: str) -> dict:
    try:
        cls = get_adapter_class(name)
    except KeyError:
        raise HTTPException(404, f"Unknown adapter: {name}") from None
    inst = cls()
    try:
        status = await inst.status()
        toggle = inst.get_toggle()
        reason = inst.disabled_reason()
    finally:
        await inst.aclose()
    return {
        "metadata": cls.metadata.model_dump(),
        "status": status.value,
        "toggle": toggle.model_dump(mode="json"),
        "disabled_reason": reason,
    }


# ----------------------- toggle helpers -----------------------

def _require_known(name: str) -> None:
    try:
        get_adapter_class(name)
    except KeyError:
        raise HTTPException(404, f"Unknown adapter: {name}") from None


# ----------------------- bulk endpoints -----------------------

@router.post("/bulk/enable")
async def bulk_enable(body: BulkToggleRequest) -> list[AdapterToggle]:
    store = get_toggle_store()
    out: list[AdapterToggle] = []
    for name in body.names:
        _require_known(name)
        out.append(store.enable(name, set_by=body.set_by, reason=body.reason))
    return out


@router.post("/bulk/disable")
async def bulk_disable(body: BulkToggleRequest) -> list[AdapterToggle]:
    store = get_toggle_store()
    out: list[AdapterToggle] = []
    for name in body.names:
        _require_known(name)
        out.append(store.disable(name, set_by=body.set_by, reason=body.reason))
    return out


# ----------------------- single-adapter toggle endpoints -----------------------

@router.post("/{name}/enable")
async def enable_adapter(name: str, body: ToggleRequest = Body(default=ToggleRequest())) -> AdapterToggle:
    _require_known(name)
    return get_toggle_store().enable(name, set_by=body.set_by, reason=body.reason)


@router.post("/{name}/disable")
async def disable_adapter(name: str, body: ToggleRequest = Body(default=ToggleRequest())) -> AdapterToggle:
    _require_known(name)
    return get_toggle_store().disable(name, set_by=body.set_by, reason=body.reason)


@router.post("/{name}/pause")
async def pause_adapter(name: str, body: PauseRequest) -> AdapterToggle:
    _require_known(name)
    until = datetime.now(timezone.utc) + timedelta(minutes=body.minutes)
    return get_toggle_store().pause(name, until=until, set_by=body.set_by, reason=body.reason)


@router.post("/{name}/resume")
async def resume_adapter(name: str, body: ToggleRequest = Body(default=ToggleRequest())) -> AdapterToggle:
    _require_known(name)
    return get_toggle_store().enable(
        name,
        set_by=body.set_by,
        reason=body.reason or "Resumed from pause/auto-disable",
    )


# ----------------------- toggle audit (raw store dump) -----------------------

@router.get("/_admin/toggles")
async def list_all_toggles() -> dict[str, AdapterToggle]:
    """All persisted toggle records (including for adapters that have since
    been removed from the registry — useful for audit)."""
    return get_toggle_store().all()
