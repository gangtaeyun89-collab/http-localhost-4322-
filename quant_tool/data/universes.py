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


def all_etfs() -> tuple[str, ...]:
    """Union of every ETF-style universe defined above, de-duplicated."""
    seen: dict[str, None] = {}
    for group in (SECTOR_ETFS, INDUSTRY_ETFS, COUNTRY_ETFS, STYLE_ETFS):
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
    for a, b in DUAL_LISTINGS + PEER_PAIRS:
        seen[a] = None
        seen[b] = None
    return tuple(seen.keys())
