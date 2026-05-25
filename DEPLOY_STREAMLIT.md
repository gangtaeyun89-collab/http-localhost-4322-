# Deploy the dashboard to Streamlit Community Cloud

The dashboard at `quant_tool/polymarket/dashboard/app.py` can run as a free
public web app on Streamlit Community Cloud. The **Wallet** page (live
on-chain reads from Polygon) works fully; the **Live monitor** page does
not (Streamlit Cloud has no place to run the persistent bot process).

## One-time setup

1. Push the latest of this branch to GitHub. The dashboard expects the repo
   layout we already have — no changes needed.

2. Sign up at <https://streamlit.io/cloud> with your GitHub account. The
   free tier covers one private app or unlimited public apps.

3. In Streamlit Cloud, click **Create app**:

   | Field | Value |
   |---|---|
   | Repository | `gangtaeyun89-collab/http-localhost-4322-` |
   | Branch | `claude/quirky-lamport-M8RDU` (or `main` after merge) |
   | Main file path | `quant_tool/polymarket/dashboard/app.py` |
   | App URL | pick any subdomain, e.g. `polymarket-bot` |

4. Click **Advanced settings → Secrets**, paste the contents of
   `.streamlit/secrets.toml.example` (filling in your real values).

5. Click **Deploy**. First build takes 2–3 minutes (it installs everything
   from `requirements.txt`).

You'll get a URL like `https://polymarket-bot.streamlit.app`. Open it from
any device — your phone, another laptop, anywhere.

## Notes & limits

- **Auto-deploy on push.** Streamlit Cloud watches the configured branch.
  Pushing a new commit rebuilds the app in ~1 minute.
- **No background processes.** `scripts/polymarket_live.py` cannot run on
  Streamlit Cloud. Run it on your own laptop or a paid host (Fly.io,
  Railway, DigitalOcean), then point the dashboard at the SQLite file
  somewhere it can read (out of scope for the free tier).
- **Memory.** Streamlit Cloud free tier has ~1 GB RAM. Captures over ~50 MB
  can OOM during replay; trim with smaller `--markets` / `--duration` or
  use the **Backtest sweep** page sparingly.
- **Network policy.** Both Polygon RPC and Polymarket's data-api are
  reachable from Streamlit Cloud's IPs by default.

## Updating

Just push to the branch:

```bash
git push origin claude/quirky-lamport-M8RDU
```

Streamlit Cloud picks it up automatically.
