import { Construction } from "lucide-react";

// Skeleton page for sections that exist in navigation but aren't built yet.
// Same shell + a clearly-marked "coming soon" block, so the navigation
// structure works end-to-end while we fill the dashboards in one by one.
export function Placeholder({
  title,
  subtitle,
  note,
}: {
  title: string;
  subtitle?: string;
  note?: string;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-24 text-center">
      <Construction className="h-8 w-8 text-text-muted" />
      <h1 className="mt-4 text-xl font-semibold text-text-primary">{title}</h1>
      {subtitle && (
        <div className="mt-1 text-2xs uppercase tracking-widest text-text-muted">
          {subtitle}
        </div>
      )}
      {note && (
        <p className="mt-4 max-w-md text-sm text-text-secondary">{note}</p>
      )}
    </div>
  );
}
