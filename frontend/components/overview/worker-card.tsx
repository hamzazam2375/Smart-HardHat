"use client";

import {
  BATTERY_CRITICAL_PCT,
  BATTERY_LOW_PCT,
  CO_URGENT_PPM,
  CO_WARNING_PPM,
  HEAT_WARNING_C,
  STALE_AFTER_S,
  type ActiveAlert,
  type DeviceStatus,
  type Reading,
  type RiskStatus,
} from "@/lib/overview-types";
import { formatAge } from "@/lib/format";
import { Badge, type Tone } from "./badge";
import { EVENT_LABEL } from "./alert-list";

export type Freshness = "current" | "stale" | "never";

export function freshness(d: { receivedAt: string | null }, now: number): Freshness {
  if (!d.receivedAt) return "never";
  return now - Date.parse(d.receivedAt) > STALE_AFTER_S * 1000 ? "stale" : "current";
}

interface Shown {
  text: string;
  note?: string;
  tone?: Tone; // when set, a badge is shown with `note`
}

/** Missing and invalid are distinct states and never shown as a number. */
function showReading(r: Reading, unit: string, digits = 0): Shown {
  if (r.quality === "invalid") return { text: "Invalid", note: "sensor fault", tone: "warning" };
  if (r.quality === "unsupported") return { text: "Not computed", note: "outside formula range" };
  if (r.quality === "missing" || r.value === null) return { text: "No data" };
  return { text: `${r.value.toFixed(digits)} ${unit}` };
}

function coShown(r: Reading): Shown {
  const s = showReading(r, "ppm");
  if (r.quality !== "valid" || r.value === null) return s;
  if (r.value >= CO_URGENT_PPM) return { ...s, note: "urgent", tone: "danger" };
  if (r.value >= CO_WARNING_PPM) return { ...s, note: "warning", tone: "warning" };
  return s;
}

function heatShown(r: Reading): Shown {
  const s = showReading(r, "°C", 1);
  if (r.quality === "valid" && r.value !== null && r.value >= HEAT_WARNING_C) return { ...s, note: "heat warning", tone: "warning" };
  return s;
}

function batteryShown(b: DeviceStatus["battery"]): Shown {
  const s = showReading(b, "%");
  if (b.quality !== "valid" || b.value === null) return s;
  const text = `${s.text}${b.isEstimate ? " (est.)" : ""}`;
  if (b.value <= BATTERY_CRITICAL_PCT) return { text, note: "critical", tone: "danger" };
  if (b.value <= BATTERY_LOW_PCT) return { text, note: "low", tone: "warning" };
  return { text };
}

function motionShown(m: DeviceStatus["motion"]): Shown {
  if (m.quality === "invalid") return { text: "Invalid", note: "fall detection unavailable", tone: "warning" };
  if (m.quality === "missing" || !m.state) return { text: "No data" };
  if (m.state === "still_after_impact") return { text: "Still after impact", note: "fall rule", tone: "danger" };
  if (m.state === "fall_pre_alert") return { text: "Fall pre-alert", note: "15 s countdown", tone: "danger" };
  return { text: "Normal movement" };
}

function gpsShown(g: DeviceStatus["gps"], now: number): Shown {
  if (g.state === "invalid") return { text: "Invalid", note: "GPS fault", tone: "warning" };
  if (g.state === "no_fix") {
    return g.fixAt
      ? { text: "No current outdoor fix", note: `last fix ${formatAge(now - Date.parse(g.fixAt))} ago`, tone: "muted" }
      : { text: "No current outdoor fix" };
  }
  return {
    text: g.lat !== undefined ? `${g.lat.toFixed(4)}, ${g.lon?.toFixed(4)}` : "Fix available",
    note: g.fixAt ? `fix ${formatAge(now - Date.parse(g.fixAt))} ago` : undefined,
    tone: "muted",
  };
}

const RISK_TONE: Record<string, Tone> = { low: "ok", moderate: "warning", high: "danger", critical: "danger" };

