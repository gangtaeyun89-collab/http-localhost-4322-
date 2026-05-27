"""Sector-grouped pair scoreboard.

The flat /api/pairs/list is the right shape for a watch table but the
wrong shape for the "where is the action right now?" question -- one
50-row table doesn't tell you that all five live signals are in
apartment REITs. This service groups the cointegration screen by
homogeneous industry basket (the same ones the discovery layer already
uses) and ranks each basket's top three pairs.

Cached behind a small parameter tuple: the screen is O(N^2) per basket
but the baskets are small (~10 tickers each), so the whole sweep is
cheap once and free afterwards.
"""

from __future__ import annotations

import itertools
import math
from functools import lru_cache

from backend.app.services.data_source import load_universe, universe_source
from quant_tool.data import universes as univ
from quant_tool.strategy.pair_finder import cointegration_test


# Stable (id, Korean label, ticker tuple) triples. Order is how the
# dashboard renders cards row-by-row. Keep the same order as the universes
# router so users see a familiar layout.
SECTOR_DEFS: list[tuple[str, str, tuple[str, ...]]] = [
    ("sp500_banks_large", "대형 은행 / Large Banks", univ.SP500_BANKS_LARGE),
    ("sp500_investment_banks", "투자은행 / Investment Banks", univ.SP500_INVESTMENT_BANKS),
    ("sp500_insurance_pc", "손해보험 / P&C Insurance", univ.SP500_INSURANCE_PC),
    ("sp500_semiconductors", "반도체 / Semiconductors", univ.SP500_SEMICONDUCTORS),
    ("sp500_software", "소프트웨어 / Software", univ.SP500_SOFTWARE),
    ("sp500_big_pharma", "대형 제약 / Big Pharma", univ.SP500_BIG_PHARMA),
    ("sp500_health_insurance", "건강보험 / Managed Care", univ.SP500_HEALTH_INSURANCE),
    ("sp500_oil_majors", "통합 정유사 / Oil Majors", univ.SP500_OIL_MAJORS),
    ("sp500_oil_services", "유전 서비스 / Oil Services", univ.SP500_OIL_SERVICES),
    ("sp500_refiners", "정제사 / Refiners", univ.SP500_REFINERS),
    ("sp500_railroads", "철도 / Railroads", univ.SP500_RAILROADS),
    ("sp500_airlines", "항공사 / Airlines", univ.SP500_AIRLINES),
    ("sp500_logistics", "물류 / Logistics", univ.SP500_LOGISTICS),
    ("sp500_bigbox_retail", "대형마트 / Big-Box Retail", univ.SP500_BIGBOX_RETAIL),
    ("sp500_home_improvement", "홈 인테리어 / Home Improvement", univ.SP500_HOME_IMPROVEMENT),
    ("sp500_restaurants", "외식 / QSR", univ.SP500_RESTAURANTS),
    ("sp500_beverages", "음료 / Beverages", univ.SP500_BEVERAGES),
    ("sp500_household_staples", "생필품 / Household Staples", univ.SP500_HOUSEHOLD_STAPLES),
    ("sp500_payments", "결제 / Payments", univ.SP500_PAYMENTS),
    ("sp500_telecom", "통신 / Telecom", univ.SP500_TELECOM),
    ("sp500_utilities_electric", "전력유틸리티 / Electric Utilities", univ.SP500_UTILITIES_ELECTRIC),
    ("sp500_reits", "리츠 / REITs", univ.SP500_REITS),
    ("sp500_aerospace_defense", "항공우주·방산 / A&D", univ.SP500_AEROSPACE_DEFENSE),
    ("sp500_machinery", "기계 / Machinery", univ.SP500_MACHINERY),
    ("sp500_automakers", "자동차 / Automakers", univ.SP500_AUTOMAKERS),
    ("sp500_gold_miners", "금광주 / Gold Miners", univ.SP500_GOLD_MINERS),
]


def _label(sector_id: str) -> str | None:
    for sid, label, _ in SECTOR_DEFS:
        if sid == sector_id:
            return label
    return None


