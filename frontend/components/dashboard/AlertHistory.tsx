"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Bell, Trash2 } from "lucide-react";
import {
  clearHistory,
  ensureNotificationPermission,
  readHistory,
  resetCooldown,
  type AlertEvent,
} from "@/lib/alerts";
import { cn, fmtNum } from "@/lib/utils";

// Side panel that mirrors localStorage. Listens for both the cross-tab
// `storage` event and the in-tab `statarb.alerts.update` event the writer
// fires after pushing, so updates show up immediately.

export function AlertHistory() {
  const [items, setItems] = useState<AlertEvent[]>([]);
  const [perm, setPerm] = useState<NotificationPermission>(
    typeof Notification === "undefined" ? "denied" : Notification.permission
  );

  useEffect(() => {
    setItems(readHistory());
    const refresh = () => setItems(readHistory());
    window.addEventListener("storage", refresh);
    window.addEventListener("statarb.alerts.update", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("statarb.alerts.update", refresh);
    };
  }, []);

  async function enableNotifications() {
    const next = await ensureNotificationPermission();
    setPerm(next);
  }

  return (
    <aside className="flex h-full flex-col border-l border-border-subtle bg-bg-panel">
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
        <div className="flex items-center gap-1.5 text-2xs uppercase tracking-widest text-text-secondary">
          <Bell className="h-3 w-3" />
          알림 / Alerts
        </div>
        <button
          onClick={() => {
            clearHistory();
            resetCooldown();
          }}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-2xs text-text-muted hover:bg-bg-elevated hover:text-text-primary"
        >
          <Trash2 className="h-3 w-3" />
          clear
        </button>
      </div>

      {perm !== "granted" && (
        <button
          onClick={enableNotifications}
          className="m-2 rounded border border-accent-cyan/40 bg-accent-cyan/10 px-3 py-1.5 text-2xs uppercase tracking-widest text-accent-cyan hover:bg-accent-cyan/20"
        >
          브라우저 알림 켜기
        </button>
      )}

      <div className="flex-1 overflow-y-auto">
        {items.length === 0 ? (
          <div className="px-3 py-6 text-2xs uppercase tracking-widest text-text-faint">
            no alerts yet · |z| ≥ 2.0
          </div>
        ) : (
          <ul className="divide-y divide-border-subtle">
            {items.map((evt, i) => (
              <AlertRow key={`${evt.id}-${evt.ts}-${i}`} evt={evt} />
            ))}
          </ul>
        )}
      </div>

      <div className="border-t border-border-subtle px-3 py-2 text-2xs uppercase tracking-widest text-text-faint">
        showing latest {items.length} · |z|≥2 warn · |z|≥2.5 crit
      </div>
    </aside>
  );
}

function AlertRow({ evt }: { evt: AlertEvent }) {
  const sevClass =
    evt.severity === "crit"
      ? "border-l-2 border-accent-red bg-accent-red/5"
      : "border-l-2 border-accent-yellow bg-accent-yellow/5";
  const signalClass =
    evt.signal === "short_spread"
      ? "text-accent-red"
      : "text-accent-green";
  const time = new Date(evt.ts).toLocaleTimeString("ko-KR", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  return (
    <li className={cn("px-3 py-2", sevClass)}>
      <Link
        href={`/equity/pairs/${evt.id}`}
        className="block hover:bg-bg-elevated"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <span className="num text-xs font-semibold text-accent-cyan">
              {evt.base}
            </span>
            <span className="text-text-faint">/</span>
            <span className="num text-xs font-semibold text-accent-magenta">
              {evt.quote}
            </span>
          </div>
          <span className="num text-2xs text-text-muted">{time}</span>
        </div>
        <div className="mt-1 flex items-center justify-between text-2xs">
          <span className={cn("font-semibold", signalClass)}>
            {evt.signal === "short_spread" ? "SHORT SPREAD" : "LONG SPREAD"}
          </span>
          <span className="num text-text-primary">
            z = {fmtNum(evt.zscore, 2, true)}
          </span>
        </div>
      </Link>
    </li>
  );
}
