# Adding a new adapter

This codebase is built so adding a new source — a state workforce board, a
niche job site, a paid API, anything — is a **single-file drop-in**. No edits
to the orchestrator, the API layer, the React frontend, or any registry list.

## The contract

Every adapter must:

1. Subclass `SourceAdapter` from `app.adapters.base`.
2. Define a class-level `metadata: AdapterMetadata` describing what it is.
3. Implement `async search(jd, limit) -> list[Candidate]`.
4. Apply the `@register_adapter` decorator.

That's the whole contract. Everything else (UI tabs, cost estimation, health
checks, rate-limit gating, on/off toggles, role-type filtering, region
filtering) is read declaratively from `metadata`.

## In-tree adapters (recommended for first-party sources)

Drop a new `.py` file in `backend/app/adapters/sources/`. Filename =
snake_case, same as the adapter name. At startup the registry walks the
`sources/` package and imports every module, so the decorator runs.

### Minimal example

```python
# app/adapters/sources/my_new_board.py
from app.adapters import (
    AdapterAccessMode, AdapterCapability, AdapterMetadata, AdapterTier,
    RoleType, SourceAdapter, register_adapter,
)
from app.models import Candidate, ContactInfo, ParsedJD


@register_adapter
class MyNewBoardAdapter(SourceAdapter):
    metadata = AdapterMetadata(
        name="my_new_board",
        display_name="My New Board",
        tier=AdapterTier.NON_PREMIUM,
        access_mode=AdapterAccessMode.PUBLIC_API,
        capabilities=[AdapterCapability.SEARCH],
        supported_role_types=[RoleType.BLUE_COLLAR, RoleType.DRIVING],
        supported_regions=["US"],
        required_env_vars=[],
    )

    async def search(self, jd: ParsedJD, limit: int = 25) -> list[Candidate]:
        # 1. Translate parsed JD into the source's query language
        # 2. Call the source
        # 3. Return list[Candidate] normalized into our schema
        return []
```

That's it. Restart the backend and the new adapter shows up:
- In `GET /api/adapters` (status + metadata)
- In the source picker UI (under the right tier tab)
- In every search the orchestrator runs (when enabled and matching the JD)

## Third-party / out-of-tree adapters (Python plugins)

External Python packages can register adapters via the `sourcing.adapters`
entry-point group. Useful when you want to:
- Ship an adapter as a separately maintained pip package
- Keep proprietary adapters out of this repo
- Let third parties extend the system without forking

In your plugin package's `pyproject.toml`:

```toml
[project.entry-points."sourcing.adapters"]
my_board = "my_pkg.adapters:MyBoardAdapter"
another_board = "my_pkg.adapters:AnotherBoardAdapter"
```

Then `pip install my_pkg` in the same environment as this app. The registry's
`discover_entry_points()` finds them at startup automatically.

## Metadata reference (what each field controls)

| Field | What it controls |
|---|---|
| `name` | Stable ID. Used in URLs, env vars, attribution, dedup keys. **Don't change after launch.** |
| `display_name` | Label in UI. Free to change. |
| `tier` | Which tab in the source picker (`INTERNAL`, `NON_PREMIUM`, `PREMIUM`, `INBOUND`). |
| `access_mode` | How data is fetched (`PUBLIC_API`, `PAID_API`, `SCRAPING`, etc). Drives logging, retry, ToS warning. |
| `capabilities` | Which features (`SEARCH`, `ENRICH`, `POST_JOB`, `EMAIL_LOOKUP`, `PHONE_LOOKUP`, `VERIFY`, `BULK`, `STREAM`). |
| `supported_role_types` | Orchestrator skips this adapter for JDs outside its taxonomy. |
| `supported_regions` | Same idea, for geography. |
| `cost.per_search` / `per_candidate` | Premium tab shows estimated spend before the recruiter clicks Run. |
| `rate_limit_per_min/day` | Orchestrator throttles calls to respect limits. |
| `required_env_vars` | Default `is_enabled()` checks all are populated. Adapter shows up disabled in UI with a tooltip listing missing vars. |
| `tos_risk` | UI warns the recruiter before enabling. |
| `is_experimental` / `deprecated` | UI flags / sorts accordingly. |

