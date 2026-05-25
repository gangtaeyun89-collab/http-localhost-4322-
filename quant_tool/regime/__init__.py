"""Market regime detection for concentrated single-name holdings.

Built around the SK Hynix sell-timing use case but symbol-agnostic. Two
complementary detectors are exposed:

* :class:`GaussianHMM` -- a smooth, multi-state hidden Markov model fit by
  Baum-Welch.  Use it to label the *current* regime (bull / chop / crisis)
  and read posterior probabilities for steady-state risk decisions.
* :func:`bocpd` -- Adams & MacKay (2007) Bayesian online change-point
  detection.  Reacts faster than the HMM but with more false positives;
  use it as a tripwire alongside the HMM, not on its own.

:mod:`signals` turns the posterior into a discrete TRIM / HOLD / REDUCE
recommendation.  It is a decision-support overlay, not financial advice.
"""

from quant_tool.regime.hmm import GaussianHMM
from quant_tool.regime.bocpd import bocpd
from quant_tool.regime.features import build_features
from quant_tool.regime.signals import RegimeSignal, generate_signals
from quant_tool.regime.backtest import RegimeBacktestResult, run_regime_backtest

__all__ = [
    "GaussianHMM",
    "bocpd",
    "build_features",
    "RegimeSignal",
    "generate_signals",
    "RegimeBacktestResult",
    "run_regime_backtest",
]
