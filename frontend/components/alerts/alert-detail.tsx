"use client";

// Alert detail and acknowledgment (F26-113 §4.8.3; UC-06..UC-11; FR-34..FR-36, FR-38).
// The source event (type, readings, detection time) is shown as received. Missing context
// (time, assignment, location, readings) is stated, never filled in. Re-fetches every 30 s
// (INTERIM until SSE /api/stream exists).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ResponsePanel } from "@/components/alerts/response-panel";
import { EVENT_LABEL, LOCAL_STATE, PRIORITY } from "@/components/overview/alert-list";
import { Badge, DateTime, type Tone } from "@/components/overview/badge";
import { showReading, type Shown } from "@/components/overview/worker-card";
import type { AlertAction, AlertDetail, AlertDetailEvent, WorkflowState } from "@/lib/alert-types";
import { formatAge } from "@/lib/format";
import { CO_URGENT_PPM, CO_WARNING_PPM } from "@/lib/overview-types";

const REFRESH_MS = 30_000;

const WORKFLOW: Record<WorkflowState, { label: string; tone: Tone }> = {
  open: { label: "Open, needs response", tone: "danger" },
  acknowledged: { label: "Acknowledged, not resolved", tone: "info" },
  resolved: { label: "Resolved", tone: "ok" },
};

const ACTION_LABEL: Record<AlertAction["type"], string> = {
  acknowledge: "Acknowledged",
  note: "Note",
  resolve: "Resolved",
};

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="font-semibold">{title}</h2>
      <div className="mt-2">{children}</div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 py-1.5">
      <dt className="text-sm text-slate-500">{label}</dt>
      <dd className="text-right text-sm font-medium text-slate-900">{children}</dd>
    </div>
  );
}

function ShownValue({ shown }: { shown: Shown }) {
  return (
    <>
      {shown.text}
      {shown.note && (
        <span className="ml-1.5">
          {shown.tone && shown.tone !== "muted" ? (
            <Badge tone={shown.tone}>{shown.note}</Badge>
          ) : (
            <span className="text-xs font-normal text-slate-500">{shown.note}</span>
          )}
        </span>
      )}
    </>
  );
}

function TimesCard({ alert, now }: { alert: AlertDetailEvent; now: number }) {
  return (
    <Card title="Event">
      <p className="text-sm text-slate-700">{alert.detail}</p>
      <dl className="mt-2 divide-y divide-slate-100">
        <Field label="Detected on hardhat">
          {alert.detectedAt ? (
            <>
              <DateTime iso={alert.detectedAt} />
              <span className="block text-xs font-normal text-slate-500">
                {formatAge(now - Date.parse(alert.detectedAt))} ago
                {alert.timeQuality === "estimated" && " · estimated time (clock not synchronised)"}
              </span>
            </>
          ) : (
            <span className="text-amber-800">Detection time unknown (no trustworthy hardhat time)</span>
          )}
        </Field>
        <Field label="Received by server">
          <DateTime iso={alert.receivedAt} />
        </Field>
        <Field label="On the hardhat">{LOCAL_STATE[alert.localState]}</Field>
        <Field label="Hardhat">
          <span className="font-mono">{alert.deviceLabel}</span>
        </Field>
        <Field label="Source event">
          <span className="font-mono text-xs">{alert.sourceEventKey}</span>
        </Field>
      </dl>
    </Card>
  );
}

function WorkerCardDetail({ alert }: { alert: AlertDetailEvent }) {
  const a = alert.assignment;
  return (
    <Card title="Worker">
      {a.state === "resolved" ? (
        <dl className="divide-y divide-slate-100">
          <Field label="Assigned worker">
            {a.worker.name} <span className="font-mono text-xs text-slate-500">{a.worker.code}</span>
          </Field>
          <Field label="Assignment interval">
            <DateTime iso={a.startAt} /> – {a.endAt ? <DateTime iso={a.endAt} /> : "now (active)"}
          </Field>
        </dl>
      ) : (
        <div className="space-y-1 text-sm">
          <p>
            <Badge tone="warning">Worker unknown</Badge>
          </p>
          <p className="text-slate-700">{a.reason}</p>
          <p className="text-xs text-slate-500">
            The event stays linked to hardhat {alert.deviceLabel}. It is not assigned to the current wearer by default.
          </p>
        </div>
      )}
    </Card>
  );
}

