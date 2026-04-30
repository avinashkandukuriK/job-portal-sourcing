"""Run automated workforce portal searches and persist normalized candidates."""
from __future__ import annotations

from app.db.repository import (
    create_portal_run,
    save_candidate_source,
    save_portal_run_candidate,
    update_portal_run,
    upsert_candidate,
)
from app.models.portal import PortalRunCandidate, PortalRunRequest, PortalRunResponse, SourcePlanRequest
from app.portals.connectors import PortalSearchPlan, build_connector
from app.portals.directory import get_portal
from app.portals.planner import build_source_plan


def _candidate_key(candidate: PortalRunCandidate) -> str:
    c = candidate.candidate
    if c.contact.email:
        return f"email:{c.contact.email.lower()}"
    if c.contact.phone:
        return f"phone:{c.contact.phone}"
    if c.profile_url:
        return f"url:{c.profile_url.lower()}"
    return f"{c.source}:{c.source_id}"


def _dedupe_candidates(candidates: list[PortalRunCandidate]) -> list[PortalRunCandidate]:
    seen: set[str] = set()
    unique: list[PortalRunCandidate] = []
    for candidate in candidates:
        key = _candidate_key(candidate)
        if key in seen:
            candidate.skipped_reason = "Duplicate candidate in portal run."
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


async def run_portal_search(
    request: PortalRunRequest,
    *,
    connector_override=None,
    persist: bool = True,
) -> PortalRunResponse:
    portal = get_portal(request.portal_id)
    if portal is None or portal.state != request.state:
        raise ValueError(f"Unknown portal for state: {request.portal_id} / {request.state}")

    source_plan = build_source_plan(
        SourcePlanRequest(
            jd_text=request.jd_text,
            state=request.state,
            city=request.city,
            title_hint=request.title_hint,
        )
    )
    recommendation = next(
        (item for item in source_plan.recommended_portals if item.portal.id == portal.id),
        None,
    )
    if recommendation is None:
        raise ValueError(f"Portal {portal.id} is not configured for {request.state}")

    connector = connector_override or build_connector(portal)
    readiness = connector.check_readiness()
    run = PortalRunResponse(
        status="running" if readiness.ready else "not_ready",
        portal=portal,
        parsed_jd=source_plan.parsed_jd,
        search_terms=recommendation.search_terms,
        warnings=[] if readiness.ready else readiness.messages,
    )
    run_id = await create_portal_run(run, raw_jd_text=request.jd_text) if persist else None
    run.id = run_id
    if not readiness.ready:
        return run

    result = await connector.run_search(
        PortalSearchPlan(
            portal=portal,
            parsed_jd=source_plan.parsed_jd,
            search_terms=recommendation.search_terms,
            city=request.city,
            limit=request.limit,
        )
    )
    portal_candidates = _dedupe_candidates([PortalRunCandidate(candidate=c) for c in result.candidates])
    saved = 0
    for portal_candidate in portal_candidates:
        candidate_id = await upsert_candidate(portal_candidate.candidate) if persist else None
        portal_candidate.candidate_id = candidate_id
        portal_candidate.saved = bool(candidate_id) or not persist
        if portal_candidate.saved:
            saved += 1
            if persist and candidate_id:
                await save_candidate_source(
                    candidate_id=candidate_id,
                    source_type="workforce_portal",
                    source_name=portal.name,
                    source_state=portal.state,
                    source_url=portal_candidate.candidate.profile_url,
                    consent_note="Candidate contact details visible through authorized employer workforce portal access.",
                )
        elif persist:
            portal_candidate.skipped_reason = "Candidate could not be saved."
        if persist and run_id:
            await save_portal_run_candidate(
                portal_run_id=run_id,
                candidate_id=portal_candidate.candidate_id,
                source_profile_url=portal_candidate.candidate.profile_url,
                candidate_snapshot=portal_candidate.candidate.model_dump(mode="json"),
                saved=portal_candidate.saved,
                skipped_reason=portal_candidate.skipped_reason,
            )

    run.status = "failed" if result.error else "completed"
    run.candidates = portal_candidates
    run.candidates_found = len(result.candidates)
    run.candidates_saved = saved
    run.candidates_skipped = len(result.candidates) - saved
    run.warnings = result.warnings
    run.error = result.error
    if persist and run_id:
        await update_portal_run(run_id, run, raw_jd_text=request.jd_text)
    return run
