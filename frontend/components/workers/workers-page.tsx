"use client";

// Workers and worker-to-device assignment (F26-113 §4.8.4; UC-02, UC-03; FR-27, FR-28).
// History keeps earlier intervals visible so the current wearer can be told apart from the
// worker of an earlier shift. Re-fetches every 30 s (INTERIM until SSE).
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Badge, DateTime } from "@/components/overview/badge";
import type { Assignment, AssignmentsSnapshot } from "@/lib/assignment-types";
import { formatAge } from "@/lib/format";
import { AssignForm } from "./assign-form";
import { AddWorkerForm, EndAssignmentControl } from "./worker-forms";

const REFRESH_MS = 30_000;

const TH = "px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500";
const TD = "px-3 py-2 align-top text-sm";

function Who({ a }: { a: Assignment }) {
  return (
    <>
      <span className="font-mono text-xs text-slate-500">{a.worker.code}</span>
      <span className="block">{a.worker.name}</span>
    </>
  );
}

function ActiveTable({ active }: { active: Assignment[] }) {
  return (
    <section aria-labelledby="active-heading" className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="p-4 pb-2">
        <h2 id="active-heading" className="font-semibold">
          Active assignments
        </h2>
      </div>
      {active.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-slate-600">No hardhat is assigned. Unassigned hardhats show no worker.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead>
              <tr>
                <th scope="col" className={TH}>Worker</th>
                <th scope="col" className={TH}>Hardhat</th>
                <th scope="col" className={TH}>Started</th>
                <th scope="col" className={TH}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {active.map((a) => (
                <tr key={a.id}>
                  <td className={TD}>
                    <Who a={a} />
                  </td>
                  <td className={`${TD} font-mono`}>{a.device.label}</td>
                  <td className={TD}>
                    <DateTime iso={a.startAt} />
                    <span className="block text-xs text-slate-500">by {a.createdBy}</span>
                  </td>
                  <td className={`${TD} w-64`}>
                    <EndAssignmentControl assignment={a} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function HistoryTable({ history }: { history: Assignment[] }) {
  return (
    <section aria-labelledby="assign-history-heading" className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2 p-4 pb-2">
        <h2 id="assign-history-heading" className="font-semibold">
          Assignment history
        </h2>
        <p className="text-xs text-slate-500">Ended in the last 30 days (retention period), newest first</p>
      </div>
      {history.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-slate-600">No ended assignments in the retention period.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead>
              <tr>
                <th scope="col" className={TH}>Worker</th>
                <th scope="col" className={TH}>Hardhat</th>
                <th scope="col" className={TH}>Interval</th>
                <th scope="col" className={TH}>Ended by</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {history.map((a) => (
                <tr key={a.id}>
                  <td className={TD}>
                    <Who a={a} />
                  </td>
                  <td className={`${TD} font-mono`}>{a.device.label}</td>
                  <td className={TD}>
                    <DateTime iso={a.startAt} /> – {a.endAt && <DateTime iso={a.endAt} />}
                    {a.endAt && (
                      <span className="block text-xs text-slate-500">
                        {formatAge(Date.parse(a.endAt) - Date.parse(a.startAt))}
                      </span>
                    )}
                  </td>
                  <td className={TD}>
                    {a.endedBy ?? "—"}
                    {a.reason && <span className="block text-xs text-slate-500">{a.reason}</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function WorkerList({ snapshot }: { snapshot: AssignmentsSnapshot }) {
  return (
    <section aria-labelledby="workers-list-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="workers-list-heading" className="font-semibold">
        Workers <span className="text-sm font-normal text-slate-500">({snapshot.workers.length})</span>
      </h2>
      {snapshot.workers.length === 0 ? (
        <p className="mt-2 text-sm text-slate-600">No worker records yet. Add one above.</p>
      ) : (
        <ul className="mt-2 divide-y divide-slate-100">
          {snapshot.workers.map((w) => (
            <li key={w.id} className="flex items-start justify-between gap-2 py-2 text-sm">
              <span className="min-w-0">
                <span className="font-mono text-xs text-slate-500">{w.code}</span>
                <span className="block truncate">{w.name}</span>
              </span>
              {!w.active ? (
                <Badge tone="muted">Inactive</Badge>
              ) : w.currentAssignment ? (
                <Badge tone="ok">{w.currentAssignment.deviceLabel}</Badge>
              ) : (
                <span className="text-xs text-slate-500">Not assigned</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function WorkersPage({ snapshot }: { snapshot: AssignmentsSnapshot }) {
  const router = useRouter();
  useEffect(() => {
    const refresh = setInterval(() => router.refresh(), REFRESH_MS);
    return () => clearInterval(refresh);
  }, [router]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 md:px-8">
      <header>
        <h1 className="text-2xl font-semibold">Workers and assignments</h1>
        <p className="text-sm text-slate-500">
          Link a worker to a registered hardhat for a shift. Start and end times decide which worker a delayed event
          belongs to.
        </p>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <AssignForm snapshot={snapshot} />
          <ActiveTable active={snapshot.active} />
        </div>
        <div className="space-y-6">
          <AddWorkerForm />
          <WorkerList snapshot={snapshot} />
        </div>
      </div>

      <HistoryTable history={snapshot.history} />
    </div>
  );
}
