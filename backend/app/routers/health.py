"""Liveness + data-source readiness probe."""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import settings
from backend.app.services.data_source import csv_available, list_tickers

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "csv_dir": str(settings.csv_dir),
        "csv_available": csv_available(),
        "ticker_count": len(list_tickers()),
        "asset_class": settings.asset_class,
    }
