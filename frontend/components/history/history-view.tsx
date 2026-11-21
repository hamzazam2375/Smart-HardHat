"use client";

// Retained history with filters (F26-113 §4.8.5; UC-13; FR-37). The range is chosen in the
// browser's local time and sent as UTC ISO timestamps, so the time-zone conversion is explicit
// and cannot move an event outside the chosen range. Filters live in the URL (shareable, back
// button works). A cancelled pre-alert stays distinct from a possible fall.
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useSyncExternalStore } from "react";
import { EVENT_LABEL, PRIORITY } from "@/components/overview/alert-list";
import { Badge, DateTime, type Tone } from "@/components/overview/badge";
import { INPUT_CLS } from "@/components/forms";
import type { WorkflowState } from "@/lib/alert-types";
import type { HistoryItem, HistoryPage, HistoryQuery } from "@/lib/history-types";
import type { EventType } from "@/lib/overview-types";

const STATE_BADGE: Record<WorkflowState, { label: string; tone: Tone }> = {
  open: { label: "Open", tone: "danger" },
  acknowledged: { label: "Acknowledged", tone: "info" },
  resolved: { label: "Resolved", tone: "ok" },
};

// Outcome wording keeps the two motion-rule results apart.
const TYPE_NOTE: Partial<Record<EventType, string>> = {
  cancellation: "worker cancelled within 15 s",
  possible_fall: "countdown expired, not cancelled",
};

const TYPE_OPTIONS: EventType[] = [
  "sos",
  "possible_fall",
  "cancellation",
  "co_urgent",
  "co_warning",
  "heat_warning",
  "sensor_fault",
  "battery_low",
  "battery_critical",
];

const noop = () => () => {};
/** true only after hydration, so local-time values never mismatch the server render. */
function useMounted() {
  return useSyncExternalStore(noop, () => true, () => false);
}