## Lifecycle hooks (all optional)

```python
async def setup(self) -> None:
    # Open httpx client, load model, etc.
    self._client = httpx.AsyncClient(...)

async def aclose(self) -> None:
    # Cleanup
    await self._client.aclose()

async def is_enabled(self) -> bool:
    # Default checks required_env_vars; override for richer checks
    return True

async def status(self) -> AdapterStatus:
    # Override for live ping/health-check
    return AdapterStatus.READY
```

## Optional capabilities

If your adapter declares `AdapterCapability.ENRICH`, also implement:

```python
async def enrich(self, candidate: Candidate) -> Candidate:
    # Fill in missing email/phone/skills/etc.
    return candidate
```

If it declares `AdapterCapability.POST_JOB`, also implement:

```python
async def post_job(self, parsed_jd: ParsedJD, *, dry_run: bool = False) -> dict:
    return {"posting_url": "...", "external_id": "..."}
```

## Testing a new adapter

1. Run `python -m app.cli adapters list` — your adapter should appear.
2. Run `python -m app.cli adapters status my_new_board` — should report READY.
3. Hit `GET /api/adapters` — your adapter is there with metadata + status.
4. Open the React UI → New Search → Source Picker — your adapter is in the right tab.
5. Run an end-to-end search and verify candidates flow into the results table.

## Naming conventions

- File and `metadata.name`: lowercase snake_case. Use the canonical brand
  name when applicable (`indeed_resume`, `ziprecruiter`, `nm_workforce`).
- Class name: PascalCase + `Adapter` suffix (`IndeedResumeAdapter`).
- One adapter per file. Easier to grep, easier to delete.
- Required env vars: `UPPER_SNAKE_CASE`, prefixed with the source name
  (`INDEED_PUBLISHER_ID`, `PROXYCURL_API_KEY`).

## Versioning

Bump `metadata.version` (semver) when you change the adapter. Future migration
tooling will use this to detect and re-run migrations on candidate records
sourced by older versions of the adapter.

## Runtime on/off (toggle layer)

Every registered adapter has a persistent toggle record (separate from
code-level config). State is one of `enabled`, `disabled`, `paused`, or
`auto_disabled`. The orchestrator calls `is_active()` which is the AND of:

- **`is_configured()`** — code-level: env vars present, not deprecated
- **`get_toggle().is_currently_active()`** — runtime: not admin-disabled,
  paused window expired, etc.

So a fully-configured adapter that's been disabled by an admin will silently
sit out of search runs until re-enabled. No code changes, no restart.

### How to flip an adapter

**HTTP** — used by the admin UI:
```
POST /api/adapters/indeed_resume/disable    {"reason": "rate-limited today"}
POST /api/adapters/indeed_resume/enable
POST /api/adapters/craigslist/pause         {"minutes": 60, "reason": "captcha hit"}
POST /api/adapters/craigslist/resume
POST /api/adapters/bulk/disable             {"names": ["monster", "careerbuilder"]}
```

**CLI** — for ops / debugging:
```
python -m app.cli adapters list
python -m app.cli adapters status indeed_resume
python -m app.cli adapters disable indeed_resume --reason "rate limit"
python -m app.cli adapters enable indeed_resume
python -m app.cli adapters pause craigslist --minutes 60 --reason "captcha"
python -m app.cli adapters resume craigslist
```

**Storage** — JSON file (`data/adapter_toggles.json`) for dev, Supabase
(`adapter_toggles` table) for prod. The factory in `toggle_store.py` picks
based on `SUPABASE_URL`/`SUPABASE_KEY` presence.

### Optional: circuit-breaker auto-disable

Adapters that fail consecutively can be auto-disabled by calling
`get_toggle_store().record_failure(name)` from your error path. After 5
consecutive failures (configurable) the store flips state to `auto_disabled`
with a 30-minute cooldown. A successful call clears it via
`record_success(name)`. Wire this into your `search()` exception handler if
you want the safety net.
