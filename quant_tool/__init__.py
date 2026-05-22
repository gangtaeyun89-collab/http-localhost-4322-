"""AI-assisted crypto statistical-arbitrage and hedging toolkit.

The package is split into independent layers that communicate through plain
pandas/numpy objects so any single layer can be swapped or tested in isolation:

    data        market data ingestion and feature computation
    strategy    pair selection, spread construction and signal generation
    ai          dynamic models (Kalman hedge ratio) used by the strategy layer
    risk        position sizing and exposure limits
    execution   trading cost modelling
    backtest    vectorised, look-ahead-free backtest engine and metrics
    monitoring  structured logging

The backtest engine consumes the exact same strategy code that a live runner
would, so research results stay consistent with production behaviour.
"""

__version__ = "0.1.0"
