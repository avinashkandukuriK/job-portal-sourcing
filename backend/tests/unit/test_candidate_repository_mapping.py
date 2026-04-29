from __future__ import annotations

from app.db.repository import _candidate_source_to_row, _candidate_to_row, _portal_run_to_row
from app.models import Candidate, ContactInfo
from app.models.portal import PortalRunResponse, SourcePlanRequest
from app.portals import build_source_plan


def test_candidate_to_row_maps_portal_contact_and_source() -> None:
    candidate = Candidate(
        source="illinois_joblink",
        source_id="ijl-123",
        profile_url="https://ijl.illinois.gov/profile/ijl-123",
        name="Maria Santos",
        current_title="Forklift Operator",
        location="Chicago, IL",
        skills=["Forklift", "Warehouse"],
        contact=ContactInfo(email="maria@example.com", phone="3125550101"),
        raw={"portal": "IllinoisJobLink"},
    )

    row = _candidate_to_row(candidate)

    assert row["source"] == "illinois_joblink"
    assert row["source_id"] == "ijl-123"
    assert row["email"] == "maria@example.com"
    assert row["phone"] == "3125550101"
    assert row["state"] == "IL"
    assert row["skills_normalized"] == ["forklift", "warehouse"]


def test_candidate_source_to_row_tracks_visibility_and_capture_method() -> None:
    row = _candidate_source_to_row(
        candidate_id="candidate-1",
        source_type="workforce_portal",
        source_name="IllinoisJobLink",
        source_state="IL",
        source_url="https://ijl.illinois.gov/profile/ijl-123",
        capture_method="automated_portal",
        contact_visibility="visible_in_employer_portal",
        consent_note="Contact fields visible through employer account.",
    )

    assert row["candidate_id"] == "candidate-1"
    assert row["source_name"] == "IllinoisJobLink"
    assert row["capture_method"] == "automated_portal"
    assert row["contact_visibility"] == "visible_in_employer_portal"


def test_portal_run_to_row_preserves_jd_and_counts(whitecap_jd_text: str) -> None:
    plan = build_source_plan(SourcePlanRequest(jd_text=whitecap_jd_text, state="IL"))
    portal = plan.recommended_portals[0].portal
    run = PortalRunResponse(
        status="completed",
        portal=portal,
        parsed_jd=plan.parsed_jd,
        search_terms=plan.recommended_portals[0].search_terms,
        candidates_found=2,
        candidates_saved=1,
        candidates_skipped=1,
        warnings=["Skipped duplicate candidate."],
    )

    row = _portal_run_to_row(run, raw_jd_text=whitecap_jd_text)

    assert row["portal_id"] == "illinois_joblink"
    assert row["portal_name"] == "IllinoisJobLink"
    assert row["state"] == "IL"
    assert row["status"] == "completed"
    assert row["candidates_found"] == 2
    assert row["search_terms"][0] == "Forklift"
