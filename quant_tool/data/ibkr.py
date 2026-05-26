"""Interactive Brokers (IBKR) market data adapter.

Produces the same DataFrame shape as :mod:`quant_tool.data.ingestion` -- a
UTC-indexed OHLCV frame -- so candles fetched from IBKR drop straight into the
strategy and backtest layers without any further plumbing.

The IBKR API is reached through ``ib_insync`` over a running TWS or IB
Gateway. Both are optional dependencies; the import is deferred so the rest of
the toolkit (and the offline tests) still runs without them.

Two access points:

* :func:`fetch_historical` -- paginated historical bars (the workhorse for
  backtest data and pair screening).
* :func:`stream_live_bars` -- a real-time bar subscription, yielding bars as
  they close. Use it from the live signal loop.

IBKR's historical API has two quirks worth knowing about:

* It paces requests (roughly 60 per 10 minutes). :func:`fetch_historical`
  inserts a small sleep between pages.
* ``durationStr`` and ``barSizeSetting`` come from a fixed vocabulary. We map
  a friendly ``timeframe`` string to ``barSizeSetting`` and pick a per-request
  ``durationStr`` based on the bar size.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pandas as pd

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PAPER_PORT = 7497
DEFAULT_LIVE_PORT = 7496

# Map a friendly timeframe string to IBKR's barSizeSetting vocabulary.
_BAR_SIZE = {
    "1s": "1 secs",
    "5s": "5 secs",
    "15s": "15 secs",
    "30s": "30 secs",
    "1m": "1 min",
    "2m": "2 mins",
    "3m": "3 mins",
    "5m": "5 mins",
    "15m": "15 mins",
    "30m": "30 mins",
    "1h": "1 hour",
    "2h": "2 hours",
    "4h": "4 hours",
    "1d": "1 day",
    "1w": "1 week",
}

# How much history to ask for in a single page, per bar size. IBKR rejects
# requests that pull "too much" relative to the bar resolution; these values
# are conservative defaults that work in practice.
_PAGE_DURATION = {
    "1s": "1800 S",
    "5s": "3600 S",
    "15s": "14400 S",
    "30s": "28800 S",
    "1m": "1 D",
    "2m": "2 D",
    "3m": "3 D",
    "5m": "5 D",
    "15m": "10 D",
    "30m": "20 D",
    "1h": "30 D",
    "2h": "60 D",
    "4h": "90 D",
    "1d": "1 Y",
    "1w": "5 Y",
}


def _import_ib_insync():
    try:
        import ib_insync  # noqa: F401
    except ImportError as exc:
        raise ImportError(
            "IBKR support requires the optional 'ib_insync' dependency: "
            "pip install ib_insync"
        ) from exc
    return ib_insync


def connect(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PAPER_PORT,
    client_id: int = 1,
    timeout: float = 10.0,
):
    """Open a connection to a running TWS or IB Gateway.

    ``port`` defaults to 7497 (Paper Trading); use 7496 for live. ``client_id``
    must be unique per concurrent connection -- pick a different value if you
    open several scripts against the same gateway.
    """
    ib_insync = _import_ib_insync()
    ib = ib_insync.IB()
    ib.connect(host, port, clientId=client_id, timeout=timeout)
    return ib


def make_stock_contract(symbol: str, exchange: str = "SMART", currency: str = "USD"):
    """Build (and qualify) a US stock/ETF contract.

    SMART routing is the right default for US equities and ETFs; IBKR picks
    the best venue at order time.
    """
    ib_insync = _import_ib_insync()
    return ib_insync.Stock(symbol, exchange, currency)


def _bars_to_frame(bars) -> pd.DataFrame:
    """Convert an ``ib_insync`` BarDataList to our standard OHLCV frame."""
    if not bars:
        return pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            index=pd.DatetimeIndex([], tz="UTC", name="timestamp"),
        )
    rows = []
    for bar in bars:
        ts = bar.date
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        else:
            # date-only bars (daily/weekly): treat as UTC midnight
            ts = datetime(ts.year, ts.month, ts.day, tzinfo=timezone.utc)
        rows.append(
            {
                "timestamp": ts,
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "volume": float(bar.volume) if bar.volume is not None else 0.0,
            }
        )
    df = pd.DataFrame(rows).set_index("timestamp").sort_index()
    return df[~df.index.duplicated(keep="last")]


def fetch_historical(
    ib,
    symbol: str,
    timeframe: str = "1d",
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    what_to_show: str = "TRADES",
    use_rth: bool = True,
    page_pause: float = 1.0,
    exchange: str = "SMART",
    currency: str = "USD",
) -> pd.DataFrame:
    """Fetch historical OHLCV from IBKR, paging back from ``end`` to ``start``.

    ``timeframe`` is one of the keys of :data:`_BAR_SIZE` (e.g. ``"1d"``,
    ``"1h"``, ``"5m"``). ``start`` and ``end`` accept ISO date strings or
    ``datetime`` objects; ``end=None`` means "now" and ``start=None`` means
    "as far back as one page goes".

    ``what_to_show`` follows IBKR's vocabulary -- ``TRADES``, ``MIDPOINT``,
    ``BID``, ``ASK``, ``ADJUSTED_LAST`` for split/dividend-adjusted closes.

    ``use_rth=True`` restricts to Regular Trading Hours; flip to ``False`` to
    include pre/post-market.
    """
    if timeframe not in _BAR_SIZE:
        raise ValueError(
            f"unsupported timeframe {timeframe!r}; choose from {sorted(_BAR_SIZE)}"
        )

    contract = make_stock_contract(symbol, exchange=exchange, currency=currency)
    ib.qualifyContracts(contract)

    end_dt = _coerce_dt(end) if end is not None else datetime.now(tz=timezone.utc)
    start_dt = _coerce_dt(start) if start is not None else None

    bar_size = _BAR_SIZE[timeframe]
    page_duration = _PAGE_DURATION[timeframe]

    frames: list[pd.DataFrame] = []
    cursor = end_dt
    while True:
        bars = ib.reqHistoricalData(
            contract,
            endDateTime=cursor.strftime("%Y%m%d-%H:%M:%S"),
            durationStr=page_duration,
            barSizeSetting=bar_size,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=2,  # epoch ints, easier to parse
        )
        page = _bars_to_frame(bars)
        if page.empty:
            break

        frames.append(page)
        oldest = page.index.min()
        if start_dt is not None and oldest <= start_dt:
            break
        # No start bound -> one page is enough.
        if start_dt is None:
            break
        # Step the cursor one bar before the oldest seen to avoid overlap.
        cursor = oldest.to_pydatetime() - timedelta(seconds=1)
        time.sleep(page_pause)

    if not frames:
        return _bars_to_frame([])

    out = pd.concat(frames).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    if start_dt is not None:
        out = out[out.index >= start_dt]
    if end is not None:
        out = out[out.index <= end_dt]
    return out


def _coerce_dt(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def stream_live_bars(
    ib,
    symbol: str,
    bar_size_seconds: int = 5,
    what_to_show: str = "TRADES",
    use_rth: bool = True,
    exchange: str = "SMART",
    currency: str = "USD",
) -> Iterator[pd.Series]:
    """Yield real-time bars as they close.

    ``bar_size_seconds`` must be 5 (IBKR only streams 5-second realtime bars
    natively; aggregate up in the consumer if you need 1m/5m).

    Each yielded value is a Series with ``open/high/low/close/volume`` and a
    UTC timestamp ``.name`` -- ready to append to a streaming DataFrame.
    """
    if bar_size_seconds != 5:
        raise ValueError("IBKR realtime bars are 5-second only")

    contract = make_stock_contract(symbol, exchange=exchange, currency=currency)
    ib.qualifyContracts(contract)

    bars = ib.reqRealTimeBars(
        contract, barSize=bar_size_seconds, whatToShow=what_to_show, useRTH=use_rth
    )
    seen = 0
    try:
        while True:
            ib.sleep(1)
            while seen < len(bars):
                bar = bars[seen]
                seen += 1
                ts = bar.time
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                yield pd.Series(
                    {
                        "open": float(bar.open_),
                        "high": float(bar.high),
                        "low": float(bar.low),
                        "close": float(bar.close),
                        "volume": float(bar.volume) if bar.volume is not None else 0.0,
                    },
                    name=ts.astimezone(timezone.utc),
                )
    finally:
        ib.cancelRealTimeBars(bars)


def save_ohlcv(df: pd.DataFrame, path: str | Path) -> None:
    """Write an OHLCV frame to CSV in the shape :func:`load_ohlcv` reads.

    Mirrors ``download_data.py`` so IBKR files are interchangeable with the
    ccxt CSVs already wired into the backtester.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    out.index.name = "timestamp"
    out.reset_index().to_csv(path, index=False)
