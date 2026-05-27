"""Market data ingestion.

Three sources are supported, all producing the same shape -- a DataFrame
indexed by UTC timestamp -- so they are interchangeable downstream:

* :func:`fetch_ohlcv` pulls real candles from any ``ccxt``-supported exchange.
  ``ccxt`` is an optional dependency; the import is deferred so the rest of the
  toolkit (and the offline demo) runs without it.
* :func:`load_ohlcv` / :func:`load_pair` read candles you have exported to a
  CSV or Parquet file -- the way to validate on real data when outbound
  network access is unavailable.
* :func:`generate_cointegrated_pair` synthesises a genuinely cointegrated price
  pair. It lets the backtest, tests and demo run fully offline and gives a
  controlled ground truth (known hedge ratio) to validate the engine against.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from quant_tool.data.features import align_prices


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


def _to_utc_index(values: pd.Series) -> pd.DatetimeIndex:
    """Parse a timestamp column to a tz-aware UTC DatetimeIndex.

    Accepts ISO-8601 strings or epoch integers; the epoch unit (s/ms/us/ns) is
    inferred from the values' magnitude.
    """
    if pd.api.types.is_numeric_dtype(values):
        scale = float(values.dropna().abs().median())
        if scale >= 1e17:
            unit = "ns"
        elif scale >= 1e14:
            unit = "us"
        elif scale >= 1e11:
            unit = "ms"
        else:
            unit = "s"
        return pd.to_datetime(values, unit=unit, utc=True)
    return pd.to_datetime(values, utc=True)


def load_ohlcv(path: str | Path, timestamp_col: str = "timestamp") -> pd.DataFrame:
    """Load OHLCV candles you have exported to a CSV or Parquet file.

    The file must contain a timestamp and at least a ``close`` column;
    ``open/high/low/volume`` are carried through when present. Column names are
    matched case-insensitively. The timestamp may also be the file's index
    (common in Parquet exports). The output mirrors :func:`fetch_ohlcv` -- a
    DataFrame indexed by UTC timestamp -- so exported and live candles are
    interchangeable everywhere else.

    Parquet support relies on whatever Parquet engine pandas finds (e.g.
    ``pyarrow``); install one if you use ``.parquet`` files.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(path)
    elif suffix in {".csv", ".txt"}:
        df = pd.read_csv(path)
    else:
        raise ValueError(f"unsupported file type {suffix!r}; use .csv or .parquet")

    ts = timestamp_col.lower()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if ts not in df.columns:
        # The timestamp may be the index (e.g. a Parquet round-trip); surface
        # it as a column so the rest of the function is uniform.
        df = df.reset_index()
        df.columns = [str(c).strip().lower() for c in df.columns]
    if ts not in df.columns:
        raise ValueError(
            f"{path} has no '{timestamp_col}' column; found {list(df.columns)}"
        )
    if "close" not in df.columns:
        raise ValueError(f"{path} has no 'close' column; found {list(df.columns)}")

    df = df.set_index(_to_utc_index(df[ts]))
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].astype(float).sort_index()
    return df[~df.index.duplicated(keep="last")]


def load_pair(
    base_path: str | Path,
    quote_path: str | Path,
    timestamp_col: str = "timestamp",
) -> pd.DataFrame:
    """Load two exported OHLCV files and align them into a base/quote frame.

    Returns a DataFrame with ``base`` and ``quote`` close-price columns on the
    shared timestamp index -- exactly the input shape :func:`run_backtest`
    expects. Bars missing from either file are dropped by the alignment.
    """
    base = load_ohlcv(base_path, timestamp_col)["close"]
    quote = load_ohlcv(quote_path, timestamp_col)["close"]
    return align_prices(base, quote)


def load_universe_from_dir(
    directory: str | Path,
    pattern: str = "*.csv",
    timestamp_col: str = "timestamp",
    min_bars: int = 0,
) -> pd.DataFrame:
    """Load every OHLCV file in ``directory`` into a universe price frame.

    Each file becomes one column of close prices, named after the file stem
    (so ``XLF.csv`` -> column ``XLF``). The columns are inner-joined on the
    shared timestamp index so every asset has a price at every retained
    timestamp -- the shape :func:`quant_tool.strategy.discovery.discover_pairs`
    expects.

    ``min_bars`` drops files shorter than the threshold *before* alignment, so
    one short series does not throw away history for the rest of the universe.
    """
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a directory")

    series: dict[str, pd.Series] = {}
    for path in sorted(directory.glob(pattern)):
        df = load_ohlcv(path, timestamp_col=timestamp_col)
        if len(df) < min_bars:
            continue
        series[path.stem] = df["close"]

    if not series:
        raise ValueError(
            f"no OHLCV files matching {pattern!r} found in {directory}"
        )

    return pd.concat(series, axis=1).dropna()


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


def generate_universe(
    n_clusters: int = 3,
    assets_per_cluster: int = 4,
    n_noise_assets: int = 3,
    n: int = 2500,
    cluster_trend_vol: float = 0.020,
    idio_halflife: float = 30.0,
    idio_vol: float = 0.008,
    start_price: float = 100.0,
    seed: int | None = 42,
) -> pd.DataFrame:
    """Synthesise a universe of assets with embedded cointegrated clusters.

    Each cluster shares one common stochastic trend; an asset's log price is
    that trend (scaled by an asset-specific loading) plus a stationary
    Ornstein-Uhlenbeck idiosyncratic term. So *every pair within a cluster is
    cointegrated* -- the common trend cancels in the right linear combination
    -- while assets in different clusters, and the extra pure-random-walk noise
    assets, are not.

    Columns are named ``c{cluster}_a{asset}`` (and ``noise_{k}``) so callers
    and tests can recover the ground-truth structure. This is the controlled
    input for the pair-discovery pipeline.
    """
    if min(n_clusters, assets_per_cluster) < 1:
        raise ValueError("n_clusters and assets_per_cluster must be >= 1")
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-01", periods=n, freq="h", tz="UTC")
    phi = 0.5 ** (1.0 / idio_halflife)  # OU decay of the idiosyncratic term

    def _ou() -> np.ndarray:
        path = np.zeros(n)
        shocks = rng.normal(0.0, idio_vol, size=n)
        for t in range(1, n):
            path[t] = phi * path[t - 1] + shocks[t]
        return path

    columns: dict[str, np.ndarray] = {}
    for c in range(n_clusters):
        trend = np.cumsum(rng.normal(0.0, cluster_trend_vol, size=n))
        for a in range(assets_per_cluster):
            loading = rng.uniform(0.7, 1.3)
            level = np.log(start_price) + rng.uniform(-0.3, 0.3)
            columns[f"c{c}_a{a}"] = np.exp(level + loading * trend + _ou())

    for k in range(n_noise_assets):
        walk = np.cumsum(rng.normal(0.0, cluster_trend_vol, size=n))
        level = np.log(start_price) + rng.uniform(-0.3, 0.3)
        columns[f"noise_{k}"] = np.exp(level + walk)

    return pd.DataFrame(columns, index=index)
