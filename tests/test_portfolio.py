"""Tests for portfolio-level sizing: Ledoit-Wolf covariance and Kelly weights."""

import numpy as np
import pandas as pd
import pytest

from quant_tool.risk.portfolio import kelly_weights, ledoit_wolf_covariance


def test_ledoit_wolf_is_positive_definite_when_undersampled():
    """With more assets than observations the sample covariance is singular;
    the shrinkage estimate must still be invertible (all eigenvalues > 0)."""
    rng = np.random.default_rng(0)
    returns = pd.DataFrame(
        rng.normal(size=(6, 10)), columns=[f"p{i}" for i in range(10)]
    )
    cov = ledoit_wolf_covariance(returns)
    eigenvalues = np.linalg.eigvalsh(cov.to_numpy())
    assert (eigenvalues > 0).all()


def test_ledoit_wolf_is_labeled_and_symmetric():
    rng = np.random.default_rng(1)
    returns = pd.DataFrame(rng.normal(size=(200, 3)), columns=["a", "b", "c"])
    cov = ledoit_wolf_covariance(returns)
    assert list(cov.index) == ["a", "b", "c"]
    assert list(cov.columns) == ["a", "b", "c"]
    np.testing.assert_allclose(cov.to_numpy(), cov.to_numpy().T)


def test_kelly_weights_match_the_formula():
    # Sigma = I, so f = fraction * Sigma^-1 * mu = fraction * mu.
    labels = ["a", "b", "c"]
    mu = pd.Series([0.1, 0.2, 0.3], index=labels)
    cov = pd.DataFrame(np.eye(3), index=labels, columns=labels)
    weights = kelly_weights(mu, cov, fraction=0.5, max_gross_leverage=10.0)
    np.testing.assert_allclose(weights.to_numpy(), [0.05, 0.10, 0.15])


def test_kelly_weights_respect_leverage_cap():
    labels = ["a", "b"]
    mu = pd.Series([10.0, 10.0], index=labels)
    cov = pd.DataFrame(np.eye(2), index=labels, columns=labels)
    weights = kelly_weights(mu, cov, fraction=1.0, max_gross_leverage=1.0)
    assert np.abs(weights.to_numpy()).sum() == pytest.approx(1.0)


def test_kelly_weights_reject_bad_fraction():
    labels = ["a"]
    mu = pd.Series([0.1], index=labels)
    cov = pd.DataFrame([[1.0]], index=labels, columns=labels)
    with pytest.raises(ValueError):
        kelly_weights(mu, cov, fraction=1.5)


def test_kelly_weights_reject_misaligned_inputs():
    mu = pd.Series([0.1, 0.2], index=["a", "b"])
    cov = pd.DataFrame(np.eye(2), index=["a", "x"], columns=["a", "x"])
    with pytest.raises(ValueError):
        kelly_weights(mu, cov)
