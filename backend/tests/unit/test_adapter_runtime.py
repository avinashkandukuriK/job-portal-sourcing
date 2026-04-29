"""Adapter runtime tests for deploy-critical behavior."""
from __future__ import annotations

import sys
import types

from fastapi.testclient import TestClient


def test_bulk_enable_route_is_not_shadowed(monkeypatch) -> None:
    import app.api.adapters_routes as routes
    from app.adapters import discover_all
    from app.adapters.toggle_store import AdapterToggle
    from app.main import create_app

    class FakeStore:
        def enable(self, name: str, *, set_by: str | None = None, reason: str | None = None) -> AdapterToggle:
            return AdapterToggle(name=name, set_by=set_by, reason=reason)

    discover_all()
    monkeypatch.setattr(routes, "get_toggle_store", lambda: FakeStore())

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/adapters/bulk/enable",
            json={"names": ["craigslist"], "reason": "deployment smoke"},
        )

    assert response.status_code == 200
    assert response.json()[0]["name"] == "craigslist"


def test_discovery_registers_public_api_adapters() -> None:
    from app.adapters import all_adapter_classes, discover_all

    discover_all()
    names = {cls.metadata.name for cls in all_adapter_classes()}

    assert "github" in names
    assert "stackoverflow" in names


def test_toggle_store_prefers_service_key_for_supabase(monkeypatch) -> None:
    import app.adapters.toggle_store as toggle_store
    import app.config as config

    captured: dict[str, str] = {}

    def fake_create_client(url: str, key: str) -> object:
        captured["url"] = url
        captured["key"] = key
        return object()

    fake_supabase = types.SimpleNamespace(create_client=fake_create_client)
    monkeypatch.setitem(sys.modules, "supabase", fake_supabase)

    settings = types.SimpleNamespace(
        has_supabase=True,
        supabase_url="https://example.supabase.co",
        supabase_key="publishable-key",
        supabase_service_key="service-role-key",
    )
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    toggle_store.reset_toggle_store()

    store = toggle_store.get_toggle_store()

    assert store.__class__.__name__ == "SupabaseToggleStore"
    assert captured == {
        "url": "https://example.supabase.co",
        "key": "service-role-key",
    }
    toggle_store.reset_toggle_store()
