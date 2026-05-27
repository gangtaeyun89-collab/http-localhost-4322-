"""Walk-forward backtest endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.schemas import BacktestRequest, BacktestResult
from backend.app.services.backtest_service import run_walk_forward


router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.post("", response_model=BacktestResult)
def post_backtest(req: BacktestRequest) -> BacktestResult:
    """Run a walk-forward backtest on a single pair.

    Synchronous: a daily-bar walk-forward over ~1500 bars finishes in a
    second or two on the box that hosts the API. For larger histories or
    intraday bars we'd want a job queue + WebSocket progress channel, but
    that's overkill at the cadence this dashboard runs.
    """
    try:
        return run_walk_forward(req)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
