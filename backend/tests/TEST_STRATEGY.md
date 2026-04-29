# Test Strategy

## Pyramid

```
              ┌────────────┐
              │    E2E     │   2-3 tests, hit live Supabase staging
              └────────────┘
            ┌────────────────┐
            │  Integration   │   ~10 tests, FastAPI + mock adapters + in-memory toggle store
            └────────────────┘
          ┌──────────────────────┐
          │     Unit Tests       │   ~50 tests, fast, focused on pure logic
          └──────────────────────┘
```

## What to test (and what type)

| Module | Test type | Coverage target |
|---|---|---|
| `core/jd_parser.py` | Unit — fixture JDs in / structured ParsedJD out | 90%+ — business-critical |
| `core/scorer.py` | Unit — fixture (Candidate, ParsedJD) pairs | 90%+ |
| `core/orchestrator.py` | Integration — fake adapters, assert dedup + scoring + persistence calls | 80%+ |
| `adapters/base.py` + `registry.py` | Unit — register/lookup/auto-discovery | 80%+ |
| `adapters/toggle_store.py` (JSONFileToggleStore) | Unit — enable/disable/pause/auto-disable lifecycle | 90%+ |
| `adapters/sources/craigslist.py` | Unit — fixture HTML in / Candidate out | parser only |
| `adapters/sources/internal_db.py` | Integration — mock Supabase → fake rows | smoke |
| `db/repository.py` | Integration — mock supabase client; assert correct queries | 70%+ |
| `models/*.py` | Unit — Pydantic round-trip | 100% (free) |
| `api/*_routes.py` | Integration — FastAPI TestClient | happy-path + 1-2 errors per endpoint |

## Skip

- Trivial getters / Pydantic field declarations (Pydantic itself is well-tested)
- Third-party clients (httpx, supabase-py)
- Type stubs and re-exports

## Critical paths (must have tests before we ship)

1. **JD parsing of the White Cap JD** — must extract title="Forklift", pay_rate=20.0, drug_test_panel=4, location="Albuquerque, NM", requires_i9=True, conversion_hours=400.
2. **Adapter framework** — `@register_adapter` decorator works, `discover_in_tree()` finds files, `is_active()` respects toggle state.
3. **Toggle lifecycle** — disable / pause / auto-resume / circuit-breaker auto-disable.
4. **Orchestrator dedup** — same candidate from two adapters merges to one.
5. **Scorer determinism** — same input → same output (no non-determinism from skill ordering).

## Initial gaps (acknowledged)

- No live-Supabase integration tests yet (would need staging schema separate from prod)
- No frontend tests (frontend not built yet)
- No load tests (premature for MVP)
- No security review (TCPA opt-out flow needs one before go-live)

## Test file layout

```
backend/tests/
├── TEST_STRATEGY.md          (this file)
├── conftest.py               (pytest fixtures)
├── unit/
│   ├── test_jd_parser.py
│   ├── test_scorer.py
│   ├── test_models.py
│   ├── test_adapter_registry.py
│   ├── test_toggle_store.py
│   └── test_capabilities.py
└── integration/
    ├── test_orchestrator.py
    └── test_api_smoke.py
```

## Running

```bash
cd backend
pip install -r requirements.txt
pip install pytest pytest-asyncio
pytest tests/ -v
```