function RiskLine({ risk, stale, now }: { risk: RiskStatus; stale: boolean; now: number }) {
  if (risk.state === "unavailable") {
    return (
      <p className="text-sm">
        <span className="text-slate-500">Assessment: </span>
        <Badge tone="muted">Unavailable</Badge> <span className="text-slate-600">{risk.reason}</span>
      </p>
    );
  }
  const level = risk.level[0].toUpperCase() + risk.level.slice(1);
  return (
    <p className="text-sm">
      <span className="text-slate-500">Assessment: </span>
      <Badge tone={stale ? "stale" : RISK_TONE[risk.level]}>{level}</Badge>{" "}
      <span className="text-slate-600">
        {risk.source === "rule_override" ? "rule override" : `advisory, model ${risk.modelVersion}`} ·{" "}
        {formatAge(now - Date.parse(risk.assessedAt))} ago
      </span>
    </p>
  );
}

function Row({ label, shown, stale }: { label: string; shown: Shown; stale: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className={`text-right text-sm font-medium ${stale ? "text-slate-400" : "text-slate-900"}`}>
        {shown.text}
        {shown.note && (
          <span className="ml-1.5">
            {shown.tone && shown.tone !== "muted" && !stale ? (
              <Badge tone={shown.tone}>{shown.note}</Badge>
            ) : (
              <span className="text-xs font-normal text-slate-500">{shown.note}</span>
            )}
          </span>
        )}
      </dd>
    </div>
  );
}

export function WorkerCard({ device, alerts, now }: { device: DeviceStatus; alerts: ActiveAlert[]; now: number }) {
  const fresh = freshness(device, now);
  const stale = fresh !== "current";
  const age = device.receivedAt ? formatAge(now - Date.parse(device.receivedAt)) : null;
  const top = [...alerts].sort((a, b) => a.priority - b.priority)[0];
  const urgent = top && top.priority <= 2;

  return (
    <article
      className={`flex flex-col rounded-xl border bg-white shadow-sm ${
        urgent ? "border-red-300 ring-2 ring-red-200" : stale ? "border-dashed border-slate-300" : "border-slate-200"
      }`}
    >
      <header className="border-b border-slate-100 p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate font-semibold">{device.worker ? device.worker.name : "No worker assigned"}</h3>
            <p className="text-xs text-slate-500">
              {device.worker && <span className="font-mono">{device.worker.code} · </span>}
              <span className="font-mono">{device.label}</span>
            </p>
          </div>
          {fresh === "current" && <Badge tone="ok">Current</Badge>}
          {fresh === "stale" && <Badge tone="stale">Stale</Badge>}
          {fresh === "never" && <Badge tone="muted">Unknown</Badge>}
        </div>
        <p className="mt-2 text-xs text-slate-600">
          {age ? (
            <>
              Last update <span className="font-medium text-slate-800">{age} ago</span>
              {device.timeQuality === "estimated" && " · device time estimated"}
              {device.timeQuality === "unknown" && " · device time unknown"}
            </>
          ) : (
            "This device has never reported."
          )}
        </p>
        {top && (
          <p className="mt-2">
            <Badge tone={top.priority <= 2 ? "danger" : top.priority <= 4 ? "warning" : "info"}>
              {EVENT_LABEL[top.type]} · {top.state === "open" ? "open" : "acknowledged"}
            </Badge>
            {alerts.length > 1 && <span className="ml-1 text-xs text-slate-500">+{alerts.length - 1} more</span>}
          </p>
        )}
      </header>

      {fresh === "never" ? (
        <p className="p-4 text-sm text-slate-500">No readings. Status unknown, not healthy.</p>
      ) : (
        <div className="flex flex-1 flex-col p-4">
          {stale && (
            <p className="mb-2 rounded-md bg-slate-100 px-2 py-1 text-xs text-slate-700">
              Last known values, not current. No update for {age}.
            </p>
          )}
          <dl className="divide-y divide-slate-100">
            <Row label="CO" shown={coShown(device.co)} stale={stale} />
            <Row label="Temperature" shown={showReading(device.temperature, "°C", 1)} stale={stale} />
            <Row label="Humidity" shown={showReading(device.humidity, "%")} stale={stale} />
            <Row label="Heat index" shown={heatShown(device.heatIndex)} stale={stale} />
            <Row label="Motion" shown={motionShown(device.motion)} stale={stale} />
            <Row label="Battery" shown={batteryShown(device.battery)} stale={stale} />
            <Row label="Location" shown={gpsShown(device.gps, now)} stale={stale} />
          </dl>
          <div className="mt-auto pt-3">
            <RiskLine risk={device.risk} stale={stale} now={now} />
          </div>
        </div>
      )}
    </article>
  );
}
