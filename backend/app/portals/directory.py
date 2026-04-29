"""Static state workforce portal directory.

The shape is intentionally data-first so these entries can move to Supabase
later without changing the planner or connector interfaces.
"""
from __future__ import annotations

from app.models.portal import PortalDefinition

_PORTALS: tuple[PortalDefinition, ...] = (
    PortalDefinition(
        id="caljobs",
        state="CA",
        state_name="California",
        name="CalJOBS",
        employer_url="https://edd.ca.gov/caljobs",
        automation_mode="browser",
        credential_env_vars=["CALJOBS_USERNAME", "CALJOBS_PASSWORD"],
        suggested_filters=["location", "resume active", "skills", "occupation", "last updated"],
        supported_capture_fields=["name", "email", "phone", "city", "state", "zip", "skills", "resume"],
        search_notes="Use CalJOBS employer candidate search for resumes made visible to employers.",
        usage_guidance="Search only through an authorized employer account and capture candidates visible to that account.",
    ),
    PortalDefinition(
        id="illinois_joblink",
        state="IL",
        state_name="Illinois",
        name="IllinoisJobLink",
        employer_url="https://ijl.illinois.gov/employer",
        automation_mode="browser",
        credential_env_vars=["ILLINOIS_JOBLINK_USERNAME", "ILLINOIS_JOBLINK_PASSWORD"],
        suggested_filters=["location", "active resume", "skills", "job title", "resume match alerts"],
        supported_capture_fields=["name", "email", "phone", "city", "state", "zip", "skills", "resume"],
        search_notes="IllinoisJobLink supports free employer candidate search and resume match alerts.",
        usage_guidance="Use employer login, search active resumes, and save contactable candidates into the internal DB.",
    ),
    PortalDefinition(
        id="employ_florida",
        state="FL",
        state_name="Florida",
        name="Employ Florida",
        employer_url="https://www.employflorida.com/",
        automation_mode="browser",
        credential_env_vars=["EMPLOY_FLORIDA_USERNAME", "EMPLOY_FLORIDA_PASSWORD"],
        suggested_filters=["location", "skills", "resume search agent", "occupation", "availability"],
        supported_capture_fields=["name", "email", "phone", "city", "state", "zip", "skills", "resume"],
        search_notes="Employ Florida offers employer tools for candidate search and resume search agents.",
        usage_guidance="Run searches through employer access and preserve portal source metadata for every saved lead.",
    ),
    PortalDefinition(
        id="indiana_career_connect",
        state="IN",
        state_name="Indiana",
        name="Indiana Career Connect",
        employer_url="https://www.indianacareerconnect.com/",
        automation_mode="browser",
        credential_env_vars=["INDIANA_CAREER_CONNECT_USERNAME", "INDIANA_CAREER_CONNECT_PASSWORD"],
        suggested_filters=["location", "candidate search", "skills", "qualifications", "resume"],
        supported_capture_fields=["name", "email", "phone", "city", "state", "zip", "skills", "resume"],
        search_notes="Indiana Career Connect provides free employer candidate searches for Hoosier job seekers.",
        usage_guidance="Use the employer candidate search workflow and stop on account challenges or access warnings.",
    ),
    PortalDefinition(
        id="masshire_jobquest",
        state="MA",
        state_name="Massachusetts",
        name="MassHire JobQuest",
        employer_url="https://jobquest.dcs.eol.mass.gov/jobquest/Employers",
        automation_mode="browser",
        credential_env_vars=["MASSHIRE_JOBQUEST_USERNAME", "MASSHIRE_JOBQUEST_PASSWORD"],
        suggested_filters=["location", "JobMatch profile", "resume", "skills", "job title"],
        supported_capture_fields=["name", "email", "phone", "city", "state", "zip", "skills", "resume"],
        search_notes="MassHire JobQuest lets employers attract and select qualified candidates.",
        usage_guidance="Use configured employer access and save candidates with contact visibility notes.",
    ),
)


def list_portals() -> list[PortalDefinition]:
    return list(_PORTALS)


def portals_for_state(state: str | None) -> list[PortalDefinition]:
    if not state:
        return []
    normalized = state.strip().upper()
    return [portal for portal in _PORTALS if portal.state == normalized]


def get_portal(portal_id: str) -> PortalDefinition | None:
    normalized = portal_id.strip().lower()
    return next((portal for portal in _PORTALS if portal.id == normalized), None)
