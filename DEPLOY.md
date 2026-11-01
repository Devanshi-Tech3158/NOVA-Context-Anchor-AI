# Deploying Content Anchor (backend on Render, frontend on Vercel)

## Why not Vercel for the backend?
v0.2 starts background job workers, keeps SQLite files on disk, and in production mode needs
encryption keys plus a heavy embedding model. Vercel functions are short-lived with no persistent
disk, so use a long-running host (Render/Railway/Fly) for the API and Vercel only for the static frontend.

## Step 0: push the right code
Your GitHub repo has the old v0.1.0 code. Unzip your Phases 9-10 zip, then copy the files from this
`deploy-fix` folder over it (same paths), then:

    git add -A && git commit -m "v0.2.0 + deployment config" && git push

Files in this folder and where they go:
- `nova/api/main.py`  -> replaces `nova/api/main.py` (only change: adds a `/` route)
- `render.yaml`       -> repo root
- `frontend/vercel.json` -> `frontend/vercel.json`

## Step 1: backend on Render
1. render.com > New > Blueprint > pick your repo (it reads `render.yaml`).
2. Wait for the deploy, then open `https://<your-service>.onrender.com/healthz` -> `{"status":"ok"}`
   and `/docs` for the Swagger UI.
3. Free plan sleeps after inactivity (first request takes ~30-60 s) and its disk resets on redeploy.

## Step 2: frontend on Vercel
1. Edit `frontend/vercel.json`: replace both `REPLACE-WITH-YOUR-RENDER-URL.onrender.com` with your real Render host.
2. Vercel > New Project > import the repo > **Root Directory = `frontend`**.
   (If your current Vercel project points at the repo root, delete it or change its Root Directory.)
3. Deploy. The build uses `npx vite build` (skips `check:assets`, which needs Python on Vercel).
   If you want the full `npm run build`, set it as the build command only if Python is available.

## Security note
In demo mode (`NOVA_ENV=development`, no API key) the API has NO authentication. Anyone with the URL can
call it. Fine for a demo, not for real data. For anything real, switch to the production block in
`.env.render.example`.

## Quick checks
- `/healthz` ok, `/readyz` ok, `/docs` loads on the Render URL
- Frontend loads on the Vercel URL and its calls to `/api/...` reach the backend
