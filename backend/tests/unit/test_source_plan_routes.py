from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_source_plan_route_returns_illinois_portal(whitecap_jd_text: str) -> None:
    client = TestClient(create_app())

    response = client.post("/api/source-plan", json={"jd_text": whitecap_jd_text, "state": "IL"})

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "IL"
    assert body["recommended_portals"][0]["portal"]["id"] == "illinois_joblink"
    assert "Forklift" in body["recommended_portals"][0]["search_terms"]


def test_source_plan_route_rejects_empty_jd() -> None:
    client = TestClient(create_app())

    response = client.post("/api/source-plan", json={"jd_text": "", "state": "IL"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Empty job description"