/** ISO -> value for <input type="datetime-local"> in the browser's time zone. */
function toLocalInput(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

function tzLabel(): string {
  const off = -new Date().getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const a = Math.abs(off);
  return `UTC${sign}${String(Math.floor(a / 60)).padStart(2, "0")}:${String(a % 60).padStart(2, "0")}`;
}

function Filters({ query, page }: { query: HistoryQuery; page: HistoryPage | null }) {
  const router = useRouter();
  const mounted = useMounted();

  function go(next: Record<string, string>) {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) if (v) qs.set(k, v);
    router.push(`/history${qs.size ? `?${qs}` : ""}`);
  }

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const local = (k: string) => {
      const v = String(f.get(k) ?? "");
      return v ? new Date(v).toISOString() : ""; // local wall time -> explicit UTC instant
    };
    go({
      from: local("from"),
      to: local("to"),
      workerId: String(f.get("workerId") ?? ""),
      deviceId: String(f.get("deviceId") ?? ""),
      type: String(f.get("type") ?? ""),
      state: String(f.get("state") ?? ""),
    });
  }

  function preset(hours: number | null) {
    const keep = { workerId: query.workerId ?? "", deviceId: query.deviceId ?? "", type: query.type ?? "", state: query.state ?? "" };
    go({ ...keep, from: hours ? new Date(Date.now() - hours * 3_600_000).toISOString() : "" });
  }

  const opts = page?.options;
  return (
    <section aria-labelledby="filters-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="filters-heading" className="font-semibold">
          Filters
        </h2>
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-slate-500">Quick range:</span>
          <button type="button" onClick={() => preset(24)} className="text-slate-800 underline-offset-2 hover:underline">
            Last 24 h
          </button>
          <button type="button" onClick={() => preset(24 * 7)} className="text-slate-800 underline-offset-2 hover:underline">
            Last 7 days
          </button>
          <button type="button" onClick={() => preset(null)} className="text-slate-800 underline-offset-2 hover:underline">
            All retained (30 days)
          </button>
        </div>
      </div>
      {/* key: remount once mounted so datetime defaults are in the browser's local time */}
      <form key={mounted ? `m-${JSON.stringify(query)}` : "ssr"} onSubmit={onSubmit} className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
        <div className="space-y-1 lg:col-span-1">
          <label htmlFor="f-from" className="block text-xs font-medium text-slate-700">
            Received from {mounted && <span className="font-normal text-slate-500">({tzLabel()})</span>}
          </label>
          <input id="f-from" name="from" type="datetime-local" defaultValue={mounted ? toLocalInput(query.from) : ""} className={INPUT_CLS} />
        </div>
        <div className="space-y-1 lg:col-span-1">
          <label htmlFor="f-to" className="block text-xs font-medium text-slate-700">
            Received until
          </label>
          <input id="f-to" name="to" type="datetime-local" defaultValue={mounted ? toLocalInput(query.to) : ""} className={INPUT_CLS} />
        </div>
        <div className="space-y-1">
          <label htmlFor="f-worker" className="block text-xs font-medium text-slate-700">
            Worker
          </label>
          <select id="f-worker" name="workerId" defaultValue={query.workerId ?? ""} className={INPUT_CLS}>
            <option value="">All workers</option>
            {opts?.workers.map((w) => (
              <option key={w.id} value={w.id}>
                {w.code} · {w.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="f-device" className="block text-xs font-medium text-slate-700">
            Hardhat
          </label>
          <select id="f-device" name="deviceId" defaultValue={query.deviceId ?? ""} className={INPUT_CLS}>
            <option value="">All hardhats</option>
            {opts?.devices.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
                {d.state !== "registered" ? ` (${d.state})` : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="f-type" className="block text-xs font-medium text-slate-700">
            Event type
          </label>
          <select id="f-type" name="type" defaultValue={query.type ?? ""} className={INPUT_CLS}>
            <option value="">All types</option>
            {TYPE_OPTIONS.map((t) => (
              <option key={t} value={t}>
                {EVENT_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <label htmlFor="f-state" className="block text-xs font-medium text-slate-700">
            Response state
          </label>
          <select id="f-state" name="state" defaultValue={query.state ?? ""} className={INPUT_CLS}>
            <option value="">All states</option>
            <option value="open">Open</option>
            <option value="acknowledged">Acknowledged</option>
            <option value="resolved">Resolved</option>
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-6">
          <button type="submit" className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800">
            Apply filters
          </button>
          <Link href="/history" className="text-sm text-slate-600 hover:underline">
            Clear
          </Link>
        </div>
      </form>
    </section>
  );
}

function Row({ item }: { item: HistoryItem }) {
  const s = STATE_BADGE[item.state];
  const p = PRIORITY[item.priority];
  return (
    <tr className="align-top">
      <td className="px-3 py-2 text-sm whitespace-nowrap">
        <DateTime iso={item.receivedAt} />
      </td>
      <td className="px-3 py-2 text-sm whitespace-nowrap">
        {item.detectedAt ? (
          <>
            <DateTime iso={item.detectedAt} />
            {item.timeQuality === "estimated" && <span className="block text-xs text-slate-500">estimated</span>}
          </>
        ) : (
          <span className="text-amber-800">unknown</span>
        )}
      </td>
      <td className="px-3 py-2 text-sm">
        <span className="flex flex-wrap items-center gap-1.5">
          <Badge tone={p.tone}>P{item.priority}</Badge>
          <span className="font-medium">{EVENT_LABEL[item.type]}</span>
        </span>
        {TYPE_NOTE[item.type] && <span className="block text-xs text-slate-500">{TYPE_NOTE[item.type]}</span>}
      </td>
      <td className="px-3 py-2 text-sm">
        {item.worker ? (
          <>
            {item.worker.name}
            <span className="block font-mono text-xs text-slate-500">{item.worker.code}</span>
          </>
        ) : (
          <span className="text-slate-600">unknown (assignment uncertain)</span>
        )}
      </td>
      <td className="px-3 py-2 font-mono text-sm">{item.deviceLabel}</td>
      <td className="px-3 py-2 text-sm">
        <Badge tone={s.tone}>{s.label}</Badge>
        {item.resolved && <span className="block text-xs text-slate-500">by {item.resolved.by}</span>}
      </td>
      <td className="px-3 py-2 text-sm">
        <Link href={`/alerts/${item.eventId}`} className="font-medium text-slate-900 underline-offset-2 hover:underline">
          Open
        </Link>
      </td>
    </tr>
  );
}

export function HistoryView({ page, error, query }: { page: HistoryPage | null; error: string | null; query: HistoryQuery }) {
  const pageNo = Math.max(1, Number(query.page) || 1);
  const nextHref = (() => {
    if (!page?.nextCursor) return null;
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v && k !== "cursor" && k !== "page") qs.set(k, v);
    qs.set("cursor", page.nextCursor);
    qs.set("page", String(pageNo + 1));
    return `/history?${qs}`;
  })();
  const firstHref = (() => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(query)) if (v && k !== "cursor" && k !== "page") qs.set(k, v);
    return `/history${qs.size ? `?${qs}` : ""}`;
  })();

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 md:px-8">
      <header>
        <h1 className="text-2xl font-semibold">History</h1>
        <p className="text-sm text-slate-500">
          Events kept within the 30-day retention period. Older identifiable records are deleted and cannot be shown.
        </p>
      </header>

      <Filters query={query} page={page} />

      {error ? (
        <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          ▲ {error}
        </p>
      ) : (
        page && (
          <section aria-labelledby="results-heading" className="rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2 p-4 pb-2">
              <h2 id="results-heading" className="font-semibold">
                Results <span className="text-sm font-normal text-slate-500">· page {pageNo}</span>
              </h2>
              <p className="text-xs text-slate-600">
                Received <DateTime iso={page.range.from} /> to <DateTime iso={page.range.to} /> (shown in your local
                time; the range applies to server receipt time)
              </p>
            </div>
            {page.range.clamped && (
              <p className="mx-4 mb-2 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
                The start was moved to the retention limit (<DateTime iso={page.range.retentionStart} />). Older history is
                not retained.
              </p>
            )}
            {page.items.length === 0 ? (
              <p className="px-4 pb-4 text-sm text-slate-600">
                No retained records match these filters. This is an empty result, not a server failure.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-100">
                  <thead>
                    <tr>
                      {["Received", "Detected", "Event", "Worker", "Hardhat", "Response", ""].map((h, i) => (
                        <th key={i} scope="col" className="px-3 py-2 text-left text-xs font-medium tracking-wide text-slate-500 uppercase">
                          {h || <span className="sr-only">Open</span>}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {page.items.map((item) => (
                      <Row key={item.eventId} item={item} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <nav aria-label="Pagination" className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 p-4 text-sm">
              {pageNo > 1 ? (
                <Link href={firstHref} className="text-slate-700 hover:underline">
                  ← First page
                </Link>
              ) : (
                <span />
              )}
              {nextHref ? (
                <Link href={nextHref} className="font-medium text-slate-900 hover:underline">
                  Older results →
                </Link>
              ) : (
                <span className="text-xs text-slate-500">End of results</span>
              )}
            </nav>
          </section>
        )
      )}
    </div>
  );
}
