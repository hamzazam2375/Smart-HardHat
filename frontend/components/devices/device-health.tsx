"use client";

// Device health (F26-113 §4.8.6; UC-14, UC-15, UC-18; FR-06, FR-23, FR-26, FR-53).
// Each channel shows its own state and the function it affects, so a maintenance fault is not
// confused with a worker emergency and a missing GPS fix is not read as a CO/motion failure.
// Never-reported devices are "Unknown" and stale ones "Stale", never healthy. Device and gateway
// connectivity are shown separately. Re-fetches every 30 s (INTERIM until SSE).
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Badge, DateTime, type Tone } from "@/components/overview/badge";
import type { Channel, ChannelState, DeviceHealth, DevicesSnapshot } from "@/lib/device-types";
import { formatAge } from "@/lib/format";
import { STALE_AFTER_S } from "@/lib/overview-types";
import { DeviceStateControl, RegisterDeviceForm } from "./device-admin";

const REFRESH_MS = 30_000;

const CHANNEL_BADGE: Record<ChannelState, { label: string; tone: Tone }> = {
  valid: { label: "Valid", tone: "ok" },
  partial: { label: "Partial", tone: "warning" },
  invalid: { label: "Fault", tone: "warning" },
  missing: { label: "No data", tone: "muted" },
  low: { label: "Low", tone: "warning" },
  critical: { label: "Critical", tone: "danger" },
  no_fix: { label: "No fix", tone: "muted" },
};

const CHANNEL_NAME = {
  co: "CO",
  environment: "Temperature / humidity",
  motion: "Motion (fall detection)",
  battery: "Battery",
  gps: "GPS (outdoor)",
} as const;

const DEVICE_STATE: Record<DeviceHealth["state"], { label: string; tone: Tone }> = {
  registered: { label: "Registered", tone: "info" },
  disabled: { label: "Disabled", tone: "muted" },
  retired: { label: "Retired", tone: "muted" },
};

function ChannelRow({ name, ch, stale }: { name: string; ch: Channel; stale: boolean }) {
  const b = CHANNEL_BADGE[ch.state];
  return (
    <div className="py-2">
      <div className="flex items-center justify-between gap-2">
        <dt className="text-sm text-slate-600">{name}</dt>
        <dd>
          <Badge tone={stale ? "stale" : b.tone}>
            {b.label}
            {stale && " (last known)"}
          </Badge>
        </dd>
      </div>
      <p className={`mt-0.5 text-xs ${stale ? "text-slate-400" : "text-slate-700"}`}>{ch.summary}</p>
      {ch.state !== "valid" && ch.affects && (
        <p className="text-xs text-slate-500">
          <span className="font-medium">Affects:</span> {ch.affects}
        </p>
      )}
    </div>
  );
}

function Ago({ iso, now }: { iso: string | null; now: number }) {
  if (!iso) return <span className="text-slate-500">never</span>;
  return (
    <>
      {formatAge(now - Date.parse(iso))} ago{" "}
      <span className="text-xs font-normal text-slate-500">
        (<DateTime iso={iso} />)
      </span>
    </>
  );
}

