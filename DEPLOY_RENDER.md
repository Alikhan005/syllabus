# Render Deployment (Free)

## 1. Prerequisites

1. Project is pushed to GitHub.
2. You have a Render account linked with GitHub.
3. The deploy branch is `main`.

## 2. Deploy from `render.yaml`

1. Open `https://dashboard.render.com/blueprints`.
2. Click `New Blueprint Instance`.
3. Select your GitHub repo `Alikhan005/syllabus`.
4. Confirm branch `main`.
5. Confirm Blueprint file `render.yaml` from repo root.
6. Click `Apply`.

Render creates:
1. Web service `alikhan005-syllabus` (free)
2. PostgreSQL `alikhan005-syllabus-db` (free)

## 3. Moving to a new Render trial account

1. Keep GitHub repo the same: `Alikhan005/syllabus`.
2. Import the project as a new Blueprint in the new Render account.
3. This repository already pins Render to branch `main` and repo root, so the new account uses the correct path automatically.
4. The service/database/disk names are already changed to fresh names, so the new account does not collide with the old Render app.
5. Copy sensitive env vars from the old Render service if you use them:
   - `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`
   - `DEFAULT_FROM_EMAIL`, `SERVER_EMAIL`
   - `LLM_API_KEY`
6. Render will generate a fresh `DJANGO_SECRET_KEY` automatically from `render.yaml`.
7. The new database is empty. If you need old production data, export/import it separately before switching users to the new URL.

## 4. Important free-tier notes

1. Free web service sleeps on inactivity.
2. Free Render Postgres has storage/time limits (check current Render pricing).
3. Worker is launched inside the same web service process via `deploy/render-start.sh`.
4. HTTPS redirect stays enabled in production because Django trusts Render's `X-Forwarded-Proto` header.
5. For full AI-checks on uploaded files set `LLM_API_KEY` in Render environment variables. Without it the worker will fall back only to simplified checks and friendly error messages.

## 5. First check

After deploy is finished:

1. Open your Render app URL.
2. Check health endpoint: `/healthz/`
3. Login and run one AI check to verify worker processing.

## 6. If deploy fails

1. Open service `Logs`.
2. Verify DB migration errors and environment variables.
3. Re-deploy from latest commit.
