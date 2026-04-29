# Deployment Flow

This repo is prepared for the flow:

1. Push code to GitHub.
2. Deploy `frontend/` to Vercel.
3. Deploy `backend/` to Render.
4. Use Supabase for Postgres.
5. Add Supabase environment variables to Render.
6. Add the Render backend API URL to Vercel.
7. Test frontend -> backend -> database.

## Current Repo State

The backend is Render-ready. The frontend is a Vite React app in `frontend/` and is ready for Vercel import.

## GitHub

Push the repository to GitHub. The CI workflow runs on pushes and pull requests to `main`:

- `ruff` lint
- `mypy` type check
- `pytest` with coverage
- frontend lint
- frontend build

## Supabase

Run the SQL files in `backend/migrations/` against your Supabase project in order:

1. `backend/migrations/002_adapter_toggles.sql`
2. `backend/migrations/003_core_schema.sql`

Keep these values ready for Render:

- `SUPABASE_URL`
- `SUPABASE_KEY`
- `SUPABASE_SERVICE_KEY`

Use the service-role key only on Render. Do not expose it to Vercel or browser code.

## Render Backend

The repo includes `render.yaml` for a Render Blueprint.

1. Commit and push `render.yaml`.
2. Open Render's Blueprint flow.
3. Connect the GitHub repo.
4. Render will detect the backend service from `render.yaml`.
5. Fill the secret env vars marked `sync: false`.

Required Render env vars:

```text
PYTHON_VERSION=3.11.11
APP_ENV=production
LOG_LEVEL=INFO
CORS_ORIGINS=https://your-vercel-app.vercel.app
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=sb_publishable_your_publishable_key
SUPABASE_SERVICE_KEY=your-service-role-key
```

Optional adapter env vars:

```text
GITHUB_TOKEN=
STACKEXCHANGE_KEY=
APOLLO_API_KEY=
PROXYCURL_API_KEY=
INDEED_PUBLISHER_ID=
DICE_API_KEY=
MONSTER_API_KEY=
ZIPRECRUITER_API_KEY=
```

Backend health check:

```text
https://your-render-service.onrender.com/health
```

Expected response:

```json
{"status":"ok"}
```

## Vercel Frontend

Deploy the `frontend/` folder to Vercel.

Vercel settings:

```text
Framework Preset: Vite
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
Install Command: npm ci
```

Set the backend URL in Vercel using the frontend variable name used by the app. For Vite, use:

```text
VITE_API_BASE_URL=https://sourcing-backend-s6dr.onrender.com
```

Also update Render:

```text
CORS_ORIGINS=https://your-vercel-app.vercel.app
```

## End-to-End Smoke Test

1. Open the Vercel frontend.
2. Confirm the frontend calls `VITE_API_BASE_URL`.
3. Hit `GET /health` through the frontend or directly.
4. Create or fetch data through the backend.
5. Confirm the row exists in Supabase.

Backend-only smoke test:

```bash
curl https://sourcing-backend-s6dr.onrender.com/health
curl https://sourcing-backend-s6dr.onrender.com/api/adapters
```
