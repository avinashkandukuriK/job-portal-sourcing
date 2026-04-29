"""Free-mode source planning endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.portal import SourcePlanRequest
from app.portals import build_source_plan

router = APIRouter(prefix="/api/source-plan", tags=["source_plan"])


@router.post("")
async def create_source_plan(body: SourcePlanRequest) -> dict:
    try:
        plan = build_source_plan(body)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return plan.model_dump(mode="json")
