"""Live-quote service.

Returns a small payload describing the current state of one cointegrated
pair -- last bar timestamp, last z-score, last spread, current correlation
-- so the frontend can poll it every few seconds and animate the
workbench in place. The full analytics payload is too heavy for that
cadence; this endpoint is the thing that *does* refresh fast.

The single source of truth is the CSV universe loaded by
:mod:`backend.app.services.data_source`. Refresh it externally (the
``scripts/refresh_data.sh`` wrapper around ``download_ibkr.py`` is the
recommended cadence: once daily after the US close). Doing the IBKR fetch
inline here would mean ~10 minutes of latency per cold quote -- the wrong
shape for a polling endpoint.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from backend.app.services.analysis import (
    compute_basics,
    rolling_zscore,
)
from backend.app.services.data_source import load_universe, universe_source


# Minimal in-process cache so a one-second poll cadence doesn't melt the
# discovery layer on every tick.
@dataclass
class _CacheEntry:
    expires_at: float
    payload: dict


_CACHE: dict[tuple[str, str], _CacheEntry] = {}
_TTL_SECONDS = 1.0


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


def _compute_quote(base: str, quote: str) -> dict:
    """Run the (small) per-tick computation: latest z-score + spread."""
    universe = load_universe()
    basics = compute_basics(universe, base, quote)
    z = rolling_zscore(basics.spread)
    last_z = _safe(float(z.iloc[-1]) if len(z) else 0.0)
    last_spread = _safe(
        float(basics.spread.iloc[-1]) if len(basics.spread) else 0.0
    )

    last_ret = {"base": 0.0, "quote": 0.0}
    if len(basics.aligned) >= 2:
        prev = basics.aligned.iloc[-2]
        cur = basics.aligned.iloc[-1]
        last_ret = {
            "base": _safe(float(np.log(cur["base"] / prev["base"]))),
            "quote": _safe(float(np.log(cur["quote"] / prev["quote"]))),
        }

    # Trading-signal interpretation lives next to the number so callers
    # don't have to reproduce the rule.
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
        "hedgeRatio": _safe(basics.hedge_ratio, 1.0),
        "signal": signal,
        "source": universe_source(),  # "csv" or "synthetic"
    }


def get_quote(base: str, quote: str) -> dict:
    """Cached front door for the /quote endpoint."""
    key = (base, quote)
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and hit.expires_at > now:
        return hit.payload
    payload = _compute_quote(base, quote)
    _CACHE[key] = _CacheEntry(expires_at=now + _TTL_SECONDS, payload=payload)
    return payload


def get_quotes(pairs: list[tuple[str, str]]) -> list[dict]:
    """Bulk variant used by the dashboard. Errors on individual pairs are
    surfaced as ``None`` rather than aborting the whole request."""
    out: list[dict] = []
    for base, quote in pairs:
        try:
            out.append(get_quote(base, quote))
        except Exception as exc:  # noqa: BLE001
            out.append(
                {
                    "base": base,
                    "quote": quote,
                    "asOf": _now_iso(),
                    "lastBar": {"t": _now_iso(), "base": 0.0, "quote": 0.0},
                    "lastZScore": 0.0,
                    "lastSpread": 0.0,
                    "lastReturn": {"base": 0.0, "quote": 0.0},
                    "halfLife": 0.0,
                    "pvalue": 1.0,
                    "hedgeRatio": 1.0,
                    "signal": "flat",
                    "source": "error",
                    "error": str(exc),
                }
            )
    return out
