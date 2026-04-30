"""Build free-mode source plans for state workforce portals."""
from __future__ import annotations

from app.core import parse_jd
from app.models import JobDescription, ParsedJD
from app.models.portal import PortalRecommendation, SourcePlanRequest, SourcePlanResponse

from .connectors import build_connector
from .directory import portals_for_state

ROLE_EXPANSIONS: dict[str, list[str]] = {
    "forklift": ["Forklift Operator", "Forklift Driver", "Lift Truck Operator"],
    "warehouse": ["Warehouse Associate", "Warehouse Worker", "Material Handler"],
    "cdl": ["CDL Driver", "Truck Driver"],
    "general labor": ["General Laborer", "Laborer"],
}


def generate_search_terms(parsed_jd: ParsedJD, *, max_terms: int = 10) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    candidates = [
        parsed_jd.title,
        *parsed_jd.title_variants,
        *parsed_jd.required_skills,
        *parsed_jd.required_certs,
    ]
    expansion_text = " ".join(candidates).lower()
    for keyword, expansions in ROLE_EXPANSIONS.items():
        if keyword in expansion_text:
            candidates.extend(expansions)
    for value in candidates:
        term = value.strip()
        key = term.lower()
        if term and key not in seen:
            terms.append(term)
            seen.add(key)
        if len(terms) >= max_terms:
            break
    return terms


def build_source_plan(request: SourcePlanRequest) -> SourcePlanResponse:
    parsed = parse_jd(JobDescription(text=request.jd_text, title_hint=request.title_hint))
    state = request.state or parsed.state
    city = request.city or parsed.city
    portals = portals_for_state(state)
    search_terms = generate_search_terms(parsed)

    recommendations: list[PortalRecommendation] = []
    for portal in portals:
        readiness = build_connector(portal).check_readiness()
        recommendations.append(
            PortalRecommendation(
                portal=portal,
                search_terms=search_terms,
                suggested_filters=portal.suggested_filters,
                automation_ready=readiness.ready and portal.automation_mode != "disabled",
                readiness_messages=readiness.messages,
                capture_guidance=portal.usage_guidance,
            )
        )

    message = None
    if not state:
        message = "No state found in the JD. Provide a state to choose a workforce portal."
    elif not recommendations:
        message = f"No workforce portal is configured for {state} yet."

    return SourcePlanResponse(
        parsed_jd=parsed,
        state=state,
        city=city,
        recommended_portals=recommendations,
        message=message,
    )
