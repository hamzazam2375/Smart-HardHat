"use client";

// Supervisor overview (F26-113 §4.8.2; UC-04, UC-05, UC-12, UC-15; FR-31..FR-34).
// Renders the server snapshot (GET /api/status + /api/events), ticks once a second so ages
// and the stale state stay correct, and re-fetches from the server every 30 s.
// INTERIM: polling until SSE (/api/stream) exists.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { OverviewSnapshot } from "@/lib/overview-types";
import { formatAge } from "@/lib/format";
import { AlertList } from "./alert-list";
import { Badge, Clock } from "./badge";
import { WorkerCard, freshness } from "./worker-card";

const REFRESH_MS = 30_000;

function Tile({ label, value, sub, tone = "default" }: { label: string; value: string; sub?: string; tone?: "default" | "danger" | "warning" }) {
  const ring = tone === "danger" ? "border-red-300 bg-red-50" : tone === "warning" ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white";
  return (
    <div className={`rounded-xl border p-4 shadow-sm ${ring}`}>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-600">{sub}</p>}
    </div>
  );
}

export function OverviewDashboard({ initial: snap }: { initial: OverviewSnapshot }) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.parse(snap.generatedAt));

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const refresh = setInterval(() => router.refresh(), REFRESH_MS);
    return () => {
      clearInterval(tick);
      clearInterval(refresh);
    };
  }, [router]);

  const assigned = snap.devices.filter((d) => d.worker);
  const unassigned = snap.devices.filter((d) => !d.worker);
  const urgent = snap.alerts.filter((a) => a.priority <= 2);
  const urgentOpen = urgent.filter((a) => a.state === "open");
  const others = snap.alerts.length - urgent.length;
  const staleCount = assigned.filter((d) => freshness(d, now) !== "current").length;
  const latest = Math.max(0, ...snap.devices.map((d) => (d.receivedAt ? Date.parse(d.receivedAt) : 0)));

  return (
    <div className="mx-auto max-w-7xl space-y-8 px-4 py-6 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Overview</h1>
          <p className="text-sm text-slate-500">{snap.site} · current shift</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <Badge tone="info">Refreshes every 30 s</Badge>
          <span>
            Data as of <Clock iso={snap.generatedAt} />
          </span>
        </div>
      </header>

      <section aria-label="Summary" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile label="Assigned workers" value={String(assigned.length)} sub={staleCount ? `${staleCount} not current (stale)` : "all current"} />
        <Tile
          label="Urgent alerts"
          value={String(urgent.length)}
          sub={urgent.length ? `${urgentOpen.length} open, ${urgent.length - urgentOpen.length} acknowledged` : "none unresolved"}
          tone={urgent.length ? "danger" : "default"}
        />
        <Tile label="Warnings and faults" value={String(others)} sub="unresolved, lower priority" tone={others ? "warning" : "default"} />
        <Tile label="Last update" value={latest ? `${formatAge(now - latest)} ago` : "None"} sub="newest accepted status" />
      </section>

      <AlertList alerts={snap.alerts} now={now} />

      <section aria-labelledby="workers-heading">
        <div className="mb-3 flex items-baseline justify-between gap-2">
          <h2 id="workers-heading" className="text-lg font-semibold">
            Workers on shift
          </h2>
          <p className="text-xs text-slate-500">Stale after 180 s without an update</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {assigned.map((d) => (
            <WorkerCard key={d.deviceId} device={d} now={now} alerts={snap.alerts.filter((a) => a.deviceLabel === d.label)} />
          ))}
        </div>
      </section>

      <section aria-labelledby="system-heading" className="grid gap-4 lg:grid-cols-3">
        <h2 id="system-heading" className="sr-only">
          System status
        </h2>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="font-semibold">Gateways</h3>
          <ul className="mt-2 divide-y divide-slate-100">
            {snap.gateways.map((g) => {
              const age = g.lastSeenAt ? now - Date.parse(g.lastSeenAt) : null;
              const online = g.enabled && age !== null && age <= 180_000;
              return (
                <li key={g.code} className="py-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono">{g.code}</span>
                    {!g.enabled ? (
                      <Badge tone="muted">Disabled</Badge>
                    ) : online ? (
                      <Badge tone="ok">Online</Badge>
                    ) : (
                      <Badge tone="stale">Not heard</Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {age !== null ? `Last seen ${formatAge(age)} ago` : "Never seen"} · queue {g.queueDepth} · lost{" "}
                    {g.lossCount} · fw {g.firmware}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="font-semibold">Risk model</h3>
          {snap.model.state === "active" ? (
            <div className="mt-2 space-y-1 text-sm">
              <p>
                <Badge tone="ok">Active</Badge> <span className="font-mono">{snap.model.version}</span>
              </p>
              <p className="text-xs text-slate-500">
                Activated <Clock iso={snap.model.activatedAt} /> ({formatAge(now - Date.parse(snap.model.activatedAt))} ago)
              </p>
            </div>
          ) : (
            <p className="mt-2 text-sm">
              <Badge tone="muted">Unavailable</Badge> <span className="text-slate-600">{snap.model.reason}</span>
            </p>
          )}
          <p className="mt-3 text-xs text-slate-500">
            Assessments are advisory only. SOS, fall and CO rules run on the hardhat and always take priority.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h3 className="font-semibold">Unassigned devices</h3>
          <ul className="mt-2 divide-y divide-slate-100">
            {unassigned.map((d) => {
              const f = freshness(d, now);
              return (
                <li key={d.deviceId} className="flex items-center justify-between gap-2 py-2 text-sm">
                  <span>
                    <span className="font-mono">{d.label}</span>
                    <span className="block text-xs text-slate-500">
                      {d.receivedAt ? `Last update ${formatAge(now - Date.parse(d.receivedAt))} ago` : "Never reported"}
                      {d.battery.value !== null && ` · battery ${d.battery.value}%`}
                    </span>
                  </span>
                  {f === "current" && <Badge tone="ok">Current</Badge>}
                  {f === "stale" && <Badge tone="stale">Stale</Badge>}
                  {f === "never" && <Badge tone="muted">Unknown</Badge>}
                </li>
              );
            })}
          </ul>
        </div>
      </section>
    </div>
  );
}
