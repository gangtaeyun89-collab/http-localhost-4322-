"""Live-quote service.

Returns a small payload describing the current state of one cointegrated
pair -- last bar timestamp, last z-score, last spread, current correlation
-- so the frontend can poll it every few seconds and animate the
workbench in place. The full analytics payload is too heavy for that
cadence; this endpoint is the thing that *does* refresh fast.

Two data sources, in order of preference:

* IBKR live snapshot via ``quant_tool.data.ibkr.fetch_historical`` for the
  most recent bar. Used when ``STATARB_IBKR_ENABLED=1`` and IB Gateway is
  reachable. Falls back silently on any error.
* The cached CSV universe (or synthetic fallback). Always works; treats
  the last loaded bar as "now" so the page still animates during local
  development without a market data feed.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backend.app.services.analysis import (
    compute_basics,
    rolling_zscore,
)
from backend.app.services.data_source import load_universe


# Minimal in-process cache so a one-second poll cadence doesn't melt the
# discovery layer. Keyed by (base, quote, source); the TTL is per-source
# because IBKR moves on its own schedule but CSV is a no-op refresh.
@dataclass
class _CacheEntry:
    expires_at: float
    payload: dict


_CACHE: dict[tuple[str, str, str], _CacheEntry] = {}

_DEFAULT_TTL_CSV = 1.0  # CSV "live" is essentially free; refresh cheaply.
_DEFAULT_TTL_IBKR = 4.0  # Stay under IBKR pacing rules (~60 req/10min).


def _ibkr_enabled() -> bool:
    return os.environ.get("STATARB_IBKR_ENABLED", "0").lower() in {"1", "true", "yes"}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _safe(value: float | None, default: float = 0.0) -> float:
    if value is None or not math.isfinite(value):
        return default
    return float(value)


def _last_bar(prices: pd.DataFrame) -> dict:
    """Most recent (timestamp, base, quote) row for the header tape."""
    if len(prices) == 0:
        return {"t": _now_iso(), "base": 0.0, "quote": 0.0}
    ts = prices.index[-1]
    return {
        "t": ts.strftime("%Y-%m-%dT%H:%M:%S")
        if hasattr(ts, "strftime")
        else str(ts),
        "base": float(round(float(prices["base"].iloc[-1]), 4)),
        "quote": float(round(float(prices["quote"].iloc[-1]), 4)),
    }


def _compute_quote(base: str, quote: str, *, source: str) -> dict:
    """Run the (small) per-tick computation: latest z-score + spread."""
    universe = load_universe()
    basics = compute_basics(universe, base, quote)
    z = rolling_zscore(basics.spread)
    last_z = _safe(float(z.iloc[-1]) if len(z) else 0.0)
    last_spread = _safe(float(basics.spread.iloc[-1]) if len(basics.spread) else 0.0)

    # 1-bar return for each leg (just the latest move).
    last_ret = {"base": 0.0, "quote": 0.0}
    if len(basics.aligned) >= 2:
        prev = basics.aligned.iloc[-2]
        cur = basics.aligned.iloc[-1]
        last_ret = {
            "base": _safe(float(np.log(cur["base"] / prev["base"]))),
            "quote": _safe(float(np.log(cur["quote"] / prev["quote"]))),
        }

    # Trading-signal interpretation right next to the number, so the
    # frontend doesn't have to reproduce the rule.
    signal = "flat"
    if last_z > 2.0:
        signal = "short_spread"
    elif last_z < -2.0:
        signal = "long_spread"

    return {
        "base": basics.base,
        "quote": basics.quote,
        "asOf": _now_iso(),
        "lastBar": _last_bar(basics.aligned),
        "lastZScore": float(round(last_z, 4)),
        "lastSpread": float(round(last_spread, 4)),
        "lastReturn": last_ret,
        "halfLife": _safe(basics.half_life),
        "pvalue": _safe(basics.pvalue, 1.0),
        "signal": signal,
        "source": source,
    }


def _try_ibkr_refresh(base: str, quote: str) -> bool:
    """Attempt to pull a fresh daily bar for both legs from IBKR.

    Returns True on success. We're intentionally conservative here: any
    connection / pacing / contract error makes us fall back to CSV. The
    user sees the source badge change rather than an error.
    """
    if not _ibkr_enabled():
        return False
    try:
        from quant_tool.data import ibkr

        host = os.environ.get("STATARB_IBKR_HOST", "127.0.0.1")
        port = int(os.environ.get("STATARB_IBKR_PORT", "7497"))
        client_id = int(os.environ.get("STATARB_IBKR_CLIENT_ID", "21"))
        timeframe = os.environ.get("STATARB_IBKR_TIMEFRAME", "1d")
        # Keep the request small -- only the trailing few bars are needed
        # to "tick" the last observation on the chart.
        client = ibkr.connect(host=host, port=port, client_id=client_id, timeout=5)
        try:
            for sym in (base, quote):
                ibkr.fetch_historical(
                    client,
                    symbol=sym,
                    timeframe=timeframe,
                    start=None,  # one page
                    end=None,
                    what_to_show="TRADES",
                    use_rth=True,
                )
        finally:
            client.disconnect()
        return True
    except Exception:
        return False


def get_quote(base: str, quote: str, *, force_ibkr: bool = False) -> dict:
    """Cached front door for the /quote endpoint."""
    source = "ibkr" if (force_ibkr or _ibkr_enabled()) else "csv"
    key = (base, quote, source)
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and hit.expires_at > now:
        return hit.payload

    refreshed_from_ibkr = False
    if source == "ibkr":
        refreshed_from_ibkr = _try_ibkr_refresh(base, quote)
        if not refreshed_from_ibkr:
            source = "csv"
            key = (base, quote, source)
            hit = _CACHE.get(key)
            if hit and hit.expires_at > now:
                return hit.payload

    payload = _compute_quote(base, quote, source=source)
    ttl = _DEFAULT_TTL_IBKR if source == "ibkr" else _DEFAULT_TTL_CSV
    _CACHE[key] = _CacheEntry(expires_at=now + ttl, payload=payload)
    return payload
