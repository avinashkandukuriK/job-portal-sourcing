# Sourcing Upgrade v1 Design

## Goal

Build a free-mode workflow for blue-collar staffing that connects job descriptions to state workforce portals, automatically searches authorized employer accounts where automation is permitted, and saves visible/contactable candidates into the internal database.

The first release will not bypass portal access controls, MFA, CAPTCHA, rate limits, or terms of use. It will automate only with employer-authorized credentials and connector-specific rules. When a portal cannot be safely automated, the connector reports that limitation instead of falling back to hidden scraping.

## Scope

Version 1 includes:

- A state-directory based workforce portal registry.
- A source-plan API that parses a job description and recommends workforce portals.
- Search-term generation for blue-collar roles using parsed title, skills, and alternate titles.
- Candidate create/list/detail APIs for portal-sourced leads.
- A connector interface for automated workforce portal search and candidate capture.
- Secure runtime configuration for portal credentials.
- Supabase-backed candidate, source, and activity storage.
- Frontend screens for source planning, automated portal runs, and candidate review.

Version 1 starts with these portals:

- CA: CalJOBS
- IL: IllinoisJobLink
- FL: Employ Florida
- IN: Indiana Career Connect
- MA: MassHire JobQuest

The directory must be easy to extend later by adding new state entries without changing sourcing logic.

## Data Flow

1. Recruiter pastes a job description.
2. Backend parses title, skills, location, shift, pay, and compliance hints using the existing JD parser.
3. Source planner determines the target state from request input or parsed location.
4. Source planner selects matching workforce portal entries from the state directory.
5. Backend returns recommended portals, search terms, filters, and automation readiness.
6. Recruiter starts an automated portal run.
7. Portal connector uses configured employer credentials or an authorized session to search the workforce portal.
8. Connector extracts candidates that are visible/contactable to the employer account.
9. Backend normalizes, deduplicates, and saves candidates into Supabase.
10. Candidate record stores the person, source portal, source URL/note, capture method, contact visibility, and consent note.

## Backend Design

Add a new API module:

- `POST /api/source-plan`

Request fields:

- `jd_text`: required job description text.
- `state`: optional two-letter state override.
- `city`: optional city override.

Response fields:

- parsed JD summary.
- recommended portal list.
- generated search terms.
- suggested filters.
- compliance/capture guidance.

Add candidate APIs:

- `POST /api/candidates`
- `GET /api/candidates`
- `GET /api/candidates/{id}`

Candidate create should validate at least one contact method when status is contactable: email or phone.

Add portal automation APIs:

- `POST /api/portal-runs`
- `GET /api/portal-runs`
- `GET /api/portal-runs/{id}`

Portal run request fields:

- `jd_text`
- `state`
- `portal_id`
- `city`
- `limit`

Portal run response fields:

- run ID
- status
- portal metadata
- generated search terms
- candidates saved
- candidates skipped
- warnings
- connector errors

Portal connectors use a shared interface:

- `check_readiness()`
- `build_search_plan(parsed_jd)`
- `run_search(search_plan)`
- `normalize_candidate(raw_candidate)`
- `persist_candidates(candidates)`

Each connector must explicitly declare whether it supports official API access, browser automation, CSV export import, or no automation.

## State Directory

Use a static Python registry in the backend for v1. Each entry includes:

- state code
- state name
- portal name
- employer URL
- automation mode
- credential environment variable names
- candidate search notes
- suggested filters
- supported capture fields
- usage guidance

This avoids building admin tooling before it is needed while keeping a clean migration path to Supabase later.

## Database Design

Add a Supabase migration with:

- `candidates`
- `candidate_sources`
- `candidate_activity`
- `portal_runs`
- `portal_run_candidates`

Candidate fields include:

- full name
- email
- phone
- city
- state
- ZIP code
- current title
- desired roles
- skills
- certifications
- shift preference
- pay expectation
- availability
- notes
- status

Candidate source fields include:

- candidate ID
- source type
- source name
- source state
- source URL
- capture method
- contact visibility
- consent note
- first seen timestamp

Portal run fields include:

- portal ID
- state
- job description snapshot
- search terms
- status
- started timestamp
- completed timestamp
- candidates found
- candidates saved
- warning/error summary

## Frontend Design

Add a free-mode sourcing area to the existing React app:

- JD input stays as the starting point.
- Add a state selector for source planning.
- Show recommended workforce portal cards.
- Show generated search terms and suggested filters.
- Show automation readiness for each portal.
- Add a "Run Portal Search" action.
- Show portal run progress, saved candidates, skipped candidates, and warnings.
- Keep a candidate form for manual correction or fallback entry.
- Add a candidate list showing saved portal leads.

The UI should remain operational and dashboard-like, matching the current app style.

## Error Handling

- Missing JD text returns a 400 response.
- Unknown or unsupported state returns an empty recommendation with a clear message.
- Supabase failures return actionable backend errors without leaking secrets.
- Candidate create validates state code, source metadata, and contact method shape.
- Missing portal credentials mark the connector as not ready.
- MFA, CAPTCHA, unexpected page layouts, account lock warnings, and rate-limit blocks stop the connector and return a clear warning.
- Portal runs are idempotent where possible and dedupe candidates by email, phone, and source profile URL.

## Testing

Backend tests:

- source planner returns IllinoisJobLink for IL.
- source planner returns the five initial states from the directory.
- search terms include parsed title and relevant skills.
- candidate creation payload validates required fields.
- repository maps candidate/source rows correctly.
- portal connector readiness reports missing credentials.
- portal run persists normalized candidates and source metadata.
- portal run dedupes repeated candidate records.

Frontend verification:

- `npm run lint`
- `npm run build`

Backend verification:

- `ruff check app tests`
- `mypy app`
- `pytest`

## Security And Compliance

The app will not store portal passwords in the database. Credentials must be provided through environment variables or a managed secret store. The app will not bypass MFA, CAPTCHA, paywalls, rate limits, blocked accounts, or access controls. Candidate records saved from workforce portals must include source tracking and a consent/contact visibility note so recruiters know why the candidate was contactable.

Each portal connector must be reviewed against the portal's terms before production use. If a portal prohibits automation, the connector remains disabled unless the business receives written permission or an official API/export path is available.
