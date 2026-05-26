"""Pre-defined US equity and ETF universes for pair screening.

A statistical-arbitrage pipeline starts by picking a *universe* -- the set of
instruments inside which the discovery layer searches for cointegrated
combinations. Different universes encode different priors about where
mean-reverting relationships actually live:

* :data:`SECTOR_ETFS` -- the 11 SPDR sector ETFs. Same-sector pairs (e.g.
  XLF/KRE) share factor exposure and are classic cointegration candidates.
* :data:`INDUSTRY_ETFS` -- narrower industry ETFs (semis, banks, retail).
* :data:`COUNTRY_ETFS` -- single-country MSCI ETFs. Macro-linked pairs
  (EWA/EWC, EWJ/EWY) tend to mean-revert around relative-value swings.
* :data:`STYLE_ETFS` -- value/growth/momentum/quality factor ETFs.
* :data:`MEGACAP_TECH` -- the obvious "Magnificent 7" + a few peers.
* :data:`DUAL_LISTINGS` and :data:`PEER_PAIRS` -- hand-curated obvious pairs
  to seed the screener with known-good relationships for validation.
* :data:`SP500_TOP_100` -- liquid large caps; reasonable starting universe
  when you do not yet have the full S&P 500 list.

Each universe is just a tuple of ticker symbols, so they compose freely::

    from quant_tool.data import universes
    tickers = universes.SECTOR_ETFS + universes.MEGACAP_TECH
"""

from __future__ import annotations

# SPDR sector ETFs (the 11 GICS sectors).
SECTOR_ETFS: tuple[str, ...] = (
    "XLK",  # Technology
    "XLF",  # Financials
    "XLE",  # Energy
    "XLV",  # Health Care
    "XLI",  # Industrials
    "XLY",  # Consumer Discretionary
    "XLP",  # Consumer Staples
    "XLU",  # Utilities
    "XLB",  # Materials
    "XLRE", # Real Estate
    "XLC",  # Communication Services
)

# Narrower industry ETFs that overlap with sector ETFs and often cointegrate
# with their parent sector or with each other.
INDUSTRY_ETFS: tuple[str, ...] = (
    "SMH",  # Semiconductors
    "SOXX", # Semiconductors (alt)
    "KRE",  # Regional banks
    "KBE",  # Banks
    "IBB",  # Biotech
    "XBI",  # Biotech (equal weight)
    "XOP",  # Oil & gas E&P
    "OIH",  # Oil services
    "XME",  # Metals & mining
    "XRT",  # Retail
    "ITB",  # Home construction
    "JETS", # Airlines
)

# Single-country / regional ETFs. Pairs across geographically or
# economically linked countries are well-studied stat-arb targets.
COUNTRY_ETFS: tuple[str, ...] = (
    "EWA",  # Australia
    "EWC",  # Canada
    "EWG",  # Germany
    "EWJ",  # Japan
    "EWY",  # South Korea
    "EWT",  # Taiwan
    "EWU",  # United Kingdom
    "EWZ",  # Brazil
    "EWW",  # Mexico
    "EWH",  # Hong Kong
    "MCHI", # China
    "INDA", # India
    "EEM",  # Emerging markets
    "EFA",  # Developed ex-US
)

# Broad-market and style/factor ETFs.
STYLE_ETFS: tuple[str, ...] = (
    "SPY",  # S&P 500
    "IVV",  # S&P 500 (alt)
    "VOO",  # S&P 500 (alt)
    "QQQ",  # Nasdaq 100
    "DIA",  # Dow Jones
    "IWM",  # Russell 2000
    "VTI",  # Total US market
    "MTUM", # Momentum
    "QUAL", # Quality
    "VLUE", # Value
    "USMV", # Min volatility
    "SPLV", # Low volatility
)

# Hand-picked obvious pairs: same ticker on different exchanges, A/B shares,
# or near-identical ETFs. These are easy "ground truth" cointegrated pairs
# you can use to sanity-check the discovery pipeline.
DUAL_LISTINGS: tuple[tuple[str, str], ...] = (
    ("SPY", "IVV"),
    ("SPY", "VOO"),
    ("GOOG", "GOOGL"),
    ("BRK.B", "BRK.A"),  # share class
    ("IBB", "XBI"),
    ("SMH", "SOXX"),
    ("KRE", "KBE"),
)

