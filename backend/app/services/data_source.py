"""Price-data access for the API.

Reads the configured CSV directory when populated; falls back to the
synthetic universe so the frontend still works on a fresh checkout that
has not downloaded any market data yet. The fallback also keeps the test
suite hermetic on CI where IBKR access is unavailable.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from backend.app.config import settings
from quant_tool.data.ingestion import generate_universe, load_universe_from_dir


def csv_available() -> bool:
    """True when the configured CSV directory has at least two ticker files."""
    p = Path(settings.csv_dir)
    return p.is_dir() and len(list(p.glob("*.csv"))) >= 2


@lru_cache(maxsize=1)
def load_universe() -> pd.DataFrame:
    """Cached universe loader.

    The cache invalidates on process restart only -- fine for the current
    workflow where universes are refreshed by re-running ``download_ibkr.py``
    and then bouncing the API. If we add a "rebuild universe" endpoint we'll
    need to expose ``load_universe.cache_clear()`` on it.
    """
    if csv_available():
        return load_universe_from_dir(settings.csv_dir)
    # Synthetic fallback so the frontend always has something to render.
    return generate_universe(
        n_clusters=3,
        assets_per_cluster=4,
        n_noise_assets=3,
        n=1605,
    )


def universe_source() -> str:
    return "csv" if csv_available() else "synthetic"


def list_tickers() -> list[str]:
    if not csv_available():
        return []
    return sorted(p.stem for p in Path(settings.csv_dir).glob("*.csv"))
