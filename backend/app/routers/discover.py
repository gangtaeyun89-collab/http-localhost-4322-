"""Pair discovery endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import (
    DiscoverBasketRef,
    DiscoveredPair,
    DiscoverRequest,
    DiscoverResult,
)
from backend.app.services.discover_service import known_basket_ids, run_discovery


router = APIRouter(prefix="/api/discover", tags=["discover"])


@router.post("", response_model=DiscoverResult)
def post_discover(req: DiscoverRequest) -> DiscoverResult:
    """Run the full discovery pipeline on the union of selected baskets.

    Validates basket ids up front so a typo blocks the request rather
    than silently producing an empty result.
    """
    known = known_basket_ids()
    bad = [b for b in req.baskets if b not in known]
    if bad:
        raise HTTPException(400, f"unknown basket id(s): {bad}")
    if not req.baskets:
        raise HTTPException(400, "select at least one basket")
    if not (0.0 < req.fdr_level <= 1.0):
        raise HTTPException(400, "fdr_level must be in (0, 1]")
    if req.min_half_life <= 0 or req.max_half_life <= req.min_half_life:
        raise HTTPException(400, "require 0 < min_half_life < max_half_life")

    data = run_discovery(
        baskets=req.baskets,
        fdr_level=req.fdr_level,
        distance_threshold=req.distance_threshold,
        min_half_life=req.min_half_life,
        max_half_life=req.max_half_life,
    )
    return DiscoverResult(
        pairs=[DiscoveredPair(**p) for p in data["pairs"]],
        n_clusters=data["n_clusters"],
        n_tested=data["n_tested"],
        n_universe=data["n_universe"],
        source=data["source"],
        baskets=[DiscoverBasketRef(**b) for b in data["baskets"]],
    )
