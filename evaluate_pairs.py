#!/usr/bin/env python3
"""Walk-forward OOS evaluation over every cointegrated pair in a universe.

Single-pair walk-forward tells you whether *one* pair has alpha. To know
whether stat-arb itself has alpha on a universe you need the joint answer:
how many pairs survive in OOS, what their OOS Sharpe distribution looks
like, and whether the survivors form a useful portfolio when combined.

Pipeline:

1. Cointegration-screen every pair, keep those with ``p-value <= --max-pvalue``
   and a half-life inside the ``--min/--max-half-life`` band.
2. Run walk-forward analysis on each survivor, with ``zscore_lookback``
   automatically sized to the pair's half-life (``--tune-lookback``).
3. Print a sorted OOS scoreboard.
4. Optionally combine the OOS-positive pairs into a fractional-Kelly
   portfolio backtest (``--portfolio``).

Example
-------
    python evaluate_pairs.py --csv-dir market_data/oil \\
        --train-size 800 --test-size 200 --portfolio
"""

from __future__ import annotations

import argparse
import itertools
from dataclasses import replace
from pathlib import Path

import pandas as pd

from quant_tool.backtest.portfolio import portfolio_backtest
from quant_tool.backtest.walk_forward import walk_forward
from quant_tool.config.settings import (
    BacktestConfig,
    CostConfig,
    PairConfig,
    SignalConfig,
)
from quant_tool.data.features import align_prices, infer_bars_per_year
from quant_tool.data.ingestion import load_universe_from_dir
from quant_tool.monitoring import get_logger
from quant_tool.strategy.pair_finder import cointegration_test

log = get_logger("evaluate")


