"""Repository — thin functional wrapper over the Supabase tables.

One module per concern would be cleaner long term; for now we keep it flat
so the orchestrator and API can import a small set of names. All functions
are async-friendly and return None / [] gracefully when Supabase isn't wired.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Optional

from app.models import Candidate, JobOrder, ParsedJD

from .supabase_client import get_supabase

logger = logging.getLogger(__name__)


# ============================================================================
# Candidates
# ============================================================================

def _candidate_to_row(c: Candidate) -> dict[str, Any]:
    """Map our Candidate model to a candidates row insert."""
    contact = c.contact
    profile_urls: list[dict[str, Any]] = []
    if contact.linkedin_url:
        profile_urls.append({"kind": "linkedin", "url": contact.linkedin_url})
    if contact.github_url:
        profile_urls.append({"kind": "github", "url": contact.github_url})
    if contact.twitter_url:
        profile_urls.append({"kind": "twitter", "url": contact.twitter_url})
    if contact.personal_url:
        profile_urls.append({"kind": "personal", "url": contact.personal_url})

    state = None
    if c.location and "," in c.location:
        parts = [p.strip() for p in c.location.split(",")]
        if len(parts) >= 2 and len(parts[-1]) == 2:
            state = parts[-1]

    return {
        "name": c.name,
        "email": contact.email,
        "phone": contact.phone,
        "profile_urls": profile_urls,
        "headline": c.headline,
        "current_title": c.current_title,
        "current_company": c.current_company,
        "location": c.location,
        "state": state,
        "country": c.country or "US",
        "skills": list(c.skills or []),
        "skills_normalized": [s.lower() for s in (c.skills or [])],
        "years_experience": c.years_experience,
        "source": c.source,
        "source_id": c.source_id,
        "profile_url": c.profile_url,
        "raw": c.raw or {},
    }


async def upsert_candidate(c: Candidate) -> Optional[str]:
    """Insert-or-update a candidate. Returns the candidate id."""
    sb = get_supabase()
    if sb is None:
        return None
    row = _candidate_to_row(c)

    # Dedupe: try (source, source_id) first; then phone; then email
    existing_id = None
    try:
        if row["source"] and row["source_id"]:
            res = sb.table("candidates").select("id") \
                .eq("source", row["source"]).eq("source_id", row["source_id"]).limit(1).execute()
            if res.data:
                existing_id = res.data[0]["id"]
        if not existing_id and row.get("phone"):
            res = sb.table("candidates").select("id").eq("phone", row["phone"]).limit(1).execute()
            if res.data:
                existing_id = res.data[0]["id"]
        if not existing_id and row.get("email"):
            res = sb.table("candidates").select("id") \
                .ilike("email", row["email"]).limit(1).execute()
            if res.data:
                existing_id = res.data[0]["id"]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Dedup lookup failed: %s", exc)

    try:
        if existing_id:
            sb.table("candidates").update(row).eq("id", existing_id).execute()
            return existing_id
        res = sb.table("candidates").insert(row).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Candidate upsert failed: %s", exc)
    return None


async def upsert_candidates_batch(candidates: Iterable[Candidate]) -> list[str]:
    """Sequential upserts (Supabase Python client doesn't expose true bulk
    upsert with custom dedup logic). Returns list of resulting ids in order.
    """
    out: list[str] = []
    for c in candidates:
        cid = await upsert_candidate(c)
        if cid:
            out.append(cid)
    return out


async def search_candidates(jd: ParsedJD, *, limit: int = 25) -> list[Candidate]:
    """Internal-DB search adapter calls this to find matches in your warm pool."""
    sb = get_supabase()
    if sb is None:
        return []

    try:
        q = sb.table("candidates").select("*").is_("archived_at", "null")

        # Country filter (US-focused)
        if jd.location_country:
            q = q.eq("country", jd.location_country)

        # State filter when known
        if jd.state:
            q = q.eq("state", jd.state)

        # Skill filter — overlap on skills_normalized array
        skills_norm = [s.lower() for s in (jd.required_skills or [])]
        if skills_norm:
            # PostgREST: array overlap operator
            q = q.overlaps("skills_normalized", skills_norm)

        res = q.limit(limit).execute()
        return [_row_to_candidate(r) for r in (res.data or [])]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Internal candidate search failed: %s", exc)
        return []


def _row_to_candidate(r: dict[str, Any]) -> Candidate:
    from app.models import ContactInfo
    profile_urls = r.get("profile_urls") or []
    by_kind = {p.get("kind"): p.get("url") for p in profile_urls if isinstance(p, dict)}
    return Candidate(
        source=r.get("source") or "internal_db",
        source_id=r.get("source_id") or r["id"],
        profile_url=r.get("profile_url"),
        name=r.get("name") or "Unknown",
        headline=r.get("headline"),
        current_title=r.get("current_title"),
        current_company=r.get("current_company"),
        location=r.get("location"),
        country=r.get("country"),
        skills=r.get("skills") or [],
        years_experience=r.get("years_experience"),
        contact=ContactInfo(
            email=r.get("email"),
            phone=r.get("phone"),
            linkedin_url=by_kind.get("linkedin"),
            github_url=by_kind.get("github"),
            twitter_url=by_kind.get("twitter"),
            personal_url=by_kind.get("personal"),
        ),
        raw=r.get("raw") or {},
    )


# ============================================================================
# Job orders
# ============================================================================

async def create_job_order(jo: JobOrder) -> Optional[str]:
    sb = get_supabase()
    if sb is None:
        return None
    row = jo.model_dump(mode="json", exclude={"id", "created_at", "updated_at", "parsed_jd"})
    if jo.parsed_jd:
        row["parsed_jd"] = jo.parsed_jd.model_dump(mode="json")
    # Flatten compliance requirements onto top-level columns
    comp = jo.compliance
    row.update({
        "requires_i9": comp.requires_i9,
        "requires_everify": comp.requires_everify,
        "requires_drug_test": comp.requires_drug_test,
        "drug_test_panel": comp.drug_test_panel,
        "requires_background_check": comp.requires_background_check,
        "background_check_levels": comp.background_check_levels,
        "requires_nda": comp.requires_nda,
    })
    row.pop("compliance", None)
    try:
        res = sb.table("job_orders").insert(row).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Job order create failed: %s", exc)
    return None


async def get_job_order(job_order_id: str) -> Optional[dict]:
    sb = get_supabase()
    if sb is None:
        return None
    res = sb.table("job_orders").select("*").eq("id", job_order_id).limit(1).execute()
    return (res.data or [None])[0]


async def list_job_orders(*, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    sb = get_supabase()
    if sb is None:
        return []
    q = sb.table("job_orders").select("*").order("created_at", desc=True).limit(limit)
    if status:
        q = q.eq("status", status)
    res = q.execute()
    return res.data or []


# ============================================================================
# Searches + adapter run log + search results
# ============================================================================

async def save_search(
    *,
    job_order_id: Optional[str],
    user_id: Optional[str],
    raw_jd_text: Optional[str],
    parsed_jd: ParsedJD,
    mode: str,
    selected_adapters: list[str],
    candidate_count: int,
    duration_ms: Optional[int],
    total_cost_usd: float = 0.0,
) -> Optional[str]:
    sb = get_supabase()
    if sb is None:
        return None
    row = {
        "job_order_id": job_order_id,
        "user_id": user_id,
        "raw_jd_text": raw_jd_text,
        "parsed_jd": parsed_jd.model_dump(mode="json"),
        "mode": mode,
        "selected_adapters": selected_adapters,
        "candidate_count": candidate_count,
        "duration_ms": duration_ms,
        "total_cost_usd": total_cost_usd,
        "completed_at": datetime.utcnow().isoformat(),
    }
    try:
        res = sb.table("searches").insert(row).execute()
        if res.data:
            return res.data[0]["id"]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Save search failed: %s", exc)
    return None


async def save_adapter_run_log(
    *,
    search_id: str,
    adapter_name: str,
    candidates_returned: int,
    duration_ms: Optional[int],
    cost_usd: float = 0.0,
    rate_limited: bool = False,
    error_message: Optional[str] = None,
) -> None:
    sb = get_supabase()
    if sb is None:
        return
    try:
        sb.table("adapter_run_log").insert({
            "search_id": search_id,
            "adapter_name": adapter_name,
            "candidates_returned": candidates_returned,
            "duration_ms": duration_ms,
            "cost_usd": cost_usd,
            "rate_limited": rate_limited,
            "error_message": error_message,
        }).execute()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Save adapter run log failed: %s", exc)


async def save_search_results(
    *,
    search_id: str,
    scored: list[dict],     # [{candidate_id, adapter_name, score, score_breakdown, reasoning, rank}]
) -> None:
    sb = get_supabase()
    if sb is None or not scored:
        return
    rows = [{**r, "search_id": search_id} for r in scored]
    try:
        sb.table("search_results").insert(rows).execute()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Save search results failed: %s", exc)
