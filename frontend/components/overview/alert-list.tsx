"use client";

import type { ActiveAlert, EventType } from "@/lib/overview-types";
import { formatAge } from "@/lib/format";
import { Badge, Clock, type Tone } from "./badge";

export const EVENT_LABEL: Record<EventType, string> = {
  sos: "SOS",
  possible_fall: "Possible fall",
  fall_pre_alert: "Fall pre-alert",
  co_urgent: "CO emergency",
  co_warning: "CO warning",
  sensor_fault: "Sensor fault",
  heat_warning: "Heat warning",
  battery_low: "Low battery",
  battery_critical: "Critical battery",
};

const PRIORITY: Record<number, { label: string; tone: Tone; border: string }> = {
  1: { label: "Emergency", tone: "danger", border: "border-l-red-600" },
  2: { label: "Fall pre-alert", tone: "danger", border: "border-l-red-400" },
  3: { label: "Sensor fault", tone: "warning", border: "border-l-amber-500" },
  4: { label: "Warning", tone: "warning", border: "border-l-amber-400" },
  5: { label: "Battery", tone: "info", border: "border-l-sky-400" },
};

function AlertRow({ alert, now }: { alert: ActiveAlert; now: number }) {
  const p = PRIORITY[alert.priority];
  return (
    <li className={`rounded-lg border border-l-4 border-slate-200 bg-white p-4 shadow-sm ${p.border}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={p.tone}>P{alert.priority} · {p.label}</Badge>
        <h3 className="text-base font-semibold">{EVENT_LABEL[alert.type]}</h3>
        <span className="font-mono text-xs text-slate-500">{alert.code}</span>
        <span className="ml-auto">
          {alert.state === "open" ? (
            <Badge tone="danger">Open, needs response</Badge>
          ) : (
            <Badge tone="info">Acknowledged, not resolved</Badge>
          )}
        </span>
      </div>

      <p className="mt-2 text-sm">
        <span className="font-medium">{alert.worker ? alert.worker.name : "Worker unknown (assignment uncertain)"}</span>
        <span className="text-slate-500"> · {alert.deviceLabel}</span>
      </p>
      <p className="mt-1 text-sm text-slate-700">{alert.detail}</p>

      <dl className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-slate-600">
        <div>
          <dt className="inline">Detected: </dt>
          <dd className="inline font-medium text-slate-800">
            {alert.detectedAt ? (
              <>
                <Clock iso={alert.detectedAt} /> ({formatAge(now - Date.parse(alert.detectedAt))} ago)
                {alert.timeQuality === "estimated" && " · estimated time"}
              </>
            ) : (
              "time unknown"
            )}
          </dd>
        </div>
        <div>
          <dt className="inline">Received by server: </dt>
          <dd className="inline font-medium text-slate-800">
            <Clock iso={alert.receivedAt} />
          </dd>
        </div>
        {alert.supervisorAck && (
          <div>
            <dt className="inline">Supervisor ack: </dt>
            <dd className="inline font-medium text-slate-800">
              {alert.supervisorAck.by} at <Clock iso={alert.supervisorAck.at} />
            </dd>
          </div>
        )}
        <div>
          <dt className="inline">On hardhat: </dt>
          <dd className="inline font-medium text-slate-800">
            {alert.physicalAckAt ? (
              <>
                worker acknowledged at <Clock iso={alert.physicalAckAt} />
              </>
            ) : (
              "no physical acknowledgment recorded"
            )}
          </dd>
        </div>
      </dl>
    </li>
  );
}

export function AlertList({ alerts, now }: { alerts: ActiveAlert[]; now: number }) {
  const sorted = [...alerts].sort(
    (a, b) =>
      a.priority - b.priority ||
      (a.state === b.state ? 0 : a.state === "open" ? -1 : 1) ||
      Date.parse(b.receivedAt) - Date.parse(a.receivedAt),
  );

  return (
    <section aria-labelledby="alerts-heading">
      <div className="mb-3 flex items-baseline justify-between gap-2">
        <h2 id="alerts-heading" className="text-lg font-semibold">
          Active alerts
        </h2>
        <p className="text-xs text-slate-500">Open and acknowledged events not yet resolved</p>
      </div>
      {sorted.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600">
          No unresolved alerts from accepted data. This does not cover devices that are stale or not reporting.
        </p>
      ) : (
        <ul className="space-y-3">
          {sorted.map((a) => (
            <AlertRow key={a.eventId} alert={a} now={now} />
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-slate-500">
        Acknowledging an alert on the dashboard does not silence the hardhat alarm and does not mean the worker is safe.
      </p>
    </section>
  );
}
