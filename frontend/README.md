# Sourcing Frontend

Vite + React console for the sourcing backend.

## Local Development

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Default backend:

```text
VITE_API_BASE_URL=https://sourcing-backend-s6dr.onrender.com
```

## Vercel

Use these settings:

```text
Framework Preset: Vite
Root Directory: frontend
Build Command: npm run build
Output Directory: dist
Install Command: npm ci
```
