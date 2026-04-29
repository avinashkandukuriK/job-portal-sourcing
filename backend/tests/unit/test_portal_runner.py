from __future__ import annotations

import pytest

from app.core.portal_runner import run_portal_search
from app.models.portal import PortalRunRequest
from app.portals.directory import get_portal
from app.portals.sandbox_connector import SandboxPortalConnector


@pytest.mark.anyio
async def test_portal_runner_returns_not_ready_without_live_connector(whitecap_jd_text: str) -> None:
    response = await run_portal_search(
        PortalRunRequest(jd_text=whitecap_jd_text, state="IL", portal_id="illinois_joblink"),
        persist=False,
    )

    assert response.status == "not_ready"
    assert response.candidates == []
    assert "ILLINOIS_JOBLINK_USERNAME" in response.warnings[0]


@pytest.mark.anyio
async def test_portal_runner_uses_sandbox_connector_for_automated_results(whitecap_jd_text: str) -> None:
    portal = get_portal("illinois_joblink")
    assert portal is not None

    response = await run_portal_search(
        PortalRunRequest(jd_text=whitecap_jd_text, state="IL", portal_id="illinois_joblink", city="Chicago"),
        connector_override=SandboxPortalConnector(portal),
        persist=False,
    )

    assert response.status == "completed"
    assert response.candidates_found == 2
    assert response.candidates_saved == 2
    assert response.candidates[0].candidate.source == "illinois_joblink"
    assert response.candidates[0].candidate.contact.email
