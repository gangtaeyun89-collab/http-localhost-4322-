"""End-to-end regime-detection runner for SK Hynix (or any close series).

Pipeline:

    1. load close prices from a CSV/Parquet (see ``download_skhynix.py``)
    2. build (return, realized-vol, drawdown) features
    3. fit a 3-state Gaussian HMM
    4. run BOCPD on standardised returns as a fast tripwire
    5. combine into a TRIM / HOLD / REDUCE signal
    6. print the current state and optionally plot a regime-shaded chart

Usage
-----
    python run_regime.py data/skhynix.parquet
    python run_regime.py data/skhynix.csv --plot regime.png --states 3
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from quant_tool.regime import (
    GaussianHMM,
    bocpd,
    build_features,
    generate_signals,
)
from quant_tool.regime.bocpd import recent_change_prob
from quant_tool.regime.signals import latest


DISCLAIMER = (
    "Regime detection is a decision-support tool, not financial advice. "
    "Signals are lagging by construction (HMM smoothing) and noisy by "
    "construction (BOCPD).  Use as one input among many."
)


def load_close(path: Path, symbol: str | None) -> pd.Series:
    """Load a close-price series from CSV or Parquet."""
    if path.suffix == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, parse_dates=[0], index_col=0)
    if isinstance(df, pd.Series):
        return df.astype(float)
    if symbol and symbol in df.columns:
        return df[symbol].astype(float).dropna()
    if "Close" in df.columns:
        return df["Close"].astype(float).dropna()
    if df.shape[1] == 1:
        return df.iloc[:, 0].astype(float).dropna()
    raise ValueError(
        f"Could not find a close-price column in {path}.  "
        f"Columns: {list(df.columns)}.  Pass --symbol to disambiguate."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="CSV or Parquet of close prices")
    parser.add_argument("--symbol", default=None, help="Column to use if data is a panel")
    parser.add_argument("--states", type=int, default=3)
    parser.add_argument("--vol-window", type=int, default=20)
    parser.add_argument("--dd-window", type=int, default=60)
    parser.add_argument("--crisis-threshold", type=float, default=0.6)
    parser.add_argument("--persistence", type=int, default=3)
    parser.add_argument("--plot", type=Path, default=None, help="Optional output PNG")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    close = load_close(args.data, args.symbol)
    print(f"Loaded {len(close)} bars  [{close.index[0].date()} -> {close.index[-1].date()}]")

    feats = build_features(close, vol_window=args.vol_window, dd_window=args.dd_window)
    print(f"Feature matrix: {feats.shape}  columns={list(feats.columns)}")

    X = feats.to_numpy()
    Xs = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-9)

    hmm = GaussianHMM(n_states=args.states, random_state=args.seed).fit(Xs)
    posterior = pd.DataFrame(
        hmm.predict_proba(Xs),
        index=feats.index,
        columns=range(args.states),
    )
    order = hmm.order_states_by_return(Xs)
    crisis_state = int(order[0])
    print(f"State means (standardised, col 0 = return): {hmm.means_[:, 0].round(3)}")
    print(f"Crisis state id: {crisis_state}")
    print(f"Transition matrix:\n{np.round(hmm.trans_mat_, 3)}")

    R = bocpd(Xs[:, 0])
    cp_series = pd.Series(
        recent_change_prob(R, window=5), index=feats.index, name="cp_prob"
    )

    signals = generate_signals(
        posterior,
        crisis_state=crisis_state,
        cp_prob=cp_series,
        crisis_threshold=args.crisis_threshold,
        persistence=args.persistence,
    )

    cur = latest(signals)
    print()
    print(f"  As of  : {cur.date.date()}")
    print(f"  Regime : {cur.regime}")
    print(f"  Crisis posterior : {cur.crisis_prob:.2%}")
    print(f"  Recent change-pt : {cur.cp_prob:.2%}")
    print(f"  Suggested action : {cur.action}")
    print()
    print(DISCLAIMER)

    if args.plot is not None:
        _plot(close, feats, posterior, signals, crisis_state, args.plot)
        print(f"Plot written to {args.plot}")

    return 0


def _plot(close, feats, posterior, signals, crisis_state, out_path):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed; skipping plot")
        return

    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True)
    ax = axes[0]
    ax.plot(close.index, close.values, color="black", lw=0.8)
    ax.set_title(f"Price with crisis-regime shading (state {crisis_state})")
    ax.set_yscale("log")
    crisis = posterior.iloc[:, crisis_state]
    shade = (crisis >= 0.5).astype(int)
    in_block = False
    block_start = None
    for ts, v in zip(shade.index, shade.values):
        if v and not in_block:
            in_block = True
            block_start = ts
        elif not v and in_block:
            ax.axvspan(block_start, ts, color="red", alpha=0.15)
            in_block = False
    if in_block:
        ax.axvspan(block_start, shade.index[-1], color="red", alpha=0.15)

    axes[1].stackplot(
        posterior.index,
        posterior.T.values,
        labels=[f"state {c}" for c in posterior.columns],
        alpha=0.7,
    )
    axes[1].set_title("HMM smoothed state posterior")
    axes[1].set_ylim(0, 1)
    axes[1].legend(loc="upper left", fontsize=8)

    action_map = {"HOLD": 0, "TRIM": 1, "REDUCE": 2}
    axes[2].plot(signals.index, signals["action"].map(action_map), drawstyle="steps-post")
    axes[2].set_yticks([0, 1, 2])
    axes[2].set_yticklabels(["HOLD", "TRIM", "REDUCE"])
    axes[2].set_title("Discrete action")

    fig.tight_layout()
    fig.savefig(out_path, dpi=120)


if __name__ == "__main__":
    raise SystemExit(main())
