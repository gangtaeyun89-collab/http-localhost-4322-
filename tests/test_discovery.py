"""Tests for the pair-discovery pipeline."""

import numpy as np

from quant_tool.data.ingestion import generate_universe
from quant_tool.strategy.discovery import (
    cluster_assets,
    correlation_distance,
    discover_pairs,
)


def _true_cluster(asset: str) -> str:
    """Recover the ground-truth cluster id from a column name."""
    return asset.split("_a")[0]


def test_correlation_distance_is_a_valid_metric():
    distance = correlation_distance(generate_universe(seed=1)).to_numpy()
    np.testing.assert_allclose(distance, distance.T)
    assert np.allclose(np.diag(distance), 0.0, atol=1e-9)
    assert distance.min() >= 0.0
    assert distance.max() <= 2.0 + 1e-9


def test_clustering_recovers_the_true_clusters():
    universe = generate_universe(
        n_clusters=3, assets_per_cluster=4, n_noise_assets=3, seed=2
    )
    clusters = cluster_assets(universe, distance_threshold=0.7)
    non_singleton = [members for members in clusters.values() if len(members) > 1]

    assert len(non_singleton) == 3
    for members in non_singleton:
        prefixes = {_true_cluster(m) for m in members}
        assert len(prefixes) == 1  # each group is exactly one true cluster
        assert next(iter(prefixes)).startswith("c")


def test_discover_pairs_only_finds_within_cluster_pairs():
    universe = generate_universe(
        n_clusters=3, assets_per_cluster=4, n_noise_assets=3, seed=3
    )
    result = discover_pairs(universe, distance_threshold=0.7, fdr_level=0.10)

    assert len(result.pairs) >= 10
    for pair in result.pairs:
        assert _true_cluster(pair.base) == _true_cluster(pair.quote)
        assert pair.base.startswith("c")  # noise assets are never paired
        assert pair.quote.startswith("c")


def test_discover_pairs_tests_far_fewer_than_brute_force():
    universe = generate_universe(
        n_clusters=3, assets_per_cluster=4, n_noise_assets=3, seed=4
    )
    result = discover_pairs(universe, distance_threshold=0.7)
    # Brute force would test C(15, 2) = 105 pairs; clustering-first tests ~18.
    assert result.n_tested <= 30


def test_discover_pairs_half_life_gate():
    universe = generate_universe(seed=5)
    loose = discover_pairs(universe, max_half_life=float("inf"))
    tight = discover_pairs(universe, max_half_life=5.0)
    assert len(tight.pairs) < len(loose.pairs)
