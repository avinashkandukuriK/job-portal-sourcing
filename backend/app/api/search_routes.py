"""Search endpoints — paste a JD, run sourcing, return ranked candidates."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core import SourcingOrchestrator, parse_jd
from app.models import JobDescription, SearchRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])


class ParseRequest(BaseModel):
    jd_text: str
    title_hint: Optional[str] = None


@router.post("/parse")
async def parse_endpoint(body: ParseRequest) -> dict:
    """Parse a JD into structured form. Used by the UI to show what we extracted
    before the recruiter runs the actual search.
    """
    try:
        parsed = parse_jd(JobDescription(text=body.jd_text, title_hint=body.title_hint))
        return parsed.model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("")
async def run_search(body: SearchRequest) -> dict:
    """Parse the JD, fan out to adapters, score, dedupe, persist, and return."""
    try:
        parsed = parse_jd(JobDescription(text=body.jd_text, title_hint=body.title_hint))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    orch = SourcingOrchestrator(
        job_order_id=body.job_order_id,
        raw_jd_text=body.jd_text,
        persist=True,
    )
    result = await orch.run(
        parsed,
        mode=body.mode,
        selected_adapter_names=body.sources,
        include_premium=body.include_premium,
        limit_per_source=body.limit_per_source,
    )
    return result.model_dump(mode="json")