# Hand-curated economic peer pairs. Useful as seeds and as validation.
PEER_PAIRS: tuple[tuple[str, str], ...] = (
    ("KO", "PEP"),       # Beverages
    ("V", "MA"),         # Card networks
    ("HD", "LOW"),       # Home improvement
    ("MCD", "YUM"),      # Fast food
    ("PG", "CL"),        # Consumer staples
    ("WMT", "TGT"),      # Big-box retail
    ("XOM", "CVX"),      # Integrated oil
    ("JPM", "BAC"),      # Money-center banks
    ("GS", "MS"),        # Investment banks
    ("UPS", "FDX"),      # Logistics
    ("CAT", "DE"),       # Heavy industrials
    ("NVDA", "AMD"),     # GPUs
    ("MSFT", "GOOGL"),   # Megacap tech
)

# The "Magnificent 7" plus close peers -- highly liquid, lots of relative
# value swings, but expect frequent regime breaks.
MEGACAP_TECH: tuple[str, ...] = (
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    "AMD", "AVGO", "ORCL", "CRM", "ADBE", "NFLX",
)

# A liquid large-cap universe to start with when you do not yet have the full
# S&P 500 list. Chosen for liquidity and sector spread. Edit freely.
SP500_TOP_100: tuple[str, ...] = (
    # Tech
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AVGO",
    "ORCL", "CRM", "ADBE", "NFLX", "AMD", "INTC", "QCOM", "TXN", "MU",
    "AMAT", "LRCX", "KLAC", "CSCO", "IBM", "NOW",
    # Financials
    "JPM", "BAC", "WFC", "C", "GS", "MS", "AXP", "BLK", "SCHW", "USB",
    "PNC", "TFC", "COF", "BK", "STT",
    # Health Care
    "UNH", "JNJ", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "DHR",
    "BMY", "AMGN", "GILD", "CVS", "CI", "ELV",
    # Consumer
    "WMT", "PG", "KO", "PEP", "COST", "HD", "LOW", "MCD", "SBUX", "NKE",
    "TGT", "BKNG", "TJX", "DIS",
    # Industrials/Energy
    "CAT", "DE", "BA", "GE", "HON", "LMT", "RTX", "UPS", "FDX", "UNP",
    "CSX", "XOM", "CVX", "COP", "EOG", "SLB",
    # Materials/Utilities/Real Estate/Comm
    "LIN", "SHW", "NEE", "DUK", "SO", "AMT", "PLD", "EQIX", "T", "VZ",
    "CMCSA", "TMUS",
)


# ---------------------------------------------------------------------------
# Homogeneous industry baskets. These are where cointegration actually lives:
# narrow groups of companies running the same business model against the same
# end market, so their stock prices share a common stochastic trend and the
# relative spread mean-reverts. Each list is intentionally small (8-15 names)
# so an O(N^2) pairwise screen is cheap.
# ---------------------------------------------------------------------------

# Money-center & super-regional banks. Same yield-curve and credit-cycle
# exposure -> classic cointegration cluster.
SP500_BANKS_LARGE: tuple[str, ...] = (
    "JPM", "BAC", "WFC", "C", "USB", "PNC", "TFC", "MTB", "FITB", "HBAN",
    "RF", "KEY", "CFG", "CMA",
)

# Pure-play investment banks / capital markets.
SP500_INVESTMENT_BANKS: tuple[str, ...] = (
    "GS", "MS", "SCHW", "BLK", "BX", "KKR", "APO", "AMP", "RJF", "LPLA",
    "NTRS", "STT", "BK",
)

# Property & casualty / multi-line insurers.
SP500_INSURANCE_PC: tuple[str, ...] = (
    "TRV", "CB", "PGR", "ALL", "AIG", "HIG", "WRB", "CINF", "AFL", "MET",
    "PRU", "AJG", "BRO", "MMC",
)

