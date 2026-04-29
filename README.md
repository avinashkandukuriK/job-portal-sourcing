# Sourcing — US Candidate Sourcing Web App

A pluggable candidate-sourcing tool. Paste a job description, get a ranked list of candidates pulled from multiple US-focused portals.

## Stack

- **Backend:** Python 3.11+, FastAPI, httpx, Playwright (for scraping)
- **Frontend:** React 18 + Vite + Tailwind CSS
- **Database:** Supabase (Postgres + REST)
- **Architecture:** Pluggable `SourceAdapter` interface — each portal is its own adapter

## What works out of the box (free / public APIs)

| Portal | Status | Notes |
|---|---|---|
| GitHub | ✅ Implemented | Public REST API, 5K req/hr authenticated |
| Stack Overflow | ✅ Implemented | Stack Exchange API |
| Wellfound (AngelList) | ✅ Implemented | Playwright scraper, public profiles |

## Stubbed (drop in API keys to enable)

| Portal | Status | Required |
|---|---|---|
| LinkedIn | 🔌 Stubbed | Proxycurl or Apollo API key |
| Apollo (LinkedIn + cross-source) | 🔌 Stubbed | Apollo API key |
| Indeed Resume | 🔌 Stubbed | Indeed Employer subscription |
| Dice | 🔌 Stubbed | Dice TalentSearch seat |
| Monster | 🔌 Stubbed | Monster Resume DB seat |
| ZipRecruiter | 🔌 Stubbed | ZipRecruiter Employer subscription |

## Quick start

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
playwright install chromium     # for Wellfound scraper
copy .env.example .env          # then edit with your keys
uvicorn app.main:app --reload   # http://localhost:8000

# 2. Frontend (in a separate terminal)
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## Configuration

Edit `backend/.env`:

```
# Required
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_KEY=eyJ...
GITHUB_TOKEN=ghp_...            # bumps rate limit from 60 to 5000/hr

# Optional — enables corresponding adapter
APOLLO_API_KEY=
PROXYCURL_API_KEY=
INDEED_PUBLISHER_ID=
DICE_API_KEY=
MONSTER_API_KEY=
ZIPRECRUITER_API_KEY=
```

## Honest scope

This MVP is **strongest for tech / engineering / design / data** roles, where
free public profiles (GitHub, Stack Overflow, Wellfound) carry rich signal.
For sales, marketing, finance, ops, etc., you'll need a paid aggregator
(Apollo recommended). The architecture is built to let you add those later
with a ~50-line adapter.

## Project layout

```
Sourcing/
├── backend/
│   ├── app/
│   │   ├── adapters/      # one file per portal
│   │   ├── core/          # parser, scorer, orchestrator
│   │   ├── db/            # Supabase client + repo
│   │   ├── models/        # Pydantic schemas
│   │   ├── api/           # FastAPI routes
│   │   ├── config.py
│   │   └── main.py
│   ├── migrations/
│   └── requirements.txt
└── frontend/
    └── src/
```
