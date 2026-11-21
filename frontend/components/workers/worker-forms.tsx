"use client";

import { useActionState, useState } from "react";
import { createWorker, endAssignment } from "@/app/actions/assignments";
import { FormMessage, INPUT_CLS, SubmitButton } from "@/components/forms";
import type { Assignment } from "@/lib/assignment-types";
import { INITIAL_FORM_STATE } from "@/lib/form-state";

/** UC-02: minimum worker record only (FR-27). No medical, address or employment fields. */
export function AddWorkerForm() {
  const [state, action, pending] = useActionState(createWorker, INITIAL_FORM_STATE);
  const keep = state.ok ? undefined : state.values;
  return (
    <section aria-labelledby="add-worker-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="add-worker-heading" className="font-semibold">
        Add worker
      </h2>
      {/* key: remount after each result, keeping typed values only when the submit was refused */}
      <form key={state.seq} action={action} className="mt-3 space-y-3">
        <div className="space-y-1.5">
          <label htmlFor="worker-code" className="block text-sm font-medium text-slate-700">
            Internal worker ID
          </label>
          <input
            id="worker-code"
            name="code"
            required
            maxLength={32}
            placeholder="W-004"
            defaultValue={keep?.code ?? ""}
            autoComplete="off"
            className={`${INPUT_CLS} font-mono uppercase`}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor="worker-name" className="block text-sm font-medium text-slate-700">
            Display name
          </label>
          <input
            id="worker-name"
            name="name"
            required
            maxLength={100}
            defaultValue={keep?.name ?? ""}
            autoComplete="off"
            className={INPUT_CLS}
          />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <SubmitButton pending={pending}>Create worker</SubmitButton>
          <FormMessage state={state} />
        </div>
        <p className="text-xs text-slate-500">
          Only the ID and display name are stored. Do not enter medical, address or employment details.
        </p>
      </form>
    </section>
  );
}

/** Close an active interval (POST /api/assignments/{id}/end). Asks for confirmation first. */
export function EndAssignmentControl({ assignment }: { assignment: Assignment }) {
  const [state, action, pending] = useActionState(endAssignment, INITIAL_FORM_STATE);
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="space-y-1">
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-800 hover:bg-slate-50"
        >
          End…
        </button>
        <FormMessage state={state} />
      </div>
    );
  }
  return (
    <form action={action} className="space-y-2">
      <input type="hidden" name="assignmentId" value={assignment.id} />
      <label htmlFor={`end-${assignment.id}`} className="sr-only">
        Reason for ending (optional)
      </label>
      <input
        key={state.seq}
        id={`end-${assignment.id}`}
        name="reason"
        maxLength={200}
        placeholder="Reason (optional), e.g. end of shift"
        defaultValue={state.ok ? "" : (state.values?.reason ?? "")}
        className={`${INPUT_CLS} py-1 text-xs`}
      />
      <div className="flex flex-wrap items-center gap-2">
        <SubmitButton pending={pending} variant="danger">
          End {assignment.worker.code} on {assignment.device.label}
        </SubmitButton>
        <button type="button" onClick={() => setOpen(false)} className="text-xs text-slate-600 hover:underline">
          Cancel
        </button>
      </div>
      <FormMessage state={state} />
    </form>
  );
}