function LocationCard({ alert, now }: { alert: AlertDetailEvent; now: number }) {
  const loc = alert.location;
  return (
    <Card title="Location">
      {loc.state === "fix" ? (
        <dl className="divide-y divide-slate-100">
          <Field label="Outdoor GPS fix">
            <span className="font-mono">
              {loc.lat.toFixed(5)}, {loc.lon.toFixed(5)}
            </span>
          </Field>
          <Field label="Fix time">
            {loc.fixAt ? (
              <>
                <DateTime iso={loc.fixAt} />
                <span className="block text-xs font-normal text-slate-500">
                  {formatAge(now - Date.parse(loc.fixAt))} ago
                </span>
              </>
            ) : (
              <>
                unknown
                {loc.fixAgeS !== null && (
                  <span className="block text-xs font-normal text-slate-500">
                    {loc.fixAgeS} s old at detection; detection time unknown
                  </span>
                )}
              </>
            )}
          </Field>
        </dl>
      ) : (
        <div className="space-y-2 text-sm">
          <p>
            <Badge tone="muted">Location unavailable</Badge>
          </p>
          <p className="text-slate-700">No outdoor GPS fix with this event. Indoor position is not supported.</p>
          {loc.lastKnown ? (
            <p className="text-slate-700">
              Last known fix before the event:{" "}
              <span className="font-mono">
                {loc.lastKnown.lat.toFixed(5)}, {loc.lastKnown.lon.toFixed(5)}
              </span>{" "}
              at <DateTime iso={loc.lastKnown.fixAt} /> ({formatAge(now - Date.parse(loc.lastKnown.fixAt))} ago). This
              may not be where the worker is now.
            </p>
          ) : (
            <p className="text-xs text-slate-500">No earlier fix is on record for this hardhat.</p>
          )}
        </div>
      )}
    </Card>
  );
}

function coShown(alert: AlertDetailEvent): Shown {
  const r = alert.readings!.co;
  const s = showReading(r, "ppm");
  if (r.quality !== "valid" || r.value === null) return s;
  if (r.value >= CO_URGENT_PPM) return { ...s, note: "urgent level", tone: "danger" };
  if (r.value >= CO_WARNING_PPM) return { ...s, note: "warning level", tone: "warning" };
  return s;
}

function ReadingsCard({ alert }: { alert: AlertDetailEvent }) {
  const r = alert.readings;
  return (
    <Card title="Readings at detection">
      {r ? (
        <dl className="divide-y divide-slate-100">
          <Field label="CO">
            <ShownValue shown={coShown(alert)} />
          </Field>
          <Field label="Temperature">
            <ShownValue shown={showReading(r.temperature, "°C", 1)} />
          </Field>
          <Field label="Humidity">
            <ShownValue shown={showReading(r.humidity, "%")} />
          </Field>
          <Field label="Heat index">
            <ShownValue shown={showReading(r.heatIndex, "°C", 1)} />
          </Field>
          <Field label="Peak acceleration">
            <ShownValue shown={showReading(r.accelPeak, "g", 2)} />
          </Field>
          <Field label="Battery">
            <ShownValue shown={showReading(r.battery, "%")} />
          </Field>
        </dl>
      ) : (
        <p className="text-sm text-slate-600">No readings were recorded with this event. This is not a zero reading.</p>
      )}
      <p className="mt-2 text-xs text-slate-500">Original values as received. Supervisor actions never change them.</p>
    </Card>
  );
}

