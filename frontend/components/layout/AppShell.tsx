import Link from "next/link";
import {
  BarChart3,
  Bell,
  ChevronRight,
  Coins,
  HelpCircle,
  Home,
  LineChart,
  Settings,
  ShieldCheck,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { t } from "@/lib/i18n";

// The shell is intentionally dense, like the Bloomberg / TradingView UIs the
// dashboards take after: thin sidebar with section icons + labels, slim top
// bar with market / mode pickers, and the content slot below.

type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const equityNav: NavItem[] = [
  { href: "/equity/dashboard", label: t("nav.dashboard"), icon: BarChart3 },
  { href: "/equity/pairs", label: t("nav.pairs"), icon: LineChart },
  { href: "/equity/backtest", label: t("nav.backtest"), icon: TrendingUp },
  { href: "/equity/strategies", label: t("nav.strategies"), icon: ShieldCheck },
  { href: "/equity/positions", label: t("nav.positions"), icon: Wallet },
  { href: "/equity/orders", label: t("nav.orders"), icon: ChevronRight },
  { href: "/equity/broker", label: t("nav.broker"), icon: Settings },
];

const cryptoNav: NavItem[] = [
  { href: "/crypto/dashboard", label: t("nav.dashboard"), icon: BarChart3 },
  { href: "/crypto/pairs", label: t("nav.pairs"), icon: LineChart },
  { href: "/crypto/backtest", label: t("nav.backtest"), icon: TrendingUp },
  { href: "/crypto/strategies", label: t("nav.strategies"), icon: ShieldCheck },
  { href: "/crypto/positions", label: t("nav.positions"), icon: Wallet },
  { href: "/crypto/orders", label: t("nav.orders"), icon: ChevronRight },
  { href: "/crypto/exchange", label: t("nav.exchange"), icon: Settings },
];

export function AppShell({
  market,
  children,
}: {
  market: "equity" | "crypto";
  children: React.ReactNode;
}) {
  const nav = market === "equity" ? equityNav : cryptoNav;
  const marketColor =
    market === "equity" ? "text-accent-cyan" : "text-accent-magenta";

  return (
    <div className="grid h-screen grid-cols-[200px_1fr] grid-rows-[44px_1fr]">
      {/* Top-left: brand */}
      <div className="col-span-1 row-span-1 flex items-center gap-2 border-b border-r border-border-subtle bg-bg-panel px-3">
        <Link href="/" className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-accent-green shadow-[0_0_8px_currentColor] text-accent-green" />
          <span className="text-xs font-semibold tracking-wide">
            {t("app.title")}
          </span>
        </Link>
      </div>

      {/* Top bar */}
      <header className="col-span-1 row-span-1 flex items-center justify-between border-b border-border-subtle bg-bg-panel px-4">
        <div className="flex items-center gap-3">
          <MarketSwitch active={market} />
          <span className="text-2xs uppercase tracking-widest text-text-muted">
            {market === "equity" ? "IBKR Paper" : "Binance Testnet"}
          </span>
        </div>
        <div className="flex items-center gap-3 text-text-secondary">
          <button className="rounded p-1 hover:bg-bg-elevated">
            <Bell className="h-4 w-4" />
          </button>
          <button className="rounded p-1 hover:bg-bg-elevated">
            <HelpCircle className="h-4 w-4" />
          </button>
          <div className="ml-2 text-2xs uppercase tracking-widest text-text-muted">
            v0.1
          </div>
        </div>
      </header>

      {/* Sidebar */}
      <aside className="col-span-1 row-span-1 border-r border-border-subtle bg-bg-panel">
        <nav className="flex flex-col gap-0.5 p-2">
          <SidebarLink
            href="/"
            label={t("nav.home")}
            icon={Home}
            color="text-text-secondary"
          />
          <div className="mt-3 px-2 pb-1 text-2xs uppercase tracking-widest text-text-faint">
            {market === "equity" ? t("nav.equity") : t("nav.crypto")}
          </div>
          {nav.map((item) => (
            <SidebarLink
              key={item.href}
              href={item.href}
              label={item.label}
              icon={item.icon}
              color={marketColor}
            />
          ))}
          <div className="mt-3 px-2 pb-1 text-2xs uppercase tracking-widest text-text-faint">
            common
          </div>
          <SidebarLink
            href="/settings"
            label={t("nav.settings")}
            icon={Settings}
            color="text-text-secondary"
          />
        </nav>
      </aside>

      {/* Main */}
      <main className="col-span-1 row-span-1 overflow-y-auto bg-bg-base">
        {children}
      </main>
    </div>
  );
}

function SidebarLink({
  href,
  label,
  icon: Icon,
  color,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}) {
  return (
    <Link
      href={href}
      className={cn(
        "group flex items-center gap-2 rounded px-2 py-1.5 text-xs",
        "hover:bg-bg-elevated"
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", color)} />
      <span className="text-text-primary">{label}</span>
    </Link>
  );
}

function MarketSwitch({ active }: { active: "equity" | "crypto" }) {
  return (
    <div className="flex overflow-hidden rounded border border-border-subtle">
      <Link
        href="/equity/pairs"
        className={cn(
          "flex items-center gap-1.5 px-3 py-1 text-xs",
          active === "equity"
            ? "bg-accent-cyan/15 text-accent-cyan"
            : "text-text-secondary hover:bg-bg-elevated"
        )}
      >
        <TrendingUp className="h-3 w-3" />
        {t("nav.equity")}
      </Link>
      <Link
        href="/crypto/pairs"
        className={cn(
          "flex items-center gap-1.5 px-3 py-1 text-xs",
          active === "crypto"
            ? "bg-accent-magenta/15 text-accent-magenta"
            : "text-text-secondary hover:bg-bg-elevated"
        )}
      >
        <Coins className="h-3 w-3" />
        {t("nav.crypto")}
      </Link>
    </div>
  );
}
