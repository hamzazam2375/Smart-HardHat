"use client";

// Create or reassign (UC-03; FR-28). Before confirming, the form shows the selected worker,
// hardhat and every active assignment that conflicts. Each conflicting interval must be
// explicitly selected to be closed; the server re-checks on submit and closes the selected
// interval(s) and opens the new one in one transaction.
import { useActionState, useState } from "react";
import { createAssignment } from "@/app/actions/assignments";
import { FormMessage, INPUT_CLS, SubmitButton } from "@/components/forms";
import { Badge, DateTime } from "@/components/overview/badge";
import type { Assignment, AssignmentsSnapshot } from "@/lib/assignment-types";
import { INITIAL_FORM_STATE } from "@/lib/form-state";

export function AssignForm({ snapshot }: { snapshot: AssignmentsSnapshot }) {
  const [state, action, pending] = useActionState(createAssignment, INITIAL_FORM_STATE);
  const [workerId, setWorkerId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [closing, setClosing] = useState<Record<string, boolean>>({});
  const [seenSeq, setSeenSeq] = useState(0);

  // Clear the selection after a successful assignment (adjust state during render, no effect).
  if (state.seq !== seenSeq) {
    setSeenSeq(state.seq);
    if (state.ok) {
      setWorkerId("");
      setDeviceId("");
      setClosing({});
    }
  }

  const activeWorkers = snapshot.workers.filter((w) => w.active);
  const worker = snapshot.workers.find((w) => w.id === workerId);
  const device = snapshot.devices.find((d) => d.id === deviceId);
  const byId = new Map(snapshot.active.map((a) => [a.id, a]));

  const sameAlready =
    worker?.currentAssignment && device && worker.currentAssignment.deviceId === device.id;
  const conflicts: Assignment[] = [];
  if (worker?.currentAssignment && !sameAlready) {
    const a = byId.get(worker.currentAssignment.assignmentId);
    if (a) conflicts.push(a);
  }
  if (device?.activeAssignmentId && !sameAlready) {
    const a = byId.get(device.activeAssignmentId);
    if (a && !conflicts.some((c) => c.id === a.id)) conflicts.push(a);
  }
  const allSelected = conflicts.every((c) => closing[c.id]);
  const ready = Boolean(worker && device && device.eligible && !sameAlready && allSelected);

  const pick = (setter: (v: string) => void) => (e: React.ChangeEvent<HTMLSelectElement>) => {
    setter(e.target.value);
    setClosing({});
  };

  return (
    <section aria-labelledby="assign-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="assign-heading" className="font-semibold">
        Assign a hardhat
      </h2>
      <p className="mt-0.5 text-xs text-slate-500">Starts now (server time). One active assignment per worker and per hardhat.</p>

      <form action={action} className="mt-4 space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <label htmlFor="assign-worker" className="block text-sm font-medium text-slate-700">
              Worker
            </label>
            <select id="assign-worker" name="workerId" value={workerId} onChange={pick(setWorkerId)} className={INPUT_CLS}>
              <option value="">Select a worker…</option>
              {activeWorkers.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.code} · {w.name}
                  {w.currentAssignment ? ` (wearing ${w.currentAssignment.deviceLabel})` : ""}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1.5">
            <label htmlFor="assign-device" className="block text-sm font-medium text-slate-700">
              Hardhat
            </label>
            <select id="assign-device" name="deviceId" value={deviceId} onChange={pick(setDeviceId)} className={INPUT_CLS}>
              <option value="">Select a hardhat…</option>
              {snapshot.devices.map((d) => {
                const holder = d.activeAssignmentId ? byId.get(d.activeAssignmentId) : undefined;
                return (
                  <option key={d.id} value={d.id} disabled={!d.eligible}>
                    {d.label}
                    {!d.eligible ? ` (${d.state}, cannot be assigned)` : holder ? ` (with ${holder.worker.code})` : " (available)"}
                  </option>
                );
              })}
            </select>
          </div>
        </div>

        {worker && device && (
          <div className="space-y-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm">
            <p className="font-medium">Review before confirming</p>
            <dl className="grid gap-1 sm:grid-cols-[8rem_1fr]">
              <dt className="text-slate-500">Worker</dt>
              <dd>
                <span className="font-mono">{worker.code}</span> · {worker.name}
              </dd>
              <dt className="text-slate-500">Hardhat</dt>
              <dd>
                <span className="font-mono">{device.label}</span>{" "}
                {device.activeAssignmentId ? <Badge tone="warning">in use</Badge> : <Badge tone="ok">available</Badge>}
              </dd>
              <dt className="text-slate-500">Start</dt>
              <dd>Now, when confirmed</dd>
            </dl>

            {sameAlready && (
              <p className="text-slate-700">
                <Badge tone="info">No change</Badge> {worker.code} is already wearing {device.label}.
              </p>
            )}

            {conflicts.length > 0 && (
              <fieldset className="space-y-2">
                <legend className="font-medium text-amber-900">
                  Conflicting active assignment{conflicts.length > 1 ? "s" : ""}: select to end now
                </legend>
                {conflicts.map((c) => (
                  <label key={c.id} className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-2">
                    <input
                      type="checkbox"
                      name="close"
                      value={c.id}
                      checked={Boolean(closing[c.id])}
                      onChange={(e) => setClosing((s) => ({ ...s, [c.id]: e.target.checked }))}
                      className="mt-0.5"
                    />
                    <span>
                      End <span className="font-mono">{c.worker.code}</span> ({c.worker.name}) on{" "}
                      <span className="font-mono">{c.device.label}</span>, active since <DateTime iso={c.startAt} />
                    </span>
                  </label>
                ))}
                <p className="text-xs text-slate-600">
                  The selected interval ends and the new one starts in a single step, so two conflicting active
                  assignments are never saved. Earlier events keep the worker of their own interval.
                </p>
              </fieldset>
            )}
          </div>
        )}

        <input type="hidden" name="confirm" value="yes" />
        <div className="flex flex-wrap items-center gap-3">
          <SubmitButton pending={pending} variant="brand" disabled={!ready}>
            {conflicts.length ? "Confirm reassignment" : "Confirm assignment"}
          </SubmitButton>
          <FormMessage state={state} />
        </div>
      </form>
    </section>
  );
}
