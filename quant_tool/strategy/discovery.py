"""Pair discovery over a universe of assets.

Brute-force cointegration testing of all ``N(N-1)/2`` pairs has a severe
multiple-testing problem: with 500 assets there are ~125 000 pairs, and at a 5%
significance level ~6 000 of them test "cointegrated" by chance alone.

The principled pipeline, implemented here:

1. **Distance** -- a correlation distance ``d(i,j) = sqrt(2(1 - rho))`` between
   every pair of return series. It is a proper metric, so any distance-based
   clustering can consume it.
2. **Cluster** -- group correlated assets, collapsing the universe into a
   handful of clusters (L1s, DeFi blue chips, ...).
3. **Test within clusters only** -- this drops the number of cointegration
   tests by an order of magnitude or more.
4. **FDR control** -- Benjamini-Hochberg correction on the surviving p-values
   bounds the false-discovery rate, the honest fix for multiple testing.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_tool.strategy.pair_finder import CointegrationResult, cointegration_test


@dataclass(frozen=True)
class DiscoveryResult:
    """Output of :func:`discover_pairs`.

    pairs        FDR-surviving cointegrated pairs, strongest evidence first
    n_clusters   number of clusters the universe collapsed into
    n_tested     number of within-cluster pairs that were cointegration-tested
    """

    pairs: list[CointegrationResult]
    n_clusters: int
    n_tested: int

    def describe(self) -> str:
        return (
            f"Discovered {len(self.pairs)} cointegrated pair(s) from "
            f"{self.n_tested} within-cluster test(s) across "
            f"{self.n_clusters} cluster(s)"
        )


def correlation_distance(prices: pd.DataFrame) -> pd.DataFrame:
    """Pairwise correlation distance ``d(i,j) = sqrt(2(1 - rho_ij))``.

    Computed on log returns. The result is a proper metric in ``[0, 2]``:
    identical assets are 0 apart, uncorrelated ones ``sqrt(2)``, perfectly
    anti-correlated ones 2.
    """
    returns = np.log(prices).diff().dropna()
    corr = returns.corr()
    # Clip guards tiny negative values from floating-point error.
    distance = np.sqrt(np.clip(2.0 * (1.0 - corr), 0.0, None))
    return distance


def cluster_assets(
    prices: pd.DataFrame, distance_threshold: float = 0.7
) -> dict[int, list[str]]:
    """Group assets into clusters by agglomerative clustering on the distance.

    ``distance_threshold`` is the correlation distance below which assets are
    merged; smaller means tighter, more numerous clusters. Returns a mapping
    from cluster label to the list of asset (column) names in it.
    """
    try:
        from sklearn.cluster import AgglomerativeClustering
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "cluster_assets requires the optional 'scikit-learn' dependency: "
            "pip install scikit-learn"
        ) from exc

    distance = correlation_distance(prices)
    model = AgglomerativeClustering(
        n_clusters=None,
        distance_threshold=distance_threshold,
        metric="precomputed",
        linkage="average",
    )
    labels = model.fit_predict(distance.to_numpy())

    clusters: dict[int, list[str]] = {}
    for asset, label in zip(distance.columns, labels):
        clusters.setdefault(int(label), []).append(str(asset))
    return clusters


def discover_pairs(
    prices: pd.DataFrame,
    distance_threshold: float = 0.7,
    fdr_level: float = 0.10,
    max_half_life: float = float("inf"),
) -> DiscoveryResult:
    """Discover tradable cointegrated pairs in a universe of price series.

    Clusters the universe, cointegration-tests every within-cluster pair,
    applies a Benjamini-Hochberg FDR correction at ``fdr_level`` to the
    p-values, and finally drops pairs whose mean-reversion half-life exceeds
    ``max_half_life``. Returns the survivors sorted by p-value.
    """
    try:
        from statsmodels.stats.multitest import multipletests
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise ImportError(
            "discover_pairs requires the optional 'statsmodels' dependency: "
            "pip install statsmodels"
        ) from exc

    clusters = cluster_assets(prices, distance_threshold)

    candidates: list[CointegrationResult] = []
    for members in clusters.values():
        for asset_a, asset_b in itertools.combinations(sorted(members), 2):
            candidates.append(
                cointegration_test(
                    prices[asset_a], prices[asset_b],
                    base_name=asset_a, quote_name=asset_b,
                )
            )

    if not candidates:
        return DiscoveryResult(pairs=[], n_clusters=len(clusters), n_tested=0)

    # Benjamini-Hochberg controls the expected false-discovery rate among the
    # within-cluster tests -- the honest correction for multiple testing.
    reject, _, _, _ = multipletests(
        [c.pvalue for c in candidates], alpha=fdr_level, method="fdr_bh"
    )
    survivors = [
        result
        for result, kept in zip(candidates, reject)
        if kept and result.half_life <= max_half_life
    ]
    survivors.sort(key=lambda result: result.pvalue)
    return DiscoveryResult(
        pairs=survivors, n_clusters=len(clusters), n_tested=len(candidates)
    )
