"""Market data ingestion.

Two sources are supported:

* :func:`fetch_ohlcv` pulls real candles from any ``ccxt``-supported exchange.
  ``ccxt`` is an optional dependency; the import is deferred so the rest of the
  toolkit (and the offline demo) runs without it.
* :func:`generate_cointegrated_pair` synthesises a genuinely cointegrated price
  pair. It lets the backtest, tests and demo run fully offline and gives a
  controlled ground truth (known hedge ratio) to validate the engine against.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    limit: int = 1000,
    exchange: str = "binance",
) -> pd.DataFrame:
    """Fetch OHLCV candles for ``symbol`` from ``exchange`` via ccxt.

    Returns a DataFrame indexed by UTC timestamp with columns
    ``open, high, low, close, volume``.
    """
    try:
        import ccxt
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "fetch_ohlcv requires the optional 'ccxt' dependency: pip install ccxt"
        ) from exc

    client = getattr(ccxt, exchange)()
    raw = client.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(
        raw, columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.set_index("timestamp").sort_index()


def generate_cointegrated_pair(
    n: int = 2000,
    beta: float = 0.8,
    alpha: float = 1.5,
    spread_halflife: float = 30.0,
    spread_vol: float = 0.015,
    trend_vol: float = 0.012,
    start_price: float = 100.0,
    beta_drift_vol: float = 0.0,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Synthesise two cointegrated log-price series.

    The quote leg follows a random walk. The base leg is tied to it through a
    mean-reverting (Ornstein-Uhlenbeck) spread::

        log(base) = alpha + beta_t * log(quote) + spread_t

    so ``beta_t`` is the true hedge ratio the strategy should recover.

    ``beta_drift_vol`` lets the hedge ratio wander as a random walk starting
    from ``beta`` (0 keeps it constant). A drifting ratio is realistic for
    crypto and is the regime where an adaptive Kalman hedge beats static OLS.

    Returns a DataFrame of price levels with columns ``base`` and ``quote``.
    """
    if spread_halflife <= 0:
        raise ValueError("spread_halflife must be positive")
    if beta_drift_vol < 0:
        raise ValueError("beta_drift_vol must be non-negative")
    rng = np.random.default_rng(seed)

    quote_logret = rng.normal(0.0, trend_vol, size=n)
    log_quote = np.log(start_price) + np.cumsum(quote_logret)

    if beta_drift_vol > 0:
        beta_path = beta + np.cumsum(rng.normal(0.0, beta_drift_vol, size=n))
        beta_path = beta_path - beta_path[0] + beta  # anchor the start at beta
    else:
        beta_path = np.full(n, beta)

    # OU mean reversion: phi derived from the requested half-life.
    phi = 0.5 ** (1.0 / spread_halflife)
    spread = np.empty(n)
    spread[0] = 0.0
    shocks = rng.normal(0.0, spread_vol, size=n)
    for t in range(1, n):
        spread[t] = phi * spread[t - 1] + shocks[t]

    log_base = alpha + beta_path * log_quote + spread

    index = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"base": np.exp(log_base), "quote": np.exp(log_quote)}, index=index
    )
