"""Runtime configuration for the FastAPI service.

Settings come from environment variables (prefixed ``STATARB_``) so the same
binary runs on a laptop with local CSVs and a cloud server pointed at a
mounted volume or live IBKR feed. Pydantic Settings handles parsing.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings:
    """Lightweight settings holder; replace with pydantic-settings if needed."""

    # Where the per-ticker OHLCV CSVs live. Falls back to the synthetic
    # universe generator if the directory is missing or empty, so the API
    # still serves data on a fresh checkout.
    csv_dir: Path = Path(
        os.environ.get("STATARB_CSV_DIR", REPO_ROOT / "market_data" / "industries")
    )

    # Annualisation hint. "equity" -> 252 sessions/year US calendar; "crypto"
    # -> 24/7 calendar. Inferred per-request from the data when None.
    asset_class: str = os.environ.get("STATARB_ASSET_CLASS", "equity")

    # Cointegration screen knobs for the list endpoint.
    max_pvalue: float = float(os.environ.get("STATARB_MAX_PVALUE", "0.10"))
    min_half_life: float = float(os.environ.get("STATARB_MIN_HALF_LIFE", "5"))
    max_half_life: float = float(os.environ.get("STATARB_MAX_HALF_LIFE", "200"))

    # CORS allowlist for the Next.js dev server. Override with a
    # comma-separated env value in production (or set to ["*"] for now).
    cors_origins: list[str] = (
        os.environ.get(
            "STATARB_CORS",
            "http://localhost:3000,http://localhost:4322,http://127.0.0.1:3000",
        ).split(",")
    )


settings = Settings()
