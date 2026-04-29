"""Connector contracts for state workforce portal automation."""
from __future__ import annotations

import os
from typing import Protocol

from pydantic import BaseModel, Field

from app.models import Candidate, ParsedJD
from app.models.portal import PortalDefinition


class ConnectorReadiness(BaseModel):
    ready: bool
    messages: list[str] = Field(default_factory=list)


class PortalSearchPlan(BaseModel):
    portal: PortalDefinition
    parsed_jd: ParsedJD
    search_terms: list[str]
    city: str | None = None
    limit: int = 25


class ConnectorSearchResult(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class PortalConnector(Protocol):
    portal: PortalDefinition

    def check_readiness(self) -> ConnectorReadiness:
        ...

    async def run_search(self, plan: PortalSearchPlan) -> ConnectorSearchResult:
        ...


class BrowserPortalConnector:
    """Live browser connector placeholder.

    The shared automation contract is in place, but each government portal still
    needs a reviewed, portal-specific Playwright script before production use.
    """

    def __init__(self, portal: PortalDefinition) -> None:
        self.portal = portal

    def check_readiness(self) -> ConnectorReadiness:
        missing = [name for name in self.portal.credential_env_vars if not os.getenv(name)]
        if missing:
            return ConnectorReadiness(
                ready=False,
                messages=[f"Missing portal credential env vars: {', '.join(missing)}"],
            )
        return ConnectorReadiness(
            ready=False,
            messages=[
                f"{self.portal.name} credentials are configured, but the live portal script has not been enabled yet.",
            ],
        )

    async def run_search(self, plan: PortalSearchPlan) -> ConnectorSearchResult:
        return ConnectorSearchResult(
            warnings=self.check_readiness().messages,
            error=f"Live automation for {plan.portal.name} is not enabled yet.",
        )


def build_connector(portal: PortalDefinition) -> PortalConnector:
    return BrowserPortalConnector(portal)