# Semiconductors -- the canonical stat-arb basket (Krauss, Sarmento & Horta).
SP500_SEMICONDUCTORS: tuple[str, ...] = (
    "NVDA", "AMD", "INTC", "AVGO", "QCOM", "TXN", "MU", "AMAT", "LRCX",
    "KLAC", "MRVL", "ON", "MCHP", "ADI", "NXPI", "MPWR",
)

# Enterprise / infrastructure software. Similar SaaS revenue model.
SP500_SOFTWARE: tuple[str, ...] = (
    "MSFT", "ORCL", "CRM", "ADBE", "NOW", "INTU", "WDAY", "SNPS", "CDNS",
    "PANW", "FTNT", "CRWD", "ZS", "DDOG",
)

# Big pharma. Long product cycles, shared regulatory/payor exposure.
SP500_BIG_PHARMA: tuple[str, ...] = (
    "JNJ", "LLY", "PFE", "MRK", "ABBV", "BMY", "AMGN", "GILD", "VRTX",
    "REGN", "ZTS",
)

# Managed care / health insurers. Same payor economics.
SP500_HEALTH_INSURANCE: tuple[str, ...] = (
    "UNH", "ELV", "CI", "HUM", "CVS", "CNC", "MOH",
)

# Integrated oil & gas (upstream + downstream). Crude-price driven.
SP500_OIL_MAJORS: tuple[str, ...] = (
    "XOM", "CVX", "COP", "EOG", "OXY", "PXD", "HES", "DVN", "FANG",
)

# Oil services & equipment. Levered to drilling activity.
SP500_OIL_SERVICES: tuple[str, ...] = (
    "SLB", "HAL", "BKR", "FTI", "NOV", "OXY",
)

# Refiners / midstream. Crack spread + crude price.
SP500_REFINERS: tuple[str, ...] = (
    "MPC", "VLO", "PSX", "HFC", "DK",
)

# Railroads -- a textbook tight cointegration cluster.
SP500_RAILROADS: tuple[str, ...] = (
    "UNP", "CSX", "NSC", "CP", "CNI",
)

# Air carriers.
SP500_AIRLINES: tuple[str, ...] = (
    "DAL", "UAL", "AAL", "LUV", "ALK", "JBLU", "SAVE",
)

# Parcel & freight.
SP500_LOGISTICS: tuple[str, ...] = (
    "UPS", "FDX", "EXPD", "CHRW", "ODFL", "JBHT", "XPO",
)

# Big-box / mass retail.
SP500_BIGBOX_RETAIL: tuple[str, ...] = (
    "WMT", "TGT", "COST", "BJ", "DG", "DLTR", "FIVE",
)

# Home improvement retail.
SP500_HOME_IMPROVEMENT: tuple[str, ...] = (
    "HD", "LOW", "FND", "TSCO", "WSM",
)

# Quick-service restaurants.
SP500_RESTAURANTS: tuple[str, ...] = (
    "MCD", "SBUX", "YUM", "CMG", "QSR", "DPZ", "WEN", "DRI",
)

# Beverages -- another textbook stat-arb basket.
SP500_BEVERAGES: tuple[str, ...] = (
    "KO", "PEP", "MNST", "KDP", "STZ", "TAP", "BUD",
)

# Household & personal-care staples.
SP500_HOUSEHOLD_STAPLES: tuple[str, ...] = (
    "PG", "CL", "KMB", "CHD", "CLX", "EL", "ULTA",
)

# Card networks + major issuers.
SP500_PAYMENTS: tuple[str, ...] = (
    "V", "MA", "AXP", "PYPL", "DFS", "COF", "FIS", "FISV", "GPN",
)

# US wireless + wireline telecom.
SP500_TELECOM: tuple[str, ...] = (
    "T", "VZ", "TMUS", "CMCSA", "CHTR",
)

# Regulated electric utilities.
SP500_UTILITIES_ELECTRIC: tuple[str, ...] = (
    "NEE", "DUK", "SO", "AEP", "EXC", "XEL", "WEC", "ED", "ETR", "ES",
    "DTE", "AEE", "CMS", "PPL", "FE",
)

