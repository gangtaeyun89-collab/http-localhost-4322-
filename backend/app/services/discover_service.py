"""On-demand pair discovery service.

Thin wrapper over ``quant_tool.strategy.discovery.discover_pairs`` that
takes the union of selected industry baskets as the universe and returns
the FDR-surviving pairs in a JSON-friendly shape.

The expensive step (cointegration test on every within-cluster pair) is
synchronous because a typical request runs over ~10-15 tickers per
basket and finishes in well under a second on real-world data; if we
ever scale to "all 195 tickers, FDR 0.01" we'll want a background job
with a progress channel.
"""

from __future__ import annotations

import math

from backend.app.services.data_source import load_universe, universe_source
from backend.app.services.sectors_service import SECTOR_DEFS
from quant_tool.strategy.discovery import discover_pairs


def _basket_tickers(basket_id: str) -> tuple[str, ...]:
    for sid, _, tickers in SECTOR_DEFS:
        if sid == basket_id:
            return tickers
    return ()


def run_discovery(
    baskets: list[str],
    fdr_level: float = 0.10,
    distance_threshold: float = 0.7,
    min_half_life: float = 5.0,
    max_half_life: float = 200.0,
) -> dict:
    """Run discover_pairs on the union of the selected industry baskets."""
    universe = load_universe()

    # Resolve requested baskets to the tickers that are actually loaded.
    # Unknown basket ids are silently dropped -- the API surface above
    # validates ids before reaching us.
    requested: list[str] = []
    label_by_id: dict[str, str] = {}
    for basket_id in baskets:
        for sid, label, tickers in SECTOR_DEFS:
            if sid != basket_id:
                continue
            label_by_id[basket_id] = label
            for t in tickers:
                if t in universe.columns and t not in requested:
                    requested.append(t)

    if len(requested) < 2:
        return {
            "pairs": [],
            "n_clusters": 0,
            "n_tested": 0,
            "n_universe": len(requested),
            "source": universe_source(),
            "baskets": [
                {"id": b, "label": label_by_id.get(b, b)} for b in baskets
            ],
        }

    sub = universe[requested]
    result = discover_pairs(
        sub,
        distance_threshold=distance_threshold,
        fdr_level=fdr_level,
        max_half_life=max_half_life,
    )

    # Map each surviving pair to the basket it most likely belongs to --
    # the first basket in the request whose ticker tuple contains the
    # *base* leg. Lets the UI group survivors back by sector.
    def _basket_for(symbol: str) -> str | None:
        for basket_id in baskets:
            if symbol in _basket_tickers(basket_id):
                return basket_id
        return None

    pairs = []
    for r in result.pairs:
        if not math.isfinite(r.half_life):
            continue
        if r.half_life < min_half_life or r.half_life > max_half_life:
            continue
        basket_id = _basket_for(r.base) or _basket_for(r.quote)
        corr = float(sub[r.base].pct_change().corr(sub[r.quote].pct_change()))
        pairs.append(
            {
                "id": f"{r.base}-{r.quote}",
                "base": r.base,
                "quote": r.quote,
                "cointPValue": float(r.pvalue),
                "adfStatistic": float(r.statistic),
                "halfLife": float(r.half_life),
                "corr": corr if math.isfinite(corr) else 0.0,
                "basket": basket_id,
                "basketLabel": label_by_id.get(basket_id or "", basket_id or ""),
            }
        )

    return {
        "pairs": pairs,
        "n_clusters": result.n_clusters,
        "n_tested": result.n_tested,
        "n_universe": len(requested),
        "source": universe_source(),
        "baskets": [
            {"id": b, "label": label_by_id.get(b, b)} for b in baskets
        ],
    }


def known_basket_ids() -> set[str]:
    return {sid for sid, _, _ in SECTOR_DEFS}
