# Deploying Finance Quest

Backend: Railway (Docker, Postgres, Bucket). Frontend: Vercel. CI: `.github/workflows/deploy.yml`
deploys both on every push to `main` once the secrets below exist. Until then the deploy jobs
skip with a notice and CI stays green.

## What the container does
`backend/Dockerfile` runs as a non-root user and starts `backend/start.sh`, which:
1. `alembic upgrade head`
2. `python -m financequest refpack approve financequest/fixtures/reference/fq-av-001` (idempotent:
   an existing approved scenario is reused)
3. `uvicorn ... --host 0.0.0.0 --port $PORT --proxy-headers`

Railway healthchecks `/healthz` (`backend/railway.json`). Note `/healthz` answers 200 even when
the DB is down; check the JSON (`db`, `playable_count`) before the demo.

## One-time setup

### 1. Railway
1. railway.com -> New Project -> Empty Project. A paid plan is needed (see Costs).
2. Add **PostgreSQL** (New -> Database -> PostgreSQL).
3. Add a **Bucket** (New -> Bucket). Region: same as the API.
4. New -> GitHub Repo -> this repo; service name `api`. Settings -> Source -> Root Directory
   `backend` (the Dockerfile and `railway.json` are picked up from there).
5. API service -> Variables (use references to the plugins where shown):

| Variable | Value |
|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (code rewrites `postgresql://` to `postgresql+psycopg://`) |
| `ANTHROPIC_API_KEY` | your key |
| `GOOGLE_GENAI_API_KEY` | your key |
| `MODEL_ID` | `claude-opus-5-5` |
| `FAKE_LLM` | `false` |
| `DEMO_MODE` | `true` for the stage demo, else `false` |
| `CORS_ORIGINS` | `https://<prod-domain>.vercel.app,https://*.vercel.app` (add `http://localhost:5173` for local) |
| `DATA_DIR` | `data` (ephemeral scratch; durable files go to the bucket) |
| `STORAGE_BUCKET` | `${{Bucket.BUCKET}}` |
| `STORAGE_ENDPOINT` | `${{Bucket.ENDPOINT}}` |
| `STORAGE_ACCESS_KEY_ID` | `${{Bucket.ACCESS_KEY_ID}}` |
| `STORAGE_SECRET_ACCESS_KEY` | `${{Bucket.SECRET_ACCESS_KEY}}` |
| `STORAGE_REGION` | `${{Bucket.REGION}}` |

   The bucket variable names above are Railway's defaults; check the bucket's Variables tab
   and adjust the references if they differ. Optionally set `GUESSERS_PER_ATTEMPT`,
   `MAX_ATTEMPTS` etc. from `.env.example`.
6. Settings -> Networking -> Generate Domain. This is the API URL (`https://<x>.up.railway.app`).
7. Project token: Project Settings -> Tokens -> create for the `production` environment. This is
   `RAILWAY_TOKEN`.

### 2. Vercel
1. vercel.com -> Add New Project -> import this repo. **Root Directory: `frontend`**, framework
   Vite (build `npm run build`, output `dist`). `frontend/vercel.json` provides the SPA rewrite.
2. Environment Variables (Production and Preview):
   - `VITE_API_MODE=live`
   - `VITE_API_BASE_URL=https://<x>.up.railway.app` (no trailing slash)
   Never put secrets in `VITE_*` variables; they are public in the bundle.
3. Disable Git auto-deploys if CI should be the only deployer: Settings -> Git -> Ignored Build
   Step, or disconnect the repo after the first import (previews then come from you running
   `vercel deploy`). Otherwise Vercel's own GitHub integration also deploys.
4. Token: vercel.com/account/tokens -> create `VERCEL_TOKEN`.
5. IDs: in `frontend/` (or repo root) run `vercel link`; then read
   `.vercel/project.json` for `orgId` (`VERCEL_ORG_ID`) and `projectId` (`VERCEL_PROJECT_ID`).
   Do not commit `.vercel/`.
6. Put the final production domain into Railway `CORS_ORIGINS`.

### 3. GitHub secrets
```sh
gh secret set RAILWAY_TOKEN
gh secret set VERCEL_TOKEN
gh secret set VERCEL_ORG_ID
gh secret set VERCEL_PROJECT_ID
# only if the Railway service is not called "api":
gh variable set RAILWAY_SERVICE --body <service-name>
```
Then push to `main` or run Actions -> deploy -> Run workflow.

## CORS
`CORS_ORIGINS` is comma separated. Entries containing `*` are turned into a regex
(`*` -> `[A-Za-z0-9-]+`) in `Settings.cors_origin_regex`, so `https://*.vercel.app` is supported.
It matches one host label, which covers Vercel preview URLs like `fq-git-branch-team.vercel.app`.

## Stage readiness
- After deploy: `curl https://<api>/healthz` -> `"db": true`, `"playable_count": >= 1`.
- Warm up by opening the app and starting one quest shortly before the demo (Railway services do
  not sleep on paid plans, but caches and connection pools are cold after a deploy).
- Set `DEMO_MODE=true` for the demo; `FAKE_LLM=false` for real models.

## Costs and plan notes (verify on railway.com/pricing, they change)
- Railway Hobby (about 5 USD/month including 5 USD of usage) is the realistic minimum: the free
  trial has limited resources and no volumes/buckets guarantee. Usage (CPU, RAM, Postgres storage,
  bucket storage/egress) is billed beyond the included credit; a small API plus Postgres usually
  stays within a few USD per month.
- Vercel Hobby is free for non-commercial use; a team/commercial project needs Pro.
- LLM calls (Anthropic, Google) are the dominant cost; set spending limits on those keys.
