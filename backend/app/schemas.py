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


class UniverseInfo(BaseModel):
    name: str
    label: str
    tickers: list[str]


class UniversesResponse(BaseModel):
    universes: list[UniverseInfo]
    csv_dir: str
    csv_available: bool
    csv_tickers: list[str]
