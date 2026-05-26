"""Compute the per-pair analytics the frontend renders.

Every helper returns plain Python primitives (or pandas-derived rows that
serialise cleanly) so the routers just wrap them in Pydantic models. The
heavy lifting -- cointegration tests, OLS hedge, half-life estimation --
lives in ``quant_tool`` and is imported here rather than re-implemented.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_tool.data.features import align_prices, infer_bars_per_year
from quant_tool.strategy.pair_finder import cointegration_test


def _safe(value: float, default: float = 0.0) -> float:
    """Replace NaN/inf with ``default`` so the JSON serializer accepts it."""
    if value is None or not math.isfinite(value):
        return default
    return float(value)


def hurst_exponent(series: pd.Series, max_lag: int = 20) -> float:
    """Simple R/S Hurst estimator.

    H ~ 0.5 -> random walk, H > 0.5 -> trending, H < 0.5 -> mean-reverting.
    Stat-arb pairs we want are mean-reverting in the *spread*, not the legs,
    so this is mostly a sanity number on the spread itself.
    """
    s = series.dropna().values
    if len(s) < max_lag + 2:
        return float("nan")
    lags = range(2, max_lag + 1)
    tau = []
    for lag in lags:
        diff = s[lag:] - s[:-lag]
        if diff.std() == 0:
            return float("nan")
        tau.append(np.sqrt(diff.std()))
    poly = np.polyfit(np.log(list(lags)), np.log(tau), 1)
    return float(poly[0] * 2.0)


@dataclass
class PairBasics:
    base: str
    quote: str
    base_series: pd.Series
    quote_series: pd.Series
    aligned: pd.DataFrame  # base/quote columns
    pvalue: float
    statistic: float
    half_life: float
    hedge_ratio: float
    spread: pd.Series


def compute_basics(
    universe: pd.DataFrame, base: str, quote: str
) -> PairBasics:
    """Run the cointegration screen and derive the OLS spread for one pair."""
    if base not in universe.columns or quote not in universe.columns:
        raise KeyError(f"unknown ticker(s): {base}, {quote}")
    aligned = align_prices(universe[base], universe[quote])
    coint = cointegration_test(
        aligned["base"], aligned["quote"], base_name=base, quote_name=quote
    )
    # Static OLS hedge from log-prices for the spread series.
    log_b = np.log(aligned["base"])
    log_q = np.log(aligned["quote"])
    beta = float(np.cov(log_b, log_q, ddof=1)[0, 1] / np.var(log_q, ddof=1))
    spread = log_b - beta * log_q
    return PairBasics(
        base=base,
        quote=quote,
        base_series=aligned["base"],
        quote_series=aligned["quote"],
        aligned=aligned,
        pvalue=_safe(coint.pvalue, 1.0),
        statistic=_safe(coint.statistic),
        half_life=_safe(coint.half_life),
        hedge_ratio=beta,
        spread=spread,
    )


def rolling_zscore(spread: pd.Series, window: int = 60) -> pd.Series:
    mean = spread.rolling(window, min_periods=max(2, window // 4)).mean()
    std = spread.rolling(window, min_periods=max(2, window // 4)).std()
    return ((spread - mean) / std).fillna(0.0)


def rolling_corr(
    base: pd.Series, quote: pd.Series, window: int = 60
) -> pd.Series:
    return (
        np.log(base)
        .diff()
        .rolling(window, min_periods=max(2, window // 4))
        .corr(np.log(quote).diff())
        .fillna(0.0)
    )


def copula_scatter(
    base: pd.Series, quote: pd.Series, max_points: int = 1000
) -> list[dict]:
    """Empirical copula: rank-transform each leg's returns to [0,1]."""
    rb = np.log(base).diff().dropna()
    rq = np.log(quote).diff().dropna()
    common = rb.index.intersection(rq.index)
    if len(common) == 0:
        return []
    rb = rb.loc[common]
    rq = rq.loc[common]
    u = rb.rank(pct=True).values
    v = rq.rank(pct=True).values
    if len(u) > max_points:
        idx = np.linspace(0, len(u) - 1, max_points).astype(int)
        u, v = u[idx], v[idx]
    return [
        {"x": float(round(uu, 4)), "y": float(round(vv, 4))}
        for uu, vv in zip(u, v)
    ]


