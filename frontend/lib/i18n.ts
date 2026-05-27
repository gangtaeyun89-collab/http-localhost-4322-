// Minimal i18n -- no library, just typed string tables. Korean is the
// primary surface; English entries are filled in opportunistically and the
// helper falls back to the Korean string when an English value is missing.
//
// To add a new key, add the Korean text under `ko`, then optionally translate
// it under `en`. Call sites use t("...") and TypeScript checks the key.

export type Locale = "ko" | "en";

const ko = {
  // App shell
  "app.title": "통계차익 자동매매",
  "app.subtitle": "Statistical Arbitrage Trading",

  // Navigation
  "nav.home": "홈",
  "nav.equity": "미국주식 · ETF",
  "nav.crypto": "암호화폐",
  "nav.dashboard": "대시보드",
  "nav.pairs": "페어 발견",
  "nav.backtest": "백테스트",
  "nav.strategies": "전략",
  "nav.positions": "포지션",
  "nav.orders": "주문",
  "nav.broker": "브로커 설정",
  "nav.exchange": "거래소 설정",
  "nav.settings": "설정",

  // Pair analysis KPI labels
  "kpi.cointJn": "공적분 (Johansen)",
  "kpi.cointEG": "공적분 (Engle-Granger)",
  "kpi.hurst": "Hurst 지수",
  "kpi.halfLife": "반감기",
  "kpi.corr": "상관계수",
  "kpi.hedgeRatio": "헤지비율",
  "kpi.ltBeta": "장기 베타",
  "kpi.mdd": "최대낙폭",
  "kpi.returns": "수익률",
  "kpi.sharpe": "샤프",
  "kpi.periods": "기간",
  "kpi.timeframe": "주기",

  // Sections
  "section.cumReturns": "누적 수익률",
  "section.spreadZscore": "스프레드 · Z-스코어",
  "section.copula": "코퓰라 · 가격분포",
  "section.correlation": "이동 상관",
  "section.vecm": "VECM 계수",
  "section.ecmImpulse": "충격반응",
  "section.dependency": "의존성 프로필",
  "section.pairList": "페어 목록",

  // Status labels
  "status.cointegrated": "공적분",
  "status.notCointegrated": "비공적분",
  "status.passed": "통과",
  "status.failed": "실패",

  // Home
  "home.heading": "통계차익 자동매매",
  "home.lede":
    "공적분 페어 발견 · 백테스트 · 실시간 시그널 · 자동 주문 실행을 하나의 도구에 담았습니다.",
  "home.equityCta": "미국주식 / ETF 시작",
  "home.cryptoCta": "암호화폐 시작",
  "home.equityDesc":
    "IBKR Paper / Live 계좌 기반. NYSE / NASDAQ 주식 및 ETF, 일봉부터 5초봉까지.",
  "home.cryptoDesc":
    "Binance · Bybit · Upbit 등 ccxt 호환 거래소. 현물 페어 + 무기한 선물 베이시스.",

  // Misc
  "misc.realtime": "실시간",
  "misc.paper": "모의",
  "misc.live": "실거래",
} as const;

const en: Partial<Record<keyof typeof ko, string>> = {
  "app.title": "Stat Arb Auto-Trading",
  "app.subtitle": "Statistical Arbitrage Trading",
  "nav.home": "Home",
  "nav.equity": "US Equity · ETF",
  "nav.crypto": "Crypto",
  "nav.dashboard": "Dashboard",
  "nav.pairs": "Pair Discovery",
  "nav.backtest": "Backtest",
  "nav.strategies": "Strategies",
  "nav.positions": "Positions",
  "nav.orders": "Orders",
  "nav.broker": "Broker",
  "nav.exchange": "Exchange",
  "nav.settings": "Settings",
  "kpi.cointJn": "Coint. (Johansen)",
  "kpi.cointEG": "Coint. (Engle-Granger)",
  "kpi.hurst": "Hurst",
  "kpi.halfLife": "Half-life",
  "kpi.corr": "Correlation",
  "kpi.hedgeRatio": "Hedge ratio",
  "kpi.ltBeta": "Long-term beta",
  "kpi.mdd": "Max drawdown",
  "kpi.returns": "Returns",
  "kpi.sharpe": "Sharpe",
  "kpi.periods": "Periods",
  "kpi.timeframe": "Timeframe",
  "section.cumReturns": "Cumulative Returns",
  "section.spreadZscore": "Spread · Z-score",
  "section.copula": "Copula · Joint Distribution",
  "section.correlation": "Rolling Correlation",
  "section.vecm": "VECM Coefficients",
  "section.ecmImpulse": "Impulse Response",
  "section.dependency": "Dependency Profile",
  "section.pairList": "Pair List",
  "status.cointegrated": "cointegrated",
  "status.notCointegrated": "not cointegrated",
  "status.passed": "passed",
  "status.failed": "failed",
  "home.heading": "Statistical Arbitrage Auto-Trading",
  "home.lede":
    "Discover cointegrated pairs, backtest, stream signals, and execute orders -- all in one place.",
  "home.equityCta": "Start US Equity / ETF",
  "home.cryptoCta": "Start Crypto",
  "home.equityDesc":
    "Powered by IBKR Paper / Live accounts. NYSE / NASDAQ stocks and ETFs, daily down to 5-second bars.",
  "home.cryptoDesc":
    "Binance · Bybit · Upbit and other ccxt-compatible venues. Spot pairs plus perpetual basis.",
  "misc.realtime": "live",
  "misc.paper": "paper",
  "misc.live": "live",
};

export type MessageKey = keyof typeof ko;

let currentLocale: Locale = "ko";

export function setLocale(locale: Locale) {
  currentLocale = locale;
}

export function t(key: MessageKey, locale?: Locale): string {
  const l = locale ?? currentLocale;
  if (l === "en") {
    return en[key] ?? ko[key];
  }
  return ko[key];
}
