"""Candidate read endpoints for the internal database."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.repository import get_candidate, list_candidates

router = APIRouter(prefix="/api/candidates", tags=["candidates"])


@router.get("")
async def list_candidate_records(limit: int = 50) -> list[dict]:
    candidates = await list_candidates(limit=limit)
    return [candidate.model_dump(mode="json") for candidate in candidates]


@router.get("/{candidate_id}")
async def fetch_candidate(candidate_id: str) -> dict:
    candidate = await get_candidate(candidate_id)
    if not candidate:
        raise HTTPException(404, "Candidate not found")
    return candidate.model_dump(mode="json")
