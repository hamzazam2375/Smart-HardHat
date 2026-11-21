// Status badge: colour + symbol + text, so meaning never depends on colour alone (FR-33).
export type Tone = "danger" | "warning" | "ok" | "info" | "muted" | "stale";

const TONES: Record<Tone, { cls: string; symbol: string }> = {
  danger: { cls: "bg-red-100 text-red-800 ring-red-200", symbol: "▲" },
  warning: { cls: "bg-amber-100 text-amber-900 ring-amber-200", symbol: "!" },
  ok: { cls: "bg-emerald-50 text-emerald-800 ring-emerald-200", symbol: "●" },
  info: { cls: "bg-sky-50 text-sky-800 ring-sky-200", symbol: "i" },
  muted: { cls: "bg-slate-100 text-slate-700 ring-slate-200", symbol: "–" },
  stale: { cls: "bg-slate-200 text-slate-800 ring-slate-300", symbol: "◷" },
};

export function Badge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  const t = TONES[tone];
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${t.cls}`}>
      <span aria-hidden="true" className="font-bold">
        {t.symbol}
      </span>
      {children}
    </span>
  );
}

/** Wall-clock time; server and browser may differ in time zone, so skip the hydration check. */
export function Clock({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} suppressHydrationWarning>
      {new Date(iso).toLocaleTimeString("en-GB", { hour12: false })}
    </time>
  );
}
