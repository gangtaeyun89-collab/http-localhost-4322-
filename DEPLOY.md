# Deploy to Railway

Two Railway services -- one FastAPI backend, one Next.js frontend --
sharing the same GitHub repo. Railway auto-detects on push, redeploys
on every commit.

## 1. Repository prep

CSV data lives in `market_data/industries/`. Three options for how
Railway sees it:

| Option | Setup | Freshness |
|--------|-------|-----------|
| **A. Commit CSVs** | Remove `market_data/` from `.gitignore`, commit, push | Whatever you last pushed |
| **B. Synthetic fallback** | Leave `.gitignore` alone; backend serves the built-in `generate_universe()` data | Demo / mock |
| **C. yfinance backend fetch** | Wire `quant_tool.data.yfinance` (not built yet) to populate the universe on startup | ~15 min delayed |

For the first deploy pick **B** (just to confirm the pipes work), then
upgrade to **A** once you trust the rest.

If you go with A: edit `.gitignore`, drop the `market_data/` line, then
`git add market_data/industries/*.csv && git commit -m "Bundle daily
CSVs" && git push`.

## 2. Railway project

1. Sign in at https://railway.com
2. **New Project** → **Deploy from GitHub repo** → pick this repo
3. Railway scans the repo. It'll likely guess Python; that's the
   backend. Continue with the autodetected service.

## 3. Backend service

* **Service name**: `backend` (or whatever)
* **Root Directory**: `/`
* **Build Command**: (let nixpacks default; reads `requirements.txt`
  and `backend/requirements.txt` if both are present)
* **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
  (already in the root `Procfile`; Railway picks it up automatically)
* **Environment variables**:
  * `STATARB_CSV_DIR=/app/market_data/industries` (default; only set if
    you mount the CSV elsewhere)
  * `STATARB_ASSET_CLASS=equity`
  * `STATARB_CORS=*` (or restrict to your frontend URL)
* **Generate Domain**: Settings → Networking → Generate Domain. Note
  the URL (e.g. `statarb-backend-production.up.railway.app`).

## 4. Frontend service

In the same Railway project: **New Service** → **GitHub Repo** → same
repo.

* **Service name**: `frontend`
* **Root Directory**: `/frontend` (important!)
* **Build Command**: `pnpm install --no-frozen-lockfile && pnpm build`
  (already in `frontend/railway.json`)
* **Start Command**: `pnpm start -- --hostname 0.0.0.0 --port $PORT`
* **Environment variables**:
  * `API_URL=https://statarb-backend-production.up.railway.app`
    (server-side fetch, no public exposure)
  * `NEXT_PUBLIC_API_URL=https://statarb-backend-production.up.railway.app`
    (browser-side `/api/*` rewrite target)
  * `NODE_ENV=production` (auto-set by Railway)
* **Generate Domain** → that's your live site URL.

## 5. CORS

Update the backend env var if you locked CORS down:

```
STATARB_CORS=https://statarb-frontend-production.up.railway.app,http://localhost:3000
```

(Comma-separated, no trailing slash.)

## 6. Verify

* `https://<backend-domain>/api/health` → JSON with `status: "ok"`,
  `csv_available: true|false` depending on which data option you picked.
* `https://<backend-domain>/api/pairs/list?limit=3` → 3 cointegrated
  pairs (or empty rows on synthetic if no CSV).
* `https://<frontend-domain>/equity/dashboard` → the sector grid.

## 7. Daily refresh

Railway has no built-in cron. Two options:

* **From your Mac**: run `./scripts/refresh_data.sh` daily, then `git
  add market_data && git commit && git push` -- Railway redeploys
  automatically.
* **Railway Cron** (paid Hobby plan): add a cron job that runs
  `python download_ibkr.py ...` -- but it can't reach IBKR Gateway on
  your Mac, so you'd need IB Gateway running somewhere reachable (your
  own VPS, or IBKR's hosted version).

For now the Mac-push flow is simpler and matches the existing
`scripts/refresh_data.sh` / `scripts/refresh_data.plist.example`
setup.

## 8. Costs (rough)

* Railway Hobby plan: **$5 free credit/month**, then $0.000231/min of
  service runtime.
* Two services running 24/7 ≈ $10-15/month after the free credit.
* Volumes (persisted disk) are extra (~$0.25/GB/month).

For Paper trading 24/7 the free credit covers about 15 days/month;
expect ~$10/month total once you run continuously.

## 9. Going to real money later

Railway is fine for the **dashboard + paper-paper journal**. The
real-money loop needs:

* IB Gateway 24/7 reachable from the backend (Railway can't ship
  IBKR's Java client easily -- separate VPS is cleaner).
* Order execution module (still TODO; see Phase 4 notes).

When that's ready, move backend + IB Gateway to AWS EC2 us-east-1
(closer to NYSE matching engines, IBKR co-lo available) and keep the
frontend on Railway/Vercel.
