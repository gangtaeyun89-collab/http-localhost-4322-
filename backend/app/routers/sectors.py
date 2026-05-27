"""Sector-grouped pair scoreboard endpoints.

Two views the dashboard needs:

* GET /api/sectors -- one card per industry basket with the top-3
  cointegrated pairs in each, used for the home grid.
* GET /api/sectors/{id} -- every pair in a single basket plus the ticker
  list, used for the per-sector detail page.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.schemas import (
    SectorDetail,
    SectorPair,
    SectorSummary,
    SectorsResponse,
)
from backend.app.services.sectors_service import (
    get_sector_detail,
    get_sectors_summary,
)


router = APIRouter(prefix="/api/sectors", tags=["sectors"])


@router.get("", response_model=SectorsResponse)
def list_sectors(
    max_pvalue: float = Query(0.20, ge=0.0, le=1.0),
    min_half_life: float = Query(5.0, gt=0.0),
    max_half_life: float = Query(200.0, gt=0.0),
) -> SectorsResponse:
    data = get_sectors_summary(max_pvalue, min_half_life, max_half_life)
    return SectorsResponse(
        sectors=[
            SectorSummary(
                id=s["id"],
                label=s["label"],
                tickerCount=s["tickerCount"],
                tickerCountTotal=s["tickerCountTotal"],
                pairCount=s["pairCount"],
                topPairs=[SectorPair(**p) for p in s["topPairs"]],
            )
            for s in data["sectors"]
        ],
        source=data["source"],
    )


@router.get("/{sector_id}", response_model=SectorDetail)
def sector_detail(
    sector_id: str,
    max_pvalue: float = Query(0.20, ge=0.0, le=1.0),
    min_half_life: float = Query(5.0, gt=0.0),
    max_half_life: float = Query(200.0, gt=0.0),
) -> SectorDetail:
    data = get_sector_detail(sector_id, max_pvalue, min_half_life, max_half_life)
    if data is None:
        raise HTTPException(404, f"unknown sector {sector_id!r}")
    return SectorDetail(
        id=data["id"],
        label=data["label"],
        tickers=data["tickers"],
        tickerCount=data["tickerCount"],
        tickerCountTotal=data["tickerCountTotal"],
        pairCount=data["pairCount"],
        pairs=[SectorPair(**p) for p in data["pairs"]],
        source=data["source"],
    )
