"""Universe-listing endpoint.

The frontend uses this to populate the "discover pairs from..." picker.
Returns both the configured CSV inventory and the named industry
baskets baked into ``quant_tool.data.universes`` so the user can compare
"what we have on disk" with "what we could download."
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.config import settings
from backend.app.schemas import UniverseInfo, UniversesResponse
from backend.app.services.data_source import csv_available, list_tickers
from quant_tool.data import universes as univ


# Human-readable labels for the named baskets. Order matters here -- the
# frontend renders these in this exact order.
_NAMED: list[tuple[str, str, tuple[str, ...]]] = [
    ("sp500_banks_large", "대형 은행 / Large Banks", univ.SP500_BANKS_LARGE),
    ("sp500_investment_banks", "투자은행 / Investment Banks", univ.SP500_INVESTMENT_BANKS),
    ("sp500_insurance_pc", "손해보험 / P&C Insurance", univ.SP500_INSURANCE_PC),
    ("sp500_semiconductors", "반도체 / Semiconductors", univ.SP500_SEMICONDUCTORS),
    ("sp500_software", "소프트웨어 / Software", univ.SP500_SOFTWARE),
    ("sp500_big_pharma", "대형 제약 / Big Pharma", univ.SP500_BIG_PHARMA),
    ("sp500_health_insurance", "건강보험 / Managed Care", univ.SP500_HEALTH_INSURANCE),
    ("sp500_oil_majors", "통합 정유사 / Oil Majors", univ.SP500_OIL_MAJORS),
    ("sp500_oil_services", "유전 서비스 / Oil Services", univ.SP500_OIL_SERVICES),
    ("sp500_refiners", "정제사 / Refiners", univ.SP500_REFINERS),
    ("sp500_railroads", "철도 / Railroads", univ.SP500_RAILROADS),
    ("sp500_airlines", "항공사 / Airlines", univ.SP500_AIRLINES),
    ("sp500_logistics", "물류 / Logistics", univ.SP500_LOGISTICS),
    ("sp500_bigbox_retail", "대형마트 / Big-Box Retail", univ.SP500_BIGBOX_RETAIL),
    ("sp500_home_improvement", "홈 인테리어 / Home Improvement", univ.SP500_HOME_IMPROVEMENT),
    ("sp500_restaurants", "외식 / QSR", univ.SP500_RESTAURANTS),
    ("sp500_beverages", "음료 / Beverages", univ.SP500_BEVERAGES),
    ("sp500_household_staples", "생필품 / Household Staples", univ.SP500_HOUSEHOLD_STAPLES),
    ("sp500_payments", "결제 / Payments", univ.SP500_PAYMENTS),
    ("sp500_telecom", "통신 / Telecom", univ.SP500_TELECOM),
    ("sp500_utilities_electric", "전력유틸리티 / Electric Utilities", univ.SP500_UTILITIES_ELECTRIC),
    ("sp500_reits", "리츠 / REITs", univ.SP500_REITS),
    ("sp500_aerospace_defense", "항공우주·방산 / A&D", univ.SP500_AEROSPACE_DEFENSE),
    ("sp500_machinery", "기계 / Machinery", univ.SP500_MACHINERY),
    ("sp500_automakers", "자동차 / Automakers", univ.SP500_AUTOMAKERS),
    ("sp500_gold_miners", "금광주 / Gold Miners", univ.SP500_GOLD_MINERS),
]


router = APIRouter(prefix="/api", tags=["universes"])


@router.get("/universes", response_model=UniversesResponse)
def list_universes() -> UniversesResponse:
    return UniversesResponse(
        universes=[
            UniverseInfo(name=name, label=label, tickers=list(tickers))
            for name, label, tickers in _NAMED
        ],
        csv_dir=str(settings.csv_dir),
        csv_available=csv_available(),
        csv_tickers=list_tickers(),
    )
