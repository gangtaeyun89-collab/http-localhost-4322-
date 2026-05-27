"""Pair discovery and per-pair analytics endpoints."""

from __future__ import annotations

import itertools
import math
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from backend.app.config import settings
from backend.app.schemas import (
    Market,
    PairAnalysis,
    PairKPIs,
    PairListResponse,
    PairListRow,
    PairQuote,
)
from backend.app.services import analysis
from backend.app.services.data_source import load_universe, universe_source
from backend.app.services.quote_service import get_quote
from quant_tool.strategy.pair_finder import cointegration_test


router = APIRouter(prefix="/api/pairs", tags=["pairs"])


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


@lru_cache(maxsize=8)
def _screened_pairs(
    max_pvalue: float, min_half_life: float, max_half_life: float
) -> tuple[list[dict], int, int]:
    """Cointegration-screen every pair in the loaded universe.

    Cached because the screen is the expensive step (O(N^2) tests). The
    cache key is the parameter tuple, so repeated requests with the same
    filters reuse the result without recomputing.
    """
    universe = load_universe()
    symbols = list(universe.columns)
    rows: list[dict] = []
    n_tested = 0
    for a, b in itertools.combinations(symbols, 2):
        n_tested += 1
        try:
            r = cointegration_test(
                universe[a], universe[b], base_name=a, quote_name=b
            )
        except Exception:
            continue
        if not math.isfinite(r.pvalue) or r.pvalue > max_pvalue:
            continue
        if not math.isfinite(r.half_life) or not (
            min_half_life <= r.half_life <= max_half_life
        ):
            continue
        corr = float(universe[a].pct_change().corr(universe[b].pct_change()))
        rows.append(
            {
                "id": f"{a}-{b}",
                "base": a,
                "quote": b,
                "market": "equity",
                "industry": None,
                "cointPValue": float(r.pvalue),
                "halfLife": float(r.half_life),
                "oosSharpe": 0.0,  # filled in if walk-forward results exist
                "trainSharpe": 0.0,
                "corr": corr if math.isfinite(corr) else 0.0,
            }
        )
    rows.sort(key=lambda x: x["cointPValue"])
    return rows, n_tested, len(symbols)


@router.get("/list", response_model=PairListResponse)
def list_pairs(
    market: Market = "equity",
    max_pvalue: float | None = Query(None, ge=0.0, le=1.0),
    min_half_life: float | None = Query(None, gt=0.0),
    max_half_life: float | None = Query(None, gt=0.0),
    limit: int = Query(50, ge=1, le=500),
) -> PairListResponse:
    rows, n_tested, n_universe = _screened_pairs(
        max_pvalue if max_pvalue is not None else settings.max_pvalue,
        min_half_life if min_half_life is not None else settings.min_half_life,
        max_half_life if max_half_life is not None else settings.max_half_life,
    )
    return PairListResponse(
        rows=[PairListRow(**{**r, "market": market}) for r in rows[:limit]],
        n_tested=n_tested,
        n_universe=n_universe,
        source=universe_source(),
    )


# ---------------------------------------------------------------------------
# Per-pair analysis
# ---------------------------------------------------------------------------


def _parse_pair_id(pair_id: str) -> tuple[str, str]:
    if "-" not in pair_id:
        raise HTTPException(400, "pair id must look like 'BASE-QUOTE'")
    base, quote = pair_id.split("-", 1)
    return base.strip(), quote.strip()


@router.get("/{pair_id}/analysis", response_model=PairAnalysis)
def analyse_pair(pair_id: str, market: Market = "equity") -> PairAnalysis:
    base, quote = _parse_pair_id(pair_id)
    universe = load_universe()
    try:
        basics = analysis.compute_basics(universe, base, quote)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc

    kpis_dict = analysis.pair_summary_kpis(
        basics, market=market, asset_class=settings.asset_class
    )

    return PairAnalysis(
        kpis=PairKPIs(**kpis_dict),
        cumReturns=analysis.cumulative_returns_series(basics.aligned),
        zscore=analysis.zscore_series(basics.spread),
        correlation=analysis.correlation_series(
            basics.base_series, basics.quote_series
        ),
        scatter=analysis.copula_scatter(basics.base_series, basics.quote_series),
        vecm=analysis.vecm_rows(
            basics.base_series, basics.quote_series, basics.spread
        ),
        impulse=analysis.impulse_response(basics.half_life),
    )


@router.get("/{pair_id}/quote", response_model=PairQuote)
def quote_pair(pair_id: str, live: bool = False) -> PairQuote:
    """Lightweight tick endpoint -- safe to poll on a 1-5s cadence.

    ``live=true`` forces an IBKR refresh attempt even when the env flag is
    off; the service silently falls back to CSV when the gateway is
    unreachable so the page never blocks on an offline broker.
    """
    base, quote = _parse_pair_id(pair_id)
    try:
        payload = get_quote(base, quote, force_ibkr=live)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    return PairQuote(**payload)