# Residential & retail REITs.
SP500_REITS: tuple[str, ...] = (
    "PLD", "AMT", "EQIX", "CCI", "PSA", "O", "SPG", "WELL", "AVB", "EQR",
    "ESS", "MAA", "UDR", "CPT",
)

# Aerospace & defense primes.
SP500_AEROSPACE_DEFENSE: tuple[str, ...] = (
    "BA", "LMT", "RTX", "NOC", "GD", "TXT", "TDG", "LHX", "HII",
)

# Heavy machinery / agri equipment.
SP500_MACHINERY: tuple[str, ...] = (
    "CAT", "DE", "CMI", "PCAR", "PH", "ETN", "EMR", "ITW", "DOV", "ROK",
)

# Auto OEMs.
SP500_AUTOMAKERS: tuple[str, ...] = (
    "TSLA", "GM", "F", "RIVN", "LCID",
)

# Gold & precious-metal miners (commodity-driven).
SP500_GOLD_MINERS: tuple[str, ...] = (
    "NEM", "GOLD", "FNV", "WPM", "AEM", "KGC", "AGI",
)


def all_etfs() -> tuple[str, ...]:
    """Union of every ETF-style universe defined above, de-duplicated."""
    seen: dict[str, None] = {}
    for group in (SECTOR_ETFS, INDUSTRY_ETFS, COUNTRY_ETFS, STYLE_ETFS):
        for t in group:
            seen[t] = None
    return tuple(seen.keys())


INDUSTRY_BASKETS: dict[str, tuple[str, ...]] = {
    "sp500_banks_large": SP500_BANKS_LARGE,
    "sp500_investment_banks": SP500_INVESTMENT_BANKS,
    "sp500_insurance_pc": SP500_INSURANCE_PC,
    "sp500_semiconductors": SP500_SEMICONDUCTORS,
    "sp500_software": SP500_SOFTWARE,
    "sp500_big_pharma": SP500_BIG_PHARMA,
    "sp500_health_insurance": SP500_HEALTH_INSURANCE,
    "sp500_oil_majors": SP500_OIL_MAJORS,
    "sp500_oil_services": SP500_OIL_SERVICES,
    "sp500_refiners": SP500_REFINERS,
    "sp500_railroads": SP500_RAILROADS,
    "sp500_airlines": SP500_AIRLINES,
    "sp500_logistics": SP500_LOGISTICS,
    "sp500_bigbox_retail": SP500_BIGBOX_RETAIL,
    "sp500_home_improvement": SP500_HOME_IMPROVEMENT,
    "sp500_restaurants": SP500_RESTAURANTS,
    "sp500_beverages": SP500_BEVERAGES,
    "sp500_household_staples": SP500_HOUSEHOLD_STAPLES,
    "sp500_payments": SP500_PAYMENTS,
    "sp500_telecom": SP500_TELECOM,
    "sp500_utilities_electric": SP500_UTILITIES_ELECTRIC,
    "sp500_reits": SP500_REITS,
    "sp500_aerospace_defense": SP500_AEROSPACE_DEFENSE,
    "sp500_machinery": SP500_MACHINERY,
    "sp500_automakers": SP500_AUTOMAKERS,
    "sp500_gold_miners": SP500_GOLD_MINERS,
}


def all_industry_baskets() -> tuple[str, ...]:
    """Union of every homogeneous industry basket, de-duplicated."""
    seen: dict[str, None] = {}
    for group in INDUSTRY_BASKETS.values():
        for t in group:
            seen[t] = None
    return tuple(seen.keys())


def all_tickers() -> tuple[str, ...]:
    """Every named ticker across every universe, de-duplicated."""
    seen: dict[str, None] = {}
    for group in (
        SECTOR_ETFS,
        INDUSTRY_ETFS,
        COUNTRY_ETFS,
        STYLE_ETFS,
        MEGACAP_TECH,
        SP500_TOP_100,
    ):
        for t in group:
            seen[t] = None
    for group in INDUSTRY_BASKETS.values():
        for t in group:
            seen[t] = None
    for a, b in DUAL_LISTINGS + PEER_PAIRS:
        seen[a] = None
        seen[b] = None
    return tuple(seen.keys())
