"""FastAPI service exposing the quant_tool research stack to the web app.

The backend is a thin layer over the existing ``quant_tool`` package: each
endpoint maps to one workflow (pair list, pair analysis, discovery, backtest)
and the heavy lifting stays in the library where the tests already live.

Run locally with::

    uvicorn backend.app.main:app --reload --port 8000

The Next.js frontend proxies ``/api/*`` requests here through its
``rewrites()`` config, so a single browser origin works for both halves of
the stack in development.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import settings
from backend.app.routers import health, pairs, universes

app = FastAPI(
    title="Stat Arb API",
    description="Statistical-arbitrage research and execution backend.",
    version="0.1.0",
)

# Allow the dev frontend (next dev / next start) to call us directly. In
# production both halves sit behind the same domain so CORS is moot; the
# permissive default here is for local development only.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(universes.router)
app.include_router(pairs.router)
