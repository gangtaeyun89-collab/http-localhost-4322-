# Deploy the bot + dashboard to Fly.io (24/7 always-on)

Streamlit Community Cloud can host the dashboard but not the trading bot
itself. This guide deploys both pieces to **Fly.io**, where the bot keeps
running even when no one has the page open. You get one URL like
`https://polymarket-bot.fly.dev` that shows the live dashboard and is
backed by a continuously running bot writing fills to a persistent SQLite
volume.

## Cost

Fly.io gives every account ~$5 of monthly credit. The smallest machine
(1 shared CPU, 512 MB RAM) costs ~$1.94/month plus ~$0.15/month for a 1 GB
volume — well inside the free credit. **Practical cost: $0/month** unless
you upgrade specs.

You do need to add a credit card to your Fly.io account to deploy
(spam-prevention), but you won't be charged unless you exceed the credit.

## One-time setup (10 minutes)

### 1. Install the Fly CLI

macOS:
```bash
brew install flyctl
```
Or via the universal installer:
```bash
curl -L https://fly.io/install.sh | sh
```

### 2. Sign up and log in

```bash
fly auth signup    # opens browser, links to your GitHub
fly auth login     # if you already have an account
```
Add a card at <https://fly.io/dashboard/personal/billing> when prompted.

### 3. Launch the app

From the repo root:

```bash
fly launch --no-deploy --copy-config
```

- It'll detect `fly.toml` and ask if you want to use the existing config — **yes**.
- It'll pick the app name from `fly.toml` (`polymarket-bot`); pick a different one if it's already taken.
- It'll offer to create a Postgres / Redis cluster — **no** for both.

### 4. Create the persistent volume

```bash
fly volumes create polymarket_data --size 1 --region iad
```

(1 GB is plenty; SQLite usage is in the MBs.)

### 5. Set the secrets

```bash
fly secrets set \
    POLYMARKET_WALLET_ADDRESS="0xAc5c1D6657eef3F0EC2b44b5Ab2d5eDF39caf3F9" \
    POLYMARKET_PROXY_ADDRESS="0xa8Fd04Ad1A2FF5a57D850A5bE6Fce5D28848C52f" \
    POLYGON_RPC_URL="https://polygon-rpc.com" \
    POLYMARKET_CLOB_URL="https://clob.polymarket.com" \
    POLYMARKET_GAMMA_URL="https://gamma-api.polymarket.com" \
    POLYMARKET_DATA_API_URL="https://data-api.polymarket.com"
```

### 6. Deploy

```bash
fly deploy
```

First deploy takes ~3 minutes (Docker build, image push, machine start).
Subsequent deploys are ~60 seconds.

### 7. Open it

```bash
fly open
```

Or go to `https://<your-app-name>.fly.dev`. The dashboard loads and the
bot is already running.

## Day-to-day operations

| What | Command |
|---|---|
| View live bot logs | `fly logs` |
| Check the bot's status | `fly status` |
| Push a new code version | `git push` (no Fly auto-deploy) and `fly deploy` |
| Restart the bot + dashboard | `fly apps restart polymarket-bot` |
| Adjust bot config | `fly secrets set BOT_INTERVAL_SECONDS=30` then `fly deploy` |
| Open a shell inside the running container | `fly ssh console` |
| Inspect the SQLite DB | `fly ssh console -C "sqlite3 /data/polymarket.sqlite '.tables'"` |
| Stop spending money entirely | `fly apps destroy polymarket-bot` |

## Tunable env vars (set with `fly secrets set NAME=value`)

| Var | Default | What it does |
|---|---|---|
| `BOT_INTERVAL_SECONDS` | 60 | Seconds between strategy cycles |
| `BOT_MARKETS` | 30 | How many markets the bot trades each cycle |
| `BOT_BANKROLL` | 10000 | Paper-trading bankroll in USDC |
| `BOT_MAX_PER_MARKET` | 0.02 | 2% max position per market |
| `BOT_MAX_TOTAL` | 0.50 | 50% max total exposure |

## What's still missing for **live** (real-money) trading

This setup runs the bot in **paper mode**. To go live (after you're in the
US on July 14):

1. Build the live ClobBroker (`quant_tool/polymarket/execution/clob_broker.py`).
2. Add Polymarket CLOB API credentials as Fly secrets:
   `POLYMARKET_CLOB_API_KEY`, `POLYMARKET_CLOB_API_SECRET`,
   `POLYMARKET_CLOB_API_PASSPHRASE`.
3. **Signing of orders should stay local-only** — never put your wallet
   private key in Fly secrets. The CLOB API key/secret derived from a
   signed message are OK (they only grant order-placement permissions,
   not key-recovery), but plan that key rotation with care.

Tell me when you're ready and I'll add the ClobBroker.
