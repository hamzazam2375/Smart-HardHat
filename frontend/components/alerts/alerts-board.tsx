"use client";

// Active alert list (UC-05, UC-11; FR-32). Unresolved events from GET /api/events, highest
// priority first; each opens the alert detail. Resolved events are in History.
// Re-fetches every 30 s (INTERIM until SSE /api/stream).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AlertList } from "@/components/overview/alert-list";
import { Badge, Clock } from "@/components/overview/badge";
import type { ActiveAlert } from "@/lib/overview-types";

const REFRESH_MS = 30_000;

const FILTERS = {
  all: { label: "All", test: () => true },
  urgent: { label: "Emergencies and pre-alerts", test: (a: ActiveAlert) => a.priority <= 2 },
  warnings: { label: "Faults and warnings", test: (a: ActiveAlert) => a.priority === 3 || a.priority === 4 },
  battery: { label: "Battery", test: (a: ActiveAlert) => a.priority === 5 },
  open: { label: "Open (no response yet)", test: (a: ActiveAlert) => a.state === "open" },
} as const;
type FilterKey = keyof typeof FILTERS;

export function AlertsBoard({ alerts, generatedAt }: { alerts: ActiveAlert[]; generatedAt: string }) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.parse(generatedAt));
  const [filter, setFilter] = useState<FilterKey>("all");

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const refresh = setInterval(() => router.refresh(), REFRESH_MS);
    return () => {
      clearInterval(tick);
      clearInterval(refresh);
    };
  }, [router]);

  const shown = alerts.filter(FILTERS[filter].test);

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-6 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Alerts</h1>
          <p className="text-sm text-slate-500">
            Unresolved events. Resolved ones are in{" "}
            <Link href="/history?state=resolved" className="underline">
              History
            </Link>
            .
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <Badge tone="info">Refreshes every 30 s</Badge>
          <span>
            Data as of <Clock iso={generatedAt} />
          </span>
        </div>
      </header>

      <div role="group" aria-label="Filter alerts" className="flex flex-wrap gap-2">
        {(Object.keys(FILTERS) as FilterKey[]).map((k) => {
          const count = alerts.filter(FILTERS[k].test).length;
          return (
            <button
              key={k}
              type="button"
              aria-pressed={filter === k}
              onClick={() => setFilter(k)}
              className={`rounded-full px-3 py-1 text-sm ${
                filter === k ? "bg-slate-900 text-white" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
              }`}
            >
              {FILTERS[k].label} <span className="tabular-nums">({count})</span>
            </button>
          );
        })}
      </div>

      <AlertList alerts={shown} now={now} />
    </div>
  );
}
