"""Pydantic response models. Field names match the TypeScript types in
``frontend/lib/mock.ts`` exactly so the React components stay unchanged
when the data source flips from mock to real."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Market = Literal["equity", "crypto"]


class PairKPIs(BaseModel):
    base: str
    quote: str
    cointJn: bool
    cointEG: bool
    hurst: float
    halfLife: float
    corr: float
    hedgeRatio: float
    ltBeta: float
    mdd: float
    returns: float
    sharpe: float
    periods: int
    timeframe: str
    market: Market


class SeriesPoint(BaseModel):
    t: str
    base: float
    quote: float


class ZScorePoint(BaseModel):
    t: str
    spread: float
    zscore: float


class CorrPoint(BaseModel):
    t: str
    corr: float


class ScatterPoint(BaseModel):
    x: float
    y: float


class VECMRow(BaseModel):
    term: str
    baseCoef: float
    basePValue: float
    quoteCoef: float
    quotePValue: float


class ImpulsePoint(BaseModel):
    step: int
    base: float
    quote: float


class PairAnalysis(BaseModel):
    kpis: PairKPIs
    cumReturns: list[SeriesPoint]
    zscore: list[ZScorePoint]
    correlation: list[CorrPoint]
    scatter: list[ScatterPoint]
    vecm: list[VECMRow]
    impulse: list[ImpulsePoint]


class PairListRow(BaseModel):
    id: str
    base: str
    quote: str
    market: Market
    industry: str | None = None
    cointPValue: float
    halfLife: float
    oosSharpe: float
    trainSharpe: float
    corr: float


class PairListResponse(BaseModel):
    rows: list[PairListRow]
    n_tested: int
    n_universe: int
    source: str  # "csv" | "synthetic"


class QuoteBar(BaseModel):
    t: str
    base: float
    quote: float


class QuoteReturn(BaseModel):
    base: float
    quote: float


class PairQuote(BaseModel):
    """Lightweight per-pair tick payload for the polling endpoint."""

    base: str
    quote: str
    asOf: str
    lastBar: QuoteBar
    lastZScore: float
    lastSpread: float
    lastReturn: QuoteReturn
    halfLife: float
    pvalue: float
    signal: str  # "flat" | "long_spread" | "short_spread"
    source: str  # "csv" | "synthetic" | "error"


class PairQuoteBulk(BaseModel):
    quotes: list[PairQuote]
    asOf: str


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    """Inputs to /api/backtest. Matches what the React form posts."""

    base: str
    quote: str
    train_size: int = 800
    test_size: int = 200
    asset_class: Literal["equity", "crypto"] = "equity"
    target_volatility: float = 0.15
    tune_lookback: bool = True
    hedge_method: Literal["kalman", "ols"] = "kalman"
    entry_z: float = 2.0
    exit_z: float = 0.5


class WindowReport(BaseModel):
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    train_sharpe: float
    test_sharpe: float


class EquityPoint(BaseModel):
    t: str
    equity: float
    netReturn: float
    position: float


class BacktestStats(BaseModel):
    sharpe: float
    cagr: float
    maxDrawdown: float
    totalReturn: float
    annualVolatility: float
    winRate: float
    nTrades: int
    bars: int


class BacktestResult(BaseModel):
    request: BacktestRequest
    stats: BacktestStats
    equity: list[EquityPoint]
    windows: list[WindowReport]
    meanTrainSharpe: float
    meanTestSharpe: float
    overfitGap: float  # train - test; positive + large = likely overfit
    halfLife: float
    pvalue: float
    lookbackUsed: int
    barsPerYear: int
    source: str  # "csv" | "synthetic"


class UniverseInfo(BaseModel):
    name: str
    label: str
    tickers: list[str]


class UniversesResponse(BaseModel):
    universes: list[UniverseInfo]
    csv_dir: str
    csv_available: bool
    csv_tickers: list[str]