function DeviceCard({ d, now, isAdmin, activeConfig }: { d: DeviceHealth; now: number; isAdmin: boolean; activeConfig: string | null }) {
  const stale = d.receivedAt ? now - Date.parse(d.receivedAt) > STALE_AFTER_S * 1000 : false;
  const status = d.status === "unknown" ? "unknown" : stale ? "stale" : "current";
  const ds = DEVICE_STATE[d.state];
  const showWorker = "worker" in d;
  const faulty = d.channels
    ? Object.values(d.channels).filter((c) => c.state === "invalid" || c.state === "partial" || c.state === "critical").length
    : 0;

  return (
    <article
      className={`flex flex-col rounded-xl border bg-white shadow-sm ${
        status !== "current" ? "border-dashed border-slate-300" : faulty ? "border-amber-300" : "border-slate-200"
      }`}
    >
      <header className="border-b border-slate-100 p-4">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h3 className="font-mono font-semibold">{d.label}</h3>
            <p className="text-xs text-slate-500">
              radio {d.radioId} · hw {d.hardwareRevision} · fw {d.firmwareVersion}
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            <Badge tone={ds.tone}>{ds.label}</Badge>
            {status === "current" && <Badge tone="ok">Current</Badge>}
            {status === "stale" && <Badge tone="stale">Stale</Badge>}
            {status === "unknown" && <Badge tone="muted">Unknown, never reported</Badge>}
          </div>
        </div>
        {showWorker && (
          <p className="mt-2 text-xs text-slate-600">
            {d.worker ? (
              <>
                Worn by <span className="font-medium text-slate-800">{d.worker.name}</span>{" "}
                <span className="font-mono">{d.worker.code}</span>
              </>
            ) : (
              "No active assignment"
            )}
          </p>
        )}
        {d.openFaults > 0 && (
          <p className="mt-2">
            <Badge tone="warning">
              {d.openFaults} unresolved sensor fault{d.openFaults > 1 ? "s" : ""}
            </Badge>{" "}
            <span className="text-xs text-slate-500">maintenance, not a worker emergency</span>
          </p>
        )}
      </header>

      <div className="flex-1 space-y-3 p-4">
        <dl className="space-y-1 text-sm">
          <div className="flex flex-wrap justify-between gap-x-2">
            <dt className="text-slate-500">Radio last contact</dt>
            <dd className="font-medium">
              <Ago iso={d.lastSeenAt} now={now} />
            </dd>
          </div>
          <div className="flex flex-wrap justify-between gap-x-2">
            <dt className="text-slate-500">Latest accepted status</dt>
            <dd className="font-medium">
              <Ago iso={d.receivedAt} now={now} />
              {d.timeQuality && d.timeQuality !== "trusted" && (
                <span className="block text-right text-xs font-normal text-slate-500">device time {d.timeQuality}</span>
              )}
            </dd>
          </div>
          {d.gateway && (
            <div className="flex flex-wrap justify-between gap-x-2">
              <dt className="text-slate-500">Via gateway</dt>
              <dd className="font-mono">{d.gateway.code}</dd>
            </div>
          )}
        </dl>

        {d.channels ? (
          <>
            {stale && (
              <p className="rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
                No status for more than {STALE_AFTER_S} s. Channel states below are last known, not current.
              </p>
            )}
            <dl className="divide-y divide-slate-100">
              {(Object.keys(CHANNEL_NAME) as (keyof typeof CHANNEL_NAME)[]).map((k) => (
                <ChannelRow key={k} name={CHANNEL_NAME[k]} ch={d.channels![k]} stale={stale} />
              ))}
            </dl>
          </>
        ) : (
          <p className="text-sm text-slate-600">
            No status has been accepted from this hardhat. Its condition is unknown, not healthy.
          </p>
        )}

        <dl className="space-y-1 border-t border-slate-100 pt-3 text-xs">
          <div className="flex flex-wrap justify-between gap-x-2">
            <dt className="text-slate-500">Configuration in last status</dt>
            <dd className="font-mono">
              {d.config ? (
                <>
                  {d.config.version}
                  {activeConfig && d.config.version !== activeConfig && (
                    <span className="ml-1 font-sans">
                      <Badge tone="warning">differs from active {activeConfig}</Badge>
                    </span>
                  )}
                </>
              ) : (
                <span className="font-sans text-slate-500">unknown</span>
              )}
            </dd>
          </div>
          <div className="flex flex-wrap justify-between gap-x-2">
            <dt className="text-slate-500">CO calibration</dt>
            <dd className="text-right">
              {d.calibration ? (
                <>
                  <span className="font-mono">{d.calibration.sensorSerial}</span> · {d.calibration.result}
                  {d.calibration.result !== "pass" && (
                    <span className="ml-1">
                      <Badge tone="warning">{d.calibration.result}</Badge>
                    </span>
                  )}
                  <span className="block text-slate-500">
                    checked <DateTime iso={d.calibration.checkedAt} />
                    {d.calibration.dueAt && (
                      <>
                        {" "}
                        · due <DateTime iso={d.calibration.dueAt} />
                      </>
                    )}
                  </span>
                  {d.calibration.overdue && <Badge tone="warning">calibration overdue</Badge>}
                </>
              ) : (
                <span className="text-slate-500">no calibration record linked</span>
              )}
            </dd>
          </div>
        </dl>
      </div>

      {isAdmin && (
        <footer className="border-t border-slate-100 p-4">
          <DeviceStateControl device={d} />
        </footer>
      )}
    </article>
  );
}