def _ts_label(ts) -> str:
    return ts.strftime("%Y-%m-%d") if hasattr(ts, "strftime") else str(ts)


def _downsample(df: pd.DataFrame, max_points: int) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step]


def cumulative_returns_series(
    aligned: pd.DataFrame, max_points: int = 600
) -> list[dict]:
    """Resample the price series down to ``max_points`` rows for the chart."""
    df = _downsample(aligned, max_points)
    # Use bracket access (df["base"]) rather than attribute access on the row
    # tuple -- the latter shadows pandas accessors like Series.corr.
    return [
        {
            "t": _ts_label(ts),
            "base": float(round(float(df.at[ts, "base"]), 4)),
            "quote": float(round(float(df.at[ts, "quote"]), 4)),
        }
        for ts in df.index
    ]


def zscore_series(
    spread: pd.Series, max_points: int = 600
) -> list[dict]:
    z = rolling_zscore(spread)
    df = _downsample(pd.DataFrame({"spread": spread, "zscore": z}), max_points)
    return [
        {
            "t": _ts_label(ts),
            "spread": float(round(float(df.at[ts, "spread"]), 4)),
            "zscore": float(round(float(df.at[ts, "zscore"]), 4)),
        }
        for ts in df.index
    ]


def correlation_series(
    base: pd.Series, quote: pd.Series, max_points: int = 600
) -> list[dict]:
    c = rolling_corr(base, quote)
    df = _downsample(pd.DataFrame({"corr": c}), max_points)
    return [
        {
            "t": _ts_label(ts),
            "corr": float(round(float(df.at[ts, "corr"]), 4)),
        }
        for ts in df.index
    ]


def vecm_rows(
    base: pd.Series, quote: pd.Series, spread: pd.Series
) -> list[dict]:
    """Best-effort VECM-style coefficient table.

    Full VECM estimation needs statsmodels' VECM class which is
    finicky on small samples; for the dashboard we approximate the same
    information with two OLS regressions of each return on lagged returns
    and the lagged spread. The economic interpretation -- "is the
    spread's reversion concentrated in the base leg or the quote leg?" --
    is the same and is what the screenshot also displays.
    """
    try:
        import statsmodels.api as sm
    except ImportError:
        return []

    db = np.log(base).diff()
    dq = np.log(quote).diff()
    spread_lag = spread.shift(1)

    def fit(dep: pd.Series) -> dict:
        X = pd.concat(
            {
                "db_lag1": db.shift(1),
                "db_lag2": db.shift(2),
                "dq_lag1": dq.shift(1),
                "dq_lag2": dq.shift(2),
                "spread_lag1": spread_lag,
            },
            axis=1,
        ).dropna()
        y = dep.loc[X.index]
        X = sm.add_constant(X)
        res = sm.OLS(y, X).fit()
        return {
            "coef": dict(res.params),
            "pvalue": dict(res.pvalues),
        }

    base_fit = fit(db)
    quote_fit = fit(dq)

    terms = [
        ("db lag1 (β₁)", "db_lag1"),
        ("db lag2 (β₂)", "db_lag2"),
        ("dq lag1 (β₁)", "dq_lag1"),
        ("dq lag2 (β₂)", "dq_lag2"),
        ("spread lag1 (γ)", "spread_lag1"),
    ]
    return [
        {
            "term": label,
            "baseCoef": _safe(base_fit["coef"].get(key, float("nan"))),
            "basePValue": _safe(base_fit["pvalue"].get(key, float("nan")), 1.0),
            "quoteCoef": _safe(quote_fit["coef"].get(key, float("nan"))),
            "quotePValue": _safe(quote_fit["pvalue"].get(key, float("nan")), 1.0),
        }
        for label, key in terms
    ]