def _eval_one(
    base_series: pd.Series,
    quote_series: pd.Series,
    base_name: str,
    quote_name: str,
    config: BacktestConfig,
    train_size: int,
    test_size: int,
    half_life: float,
    tune_lookback: bool,
) -> dict | None:
    """Walk-forward one pair; returns metrics dict or None on failure."""
    prices = align_prices(base_series, quote_series)
    if len(prices) < train_size + test_size:
        return None
    cfg = config
    if tune_lookback:
        cfg = replace(
            cfg,
            signal=SignalConfig.for_half_life(
                half_life,
                entry_z=cfg.signal.entry_z,
                exit_z=cfg.signal.exit_z,
                stop_z=cfg.signal.stop_z,
            ),
        )
    try:
        wf = walk_forward(prices, cfg, train_size, test_size)
    except Exception as exc:  # noqa: BLE001 -- log and continue
        log.warning("walk-forward failed for %s/%s: %s", base_name, quote_name, exc)
        return None
    s = wf.stats
    # Per-window train Sharpe is computed honestly (only on the train window
    # that *precedes* its OOS test window), so its mean is forward-only and
    # safe to filter portfolios on -- unlike OOS Sharpe, which would be
    # look-ahead cherry-picking.
    n_windows = max(1, len(wf.windows))
    mean_train_sharpe = sum(w.train_sharpe for w in wf.windows) / n_windows
    mean_test_sharpe = sum(w.test_sharpe for w in wf.windows) / n_windows
    return {
        "base": base_name,
        "quote": quote_name,
        "pvalue": float("nan"),  # filled by caller
        "half_life": half_life,
        "lookback": cfg.signal.zscore_lookback,
        "train_sharpe": mean_train_sharpe,
        "test_sharpe": mean_test_sharpe,
        "oos_sharpe": s["sharpe"],
        "oos_cagr": s["cagr"],
        "oos_mdd": s["max_drawdown"],
        "trades": s["n_trades"],
        "win_rate": s["win_rate"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--csv-dir", required=True, help="directory of OHLCV CSVs")
    parser.add_argument(
        "--max-pvalue",
        type=float,
        default=0.10,
        help="cointegration p-value upper bound (raw, not FDR)",
    )
    parser.add_argument("--min-half-life", type=float, default=5.0)
    parser.add_argument("--max-half-life", type=float, default=200.0)
    parser.add_argument("--train-size", type=int, default=800)
    parser.add_argument("--test-size", type=int, default=200)
    parser.add_argument(
        "--asset-class",
        choices=["equity", "crypto"],
        default="equity",
    )
    parser.add_argument("--bars-per-year", type=int, default=None)
    parser.add_argument("--target-volatility", type=float, default=0.15)
    parser.add_argument(
        "--tune-lookback",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="size zscore_lookback to each pair's half-life (default: on)",
    )
    parser.add_argument(
        "--portfolio",
        action="store_true",
        help="run a fractional-Kelly portfolio backtest over survivor pairs",
    )
    parser.add_argument(
        "--portfolio-filter",
        choices=["oos", "train", "none"],
        default="train",
        help="how to pick portfolio pairs: 'train' (mean walk-forward train "
        "Sharpe > threshold, forward-only/honest), 'oos' (mean OOS Sharpe > "
        "threshold, look-ahead -- exploratory only), 'none' (keep all)",
    )
    parser.add_argument(
        "--portfolio-sharpe-threshold",
        type=float,
        default=0.0,
        help="Sharpe threshold for the chosen --portfolio-filter (default: 0)",
    )
    parser.add_argument(
        "--save",
        default=None,
        help="optional path to write the per-pair scoreboard as CSV",
    )
    args = parser.parse_args()

    universe = load_universe_from_dir(args.csv_dir)
    log.info("Universe: %d assets x %d bars", universe.shape[1], len(universe))

    bpy = args.bars_per_year or infer_bars_per_year(
        universe.index, asset_class=args.asset_class
    )
    cost = (
        CostConfig.for_crypto()
        if args.asset_class == "crypto"
        else CostConfig.for_us_equity()
    )
    base_config = BacktestConfig(
        pair=PairConfig(base="base", quote="quote"),
        hedge_method="kalman",
        cost=cost,
        bars_per_year=bpy,
        target_volatility=args.target_volatility,
    )
    log.info(
        "Backtest defaults: bars_per_year=%d, cost=%.1f+%.1f bps",
        bpy,
        cost.taker_fee_bps,
        cost.slippage_bps,
    )

    # --- 1. Cointegration screen on every pair --------------------------------
    symbols = list(universe.columns)
    n_pairs = len(symbols) * (len(symbols) - 1) // 2
    log.info("Screening %d candidate pair(s) ...", n_pairs)
    candidates = []
    for a, b in itertools.combinations(symbols, 2):
        try:
            r = cointegration_test(
                universe[a], universe[b], base_name=a, quote_name=b
            )
        except Exception as exc:  # degenerate input
            log.debug("skip %s/%s: %s", a, b, exc)
            continue
        if r.pvalue > args.max_pvalue:
            continue
        if not (args.min_half_life <= r.half_life <= args.max_half_life):
            continue
        candidates.append(r)
    candidates.sort(key=lambda r: r.pvalue)
    log.info(
        "Cointegration survivors: %d (p<=%.2f, half-life in [%.0f, %.0f])",
        len(candidates),
        args.max_pvalue,
        args.min_half_life,
        args.max_half_life,
    )

    if not candidates:
        log.warning("nothing to evaluate; loosen --max-pvalue or half-life band")
        return

    # --- 2. Walk-forward each survivor ----------------------------------------
    rows: list[dict] = []
    for i, r in enumerate(candidates, 1):
        log.info(
            "[%d/%d] %s ~ %s   p=%.4f  half-life=%.1f",
            i,
            len(candidates),
            r.base,
            r.quote,
            r.pvalue,
            r.half_life,
        )
        row = _eval_one(
            universe[r.base],
            universe[r.quote],
            r.base,
            r.quote,
            base_config,
            args.train_size,
            args.test_size,
            r.half_life,
            args.tune_lookback,
        )
        if row is None:
            continue
        row["pvalue"] = r.pvalue
        rows.append(row)

    if not rows:
        log.warning("no pair survived walk-forward")
        return

    df = pd.DataFrame(rows).sort_values("oos_sharpe", ascending=False)
    cols = [
        "base",
        "quote",
        "pvalue",
        "half_life",
        "lookback",
        "train_sharpe",
        "test_sharpe",
        "oos_sharpe",
        "oos_cagr",
        "oos_mdd",
        "trades",
        "win_rate",
    ]
    print("\n" + "=" * 92)
    print("Per-pair walk-forward OOS scoreboard")
    print("=" * 92)
    print(df[cols].to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    print("=" * 92)
    n = len(df)
    n_pos = int((df["oos_sharpe"] > 0).sum())
    n_strong = int((df["oos_sharpe"] > 0.3).sum())
    mean_s = float(df["oos_sharpe"].mean())
    median_s = float(df["oos_sharpe"].median())
    print(
        f"\nN={n}   mean OOS Sharpe={mean_s:+.3f}   median={median_s:+.3f}   "
        f"Sharpe>0: {n_pos}/{n}   Sharpe>0.3: {n_strong}/{n}"
    )

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        df[cols].to_csv(out, index=False)
        print(f"scoreboard written to {out}")

    # --- 3. Optional portfolio backtest of survivors --------------------------
    if args.portfolio:
        if args.portfolio_filter == "none":
            survivors = df
            filter_desc = "all pairs"
        elif args.portfolio_filter == "oos":
            survivors = df[df["oos_sharpe"] > args.portfolio_sharpe_threshold]
            filter_desc = f"OOS Sharpe > {args.portfolio_sharpe_threshold} (LOOK-AHEAD)"
        else:  # "train" -- honest forward-only filter
            survivors = df[df["train_sharpe"] > args.portfolio_sharpe_threshold]
            filter_desc = f"train Sharpe > {args.portfolio_sharpe_threshold}"
        log.info(
            "Portfolio filter '%s' -> %d / %d pair(s)",
            filter_desc,
            len(survivors),
            len(df),
        )
        if len(survivors) < 2:
            log.info("too few pairs survive -- skipping portfolio")
            return
        pairs = [(row["base"], row["quote"]) for _, row in survivors.iterrows()]
        pf = portfolio_backtest(
            universe,
            pairs,
            base_config,
            lookback=min(500, len(universe) // 3),
            rebalance=60,
            kelly_fraction=0.25,
        )
        print("\n" + "=" * 48)
        print(f"Portfolio filter: {filter_desc}")
        print(f"Pairs picked:     {len(pairs)} / {len(df)}")
        print("-" * 48)
        print(pf.describe())
        print("=" * 48)

        # Effective N from the pair return correlation matrix. A book of N
        # pairs whose returns are pairwise correlated rho has an effective N
        # of N / (1 + (N-1) rho). When rho is high (REITs, all rate-driven)
        # the diversification benefit collapses -- knowing this number
        # explains why portfolio Sharpe often falls short of the per-pair
        # average.
        try:
            from quant_tool.backtest.engine import run_backtest

            per_pair_rets = {}
            for base, quote in pairs:
                bt = run_backtest(
                    align_prices(universe[base], universe[quote]), base_config
                )
                per_pair_rets[f"{base}/{quote}"] = bt.bars["net_return"]
            ret_df = pd.concat(per_pair_rets, axis=1).dropna()
            corr = ret_df.corr()
            n = len(corr)
            mean_rho = (corr.values.sum() - n) / (n * (n - 1))
            eff_n = n / (1 + (n - 1) * mean_rho) if mean_rho > -1 / (n - 1) else n
            print(
                f"\nPair-return correlation diagnostic:\n"
                f"  Pairs N           {n}\n"
                f"  Mean pairwise rho {mean_rho:+.3f}\n"
                f"  Effective N       {eff_n:.1f}  (N / (1 + (N-1) rho))\n"
                f"  -> portfolio Sharpe ceiling ~ mean per-pair Sharpe "
                f"x sqrt({eff_n:.1f}/N) = x {(eff_n / n) ** 0.5:.2f}"
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("correlation diagnostic skipped: %s", exc)


if __name__ == "__main__":
    main()
