# Sourcing Upgrade v1 Design

## Goal

Build a free-mode workflow for blue-collar staffing that connects job descriptions to state workforce portals, then lets recruiters manually save visible/contactable candidates into the internal database.

The first release will not automate login, scrape private candidate pages, or bypass portal employer workflows. It will guide the recruiter to the right state portal, generate practical search terms, and capture candidates found through employer accounts.

## Scope

Version 1 includes:

- A state-directory based workforce portal registry.
- A source-plan API that parses a job description and recommends workforce portals.
- Search-term generation for blue-collar roles using parsed title, skills, and alternate titles.
- Candidate create/list/detail APIs for manually captured portal leads.
- Supabase-backed candidate, source, and activity storage.
- Frontend screens for source planning and candidate capture.

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
5. Backend returns recommended portals, search terms, filters, and capture guidance.
6. Recruiter opens the portal manually, logs in with employer credentials, and searches.
7. Recruiter saves visible/contactable candidate data into the app.
8. Candidate record stores the person, source portal, source URL/note, capture method, contact visibility, and consent note.

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

## State Directory

Use a static Python registry in the backend for v1. Each entry includes:

- state code
- state name
- portal name
- employer URL
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

## Frontend Design

Add a free-mode sourcing area to the existing React app:

- JD input stays as the starting point.
- Add a state selector for source planning.
- Show recommended workforce portal cards.
- Show generated search terms and suggested filters.
- Add a "Save Candidate From Portal" form.
- Add a candidate list showing saved portal leads.

The UI should remain operational and dashboard-like, matching the current app style.

## Error Handling

- Missing JD text returns a 400 response.
- Unknown or unsupported state returns an empty recommendation with a clear message.
- Supabase failures return actionable backend errors without leaking secrets.
- Candidate create validates state code, source metadata, and contact method shape.

## Testing

Backend tests:

- source planner returns IllinoisJobLink for IL.
- source planner returns the five initial states from the directory.
- search terms include parsed title and relevant skills.
- candidate creation payload validates required fields.
- repository maps candidate/source rows correctly.

Frontend verification:

- `npm run lint`
- `npm run build`

Backend verification:

- `ruff check app tests`
- `mypy app`
- `pytest`

## Security And Compliance

The app will not store portal login credentials. It will not automatically scrape private candidate pages. Candidate records saved from workforce portals must include source tracking and a consent/contact visibility note so recruiters know why the candidate was contactable.