def _tickers(sector_id: str) -> tuple[str, ...] | None:
    for sid, _, tickers in SECTOR_DEFS:
        if sid == sector_id:
            return tickers
    return None


def _screen_sector(
    sector_id: str,
    label: str,
    tickers: tuple[str, ...],
    max_pvalue: float,
    min_half_life: float,
    max_half_life: float,
) -> dict:
    """Cointegration-screen every pair inside one industry basket."""
    universe = load_universe()
    available = [t for t in tickers if t in universe.columns]
    pairs: list[dict] = []
    if len(available) >= 2:
        for a, b in itertools.combinations(available, 2):
            try:
                r = cointegration_test(
                    universe[a], universe[b], base_name=a, quote_name=b
                )
            except Exception:
                continue
            if not math.isfinite(r.pvalue) or r.pvalue > max_pvalue:
                continue
            if not math.isfinite(r.half_life):
                continue
            if not (min_half_life <= r.half_life <= max_half_life):
                continue
            corr = float(
                universe[a].pct_change().corr(universe[b].pct_change())
            )
            pairs.append(
                {
                    "id": f"{a}-{b}",
                    "base": a,
                    "quote": b,
                    "cointPValue": float(r.pvalue),
                    "halfLife": float(r.half_life),
                    "corr": corr if math.isfinite(corr) else 0.0,
                }
            )
    pairs.sort(key=lambda x: x["cointPValue"])
    return {
        "id": sector_id,
        "label": label,
        "tickers": list(available),
        "tickerCount": len(available),
        "tickerCountTotal": len(tickers),
        "pairCount": len(pairs),
        "topPairs": pairs[:3],
        "allPairs": pairs,
    }


@lru_cache(maxsize=16)
def screen_all_sectors(
    max_pvalue: float = 0.20,
    min_half_life: float = 5.0,
    max_half_life: float = 200.0,
) -> list[dict]:
    """All sectors, ordered as SECTOR_DEFS."""
    out: list[dict] = []
    for sector_id, label, tickers in SECTOR_DEFS:
        out.append(
            _screen_sector(
                sector_id, label, tickers,
                max_pvalue, min_half_life, max_half_life,
            )
        )
    return out


def get_sectors_summary(
    max_pvalue: float = 0.20,
    min_half_life: float = 5.0,
    max_half_life: float = 200.0,
) -> dict:
    """List view: every sector with its top-3 pairs and counts."""
    sectors = screen_all_sectors(max_pvalue, min_half_life, max_half_life)
    return {
        "sectors": [
            {
                "id": s["id"],
                "label": s["label"],
                "tickerCount": s["tickerCount"],
                "tickerCountTotal": s["tickerCountTotal"],
                "pairCount": s["pairCount"],
                "topPairs": s["topPairs"],
            }
            for s in sectors
        ],
        "source": universe_source(),
    }


def get_sector_detail(
    sector_id: str,
    max_pvalue: float = 0.20,
    min_half_life: float = 5.0,
    max_half_life: float = 200.0,
) -> dict | None:
    label = _label(sector_id)
    if label is None:
        return None
    tickers = _tickers(sector_id) or ()
    sectors = screen_all_sectors(max_pvalue, min_half_life, max_half_life)
    for s in sectors:
        if s["id"] == sector_id:
            return {
                "id": s["id"],
                "label": s["label"],
                "tickers": s["tickers"],
                "tickerCount": s["tickerCount"],
                "tickerCountTotal": s["tickerCountTotal"],
                "pairCount": s["pairCount"],
                "pairs": s["allPairs"],
                "source": universe_source(),
            }
    # Sector exists but had zero qualifying pairs at this filter level.
    return {
        "id": sector_id,
        "label": label,
        "tickers": list(tickers),
        "tickerCount": len(tickers),
        "tickerCountTotal": len(tickers),
        "pairCount": 0,
        "pairs": [],
        "source": universe_source(),
    }