def impulse_response(half_life: float) -> list[dict]:
    """OU-implied impulse decay: a unit shock at t-1 reverts at rate phi.

    ``phi = 0.5 ** (1 / half_life)`` so after one half-life the path is
    halved. The quote leg responds with the opposite sign (this is the
    point of a hedge); the magnitudes here are illustrative only -- a
    proper VECM impulse-response would compute them from the fitted
    coefficient matrix, but for the dashboard the OU envelope is what
    the user actually needs to interpret.
    """
    if not math.isfinite(half_life) or half_life <= 0:
        half_life = 30.0
    phi = 0.5 ** (1.0 / half_life)
    out = [{"step": -2, "base": 0.0, "quote": 0.0}]
    base_shock = -0.55
    quote_shock = -0.55
    out.append({"step": -1, "base": base_shock, "quote": quote_shock})
    for k in range(0, 10):
        # Base recovers faster (sign flips after t), quote recovers slowly.
        b = round(base_shock * (-(phi ** (k + 2))), 3)
        q = round(quote_shock * (phi ** (k + 1)), 3)
        out.append({"step": k, "base": b, "quote": q})
    return out


def pair_summary_kpis(
    basics: PairBasics, market: str, asset_class: str
) -> dict:
    """Top-of-page numbers: tests, sizing inputs, and a quick performance read."""
    aligned = basics.aligned
    bpy = infer_bars_per_year(aligned.index, asset_class=asset_class)
    timeframe = _timeframe_label(bpy)

    # Long-term beta on log returns (used as a sanity reference next to the
    # hedge ratio derived from levels).
    db = np.log(aligned["base"]).diff().dropna()
    dq = np.log(aligned["quote"]).diff().dropna()
    common = db.index.intersection(dq.index)
    db = db.loc[common]
    dq = dq.loc[common]
    if len(dq) > 1 and float(dq.var()) > 0:
        lt_beta = float(np.cov(db, dq, ddof=1)[0, 1] / dq.var())
    else:
        lt_beta = float("nan")

    corr = float(db.corr(dq)) if len(db) > 1 else float("nan")
    hurst = hurst_exponent(basics.spread)

    # Quick performance read: a long-only "spread mean-reversion" curve --
    # short the leg above its rolling mean, long the leg below. Returns
    # here are illustrative; the real backtest endpoint uses
    # quant_tool.backtest.run_backtest with realistic costs.
    z = rolling_zscore(basics.spread).fillna(0.0)
    position = (-np.sign(z).shift(1)).fillna(0.0)  # contrarian on the spread
    pair_ret = (db - basics.hedge_ratio * dq).reindex(position.index).fillna(0.0)
    pnl = position * pair_ret
    equity = (1.0 + pnl).cumprod()
    total_return = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0
    if len(pnl) > 1 and pnl.std() > 0:
        sharpe = float(pnl.mean() / pnl.std() * np.sqrt(bpy))
    else:
        sharpe = 0.0
    if len(equity):
        running_max = equity.cummax()
        drawdown = equity / running_max - 1.0
        mdd = float(drawdown.min())
    else:
        mdd = 0.0

    return {
        "base": basics.base,
        "quote": basics.quote,
        "cointJn": basics.pvalue < 0.10,  # placeholder until we wire Johansen
        "cointEG": basics.pvalue < 0.10,
        "hurst": _safe(hurst, 0.5),
        "halfLife": basics.half_life,
        "corr": _safe(corr),
        "hedgeRatio": basics.hedge_ratio,
        "ltBeta": _safe(lt_beta),
        "mdd": _safe(mdd),
        "returns": _safe(total_return),
        "sharpe": _safe(sharpe),
        "periods": len(aligned),
        "timeframe": timeframe,
        "market": market,
    }


def _timeframe_label(bpy: int) -> str:
    if bpy <= 12:
        return "Monthly"
    if bpy <= 52:
        return "Weekly"
    if bpy <= 260:
        return "Daily"
    if bpy <= 2000:
        return "Hourly"
    if bpy <= 100_000:
        return "Intraday"
    return f"~{bpy} bars/yr"
