"use client";

// Supervisor response (UC-11; FR-35). Acknowledge, note and resolve are separate actions.
// Acknowledged = someone has taken up the response, not that the worker is safe.
import { useActionState } from "react";
import { respondToAlert } from "@/app/actions/alerts";
import { FormMessage, INPUT_CLS, SubmitButton } from "@/components/forms";
import type { AlertDetailEvent } from "@/lib/alert-types";
import { INITIAL_FORM_STATE } from "@/lib/form-state";

function Hidden({ alert, action }: { alert: AlertDetailEvent; action: string }) {
  return (
    <>
      <input type="hidden" name="eventId" value={alert.eventId} />
      <input type="hidden" name="rowVersion" value={alert.rowVersion} />
      <input type="hidden" name="action" value={action} />
    </>
  );
}

function AcknowledgeForm({ alert }: { alert: AlertDetailEvent }) {
  const [state, action, pending] = useActionState(respondToAlert, INITIAL_FORM_STATE);
  return (
    <form action={action} className="space-y-2">
      <Hidden alert={alert} action="acknowledge" />
      <p className="text-sm text-slate-600">
        Acknowledge to record that you have taken up the response. This does not resolve the alert, silence the
        hardhat alarm or mean the worker is safe.
      </p>
      <SubmitButton pending={pending} variant="brand">
        Acknowledge
      </SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}

function NoteForm({ alert, kind }: { alert: AlertDetailEvent; kind: "note" | "resolve" }) {
  const [state, action, pending] = useActionState(respondToAlert, INITIAL_FORM_STATE);
  const resolve = kind === "resolve";
  const id = `${kind}-text`;
  return (
    <form action={action} className="space-y-2">
      <Hidden alert={alert} action={kind} />
      <label htmlFor={id} className="block text-sm font-medium text-slate-700">
        {resolve ? "Outcome (required to resolve)" : "Response note"}
      </label>
      <textarea
        // Remount after each result so a refused submit keeps the typed text and a success clears it.
        key={state.seq}
        id={id}
        name="note"
        rows={3}
        maxLength={1000}
        required
        defaultValue={state.ok ? "" : (state.values?.note ?? "")}
        placeholder={resolve ? "What was done and what was found" : "Action taken, who was contacted, …"}
        className={INPUT_CLS}
      />
      <div className="flex flex-wrap items-center gap-3">
        <SubmitButton pending={pending} variant={resolve ? "primary" : "secondary"}>
          {resolve ? "Resolve alert" : "Add note"}
        </SubmitButton>
        <FormMessage state={state} />
      </div>
      {resolve && (
        <p className="text-xs text-slate-500">
          Resolving closes the dashboard workflow only. It does not clear a hazard that is still active on the hardhat.
        </p>
      )}
    </form>
  );
}

export function ResponsePanel({ alert }: { alert: AlertDetailEvent }) {
  return (
    <section aria-labelledby="respond-heading" className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 id="respond-heading" className="font-semibold">
        Respond
      </h2>
      <div className="mt-3 space-y-5">
        {alert.state === "open" && <AcknowledgeForm alert={alert} />}
        {alert.state === "acknowledged" && <NoteForm alert={alert} kind="resolve" />}
        {alert.state === "resolved" && (
          <p className="text-sm text-slate-600">
            This alert is resolved. Notes can still be added; the original event and history stay unchanged.
          </p>
        )}
        <div className="border-t border-slate-100 pt-4">
          <NoteForm alert={alert} kind="note" />
        </div>
        {alert.state === "open" && (
          <p className="text-xs text-slate-500">Acknowledge the alert before resolving it.</p>
        )}
      </div>
    </section>
  );
}
