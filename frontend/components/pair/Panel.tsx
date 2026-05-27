import { cn } from "@/lib/utils";

// Outer container shared by every chart panel. Title strip on top, optional
// right-side hint (units, badges), then the chart slot below. Border + grid
// background mimic the screenshots.
export function Panel({
  title,
  hint,
  children,
  className,
}: {
  title: React.ReactNode;
  hint?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col border border-border-subtle bg-bg-panel",
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
        <div className="text-2xs uppercase tracking-widest text-text-secondary">
          {title}
        </div>
        {hint && (
          <div className="text-2xs uppercase tracking-widest text-text-muted">
            {hint}
          </div>
        )}
      </div>
      <div className="chart-grid-bg flex-1 p-2">{children}</div>
    </div>
  );
}
