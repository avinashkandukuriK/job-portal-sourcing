# Sourcing Upgrade v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a free-mode state workforce portal integration path where a pasted JD selects a state portal, starts an automated portal run, normalizes fetched candidates, and shows/saves them in the app.

**Architecture:** Add a focused backend portal package with a static state directory, a source planner, and a connector interface. Version 1 ships with deterministic mock connectors for the five starting portals so the API/UI/storage path is real and testable before adding live browser/API automation per portal. Candidate and portal-run persistence uses Supabase when configured and degrades gracefully in local/dev mode.

**Tech Stack:** FastAPI, Pydantic, Supabase Python client, pytest, ruff, mypy, React, TypeScript, Vite.

---

### Task 1: Portal Directory And Source Planner

**Files:**
- Create: `backend/app/portals/__init__.py`
- Create: `backend/app/portals/directory.py`
- Create: `backend/app/portals/planner.py`
- Create: `backend/app/models/portal.py`
- Test: `backend/tests/unit/test_source_planner.py`

- [ ] **Step 1: Write tests**

Create tests that assert the initial five state portals exist, Illinois resolves to IllinoisJobLink, and JD search terms include title/skills.

- [ ] **Step 2: Implement models**

Add Pydantic models for `PortalDefinition`, `SourcePlanRequest`, `SourcePlanResponse`, and `PortalRecommendation`.

- [ ] **Step 3: Implement directory**

Add static entries for CA, IL, FL, IN, and MA with portal IDs, employer URLs, suggested filters, automation mode, credential env var names, and usage guidance.

- [ ] **Step 4: Implement planner**

Parse the JD with `parse_jd`, resolve state from request override or parsed JD, generate search terms from title/title variants/skills/certs, and return matching portal recommendations.

- [ ] **Step 5: Verify**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_source_planner.py -v`

### Task 2: Source Plan API

**Files:**
- Create: `backend/app/api/source_plan_routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_source_plan_routes.py`

- [ ] **Step 1: Write route tests**

Use FastAPI `TestClient` to POST `/api/source-plan` with an Illinois forklift JD and assert the response includes `illinois_joblink`.

- [ ] **Step 2: Implement route**

Add `POST /api/source-plan` that accepts `SourcePlanRequest`, calls the planner, returns `SourcePlanResponse`, and maps empty JD errors to HTTP 400.

- [ ] **Step 3: Register route**

Include the new router in `backend/app/main.py`.

- [ ] **Step 4: Verify**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_source_plan_routes.py -v`

### Task 3: Candidate And Portal Run Persistence

**Files:**
- Modify: `backend/app/db/repository.py`
- Create: `backend/migrations/004_portal_sourcing.sql`
- Test: `backend/tests/unit/test_candidate_repository_mapping.py`

- [ ] **Step 1: Write repository mapping tests**

Test candidate row mapping for source metadata and portal run row construction without requiring a live Supabase client.

- [ ] **Step 2: Add migration**

Create Supabase SQL for `candidate_sources`, `candidate_activity`, `portal_runs`, and `portal_run_candidates`. Keep existing `candidates` compatible.

- [ ] **Step 3: Add repository functions**

Add `list_candidates`, `get_candidate`, `save_candidate_source`, `create_portal_run`, `update_portal_run`, and `save_portal_run_candidate`.

- [ ] **Step 4: Verify**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_candidate_repository_mapping.py -v`

### Task 4: Portal Connector Framework And Mock Runs

**Files:**
- Create: `backend/app/portals/connectors.py`
- Create: `backend/app/portals/mock_connector.py`
- Create: `backend/app/core/portal_runner.py`
- Test: `backend/tests/unit/test_portal_runner.py`

- [ ] **Step 1: Write runner tests**

Test that a portal run checks readiness, generates candidates, dedupes by email/phone/profile URL, and returns saved/skipped counts.

- [ ] **Step 2: Implement connector protocol**

Define `PortalConnector`, `ConnectorReadiness`, `PortalSearchPlan`, and `PortalRunResult`.

- [ ] **Step 3: Implement mock connector**

Return realistic blue-collar candidate records for the selected portal. This gives the UI and storage path real data while live portal automation is added separately.

- [ ] **Step 4: Implement runner**

Use the planner, directory, connector registry, candidate upsert, source save, and portal-run save/update functions.

- [ ] **Step 5: Verify**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_portal_runner.py -v`

### Task 5: Portal Run And Candidate APIs

**Files:**
- Create: `backend/app/api/portal_runs_routes.py`
- Create: `backend/app/api/candidates_routes.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/unit/test_portal_api_routes.py`

- [ ] **Step 1: Write API tests**

Test `POST /api/portal-runs`, `GET /api/portal-runs`, `GET /api/candidates`, and `GET /api/candidates/{id}` with repository calls monkeypatched.

- [ ] **Step 2: Implement routes**

Expose portal run creation and listing, plus candidate listing/detail. Return clear 404s for missing candidates.

- [ ] **Step 3: Register routes**

Include both routers in `backend/app/main.py`.

- [ ] **Step 4: Verify**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest tests/unit/test_portal_api_routes.py -v`

### Task 6: Frontend Integration

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Add API types and functions**

Add `SourcePlanResponse`, `PortalRunResponse`, `CandidateSummary`, `createSourcePlan`, `runPortalSearch`, and `getCandidates`.

- [ ] **Step 2: Add source planner UI**

Add state selector, "Plan Free Sources", portal cards, search terms, readiness, and "Run Portal Search".

- [ ] **Step 3: Add portal results UI**

Show fetched candidates in the app with name, email, phone, source portal, score/status, and save status.

- [ ] **Step 4: Verify**

Run: `cd frontend; npm run lint; npm run build`

### Task 7: Full Verification And Commit

**Files:**
- Update: affected backend/frontend files

- [ ] **Step 1: Backend quality**

Run: `cd backend; .\.venv\Scripts\python.exe -m ruff check app tests`

- [ ] **Step 2: Backend typing**

Run: `cd backend; .\.venv\Scripts\python.exe -m mypy app`

- [ ] **Step 3: Backend tests**

Run: `cd backend; .\.venv\Scripts\python.exe -m pytest`

- [ ] **Step 4: Frontend checks**

Run: `cd frontend; npm run lint; npm run build`

- [ ] **Step 5: Commit**

Commit the implemented sourcing upgrade with a concise message after all checks pass.