export function DeviceHealthView({ snapshot, isAdmin }: { snapshot: DevicesSnapshot; isAdmin: boolean }) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.parse(snapshot.generatedAt));

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const refresh = setInterval(() => router.refresh(), REFRESH_MS);
    return () => {
      clearInterval(tick);
      clearInterval(refresh);
    };
  }, [router]);

  const inService = snapshot.devices.filter((d) => d.state !== "retired");
  const retired = snapshot.devices.filter((d) => d.state === "retired");
  const activeConfig = snapshot.activeConfig?.version ?? null;

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 md:px-8">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Device health</h1>
          <p className="text-sm text-slate-500">
            Battery, sensor channels, last contact and version references for each hardhat. Device keys are never shown.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <Badge tone="info">Refreshes every 30 s</Badge>
          <span>
            Active configuration:{" "}
            {snapshot.activeConfig ? (
              <span className="font-mono text-slate-800">{snapshot.activeConfig.version}</span>
            ) : (
              <Badge tone="warning">none active</Badge>
            )}
          </span>
        </div>
      </header>

      <section aria-labelledby="gw-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <h2 id="gw-heading" className="font-semibold">
          Gateways <span className="text-xs font-normal text-slate-500">(hardhat → gateway → server path, shown separately)</span>
        </h2>
        {snapshot.gateways.length === 0 ? (
          <p className="mt-2 text-sm text-slate-600">No gateway is registered.</p>
        ) : (
          <ul className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {snapshot.gateways.map((g) => {
              const age = g.lastSeenAt ? now - Date.parse(g.lastSeenAt) : null;
              const online = g.enabled && age !== null && age <= STALE_AFTER_S * 1000;
              return (
                <li key={g.code} className="rounded-lg border border-slate-100 p-3 text-sm">
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
                  <p className="mt-1 text-xs text-slate-600">
                    {age !== null ? `Heartbeat ${formatAge(age)} ago` : "Never seen"} · fw {g.firmware}
                  </p>
                  <p className="text-xs text-slate-600">
                    Backlog {g.queueDepth} · lost {g.lossCount}
                    {g.lossCount > 0 && (
                      <span className="ml-1">
                        <Badge tone="warning">records lost</Badge>
                      </span>
                    )}
                  </p>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {isAdmin && <RegisterDeviceForm />}

      <section aria-labelledby="devices-heading">
        <h2 id="devices-heading" className="mb-3 text-lg font-semibold">
          Hardhats
        </h2>
        {inService.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">No hardhat is registered.</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {inService.map((d) => (
              <DeviceCard key={d.deviceId} d={d} now={now} isAdmin={isAdmin} activeConfig={activeConfig} />
            ))}
          </div>
        )}
      </section>

      {retired.length > 0 && (
        <details className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <summary className="cursor-pointer font-semibold">Retired hardhats ({retired.length})</summary>
          <p className="mt-1 text-xs text-slate-500">Kept so retained history stays identifiable. They cannot send operational data.</p>
          <ul className="mt-2 divide-y divide-slate-100">
            {retired.map((d) => (
              <li key={d.deviceId} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
                <span className="font-mono">{d.label}</span>
                <span className="text-xs text-slate-500">
                  radio {d.radioId} · fw {d.firmwareVersion} · last contact{" "}
                  {d.lastSeenAt ? <DateTime iso={d.lastSeenAt} /> : "never"}
                </span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