function EvidenceCard({ alert }: { alert: AlertDetailEvent }) {
  if (alert.evidence.length === 0) return null;
  return (
    <Card title="Source evidence">
      <dl className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
        {alert.evidence.map((e) => (
          <div key={e.key} className="flex items-baseline justify-between gap-3 border-b border-slate-100 py-1.5">
            <dt className="font-mono text-xs text-slate-500">{e.key}</dt>
            <dd className="font-mono text-xs text-slate-900">{String(e.value)}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function History({ actions }: { actions: AlertAction[] }) {
  return (
    <section aria-labelledby="history-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="history-heading" className="font-semibold">
        Response history
      </h2>
      {actions.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">No supervisor response recorded yet.</p>
      ) : (
        <ol className="mt-3 space-y-3 border-l-2 border-slate-200 pl-4">
          {actions.map((a) => (
            <li key={a.id} className="relative">
              <span aria-hidden="true" className="absolute top-1.5 -left-[1.4rem] h-2.5 w-2.5 rounded-full bg-slate-400" />
              <p className="text-sm">
                <span className="font-semibold">{ACTION_LABEL[a.type]}</span>
                <span className="text-slate-600"> by {a.by}</span>
              </p>
              <p className="text-xs text-slate-500">
                Server time <DateTime iso={a.at} />
              </p>
              {a.note && <p className="mt-1 text-sm whitespace-pre-wrap text-slate-800">{a.note}</p>}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function AlertDetailView({ detail }: { detail: AlertDetail }) {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.parse(detail.generatedAt));
  const { alert, actions, recommendations } = detail;
  const p = PRIORITY[alert.priority];
  const wf = WORKFLOW[alert.state];

  useEffect(() => {
    const tick = setInterval(() => setNow(Date.now()), 1000);
    const refresh = setInterval(() => router.refresh(), REFRESH_MS);
    return () => {
      clearInterval(tick);
      clearInterval(refresh);
    };
  }, [router]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 md:px-8">
      <nav aria-label="Breadcrumb" className="text-sm">
        <Link href="/" className="text-slate-600 hover:text-slate-900 hover:underline">
          ← Overview
        </Link>
      </nav>

      <header className={`rounded-xl border border-l-4 border-slate-200 bg-white p-4 shadow-sm ${p.border}`}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={p.tone}>
            P{alert.priority} · {p.label}
          </Badge>
          <h1 className="text-xl font-semibold">{EVENT_LABEL[alert.type]}</h1>
          <span className="font-mono text-sm text-slate-500">{alert.code}</span>
          {alert.isMock && <Badge tone="muted">Mock data</Badge>}
          <span className="ml-auto">
            <Badge tone={wf.tone}>{wf.label}</Badge>
          </span>
        </div>
        <p className="mt-2 text-sm">
          <span className="font-medium">
            {alert.assignment.state === "resolved" ? alert.assignment.worker.name : "Worker unknown"}
          </span>
          <span className="text-slate-500"> · {alert.deviceLabel}</span>
        </p>
        {alert.supervisorAck && (
          <p className="mt-1 text-xs text-slate-600">
            Acknowledged by {alert.supervisorAck.by} at <DateTime iso={alert.supervisorAck.at} />
          </p>
        )}
      </header>

      <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
        Dashboard actions do not silence the hardhat alarm or cancel a worker&apos;s fall countdown. Acknowledged means
        someone has taken up the response, not that the worker is safe.
      </p>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {recommendations.length > 0 && (
            <section className="rounded-xl border border-sky-200 bg-sky-50 p-4">
              <h2 className="font-semibold text-sky-900">Recommended action</h2>
              <ul className="mt-1 space-y-1">
                {recommendations.map((r) => (
                  <li key={r.code} className="text-sm text-sky-900">
                    {r.message}
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-sky-800">
                From the reviewed recommendation library (version {recommendations[0].version}). Follow the site procedure.
              </p>
            </section>
          )}
          <div className="grid gap-6 md:grid-cols-2">
            <TimesCard alert={alert} now={now} />
            <div className="space-y-6">
              <WorkerCardDetail alert={alert} />
              <LocationCard alert={alert} now={now} />
            </div>
          </div>
          <ReadingsCard alert={alert} />
          <EvidenceCard alert={alert} />
        </div>

        <div className="space-y-6">
          <ResponsePanel alert={alert} />
          <History actions={actions} />
        </div>
      </div>
    </div>
  );
}
