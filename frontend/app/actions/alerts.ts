"use server";

// Supervisor responses to an alert (UC-11; FR-35, FR-36). Each submit is one append-only
// action on the backend; the source event and the hardhat alarm are not changed.
import { refresh } from "next/cache";
import { redirect } from "next/navigation";
import { api, ApiAuthError, ApiRequestError, refusalMessage } from "@/lib/api";
import type { FormState } from "@/lib/form-state";
import { requireSession } from "@/lib/session";

const ACTIONS = new Set(["acknowledge", "note", "resolve"]);

export async function respondToAlert(prev: FormState, formData: FormData): Promise<FormState> {
  const seq = prev.seq + 1;
  const eventId = String(formData.get("eventId") ?? "");
  const action = String(formData.get("action") ?? "");
  const note = String(formData.get("note") ?? "").trim();
  const expectedRowVersion = Number(formData.get("rowVersion"));
  if (!eventId || !ACTIONS.has(action) || !Number.isInteger(expectedRowVersion)) {
    return { ok: false, message: "Invalid request. Reload the page and try again.", seq };
  }
  const values = { note };
  if (action === "note" && !note) return { ok: false, message: "Enter a note before saving.", seq };
  if (action === "resolve" && !note) return { ok: false, message: "Record the outcome before resolving.", seq };

  // An expired session must sign in again; nothing is recorded without one (UC-11 alt flow).
  const { token } = await requireSession();
  try {
    await api(`/api/events/${encodeURIComponent(eventId)}/actions`, {
      method: "POST",
      token,
      body: JSON.stringify({ action, note: note || null, expectedRowVersion }),
    });
  } catch (e) {
    if (e instanceof ApiAuthError) redirect("/sign-in");
    if (e instanceof ApiRequestError) {
      refresh(); // show the latest state instead of overwriting another supervisor's response
      return { ok: false, message: refusalMessage(e, "The response was not recorded."), seq, values };
    }
    return { ok: false, message: "The server is not reachable. The response was NOT recorded. Try again.", seq, values };
  }
  refresh();
  const done = { acknowledge: "Acknowledged.", note: "Note added.", resolve: "Resolved." }[action];
  return { ok: true, message: done ?? null, seq };
}
