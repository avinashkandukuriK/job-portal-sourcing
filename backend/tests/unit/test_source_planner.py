from __future__ import annotations

from app.models.portal import SourcePlanRequest
from app.portals import build_source_plan, generate_search_terms, list_portals, portals_for_state


def test_directory_contains_initial_state_workforce_portals() -> None:
    portal_ids = {portal.id for portal in list_portals()}

    assert {
        "caljobs",
        "illinois_joblink",
        "employ_florida",
        "indiana_career_connect",
        "masshire_jobquest",
    }.issubset(portal_ids)


def test_portals_for_state_returns_illinois_joblink() -> None:
    portals = portals_for_state("il")

    assert len(portals) == 1
    assert portals[0].id == "illinois_joblink"
    assert portals[0].name == "IllinoisJobLink"


def test_generate_search_terms_include_title_variants_and_skills(whitecap_jd_text: str) -> None:
    plan = build_source_plan(SourcePlanRequest(jd_text=whitecap_jd_text, state="IL"))

    terms = generate_search_terms(plan.parsed_jd)

    assert "Forklift" in terms
    assert "forklift driver" in [term.lower() for term in terms]
    assert "Warehouse" in terms


def test_source_plan_returns_recommendation_for_state_override(whitecap_jd_text: str) -> None:
    plan = build_source_plan(SourcePlanRequest(jd_text=whitecap_jd_text, state="IL", city="Chicago"))

    assert plan.state == "IL"
    assert plan.city == "Chicago"
    assert plan.recommended_portals[0].portal.id == "illinois_joblink"
    assert "Forklift" in plan.recommended_portals[0].search_terms
    assert plan.recommended_portals[0].automation_ready is False
    assert "ILLINOIS_JOBLINK_USERNAME" in plan.recommended_portals[0].readiness_messages[0]


def test_source_plan_reports_missing_state() -> None:
    plan = build_source_plan(SourcePlanRequest(jd_text="Need warehouse help with loading and unloading."))

    assert plan.state is None
    assert plan.recommended_portals == []
    assert plan.message == "No state found in the JD. Provide a state to choose a workforce portal."
