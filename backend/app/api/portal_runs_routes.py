"""Workforce portal automation run endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.portal_runner import run_portal_search
from app.db.repository import get_portal_run, list_portal_runs
from app.models.portal import PortalRunRequest

router = APIRouter(prefix="/api/portal-runs", tags=["portal_runs"])


@router.get("")
async def list_runs(limit: int = 25) -> list[dict]:
    return await list_portal_runs(limit=limit)


@router.get("/{portal_run_id}")
async def fetch_run(portal_run_id: str) -> dict:
    row = await get_portal_run(portal_run_id)
    if not row:
        raise HTTPException(404, "Portal run not found")
    return row


@router.post("")
async def create_run(body: PortalRunRequest) -> dict:
    try:
        result = await run_portal_search(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.model_dump(mode="json")
