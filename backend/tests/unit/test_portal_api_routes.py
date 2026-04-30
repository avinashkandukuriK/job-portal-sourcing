from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Candidate, ContactInfo


def test_portal_run_route_returns_not_ready_without_credentials(whitecap_jd_text: str) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/portal-runs",
        json={"jd_text": whitecap_jd_text, "state": "IL", "portal_id": "illinois_joblink", "limit": 5},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["portal"]["id"] == "illinois_joblink"
    assert "ILLINOIS_JOBLINK_USERNAME" in body["warnings"][0]


def test_portal_run_route_rejects_unknown_portal(whitecap_jd_text: str) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/api/portal-runs",
        json={"jd_text": whitecap_jd_text, "state": "IL", "portal_id": "missing"},
    )

    assert response.status_code == 400


def test_candidate_list_route_returns_repository_candidates(monkeypatch) -> None:
    async def fake_list_candidates(*, limit: int = 50):
        return [
            Candidate(
                source="illinois_joblink",
                source_id="candidate-1",
                name="Maria Santos",
                current_title="Forklift Operator",
                location="Chicago, IL",
                skills=["Forklift"],
                contact=ContactInfo(email="maria@example.com", phone="3125550101"),
            )
        ]

    monkeypatch.setattr("app.api.candidates_routes.list_candidates", fake_list_candidates)
    client = TestClient(create_app())

    response = client.get("/api/candidates")

    assert response.status_code == 200
    assert response.json()[0]["name"] == "Maria Santos"


def test_candidate_detail_route_returns_404(monkeypatch) -> None:
    async def fake_get_candidate(candidate_id: str):
        return None

    monkeypatch.setattr("app.api.candidates_routes.get_candidate", fake_get_candidate)
    client = TestClient(create_app())

    response = client.get("/api/candidates/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Candidate not found"
