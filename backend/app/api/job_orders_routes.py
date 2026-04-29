"""Job order endpoints — create from a JD, list, fetch."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.core import parse_jd
from app.db.repository import (
    create_job_order,
    get_job_order,
    list_job_orders,
)
from app.models import (
    ComplianceRequirements,
    JobDescription,
    JobOrder,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/job_orders", tags=["job_orders"])


@router.get("")
async def list_orders(status: Optional[str] = None, limit: int = 50) -> list[dict]:
    return await list_job_orders(status=status, limit=limit)


@router.get("/{job_order_id}")
async def fetch_order(job_order_id: str) -> dict:
    row = await get_job_order(job_order_id)
    if not row:
        raise HTTPException(404, "Job order not found")
    return row


@router.post("")
async def create_order(body: dict) -> dict:
    """Create a job order from raw JD text + optional client info.
    Body: { jd_text, client_id?, client_contact_id?, title_hint?, fill_deadline? }
    """
    jd_text = body.get("jd_text")
    if not jd_text:
        raise HTTPException(400, "jd_text required")
    try:
        parsed = parse_jd(JobDescription(text=jd_text, title_hint=body.get("title_hint")))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    compliance = ComplianceRequirements(**(parsed.compliance.model_dump() if parsed.compliance else {}))
    jo = JobOrder(
        client_id=body.get("client_id"),
        client_contact_id=body.get("client_contact_id"),
        title=parsed.title,
        title_variants=parsed.title_variants,
        raw_jd_text=jd_text,
        parsed_jd=parsed,
        required_skills=parsed.required_skills,
        nice_to_have_skills=parsed.nice_to_have_skills,
        required_certs=parsed.required_certs,
        seniority=parsed.seniority,
        min_years_experience=parsed.min_years_experience,
        max_years_experience=parsed.max_years_experience,
        location=parsed.location,
        state=parsed.state,
        zip=parsed.zip,
        radius_miles=parsed.radius_miles or 25,
        remote_ok=parsed.remote_ok,
        pay_rate=parsed.pay_rate,
        pay_rate_unit=parsed.pay_rate_unit or "hourly",
        temps_needed=parsed.temps_needed,
        conversion_hours=parsed.conversion_hours,
        shift=parsed.shift,
        compliance=compliance,
        fill_deadline=body.get("fill_deadline"),
    )
    new_id = await create_job_order(jo)
    if not new_id:
        raise HTTPException(500, "Could not persist job order (Supabase not configured?)")
    row = await get_job_order(new_id)
    return row or {"id": new_id}
