import { cn, fmtNum } from "@/lib/utils";
import type { VECMRow } from "@/lib/mock";

// VECM lag coefficients with their p-values for both legs as dependent
// variable, exactly the screenshot layout. P-values under 0.05 are
// highlighted neon-green; the coefficients themselves stay neutral.
export function VECMTable({
  rows,
  base,
  quote,
}: {
  rows: VECMRow[];
  base: string;
  quote: string;
}) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-text-muted">
          <th className="px-2 py-1 text-left font-normal">term</th>
          <th className="px-2 py-1 text-right font-normal text-accent-cyan">
            {base} (as dependent)
          </th>
          <th className="px-2 py-1 text-right font-normal text-accent-magenta">
            {quote} (as dependent)
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-border-subtle">
            <td className="px-2 py-1.5 text-text-secondary">{r.term}</td>
            <td className="px-2 py-1.5 text-right">
              <Coef coef={r.baseCoef} pvalue={r.basePValue} />
            </td>
            <td className="px-2 py-1.5 text-right">
              <Coef coef={r.quoteCoef} pvalue={r.quotePValue} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Coef({ coef, pvalue }: { coef: number; pvalue: number }) {
  const significant = pvalue < 0.05;
  return (
    <span className="num">
      <span className={cn(significant ? "text-accent-green" : "text-text-primary")}>
        {fmtNum(coef, 2)}
      </span>
      <span className="ml-1 text-2xs text-text-muted">
        (p={fmtNum(pvalue, 2)})
      </span>
    </span>
  );
}
