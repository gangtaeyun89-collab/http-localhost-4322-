import Link from "next/link";
import { ArrowRight, Coins, TrendingUp } from "lucide-react";
import { t } from "@/lib/i18n";

export default function HomePage() {
  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="border-b border-border-subtle bg-bg-panel">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-accent-green text-accent-green shadow-[0_0_8px_currentColor]" />
            <span className="text-sm font-semibold tracking-wide">
              {t("app.title")}
            </span>
          </div>
          <div className="text-2xs uppercase tracking-widest text-text-muted">
            v0.1 · paper trading
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-16">
        <h1 className="text-4xl font-semibold leading-tight">
          {t("home.heading")}
        </h1>
        <p className="mt-4 max-w-2xl text-base text-text-secondary">
          {t("home.lede")}
        </p>

        <div className="mt-12 grid gap-4 md:grid-cols-2">
          <MarketCard
            href="/equity/pairs"
            accent="cyan"
            icon={<TrendingUp className="h-5 w-5" />}
            title={t("nav.equity")}
            description={t("home.equityDesc")}
            cta={t("home.equityCta")}
          />
          <MarketCard
            href="/crypto/pairs"
            accent="magenta"
            icon={<Coins className="h-5 w-5" />}
            title={t("nav.crypto")}
            description={t("home.cryptoDesc")}
            cta={t("home.cryptoCta")}
          />
        </div>

        <div className="mt-16 grid grid-cols-2 gap-px border border-border-subtle bg-border-subtle md:grid-cols-4">
          {[
            { k: "공적분 검증", v: "Johansen · Engle-Granger · FDR" },
            { k: "신호 엔진", v: "Z-Score · OU · Kalman" },
            { k: "리스크", v: "Vol-Target · Fractional Kelly" },
            { k: "실행", v: "IBKR Combo · ccxt Spot" },
          ].map((it) => (
            <div key={it.k} className="bg-bg-panel p-4">
              <div className="text-2xs uppercase tracking-widest text-text-muted">
                {it.k}
              </div>
              <div className="mt-1 text-xs text-text-primary">{it.v}</div>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}

function MarketCard({
  href,
  accent,
  icon,
  title,
  description,
  cta,
}: {
  href: string;
  accent: "cyan" | "magenta";
  icon: React.ReactNode;
  title: string;
  description: string;
  cta: string;
}) {
  const color = accent === "cyan" ? "text-accent-cyan" : "text-accent-magenta";
  const ring =
    accent === "cyan"
      ? "hover:border-accent-cyan/40 hover:shadow-[0_0_24px_-12px_#00d4ff]"
      : "hover:border-accent-magenta/40 hover:shadow-[0_0_24px_-12px_#ff2ad4]";
  return (
    <Link
      href={href}
      className={`group flex flex-col gap-3 border border-border-subtle bg-bg-panel p-6 transition ${ring}`}
    >
      <div className={`flex items-center gap-2 ${color}`}>
        {icon}
        <h2 className="text-base font-semibold">{title}</h2>
      </div>
      <p className="text-sm text-text-secondary">{description}</p>
      <div className={`mt-2 flex items-center gap-1.5 text-sm ${color}`}>
        {cta}
        <ArrowRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5" />
      </div>
    </Link>
  );
}
