import Link from "next/link";
import { Check } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { mockPairList } from "@/lib/mock";
import { cn, fmtNum, fmtPct } from "@/lib/utils";
import { t } from "@/lib/i18n";

// Pair scoreboard. Shape mirrors the right-most 'dependency' column in the
// reference screenshots: dense numeric rows, neon-green for strong values,
// click any row to drop into the per-pair workbench.

export default function EquityPairsPage() {
  return (
    <AppShell market="equity">
      <PageHeader />
      <div className="border-y border-border-subtle bg-bg-panel">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted">
              <Th>페어 / Pair</Th>
              <Th>산업 / Industry</Th>
              <Th right>p-value</Th>
              <Th right>half-life</Th>
              <Th right>corr</Th>
              <Th right>train Sharpe</Th>
              <Th right>OOS Sharpe</Th>
              <Th right>profile</Th>
            </tr>
          </thead>
          <tbody>
            {mockPairList.map((row) => (
              <tr
                key={row.id}
                className="border-t border-border-subtle hover:bg-bg-elevated"
              >
                <Td>
                  <Link
                    href={`/equity/pairs/${row.id}`}
                    className="flex items-center gap-2"
                  >
                    <span className="num font-semibold text-accent-cyan">
                      {row.base}
                    </span>
                    <span className="text-text-faint">/</span>
                    <span className="num font-semibold text-accent-magenta">
                      {row.quote}
                    </span>
                  </Link>
                </Td>
                <Td>
                  <span className="text-text-secondary">{row.industry}</span>
                </Td>
                <Td right>
                  <span className="num">{fmtNum(row.cointPValue, 4)}</span>
                </Td>
                <Td right>
                  <span className="num">{fmtNum(row.halfLife, 1)}</span>
                </Td>
                <Td right>
                  <span
                    className={cn(
                      "num",
                      row.corr > 0.8 ? "text-accent-green" : "text-text-primary"
                    )}
                  >
                    {fmtPct(row.corr, 1, false)}
                  </span>
                </Td>
                <Td right>
                  <span
                    className={cn(
                      "num",
                      row.trainSharpe > 0 ? "text-accent-green" : "text-accent-red"
                    )}
                  >
                    {fmtNum(row.trainSharpe, 2, true)}
                  </span>
                </Td>
                <Td right>
                  <span
                    className={cn(
                      "num font-semibold",
                      row.oosSharpe > 0.8
                        ? "text-accent-green"
                        : row.oosSharpe > 0
                        ? "text-text-primary"
                        : "text-accent-red"
                    )}
                  >
                    {fmtNum(row.oosSharpe, 2, true)}
                  </span>
                </Td>
                <Td right>
                  <ProfileBadge passed={row.oosSharpe > 0.3} />
                </Td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-3 text-2xs uppercase tracking-widest text-text-muted">
        {mockPairList.length} pair(s) · sorted by OOS Sharpe · mock data
      </div>
    </AppShell>
  );
}

function PageHeader() {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle bg-bg-panel px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-text-muted">
          {t("nav.pairs")}
        </div>
        <span className="text-text-faint">/</span>
        <span className="text-xs text-text-secondary">
          {t("section.pairList")}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <button className="rounded border border-border-subtle px-3 py-1 text-2xs uppercase tracking-widest text-text-secondary hover:bg-bg-elevated">
          새 페어 발견
        </button>
        <button className="rounded border border-accent-cyan/40 bg-accent-cyan/10 px-3 py-1 text-2xs uppercase tracking-widest text-accent-cyan hover:bg-accent-cyan/20">
          백테스트 실행
        </button>
      </div>
    </div>
  );
}

function Th({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <th
      className={cn(
        "px-3 py-2 font-normal uppercase tracking-widest text-2xs",
        right ? "text-right" : "text-left"
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <td className={cn("px-3 py-2", right ? "text-right" : "text-left")}>
      {children}
    </td>
  );
}

function ProfileBadge({ passed }: { passed: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs",
        passed
          ? "bg-accent-green/10 text-accent-green"
          : "bg-bg-elevated text-text-muted"
      )}
    >
      <Check className="h-3 w-3" />
      profile
    </span>
  );
}
