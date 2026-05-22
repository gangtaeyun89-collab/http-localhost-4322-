"""Tests for the weekly portfolio report."""

import numpy as np
import pandas as pd
import pytest

from quant_tool.allocation.report import Sleeve, build_report


def test_drifted_sleeve_triggers_rebalance():
    sleeve = Sleeve("Growth", pd.Series({"VTI": 0.8, "BND": 0.2}))
    holdings = {"Growth": pd.Series({"VTI": 9000.0, "BND": 1000.0})}  # 90/10
    report = build_report([sleeve], holdings, rebalance_band=0.05)

    sr = report.sleeves[0]
    assert sr.action == "REBALANCE"
    assert sr.trades.sum() == pytest.approx(0.0, abs=1e-6)
    assert sr.trades["VTI"] < 0 and sr.trades["BND"] > 0


def test_in_band_sleeve_holds():
    sleeve = Sleeve("Growth", pd.Series({"VTI": 0.8, "BND": 0.2}))
    holdings = {"Growth": pd.Series({"VTI": 8100.0, "BND": 1900.0})}  # ~1% drift
    report = build_report([sleeve], holdings, rebalance_band=0.05)

    sr = report.sleeves[0]
    assert sr.action == "HOLD"
    assert (sr.trades == 0.0).all()


def test_cash_only_sleeve_recommends_buying_in():
    sleeve = Sleeve("Growth", pd.Series({"VTI": 0.8, "BND": 0.2}))
    holdings = {"Growth": pd.Series({"CASH": 10000.0})}
    report = build_report([sleeve], holdings, rebalance_band=0.05)

    sr = report.sleeves[0]
    assert sr.action == "REBALANCE"
    assert sr.trades["CASH"] < 0  # sell the cash
    assert sr.trades["VTI"] == pytest.approx(8000.0)
    assert sr.trades["BND"] == pytest.approx(2000.0)


def test_risk_flag_for_a_drawdown():
    idx = pd.date_range("2024-01-01", periods=300, freq="D")
    path = np.concatenate([np.linspace(100, 150, 200), np.linspace(150, 120, 100)])
    prices = pd.DataFrame({"FALL": path}, index=idx)
    report = build_report(
        [Sleeve("S", pd.Series({"FALL": 1.0}))],
        {"S": pd.Series({"FALL": 1000.0})},
        prices=prices,
    )
    assert any("below its 1-year high" in flag for flag in report.risk_flags)


def test_render_produces_readable_text():
    sleeve = Sleeve("Growth", pd.Series({"VTI": 0.8, "BND": 0.2}), note="long horizon")
    holdings = {"Growth": pd.Series({"VTI": 9000.0, "BND": 1000.0})}
    text = build_report([sleeve], holdings).render()

    assert "WEEKLY PORTFOLIO REPORT" in text
    assert "Growth" in text
    assert "REBALANCE" in text
