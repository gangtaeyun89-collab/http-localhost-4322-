"""Tests for CSV/Parquet candle ingestion."""

import numpy as np
import pandas as pd
import pytest

from quant_tool.backtest.engine import run_backtest
from quant_tool.config.settings import BacktestConfig, PairConfig
from quant_tool.data.ingestion import (
    generate_cointegrated_pair,
    load_ohlcv,
    load_pair,
)


def test_load_ohlcv_parses_iso_timestamps(tmp_path):
    path = tmp_path / "candles.csv"
    idx = pd.date_range("2024-01-01", periods=50, freq="h", tz="UTC")
    pd.DataFrame(
        {
            "timestamp": idx,
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": np.arange(50.0),
            "volume": 10.0,
        }
    ).to_csv(path, index=False)

    df = load_ohlcv(path)
    assert isinstance(df.index, pd.DatetimeIndex)
    assert str(df.index.tz) == "UTC"
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df["close"].iloc[-1] == 49.0
    assert df.index.is_monotonic_increasing


def test_load_ohlcv_parses_epoch_millis(tmp_path):
    path = tmp_path / "epoch.csv"
    base_ms = 1_704_067_200_000  # 2024-01-01T00:00:00Z in milliseconds
    ts = [base_ms + i * 3_600_000 for i in range(30)]
    pd.DataFrame({"timestamp": ts, "close": np.arange(30.0)}).to_csv(path, index=False)

    df = load_ohlcv(path)
    assert df.index[0].year == 2024
    assert len(df) == 30


def test_load_ohlcv_deduplicates_timestamps(tmp_path):
    path = tmp_path / "dupes.csv"
    pd.DataFrame(
        {
            "timestamp": [
                "2024-01-01T00:00Z",
                "2024-01-01T00:00Z",
                "2024-01-01T01:00Z",
            ],
            "close": [1.0, 2.0, 3.0],
        }
    ).to_csv(path, index=False)

    df = load_ohlcv(path)
    assert len(df) == 2
    assert df["close"].iloc[0] == 2.0  # the duplicate keeps the last value


def test_load_ohlcv_rejects_missing_close(tmp_path):
    path = tmp_path / "noclose.csv"
    pd.DataFrame({"timestamp": [1, 2], "price": [1.0, 2.0]}).to_csv(path, index=False)
    with pytest.raises(ValueError):
        load_ohlcv(path)


def test_load_ohlcv_rejects_unknown_extension(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("{}")
    with pytest.raises(ValueError):
        load_ohlcv(path)


def test_load_ohlcv_reads_parquet(tmp_path):
    """Parquet round-trip: the timestamp arrives as a named index, not a column."""
    pytest.importorskip("pyarrow")
    idx = pd.date_range("2024-01-01", periods=40, freq="h", tz="UTC")
    frame = pd.DataFrame({"close": np.arange(40.0)}, index=idx)
    frame.index.name = "timestamp"
    path = tmp_path / "candles.parquet"
    frame.to_parquet(path)

    df = load_ohlcv(path)
    assert list(df.columns) == ["close"]
    assert len(df) == 40
    assert str(df.index.tz) == "UTC"


def test_load_pair_round_trip_feeds_the_backtest(tmp_path):
    """Synthetic pair -> CSV files -> load_pair -> run_backtest, end to end."""
    prices = generate_cointegrated_pair(n=1200, seed=33)
    base_path = tmp_path / "base.csv"
    quote_path = tmp_path / "quote.csv"
    pd.DataFrame(
        {"timestamp": prices.index, "close": prices["base"].to_numpy()}
    ).to_csv(base_path, index=False)
    pd.DataFrame(
        {"timestamp": prices.index, "close": prices["quote"].to_numpy()}
    ).to_csv(quote_path, index=False)

    loaded = load_pair(base_path, quote_path)
    assert list(loaded.columns) == ["base", "quote"]
    assert len(loaded) == len(prices)
    np.testing.assert_allclose(
        loaded["base"].to_numpy(), prices["base"].to_numpy(), rtol=1e-6
    )

    result = run_backtest(
        loaded, BacktestConfig(pair=PairConfig("ETH", "BTC"), hedge_method="kalman")
    )
    assert result.stats["bars"] == len(loaded)
