"""Sandbox connector used by tests and local demos.

This is intentionally opt-in from the runner; production code should use real
portal-specific connectors once account access and terms are approved.
"""
from __future__ import annotations

from app.models import Candidate, ContactInfo
from app.models.portal import PortalDefinition

from .connectors import ConnectorReadiness, ConnectorSearchResult, PortalSearchPlan


class SandboxPortalConnector:
    def __init__(self, portal: PortalDefinition) -> None:
        self.portal = portal

    def check_readiness(self) -> ConnectorReadiness:
        return ConnectorReadiness(ready=True, messages=["Sandbox connector ready."])

    async def run_search(self, plan: PortalSearchPlan) -> ConnectorSearchResult:
        title = plan.parsed_jd.title if plan.parsed_jd.title != "Unknown Role" else "Warehouse Associate"
        city = plan.city or plan.parsed_jd.city or self.portal.state_name
        skills = plan.parsed_jd.required_skills[:4] or ["Warehouse", "Reliability"]
        candidates = [
            Candidate(
                source=self.portal.id,
                source_id=f"{self.portal.id}-sandbox-1",
                profile_url=f"{self.portal.employer_url.rstrip('/')}/candidate/sandbox-1",
                name="Maria Santos",
                current_title=title,
                location=f"{city}, {self.portal.state}",
                skills=skills,
                country="US",
                contact=ContactInfo(email="maria.santos@example.com", phone="555-010-4100"),
                raw={"portal": self.portal.name, "connector": "sandbox"},
            ),
            Candidate(
                source=self.portal.id,
                source_id=f"{self.portal.id}-sandbox-2",
                profile_url=f"{self.portal.employer_url.rstrip('/')}/candidate/sandbox-2",
                name="James Walker",
                current_title="Material Handler",
                location=f"{city}, {self.portal.state}",
                skills=list(dict.fromkeys([*skills, "Loading", "Unloading"])),
                country="US",
                contact=ContactInfo(email="james.walker@example.com", phone="555-010-4101"),
                raw={"portal": self.portal.name, "connector": "sandbox"},
            ),
        ]
        return ConnectorSearchResult(candidates=candidates[: plan.limit])
